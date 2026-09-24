"""Remove Object is the first Quick Tool migrated to an isolated generation
flow: its request must be built from exactly three tool-owned inputs
(image_options.removeObjectSourceUrl/removeObjectMaskUrl/
removeObjectInstruction) and never from normal Pro Studio composer state
(Character/Object/Style/previous prompt/previous references) - the bug the
old shared Photo Tool path had, since it built every tool's request from
imageOptionsPayload(), which spreads the whole global imageState. These
tests cover is_remove_object_request, the +5 credit Quick Tool fee (on top
of the real model cost, applied once at the single price choke point so it
can never be charged/refunded independently of the model cost), prompt
construction, and the isolated provider-call function itself - including
that noise from a normal Pro Studio payload never leaks into the request."""
import main


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
    assert "marked" in prompt.lower()
    assert "What to remove:" not in prompt


def test_build_remove_object_prompt_with_text_only():
    prompt = main.build_remove_object_prompt(False, "the red cup on the table")
    assert "What to remove: the red cup on the table" in prompt
    assert "green overlay" not in prompt.lower()


def test_build_remove_object_prompt_with_both():
    prompt = main.build_remove_object_prompt(True, "the red cup")
    assert "marked" in prompt.lower()
    assert "What to remove: the red cup" in prompt


async def _run_generate_remove_object_image(payload):
    return await main.generate_remove_object_image(payload)


def test_generate_remove_object_image_requires_source_image(monkeypatch):
    import asyncio
    monkeypatch.setattr(main, "BYTEPLUS_ARK_API_KEY", "test-key")
    result = asyncio.run(_run_generate_remove_object_image({
        "image_options": {"tool": "remove_object", "removeObjectInstruction": "remove the cup"},
    }))
    assert result["ok"] is False


def test_generate_remove_object_image_rejects_image_only(monkeypatch):
    import asyncio

    def _explode(*a, **k):
        raise AssertionError("must never call the provider without a mask or instruction")

    monkeypatch.setattr(main, "BYTEPLUS_ARK_API_KEY", "test-key")
    monkeypatch.setattr(main, "request_byteplus_seedream_image", _explode)
    result = asyncio.run(_run_generate_remove_object_image({
        "image_options": {
            "tool": "remove_object",
            "removeObjectSourceUrl": "https://example.com/source.png",
            "removeObjectMaskUrl": "",
            "removeObjectInstruction": "",
        },
    }))
    assert result["ok"] is False


def test_generate_remove_object_image_text_only_success_never_composes_mask(monkeypatch):
    import asyncio
    captured = {}

    def fake_request(model, prompt, reference_images, size="", seed=None, quality="high"):
        captured["model"] = model
        captured["prompt"] = prompt
        captured["reference_images"] = list(reference_images)
        return (["https://cdn.example.com/result.png"], "")

    def _explode_compose(*a, **k):
        raise AssertionError("must not composite a mask when none was drawn")

    monkeypatch.setattr(main, "BYTEPLUS_ARK_API_KEY", "test-key")
    monkeypatch.setattr(main, "request_byteplus_seedream_image", fake_request)
    monkeypatch.setattr(main, "compose_remove_object_marked_image", _explode_compose)
    monkeypatch.setattr(main, "send_generated_images_to_telegram", lambda *a, **k: True)

    payload = {
        "telegram_id": 0,
        "job_id": "job_1",
        "image_options": {
            "tool": "remove_object",
            "removeObjectSourceUrl": "https://example.com/source.png",
            "removeObjectMaskUrl": "",
            "removeObjectInstruction": "the red cup on the table",
            # Leaked normal Pro Studio state that must be completely ignored.
            "characterId": "char_1",
            "characterReferences": ["https://example.com/leak1.png"],
            "objectReferences": ["https://example.com/leak2.png"],
            "style": "cinematic",
        },
    }
    result = asyncio.run(_run_generate_remove_object_image(payload))
    assert result["ok"] is True
    assert captured["reference_images"] == ["https://example.com/source.png"]
    assert "What to remove: the red cup on the table" in captured["prompt"]
    assert "char_1" not in captured["prompt"]
    assert "leak1" not in " ".join(captured["reference_images"])
    assert "leak2" not in " ".join(captured["reference_images"])
    assert result["cost_credits"] >= main.REMOVE_OBJECT_TOOL_FEE_CREDITS


def test_generate_remove_object_image_with_mask_composites_and_uses_marked_image(monkeypatch):
    import asyncio
    captured = {}

    def fake_compose(source_url, mask_url):
        captured["compose_args"] = (source_url, mask_url)
        return "https://cdn.example.com/marked.jpg"

    def fake_request(model, prompt, reference_images, size="", seed=None, quality="high"):
        captured["reference_images"] = list(reference_images)
        captured["prompt"] = prompt
        return (["https://cdn.example.com/result.png"], "")

    monkeypatch.setattr(main, "BYTEPLUS_ARK_API_KEY", "test-key")
    monkeypatch.setattr(main, "compose_remove_object_marked_image", fake_compose)
    monkeypatch.setattr(main, "request_byteplus_seedream_image", fake_request)
    monkeypatch.setattr(main, "send_generated_images_to_telegram", lambda *a, **k: True)

    payload = {
        "telegram_id": 0,
        "job_id": "job_2",
        "image_options": {
            "tool": "remove_object",
            "removeObjectSourceUrl": "https://example.com/source.png",
            "removeObjectMaskUrl": "https://example.com/mask.png",
            "removeObjectInstruction": "",
        },
    }
    result = asyncio.run(_run_generate_remove_object_image(payload))
    assert result["ok"] is True
    assert captured["compose_args"] == ("https://example.com/source.png", "https://example.com/mask.png")
    assert captured["reference_images"] == ["https://cdn.example.com/marked.jpg"]
    assert "marked" in captured["prompt"].lower()


def test_generate_remove_object_image_falls_back_when_compose_fails(monkeypatch):
    import asyncio
    captured = {}

    def failing_compose(source_url, mask_url):
        return ""

    def fake_request(model, prompt, reference_images, size="", seed=None, quality="high"):
        captured["reference_images"] = list(reference_images)
        captured["prompt"] = prompt
        return (["https://cdn.example.com/result.png"], "")

    monkeypatch.setattr(main, "BYTEPLUS_ARK_API_KEY", "test-key")
    monkeypatch.setattr(main, "compose_remove_object_marked_image", failing_compose)
    monkeypatch.setattr(main, "request_byteplus_seedream_image", fake_request)
    monkeypatch.setattr(main, "send_generated_images_to_telegram", lambda *a, **k: True)

    payload = {
        "telegram_id": 0,
        "job_id": "job_3",
        "image_options": {
            "tool": "remove_object",
            "removeObjectSourceUrl": "https://example.com/source.png",
            "removeObjectMaskUrl": "https://example.com/mask.png",
            "removeObjectInstruction": "",
        },
    }
    result = asyncio.run(_run_generate_remove_object_image(payload))
    # Compose failed and there is no text instruction either - falls back
    # to the unmarked source image rather than raising or sending nothing.
    assert result["ok"] is True
    assert captured["reference_images"] == ["https://example.com/source.png"]


def test_dispatch_prefers_remove_object_over_generic_seedream_route():
    payload = {
        "model": "seedream_5_0_lite",
        "image_options": {"tool": "remove_object"},
    }
    assert main.is_remove_object_request(payload) is True
    # Same payload would also match the generic Seedream dispatch check -
    # dispatch_prostudio_provider_request checks is_remove_object_request
    # first, specifically so this never falls through to
    # generateBytePlusSeedreamImage (which reads the leaky image_options
    # shape) instead of the isolated generate_remove_object_image.
    assert main.is_seedream_request(payload) is True
