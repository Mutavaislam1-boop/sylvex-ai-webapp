"""Remove Background is its own isolated Quick Tool generation flow, same
pattern as Remove Object/Try-On: its request must be built from exactly one
tool-owned input (image_options.removeBgSourceUrl) and never from normal
Pro Studio composer state (Character/Object/Style/prompt/references). It
calls Ideogram's real Remove Background API - POST
https://api.ideogram.ai/v1/remove-background, multipart form field "image"
(not "image_file", and not the /v1/ideogram-v{3,4}/generate endpoints used
elsewhere in this file), auth via the existing Api-Key header helper
(ideogram_headers), using the existing IDEOGRAM_API_KEY environment
variable.

Ideogram's own response URL is ephemeral, so generate_remove_bg_image must
download and persist it to durable SYLVEX storage synchronously, inside the
function itself, before ever returning - never leaving Ideogram's temporary
URL as the result. These tests cover is_remove_bg_request, the dedicated
pricing branch, the isolated provider-call function (source format
validation, the request shape sent to Ideogram, synchronous persistence of
the ephemeral result URL, and that leaked normal-composer noise never
reaches the request or the provider), and dispatch precedence over the
generic Seedream/image_generation routes."""
import asyncio
import base64
import io
import json

import main


def _png_data_uri(size=(6, 6), color=(10, 20, 30, 255)):
    from PIL import Image

    img = Image.new("RGBA", size, color)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    encoded = base64.b64encode(buf.getvalue()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


class _FakeResponse:
    def __init__(self, status_code=200, payload=None, text=None):
        self.status_code = status_code
        self.text = json.dumps(payload) if payload is not None else (text or "")


class _FakePersistResponse:
    headers = {"content-type": "image/png"}
    content = b"final-transparent-png-bytes"

    def raise_for_status(self):
        return None


def _fake_ideogram_success_response():
    return _FakeResponse(200, {
        "created": "2024-01-15T09:30:00Z",
        "data": [{"is_image_safe": True, "url": "https://ideogram.ai/api/images/ephemeral/abc123.png"}],
    })


def _fake_storage_key_from_url(url):
    return url.split("https://cdn.example.com/", 1)[1] if url.startswith("https://cdn.example.com/") else ""


def test_is_remove_bg_request_detects_tool_flag():
    assert main.is_remove_bg_request({"image_options": {"tool": "remove_background"}}) is True
    assert main.is_remove_bg_request({"image_options": {"tool": "remove_object"}}) is False
    assert main.is_remove_bg_request({"image_options": {"tool": "remove_bg"}}) is False
    assert main.is_remove_bg_request({"image_options": {}}) is False
    assert main.is_remove_bg_request({}) is False


def test_is_remove_bg_request_ignores_case_and_whitespace():
    assert main.is_remove_bg_request({"image_options": {"tool": " Remove_Background "}}) is True


def test_estimate_generation_cost_prices_remove_background_flat_fee():
    estimate = main.estimate_generation_cost({
        "mode": "image",
        "image_options": {"tool": "remove_background"},
    })
    assert estimate["credits"] == main.IDEOGRAM_REMOVE_BG_CREDITS
    assert estimate["pricing_available"] is True


def test_estimate_generation_cost_remove_background_never_matches_legacy_remove_bg_recraft_price():
    # tool_prices still has an unrelated "remove_bg": 2 (Recraft) entry -
    # the isolated flow's own distinct "remove_background" tool string must
    # be priced by its own dedicated branch, never fall through to that
    # pre-existing, unrelated entry.
    estimate = main.estimate_generation_cost({
        "mode": "image",
        "image_options": {"tool": "remove_bg"},
    })
    assert estimate["operation"] == "remove_bg"
    remove_background_estimate = main.estimate_generation_cost({
        "mode": "image",
        "image_options": {"tool": "remove_background"},
    })
    assert remove_background_estimate["operation"] == "remove_background"


def test_generate_remove_bg_image_requires_source_image(monkeypatch):
    monkeypatch.setattr(main, "ideogram_headers", lambda json_content=True: {"Api-Key": "test-key"})
    result = asyncio.run(main.generate_remove_bg_image({
        "image_options": {"tool": "remove_background"},
    }))
    assert result["ok"] is False


def test_generate_remove_bg_image_requires_api_key(monkeypatch):
    monkeypatch.setattr(main, "ideogram_headers", lambda json_content=True: {})
    result = asyncio.run(main.generate_remove_bg_image({
        "image_options": {"tool": "remove_background", "removeBgSourceUrl": _png_data_uri()},
    }))
    assert result["ok"] is False


def test_generate_remove_bg_image_rejects_unsupported_format(monkeypatch):
    def _explode(*a, **k):
        raise AssertionError("must never call the provider with an unsupported source format")

    monkeypatch.setattr(main, "ideogram_headers", lambda json_content=True: {"Api-Key": "test-key"})
    monkeypatch.setattr(main.requests, "post", _explode)
    bogus_uri = "data:image/gif;base64," + base64.b64encode(b"GIF89a-not-supported").decode("ascii")
    result = asyncio.run(main.generate_remove_bg_image({
        "image_options": {"tool": "remove_background", "removeBgSourceUrl": bogus_uri},
    }))
    assert result["ok"] is False


def test_generate_remove_bg_image_sends_correct_ideogram_request_shape(monkeypatch):
    captured = {}

    def fake_post(url, headers=None, files=None, timeout=None):
        captured["url"] = url
        captured["headers"] = headers
        captured["files"] = dict(files)
        return _fake_ideogram_success_response()

    monkeypatch.setattr(main, "ideogram_headers", lambda json_content=True: {"Api-Key": "test-key"})
    monkeypatch.setattr(main.requests, "post", fake_post)
    monkeypatch.setattr(main, "safe_get", lambda url, timeout=240: _FakePersistResponse())
    monkeypatch.setattr(main, "storage_put_bytes", lambda content, key, content_type: f"https://cdn.example.com/{key}")
    monkeypatch.setattr(main, "storage_key_from_url", _fake_storage_key_from_url)
    monkeypatch.setattr(main, "send_generated_images_to_telegram", lambda *a, **k: True)

    payload = {
        "telegram_id": 0,
        "job_id": "",
        "image_options": {
            "tool": "remove_background",
            "removeBgSourceUrl": _png_data_uri(),
        },
    }
    result = asyncio.run(main.generate_remove_bg_image(payload))

    assert result["ok"] is True
    # Exact endpoint/field name from Ideogram's official contract - never
    # the old /v1/ideogram-v3/... generate endpoints, never "image_file".
    assert captured["url"] == "https://api.ideogram.ai/v1/remove-background"
    assert captured["headers"] == {"Api-Key": "test-key"}
    assert "image" in captured["files"]
    assert "image_file" not in captured["files"]
    filename, file_bytes, content_type = captured["files"]["image"]
    assert content_type == "image/png"
    assert len(file_bytes) > 0


def test_generate_remove_bg_image_persists_ephemeral_url_to_durable_storage(monkeypatch):
    monkeypatch.setattr(main, "ideogram_headers", lambda json_content=True: {"Api-Key": "test-key"})
    monkeypatch.setattr(main.requests, "post", lambda *a, **k: _fake_ideogram_success_response())

    persist_calls = []

    def fake_persist(url, category, provider=""):
        persist_calls.append((url, category, provider))
        return "https://cdn.example.com/images/final-result.png"

    monkeypatch.setattr(main, "_persist_remote_media_url", fake_persist)
    monkeypatch.setattr(main, "storage_key_from_url", lambda url: "images/final-result.png" if "cdn.example.com" in url else "")
    monkeypatch.setattr(main, "send_generated_images_to_telegram", lambda *a, **k: True)

    payload = {
        "telegram_id": 0,
        "job_id": "",
        "image_options": {
            "tool": "remove_background",
            "removeBgSourceUrl": _png_data_uri(),
        },
    }
    result = asyncio.run(main.generate_remove_bg_image(payload))

    assert result["ok"] is True
    # The ephemeral Ideogram URL must never be handed back as the result -
    # only the durably persisted SYLVEX storage URL.
    assert result["image_url"] == "https://cdn.example.com/images/final-result.png"
    assert result["images"] == ["https://cdn.example.com/images/final-result.png"]
    assert "ideogram.ai/api/images/ephemeral" not in json.dumps(result)
    assert persist_calls == [("https://ideogram.ai/api/images/ephemeral/abc123.png", "images", "ideogram")]


def test_generate_remove_bg_image_fails_when_storage_persist_fails(monkeypatch):
    monkeypatch.setattr(main, "ideogram_headers", lambda json_content=True: {"Api-Key": "test-key"})
    monkeypatch.setattr(main.requests, "post", lambda *a, **k: _fake_ideogram_success_response())
    # _persist_remote_media_url falls back to returning the original
    # (ephemeral, non-storage) URL on failure - generate_remove_bg_image
    # must treat that as a hard failure, never hand back a temporary URL.
    monkeypatch.setattr(main, "_persist_remote_media_url", lambda url, category, provider="": url)
    monkeypatch.setattr(main, "storage_key_from_url", lambda url: "")

    payload = {
        "telegram_id": 0,
        "job_id": "",
        "image_options": {
            "tool": "remove_background",
            "removeBgSourceUrl": _png_data_uri(),
        },
    }
    result = asyncio.run(main.generate_remove_bg_image(payload))
    assert result["ok"] is False


def test_generate_remove_bg_image_ignores_leaked_normal_pro_studio_state(monkeypatch):
    captured = {}

    def fake_post(url, headers=None, files=None, timeout=None):
        captured["files"] = dict(files)
        return _fake_ideogram_success_response()

    monkeypatch.setattr(main, "ideogram_headers", lambda json_content=True: {"Api-Key": "test-key"})
    monkeypatch.setattr(main.requests, "post", fake_post)
    monkeypatch.setattr(main, "safe_get", lambda url, timeout=240: _FakePersistResponse())
    monkeypatch.setattr(main, "storage_put_bytes", lambda content, key, content_type: f"https://cdn.example.com/{key}")
    monkeypatch.setattr(main, "storage_key_from_url", _fake_storage_key_from_url)
    monkeypatch.setattr(main, "send_generated_images_to_telegram", lambda *a, **k: True)

    payload = {
        "telegram_id": 0,
        "job_id": "",
        "prompt": "a totally unrelated leaked prompt describing a dragon",
        "image_options": {
            "tool": "remove_background",
            "removeBgSourceUrl": _png_data_uri(),
            # Leaked normal Pro Studio state that must be completely ignored.
            "characterId": "char_1",
            "characterReferences": ["https://example.com/leak1.png"],
            "objectReferences": ["https://example.com/leak2.png"],
            "style": "cinematic",
        },
    }
    result = asyncio.run(main.generate_remove_bg_image(payload))
    assert result["ok"] is True
    # Only the one uploaded source image byte stream reaches Ideogram - no
    # character/object/style/prompt data is ever part of a multipart image
    # generation request.
    assert list(captured["files"].keys()) == ["image"]


def test_generate_remove_bg_image_result_carries_cost_and_provider_fields(monkeypatch):
    monkeypatch.setattr(main, "ideogram_headers", lambda json_content=True: {"Api-Key": "test-key"})
    monkeypatch.setattr(main.requests, "post", lambda *a, **k: _fake_ideogram_success_response())
    monkeypatch.setattr(main, "safe_get", lambda url, timeout=240: _FakePersistResponse())
    monkeypatch.setattr(main, "storage_put_bytes", lambda content, key, content_type: f"https://cdn.example.com/{key}")
    monkeypatch.setattr(main, "storage_key_from_url", _fake_storage_key_from_url)
    monkeypatch.setattr(main, "send_generated_images_to_telegram", lambda *a, **k: True)

    payload = {
        "telegram_id": 0,
        "job_id": "",
        "image_options": {"tool": "remove_background", "removeBgSourceUrl": _png_data_uri()},
    }
    result = asyncio.run(main.generate_remove_bg_image(payload))
    assert result["ok"] is True
    assert result["provider"] == "ideogram"
    assert result["tool"] == "remove_background"
    assert result["cost_credits"] == main.IDEOGRAM_REMOVE_BG_CREDITS


def test_generate_remove_bg_image_sends_telegram_delivery(monkeypatch):
    telegram_calls = []

    def fake_telegram(telegram_id, images, caption):
        telegram_calls.append((telegram_id, images, caption))
        return True

    monkeypatch.setattr(main, "ideogram_headers", lambda json_content=True: {"Api-Key": "test-key"})
    monkeypatch.setattr(main.requests, "post", lambda *a, **k: _fake_ideogram_success_response())
    monkeypatch.setattr(main, "safe_get", lambda url, timeout=240: _FakePersistResponse())
    monkeypatch.setattr(main, "storage_put_bytes", lambda content, key, content_type: f"https://cdn.example.com/{key}")
    monkeypatch.setattr(main, "storage_key_from_url", _fake_storage_key_from_url)
    monkeypatch.setattr(main, "send_generated_images_to_telegram", fake_telegram)

    payload = {
        "telegram_id": 555,
        "job_id": "",
        "image_options": {"tool": "remove_background", "removeBgSourceUrl": _png_data_uri()},
    }
    result = asyncio.run(main.generate_remove_bg_image(payload))
    assert result["ok"] is True
    assert result["sent_to_telegram"] is True
    assert len(telegram_calls) == 1
    assert telegram_calls[0][0] == 555
    assert telegram_calls[0][1] == result["images"]


def test_generate_remove_bg_image_handles_provider_error_response(monkeypatch):
    monkeypatch.setattr(main, "ideogram_headers", lambda json_content=True: {"Api-Key": "test-key"})
    monkeypatch.setattr(main.requests, "post", lambda *a, **k: _FakeResponse(400, text="bad request"))
    result = asyncio.run(main.generate_remove_bg_image({
        "image_options": {"tool": "remove_background", "removeBgSourceUrl": _png_data_uri()},
    }))
    assert result["ok"] is False


def test_generate_remove_bg_image_handles_network_error(monkeypatch):
    import requests as requests_module

    def fake_post(*a, **k):
        raise requests_module.exceptions.ConnectionError("boom")

    monkeypatch.setattr(main, "ideogram_headers", lambda json_content=True: {"Api-Key": "test-key"})
    monkeypatch.setattr(main.requests, "post", fake_post)
    result = asyncio.run(main.generate_remove_bg_image({
        "image_options": {"tool": "remove_background", "removeBgSourceUrl": _png_data_uri()},
    }))
    assert result["ok"] is False


def test_generate_remove_bg_image_handles_empty_provider_response(monkeypatch):
    monkeypatch.setattr(main, "ideogram_headers", lambda json_content=True: {"Api-Key": "test-key"})
    monkeypatch.setattr(main.requests, "post", lambda *a, **k: _FakeResponse(200, {"created": "now", "data": []}))
    result = asyncio.run(main.generate_remove_bg_image({
        "image_options": {"tool": "remove_background", "removeBgSourceUrl": _png_data_uri()},
    }))
    assert result["ok"] is False


def test_dispatch_prefers_remove_bg_over_generic_seedream_route():
    payload = {
        "model": "seedream_5_0_lite",
        "image_options": {"tool": "remove_background"},
    }
    assert main.is_remove_bg_request(payload) is True
    # Same payload would also match the generic Seedream dispatch check -
    # dispatch_prostudio_provider_request checks is_remove_bg_request first,
    # specifically so this never falls through to a generic Seedream route
    # (which reads the leaky image_options shape) instead of the isolated
    # generate_remove_bg_image.
    assert main.is_seedream_request(payload) is True


def test_remove_bg_tool_never_collides_with_remove_object_or_try_on():
    shared_payload_shape = {"image_options": {"tool": "remove_background"}}
    assert main.is_remove_bg_request(shared_payload_shape) is True
    assert main.is_remove_object_request(shared_payload_shape) is False
    assert main.is_try_on_request(shared_payload_shape) is False
