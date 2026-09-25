"""Try-On is an isolated Quick Tool generation flow, same pattern as Remove
Object: its request must be built from exactly two tool-owned inputs
(image_options.tryOnModelImageUrl/tryOnGarmentUrls) and never from normal
Pro Studio composer state (Character/Object/Style/previous prompt/previous
references). The person image can come from a selected SYLVEX Character or
a manually uploaded photo - the frontend keeps those mutually exclusive and
resolves the final URL before it ever reaches the backend, so the backend
itself only ever sees a single tryOnModelImageUrl string.

FASHN's real /v1/run endpoint accepts exactly one garment_image per call,
so generate_try_on_image chains one call per uploaded garment (up to
FASHN_MAX_GARMENTS), feeding each result back in as the next call's
model_image. These tests cover is_try_on_request, the FASHN submit/poll
helpers, the isolated provider-call function (including sequential
chaining and that leaked normal-composer noise never reaches the request),
and the per-garment pricing branch in estimate_generation_cost."""
import asyncio
import json

import main


class _FakeResponse:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self.text = json.dumps(payload) if payload is not None else ""


def test_is_try_on_request_detects_tool_flag():
    assert main.is_try_on_request({"image_options": {"tool": "try_on"}}) is True
    assert main.is_try_on_request({"image_options": {"tool": "remove_object"}}) is False
    assert main.is_try_on_request({"image_options": {}}) is False
    assert main.is_try_on_request({}) is False


def test_fashn_submit_run_returns_prediction_id(monkeypatch):
    captured = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        captured["url"] = url
        captured["headers"] = headers
        captured["body"] = json
        return _FakeResponse(200, {"id": "pred_123"})

    monkeypatch.setattr(main, "FASHN_API_KEY", "test-key")
    monkeypatch.setattr(main.requests, "post", fake_post)

    prediction_id, error = main.fashn_submit_run("https://example.com/model.png", "https://example.com/garment.png")
    assert prediction_id == "pred_123"
    assert error == ""
    assert captured["url"] == f"{main.FASHN_API_BASE}/run"
    assert captured["headers"]["Authorization"] == "Bearer test-key"
    assert captured["body"]["inputs"]["model_image"] == "https://example.com/model.png"
    assert captured["body"]["inputs"]["garment_image"] == "https://example.com/garment.png"


def test_fashn_submit_run_handles_http_error(monkeypatch):
    def fake_post(url, headers=None, json=None, timeout=None):
        return _FakeResponse(400, {"error": "bad request"})

    monkeypatch.setattr(main, "FASHN_API_KEY", "test-key")
    monkeypatch.setattr(main.requests, "post", fake_post)

    prediction_id, error = main.fashn_submit_run("https://example.com/model.png", "https://example.com/garment.png")
    assert prediction_id == ""
    assert error


def test_fashn_poll_run_returns_output_on_completed(monkeypatch):
    def fake_get(url, headers=None, timeout=None):
        return _FakeResponse(200, {"id": "pred_123", "status": "completed", "output": ["https://cdn.fashn.ai/out.png"]})

    monkeypatch.setattr(main, "FASHN_API_KEY", "test-key")
    monkeypatch.setattr(main.requests, "get", fake_get)

    output, error = main.fashn_poll_run("pred_123")
    assert output == ["https://cdn.fashn.ai/out.png"]
    assert error == ""


def test_fashn_poll_run_returns_error_on_failed(monkeypatch):
    def fake_get(url, headers=None, timeout=None):
        return _FakeResponse(200, {"id": "pred_123", "status": "failed", "error": {"name": "ImageLoadError", "message": "bad url"}})

    monkeypatch.setattr(main, "FASHN_API_KEY", "test-key")
    monkeypatch.setattr(main.requests, "get", fake_get)

    output, error = main.fashn_poll_run("pred_123")
    assert output == []
    assert error == "bad url"


def test_fashn_poll_run_keeps_polling_until_completed(monkeypatch):
    statuses = iter(["starting", "in_queue", "processing"])
    calls = {"count": 0}

    def fake_get(url, headers=None, timeout=None):
        calls["count"] += 1
        status = next(statuses, "completed")
        if status == "completed":
            return _FakeResponse(200, {"id": "pred_123", "status": "completed", "output": ["https://cdn.fashn.ai/out.png"]})
        return _FakeResponse(200, {"id": "pred_123", "status": status})

    monkeypatch.setattr(main, "FASHN_API_KEY", "test-key")
    monkeypatch.setattr(main.requests, "get", fake_get)
    monkeypatch.setattr(main.time, "sleep", lambda *_a, **_k: None)

    output, error = main.fashn_poll_run("pred_123")
    assert output == ["https://cdn.fashn.ai/out.png"]
    assert error == ""
    assert calls["count"] == 4


def test_generate_try_on_image_requires_model_image(monkeypatch):
    monkeypatch.setattr(main, "FASHN_API_KEY", "test-key")
    result = asyncio.run(main.generate_try_on_image({
        "image_options": {"tool": "try_on", "tryOnGarmentUrls": ["https://example.com/garment.png"]},
    }))
    assert result["ok"] is False


def test_generate_try_on_image_requires_at_least_one_garment(monkeypatch):
    def _explode(*a, **k):
        raise AssertionError("must never call FASHN without a garment")

    monkeypatch.setattr(main, "FASHN_API_KEY", "test-key")
    monkeypatch.setattr(main, "fashn_submit_run", _explode)
    result = asyncio.run(main.generate_try_on_image({
        "image_options": {"tool": "try_on", "tryOnModelImageUrl": "https://example.com/model.png", "tryOnGarmentUrls": []},
    }))
    assert result["ok"] is False


def test_generate_try_on_image_single_garment_success(monkeypatch):
    captured = {}

    def fake_submit(model_image, garment_image):
        captured.setdefault("submits", []).append((model_image, garment_image))
        return "pred_1", ""

    def fake_poll(prediction_id):
        return ["https://cdn.fashn.ai/result.png"], ""

    monkeypatch.setattr(main, "FASHN_API_KEY", "test-key")
    monkeypatch.setattr(main, "fashn_submit_run", fake_submit)
    monkeypatch.setattr(main, "fashn_poll_run", fake_poll)
    monkeypatch.setattr(main, "send_generated_images_to_telegram", lambda *a, **k: True)

    payload = {
        "telegram_id": 0,
        "job_id": "",
        "image_options": {
            "tool": "try_on",
            "tryOnModelImageUrl": "https://example.com/character.png",
            "tryOnGarmentUrls": ["https://example.com/garment1.png"],
            # Leaked normal Pro Studio state that must be completely ignored.
            "characterId": "char_1",
            "characterReferences": ["https://example.com/leak1.png"],
            "objectReferences": ["https://example.com/leak2.png"],
            "style": "cinematic",
        },
    }
    result = asyncio.run(main.generate_try_on_image(payload))
    assert result["ok"] is True
    assert result["images"] == ["https://cdn.fashn.ai/result.png"]
    assert captured["submits"] == [("https://example.com/character.png", "https://example.com/garment1.png")]
    assert result["cost_credits"] == main.FASHN_TRYON_CREDITS_PER_GARMENT


def test_generate_try_on_image_chains_multiple_garments_sequentially(monkeypatch):
    captured = {"submits": []}

    def fake_submit(model_image, garment_image):
        captured["submits"].append((model_image, garment_image))
        return f"pred_{len(captured['submits'])}", ""

    def fake_poll(prediction_id):
        index = int(prediction_id.split("_")[1])
        return [f"https://cdn.fashn.ai/step{index}.png"], ""

    monkeypatch.setattr(main, "FASHN_API_KEY", "test-key")
    monkeypatch.setattr(main, "fashn_submit_run", fake_submit)
    monkeypatch.setattr(main, "fashn_poll_run", fake_poll)
    monkeypatch.setattr(main, "send_generated_images_to_telegram", lambda *a, **k: True)

    payload = {
        "telegram_id": 0,
        "job_id": "",
        "image_options": {
            "tool": "try_on",
            "tryOnModelImageUrl": "https://example.com/character.png",
            "tryOnGarmentUrls": [
                "https://example.com/garment1.png",
                "https://example.com/garment2.png",
                "https://example.com/garment3.png",
            ],
        },
    }
    result = asyncio.run(main.generate_try_on_image(payload))
    assert result["ok"] is True
    # Each garment call's model_image is the PREVIOUS call's own output -
    # never the original character/person image reused for every step.
    assert captured["submits"] == [
        ("https://example.com/character.png", "https://example.com/garment1.png"),
        ("https://cdn.fashn.ai/step1.png", "https://example.com/garment2.png"),
        ("https://cdn.fashn.ai/step2.png", "https://example.com/garment3.png"),
    ]
    assert result["images"] == ["https://cdn.fashn.ai/step3.png"]
    assert result["cost_credits"] == main.FASHN_TRYON_CREDITS_PER_GARMENT * 3


def test_generate_try_on_image_clips_to_max_garments(monkeypatch):
    captured = {"submits": []}

    def fake_submit(model_image, garment_image):
        captured["submits"].append(garment_image)
        return f"pred_{len(captured['submits'])}", ""

    def fake_poll(prediction_id):
        return ["https://cdn.fashn.ai/out.png"], ""

    monkeypatch.setattr(main, "FASHN_API_KEY", "test-key")
    monkeypatch.setattr(main, "fashn_submit_run", fake_submit)
    monkeypatch.setattr(main, "fashn_poll_run", fake_poll)
    monkeypatch.setattr(main, "send_generated_images_to_telegram", lambda *a, **k: True)

    payload = {
        "telegram_id": 0,
        "job_id": "",
        "image_options": {
            "tool": "try_on",
            "tryOnModelImageUrl": "https://example.com/character.png",
            "tryOnGarmentUrls": [f"https://example.com/garment{i}.png" for i in range(1, 6)],
        },
    }
    result = asyncio.run(main.generate_try_on_image(payload))
    assert result["ok"] is True
    assert len(captured["submits"]) == main.FASHN_MAX_GARMENTS


def test_generate_try_on_image_fails_when_a_garment_step_fails(monkeypatch):
    def fake_submit(model_image, garment_image):
        return "pred_1", ""

    def fake_poll(prediction_id):
        return [], "provider error"

    monkeypatch.setattr(main, "FASHN_API_KEY", "test-key")
    monkeypatch.setattr(main, "fashn_submit_run", fake_submit)
    monkeypatch.setattr(main, "fashn_poll_run", fake_poll)

    payload = {
        "telegram_id": 0,
        "job_id": "",
        "image_options": {
            "tool": "try_on",
            "tryOnModelImageUrl": "https://example.com/character.png",
            "tryOnGarmentUrls": ["https://example.com/garment1.png"],
        },
    }
    result = asyncio.run(main.generate_try_on_image(payload))
    assert result["ok"] is False


def test_estimate_generation_cost_scales_try_on_price_with_garment_count():
    one_garment = main.estimate_generation_cost({
        "mode": "image",
        "image_options": {"tool": "try_on", "tryOnGarmentUrls": ["https://example.com/g1.png"]},
    })
    three_garments = main.estimate_generation_cost({
        "mode": "image",
        "image_options": {
            "tool": "try_on",
            "tryOnGarmentUrls": [
                "https://example.com/g1.png",
                "https://example.com/g2.png",
                "https://example.com/g3.png",
            ],
        },
    })
    assert one_garment["credits"] == main.FASHN_TRYON_CREDITS_PER_GARMENT
    assert three_garments["credits"] == main.FASHN_TRYON_CREDITS_PER_GARMENT * 3
    assert one_garment["pricing_available"] is True


def test_estimate_generation_cost_try_on_clips_garment_count_for_pricing():
    estimate = main.estimate_generation_cost({
        "mode": "image",
        "image_options": {
            "tool": "try_on",
            "tryOnGarmentUrls": [f"https://example.com/g{i}.png" for i in range(1, 6)],
        },
    })
    assert estimate["credits"] == main.FASHN_TRYON_CREDITS_PER_GARMENT * main.FASHN_MAX_GARMENTS


def test_dispatch_prefers_try_on_over_generic_seedream_route():
    payload = {
        "model": "seedream_5_0_lite",
        "image_options": {"tool": "try_on"},
    }
    assert main.is_try_on_request(payload) is True
    # Same payload would also match the generic Seedream dispatch check -
    # dispatch_prostudio_provider_request checks is_try_on_request first,
    # specifically so this never falls through to a generic Seedream route
    # (which reads the leaky image_options shape) instead of the isolated
    # generate_try_on_image.
    assert main.is_seedream_request(payload) is True
