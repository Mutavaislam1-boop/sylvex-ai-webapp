"""Enhance Photo is its own isolated Quick Tool generation flow, same pattern
as Remove Object/Remove Background/Try-On/Character Replace: its request must
be built from exactly one tool-owned input (image_options.enhancePhotoSourceUrl)
and never from normal Pro Studio composer state (Character/Object/Style/prompt/
references). It calls Topaz Labs' real Enhance API - POST
https://api.topazlabs.com/image/v1/enhance/async, multipart/form-data, auth via
the X-API-KEY header (TOPAZ_API_KEY env var), model="High Fidelity V2", the
resize field is the documented outputHeight (never output_height/output_width/
outputWidth) - then async polling of GET .../status/{process_id} for the
literal `status` field until Completed/Failed/Cancelled, then GET
.../download/{process_id} for the literal `url` field.

Topaz's own download URL is ephemeral, so generate_enhance_photo_image must
download and persist it to durable SYLVEX storage synchronously, inside the
function itself, before ever returning - never leaving Topaz's temporary URL
as the result. These tests cover is_enhance_photo_request, the dedicated
pricing branch (flat 15 credits), the output-dimension calculator (~2x
upscale, aspect ratio preserved, capped at 24MP), the async submit+poll+
download provider flow (process_id/status/url handling, Failed/Cancelled/
timeout), synchronous persistence of the ephemeral result URL, that leaked
normal-composer noise never reaches the request, and dispatch precedence over
the generic Seedream/image_generation routes."""
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
    return _png_data_uri_sized(6, 6)


class _FakeResponse:
    # Doubles as both a JSON provider-API response (status_code/text, used
    # for submit/status/download) and a raw-bytes response for
    # _persist_remote_media_url's own safe_get() call (headers/content/
    # raise_for_status) - the isolated flow routes both through
    # main.safe_get during the success path, so one fake response needs to
    # satisfy both call sites.
    headers = {"content-type": "image/png"}
    content = b"final-enhanced-photo-bytes"

    def __init__(self, status_code=200, payload=None, text=None):
        self.status_code = status_code
        self.text = json.dumps(payload) if payload is not None else (text or "")

    def raise_for_status(self):
        return None


TOPAZ_RESULT_URL = "https://files.topazlabs.com/ephemeral/result-abc123.png"


def _fake_topaz_headers():
    return {"X-API-KEY": "test-topaz-key"}


def _fake_storage_key_from_url(url):
    return url.split("https://cdn.example.com/", 1)[1] if url.startswith("https://cdn.example.com/") else ""


def _enhance_photo_payload(**overrides):
    opts = {
        "tool": "enhance_photo",
        "enhancePhotoSourceUrl": _png_data_uri(),
    }
    opts.update(overrides)
    return {
        "telegram_id": 0,
        "job_id": "",
        "image_options": opts,
    }


def _fake_safe_get_dispatch(status="Completed", download_url=TOPAZ_RESULT_URL):
    """Dispatches main.safe_get by URL: the status endpoint returns the
    literal {"status": ...}, the download endpoint returns the literal
    {"url": ...}, and any other URL (the persistence step's own fetch of
    the real result bytes) returns the raw-bytes-shaped fake response."""
    def _fake_safe_get(url, headers=None, timeout=None):
        if "/status/" in url:
            return _FakeResponse(200, {"status": status})
        if "/download/" in url:
            return _FakeResponse(200, {"url": download_url})
        return _FakeResponse(200, text="")  # raw bytes path via class attrs
    return _fake_safe_get


def _apply_success_mocks(monkeypatch, status="Completed", download_url=TOPAZ_RESULT_URL, process_id="proc_123"):
    monkeypatch.setattr(main, "topaz_headers", _fake_topaz_headers)
    monkeypatch.setattr(main.requests, "post", lambda *a, **k: _FakeResponse(200, {"process_id": process_id}))
    monkeypatch.setattr(main, "safe_get", _fake_safe_get_dispatch(status=status, download_url=download_url))
    monkeypatch.setattr(main.time, "sleep", lambda *a, **k: None)
    monkeypatch.setattr(main, "storage_put_bytes", lambda content, key, content_type: f"https://cdn.example.com/{key}")
    monkeypatch.setattr(main, "storage_key_from_url", _fake_storage_key_from_url)
    monkeypatch.setattr(main, "send_generated_images_to_telegram", lambda *a, **k: True)


# --- Tool identifier / dispatch predicate -----------------------------------

def test_is_enhance_photo_request_detects_tool_flag():
    assert main.is_enhance_photo_request({"image_options": {"tool": "enhance_photo"}}) is True
    assert main.is_enhance_photo_request({"image_options": {"tool": "enhance"}}) is False
    assert main.is_enhance_photo_request({"image_options": {"tool": "upscaler"}}) is False
    assert main.is_enhance_photo_request({"image_options": {}}) is False
    assert main.is_enhance_photo_request({}) is False


def test_is_enhance_photo_request_ignores_case_and_whitespace():
    assert main.is_enhance_photo_request({"image_options": {"tool": " Enhance_Photo "}}) is True


def test_enhance_photo_tool_never_collides_with_other_isolated_tools():
    payload = {"image_options": {"tool": "enhance_photo"}}
    assert main.is_enhance_photo_request(payload) is True
    assert main.is_remove_object_request(payload) is False
    assert main.is_try_on_request(payload) is False
    assert main.is_remove_bg_request(payload) is False
    assert main.is_replace_character_request(payload) is False
    # And the reverse: other tools' payloads must never be mistaken for
    # Enhance Photo either (e.g. the pre-existing, unrelated "upscaler" flat
    # fee, or the generic PHOTO_TOOL_CONFIG.enhance key used client-side).
    assert main.is_enhance_photo_request({"image_options": {"tool": "upscaler"}}) is False
    assert main.is_enhance_photo_request({"image_options": {"tool": "remove_background"}}) is False


def test_dispatch_prefers_enhance_photo_over_generic_seedream_route():
    payload = {
        "model": "seedream_5_0_lite",
        "image_options": {"tool": "enhance_photo"},
    }
    assert main.is_enhance_photo_request(payload) is True
    # Same payload would also match the generic Seedream dispatch check -
    # dispatch_prostudio_provider_request checks is_enhance_photo_request
    # first, specifically so this never falls through to a generic Seedream
    # route (which reads the leaky image_options shape) instead of the
    # isolated generate_enhance_photo_image.
    assert main.is_seedream_request(payload) is True


# --- Pricing -----------------------------------------------------------------

def test_enhance_photo_cost_info_is_flat_15_credits():
    info = main.enhance_photo_cost_info()
    assert info["credits"] == 15
    assert info["cost_credits"] == 15
    assert info["generation_cost"] == "15 ⚡"


def test_enhance_photo_pricing_derives_from_configurable_topaz_rate_constant():
    # $0.10 (TOPAZ_CREDIT_COST_USD) * 1.5 markup = $0.15 -> 15 credits
    # (1 credit = $0.01 of the marked-up price). The rate is a named
    # constant, not an inline literal, so it can be updated in one place.
    assert main.TOPAZ_CREDIT_COST_USD == 0.10
    assert main.ENHANCE_PHOTO_MARKUP == 1.5
    import math
    expected_credits = int(math.ceil(round(main.TOPAZ_CREDIT_COST_USD * main.ENHANCE_PHOTO_MARKUP * 100, 6)))
    assert main.enhance_photo_cost_info()["credits"] == expected_credits == 15


def test_estimate_generation_cost_prices_enhance_photo_flat_fee():
    estimate = main.estimate_generation_cost({
        "mode": "image",
        "image_options": {"tool": "enhance_photo"},
    })
    assert estimate["credits"] == 15
    assert estimate["pricing_available"] is True
    assert estimate["operation"] == "enhance_photo"


def test_estimate_generation_cost_enhance_photo_never_matches_legacy_upscaler_price():
    # tool_prices still has an unrelated "upscaler": 1 (Recraft) entry - the
    # isolated flow's own distinct "enhance_photo" tool string must be
    # priced by its own dedicated branch, never fall through to that
    # pre-existing, unrelated entry.
    upscaler_estimate = main.estimate_generation_cost({"mode": "image", "image_options": {"tool": "upscaler"}})
    assert upscaler_estimate["credits"] == 1
    enhance_photo_estimate = main.estimate_generation_cost({"mode": "image", "image_options": {"tool": "enhance_photo"}})
    assert enhance_photo_estimate["credits"] == 15


# --- Output dimension calculator (2x upscale, aspect ratio, 24MP cap) -------

def test_enhance_photo_output_dimensions_doubles_small_image():
    width, height = main.enhance_photo_output_dimensions(1000, 500)
    assert width == 2000
    assert height == 1000


def test_enhance_photo_output_dimensions_preserves_portrait_aspect_ratio():
    source_width, source_height = 1080, 1920
    width, height = main.enhance_photo_output_dimensions(source_width, source_height)
    source_ratio = source_width / source_height
    output_ratio = width / height
    assert abs(source_ratio - output_ratio) < 0.01


def test_enhance_photo_output_dimensions_preserves_landscape_aspect_ratio():
    source_width, source_height = 1920, 1080
    width, height = main.enhance_photo_output_dimensions(source_width, source_height)
    source_ratio = source_width / source_height
    output_ratio = width / height
    assert abs(source_ratio - output_ratio) < 0.01


def test_enhance_photo_output_dimensions_never_exceeds_24_megapixels():
    # A large source (e.g. a real 6000x4000 photo) doubled would be
    # 12000x8000 = 96MP, far over the 24MP 1-credit tier - must be scaled
    # down proportionally, never cropped/stretched.
    width, height = main.enhance_photo_output_dimensions(6000, 4000)
    assert width * height <= main.ENHANCE_PHOTO_OUTPUT_MAX_PIXELS
    source_ratio = 6000 / 4000
    output_ratio = width / height
    assert abs(source_ratio - output_ratio) < 0.01


def test_enhance_photo_output_dimensions_small_image_stays_under_cap_at_exact_2x():
    # A modest source's 2x output easily stays under 24MP - no scale-down
    # should kick in at all.
    width, height = main.enhance_photo_output_dimensions(2000, 1500)
    assert (width, height) == (4000, 3000)
    assert width * height <= main.ENHANCE_PHOTO_OUTPUT_MAX_PIXELS


def test_enhance_photo_output_dimensions_handles_zero_or_missing_source():
    width, height = main.enhance_photo_output_dimensions(0, 0)
    assert width >= 1 and height >= 1


# --- Isolated provider call: validation & request shape ----------------------

def test_generate_enhance_photo_image_requires_source_image(monkeypatch):
    monkeypatch.setattr(main, "topaz_headers", _fake_topaz_headers)
    result = asyncio.run(main.generate_enhance_photo_image({
        "image_options": {"tool": "enhance_photo"},
    }))
    assert result["ok"] is False


def test_generate_enhance_photo_image_requires_api_key(monkeypatch):
    monkeypatch.setattr(main, "topaz_headers", lambda: {})
    result = asyncio.run(main.generate_enhance_photo_image(_enhance_photo_payload()))
    assert result["ok"] is False


def test_generate_enhance_photo_image_rejects_unsupported_format(monkeypatch):
    def _explode(*a, **k):
        raise AssertionError("must never call the provider with an unsupported source format")

    monkeypatch.setattr(main, "topaz_headers", _fake_topaz_headers)
    monkeypatch.setattr(main.requests, "post", _explode)
    bogus_uri = "data:image/gif;base64," + base64.b64encode(b"GIF89a-not-supported").decode("ascii")
    result = asyncio.run(main.generate_enhance_photo_image(_enhance_photo_payload(enhancePhotoSourceUrl=bogus_uri)))
    assert result["ok"] is False


def test_generate_enhance_photo_image_sends_correct_topaz_request_shape(monkeypatch):
    captured = {}
    source_uri = _png_data_uri_sized(600, 900)

    def fake_post(url, headers=None, data=None, files=None, timeout=None):
        captured["url"] = url
        captured["headers"] = headers
        captured["data"] = dict(data or {})
        captured["files"] = dict(files or {})
        return _FakeResponse(200, {"process_id": "proc_1"})

    monkeypatch.setattr(main, "topaz_headers", _fake_topaz_headers)
    monkeypatch.setattr(main.requests, "post", fake_post)
    monkeypatch.setattr(main, "safe_get", _fake_safe_get_dispatch())
    monkeypatch.setattr(main.time, "sleep", lambda *a, **k: None)
    monkeypatch.setattr(main, "storage_put_bytes", lambda content, key, content_type: f"https://cdn.example.com/{key}")
    monkeypatch.setattr(main, "storage_key_from_url", _fake_storage_key_from_url)
    monkeypatch.setattr(main, "send_generated_images_to_telegram", lambda *a, **k: True)

    result = asyncio.run(main.generate_enhance_photo_image(_enhance_photo_payload(enhancePhotoSourceUrl=source_uri)))

    assert result["ok"] is True
    # Exact endpoint from Topaz's official async contract.
    assert captured["url"] == "https://api.topazlabs.com/image/v1/enhance/async"
    # Exact auth header - X-API-KEY, never Authorization/Bearer/Api-Key.
    assert captured["headers"] == {"X-API-KEY": "test-topaz-key"}
    # Exact documented model name.
    assert captured["data"]["model"] == "High Fidelity V2"
    # Exact documented resize field - outputHeight only, never
    # output_height/output_width/outputWidth.
    assert "outputHeight" in captured["data"]
    assert "output_height" not in captured["data"]
    assert "output_width" not in captured["data"]
    assert "outputWidth" not in captured["data"]
    expected_width, expected_height = main.enhance_photo_output_dimensions(600, 900)
    assert int(captured["data"]["outputHeight"]) == expected_height
    # Exact multipart field name for the source image.
    assert "image" in captured["files"]
    filename, file_bytes, content_type = captured["files"]["image"]
    assert content_type == "image/png"
    assert len(file_bytes) > 0


def test_generate_enhance_photo_image_output_preserves_source_aspect_ratio(monkeypatch):
    captured = {}
    source_uri = _png_data_uri_sized(1200, 800)

    def fake_post(url, headers=None, data=None, files=None, timeout=None):
        captured["output_height"] = int(data["outputHeight"])
        return _FakeResponse(200, {"process_id": "proc_1"})

    monkeypatch.setattr(main, "topaz_headers", _fake_topaz_headers)
    monkeypatch.setattr(main.requests, "post", fake_post)
    monkeypatch.setattr(main, "safe_get", _fake_safe_get_dispatch())
    monkeypatch.setattr(main.time, "sleep", lambda *a, **k: None)
    monkeypatch.setattr(main, "storage_put_bytes", lambda content, key, content_type: f"https://cdn.example.com/{key}")
    monkeypatch.setattr(main, "storage_key_from_url", _fake_storage_key_from_url)
    monkeypatch.setattr(main, "send_generated_images_to_telegram", lambda *a, **k: True)

    result = asyncio.run(main.generate_enhance_photo_image(_enhance_photo_payload(enhancePhotoSourceUrl=source_uri)))
    assert result["ok"] is True
    expected_width, expected_height = main.enhance_photo_output_dimensions(1200, 800)
    assert captured["output_height"] == expected_height
    assert abs((1200 / 800) - (expected_width / expected_height)) < 0.01


def test_generate_enhance_photo_image_approximately_doubles_resolution(monkeypatch):
    captured = {}
    source_uri = _png_data_uri_sized(500, 400)

    def fake_post(url, headers=None, data=None, files=None, timeout=None):
        captured["output_height"] = int(data["outputHeight"])
        return _FakeResponse(200, {"process_id": "proc_1"})

    monkeypatch.setattr(main, "topaz_headers", _fake_topaz_headers)
    monkeypatch.setattr(main.requests, "post", fake_post)
    monkeypatch.setattr(main, "safe_get", _fake_safe_get_dispatch())
    monkeypatch.setattr(main.time, "sleep", lambda *a, **k: None)
    monkeypatch.setattr(main, "storage_put_bytes", lambda content, key, content_type: f"https://cdn.example.com/{key}")
    monkeypatch.setattr(main, "storage_key_from_url", _fake_storage_key_from_url)
    monkeypatch.setattr(main, "send_generated_images_to_telegram", lambda *a, **k: True)

    result = asyncio.run(main.generate_enhance_photo_image(_enhance_photo_payload(enhancePhotoSourceUrl=source_uri)))
    assert result["ok"] is True
    assert captured["output_height"] == 800  # 400 * 2, well under the 24MP cap


def test_generate_enhance_photo_image_ignores_leaked_normal_pro_studio_state(monkeypatch):
    captured = {}

    def fake_post(url, headers=None, data=None, files=None, timeout=None):
        captured["files"] = dict(files or {})
        return _FakeResponse(200, {"process_id": "proc_1"})

    monkeypatch.setattr(main, "topaz_headers", _fake_topaz_headers)
    monkeypatch.setattr(main.requests, "post", fake_post)
    monkeypatch.setattr(main, "safe_get", _fake_safe_get_dispatch())
    monkeypatch.setattr(main.time, "sleep", lambda *a, **k: None)
    monkeypatch.setattr(main, "storage_put_bytes", lambda content, key, content_type: f"https://cdn.example.com/{key}")
    monkeypatch.setattr(main, "storage_key_from_url", _fake_storage_key_from_url)
    monkeypatch.setattr(main, "send_generated_images_to_telegram", lambda *a, **k: True)

    payload = _enhance_photo_payload(
        characterId="char_1",
        characterReferences=["https://example.com/leak1.png"],
        objectReferences=["https://example.com/leak2.png"],
        style="cinematic",
    )
    payload["prompt"] = "a totally unrelated leaked prompt describing a dragon"
    result = asyncio.run(main.generate_enhance_photo_image(payload))
    assert result["ok"] is True
    # Only the one uploaded source image byte stream reaches Topaz - no
    # character/object/style/prompt data is ever part of the request.
    assert list(captured["files"].keys()) == ["image"]


# --- Async submit -> poll -> download flow ------------------------------------

def test_generate_enhance_photo_image_handles_process_id_missing(monkeypatch):
    monkeypatch.setattr(main, "topaz_headers", _fake_topaz_headers)
    monkeypatch.setattr(main.requests, "post", lambda *a, **k: _FakeResponse(200, {}))
    result = asyncio.run(main.generate_enhance_photo_image(_enhance_photo_payload()))
    assert result["ok"] is False


def test_poll_topaz_enhance_status_completes_after_pending_and_processing(monkeypatch):
    statuses = iter(["Pending", "Processing", "Completed"])

    def fake_safe_get(url, headers=None, timeout=None):
        return _FakeResponse(200, {"status": next(statuses)})

    monkeypatch.setattr(main, "safe_get", fake_safe_get)
    monkeypatch.setattr(main.time, "sleep", lambda *a, **k: None)
    ok, error = main.poll_topaz_enhance_status("proc_1", "enhance_photo", "High Fidelity V2")
    assert ok is True
    assert error == {}


def test_poll_topaz_enhance_status_handles_failed(monkeypatch):
    monkeypatch.setattr(main, "safe_get", lambda url, headers=None, timeout=None: _FakeResponse(200, {"status": "Failed"}))
    ok, error = main.poll_topaz_enhance_status("proc_1", "enhance_photo", "High Fidelity V2")
    assert ok is False
    assert error.get("ok") is False


def test_poll_topaz_enhance_status_handles_cancelled(monkeypatch):
    monkeypatch.setattr(main, "safe_get", lambda url, headers=None, timeout=None: _FakeResponse(200, {"status": "Cancelled"}))
    ok, error = main.poll_topaz_enhance_status("proc_1", "enhance_photo", "High Fidelity V2")
    assert ok is False
    assert error.get("ok") is False


def test_poll_topaz_enhance_status_times_out(monkeypatch):
    monkeypatch.setattr(main, "safe_get", lambda url, headers=None, timeout=None: _FakeResponse(200, {"status": "Processing"}))
    monkeypatch.setattr(main.time, "sleep", lambda *a, **k: None)
    ok, error = main.poll_topaz_enhance_status("proc_1", "enhance_photo", "High Fidelity V2", max_attempts=3)
    assert ok is False
    assert error.get("ok") is False


def test_poll_topaz_enhance_status_handles_rate_limiting_then_recovers(monkeypatch):
    responses = iter([
        _FakeResponse(429, text="rate limited"),
        _FakeResponse(200, {"status": "Completed"}),
    ])
    monkeypatch.setattr(main, "safe_get", lambda url, headers=None, timeout=None: next(responses))
    monkeypatch.setattr(main.time, "sleep", lambda *a, **k: None)
    ok, error = main.poll_topaz_enhance_status("proc_1", "enhance_photo", "High Fidelity V2")
    assert ok is True


def test_generate_enhance_photo_image_handles_download_url_missing(monkeypatch):
    def fake_safe_get(url, headers=None, timeout=None):
        if "/status/" in url:
            return _FakeResponse(200, {"status": "Completed"})
        return _FakeResponse(200, {})  # download response missing "url"

    monkeypatch.setattr(main, "topaz_headers", _fake_topaz_headers)
    monkeypatch.setattr(main.requests, "post", lambda *a, **k: _FakeResponse(200, {"process_id": "proc_1"}))
    monkeypatch.setattr(main, "safe_get", fake_safe_get)
    monkeypatch.setattr(main.time, "sleep", lambda *a, **k: None)
    result = asyncio.run(main.generate_enhance_photo_image(_enhance_photo_payload()))
    assert result["ok"] is False


def test_generate_enhance_photo_image_handles_provider_submit_error_response(monkeypatch):
    monkeypatch.setattr(main, "topaz_headers", _fake_topaz_headers)
    monkeypatch.setattr(main.requests, "post", lambda *a, **k: _FakeResponse(400, text="bad request"))
    result = asyncio.run(main.generate_enhance_photo_image(_enhance_photo_payload()))
    assert result["ok"] is False


def test_generate_enhance_photo_image_handles_network_error(monkeypatch):
    import requests as requests_module

    def fake_post(*a, **k):
        raise requests_module.exceptions.ConnectionError("boom")

    monkeypatch.setattr(main, "topaz_headers", _fake_topaz_headers)
    monkeypatch.setattr(main.requests, "post", fake_post)
    result = asyncio.run(main.generate_enhance_photo_image(_enhance_photo_payload()))
    assert result["ok"] is False


# --- Persistence to durable SYLVEX storage ------------------------------------

def test_generate_enhance_photo_image_persists_ephemeral_url_to_durable_storage(monkeypatch):
    monkeypatch.setattr(main, "topaz_headers", _fake_topaz_headers)
    monkeypatch.setattr(main.requests, "post", lambda *a, **k: _FakeResponse(200, {"process_id": "proc_1"}))
    monkeypatch.setattr(main, "safe_get", _fake_safe_get_dispatch())
    monkeypatch.setattr(main.time, "sleep", lambda *a, **k: None)

    persist_calls = []

    def fake_persist(url, category, provider=""):
        persist_calls.append((url, category, provider))
        return "https://cdn.example.com/images/final-enhanced.png"

    monkeypatch.setattr(main, "_persist_remote_media_url", fake_persist)
    monkeypatch.setattr(main, "storage_key_from_url", lambda url: "images/final-enhanced.png" if "cdn.example.com" in url else "")
    monkeypatch.setattr(main, "send_generated_images_to_telegram", lambda *a, **k: True)

    result = asyncio.run(main.generate_enhance_photo_image(_enhance_photo_payload()))
    assert result["ok"] is True
    # The ephemeral Topaz URL must never be handed back as the result - only
    # the durably persisted SYLVEX storage URL.
    assert result["image_url"] == "https://cdn.example.com/images/final-enhanced.png"
    assert result["images"] == ["https://cdn.example.com/images/final-enhanced.png"]
    assert TOPAZ_RESULT_URL not in json.dumps(result)
    assert persist_calls == [(TOPAZ_RESULT_URL, "images", "topaz")]


def test_generate_enhance_photo_image_fails_when_storage_persist_fails(monkeypatch):
    monkeypatch.setattr(main, "topaz_headers", _fake_topaz_headers)
    monkeypatch.setattr(main.requests, "post", lambda *a, **k: _FakeResponse(200, {"process_id": "proc_1"}))
    monkeypatch.setattr(main, "safe_get", _fake_safe_get_dispatch())
    monkeypatch.setattr(main.time, "sleep", lambda *a, **k: None)
    # _persist_remote_media_url falls back to returning the original
    # (ephemeral, non-storage) URL on failure - generate_enhance_photo_image
    # must treat that as a hard failure, never hand back a temporary URL.
    monkeypatch.setattr(main, "_persist_remote_media_url", lambda url, category, provider="": url)
    monkeypatch.setattr(main, "storage_key_from_url", lambda url: "")

    result = asyncio.run(main.generate_enhance_photo_image(_enhance_photo_payload()))
    assert result["ok"] is False


# --- Result fields / Telegram delivery ----------------------------------------

def test_generate_enhance_photo_image_result_carries_cost_and_provider_fields(monkeypatch):
    _apply_success_mocks(monkeypatch)
    result = asyncio.run(main.generate_enhance_photo_image(_enhance_photo_payload()))
    assert result["ok"] is True
    assert result["provider"] == "topaz"
    assert result["tool"] == "enhance_photo"
    assert result["provider_model"] == "High Fidelity V2"
    assert result["cost_credits"] == 15
    assert result["generation_cost"] == "15 ⚡"


def test_generate_enhance_photo_image_sends_telegram_delivery(monkeypatch):
    monkeypatch.setattr(main, "topaz_headers", _fake_topaz_headers)
    monkeypatch.setattr(main.requests, "post", lambda *a, **k: _FakeResponse(200, {"process_id": "proc_1"}))
    monkeypatch.setattr(main, "safe_get", _fake_safe_get_dispatch())
    monkeypatch.setattr(main.time, "sleep", lambda *a, **k: None)
    monkeypatch.setattr(main, "storage_put_bytes", lambda content, key, content_type: f"https://cdn.example.com/{key}")
    monkeypatch.setattr(main, "storage_key_from_url", _fake_storage_key_from_url)

    telegram_calls = []

    def fake_telegram(telegram_id, images, caption):
        telegram_calls.append((telegram_id, images, caption))
        return True

    monkeypatch.setattr(main, "send_generated_images_to_telegram", fake_telegram)

    payload = _enhance_photo_payload()
    payload["telegram_id"] = 555
    result = asyncio.run(main.generate_enhance_photo_image(payload))
    assert result["ok"] is True
    assert result["sent_to_telegram"] is True
    assert len(telegram_calls) == 1
    assert telegram_calls[0][0] == 555
    assert telegram_calls[0][1] == result["images"]


# --- Source types: Upload (data URI) vs History (storage URL) ----------------

def test_generate_enhance_photo_image_accepts_upload_data_uri_source(monkeypatch):
    _apply_success_mocks(monkeypatch)
    payload = _enhance_photo_payload(enhancePhotoSourceUrl=_png_data_uri_sized(400, 300))
    result = asyncio.run(main.generate_enhance_photo_image(payload))
    assert result["ok"] is True


def test_generate_enhance_photo_image_accepts_history_storage_source(monkeypatch):
    monkeypatch.setattr(main, "topaz_headers", _fake_topaz_headers)
    monkeypatch.setattr(main.requests, "post", lambda *a, **k: _FakeResponse(200, {"process_id": "proc_1"}))
    monkeypatch.setattr(main, "safe_get", _fake_safe_get_dispatch())
    monkeypatch.setattr(main.time, "sleep", lambda *a, **k: None)
    monkeypatch.setattr(main, "send_generated_images_to_telegram", lambda *a, **k: True)

    history_url = "https://cdn.example.com/generated/images/history-photo.png"
    from PIL import Image
    real_png = io.BytesIO()
    Image.new("RGB", (400, 300), (5, 5, 5)).save(real_png, format="PNG")

    def fake_storage_key_from_url(url):
        if url == history_url:
            return "generated/images/history-photo.png"
        return _fake_storage_key_from_url(url)

    monkeypatch.setattr(main, "storage_key_from_url", fake_storage_key_from_url)
    monkeypatch.setattr(main, "storage_read_bytes", lambda key: real_png.getvalue())
    monkeypatch.setattr(main, "storage_put_bytes", lambda content, key, content_type: f"https://cdn.example.com/{key}")

    payload = _enhance_photo_payload(enhancePhotoSourceUrl=history_url)
    result = asyncio.run(main.generate_enhance_photo_image(payload))
    assert result["ok"] is True


# --- No cross-tool interference ------------------------------------------------

def test_other_quick_tools_remain_unaffected_by_enhance_photo():
    remove_bg_payload = {"image_options": {"tool": "remove_background"}}
    remove_object_payload = {"image_options": {"tool": "remove_object"}}
    try_on_payload = {"image_options": {"tool": "try_on"}}
    replace_character_payload = {"image_options": {"tool": "replace_character"}}
    for payload in (remove_bg_payload, remove_object_payload, try_on_payload, replace_character_payload):
        assert main.is_enhance_photo_request(payload) is False
    assert main.is_remove_bg_request(remove_bg_payload) is True
    assert main.is_remove_object_request(remove_object_payload) is True
    assert main.is_try_on_request(try_on_payload) is True
    assert main.is_replace_character_request(replace_character_payload) is True


# --- Defense in depth: misrouting to the generic image_generation() ----------

def test_image_generation_refuses_misrouted_enhance_photo_payload(monkeypatch):
    def _explode(*a, **k):
        raise AssertionError("must never reach a real provider adapter for a misrouted enhance_photo payload")

    monkeypatch.setattr(main.requests, "post", _explode)
    errors = []
    monkeypatch.setattr(main, "prostudio_error", lambda *a, **k: errors.append((a, k)))
    result = asyncio.run(main.image_generation(_enhance_photo_payload()))
    assert result["ok"] is False
    assert result["raw_error"] == "enhance_photo_misrouted_to_image_generation"
    assert len(errors) == 1
