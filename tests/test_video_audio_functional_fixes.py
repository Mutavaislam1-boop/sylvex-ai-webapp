"""Regression tests for a batch of functional (non-pricing) bugs found in a
full Pro Studio diagnostic sweep, prioritized after the money-bug fixes:

1. Sora 2 / Sora 2 Pro ignored the user's chosen duration entirely, always
   sending "16" (a value the frontend never even offered and OpenAI's
   documented API rejects) - now quantizes to OpenAI's real 4/8/12 enum.
2. Veo 3.1, MiniMax Hailuo 2.3 and all 3 Seedance models forwarded a raw
   start_image/reference URL straight to the provider without resolving a
   relative/internal path into a fully-qualified one first, unlike every
   other provider in this file - a locally-stored reference photo would
   reach the provider as an unreachable path.
3. Grok Video/Edit never forwarded xAI's documented generate_audio flag, so
   the sound toggle had no effect on the actual request.
4. Gemini Omni Flash never forwarded a duration at all (Google's own docs
   confirm there is no way to disable audio for this model - sound:false is
   set on the model instead of trying to forward a nonexistent flag).
5. Lyria RealTime's vocal "auto" option was indistinguishable from
   "instrumental" - the code force-added "Instrumental only, no vocals." to
   the prompt for every request to this model regardless of the user's
   choice, and always used the QUALITY generation mode (no vocal-like
   textures at all).
"""
import services.video_router as video_router
import services.audio_router as audio_router


def test_sora_seconds_quantizes_to_openais_real_enum():
    assert video_router._openai_sora_seconds(5) == "4"
    assert video_router._openai_sora_seconds(4) == "4"
    # 10 is equidistant from 8 and 12; min() deterministically picks the
    # first (lower) candidate in the (4, 8, 12) tuple on a tie.
    assert video_router._openai_sora_seconds(10) == "8"
    assert video_router._openai_sora_seconds(11) == "12"
    assert video_router._openai_sora_seconds(8) == "8"
    assert video_router._openai_sora_seconds(None) == "4"
    assert video_router._openai_sora_seconds("garbage") == "4"


def test_veo_normalizes_relative_start_image_to_a_public_url(monkeypatch):
    monkeypatch.setattr(video_router, "_get_env", lambda *names: "test-key")
    monkeypatch.setattr(video_router, "_provider_model_for_video", lambda model_id: "veo-3.1")
    monkeypatch.setenv("WEBAPP_URL", "https://sylvex.example")
    captured = {}

    def fake_request_json(url, headers, body):
        captured["body"] = body
        class _Resp:
            status_code = 200
            text = '{"name": "operations/veo-task-1"}'
        return _Resp()

    monkeypatch.setattr(video_router, "_request_json", fake_request_json)
    payload = {"video_options": {"start_image": "/generated/photo.png", "duration": 5, "ratio": "16:9"}}
    video_router._call_veo("veo_3_1", "a sunset", payload)
    image = captured["body"]["instances"][0]["image"]["url"]
    assert image == "https://sylvex.example/generated/photo.png"


def test_minimax_normalizes_relative_first_frame_image(monkeypatch):
    monkeypatch.setattr(video_router, "_get_env", lambda *names: "test-key")
    monkeypatch.setattr(video_router, "_provider_model_for_video", lambda model_id: "minimax-hailuo-2-3")
    monkeypatch.setenv("WEBAPP_URL", "https://sylvex.example")
    captured = {}

    def fake_request_json(url, headers, body):
        captured["body"] = body
        class _Resp:
            status_code = 200
            text = '{"task_id": "minimax-task-1"}'
        return _Resp()

    monkeypatch.setattr(video_router, "_request_json", fake_request_json)
    payload = {"video_options": {"start_image": "/generated/photo.png", "duration": 5, "resolution": "720p"}}
    video_router._call_minimax("minimax_hailuo_2_3", "a river", payload)
    assert captured["body"]["first_frame_image"] == "https://sylvex.example/generated/photo.png"


def test_seedance_body_normalizes_relative_image_and_video_references(monkeypatch):
    monkeypatch.setenv("WEBAPP_URL", "https://sylvex.example")
    payload = {
        "video_options": {
            "start_image": "/generated/start.png",
            "reference_images": ["/generated/ref.png", "https://already.example/abs.png"],
            "input_video": "/generated/clip.mp4",
            "duration": 5,
            "resolution": "720p",
        }
    }
    body = video_router._seedance_body("seedance_2_fast", "a robot dancing", payload)
    assert body is not None
    image_urls = [item["image_url"]["url"] for item in body["content"] if item.get("type") == "image_url"]
    video_urls = [item["video_url"]["url"] for item in body["content"] if item.get("type") == "video_url"]
    assert "https://sylvex.example/generated/start.png" in image_urls
    assert "https://sylvex.example/generated/ref.png" in image_urls
    assert "https://already.example/abs.png" in image_urls
    assert "https://sylvex.example/generated/clip.mp4" in video_urls
    assert not any(url.startswith("/generated/") for url in image_urls + video_urls)


def test_grok_forwards_generate_audio_flag(monkeypatch):
    monkeypatch.setattr(video_router, "_get_env", lambda *names: "test-key")
    monkeypatch.setattr(video_router, "_provider_model_for_video", lambda model_id: "grok-video-1")
    monkeypatch.setattr(video_router, "_public_input_url", lambda url: url)
    captured = {}

    def fake_request_json(url, headers, body):
        captured["body"] = body
        class _Resp:
            status_code = 200
            text = '{"id": "grok-task-1", "status": "queued"}'
        return _Resp()

    monkeypatch.setattr(video_router, "_request_json", fake_request_json)

    video_router._call_grok("grok_video", "a rocket", {"video_options": {"sound": True, "duration": 5}})
    assert captured["body"]["generate_audio"] is True

    video_router._call_grok("grok_video", "a rocket", {"video_options": {"sound": False, "duration": 5}})
    assert captured["body"]["generate_audio"] is False


def test_gemini_omni_flash_forwards_duration_and_has_no_sound_toggle():
    assert video_router.VIDEO_MODEL_CONFIG["gemini_omni_flash"]["sound"] is False
    # The Runway-wrapped variant is a different product/API path and keeps its own sound flag.
    assert video_router.VIDEO_MODEL_CONFIG["runway_gemini_omni_flash"]["sound"] is True


def test_gemini_video_request_includes_duration_seconds(monkeypatch):
    monkeypatch.setattr(video_router, "_get_env", lambda *names: "test-key")
    monkeypatch.setattr(video_router, "_provider_model_for_video", lambda model_id: "gemini-omni-flash-preview")
    captured = {}

    def fake_request_json(url, headers, body):
        captured["body"] = body
        class _Resp:
            status_code = 200
            text = '{"id": "gemini-task-1", "status": "processing"}'
        return _Resp()

    monkeypatch.setattr(video_router, "_request_json", fake_request_json)
    monkeypatch.setattr(video_router, "_safe_provider_json_response", lambda response, provider, endpoint: {"id": "gemini-task-1", "status": "processing"})
    monkeypatch.setattr(video_router, "_log_provider_response", lambda *a, **k: None)

    video_router._call_gemini_video("gemini_omni_flash", "a forest", {"video_options": {"duration": 8, "ratio": "16:9"}})
    video_config = captured["body"]["generation_config"]["video_config"]
    assert video_config["duration_seconds"] == 8


def test_heygen_models_have_no_functional_sound_toggle():
    for model_id in (
        "heygen_v3_video_agent", "heygen_avatar_iv", "heygen_avatar_v",
        "heygen_avatar_iii", "heygen_image_video", "heygen_cinematic_avatar",
    ):
        assert video_router.VIDEO_MODEL_CONFIG[model_id]["sound"] is False, model_id


def test_lyria_realtime_auto_vocal_does_not_force_instrumental_prompt_text():
    prompt_auto = audio_router._lyria_prompt(
        {"prompt": "a calm piano piece", "music_options": {"vocal": "auto"}},
        "models/lyria-realtime-exp",
    )
    assert "Instrumental only" not in prompt_auto

    prompt_instrumental = audio_router._lyria_prompt(
        {"prompt": "a calm piano piece", "music_options": {"vocal": "instrumental"}},
        "models/lyria-realtime-exp",
    )
    assert "Instrumental only" in prompt_instrumental


def test_lyria_realtime_auto_vocal_uses_vocalization_generation_mode(monkeypatch):
    import asyncio
    import sys
    import types as py_types

    monkeypatch.setattr(audio_router, "_get_env", lambda *names: "test-gemini-key")
    monkeypatch.setattr(audio_router, "_lyria_prompt", lambda payload, model: "a calm piano melody")
    captured = {}

    class _Chunk:
        def __init__(self, data):
            self.data = data

    class _ServerContent:
        def __init__(self, data):
            self.audio_chunks = [_Chunk(data)]

    class _Message:
        def __init__(self, data):
            self.server_content = _ServerContent(data)

    class _FakeSession:
        async def set_weighted_prompts(self, prompts):
            pass

        async def set_music_generation_config(self, config):
            captured["config"] = config

        async def play(self):
            pass

        async def receive(self):
            # One message carrying enough bytes to satisfy the 1-second
            # target immediately, so collect_stream() returns without
            # looping - a real hang-detection scenario is covered by the
            # separate test_lyria_realtime_times_out_cleanly_without_hanging.
            yield _Message(b"\x00" * (1 * 48000 * 2 * 2))

        async def stop(self):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc_info):
            return False

    class _FakeMusicNamespace:
        def connect(self, model):
            return _FakeSession()

    class _FakeClient:
        def __init__(self, api_key, http_options):
            self.aio = type("_Aio", (), {"live": type("_Live", (), {"music": _FakeMusicNamespace()})()})()

    fake_genai = type("_FakeGenaiModule", (), {"Client": _FakeClient})()
    fake_types_module = py_types.SimpleNamespace(
        MusicGenerationMode=type("_Mode", (), {"QUALITY": "QUALITY", "VOCALIZATION": "VOCALIZATION"}),
        WeightedPrompt=lambda text, weight: {"text": text, "weight": weight},
        LiveMusicGenerationConfig=lambda **kw: kw,
    )
    monkeypatch.setitem(sys.modules, "google", type("_Google", (), {"genai": fake_genai})())
    monkeypatch.setitem(sys.modules, "google.genai", fake_genai)
    monkeypatch.setitem(sys.modules, "google.genai.types", fake_types_module)
    fake_genai.types = fake_types_module

    payload = {"music_options": {"duration_seconds": 1, "vocal": "auto"}}
    asyncio.run(audio_router.lyria_music_generation(payload, "google_lyria_realtime", "models/lyria-realtime-exp"))
    assert captured["config"]["music_generation_mode"] == "VOCALIZATION"

    captured.clear()
    payload_instrumental = {"music_options": {"duration_seconds": 1, "vocal": "instrumental"}}
    asyncio.run(audio_router.lyria_music_generation(payload_instrumental, "google_lyria_realtime", "models/lyria-realtime-exp"))
    assert captured["config"]["music_generation_mode"] == "QUALITY"
