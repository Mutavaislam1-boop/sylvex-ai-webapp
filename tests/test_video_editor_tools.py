"""SYLVEX Video Editor native tools: pricing under the SYLVEX rule, the
Enhance Video tool (server-measured source, Runway upscaler, durable
result), the editing transcript, and project storage.
Project storage runs against a real Postgres when SYLVEX_TEST_DATABASE_URL is set."""
import asyncio
import json
import os
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

import main
from services import video_editor as ve

DB_URL = os.getenv("SYLVEX_TEST_DATABASE_URL", "")
needs_db = pytest.mark.skipif(not DB_URL, reason="Set SYLVEX_TEST_DATABASE_URL to run real-SQL tests")
STORED = "/api/public/storage/generated/video-inputs/source.mp4"


class FakeRequest:
    def __init__(self, payload=None, telegram_id=7):
        self._payload = payload or {}
        self.state = SimpleNamespace(telegram_id=telegram_id)

    async def json(self):
        return dict(self._payload)


def _run(coro):
    return asyncio.run(coro)


def _body(response):
    if isinstance(response, dict):
        return 200, response
    return response.status_code, json.loads(response.body)


def _video(seconds=4, fps=25, audio=True, fmt="mp4"):
    ffmpeg = ve._ffmpeg()
    if not ffmpeg:
        pytest.skip("ffmpeg not available")
    with tempfile.TemporaryDirectory() as folder:
        target = os.path.join(folder, "clip." + fmt)
        command = [ffmpeg, "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i", f"testsrc=size=320x180:rate={fps}:duration={seconds}"]
        if audio:
            command += ["-f", "lavfi", "-i", f"sine=frequency=440:duration={seconds}"]
        command += ["-pix_fmt", "yuv420p", "-shortest", target]
        subprocess.run(command, check=True)
        return Path(target).read_bytes()


# ----------------------------------------------------------------- pricing

def test_enhance_levels_follow_the_source_size_and_runway_frame_rates():
    assert ve.enhance_resolution("clean", 1280, 720) == "720p"
    assert ve.enhance_resolution("2x", 1280, 720) == "2k"
    assert ve.enhance_resolution("2x", 1920, 1080) == "4k"
    assert ve.enhance_resolution("clean", 1080, 1920) == "1k"  # portrait: short side
    assert ve.enhance_resolution("4k", 0, 0) == "4k"
    assert ve.enhance_resolution("clean", 0, 0) == "" and ve.enhance_resolution("8k", 100, 100) == ""
    # 10 s at 30 fps = 300 output frames; 4K is $0.012/frame -> $3.60 * 1.5 = 540
    info = ve.enhance_cost_info({"duration": 10, "fps": 30, "width": 1920, "height": 1080}, "2x")
    assert (info["credits"], info["frames"], info["resolution"], info["pricing_available"]) == (540, 300, "4k", True)
    # 720p: 3.2 s at 25 fps = 80 frames * $0.007 = $0.56 -> 84
    assert ve.enhance_cost_info({"duration": 3.2, "fps": 25, "width": 1280, "height": 720}, "clean")["credits"] == 84
    assert ve.enhance_cost_info({"duration": 3, "fps": 0, "width": 1280, "height": 720}, "clean")["pricing_available"] is False


def test_transcription_is_priced_per_minute_with_a_minimum():
    assert ve.transcribe_credits(1) == 1
    assert ve.transcribe_credits(600) == 9  # 10 min * $0.006 * 1.5 * 100
    assert ve.transcribe_credits(61) == 1


def test_estimate_uses_server_measured_enhance_source():
    payload = {"mode": "video", "video_options": {"tool": "enhance_video", "enhanceLevel": "4k",
                                                  "source_meta": {"duration": 2, "fps": 24, "width": 640, "height": 360}}}
    info = main.estimate_generation_cost(payload)
    assert info["pricing_available"] and info["credits"] == 87 and info["operation"] == "enhance_video"


def test_actions_name_what_runs_each_editor_action():
    with pytest.raises(main.HTTPException):
        _run(main.public_video_editor_actions(FakeRequest(telegram_id=0)))
    response = _run(main.public_video_editor_actions(FakeRequest()))
    actions = json.loads(response.body)["actions"]
    assert actions["generateVideo"]["model"] == "seedance_2_0"
    assert actions["animatePhoto"]["tool"] == "animate_photo" and actions["animatePhoto"]["credits"] == 90
    assert actions["generateMusic"]["model"] == "suno_chirp_5_5"
    assert actions["voiceOver"]["model"] == "elevenlabs_eleven_v3"
    assert [level["id"] for level in actions["enhanceVideo"]["levels"]] == ["clean", "2x", "4k"]
    assert actions["transcribe"]["creditsPerMinute"] == pytest.approx(0.9)


def test_editor_requests_are_recognised():
    assert main.video_editor_request({"music_options": {"source": "video_editor"}})
    assert not main.video_editor_request({"music_options": {"source": "quick_music"}})


# ------------------------------------------------------------ enhance source

def test_partial_clip_is_cut_and_measured_on_the_server(monkeypatch):
    source = _video(seconds=4, fps=25)
    stored = {}
    monkeypatch.setattr(ve, "load_media_bytes", lambda url, max_bytes=0: source)
    monkeypatch.setattr(ve, "storage_put_bytes", lambda data, key, ctype: stored.update(data=data, key=key) or "/api/public/storage/" + key)
    prepared = ve.prepare_enhance_source(STORED, 1, 3)
    assert prepared["url"].startswith("/api/public/storage/generated/video-inputs/") and stored["key"].endswith(".mp4")
    assert abs(prepared["meta"]["duration"] - 2) < 0.15 and prepared["meta"]["fps"] == 25
    assert (prepared["start"], prepared["end"]) == (1.0, 3.0)
    whole = ve.prepare_enhance_source(STORED, 0, None)
    assert whole["url"] == STORED and abs(whole["meta"]["duration"] - 4) < 0.1
    with pytest.raises(ValueError, match="enhance_segment_too_short"):
        ve.prepare_enhance_source(STORED, 1, 1.2)
    monkeypatch.setattr(ve, "ENHANCE_MAX_SECONDS", 2)
    with pytest.raises(ValueError, match="enhance_too_long"):
        ve.prepare_enhance_source(STORED, 0, 3.5)


def test_estimate_lists_every_level_for_the_clip(monkeypatch):
    source = _video(seconds=3, fps=25)
    monkeypatch.setattr(ve, "load_media_bytes", lambda url, max_bytes=0: source)
    info = ve.estimate_enhance(STORED, 0, 2)
    assert info["duration"] == 2 and info["fps"] == 25
    assert [(level["id"], level["resolution"], level["credits"]) for level in info["levels"]] == [
        ("clean", "720p", 53), ("2x", "720p", 53), ("4k", "4k", 90)]


def test_client_cannot_supply_the_measured_source(monkeypatch):
    seen = {}

    def prepare(url, start, end):
        seen.update(url=url, start=start, end=end)
        return {"url": "/api/public/storage/generated/video-inputs/cut.mp4", "meta": {"duration": 2, "fps": 30, "width": 1920, "height": 1080, "has_audio": True}}

    monkeypatch.setattr(ve, "prepare_enhance_source", prepare)
    payload = {"mode": "video", "prompt": "", "model": "x", "video_options": {
        "tool": "enhance_video", "enhanceLevel": "clean", "enhanceSourceUrl": STORED, "enhanceStart": 1, "enhanceEnd": 3,
        "source_meta": {"duration": 0.1, "fps": 1, "width": 10, "height": 10}, "enhanceInputUrl": "https://evil.example/x.mp4"}}
    assert _run(main.prepare_enhance_video_request(payload)) is None
    opts = payload["video_options"]
    assert seen == {"url": STORED, "start": 1, "end": 3}
    assert opts["enhanceInputUrl"].endswith("/cut.mp4") and opts["source_meta"]["fps"] == 30 and opts["enhanceResolution"] == "1k"
    assert payload["model"] == "sylvex_enhance_video" and payload["provider"] == "runway" and payload["prompt"]
    assert main.estimate_generation_cost(payload)["credits"] == 63  # 60 frames * $0.007 * 1.5


def test_enhance_rejects_foreign_sources_and_unknown_levels(monkeypatch):
    bad_url = {"mode": "video", "video_options": {"tool": "enhance_video", "enhanceLevel": "clean", "enhanceSourceUrl": "https://evil.example/a.mp4"}}
    assert _run(main.prepare_enhance_video_request(bad_url))["error"] == "enhance_source_invalid"
    bad_level = {"mode": "video", "video_options": {"tool": "enhance_video", "enhanceLevel": "8k", "enhanceSourceUrl": STORED}}
    assert _run(main.prepare_enhance_video_request(bad_level))["error"] == "enhance_level_invalid"
    monkeypatch.setattr(ve, "prepare_enhance_source", lambda *a: (_ for _ in ()).throw(ValueError("enhance_too_long")))
    long_clip = {"mode": "video", "video_options": {"tool": "enhance_video", "enhanceLevel": "clean", "enhanceSourceUrl": STORED}}
    error = _run(main.prepare_enhance_video_request(long_clip))
    assert error["error"] == "enhance_too_long" and "секунд" in error["message"]


def test_enhance_calls_the_runway_upscaler_and_keeps_a_durable_result(monkeypatch):
    sent = {}

    class Response:
        status_code = 200
        text = "{}"

        def json(self):
            return {"id": "task-1"}

    monkeypatch.setattr(main, "runway_animate_photo_headers", lambda: {"Authorization": "Bearer test"})
    monkeypatch.setattr(main.requests, "post", lambda url, headers, json, timeout: sent.update(url=url, body=json) or Response())
    monkeypatch.setattr(main, "safe_provider_json", lambda response, provider, endpoint: response.json())
    monkeypatch.setattr(main, "poll_animate_photo_task", lambda task_id, headers, max_attempts: (True, "https://runway.example/out.mp4", {}))
    monkeypatch.setattr(main, "_persist_remote_media_url", lambda url, category, provider="": "/api/public/storage/generated/videos/out.mp4")
    monkeypatch.setattr(main, "WEBAPP_URL", "https://app.example")
    payload = {"video_options": {"tool": "enhance_video", "enhanceLevel": "2x", "enhanceResolution": "2k",
                                 "enhanceInputUrl": "/api/public/storage/generated/video-inputs/cut.mp4",
                                 "source_meta": {"duration": 2, "fps": 25, "width": 1280, "height": 720}}}
    result = _run(main.generate_enhance_video(payload))
    assert sent["url"] == "https://api.dev.runwayml.com/v1/video_upscale"
    assert sent["body"]["model"] == "magnific_video_upscaler_creative" and sent["body"]["resolution"] == "2k"
    assert sent["body"]["videoUri"].startswith("https://") and "/cut.mp4" in sent["body"]["videoUri"]
    assert result["ok"] and result["video_url"].endswith("/out.mp4") and result["storage_status"] == "completed"
    assert result["cost_credits"] == 68  # 50 frames * $0.009 * 1.5 = 67.5 -> 68


# --------------------------------------------------------------- transcript

def test_transcript_segments_are_parsed(monkeypatch):
    class Response:
        status_code = 200

        def json(self):
            return {"language": "russian", "duration": 9.5, "segments": [
                {"start": 0.4, "end": 2.1, "text": " Привет "}, {"start": 3, "end": 3, "text": "x"}, {"start": "a", "end": 1, "text": "y"}]}

    captured = {}
    monkeypatch.setattr(ve.requests, "post", lambda url, headers, files, data, timeout: captured.update(url=url, data=data) or Response())
    result = ve.transcribe_segments(b"mp3", "key", "https://api.openai.com/v1", "ru")
    assert captured["url"].endswith("/audio/transcriptions") and captured["data"]["response_format"] == "verbose_json"
    assert captured["data"]["timestamp_granularities[]"] == "segment" and captured["data"]["language"] == "ru"
    assert result == {"ok": True, "segments": [{"start": 0.4, "end": 2.1, "text": "Привет"}], "language": "russian", "duration": 9.5}


def test_transcribe_endpoint_bills_by_audio_length(monkeypatch):
    billed = {}

    async def fake_billed(owner, credits, label, call, **kwargs):
        billed.update(owner=owner, credits=credits, label=label)
        result = await call()
        result["cost_credits"] = credits
        return result

    monkeypatch.setattr(main, "OPENAI_API_KEY", "key")
    monkeypatch.setattr(main, "run_billed_helper", fake_billed)
    monkeypatch.setattr(ve, "load_media_bytes", lambda url, max_bytes=0: b"media")
    monkeypatch.setattr(ve, "probe_media", lambda content, suffix: {"duration": 125.0, "has_audio": True})
    monkeypatch.setattr(ve, "extract_speech_audio", lambda content, suffix: b"mp3")
    monkeypatch.setattr(ve, "transcribe_segments", lambda audio, key, base, language: {"ok": True, "segments": [{"start": 0, "end": 1, "text": "Да"}], "language": "ru"})
    status, body = _body(_run(main.public_video_editor_transcribe(FakeRequest({"url": STORED}, 11))))
    assert status == 200 and body["segments"] == [{"start": 0, "end": 1, "text": "Да"}]
    assert billed == {"owner": 11, "credits": 2, "label": "video_editor_transcribe"} and body["cost_credits"] == 2


def test_transcribe_without_sound_is_free_and_long_files_are_refused(monkeypatch):
    monkeypatch.setattr(main, "OPENAI_API_KEY", "key")
    monkeypatch.setattr(main, "run_billed_helper", lambda *a, **k: pytest.fail("must not bill"))
    monkeypatch.setattr(ve, "load_media_bytes", lambda url, max_bytes=0: b"media")
    monkeypatch.setattr(ve, "probe_media", lambda content, suffix: {"duration": 30.0, "has_audio": False})
    status, body = _body(_run(main.public_video_editor_transcribe(FakeRequest({"url": STORED}))))
    assert status == 200 and body["segments"] == [] and body["cost_credits"] == 0
    monkeypatch.setattr(ve, "probe_media", lambda content, suffix: {"duration": 4000.0, "has_audio": True})
    status, body = _body(_run(main.public_video_editor_transcribe(FakeRequest({"url": STORED}))))
    assert status == 400 and body["error"] == "transcribe_too_long"
    status, body = _body(_run(main.public_video_editor_transcribe(FakeRequest({"url": "https://evil.example/a.mp4"}))))
    assert status == 400 and body["error"] == "transcribe_source_invalid"


# ----------------------------------------------------------------- projects

def _project(project_id, **extra):
    project = {"schema": "sylvex.video-project", "version": 2, "id": project_id, "name": "Мой ролик",
               "media": {"video_src_1": {"id": "video_src_1", "kind": "video", "url": STORED, "duration": 4}},
               "videoClips": [{"id": "clip_1", "mediaId": "video_src_1", "sourceStart": 0, "sourceEnd": 4}],
               "audioClips": [], "texts": [], "transcripts": {}, "ui": {"pps": 80}}
    project.update(extra)
    return project


def test_project_validation():
    pid = "project_abcdef"
    assert ve.validate_project(pid, _project(pid))
    for broken, code in [
        (_project("project_other"), "invalid_video_project"),
        (_project(pid, schema="x"), "invalid_video_project"),
        (_project(pid, media={"m": {"kind": "video", "url": "blob:https://app/1"}}), "invalid_video_media_url"),
        (_project(pid, media={"m": {"kind": "font", "url": ""}}), "invalid_video_media"),
        (_project(pid, texts="x"), "invalid_video_project"),
    ]:
        with pytest.raises(ValueError, match=code):
            ve.validate_project(pid, broken)
    with pytest.raises(ValueError, match="invalid_video_project"):
        ve.validate_project("../etc", _project("../etc"))


@pytest.fixture()
def db(monkeypatch):
    monkeypatch.setattr(main, "DATABASE_URL", DB_URL)
    monkeypatch.setattr(main, "_PROSTUDIO_SCHEMA_READY", False)
    return int(str(uuid.uuid4().int)[:9])


@needs_db
def test_projects_are_saved_listed_shared_and_deleted(db):
    owner, other = db, db + 1
    pid = "project_" + uuid.uuid4().hex[:12]
    request = lambda body=None, who=owner: FakeRequest(body, who)
    saved = _run(main.public_video_editor_save_project(request({"project": _project(pid)}), pid))
    token = saved["shareToken"]
    assert saved["ok"] and len(token) >= 20
    again = _run(main.public_video_editor_save_project(request({"project": _project(pid, name="Новое имя")}), pid))
    assert again["shareToken"] == token  # the link stays valid across saves
    listed = _run(main.public_video_editor_projects(request()))["projects"]
    assert [item["id"] for item in listed] == [pid] and listed[0]["title"] == "Новое имя"
    mine = _run(main.public_video_editor_project(request(), pid))
    assert mine["owner"] and mine["shareToken"] == token and mine["project"]["ui"] == {"pps": 80}
    # Another account needs the link's token, and never sees the token itself.
    hidden = _run(main.public_video_editor_project(request(who=other), pid))
    assert hidden.status_code == 404
    shared = _run(main.public_video_editor_project(request(who=other), pid, token=token))
    assert shared["owner"] is False and shared["shareToken"] == "" and shared["project"]["name"] == "Новое имя"
    wrong = _run(main.public_video_editor_project(request(who=other), pid, token="x" * 32))
    assert wrong.status_code == 404
    status, body = _body(_run(main.public_video_editor_save_project(request({"project": _project("project_zzzzzz")}), pid)))
    assert status == 422 and body["error"] == "invalid_video_project"
    assert _run(main.public_video_editor_delete_project(request(who=other), pid))["deleted"] is False
    assert _run(main.public_video_editor_delete_project(request(), pid))["deleted"] is True
    assert _run(main.public_video_editor_projects(request()))["projects"] == []
