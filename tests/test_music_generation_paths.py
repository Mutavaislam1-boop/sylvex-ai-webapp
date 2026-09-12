"""Music generation: the Lyria RealTime WebSocket path must be genuinely
non-blocking, bounded (no zombie session that hangs forever), and reach a
clean terminal failure - without leaking the Gemini API key embedded in
the SDK's WebSocket URL - when the provider never delivers enough audio."""
import asyncio

import pytest

import services.audio_router as audio_router


@pytest.mark.asyncio
async def test_lyria_realtime_times_out_cleanly_without_hanging(monkeypatch):
    monkeypatch.setattr(audio_router, "_get_env", lambda *names: "test-gemini-key")
    monkeypatch.setattr(audio_router, "_lyria_prompt", lambda payload, model: "a calm piano melody")

    class _HangingSession:
        async def set_weighted_prompts(self, prompts):
            pass

        async def set_music_generation_config(self, config):
            pass

        async def play(self):
            pass

        async def receive(self):
            # A server that never sends audio and never closes the stream -
            # exactly the "zombie" scenario the timeout must guard against.
            await asyncio.sleep(3600)
            yield None

        async def stop(self):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc_info):
            return False

    class _HangingMusicNamespace:
        def connect(self, model):
            return _HangingSession()

    class _HangingClient:
        def __init__(self, api_key, http_options):
            assert "test-gemini-key" in api_key or api_key == "test-gemini-key"
            self.aio = type("_Aio", (), {"live": type("_Live", (), {"music": _HangingMusicNamespace()})()})()

    fake_genai = type("_FakeGenaiModule", (), {"Client": _HangingClient})()
    fake_types_module = type("_FakeTypesModule", (), {
        "MusicGenerationMode": type("_Mode", (), {"QUALITY": "QUALITY"}),
        "WeightedPrompt": lambda text, weight: {"text": text, "weight": weight},
        "LiveMusicGenerationConfig": lambda **kw: kw,
    })()

    import sys
    monkeypatch.setitem(sys.modules, "google", type("_Google", (), {"genai": fake_genai})())
    monkeypatch.setitem(sys.modules, "google.genai", fake_genai)
    monkeypatch.setitem(sys.modules, "google.genai.types", fake_types_module)
    fake_genai.types = fake_types_module

    payload = {"music_options": {"duration_seconds": 1}}  # timeout = 1 + 90 = 91s in real code

    async def instant_wait_for(coro, timeout):
        # Prove the call site truly bounds the hang with asyncio.wait_for by
        # exercising the real timeout path on a much shorter clock, rather
        # than actually waiting 91 seconds in a unit test.
        coro.close()
        raise asyncio.TimeoutError()

    monkeypatch.setattr(audio_router.asyncio, "wait_for", instant_wait_for)

    result = await audio_router.lyria_music_generation(payload, "lyria_realtime", "models/lyria-realtime-exp")

    assert result.get("ok") is False, "a hung/timed-out session must reach a terminal failure, not hang forever"
    assert "details" not in result, "must not attach repr(exc) - the Lyria SDK embeds the API key in its connection URL"
    assert "test-gemini-key" not in str(result), "the API key must never appear anywhere in the returned result"
