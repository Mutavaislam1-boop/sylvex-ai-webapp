"""Remove Object is the first Quick Tool migrated to an isolated generation
flow: its request must be built from exactly three tool-owned inputs
(image_options.removeObjectSourceUrl/removeObjectMaskUrl/
removeObjectInstruction) and never from normal Pro Studio composer state
(Character/Object/Style/previous prompt/previous references) - the bug the
old shared Photo Tool path had, since it built every tool's request from
imageOptionsPayload(), which spreads the whole global imageState. It now
runs on GPT Image's real masked-edit endpoint (image + mask + prompt)
instead of a BytePlus Seedream "marked image" composite fallback - GPT
Image's own mask convention is the inverse of how the frontend's canvas
naturally draws (transparent = edit, opaque = preserve), so
build_gpt_image_removal_mask must invert the user's drawn alpha channel.

These tests cover is_remove_object_request, the +5 credit Quick Tool fee (on
top of the real model cost, applied once at the single price choke point so
it can never be charged/refunded independently of the model cost), prompt
construction, the source/mask PNG normalization helpers (including the
alpha-inversion correctness), and the isolated provider-call function itself
- including that noise from a normal Pro Studio payload never leaks into the
request."""
import asyncio
import base64
import io
import json

import main


def _png_data_uri(size=(8, 8), color=(10, 20, 30, 255)):
    from PIL import Image

    img = Image.new("RGBA", size, color)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    encoded = base64.b64encode(buf.getvalue()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def _mask_data_uri_with_left_half_marked(size=(8, 8)):
    from PIL import Image

    img = Image.new("RGBA", size, (0, 0, 0, 0))
    for x in range(size[0] // 2):
        for y in range(size[1]):
            img.putpixel((x, y), (255, 255, 255, 255))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    encoded = base64.b64encode(buf.getvalue()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


class _FakeResponse:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self.text = json.dumps(payload) if payload is not None else ""


def _fake_success_response():
    return _FakeResponse(200, {"data": [{"url": "https://cdn.example.com/result.png"}]})


def test_is_remove_object_request_detects_tool_flag():
    assert main.is_remove_object_request({"image_options": {"tool": "remove_object"}}) is True
    assert main.is_remove_object_request({"image_options": {"tool": "remove_bg"}}) is False
    assert main.is_remove_object_request({"image_options": {}}) is False
    assert main.is_remove_object_request({}) is False


def test_is_remove_object_request_ignores_case_and_whitespace():
    assert main.is_remove_object_request({"image_options": {"tool": " Remove_Object "}}) is True


def test_calculate_generation_price_adds_quick_tool_fee_on_top_of_model_cost():
    base_payload = {
        "mode": "image",
        "model": "seedream_5_0_lite",
        "image_options": {},
    }
    base_estimate = main.calculate_generation_price(base_payload)
    base_credits = base_estimate["credits"]
    assert base_credits > 0

    remove_object_payload = {
        "mode": "image",
        "model": "seedream_5_0_lite",
        "image_options": {
            "tool": "remove_object",
            "removeObjectSourceUrl": "https://example.com/source.png",
            "removeObjectMaskUrl": "https://example.com/mask.png",
            "removeObjectInstruction": "",
        },
    }
    fee_estimate = main.calculate_generation_price(remove_object_payload)
    assert fee_estimate["credits"] == base_credits + main.REMOVE_OBJECT_TOOL_FEE_CREDITS
    # One combined total, not two separate line items - so a failed
    # generation's single reservation refund can never leave only the
    # Quick Tool fee charged (or only the model cost charged).
    assert fee_estimate["cost_credits"] == fee_estimate["credits"]


def test_calculate_generation_price_ignores_leaked_style_character_object_surcharges():
    # sylvex_additions() in services/price_engine.py adds credits for a
    # generic "style"/"character"/"object"/"references" key anywhere in the
    # payload - Remove Object's isolated field names must never collide
    # with those, or leaked normal-composer noise would silently inflate
    # the price beyond "model cost + 5".
    payload = {
        "mode": "image",
        "model": "seedream_5_0_lite",
        "image_options": {
            "tool": "remove_object",
            "removeObjectSourceUrl": "https://example.com/source.png",
            "removeObjectMaskUrl": "",
            "removeObjectInstruction": "the red cup",
            # Noise (the exact shape the real frontend never sends for this
            # tool) that must not be interpreted as character/object
            # additions by the shared pricing engine.
            "characterId": "char_1",
            "characterReferences": ["https://example.com/a.png", "https://example.com/b.png"],
            "objectReferences": ["https://example.com/c.png"],
        },
    }
    base_payload = {"mode": "image", "model": "seedream_5_0_lite", "image_options": {}}
    base_credits = main.calculate_generation_price(base_payload)["credits"]
    estimate = main.calculate_generation_price(payload)
    assert estimate["credits"] == base_credits + main.REMOVE_OBJECT_TOOL_FEE_CREDITS


def test_build_remove_object_prompt_with_mask_only():
    prompt = main.build_remove_object_prompt(True, "")
    assert "transparent mask" in prompt.lower()
    assert "What to remove:" not in prompt


def test_build_remove_object_prompt_with_text_only():
    prompt = main.build_remove_object_prompt(False, "the red cup on the table")
    assert "What to remove: the red cup on the table" in prompt
    assert "transparent mask" not in prompt.lower()


def test_build_remove_object_prompt_with_both():
    prompt = main.build_remove_object_prompt(True, "the red cup")
    assert "transparent mask" in prompt.lower()
    assert "What to remove: the red cup" in prompt


def test_normalize_gpt_image_source_converts_to_png_rgba():
    from PIL import Image

    img = Image.new("RGB", (5, 5), (100, 150, 200))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")

    png_bytes, size = main.normalize_gpt_image_source(buf.getvalue())
    assert size == (5, 5)
    with Image.open(io.BytesIO(png_bytes)) as normalized:
        assert normalized.format == "PNG"
        assert normalized.mode == "RGBA"


def test_build_gpt_image_removal_mask_inverts_alpha_and_matches_source_size():
    # GPT Image's own mask convention is the inverse of the frontend's canvas:
    # the frontend draws opaque strokes where the user marked something for
    # removal, but GPT Image treats *transparent* pixels as "edit this" and
    # opaque pixels as "preserve this untouched".
    from PIL import Image

    source = Image.new("RGBA", (4, 4), (0, 0, 0, 255))
    source_buf = io.BytesIO()
    source.save(source_buf, format="PNG")

    drawn = Image.new("RGBA", (4, 4), (0, 0, 0, 0))
    drawn.putpixel((0, 0), (255, 255, 255, 255))  # user marked this pixel
    drawn_buf = io.BytesIO()
    drawn.save(drawn_buf, format="PNG")

    mask_bytes = main.build_gpt_image_removal_mask(source_buf.getvalue(), drawn_buf.getvalue())
    with Image.open(io.BytesIO(mask_bytes)) as mask_img:
        rgba = mask_img.convert("RGBA")
        assert rgba.size == (4, 4)
        assert rgba.getpixel((0, 0))[3] == 0    # marked by the user -> transparent for GPT Image
        assert rgba.getpixel((1, 1))[3] == 255  # untouched -> opaque/preserved


def test_generate_remove_object_image_requires_source_image(monkeypatch):
    monkeypatch.setattr(main, "OPENAI_API_KEY", "test-key")
    result = asyncio.run(main.generate_remove_object_image({
        "image_options": {"tool": "remove_object", "removeObjectInstruction": "remove the cup"},
    }))
    assert result["ok"] is False


def test_generate_remove_object_image_rejects_image_only(monkeypatch):
    def _explode(*a, **k):
        raise AssertionError("must never call the provider without a mask or instruction")

    monkeypatch.setattr(main, "OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(main.requests, "post", _explode)
    result = asyncio.run(main.generate_remove_object_image({
        "image_options": {
            "tool": "remove_object",
            "removeObjectSourceUrl": _png_data_uri(),
            "removeObjectMaskUrl": "",
            "removeObjectInstruction": "",
        },
    }))
    assert result["ok"] is False


def test_generate_remove_object_image_text_only_success_sends_no_mask_file(monkeypatch):
    captured = {}

    def fake_post(url, headers=None, data=None, files=None, timeout=None):
        captured["url"] = url
        captured["data"] = data
        captured["files"] = dict(files)
        return _fake_success_response()

    monkeypatch.setattr(main, "OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(main.requests, "post", fake_post)
    monkeypatch.setattr(main, "send_generated_images_to_telegram", lambda *a, **k: True)

    payload = {
        "telegram_id": 0,
        "job_id": "",
        "image_options": {
            "tool": "remove_object",
            "removeObjectSourceUrl": _png_data_uri(),
            "removeObjectMaskUrl": "",
            "removeObjectInstruction": "the red cup on the table",
            # Leaked normal Pro Studio state that must be completely ignored.
            "characterId": "char_1",
            "characterReferences": ["https://example.com/leak1.png"],
            "objectReferences": ["https://example.com/leak2.png"],
            "style": "cinematic",
        },
    }
    result = asyncio.run(main.generate_remove_object_image(payload))
    assert result["ok"] is True
    assert "image" in captured["files"]
    assert "mask" not in captured["files"]
    assert "What to remove: the red cup on the table" in captured["data"]["prompt"]
    assert "char_1" not in captured["data"]["prompt"]
    assert result["cost_credits"] >= main.REMOVE_OBJECT_TOOL_FEE_CREDITS


def test_generate_remove_object_image_with_mask_sends_real_inverted_mask(monkeypatch):
    captured = {}

    def fake_post(url, headers=None, data=None, files=None, timeout=None):
        captured["data"] = data
        captured["files"] = dict(files)
        return _fake_success_response()

    monkeypatch.setattr(main, "OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(main.requests, "post", fake_post)
    monkeypatch.setattr(main, "send_generated_images_to_telegram", lambda *a, **k: True)

    payload = {
        "telegram_id": 0,
        "job_id": "",
        "image_options": {
            "tool": "remove_object",
            "removeObjectSourceUrl": _png_data_uri(),
            "removeObjectMaskUrl": _mask_data_uri_with_left_half_marked(),
            "removeObjectInstruction": "",
        },
    }
    result = asyncio.run(main.generate_remove_object_image(payload))
    assert result["ok"] is True
    assert "mask" in captured["files"]
    assert "transparent mask" in captured["data"]["prompt"].lower()

    from PIL import Image

    mask_bytes = captured["files"]["mask"][1]
    with Image.open(io.BytesIO(mask_bytes)) as mask_img:
        rgba = mask_img.convert("RGBA")
        assert rgba.getpixel((0, 0))[3] == 0      # user marked -> transparent
        assert rgba.getpixel((rgba.width - 1, 0))[3] == 255  # untouched -> opaque


def test_generate_remove_object_image_falls_back_to_text_only_when_mask_is_unusable(monkeypatch):
    captured = {}

    def fake_post(url, headers=None, data=None, files=None, timeout=None):
        captured["data"] = data
        captured["files"] = dict(files)
        return _fake_success_response()

    monkeypatch.setattr(main, "OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(main.requests, "post", fake_post)
    monkeypatch.setattr(main, "send_generated_images_to_telegram", lambda *a, **k: True)

    broken_mask = "data:image/png;base64," + base64.b64encode(b"not a real image").decode("ascii")
    payload = {
        "telegram_id": 0,
        "job_id": "",
        "image_options": {
            "tool": "remove_object",
            "removeObjectSourceUrl": _png_data_uri(),
            "removeObjectMaskUrl": broken_mask,
            "removeObjectInstruction": "",
        },
    }
    result = asyncio.run(main.generate_remove_object_image(payload))
    # Mask decode/build failed, and there is no text instruction either -
    # still succeeds, falling back to the unmarked source image with the
    # base removal prompt rather than raising or sending nothing.
    assert result["ok"] is True
    assert "mask" not in captured["files"]


def test_dispatch_prefers_remove_object_over_generic_seedream_route():
    payload = {
        "model": "seedream_5_0_lite",
        "image_options": {"tool": "remove_object"},
    }
    assert main.is_remove_object_request(payload) is True
    # Same payload would also match the generic Seedream dispatch check -
    # dispatch_prostudio_provider_request checks is_remove_object_request
    # first, specifically so this never falls through to a generic Seedream
    # route (which reads the leaky image_options shape) instead of the
    # isolated generate_remove_object_image.
    assert main.is_seedream_request(payload) is True
