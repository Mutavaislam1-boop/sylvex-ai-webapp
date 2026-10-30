"""A published Media block generates with the model its admin chose, through
the shared generation pipeline - never on GPT Image or another model in its
place - and a block whose model cannot generate says so instead.

No provider is called: the provider adapters are replaced by recorders."""
import asyncio

import pytest

from services import media_blocks as mb


def photo_block(model, generation="image", **kw):
    block = {"id": 7, "block_type": "photo", "name": "Neon", "prompt": "neon portrait", "model": model,
             "preview_url": "https://cdn.example/cover.png", "source_url": "https://cdn.example/ref.png",
             "config": {"generation": generation, "ref_mode": "C", "aspect": "3:4", "placements": ["photo_references"],
                        "fields": [{"key": "me", "label": "Your photo", "accept": "image", "required": True, "purpose": "", "input": ""}]}}
    block.update(kw)
    return block


@pytest.fixture
def routes(monkeypatch):
    import main
    calls = []

    def recorder(name):
        async def fake(payload):
            calls.append((name, payload.get("model"), (payload.get("image_options") or {}).get("modelId")))
            return {"ok": True, "type": "image", "image_url": "https://cdn.example/out.png"}
        return fake

    monkeypatch.setattr(main, "generateBytePlusSeedreamImage", recorder("seedream"))
    monkeypatch.setattr(main, "image_generation", recorder("image_generation"))
    monkeypatch.setattr(main, "run_provider_coroutine_off_loop", lambda factory: factory())
    return main, calls


def dispatch(main, payload):
    from services.billing_safety import billing_scope
    payload = dict(payload, job_id="job-1")
    with billing_scope("job-1", 30):
        return asyncio.run(main.dispatch_prostudio_provider_request(
            "job-1", payload, payload["mode"], payload["model"], (payload.get("provider") or "sylvex-router"), {"text"}))


def test_a_seedream_block_goes_to_seedream(routes):
    main, calls = routes
    payload = mb.generation_payload(photo_block("seedream_4_5"), {"me": "https://images.example/me.png"})
    assert payload["model"] == "seedream_4_5" and payload["image_options"]["modelId"] == "seedream_4_5"
    dispatch(main, payload)
    assert calls == [("seedream", "seedream_4_5", "seedream_4_5")]


def test_another_image_model_keeps_its_own_id(routes):
    main, calls = routes
    payload = mb.generation_payload(photo_block("nano_banana_pro"), {"me": "https://images.example/me.png"})
    dispatch(main, payload)
    # The shared image route reads the model from the request; GPT Image is never put in its place.
    assert calls == [("image_generation", "nano_banana_pro", "nano_banana_pro")]


def test_the_seedream_adapter_resolves_the_chosen_version(monkeypatch):
    import main
    monkeypatch.setattr(main, "BYTEPLUS_ARK_API_KEY", "test-key")
    model = main.find_image_model("seedream_4_5").get("api_model") or main.map_image_model_to_provider_model("seedream_4_5")
    assert model == main.BYTEPLUS_SEEDREAM_MODEL_MAP["seedream_4_5"] and "4-5" in model


def test_block_model_state(monkeypatch):
    import main
    monkeypatch.setitem(main.MODEL_STATES_CACHE, "value", {})
    monkeypatch.setitem(main.MODEL_STATES_CACHE, "expires_at", 1e18)
    for name in ("BYTEPLUS_ARK_API_KEY", "BYTEDANCE_API_KEY", "BYTEPLUS_API_KEY", "ARK_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    assert main._media_model_state("seedream_4_5") == "no_keys"
    monkeypatch.setenv("BYTEPLUS_ARK_API_KEY", "x")
    assert main._media_model_state("seedream_4_5") == "available"
    monkeypatch.setitem(main.MODEL_STATES_CACHE, "value", {"seedream_4_5": {"reason": "outage"}})
    assert main._media_model_state("seedream_4_5") == "turned_off"
    assert main._media_model_state("no_such_model") == "unknown"


def test_editor_models_show_registry_models_as_available(monkeypatch):
    """The constructor lists the models SYLVEX generates with; one is shown
    unavailable only when it is turned off or its provider has no keys."""
    import main
    monkeypatch.setitem(main.MODEL_STATES_CACHE, "value", {})
    monkeypatch.setitem(main.MODEL_STATES_CACHE, "expires_at", 1e18)
    monkeypatch.setenv("BYTEPLUS_ARK_API_KEY", "x")
    monkeypatch.setenv("GEMINI_API_KEY", "x")
    models = {m["id"]: m for m in main._media_models()}
    assert models["seedream_4_5"]["status"] == "available" and models["seedream_4_5"]["provider"] == "bytedance"
    assert models["nano_banana_pro"]["status"] == "available"
    assert all(m["status"] in ("available", "turned_off", "no_keys") for m in models.values())
