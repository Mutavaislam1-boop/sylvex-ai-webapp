"""ElevenLabs Music: duration-based pricing, audio-reference guard and the
provider request (prompt / upload + conditioned composition plan)."""
import asyncio
import json
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).parent.parent))

import main
import services.audio_router as audio_router
from services.billing_safety import billing_scope


def _run(coro):
    return asyncio.run(coro)


def test_price_follows_duration_and_reference():
    cost = main.elevenlabs_music_cost_info
    # $0.15/min x 1.5 -> credits, rounded up (matches the published 23/45 per 1/2 min).
    assert cost({"model": "elevenlabs_music", "duration_seconds": 60})["credits"] == 23
    assert cost({"model": "elevenlabs_music", "duration_seconds": 120})["credits"] == 45
    assert cost({"model": "elevenlabs_music", "duration_seconds": 30})["credits"] == 12
    assert cost({"model": "elevenlabs_music", "duration": "auto"})["credits"] == 23
    with_ref = cost({"model": "elevenlabs_music", "duration_seconds": 60, "reference_audio": {"url": "/x.mp3", "duration_ms": 20000}})
    assert with_ref["credits"] == 30
    payload = {"mode": "music", "model": "elevenlabs_music", "music_options": {"model": "elevenlabs_music", "duration_seconds": 180}}
    assert main.estimate_generation_cost(payload)["credits"] == 68
    # Fixed-price models are unchanged.
    assert main.estimate_generation_cost({"mode": "music", "music_options": {"model": "suno_chirp_5_5"}})["credits"] == 18


def test_reference_is_rejected_where_unsupported_never_ignored():
    ok = {"mode": "music", "music_options": {"model": "elevenlabs_music", "reference_audio": {"url": "https://cdn/x.mp3", "duration_ms": 25000}}}
    assert main.validate_music_reference_request(ok) is None
    suno = {"mode": "music", "music_options": {"model": "suno_chirp_5_5", "reference_audio": {"url": "https://cdn/x.mp3", "duration_ms": 25000}}}
    assert main.validate_music_reference_request(suno)["error"] == "reference_not_supported"
    long = {"mode": "music", "music_options": {"model": "elevenlabs_music", "reference_audio": {"url": "https://cdn/x.mp3", "duration_ms": 45000}}}
    assert main.validate_music_reference_request(long)["error"] == "reference_too_long"
    empty = {"mode": "music", "music_options": {"model": "elevenlabs_music", "reference_audio": {}}}
    assert main.validate_music_reference_request(empty)["error"] == "reference_invalid"
    assert main.validate_music_reference_request({"mode": "music", "music_options": {"model": "suno_chirp_5_5"}}) is None
    # Defence in depth inside the provider router.
    with billing_scope("ref-guard", 0, free=True):
        result = _run(audio_router.audio_generation(dict(suno, prompt="x")))
    assert result["ok"] is False


class FakeResponse:
    def __init__(self, status=200, data=None, content=b""):
        self.status_code = status
        self._data = data
        self.content = content if content else (json.dumps(data).encode() if data is not None else b"")
        self.text = self.content.decode(errors="ignore")

    def json(self):
        return self._data


def _fake_client(calls, responses):
    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def post(self, url, headers=None, json=None, files=None, params=None):
            calls.append({"url": url, "json": json, "files": files, "headers": headers})
            return responses.pop(0)
    return FakeClient


def _setup(monkeypatch, calls, responses):
    monkeypatch.setattr(audio_router.httpx, "AsyncClient", _fake_client(calls, responses))
    monkeypatch.setattr(audio_router, "_get_env", lambda *names: "el-key" if "ELEVENLABS_API_KEY" in names else "")
    monkeypatch.setattr(audio_router, "_save_audio_file", lambda content, ext=".mp3": "/generated/audio/song.mp3")

    async def fake_media(client, url):
        return b"ID3reference", "ref.mp3", "audio/mpeg"
    monkeypatch.setattr(audio_router, "_load_provider_media", fake_media)


def test_prompt_generation_sends_genre_vocal_length(monkeypatch):
    calls = []
    _setup(monkeypatch, calls, [FakeResponse(200, content=b"MP3DATA")])
    payload = {"mode": "music", "model": "elevenlabs_music", "prompt": "Sea breeze", "skip_telegram": True,
               "music_options": {"model": "elevenlabs_music", "genre": "lofi", "vocal": "instrumental", "duration_seconds": 120}}
    with billing_scope("el-prompt", 0, free=True):
        result = _run(audio_router.audio_generation(payload))
    assert result["ok"] and result["audio_url"] == "/generated/audio/song.mp3"
    assert len(calls) == 1 and calls[0]["url"].endswith("/v1/music")
    body = calls[0]["json"]
    assert body["model_id"] == "music_v2_5" and body["music_length_ms"] == 120000 and body["force_instrumental"] is True
    assert "Sea breeze" in body["prompt"] and "lofi" in body["prompt"] and "Instrumental only" in body["prompt"]
    assert calls[0]["headers"]["xi-api-key"] == "el-key"


def test_reference_is_uploaded_and_conditions_the_plan(monkeypatch):
    calls = []
    plan = {"chunks": [{"text": "[Intro]", "duration_ms": 30000, "positive_styles": ["lofi"], "negative_styles": []},
                       {"text": "[Verse]", "duration_ms": 30000, "positive_styles": [], "negative_styles": []}]}
    _setup(monkeypatch, calls, [FakeResponse(200, {"song_id": "song-123"}), FakeResponse(200, plan), FakeResponse(200, content=b"MP3")])
    payload = {"mode": "music", "model": "elevenlabs_music", "prompt": "Calm piano", "skip_telegram": True,
               "music_options": {"model": "elevenlabs_music", "vocal": "female", "duration_seconds": 60,
                                 "reference_audio": {"url": "/generated/audio/ref.mp3", "duration_ms": 18000}}}
    with billing_scope("el-ref", 0, free=True):
        result = _run(audio_router.audio_generation(payload))
    assert result["ok"]
    assert [c["url"].rsplit("/v1/", 1)[1] for c in calls] == ["music/upload", "music/plan", "music"]
    assert calls[0]["files"]["file"][1] == b"ID3reference"
    assert calls[1]["json"] == {"prompt": calls[1]["json"]["prompt"], "music_length_ms": 60000, "model_id": "music_v2_5"}
    assert "Female lead vocals" in calls[1]["json"]["prompt"]
    composed = calls[2]["json"]
    assert composed["model_id"] == "music_v2_5" and "prompt" not in composed
    first = composed["composition_plan"]["chunks"][0]
    assert first["conditioning_ref"] == {"song_id": "song-123", "range": {"start_ms": 0, "end_ms": 18000}}


def test_reference_failure_fails_the_job(monkeypatch):
    calls = []
    _setup(monkeypatch, calls, [FakeResponse(403, {"detail": {"status": "not_allowed", "message": "Inpainting not available"}})])
    payload = {"mode": "music", "model": "elevenlabs_music", "prompt": "Calm piano", "skip_telegram": True,
               "music_options": {"model": "elevenlabs_music", "reference_audio": {"url": "/r.mp3", "duration_ms": 10000}}}
    with billing_scope("el-ref-fail", 0, free=True):
        result = _run(audio_router.audio_generation(payload))
    assert result["ok"] is False and result.get("stage") == "reference_upload"
    assert len(calls) == 1  # nothing composed without the reference
