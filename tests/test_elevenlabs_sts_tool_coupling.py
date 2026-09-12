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


@pytest.mark.asyncio
async def test_selecting_an_sts_model_without_the_sts_tool_still_requires_audio(monkeypatch):
    """The frontend left elevenlabs_tool at its text_to_speech default even
    though an *_sts_v2 model was picked. The tool must be auto-forced to
    speech_to_speech, and since no audio was uploaded, the request must be
    rejected with a clear "requires uploaded audio" error - not silently
    sent as a broken text-to-speech call."""
    calls = []
    _patch_common(monkeypatch, calls)
    monkeypatch.setattr(audio_router, "_runway_input_media_url", lambda payload: "")

    payload = {
        "prompt": "hello there",
        "voice_options": {"model": "elevenlabs_multilingual_sts_v2"},
        "model": "elevenlabs_multilingual_sts_v2",
    }
    result = await audio_router.elevenlabs_voice_generation(payload)

    assert result.get("ok") is False
    assert not calls, "no HTTP request should go out without the required audio"
    assert "audio" in (result.get("raw_error") or result.get("error") or "").lower()


@pytest.mark.asyncio
async def test_selecting_an_sts_model_with_audio_hits_the_speech_to_speech_endpoint(monkeypatch):
    calls = []
    _patch_common(monkeypatch, calls)
    monkeypatch.setattr(audio_router, "_runway_input_media_url", lambda payload: "https://example.com/source.wav")

    async def fake_load_media(client, media_url):
        return b"fake-wav-bytes", "source.wav", "audio/wav"

    monkeypatch.setattr(audio_router, "_load_provider_media", fake_load_media)

    payload = {
        "voice_options": {"model": "elevenlabs_multilingual_sts_v2"},
        "model": "elevenlabs_multilingual_sts_v2",
    }
    result = await audio_router.elevenlabs_voice_generation(payload)

    assert result.get("ok") is True, result
    assert len(calls) == 1
    url, kwargs = calls[0]
    assert "/speech-to-speech/" in url
    assert kwargs["data"]["model_id"] == "eleven_multilingual_sts_v2"
    assert result.get("tool") == "speech_to_speech"


@pytest.mark.asyncio
async def test_speech_to_speech_tool_with_a_non_sts_model_is_coerced_to_an_sts_model(monkeypatch):
    """If the tool selector says speech_to_speech but the chosen model is a
    plain TTS model (e.g. left over from a previous selection), the
    provider_model must be swapped to a real STS model - ElevenLabs' STS
    endpoint rejects a non-STS model_id."""
    calls = []
    _patch_common(monkeypatch, calls)
    monkeypatch.setattr(audio_router, "_runway_input_media_url", lambda payload: "https://example.com/source.wav")

    async def fake_load_media(client, media_url):
        return b"fake-wav-bytes", "source.wav", "audio/wav"

    monkeypatch.setattr(audio_router, "_load_provider_media", fake_load_media)

    payload = {
        "voice_options": {"model": "elevenlabs_eleven_v3", "elevenlabs_tool": "speech_to_speech"},
        "model": "elevenlabs_eleven_v3",
    }
    result = await audio_router.elevenlabs_voice_generation(payload)

    assert result.get("ok") is True, result
    url, kwargs = calls[0]
    assert kwargs["data"]["model_id"] in audio_router.ELEVENLABS_STS_MODELS


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
