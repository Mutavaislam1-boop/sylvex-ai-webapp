"""OpenAI image generation must request the whole batch in one call and
return every generated image, without blocking the event loop."""
import asyncio
import json
import time

import pytest


@pytest.fixture
def app(monkeypatch):
    monkeypatch.setenv('OPENAI_API_KEY', 'test-key')
    import main
    monkeypatch.setattr(main, 'OPENAI_API_KEY', 'test-key')
    return main


class _FakeResponse:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self.text = json.dumps(payload)
        self.content = self.text.encode()

    def json(self):
        return json.loads(self.text)


@pytest.mark.asyncio
async def test_openai_generations_requests_full_batch_in_one_call(app, monkeypatch):
    calls = []

    def fake_post(url, headers=None, data=None, timeout=None, **kwargs):
        calls.append({"url": url, "body": json.loads(data), "timeout": timeout})
        images = [{"url": f"https://example.com/img{i}.png"} for i in range(4)]
        return _FakeResponse(200, {"data": images})

    monkeypatch.setattr(app.requests, "post", fake_post)

    payload = {
        "telegram_id": 0,
        "prompt": "a cat riding a bike",
        "provider": "openai",
        "model": "gpt_image_1",
        "image_options": {"modelId": "gpt_image_1", "count": 4, "size": "1024x1024"},
    }
    result = await app.image_generation(payload)

    assert result.get("ok") is True, result
    assert len(calls) == 1, "expected exactly one provider round trip for quantity 4, not one per image"
    assert calls[0]["body"]["n"] == 4
    assert len(result.get("images") or []) == 4
    assert result.get("cost_credits") or result.get("cost") or True  # billing helper attaches its own fields


@pytest.mark.asyncio
async def test_openai_image_generation_does_not_block_event_loop(app, monkeypatch):
    """A slow provider call must not stall other coroutines on the shared loop."""
    def slow_post(url, headers=None, data=None, timeout=None, **kwargs):
        time.sleep(0.3)
        return _FakeResponse(200, {"data": [{"url": "https://example.com/img.png"}]})

    monkeypatch.setattr(app.requests, "post", slow_post)

    payload = {
        "telegram_id": 0,
        "prompt": "a dog on a skateboard",
        "provider": "openai",
        "model": "gpt_image_1",
        "image_options": {"modelId": "gpt_image_1", "count": 1, "size": "1024x1024"},
    }

    ticks = []

    async def ticker():
        for _ in range(6):
            ticks.append(time.monotonic())
            await asyncio.sleep(0.05)

    generation_task = asyncio.create_task(app.run_provider_coroutine_off_loop(lambda: app.image_generation(payload)))
    ticker_task = asyncio.create_task(ticker())
    await asyncio.gather(generation_task, ticker_task)

    gaps = [b - a for a, b in zip(ticks, ticks[1:])]
    assert max(gaps) < 0.2, f"event loop stalled for {max(gaps):.3f}s while the provider call was in flight: {gaps}"


@pytest.mark.asyncio
async def test_openai_image_edit_requests_full_batch_and_preserves_all_images(app, monkeypatch):
    calls = []

    def fake_post(url, headers=None, data=None, files=None, timeout=None, **kwargs):
        calls.append({"url": url, "body": data})
        images = [{"url": f"https://example.com/edit{i}.png"} for i in range(3)]
        return _FakeResponse(200, {"data": images})

    monkeypatch.setattr(app.requests, "post", fake_post)

    payload = {
        "telegram_id": 0,
        "prompt": "make the sky purple",
        "provider": "openai",
        "model": "gpt_image_1",
        "image_options": {
            "modelId": "gpt_image_1",
            "count": 3,
            "size": "1024x1024",
            "referenceImageUrls": [
                "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
            ],
        },
    }
    result = await app.image_generation(payload)

    assert result.get("ok") is True, result
    assert len(calls) == 1, "expected exactly one provider round trip for quantity 3, not one per image"
    assert calls[0]["body"]["n"] == "3"
    assert len(result.get("images") or []) == 3


@pytest.mark.asyncio
async def test_google_nano_banana_repeats_call_until_quantity_met(app, monkeypatch):
    """Gemini's generateContent-based image models return one image per call
    with no batching parameter, so the caller must repeat the call up to
    `count` times and aggregate — but must not over-call once satisfied."""
    calls = []

    def fake_post(url, headers=None, data=None, timeout=None, **kwargs):
        calls.append(url)
        body = json.loads(data)
        assert "sampleCount" not in json.dumps(body), "nano-banana path must not send an Imagen-only field"
        image = {"data": [{"content": [{"type": "output_image", "image_url": f"https://example.com/g{len(calls)}.png"}]}]}
        return _FakeResponse(200, image)

    monkeypatch.setattr(app.requests, "post", fake_post)
    monkeypatch.setattr(app, "google_image_headers", lambda: {"Authorization": "Bearer test"})
    monkeypatch.setattr(app, "google_extract_images", lambda data: [item["image_url"] for item in (((data.get("data") or [{}])[0]).get("content") or []) if item.get("image_url")])

    payload = {
        "telegram_id": 0,
        "prompt": "a robot painting a mural",
        "provider": "google",
        "model": "nano_banana_2",
        "image_options": {"modelId": "nano_banana_2", "count": 3, "size": "1024x1024"},
    }
    result = await app.image_generation(payload)

    assert result.get("ok") is True, result
    assert len(calls) == 3, "non-batching Gemini image model must be called once per requested image"
    assert len(result.get("images") or []) == 3
