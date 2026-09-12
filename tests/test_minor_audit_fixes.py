"""Three unrelated low-priority audit findings grouped together as "Fix 10":

1. gemini_3_1_flash's default provider model dropped the ".1" that its
   sibling gemini_3_1_pro and the frontend's declared providerModel both
   use ("gemini-3-flash-preview" vs "gemini-3.1-pro-preview" /
   "gemini-3.1-flash"), inconsistent with the actual model family.
2. Luma Dream Machine silently fell back to the same provider model as
   Luma Ray v3.2 (LUMA_VIDEO_MODEL / "ray-3.2") whenever
   LUMA_DREAM_MACHINE_MODEL wasn't set, even though they are two distinct
   frontend model entries.
3. Qwen Image (base variant) had a redundant double retry loop: an outer
   loop in image_generation() called call_qwen_image() up to `count`
   times, even though call_qwen_image() already loops internally until
   `count` images are collected - functionally harmless but wasteful.
"""
import json

import pytest

import services.video_router as video_router


def test_gemini_3_1_flash_default_matches_the_3_1_family(monkeypatch):
    monkeypatch.delenv("GEMINI_TEXT_FLASH_MODEL", raising=False)
    monkeypatch.delenv("GEMINI-TEXT-FLASH-MODEL", raising=False)
    import importlib
    import main
    reloaded = importlib.reload(main)
    try:
        provider_model = reloaded.TEXT_MODEL_VARIANTS["gemini_3_1_flash"]["provider_model"]
        assert provider_model == "gemini-3.1-flash-preview", provider_model
        assert "3.1" in provider_model
    finally:
        importlib.reload(main)


def test_luma_dream_machine_has_its_own_distinct_default_model(monkeypatch):
    monkeypatch.delenv("LUMA_DREAM_MACHINE_MODEL", raising=False)
    monkeypatch.delenv("LUMA_RAY_V3_2_MODEL", raising=False)
    monkeypatch.delenv("LUMA_VIDEO_MODEL", raising=False)
    import importlib
    reloaded = importlib.reload(video_router)
    try:
        ray_model = reloaded.VIDEO_PROVIDER_MODEL_MAP["luma_ray_v3_2"]["provider_model"]
        dream_model = reloaded.VIDEO_PROVIDER_MODEL_MAP["luma_dream_machine"]["provider_model"]
        assert ray_model != dream_model, "Luma Ray v3.2 and Dream Machine must not resolve to the same provider model"
        assert dream_model
    finally:
        importlib.reload(video_router)


class _FakeResponse:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self.text = json.dumps(payload)
        self.content = self.text.encode()


@pytest.mark.asyncio
async def test_qwen_base_model_makes_exactly_count_provider_calls(monkeypatch):
    import main
    monkeypatch.setenv("DASHSCOPE_API_KEY", "test-key")

    calls = []

    def fake_post(url, headers=None, data=None, timeout=None, **kwargs):
        calls.append(url)
        body = {"output": {"choices": [{"message": {"content": [{"image": f"https://example.com/qwen{len(calls)}.png"}]}}]}}
        return _FakeResponse(200, body)

    monkeypatch.setattr(main.requests, "post", fake_post)

    payload = {
        "telegram_id": 0,
        "prompt": "a lighthouse at dusk",
        "provider": "qwen",
        "model": "qwen_image",
        "image_options": {"modelId": "qwen_image", "count": 3, "size": "1024x1024"},
    }
    result = await main.image_generation(payload)

    assert result.get("ok") is True, result
    assert len(calls) == 3, f"qwen_image (n=1 per call) must make exactly `count` provider calls, not more: {len(calls)}"
    assert len(result.get("images") or []) == 3


@pytest.mark.asyncio
async def test_qwen_batching_model_makes_exactly_one_provider_call(monkeypatch):
    import main
    monkeypatch.setenv("DASHSCOPE_API_KEY", "test-key")

    calls = []

    def fake_post(url, headers=None, data=None, timeout=None, **kwargs):
        calls.append(json.loads(data))
        images = [{"image": f"https://example.com/batch{i}.png"} for i in range(4)]
        body = {"output": {"choices": [{"message": {"content": images}}]}}
        return _FakeResponse(200, body)

    monkeypatch.setattr(main.requests, "post", fake_post)

    payload = {
        "telegram_id": 0,
        "prompt": "four seasons in one frame",
        "provider": "qwen",
        "model": "qwen_image_2",
        "image_options": {"modelId": "qwen_image_2", "count": 4, "size": "1024x1024"},
    }
    result = await main.image_generation(payload)

    assert result.get("ok") is True, result
    assert len(calls) == 1, "qwen_image_2 batches natively via n - must not be called more than once"
    assert calls[0]["parameters"]["n"] == 4
    assert len(result.get("images") or []) == 4
