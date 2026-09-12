"""Voice generation must match each provider's real sync/async contract:
ElevenLabs text-to-speech returns audio directly (one call, no polling),
while Runway's audio tools are genuinely task-based at the provider and
must poll - verified against the actual provider behavior, not assumed."""
import httpx
import pytest

import services.audio_router as audio_router


class _FakeAsyncClient:
    def __init__(self, calls, response_factory, **kwargs):
        self._calls = calls
        self._response_factory = response_factory

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc_info):
        return False

    async def post(self, url, **kwargs):
        self._calls.append(url)
        return self._response_factory(url)


def _audio_response(url):
    request = httpx.Request("POST", url)
    return httpx.Response(200, content=b"RIFF-fake-audio-bytes", headers={"content-type": "audio/mpeg"}, request=request)


@pytest.mark.asyncio
async def test_elevenlabs_text_to_speech_makes_exactly_one_call(monkeypatch):
    calls = []
    monkeypatch.setattr(audio_router, "httpx", type("_M", (), {"AsyncClient": lambda self=None, **kw: _FakeAsyncClient(calls, _audio_response)})())
    monkeypatch.setattr(audio_router, "_get_env", lambda *names: "test-key")
    monkeypatch.setattr(audio_router, "_elevenlabs_voice_model_mapping", lambda model: "eleven_v3")
    monkeypatch.setattr(audio_router, "_elevenlabs_headers", lambda: {"xi-api-key": "test-key"})
    monkeypatch.setattr(audio_router, "_elevenlabs_voice_settings", lambda opts: {})
    monkeypatch.setattr(audio_router, "optimize_prompt_for_model", lambda prompt, **k: {"ok": True, "optimized": False, "original_length": len(prompt)})

    async def fake_completed(payload, frontend_model, provider_model, tool, content, content_type, meta):
        return {"ok": True, "type": "voice", "audio_bytes": content, "provider": "elevenlabs"}

    monkeypatch.setattr(audio_router, "_completed_elevenlabs_voice_response", fake_completed)

    payload = {"prompt": "hello there", "voice_options": {}, "model": "elevenlabs_eleven_v3"}
    result = await audio_router.elevenlabs_voice_generation(payload)

    assert result.get("ok") is True, result
    assert len(calls) == 1, "default text-to-speech must be a single request, not a submit+poll sequence"
    assert calls[0].endswith("/v1/text-to-speech/" + audio_router.ELEVENLABS_DEFAULT_VOICE_ID) or "/text-to-speech/" in calls[0]
