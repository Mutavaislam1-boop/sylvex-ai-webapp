"""Grok Video had three compounding audit findings: (1) GROK_VIDEO_MODEL /
GROK_VIDEO_EDIT_MODEL had no hardcoded default, so provider_model was None
and every request failed with "unknown provider model mapping" unless the
env var was set; (2) _call_grok forwarded SYLVEX's raw internal payload
dict (start_image/ratio/resolution/etc, our own key names) straight to
xAI instead of building an explicit request body; (3) poll_video_generation
had no "grok" branch, so an async Grok Video job that didn't finish on the
first submit call fell into the generic catch-all and stayed "processing"
forever."""
import json

import pytest

import services.video_router as video_router


class _FakeResponse:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self.text = json.dumps(payload)


def test_grok_video_has_hardcoded_default_models(monkeypatch):
    monkeypatch.delenv("GROK_VIDEO_MODEL", raising=False)
    monkeypatch.delenv("GROK_VIDEO_EDIT_MODEL", raising=False)
    import importlib
    reloaded = importlib.reload(video_router)
    try:
        assert reloaded._provider_model_for_video("grok_video")
        assert reloaded._provider_model_for_video("grok_video_edit")
    finally:
        importlib.reload(video_router)


def test_call_grok_builds_an_explicit_body_not_the_raw_internal_payload(monkeypatch):
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

    payload = {"video_options": {"ratio": "16:9", "duration": 5}}
    video_router._call_grok("grok_video", "a rocket launching", payload)

    body = captured["body"]
    assert body["model"] == "grok-video-1"
    assert body["prompt"] == "a rocket launching"
    # Internal SYLVEX keys must not leak into the provider request.
    assert "start_image" not in body
    assert "resolution" not in body


@pytest.mark.asyncio
async def test_grok_poll_keeps_polling_while_processing(monkeypatch):
    monkeypatch.setattr(video_router, "_get_env", lambda *names: "test-key")
    monkeypatch.setattr(
        video_router, "_request_get",
        lambda url, headers: _FakeResponse(200, {"status": "in_progress", "id": "grok-task-2"}),
    )
    result = await video_router.poll_video_generation({"provider": "grok", "task_id": "grok-task-2", "model": "grok_video"})
    assert result.get("status") == "processing"


@pytest.mark.asyncio
async def test_grok_poll_completes_with_a_video_url(monkeypatch):
    monkeypatch.setattr(video_router, "_get_env", lambda *names: "test-key")
    monkeypatch.setattr(
        video_router, "_request_get",
        lambda url, headers: _FakeResponse(200, {"status": "completed", "video_url": "https://x.ai/videos/grok-task-3.mp4"}),
    )
    result = await video_router.poll_video_generation({"provider": "grok", "task_id": "grok-task-3", "model": "grok_video"})
    assert result.get("status") == "completed"
    assert "https://x.ai/videos/grok-task-3.mp4" in (result.get("videos") or [result.get("video_url")])


@pytest.mark.asyncio
async def test_grok_poll_reports_failure(monkeypatch):
    monkeypatch.setattr(video_router, "_get_env", lambda *names: "test-key")
    monkeypatch.setattr(
        video_router, "_request_get",
        lambda url, headers: _FakeResponse(200, {"status": "failed"}),
    )
    result = await video_router.poll_video_generation({"provider": "grok", "task_id": "grok-task-4", "model": "grok_video"})
    assert result.get("ok") is False
