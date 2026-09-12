"""Kling's own text2video/image2video API reports completion as
task_status "succeed" (not "succeeded") - confirmed against current Kling
API documentation, and already handled correctly by the three sibling
Kling poll functions (legacy/effects/lip-sync). The primary
_kling_poll_until_ready (used for standard text-to-video and
image-to-video, Kling's most common use case here) was missing it, so a
video Kling had already finished kept reporting "processing" until the
job was eventually recovered as stale - looking exactly like the reported
"video generation times out / doesn't return a result" symptom."""
import json

import pytest

import services.video_router as video_router


class _FakeResponse:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self.text = json.dumps(payload)


def _kling_response(task_status, video_url=None):
    task = {"task_status": task_status, "task_result": {}}
    if video_url:
        task["task_result"] = {"videos": [{"url": video_url}]}
    return {"code": 0, "data": task}


def test_kling_succeed_status_is_recognized_as_completed(monkeypatch):
    monkeypatch.setattr(
        video_router, "_request_get",
        lambda url, headers: _FakeResponse(200, _kling_response("succeed", "https://example.com/video.mp4")),
    )

    result = video_router._kling_poll_until_ready("task-123", {"Authorization": "Bearer test"})

    assert result.get("ok") is True, result
    assert result.get("status") == "completed"
    assert "https://example.com/video.mp4" in (result.get("videos") or result.get("urls") or [result.get("video_url")])


def test_kling_processing_status_keeps_polling(monkeypatch):
    calls = {"n": 0}

    def fake_get(url, headers):
        calls["n"] += 1
        if calls["n"] < 3:
            return _FakeResponse(200, _kling_response("processing"))
        return _FakeResponse(200, _kling_response("succeed", "https://example.com/video.mp4"))

    monkeypatch.setattr(video_router, "_request_get", fake_get)
    monkeypatch.setattr(video_router, "_kling_poll_attempt_settings", lambda default_attempts, default_interval: (10, 0))

    result = video_router._kling_poll_until_ready("task-456", {"Authorization": "Bearer test"})

    assert result.get("status") == "completed"
    assert calls["n"] == 3


def test_kling_failed_status_returns_error(monkeypatch):
    monkeypatch.setattr(
        video_router, "_request_get",
        lambda url, headers: _FakeResponse(200, _kling_response("failed")),
    )

    result = video_router._kling_poll_until_ready("task-789", {"Authorization": "Bearer test"})

    assert result.get("ok") is False
