"""Animate Photo is its own isolated Quick Tool generation flow, same
pattern as Enhance Photo/Remove Object/Remove Background/Try-On/Character
Replace, but for VIDEO instead of image: its request must be built from
exactly two tool-owned inputs (video_options.animatePhotoSourceUrl,
mandatory, and video_options.animatePhotoPrompt, optional/<=250 chars) and
never from normal Pro Studio composer state (Character/Object/Style/prompt/
references/previous video state). It calls Runway's real Gen-4.5
image-to-video API - POST https://api.dev.runwayml.com/v1/image_to_video,
JSON body, Bearer auth via RUNWAYML_API_SECRET, X-Runway-Version:
2024-11-06, model="gen4.5", duration=5 fixed (no model/duration/resolution/
ratio selector) - then async polling of GET /v1/tasks/{id} for the literal
`status` field until SUCCEEDED/FAILED/CANCELED, then the literal `output`
array's first entry is the result video URL.

Runway's own output URL is ephemeral, so generate_animate_photo_video must
download and persist it to durable SYLVEX storage synchronously, inside the
function itself, before ever returning - never leaving Runway's temporary
URL as the result. These tests cover is_animate_photo_request, the
dedicated pricing branch (flat 90 credits), the output-ratio selector (~
nearest supported Gen-4.5 ratio to the source aspect ratio) and the source
aspect-ratio validator (0.5-2.0), the async submit+poll+download provider
flow (id/status/output handling, FAILED/CANCELED/timeout/throttled),
synchronous persistence of the ephemeral result URL, that leaked
normal-composer noise never reaches the request, and dispatch precedence
over the generic video_generation() route - including the real
frontend-shaped payload end to end."""
import asyncio
import base64
import io
import json

import main


def _png_data_uri_sized(width, height):
    from PIL import Image

    img = Image.new("RGB", (width, height), (20, 40, 60))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    encoded = base64.b64encode(buf.getvalue()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def _png_data_uri():
    return _png_data_uri_sized(1280, 720)


class _FakeResponse:
    headers = {"content-type": "application/json"}
    content = b"final-animated-video-bytes"

    def __init__(self, status_code=200, payload=None, text=None, headers=None, content=None):
        self.status_code = status_code
        self.text = json.dumps(payload) if payload is not None else (text or "")
        if headers is not None:
            self.headers = headers
        if content is not None:
            self.content = content

    def raise_for_status(self):
        return None


RUNWAY_RESULT_URL = "https://dnznrvs05pmza.cloudfront.net/ephemeral/result-abc123.mp4"


def _fake_runway_headers():
    return {
        "Authorization": "Bearer test-runway-key",
        "Content-Type": "application/json",
        "X-Runway-Version": "2024-11-06",
    }


def _fake_storage_key_from_url(url):
    return url.split("https://cdn.example.com/", 1)[1] if url.startswith("https://cdn.example.com/") else ""


def _animate_photo_payload(**overrides):
    opts = {
        "tool": "animate_photo",
        "animatePhotoSourceUrl": _png_data_uri(),
        "animatePhotoPrompt": "",
    }
    opts.update(overrides)
    return {
        "telegram_id": 0,
        "job_id": "",
        "video_options": opts,
    }


def _fake_safe_get_poll(status="SUCCEEDED", output_url=RUNWAY_RESULT_URL, data_override=None):
    def _fake_safe_get(url, headers=None, timeout=None):
        payload = data_override if data_override is not None else {"status": status, "output": [output_url] if output_url else []}
        return _FakeResponse(200, payload)
    return _fake_safe_get


def _apply_success_mocks(monkeypatch, task_id="task_123", status="SUCCEEDED", output_url=RUNWAY_RESULT_URL):
    monkeypatch.setattr(main, "runway_animate_photo_headers", _fake_runway_headers)
    monkeypatch.setattr(main.requests, "post", lambda *a, **k: _FakeResponse(200, {"id": task_id}))
    monkeypatch.setattr(main, "safe_get", _fake_safe_get_poll(status=status, output_url=output_url))
    monkeypatch.setattr(main.time, "sleep", lambda *a, **k: None)
    monkeypatch.setattr(main, "storage_put_bytes", lambda content, key, content_type: f"https://cdn.example.com/{key}")
    monkeypatch.setattr(main, "storage_key_from_url", _fake_storage_key_from_url)
    monkeypatch.setattr(main, "_send_generated_videos_to_telegram", lambda *a, **k: True)


# --- Tool identifier / dispatch predicate -----------------------------------

def test_is_animate_photo_request_detects_tool_flag():
    assert main.is_animate_photo_request({"video_options": {"tool": "animate_photo"}}) is True
    assert main.is_animate_photo_request({"video_options": {"tool": "runway_gen4_5"}}) is False
    assert main.is_animate_photo_request({"video_options": {}}) is False
    assert main.is_animate_photo_request({}) is False


def test_is_animate_photo_request_ignores_case_and_whitespace():
    assert main.is_animate_photo_request({"video_options": {"tool": " Animate_Photo "}}) is True


def test_animate_photo_tool_never_collides_with_isolated_image_tools():
    payload = {"video_options": {"tool": "animate_photo"}}
    assert main.is_animate_photo_request(payload) is True
    assert main.is_enhance_photo_request(payload) is False
    assert main.is_remove_object_request(payload) is False
    assert main.is_try_on_request(payload) is False
    assert main.is_remove_bg_request(payload) is False
    assert main.is_replace_character_request(payload) is False


# --- Pricing -----------------------------------------------------------------

def test_animate_photo_cost_info_is_flat_90_credits():
    info = main.animate_photo_cost_info()
    assert info["credits"] == 90
    assert info["cost_credits"] == 90
    assert info["generation_cost"] == "90 ⚡"


def test_animate_photo_pricing_derives_from_configurable_runway_rate_constants():
    # 12 credits/sec (RUNWAY_GEN45_CREDITS_PER_SECOND) * 5s (duration) *
    # $0.01/credit (RUNWAY_CREDIT_COST_USD) = $0.60 provider cost;
    # * 1.5 markup = $0.90 -> 90 credits. The rates are named constants, not
    # inline literals, so they can be updated in one place.
    assert main.RUNWAY_GEN45_CREDITS_PER_SECOND == 12
    assert main.RUNWAY_CREDIT_COST_USD == 0.01
    assert main.ANIMATE_PHOTO_DURATION_SECONDS == 5
    assert main.ANIMATE_PHOTO_MARKUP == 1.5
    import math
    provider_cost = main.RUNWAY_GEN45_CREDITS_PER_SECOND * main.ANIMATE_PHOTO_DURATION_SECONDS * main.RUNWAY_CREDIT_COST_USD
    expected_credits = int(math.ceil(round(provider_cost * main.ANIMATE_PHOTO_MARKUP * 100, 6)))
    assert main.animate_photo_cost_info()["credits"] == expected_credits == 90


def test_estimate_generation_cost_prices_animate_photo_flat_fee():
    estimate = main.estimate_generation_cost({
        "mode": "video",
        "video_options": {"tool": "animate_photo"},
    })
    assert estimate["credits"] == 90
    assert estimate["pricing_available"] is True
    assert estimate["operation"] == "animate_photo"


def test_estimate_generation_cost_animate_photo_never_reaches_generic_video_pricing_table(monkeypatch):
    def _explode(*a, **k):
        raise AssertionError("must never fall through to estimate_video_generation_cost for an animate_photo payload")

    monkeypatch.setattr(main, "estimate_video_generation_cost", _explode)
    estimate = main.estimate_generation_cost({
        "mode": "video",
        "video_options": {"tool": "animate_photo"},
    })
    assert estimate["credits"] == 90


# --- Output ratio selection & source aspect-ratio validation -----------------

def test_animate_photo_select_output_ratio_exact_landscape_match():
    assert main.animate_photo_select_output_ratio(1920, 1080) == "1280:720"


def test_animate_photo_select_output_ratio_exact_portrait_match():
    assert main.animate_photo_select_output_ratio(1080, 1920) == "720:1280"


def test_animate_photo_select_output_ratio_exact_square_match():
    assert main.animate_photo_select_output_ratio(1000, 1000) == "960:960"


def test_animate_photo_select_output_ratio_nearest_for_4_3():
    # 4:3 (ratio 1.333) is closest to 1104:832 (ratio ~1.327) among the
    # documented Gen-4.5 output ratios.
    assert main.animate_photo_select_output_ratio(1200, 900) == "1104:832"


def test_animate_photo_select_output_ratio_never_stretches_never_selects_unsupported_value():
    for width, height in [(1920, 1080), (1080, 1920), (1000, 1000), (1200, 900), (900, 1200)]:
        ratio = main.animate_photo_select_output_ratio(width, height)
        assert tuple(int(x) for x in ratio.split(":")) in main.ANIMATE_PHOTO_SUPPORTED_RATIOS


def test_animate_photo_source_ratio_supported_within_bounds():
    assert main.animate_photo_source_ratio_supported(200, 100) is True  # ratio 2.0, boundary
    assert main.animate_photo_source_ratio_supported(100, 200) is True  # ratio 0.5, boundary
    assert main.animate_photo_source_ratio_supported(1920, 1080) is True


def test_animate_photo_source_ratio_supported_rejects_out_of_range():
    assert main.animate_photo_source_ratio_supported(300, 100) is False  # ratio 3.0
    assert main.animate_photo_source_ratio_supported(100, 300) is False  # ratio 0.333


# --- Isolated provider call: validation & request shape ----------------------

def test_generate_animate_photo_video_requires_source_image(monkeypatch):
    monkeypatch.setattr(main, "runway_animate_photo_headers", _fake_runway_headers)
    result = asyncio.run(main.generate_animate_photo_video({
        "video_options": {"tool": "animate_photo"},
    }))
    assert result["ok"] is False


def test_generate_animate_photo_video_requires_api_key(monkeypatch):
    monkeypatch.setattr(main, "runway_animate_photo_headers", lambda: {})
    result = asyncio.run(main.generate_animate_photo_video(_animate_photo_payload()))
    assert result["ok"] is False


def test_generate_animate_photo_video_rejects_prompt_over_250_chars(monkeypatch):
    def _explode(*a, **k):
        raise AssertionError("must never call the provider with an over-limit prompt")

    monkeypatch.setattr(main, "runway_animate_photo_headers", _fake_runway_headers)
    monkeypatch.setattr(main.requests, "post", _explode)
    payload = _animate_photo_payload(animatePhotoPrompt="x" * 251)
    result = asyncio.run(main.generate_animate_photo_video(payload))
    assert result["ok"] is False


def test_generate_animate_photo_video_accepts_exactly_250_char_prompt(monkeypatch):
    captured = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        captured["prompt_text"] = json["promptText"]
        return _FakeResponse(200, {"id": "task_1"})

    _apply_success_mocks(monkeypatch)
    monkeypatch.setattr(main.requests, "post", fake_post)
    payload = _animate_photo_payload(animatePhotoPrompt="y" * 250)
    result = asyncio.run(main.generate_animate_photo_video(payload))
    assert result["ok"] is True
    assert captured["prompt_text"] == "y" * 250


def test_generate_animate_photo_video_uses_internal_default_prompt_when_empty(monkeypatch):
    captured = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        captured["prompt_text"] = json["promptText"]
        return _FakeResponse(200, {"id": "task_1"})

    _apply_success_mocks(monkeypatch)
    monkeypatch.setattr(main.requests, "post", fake_post)
    payload = _animate_photo_payload(animatePhotoPrompt="")
    result = asyncio.run(main.generate_animate_photo_video(payload))
    assert result["ok"] is True
    assert captured["prompt_text"] == main.ANIMATE_PHOTO_DEFAULT_PROMPT
    # The internal default must never be echoed back as if the user typed it.
    assert result.get("prompt") != main.ANIMATE_PHOTO_DEFAULT_PROMPT or "prompt" not in result


def test_generate_animate_photo_video_uses_user_prompt_when_provided(monkeypatch):
    captured = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        captured["prompt_text"] = json["promptText"]
        return _FakeResponse(200, {"id": "task_1"})

    _apply_success_mocks(monkeypatch)
    monkeypatch.setattr(main.requests, "post", fake_post)
    payload = _animate_photo_payload(animatePhotoPrompt="She smiles and looks at the camera")
    result = asyncio.run(main.generate_animate_photo_video(payload))
    assert result["ok"] is True
    assert captured["prompt_text"] == "She smiles and looks at the camera"


def test_generate_animate_photo_video_rejects_unsupported_format(monkeypatch):
    def _explode(*a, **k):
        raise AssertionError("must never call the provider with an unsupported source format")

    monkeypatch.setattr(main, "runway_animate_photo_headers", _fake_runway_headers)
    monkeypatch.setattr(main.requests, "post", _explode)
    bogus_uri = "data:image/gif;base64," + base64.b64encode(b"GIF89a-not-supported").decode("ascii")
    result = asyncio.run(main.generate_animate_photo_video(_animate_photo_payload(animatePhotoSourceUrl=bogus_uri)))
    assert result["ok"] is False


def test_generate_animate_photo_video_rejects_unsupported_source_aspect_ratio(monkeypatch):
    def _explode(*a, **k):
        raise AssertionError("must never submit a paid Runway task for an unsupported source aspect ratio")

    monkeypatch.setattr(main, "runway_animate_photo_headers", _fake_runway_headers)
    monkeypatch.setattr(main.requests, "post", _explode)
    # 3000x900 -> ratio 3.333, outside the documented 0.5-2.0 range.
    wide_uri = _png_data_uri_sized(3000, 900)
    result = asyncio.run(main.generate_animate_photo_video(_animate_photo_payload(animatePhotoSourceUrl=wide_uri)))
    assert result["ok"] is False


def test_generate_animate_photo_video_sends_correct_runway_request_shape(monkeypatch):
    captured = {}
    source_uri = _png_data_uri_sized(1920, 1080)

    def fake_post(url, headers=None, json=None, timeout=None):
        captured["url"] = url
        captured["headers"] = headers
        captured["json"] = json
        return _FakeResponse(200, {"id": "task_1"})

    monkeypatch.setattr(main, "runway_animate_photo_headers", _fake_runway_headers)
    monkeypatch.setattr(main.requests, "post", fake_post)
    monkeypatch.setattr(main, "safe_get", _fake_safe_get_poll())
    monkeypatch.setattr(main.time, "sleep", lambda *a, **k: None)
    monkeypatch.setattr(main, "storage_put_bytes", lambda content, key, content_type: f"https://cdn.example.com/{key}")
    monkeypatch.setattr(main, "storage_key_from_url", _fake_storage_key_from_url)
    monkeypatch.setattr(main, "_send_generated_videos_to_telegram", lambda *a, **k: True)

    result = asyncio.run(main.generate_animate_photo_video(_animate_photo_payload(animatePhotoSourceUrl=source_uri)))

    assert result["ok"] is True
    # Exact endpoint from Runway's official Gen-4.5 async contract.
    assert captured["url"] == "https://api.dev.runwayml.com/v1/image_to_video"
    # Exact auth header - Bearer, never Api-Key/X-API-KEY.
    assert captured["headers"]["Authorization"] == "Bearer test-runway-key"
    assert captured["headers"]["X-Runway-Version"] == "2024-11-06"
    # Exact documented model/duration - never invented extra fields.
    assert captured["json"]["model"] == "gen4.5"
    assert captured["json"]["duration"] == 5
    assert set(captured["json"].keys()) == {"model", "promptImage", "promptText", "ratio", "duration"}
    assert captured["json"]["ratio"] == "1280:720"
    assert captured["json"]["promptImage"].startswith(("http://", "https://"))


def test_generate_animate_photo_video_ignores_leaked_normal_pro_studio_state(monkeypatch):
    captured = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        captured["json"] = json
        return _FakeResponse(200, {"id": "task_1"})

    _apply_success_mocks(monkeypatch)
    monkeypatch.setattr(main.requests, "post", fake_post)

    payload = _animate_photo_payload(
        characterId="char_1",
        characterReferences=["https://example.com/leak1.png"],
        objectReferences=["https://example.com/leak2.png"],
        style="oil_painting_style_leak",
    )
    payload["prompt"] = "a totally unrelated leaked prompt describing a dragon"
    result = asyncio.run(main.generate_animate_photo_video(payload))
    assert result["ok"] is True
    # Only the two tool-owned fields ever shape the request.
    assert "oil_painting_style_leak" not in json.dumps(captured["json"])
    assert "dragon" not in json.dumps(captured["json"])
    assert "leak1.png" not in json.dumps(captured["json"])
    assert "leak2.png" not in json.dumps(captured["json"])


# --- Async submit -> poll -> download flow ------------------------------------

def test_generate_animate_photo_video_handles_missing_task_id(monkeypatch):
    monkeypatch.setattr(main, "runway_animate_photo_headers", _fake_runway_headers)
    monkeypatch.setattr(main.requests, "post", lambda *a, **k: _FakeResponse(200, {}))
    result = asyncio.run(main.generate_animate_photo_video(_animate_photo_payload()))
    assert result["ok"] is False


def test_poll_animate_photo_task_handles_pending_then_running_then_succeeded(monkeypatch):
    statuses = iter(["PENDING", "RUNNING", "SUCCEEDED"])

    def fake_safe_get(url, headers=None, timeout=None):
        status = next(statuses)
        payload = {"status": status}
        if status == "SUCCEEDED":
            payload["output"] = [RUNWAY_RESULT_URL]
        return _FakeResponse(200, payload)

    monkeypatch.setattr(main, "safe_get", fake_safe_get)
    monkeypatch.setattr(main.time, "sleep", lambda *a, **k: None)
    ok, output_url, error = main.poll_animate_photo_task("task_1", _fake_runway_headers())
    assert ok is True
    assert output_url == RUNWAY_RESULT_URL
    assert error == {}


def test_poll_animate_photo_task_handles_throttled_non_terminal_state(monkeypatch):
    statuses = iter(["THROTTLED", "THROTTLED", "SUCCEEDED"])

    def fake_safe_get(url, headers=None, timeout=None):
        status = next(statuses)
        payload = {"status": status}
        if status == "SUCCEEDED":
            payload["output"] = [RUNWAY_RESULT_URL]
        return _FakeResponse(200, payload)

    monkeypatch.setattr(main, "safe_get", fake_safe_get)
    monkeypatch.setattr(main.time, "sleep", lambda *a, **k: None)
    ok, output_url, error = main.poll_animate_photo_task("task_1", _fake_runway_headers())
    assert ok is True
    assert output_url == RUNWAY_RESULT_URL


def test_poll_animate_photo_task_handles_failed(monkeypatch):
    monkeypatch.setattr(main, "safe_get", lambda url, headers=None, timeout=None: _FakeResponse(200, {"status": "FAILED", "failureCode": "INTERNAL.BAD_OUTPUT", "failureReason": "internal error"}))
    ok, output_url, error = main.poll_animate_photo_task("task_1", _fake_runway_headers())
    assert ok is False
    assert output_url is None
    assert error.get("ok") is False
    # failureCode/failureReason are diagnostics only - never in the
    # user-facing error/message text.
    assert "INTERNAL.BAD_OUTPUT" not in (error.get("error") or "")
    assert "INTERNAL.BAD_OUTPUT" not in (error.get("message") or "")


def test_poll_animate_photo_task_handles_canceled(monkeypatch):
    monkeypatch.setattr(main, "safe_get", lambda url, headers=None, timeout=None: _FakeResponse(200, {"status": "CANCELED"}))
    ok, output_url, error = main.poll_animate_photo_task("task_1", _fake_runway_headers())
    assert ok is False
    assert output_url is None
    assert error.get("ok") is False


def test_poll_animate_photo_task_times_out(monkeypatch):
    monkeypatch.setattr(main, "safe_get", lambda url, headers=None, timeout=None: _FakeResponse(200, {"status": "RUNNING"}))
    monkeypatch.setattr(main.time, "sleep", lambda *a, **k: None)
    ok, output_url, error = main.poll_animate_photo_task("task_1", _fake_runway_headers(), max_attempts=3)
    assert ok is False
    assert output_url is None
    assert error.get("ok") is False


def test_poll_animate_photo_task_backs_off_on_5xx_then_recovers(monkeypatch):
    responses = iter([
        _FakeResponse(503, text="service unavailable"),
        _FakeResponse(200, {"status": "SUCCEEDED", "output": [RUNWAY_RESULT_URL]}),
    ])
    monkeypatch.setattr(main, "safe_get", lambda url, headers=None, timeout=None: next(responses))
    monkeypatch.setattr(main.time, "sleep", lambda *a, **k: None)
    ok, output_url, error = main.poll_animate_photo_task("task_1", _fake_runway_headers())
    assert ok is True
    assert output_url == RUNWAY_RESULT_URL


def test_poll_animate_photo_task_backs_off_on_429_then_recovers(monkeypatch):
    responses = iter([
        _FakeResponse(429, text="rate limited"),
        _FakeResponse(200, {"status": "SUCCEEDED", "output": [RUNWAY_RESULT_URL]}),
    ])
    monkeypatch.setattr(main, "safe_get", lambda url, headers=None, timeout=None: next(responses))
    monkeypatch.setattr(main.time, "sleep", lambda *a, **k: None)
    ok, output_url, error = main.poll_animate_photo_task("task_1", _fake_runway_headers())
    assert ok is True


def test_generate_animate_photo_video_handles_missing_output(monkeypatch):
    monkeypatch.setattr(main, "runway_animate_photo_headers", _fake_runway_headers)
    monkeypatch.setattr(main.requests, "post", lambda *a, **k: _FakeResponse(200, {"id": "task_1"}))
    monkeypatch.setattr(main, "safe_get", lambda url, headers=None, timeout=None: _FakeResponse(200, {"status": "SUCCEEDED", "output": []}))
    monkeypatch.setattr(main.time, "sleep", lambda *a, **k: None)
    result = asyncio.run(main.generate_animate_photo_video(_animate_photo_payload()))
    assert result["ok"] is False


def test_generate_animate_photo_video_handles_provider_submit_error_response(monkeypatch):
    monkeypatch.setattr(main, "runway_animate_photo_headers", _fake_runway_headers)
    monkeypatch.setattr(main.requests, "post", lambda *a, **k: _FakeResponse(400, text="bad request"))
    result = asyncio.run(main.generate_animate_photo_video(_animate_photo_payload()))
    assert result["ok"] is False


def test_generate_animate_photo_video_handles_network_error(monkeypatch):
    import requests as requests_module

    def fake_post(*a, **k):
        raise requests_module.exceptions.ConnectionError("boom")

    monkeypatch.setattr(main, "runway_animate_photo_headers", _fake_runway_headers)
    monkeypatch.setattr(main.requests, "post", fake_post)
    result = asyncio.run(main.generate_animate_photo_video(_animate_photo_payload()))
    assert result["ok"] is False


def test_generate_animate_photo_video_never_submits_a_second_runway_task(monkeypatch):
    submit_calls = []

    def fake_post(url, headers=None, json=None, timeout=None):
        submit_calls.append(url)
        return _FakeResponse(200, {"id": "task_1"})

    _apply_success_mocks(monkeypatch)
    monkeypatch.setattr(main.requests, "post", fake_post)

    result = asyncio.run(main.generate_animate_photo_video(_animate_photo_payload()))
    assert result["ok"] is True
    assert len(submit_calls) == 1


# --- Persistence to durable SYLVEX storage ------------------------------------

def test_generate_animate_photo_video_persists_ephemeral_url_to_durable_storage(monkeypatch):
    monkeypatch.setattr(main, "runway_animate_photo_headers", _fake_runway_headers)
    monkeypatch.setattr(main.requests, "post", lambda *a, **k: _FakeResponse(200, {"id": "task_1"}))
    monkeypatch.setattr(main, "safe_get", _fake_safe_get_poll())
    monkeypatch.setattr(main.time, "sleep", lambda *a, **k: None)

    persist_calls = []

    def fake_persist(url, category, provider=""):
        persist_calls.append((url, category, provider))
        return "https://cdn.example.com/videos/final-animated.mp4"

    monkeypatch.setattr(main, "_persist_remote_media_url", fake_persist)
    monkeypatch.setattr(main, "storage_key_from_url", lambda url: "videos/final-animated.mp4" if "cdn.example.com" in url else "")
    monkeypatch.setattr(main, "_send_generated_videos_to_telegram", lambda *a, **k: True)

    result = asyncio.run(main.generate_animate_photo_video(_animate_photo_payload()))
    assert result["ok"] is True
    assert result["video_url"] == "https://cdn.example.com/videos/final-animated.mp4"
    assert result["videos"] == ["https://cdn.example.com/videos/final-animated.mp4"]
    assert RUNWAY_RESULT_URL not in json.dumps(result)
    assert persist_calls == [(RUNWAY_RESULT_URL, "videos", "runway")]


def test_generate_animate_photo_video_fails_when_storage_persist_fails(monkeypatch):
    monkeypatch.setattr(main, "runway_animate_photo_headers", _fake_runway_headers)
    monkeypatch.setattr(main.requests, "post", lambda *a, **k: _FakeResponse(200, {"id": "task_1"}))
    monkeypatch.setattr(main, "safe_get", _fake_safe_get_poll())
    monkeypatch.setattr(main.time, "sleep", lambda *a, **k: None)
    monkeypatch.setattr(main, "_persist_remote_media_url", lambda url, category, provider="": url)
    monkeypatch.setattr(main, "storage_key_from_url", lambda url: "")

    result = asyncio.run(main.generate_animate_photo_video(_animate_photo_payload()))
    assert result["ok"] is False


# --- Result fields / Telegram delivery ----------------------------------------

def test_generate_animate_photo_video_result_carries_cost_and_provider_fields(monkeypatch):
    _apply_success_mocks(monkeypatch)
    result = asyncio.run(main.generate_animate_photo_video(_animate_photo_payload()))
    assert result["ok"] is True
    assert result["provider"] == "runway"
    assert result["tool"] == "animate_photo"
    assert result["provider_model"] == "gen4.5"
    assert result["duration"] == 5
    assert result["cost_credits"] == 90
    assert result["generation_cost"] == "90 ⚡"


def test_generate_animate_photo_video_sends_telegram_delivery(monkeypatch):
    monkeypatch.setattr(main, "runway_animate_photo_headers", _fake_runway_headers)
    monkeypatch.setattr(main.requests, "post", lambda *a, **k: _FakeResponse(200, {"id": "task_1"}))
    monkeypatch.setattr(main, "safe_get", _fake_safe_get_poll())
    monkeypatch.setattr(main.time, "sleep", lambda *a, **k: None)
    monkeypatch.setattr(main, "storage_put_bytes", lambda content, key, content_type: f"https://cdn.example.com/{key}")
    monkeypatch.setattr(main, "storage_key_from_url", _fake_storage_key_from_url)

    telegram_calls = []

    async def fake_telegram(telegram_id, videos, caption=""):
        telegram_calls.append((telegram_id, videos, caption))
        return True

    monkeypatch.setattr(main, "_send_generated_videos_to_telegram", fake_telegram)

    payload = _animate_photo_payload()
    payload["telegram_id"] = 555
    result = asyncio.run(main.generate_animate_photo_video(payload))
    assert result["ok"] is True
    assert result["sent_to_telegram"] is True
    assert len(telegram_calls) == 1
    assert telegram_calls[0][0] == 555
    assert telegram_calls[0][1] == result["videos"]


# --- Source types: Upload (data URI) vs History (storage URL) ----------------

def test_generate_animate_photo_video_accepts_upload_data_uri_source(monkeypatch):
    _apply_success_mocks(monkeypatch)
    payload = _animate_photo_payload(animatePhotoSourceUrl=_png_data_uri_sized(1280, 720))
    result = asyncio.run(main.generate_animate_photo_video(payload))
    assert result["ok"] is True


def test_generate_animate_photo_video_accepts_history_storage_source(monkeypatch):
    monkeypatch.setattr(main, "runway_animate_photo_headers", _fake_runway_headers)
    monkeypatch.setattr(main.requests, "post", lambda *a, **k: _FakeResponse(200, {"id": "task_1"}))
    monkeypatch.setattr(main, "safe_get", _fake_safe_get_poll())
    monkeypatch.setattr(main.time, "sleep", lambda *a, **k: None)
    monkeypatch.setattr(main, "_send_generated_videos_to_telegram", lambda *a, **k: True)

    history_url = "https://cdn.example.com/generated/images/history-photo.png"
    from PIL import Image
    real_png = io.BytesIO()
    Image.new("RGB", (1280, 720), (5, 5, 5)).save(real_png, format="PNG")

    def fake_storage_key_from_url(url):
        if url == history_url:
            return "generated/images/history-photo.png"
        return _fake_storage_key_from_url(url)

    monkeypatch.setattr(main, "storage_key_from_url", fake_storage_key_from_url)
    monkeypatch.setattr(main, "storage_read_bytes", lambda key: real_png.getvalue())
    monkeypatch.setattr(main, "storage_put_bytes", lambda content, key, content_type: f"https://cdn.example.com/{key}")

    payload = _animate_photo_payload(animatePhotoSourceUrl=history_url)
    result = asyncio.run(main.generate_animate_photo_video(payload))
    assert result["ok"] is True


# --- Dispatch precedence + real frontend-shaped routing regression -----------

def test_dispatch_prefers_animate_photo_over_generic_video_route():
    payload = {
        "model": "runway_gen4_5_animate_photo",
        "video_options": {"tool": "animate_photo"},
    }
    assert main.is_animate_photo_request(payload) is True


def test_video_generation_refuses_misrouted_animate_photo_payload(monkeypatch):
    def _explode(*a, **k):
        raise AssertionError("must never reach a real provider adapter for a misrouted animate_photo payload")

    monkeypatch.setattr(main.requests, "post", _explode)
    frontend_payload = {
        "mode": "video",
        "category": "video",
        "model": "runway_gen4_5_animate_photo",
        "provider": "runway",
        "prompt": "",
        "video_options": {
            "tool": "animate_photo",
            "animatePhotoSourceUrl": _png_data_uri(),
            "animatePhotoPrompt": "",
        },
        "history": [],
        "telegram_id": 0,
        "job_id": "",
    }
    result = asyncio.run(main.video_generation(frontend_payload))
    assert result["ok"] is False
    assert result["raw_error"] == "animate_photo_misrouted_to_video_generation"


def test_animate_photo_real_frontend_payload_dispatches_end_to_end(monkeypatch):
    """A full real frontend-shaped payload (mirroring exactly what
    generateAnimatePhotoTool() in cabinet.js builds via callGenerate's
    isolateRequest escape hatch) must route through
    dispatch_prostudio_provider_request() to generate_animate_photo_video()
    and never touch the generic video_generation()."""
    _apply_success_mocks(monkeypatch)

    def _explode_generic_video_generation(*a, **k):
        raise AssertionError("generic video_generation() must never be called for an animate_photo payload")

    monkeypatch.setattr(main, "video_generation", _explode_generic_video_generation)

    frontend_payload = {
        "telegram_id": 0,
        "prompt": "",
        "mode": "video",
        "category": "video",
        "model": "runway_gen4_5_animate_photo",
        "provider": "runway",
        "image_options": {},
        "video_options": {
            "tool": "animate_photo",
            "animatePhotoSourceUrl": _png_data_uri(),
            "animatePhotoPrompt": "Hair moves gently in the wind",
        },
        "music_options": None,
        "voice_options": None,
        "text_options": None,
        "history": [],
        "attachment": None,
        "job_id": "job_animate_1",
    }

    async def _run():
        return await main.dispatch_prostudio_provider_request(
            job_id="job_animate_1",
            payload=frontend_payload,
            mode="video",
            selected_model="runway_gen4_5_animate_photo",
            selected_provider="runway",
            text_modes={"text", "chat", "pro", "lite"},
        )

    result = asyncio.run(_run())
    assert result["ok"] is True
    assert result["tool"] == "animate_photo"
    assert result["provider"] == "runway"


# --- No cross-tool interference ------------------------------------------------

def test_other_quick_tools_remain_unaffected_by_animate_photo():
    remove_bg_payload = {"image_options": {"tool": "remove_background"}}
    enhance_photo_payload = {"image_options": {"tool": "enhance_photo"}}
    replace_character_payload = {"image_options": {"tool": "replace_character"}}
    for payload in (remove_bg_payload, enhance_photo_payload, replace_character_payload):
        assert main.is_animate_photo_request(payload) is False
    assert main.is_remove_bg_request(remove_bg_payload) is True
    assert main.is_enhance_photo_request(enhance_photo_payload) is True
    assert main.is_replace_character_request(replace_character_payload) is True


def test_generic_video_generation_still_works_for_non_animate_photo_payloads(monkeypatch):
    # The defense-in-depth guard inside video_generation() must only ever
    # reject the literal "animate_photo" tool flag - every other video
    # request must reach the real provider dispatch unaffected.
    from services import video_router

    monkeypatch.setattr(video_router, "_call_runway", lambda model_id, prompt, payload: {"ok": True, "type": "video", "provider": "runway", "model": model_id, "videos": ["https://example.com/v.mp4"], "video_url": "https://example.com/v.mp4"})
    result = asyncio.run(main.video_generation({
        "prompt": "a cinematic drone shot",
        "model": "runway_gen4_5",
        "provider": "runway",
        "video_options": {},
        "skip_telegram": True,
    }))
    assert result["ok"] is True
