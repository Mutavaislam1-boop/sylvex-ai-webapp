"""ElevenLabs *_sts_v2 models only work through the /v1/speech-to-speech
endpoint and reject text-only requests. The Mini App's model picker and the
separate "elevenlabs_tool" selector are independent controls, so a user
could pick an STS voice model while the tool still defaulted to
"text_to_speech" - the request then went out to /v1/text-to-speech with no
audio ever collected, and ElevenLabs would reject the STS model_id there.
elevenlabs_voice_generation must reconcile the model/tool pair itself
instead of trusting the frontend to keep them in sync."""
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
        self._calls.append((url, kwargs))
        return self._response_factory(url)


def _audio_response(url):
    request = httpx.Request("POST", url)
    return httpx.Response(200, content=b"fake-audio-bytes", headers={"content-type": "audio/mpeg"}, request=request)


def _patch_common(monkeypatch, calls):
    monkeypatch.setattr(audio_router, "httpx", type("_M", (), {"AsyncClient": lambda self=None, **kw: _FakeAsyncClient(calls, _audio_response)})())
    monkeypatch.setattr(audio_router, "_get_env", lambda *names: "test-key")
    monkeypatch.setattr(audio_router, "_elevenlabs_headers", lambda: {"xi-api-key": "test-key"})
    monkeypatch.setattr(audio_router, "_elevenlabs_voice_settings", lambda opts: {})
    monkeypatch.setattr(audio_router, "optimize_prompt_for_model", lambda prompt, **k: {"ok": True, "optimized": False, "original_length": len(prompt)})

    async def fake_completed(payload, frontend_model, provider_model, tool, content, content_type, meta):
        return {"ok": True, "type": "voice", "provider": "elevenlabs", "provider_model": provider_model, "tool": tool}

    monkeypatch.setattr(audio_router, "_completed_elevenlabs_voice_response", fake_completed)


# Speech-to-speech has no confirmed SYLVEX cost basis yet, so the reconciled
# STS request is refused before any HTTP call (and is not priced either).

@pytest.mark.parametrize("payload", [
    # STS model while the tool selector still says text_to_speech.
    {"prompt": "hello there", "voice_options": {"model": "elevenlabs_multilingual_sts_v2"}, "model": "elevenlabs_multilingual_sts_v2"},
    # STS tool with a plain TTS model.
    {"voice_options": {"model": "elevenlabs_eleven_v3", "elevenlabs_tool": "speech_to_speech"}, "model": "elevenlabs_eleven_v3"},
])
def test_sts_model_or_tool_resolves_to_speech_to_speech(payload):
    assert audio_router.elevenlabs_dispatch_tool(payload) == "speech_to_speech"


@pytest.mark.asyncio
@pytest.mark.parametrize("payload", [
    {"prompt": "hello there", "voice_options": {"model": "elevenlabs_multilingual_sts_v2"}, "model": "elevenlabs_multilingual_sts_v2"},
    {"voice_options": {"model": "elevenlabs_eleven_v3", "elevenlabs_tool": "speech_to_speech"}, "model": "elevenlabs_eleven_v3"},
    {"prompt": "hi", "voice_options": {"model": "elevenlabs_eleven_v3", "elevenlabs_tool": "dubbing"}, "model": "elevenlabs_eleven_v3"},
    {"prompt": "hi", "voice_options": {"model": "elevenlabs_eleven_v3", "elevenlabs_tool": "dialogue"}, "model": "elevenlabs_eleven_v3"},
    {"prompt": "hi", "voice_options": {"model": "elevenlabs_eleven_v3", "elevenlabs_tool": "voice_design"}, "model": "elevenlabs_eleven_v3"},
])
async def test_unpriced_elevenlabs_tools_never_reach_the_provider(monkeypatch, payload):
    calls = []
    _patch_common(monkeypatch, calls)
    monkeypatch.setattr(audio_router, "_runway_input_media_url", lambda payload: "https://example.com/source.wav")

    async def fake_load_media(client, media_url):
        return b"fake-wav-bytes", "source.wav", "audio/wav"

    monkeypatch.setattr(audio_router, "_load_provider_media", fake_load_media)
    result = await audio_router.elevenlabs_voice_generation(payload)

    assert result.get("ok") is False
    assert not calls, "no HTTP request may go out for an unpriced ElevenLabs tool"
    assert "pricing_not_configured" in str(result)


@pytest.mark.asyncio
async def test_plain_text_to_speech_model_and_tool_are_unaffected(monkeypatch):
    calls = []
    _patch_common(monkeypatch, calls)

    payload = {"prompt": "hello there", "voice_options": {}, "model": "elevenlabs_eleven_v3"}
    result = await audio_router.elevenlabs_voice_generation(payload)

    assert result.get("ok") is True, result
    url, kwargs = calls[0]
    assert "/text-to-speech/" in url
    assert kwargs["json"]["model_id"] == "eleven_v3"
    assert result.get("tool") == "text_to_speech"
