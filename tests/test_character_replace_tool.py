"""Character Replace is its own isolated Quick Tool generation flow, rebuilt
from scratch on the same isolation pattern as Try-On/Remove Object/Remove
Background: its request must be built from exactly the tool-owned fields
below and never from normal Pro Studio composer state (Character/Object/
Style/prompt/references).

image_options fields (the single canonical shape - frontend, backend
predicate, job payload, pricing and result metadata all use the exact same
names):
  - tool: "replace_character" (main.CHARACTER_REPLACE_TOOL_KEY)
  - characterReplaceSourceUrl: the scene/photo whose person is replaced
  - characterReplaceIdentitySource: "character" | "history" | "upload"
  - characterReplaceIdentityImageUrl: the single resolved identity image
    (a saved Character's own avatar, or the selected History/Upload image)
  - characterReplaceIdentityReferenceUrls: up to 3 of a Character's own
    reference images - only meaningful when identitySource == "character"

It calls Black Forest Labs' real FLUX.2 [max] API - POST
https://api.bfl.ai/v1/flux-2-max, JSON body, x-key auth (flux_headers(),
the existing BFL_API_KEY/FLUX_API_KEY env var chain) - async submit+poll via
the existing poll_flux_image() (status=="Ready" -> result.sample). Images
are sent to FLUX in a fixed order: input_image (source), input_image_2
(identity), input_image_3/4/5 (up to 3 Character references). BFL's result
URL is temporary, so it must be persisted to durable SYLVEX storage
synchronously before the function ever returns.

Pricing is BFL's own real formula (not a flat per-tool fee): $0.07 for the
first output megapixel + $0.03/extra output MP + $0.03 per input image
(each billed as 1 MP), +50% SYLVEX markup, rounded up to a whole credit -
credits = ceil(provider_cost_usd * 1.5 * 100). Two Sources + 1 identity
image (2 inputs) -> 20 credits; source + avatar + 3 refs (5 inputs) -> 33
credits."""
import asyncio
import json

import main


def _png_data_uri():
    return "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="


def _png_data_uri_sized(width, height):
    import base64
    import io as _io

    from PIL import Image

    img = Image.new("RGB", (width, height), (20, 40, 60))
    buf = _io.BytesIO()
    img.save(buf, format="PNG")
    encoded = base64.b64encode(buf.getvalue()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


class _FakeResponse:
    # Doubles as both a JSON provider-API response (status_code/text, used
    # for submit/poll) and a raw-bytes response for _persist_remote_media_
    # url's own safe_get() call (headers/content/raise_for_status) - the
    # isolated flow routes both through main.safe_get during the success
    # path, so one fake response needs to satisfy both call sites.
    headers = {"content-type": "image/jpeg"}
    content = b"final-character-replace-bytes"

    def __init__(self, status_code=200, payload=None, text=None):
        self.status_code = status_code
        self.text = json.dumps(payload) if payload is not None else (text or "")

    def raise_for_status(self):
        return None


class _FakePersistResponse:
    headers = {"content-type": "image/png"}
    content = b"final-character-replace-bytes"

    def raise_for_status(self):
        return None


def _fake_flux_headers():
    return {"accept": "application/json", "x-key": "test-bfl-key", "Content-Type": "application/json"}


def _fake_storage_key_from_url(url):
    return url.split("https://cdn.example.com/", 1)[1] if url.startswith("https://cdn.example.com/") else ""


def _character_replace_payload(**overrides):
    opts = {
        "tool": "replace_character",
        "characterReplaceSourceUrl": "https://example.com/source.png",
        "characterReplaceIdentitySource": "upload",
        "characterReplaceIdentityImageUrl": "https://example.com/identity.png",
        "characterReplaceIdentityReferenceUrls": [],
    }
    opts.update(overrides)
    return {
        "telegram_id": 0,
        "job_id": "",
        "image_options": opts,
    }


def _apply_success_mocks(monkeypatch, submit_response=None):
    monkeypatch.setattr(main, "flux_headers", _fake_flux_headers)
    monkeypatch.setattr(main.requests, "post", lambda *a, **k: submit_response or _FakeResponse(200, {"id": "req_1", "polling_url": "https://api.bfl.ai/v1/get_result?id=req_1"}))
    monkeypatch.setattr(main, "safe_get", lambda url, headers=None, timeout=None: _FakeResponse(200, {"status": "Ready", "result": {"sample": "https://delivery.bfl.ai/results/req_1.jpeg"}}))
    monkeypatch.setattr(main, "storage_put_bytes", lambda content, key, content_type: f"https://cdn.example.com/{key}")
    monkeypatch.setattr(main, "storage_key_from_url", _fake_storage_key_from_url)
    monkeypatch.setattr(main, "send_generated_images_to_telegram", lambda *a, **k: True)


# --- Tool identifier / dispatch predicate -----------------------------------

def test_is_replace_character_request_detects_tool_flag():
    assert main.is_replace_character_request({"image_options": {"tool": "replace_character"}}) is True
    assert main.is_replace_character_request({"image_options": {"tool": "remove_object"}}) is False
    assert main.is_replace_character_request({"image_options": {}}) is False
    assert main.is_replace_character_request({}) is False


def test_is_replace_character_request_ignores_case_and_whitespace():
    assert main.is_replace_character_request({"image_options": {"tool": " Replace_Character "}}) is True


def test_character_replace_tool_never_collides_with_other_isolated_tools():
    payload = {"image_options": {"tool": "replace_character"}}
    assert main.is_replace_character_request(payload) is True
    assert main.is_remove_object_request(payload) is False
    assert main.is_try_on_request(payload) is False
    assert main.is_remove_bg_request(payload) is False


def test_dispatch_prefers_replace_character_over_generic_seedream_route():
    payload = {
        "model": "seedream_5_0_lite",
        "image_options": {"tool": "replace_character"},
    }
    assert main.is_replace_character_request(payload) is True
    # Same payload would also match the generic Seedream dispatch check -
    # dispatch_prostudio_provider_request checks is_replace_character_request
    # first, specifically so this never falls through to a generic Seedream
    # route (which reads the leaky image_options shape) instead of the
    # isolated generate_character_replace_image.
    assert main.is_seedream_request(payload) is True


def test_replace_character_payload_routes_through_dispatch_to_dedicated_function(monkeypatch):
    """Regression-style routing test, same shape as the Remove Background
    routing fix: a real Character Replace payload must be dispatched by
    dispatch_prostudio_provider_request() to generate_character_replace_
    image() - it must never fall through to the generic image_generation()
    dispatcher."""
    calls = {"replace_character": 0, "generic": 0}

    async def fake_generate_character_replace_image(payload):
        calls["replace_character"] += 1
        return {"ok": True, "type": "image", "image_url": "https://cdn.example.com/result.png", "images": ["https://cdn.example.com/result.png"]}

    async def fake_image_generation(payload):
        calls["generic"] += 1
        return {"ok": False, "error": "Unknown provider model mapping"}

    monkeypatch.setattr(main, "generate_character_replace_image", fake_generate_character_replace_image)
    monkeypatch.setattr(main, "image_generation", fake_image_generation)

    payload = _character_replace_payload()
    payload.update({"mode": "image", "category": "image", "model": "flux_2_max_character_replace", "provider": "flux"})

    result = asyncio.run(main.dispatch_prostudio_provider_request(
        payload["job_id"] or "job_1", payload, "image", payload["model"], payload["provider"], {"text", "chat", "pro", "lite"},
    ))

    assert calls["replace_character"] == 1
    assert calls["generic"] == 0
    assert result["ok"] is True


def test_image_generation_refuses_misrouted_replace_character_payload(monkeypatch):
    """Defense in depth: if a replace_character-tagged payload ever reaches
    the generic image_generation() dispatcher directly (bypassing
    dispatch_prostudio_provider_request()'s own routing), it must fail fast
    with a clear, specific error and never attempt to resolve
    "flux_2_max_character_replace" as if it were a real selectable model."""
    def _explode(*a, **k):
        raise AssertionError("must never attempt a model-mapping lookup for a misrouted replace_character payload")

    monkeypatch.setattr(main, "image_provider_mapping", _explode)
    payload = _character_replace_payload()
    payload.update({"model": "flux_2_max_character_replace", "provider": "flux"})
    result = asyncio.run(main.image_generation(payload))
    assert result["ok"] is False
    assert result["raw_error"] == "replace_character_misrouted_to_image_generation"


def test_other_quick_tools_unaffected_by_character_replace():
    # Remove Object/Try-On/Remove Background's own predicates must keep
    # working exactly as before - Character Replace is purely additive.
    assert main.is_remove_object_request({"image_options": {"tool": "remove_object"}}) is True
    assert main.is_try_on_request({"image_options": {"tool": "try_on"}}) is True
    assert main.is_remove_bg_request({"image_options": {"tool": "remove_background"}}) is True


# --- Pricing -----------------------------------------------------------------

def test_character_replace_input_image_count_upload_or_history_is_two():
    opts = {
        "characterReplaceSourceUrl": "https://example.com/source.png",
        "characterReplaceIdentitySource": "upload",
        "characterReplaceIdentityImageUrl": "https://example.com/identity.png",
    }
    assert main.character_replace_input_image_count(opts) == 2


def test_character_replace_input_image_count_character_source_counts_avatar_plus_refs():
    opts = {
        "characterReplaceSourceUrl": "https://example.com/source.png",
        "characterReplaceIdentitySource": "character",
        "characterReplaceIdentityImageUrl": "https://example.com/avatar.png",
        "characterReplaceIdentityReferenceUrls": [
            "https://example.com/ref1.png",
            "https://example.com/ref2.png",
            "https://example.com/ref3.png",
        ],
    }
    assert main.character_replace_input_image_count(opts) == 5


def test_character_replace_input_image_count_ignores_references_when_not_character_source():
    # Mutual exclusivity, enforced defensively on the backend too: stray
    # characterReplaceIdentityReferenceUrls must never inflate the count
    # (or the price, or the FLUX request) unless identitySource is
    # genuinely "character".
    opts = {
        "characterReplaceSourceUrl": "https://example.com/source.png",
        "characterReplaceIdentitySource": "history",
        "characterReplaceIdentityImageUrl": "https://example.com/identity.png",
        "characterReplaceIdentityReferenceUrls": ["https://example.com/leaked-ref.png"],
    }
    assert main.character_replace_input_image_count(opts) == 2


def test_character_replace_input_image_count_caps_at_five():
    opts = {
        "characterReplaceSourceUrl": "https://example.com/source.png",
        "characterReplaceIdentitySource": "character",
        "characterReplaceIdentityImageUrl": "https://example.com/avatar.png",
        "characterReplaceIdentityReferenceUrls": [f"https://example.com/ref{i}.png" for i in range(1, 6)],
    }
    assert main.character_replace_input_image_count(opts) == 5


def test_character_replace_cost_info_matches_worked_examples():
    # Source + 1 identity image (2 inputs): $0.07 + 2*$0.03 = $0.13 provider
    # cost -> ceil($0.13 * 1.5 * 100) = 20 credits.
    two_inputs = main.character_replace_cost_info(2)
    assert two_inputs["credits"] == 20
    assert two_inputs["provider_cost_usd"] == 0.13

    # Source + avatar + 3 refs (5 inputs): $0.07 + 5*$0.03 = $0.22 provider
    # cost -> ceil($0.22 * 1.5 * 100) = 33 credits.
    five_inputs = main.character_replace_cost_info(5)
    assert five_inputs["credits"] == 33
    assert five_inputs["provider_cost_usd"] == 0.22


def test_estimate_generation_cost_prices_replace_character_from_real_image_count():
    upload_estimate = main.estimate_generation_cost({
        "mode": "image",
        "image_options": {
            "tool": "replace_character",
            "characterReplaceSourceUrl": "https://example.com/source.png",
            "characterReplaceIdentitySource": "upload",
            "characterReplaceIdentityImageUrl": "https://example.com/identity.png",
        },
    })
    assert upload_estimate["credits"] == 20
    assert upload_estimate["pricing_available"] is True

    character_estimate = main.estimate_generation_cost({
        "mode": "image",
        "image_options": {
            "tool": "replace_character",
            "characterReplaceSourceUrl": "https://example.com/source.png",
            "characterReplaceIdentitySource": "character",
            "characterReplaceIdentityImageUrl": "https://example.com/avatar.png",
            "characterReplaceIdentityReferenceUrls": [
                "https://example.com/ref1.png",
                "https://example.com/ref2.png",
                "https://example.com/ref3.png",
            ],
        },
    })
    assert character_estimate["credits"] == 33
    # Never hardcoded - a different reference count must yield a different
    # price, not always 20 or always 33.
    assert character_estimate["credits"] != upload_estimate["credits"]


def test_estimate_generation_cost_replace_character_price_scales_with_reference_count():
    def price_for(ref_count):
        return main.estimate_generation_cost({
            "mode": "image",
            "image_options": {
                "tool": "replace_character",
                "characterReplaceSourceUrl": "https://example.com/source.png",
                "characterReplaceIdentitySource": "character",
                "characterReplaceIdentityImageUrl": "https://example.com/avatar.png",
                "characterReplaceIdentityReferenceUrls": [f"https://example.com/ref{i}.png" for i in range(ref_count)],
            },
        })["credits"]

    prices = [price_for(n) for n in (0, 1, 2, 3)]
    assert prices == sorted(prices)
    assert len(set(prices)) == 4


# --- Provider call: request shape, auth, image ordering ----------------------

def test_generate_character_replace_image_requires_source_and_identity(monkeypatch):
    monkeypatch.setattr(main, "flux_headers", _fake_flux_headers)
    result = asyncio.run(main.generate_character_replace_image({
        "image_options": {"tool": "replace_character", "characterReplaceIdentityImageUrl": "https://example.com/i.png"},
    }))
    assert result["ok"] is False

    result2 = asyncio.run(main.generate_character_replace_image({
        "image_options": {"tool": "replace_character", "characterReplaceSourceUrl": "https://example.com/s.png"},
    }))
    assert result2["ok"] is False


def test_generate_character_replace_image_requires_api_key(monkeypatch):
    monkeypatch.setattr(main, "flux_headers", lambda: {})
    result = asyncio.run(main.generate_character_replace_image(_character_replace_payload()))
    assert result["ok"] is False


def test_generate_character_replace_image_uses_correct_endpoint_and_auth(monkeypatch):
    captured = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        captured["url"] = url
        captured["headers"] = headers
        captured["json"] = json
        return _FakeResponse(200, {"id": "req_1", "polling_url": "https://api.bfl.ai/v1/get_result?id=req_1"})

    monkeypatch.setattr(main, "flux_headers", _fake_flux_headers)
    monkeypatch.setattr(main.requests, "post", fake_post)
    monkeypatch.setattr(main, "safe_get", lambda url, headers=None, timeout=None: _FakeResponse(200, {"status": "Ready", "result": {"sample": "https://delivery.bfl.ai/results/req_1.jpeg"}}))
    monkeypatch.setattr(main, "storage_put_bytes", lambda content, key, content_type: f"https://cdn.example.com/{key}")
    monkeypatch.setattr(main, "storage_key_from_url", _fake_storage_key_from_url)
    monkeypatch.setattr(main, "send_generated_images_to_telegram", lambda *a, **k: True)

    result = asyncio.run(main.generate_character_replace_image(_character_replace_payload()))

    assert result["ok"] is True
    # Exact endpoint from the task's official contract - never a generic
    # /v1/{provider_model} join like the shared call_flux_image() uses for
    # Kontext.
    assert captured["url"] == "https://api.bfl.ai/v1/flux-2-max"
    assert captured["headers"] == {"accept": "application/json", "x-key": "test-bfl-key", "Content-Type": "application/json"}
    assert captured["headers"]["x-key"] == "test-bfl-key"


def test_generate_character_replace_image_upload_source_sends_two_images_in_order(monkeypatch):
    captured = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        captured["json"] = json
        return _FakeResponse(200, {"id": "req_1", "polling_url": "https://api.bfl.ai/v1/get_result?id=req_1"})

    monkeypatch.setattr(main, "flux_headers", _fake_flux_headers)
    monkeypatch.setattr(main.requests, "post", fake_post)
    monkeypatch.setattr(main, "safe_get", lambda url, headers=None, timeout=None: _FakeResponse(200, {"status": "Ready", "result": {"sample": "https://delivery.bfl.ai/results/req_1.jpeg"}}))
    monkeypatch.setattr(main, "storage_put_bytes", lambda content, key, content_type: f"https://cdn.example.com/{key}")
    monkeypatch.setattr(main, "storage_key_from_url", _fake_storage_key_from_url)
    monkeypatch.setattr(main, "send_generated_images_to_telegram", lambda *a, **k: True)

    payload = _character_replace_payload(
        characterReplaceSourceUrl="https://example.com/source.png",
        characterReplaceIdentitySource="upload",
        characterReplaceIdentityImageUrl="https://example.com/uploaded-face.png",
        characterReplaceIdentityReferenceUrls=[],
    )
    result = asyncio.run(main.generate_character_replace_image(payload))
    assert result["ok"] is True

    body = captured["json"]
    assert body["input_image"] == "https://example.com/source.png"
    assert body["input_image_2"] == "https://example.com/uploaded-face.png"
    assert "input_image_3" not in body
    assert "input_image_4" not in body
    assert "input_image_5" not in body


def test_generate_character_replace_image_history_source_sends_two_images(monkeypatch):
    captured = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        captured["json"] = json
        return _FakeResponse(200, {"id": "req_1", "polling_url": "https://api.bfl.ai/v1/get_result?id=req_1"})

    monkeypatch.setattr(main, "flux_headers", _fake_flux_headers)
    monkeypatch.setattr(main.requests, "post", fake_post)
    monkeypatch.setattr(main, "safe_get", lambda url, headers=None, timeout=None: _FakeResponse(200, {"status": "Ready", "result": {"sample": "https://delivery.bfl.ai/results/req_1.jpeg"}}))
    monkeypatch.setattr(main, "storage_put_bytes", lambda content, key, content_type: f"https://cdn.example.com/{key}")
    monkeypatch.setattr(main, "storage_key_from_url", _fake_storage_key_from_url)
    monkeypatch.setattr(main, "send_generated_images_to_telegram", lambda *a, **k: True)

    payload = _character_replace_payload(
        characterReplaceSourceUrl="https://example.com/source.png",
        characterReplaceIdentitySource="history",
        characterReplaceIdentityImageUrl="https://example.com/history-photo.png",
        characterReplaceIdentityReferenceUrls=[],
    )
    result = asyncio.run(main.generate_character_replace_image(payload))
    assert result["ok"] is True
    body = captured["json"]
    assert body["input_image"] == "https://example.com/source.png"
    assert body["input_image_2"] == "https://example.com/history-photo.png"
    assert "input_image_3" not in body


def test_generate_character_replace_image_character_source_sends_avatar_and_up_to_three_refs_in_order(monkeypatch):
    captured = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        captured["json"] = json
        return _FakeResponse(200, {"id": "req_1", "polling_url": "https://api.bfl.ai/v1/get_result?id=req_1"})

    monkeypatch.setattr(main, "flux_headers", _fake_flux_headers)
    monkeypatch.setattr(main.requests, "post", fake_post)
    monkeypatch.setattr(main, "safe_get", lambda url, headers=None, timeout=None: _FakeResponse(200, {"status": "Ready", "result": {"sample": "https://delivery.bfl.ai/results/req_1.jpeg"}}))
    monkeypatch.setattr(main, "storage_put_bytes", lambda content, key, content_type: f"https://cdn.example.com/{key}")
    monkeypatch.setattr(main, "storage_key_from_url", _fake_storage_key_from_url)
    monkeypatch.setattr(main, "send_generated_images_to_telegram", lambda *a, **k: True)

    payload = _character_replace_payload(
        characterReplaceSourceUrl="https://example.com/source.png",
        characterReplaceIdentitySource="character",
        characterReplaceIdentityImageUrl="https://example.com/avatar.png",
        characterReplaceCharacterId="char_42",
        characterReplaceIdentityReferenceUrls=[
            "https://example.com/ref1.png",
            "https://example.com/ref2.png",
            "https://example.com/ref3.png",
        ],
    )
    result = asyncio.run(main.generate_character_replace_image(payload))
    assert result["ok"] is True

    body = captured["json"]
    # Deterministic BFL slot order per the task's exact contract.
    assert body["input_image"] == "https://example.com/source.png"
    assert body["input_image_2"] == "https://example.com/avatar.png"
    assert body["input_image_3"] == "https://example.com/ref1.png"
    assert body["input_image_4"] == "https://example.com/ref2.png"
    assert body["input_image_5"] == "https://example.com/ref3.png"
    assert "input_image_6" not in body


def test_generate_character_replace_image_uses_fixed_internal_prompt(monkeypatch):
    captured = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        captured["json"] = json
        return _FakeResponse(200, {"id": "req_1", "polling_url": "https://api.bfl.ai/v1/get_result?id=req_1"})

    monkeypatch.setattr(main, "flux_headers", _fake_flux_headers)
    monkeypatch.setattr(main.requests, "post", fake_post)
    monkeypatch.setattr(main, "safe_get", lambda url, headers=None, timeout=None: _FakeResponse(200, {"status": "Ready", "result": {"sample": "https://delivery.bfl.ai/results/req_1.jpeg"}}))
    monkeypatch.setattr(main, "storage_put_bytes", lambda content, key, content_type: f"https://cdn.example.com/{key}")
    monkeypatch.setattr(main, "storage_key_from_url", _fake_storage_key_from_url)
    monkeypatch.setattr(main, "send_generated_images_to_telegram", lambda *a, **k: True)

    result = asyncio.run(main.generate_character_replace_image(_character_replace_payload(
        prompt="a totally unrelated leaked prompt about a dragon",
    )))
    assert result["ok"] is True
    prompt = captured["json"]["prompt"]
    assert prompt == main.build_character_replace_prompt()
    assert "dragon" not in prompt
    assert "identity" in prompt.lower()
    assert "preserve" in prompt.lower()


def test_generate_character_replace_image_ignores_leaked_normal_pro_studio_state(monkeypatch):
    captured = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        captured["json"] = json
        return _FakeResponse(200, {"id": "req_1", "polling_url": "https://api.bfl.ai/v1/get_result?id=req_1"})

    monkeypatch.setattr(main, "flux_headers", _fake_flux_headers)
    monkeypatch.setattr(main.requests, "post", fake_post)
    monkeypatch.setattr(main, "safe_get", lambda url, headers=None, timeout=None: _FakeResponse(200, {"status": "Ready", "result": {"sample": "https://delivery.bfl.ai/results/req_1.jpeg"}}))
    monkeypatch.setattr(main, "storage_put_bytes", lambda content, key, content_type: f"https://cdn.example.com/{key}")
    monkeypatch.setattr(main, "storage_key_from_url", _fake_storage_key_from_url)
    monkeypatch.setattr(main, "send_generated_images_to_telegram", lambda *a, **k: True)

    payload = _character_replace_payload()
    payload["prompt"] = "leaked normal composer prompt"
    payload["image_options"].update({
        "characterId": "char_1",
        "characterReferences": ["https://example.com/leak1.png"],
        "objectReferences": ["https://example.com/leak2.png"],
        "style": "cinematic",
        "characterPrompt": "leaked character prompt text",
        "objectPrompt": "leaked object prompt text",
    })
    result = asyncio.run(main.generate_character_replace_image(payload))
    assert result["ok"] is True
    body = captured["json"]
    serialized = json.dumps(body)
    assert "leak1.png" not in serialized
    assert "leak2.png" not in serialized
    assert "leaked" not in serialized.lower()
    assert "cinematic" not in serialized
    # Only the two isolated images reach FLUX for this upload-source case.
    image_keys = [k for k in body if k.startswith("input_image")]
    assert len(image_keys) == 2


def test_generate_character_replace_image_resolves_data_uri_identity_to_public_url(monkeypatch):
    captured = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        captured["json"] = json
        return _FakeResponse(200, {"id": "req_1", "polling_url": "https://api.bfl.ai/v1/get_result?id=req_1"})

    monkeypatch.setattr(main, "flux_headers", _fake_flux_headers)
    monkeypatch.setattr(main.requests, "post", fake_post)
    monkeypatch.setattr(main, "safe_get", lambda url, headers=None, timeout=None: _FakeResponse(200, {"status": "Ready", "result": {"sample": "https://delivery.bfl.ai/results/req_1.jpeg"}}))
    monkeypatch.setattr(main, "storage_put_bytes", lambda content, key, content_type: f"https://cdn.example.com/{key}")
    monkeypatch.setattr(main, "storage_key_from_url", _fake_storage_key_from_url)
    monkeypatch.setattr(main, "send_generated_images_to_telegram", lambda *a, **k: True)

    payload = _character_replace_payload(
        characterReplaceIdentitySource="upload",
        characterReplaceIdentityImageUrl=_png_data_uri(),
    )
    result = asyncio.run(main.generate_character_replace_image(payload))
    assert result["ok"] is True
    body = captured["json"]
    assert body["input_image_2"].startswith("https://cdn.example.com/")
    assert not body["input_image_2"].startswith("data:")


# --- BFL async poll: Pending -> Ready, and Error handling --------------------

def test_generate_character_replace_image_polls_pending_then_ready(monkeypatch):
    statuses = iter(["Pending", "Pending", "Ready"])
    calls = {"count": 0}

    def fake_get(url, headers=None, timeout=None):
        # Only count polls against BFL's own polling_url - the final
        # download-and-persist step (_persist_remote_media_url) also goes
        # through main.safe_get, against a different URL, and must not be
        # confused with a poll attempt.
        if "get_result" not in url:
            return _FakeResponse(200, {"status": "Ready", "result": {"sample": "https://delivery.bfl.ai/results/req_1.jpeg"}})
        calls["count"] += 1
        status = next(statuses, "Ready")
        if status == "Ready":
            return _FakeResponse(200, {"status": "Ready", "result": {"sample": "https://delivery.bfl.ai/results/req_1.jpeg"}})
        return _FakeResponse(200, {"status": status})

    monkeypatch.setattr(main, "flux_headers", _fake_flux_headers)
    monkeypatch.setattr(main.requests, "post", lambda *a, **k: _FakeResponse(200, {"id": "req_1", "polling_url": "https://api.bfl.ai/v1/get_result?id=req_1"}))
    monkeypatch.setattr(main, "safe_get", fake_get)
    monkeypatch.setattr(main.time, "sleep", lambda *_a, **_k: None)
    monkeypatch.setattr(main, "storage_put_bytes", lambda content, key, content_type: f"https://cdn.example.com/{key}")
    monkeypatch.setattr(main, "storage_key_from_url", _fake_storage_key_from_url)
    monkeypatch.setattr(main, "send_generated_images_to_telegram", lambda *a, **k: True)

    result = asyncio.run(main.generate_character_replace_image(_character_replace_payload()))
    assert result["ok"] is True
    assert calls["count"] == 3


def test_generate_character_replace_image_handles_bfl_error_status(monkeypatch):
    monkeypatch.setattr(main, "flux_headers", _fake_flux_headers)
    monkeypatch.setattr(main.requests, "post", lambda *a, **k: _FakeResponse(200, {"id": "req_1", "polling_url": "https://api.bfl.ai/v1/get_result?id=req_1"}))
    monkeypatch.setattr(main, "safe_get", lambda url, headers=None, timeout=None: _FakeResponse(200, {"status": "Error"}))
    monkeypatch.setattr(main.time, "sleep", lambda *_a, **_k: None)

    result = asyncio.run(main.generate_character_replace_image(_character_replace_payload()))
    assert result["ok"] is False


def test_generate_character_replace_image_handles_missing_polling_url(monkeypatch):
    monkeypatch.setattr(main, "flux_headers", _fake_flux_headers)
    monkeypatch.setattr(main.requests, "post", lambda *a, **k: _FakeResponse(200, {"id": "req_1"}))
    result = asyncio.run(main.generate_character_replace_image(_character_replace_payload()))
    assert result["ok"] is False


def test_generate_character_replace_image_handles_submit_http_error(monkeypatch):
    monkeypatch.setattr(main, "flux_headers", _fake_flux_headers)
    monkeypatch.setattr(main.requests, "post", lambda *a, **k: _FakeResponse(400, text="bad request"))
    result = asyncio.run(main.generate_character_replace_image(_character_replace_payload()))
    assert result["ok"] is False


def test_generate_character_replace_image_handles_network_error(monkeypatch):
    import requests as requests_module

    def fake_post(*a, **k):
        raise requests_module.exceptions.ConnectionError("boom")

    monkeypatch.setattr(main, "flux_headers", _fake_flux_headers)
    monkeypatch.setattr(main.requests, "post", fake_post)
    result = asyncio.run(main.generate_character_replace_image(_character_replace_payload()))
    assert result["ok"] is False


# --- Storage persistence -----------------------------------------------------

def test_generate_character_replace_image_persists_ephemeral_bfl_url_to_durable_storage(monkeypatch):
    persist_calls = []

    def fake_persist(url, category, provider=""):
        persist_calls.append((url, category, provider))
        return "https://cdn.example.com/images/final-result.png"

    monkeypatch.setattr(main, "flux_headers", _fake_flux_headers)
    monkeypatch.setattr(main.requests, "post", lambda *a, **k: _FakeResponse(200, {"id": "req_1", "polling_url": "https://api.bfl.ai/v1/get_result?id=req_1"}))
    monkeypatch.setattr(main, "safe_get", lambda url, headers=None, timeout=None: _FakeResponse(200, {"status": "Ready", "result": {"sample": "https://delivery.bfl.ai/results/req_1.jpeg"}}))
    monkeypatch.setattr(main, "_persist_remote_media_url", fake_persist)
    monkeypatch.setattr(main, "storage_key_from_url", lambda url: "images/final-result.png" if "cdn.example.com" in url else "")
    monkeypatch.setattr(main, "send_generated_images_to_telegram", lambda *a, **k: True)

    result = asyncio.run(main.generate_character_replace_image(_character_replace_payload()))
    assert result["ok"] is True
    assert result["image_url"] == "https://cdn.example.com/images/final-result.png"
    assert result["images"] == ["https://cdn.example.com/images/final-result.png"]
    assert "delivery.bfl.ai" not in json.dumps(result)
    assert persist_calls == [("https://delivery.bfl.ai/results/req_1.jpeg", "images", "flux")]


def test_generate_character_replace_image_fails_when_storage_persist_fails(monkeypatch):
    monkeypatch.setattr(main, "flux_headers", _fake_flux_headers)
    monkeypatch.setattr(main.requests, "post", lambda *a, **k: _FakeResponse(200, {"id": "req_1", "polling_url": "https://api.bfl.ai/v1/get_result?id=req_1"}))
    monkeypatch.setattr(main, "safe_get", lambda url, headers=None, timeout=None: _FakeResponse(200, {"status": "Ready", "result": {"sample": "https://delivery.bfl.ai/results/req_1.jpeg"}}))
    # _persist_remote_media_url falls back to returning the original
    # (ephemeral, non-storage) URL on failure - generate_character_replace_
    # image must treat that as a hard failure, never hand back a temporary
    # BFL URL.
    monkeypatch.setattr(main, "_persist_remote_media_url", lambda url, category, provider="": url)
    monkeypatch.setattr(main, "storage_key_from_url", lambda url: "")

    result = asyncio.run(main.generate_character_replace_image(_character_replace_payload()))
    assert result["ok"] is False


# --- Result metadata / billing / Telegram delivery ---------------------------

def test_generate_character_replace_image_result_carries_cost_and_provider_fields(monkeypatch):
    _apply_success_mocks(monkeypatch)
    payload = _character_replace_payload(
        characterReplaceIdentitySource="character",
        characterReplaceIdentityImageUrl="https://example.com/avatar.png",
        characterReplaceIdentityReferenceUrls=["https://example.com/ref1.png"],
    )
    result = asyncio.run(main.generate_character_replace_image(payload))
    assert result["ok"] is True
    assert result["provider"] == "flux"
    assert result["tool"] == "replace_character"
    assert result["provider_model"] == "flux-2-max"
    # source + avatar + 1 ref = 3 inputs -> $0.07 + 3*$0.03 = $0.16 ->
    # ceil($0.16 * 1.5 * 100) = 24 credits.
    assert result["cost_credits"] == 24


def test_generate_character_replace_image_sends_telegram_delivery(monkeypatch):
    telegram_calls = []

    def fake_telegram(telegram_id, images, caption):
        telegram_calls.append((telegram_id, images, caption))
        return True

    monkeypatch.setattr(main, "flux_headers", _fake_flux_headers)
    monkeypatch.setattr(main.requests, "post", lambda *a, **k: _FakeResponse(200, {"id": "req_1", "polling_url": "https://api.bfl.ai/v1/get_result?id=req_1"}))
    monkeypatch.setattr(main, "safe_get", lambda url, headers=None, timeout=None: _FakeResponse(200, {"status": "Ready", "result": {"sample": "https://delivery.bfl.ai/results/req_1.jpeg"}}))
    monkeypatch.setattr(main, "storage_put_bytes", lambda content, key, content_type: f"https://cdn.example.com/{key}")
    monkeypatch.setattr(main, "storage_key_from_url", _fake_storage_key_from_url)
    monkeypatch.setattr(main, "send_generated_images_to_telegram", fake_telegram)

    payload = _character_replace_payload()
    payload["telegram_id"] = 777
    result = asyncio.run(main.generate_character_replace_image(payload))
    assert result["ok"] is True
    assert result["sent_to_telegram"] is True
    assert len(telegram_calls) == 1
    assert telegram_calls[0][0] == 777
    assert telegram_calls[0][1] == result["images"]


# --- Source aspect ratio preservation -----------------------------------------
#
# FLUX.2 [max] defaults to a square 1024x1024 output when width/height are
# omitted, which would silently turn a portrait/landscape source into a
# square. character_replace_output_dimensions() computes explicit width/
# height that preserve the source's own aspect ratio at ~1 output megapixel
# (BFL's $0.07 first-MP billing tier), in multiples of 16 as BFL requires.
# No resolution selector is added to the UI - this is fully automatic from
# the source image's own real dimensions.

def test_character_replace_output_dimensions_preserves_portrait_orientation():
    width, height = main.character_replace_output_dimensions(1080, 1920)
    assert height > width  # portrait in -> portrait out
    assert width % 16 == 0 and height % 16 == 0
    assert width * height <= main.CHARACTER_REPLACE_OUTPUT_MAX_PIXELS
    # Aspect ratio preserved within the tolerance the 16px grid allows.
    assert abs((width / height) - (1080 / 1920)) < 0.02


def test_character_replace_output_dimensions_preserves_landscape_orientation():
    width, height = main.character_replace_output_dimensions(1920, 1080)
    assert width > height  # landscape in -> landscape out
    assert width % 16 == 0 and height % 16 == 0
    assert width * height <= main.CHARACTER_REPLACE_OUTPUT_MAX_PIXELS
    assert abs((width / height) - (1920 / 1080)) < 0.02


def test_character_replace_output_dimensions_preserves_square_orientation():
    width, height = main.character_replace_output_dimensions(1024, 1024)
    assert width == height  # square in -> square out
    assert width % 16 == 0 and height % 16 == 0
    assert width * height <= main.CHARACTER_REPLACE_OUTPUT_MAX_PIXELS


def test_character_replace_output_dimensions_handles_extreme_aspect_ratio_safely():
    # A pathological aspect ratio must still terminate, stay within the 1 MP
    # cap, and stay on the 16px grid - the shrink loop is bounded by
    # construction (both sides floor at 16px), this just proves it in practice.
    width, height = main.character_replace_output_dimensions(3000, 300)
    assert width % 16 == 0 and height % 16 == 0
    assert width * height <= main.CHARACTER_REPLACE_OUTPUT_MAX_PIXELS
    assert width > height


def test_character_replace_output_dimensions_falls_back_to_square_for_unknown_size():
    # No detectable source dimensions (0, 0) - fall back to BFL's own
    # square default rather than dividing by zero or crashing.
    width, height = main.character_replace_output_dimensions(0, 0)
    assert width == height == 1024


def _apply_success_mocks_with_source_bytes(monkeypatch, source_data_uri):
    monkeypatch.setattr(main, "flux_headers", _fake_flux_headers)
    captured = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        captured["json"] = json
        return _FakeResponse(200, {"id": "req_1", "polling_url": "https://api.bfl.ai/v1/get_result?id=req_1"})

    monkeypatch.setattr(main.requests, "post", fake_post)
    monkeypatch.setattr(main, "safe_get", lambda url, headers=None, timeout=None: _FakeResponse(200, {"status": "Ready", "result": {"sample": "https://delivery.bfl.ai/results/req_1.jpeg"}}))
    monkeypatch.setattr(main, "storage_put_bytes", lambda content, key, content_type: f"https://cdn.example.com/{key}")
    monkeypatch.setattr(main, "storage_key_from_url", _fake_storage_key_from_url)
    monkeypatch.setattr(main, "send_generated_images_to_telegram", lambda *a, **k: True)
    payload = _character_replace_payload(characterReplaceSourceUrl=source_data_uri)
    result = asyncio.run(main.generate_character_replace_image(payload))
    return result, captured


def test_generate_character_replace_image_sends_portrait_width_height_for_portrait_source(monkeypatch):
    result, captured = _apply_success_mocks_with_source_bytes(monkeypatch, _png_data_uri_sized(600, 900))
    assert result["ok"] is True
    body = captured["json"]
    assert body["height"] > body["width"]
    assert body["width"] % 16 == 0 and body["height"] % 16 == 0
    assert body["width"] * body["height"] <= main.CHARACTER_REPLACE_OUTPUT_MAX_PIXELS
    expected_width, expected_height = main.character_replace_output_dimensions(600, 900)
    assert (body["width"], body["height"]) == (expected_width, expected_height)


def test_generate_character_replace_image_sends_landscape_width_height_for_landscape_source(monkeypatch):
    result, captured = _apply_success_mocks_with_source_bytes(monkeypatch, _png_data_uri_sized(900, 600))
    assert result["ok"] is True
    body = captured["json"]
    assert body["width"] > body["height"]
    assert body["width"] % 16 == 0 and body["height"] % 16 == 0
    assert body["width"] * body["height"] <= main.CHARACTER_REPLACE_OUTPUT_MAX_PIXELS
    expected_width, expected_height = main.character_replace_output_dimensions(900, 600)
    assert (body["width"], body["height"]) == (expected_width, expected_height)


def test_generate_character_replace_image_sends_square_width_height_for_square_source(monkeypatch):
    result, captured = _apply_success_mocks_with_source_bytes(monkeypatch, _png_data_uri_sized(800, 800))
    assert result["ok"] is True
    body = captured["json"]
    assert body["width"] == body["height"]
    assert body["width"] % 16 == 0
    assert body["width"] * body["height"] <= main.CHARACTER_REPLACE_OUTPUT_MAX_PIXELS
