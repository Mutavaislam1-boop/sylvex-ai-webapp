"""poll_video_generation had no status-parsing branch for minimax, sora,
or veo - any job from these providers that didn't finish on the very
first synchronous submit call fell into the generic catch-all, which
unconditionally returns status="processing" forever. Since video
generation for these providers is genuinely asynchronous, this meant
jobs got stuck "processing" indefinitely and could never reach a
terminal state."""
import json

import pytest

import services.video_router as video_router


class _FakeResponse:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self.text = json.dumps(payload)
        self.content = b"fake-video-bytes"


@pytest.mark.asyncio
async def test_minimax_processing_status_keeps_polling(monkeypatch):
    monkeypatch.setattr(video_router, "_get_env", lambda *names: "test-key")
    monkeypatch.setattr(
        video_router, "_request_get",
        lambda url, headers: _FakeResponse(200, {"status": "Processing", "task_id": "mm-1"}),
    )
    result = await video_router.poll_video_generation({"provider": "minimax", "task_id": "mm-1", "model": "minimax_hailuo_2_3"})
    assert result.get("status") == "processing", result


@pytest.mark.asyncio
async def test_minimax_success_retrieves_the_file_and_completes(monkeypatch):
    monkeypatch.setattr(video_router, "_get_env", lambda *names: "test-key")

    def fake_get(url, headers):
        if "query/video_generation" in url:
            return _FakeResponse(200, {"status": "Success", "file_id": "file-123"})
        if "files/retrieve" in url:
            return _FakeResponse(200, {"download_url": "https://minimax.example/video.mp4"})
        raise AssertionError("unexpected URL: " + url)

    monkeypatch.setattr(video_router, "_request_get", fake_get)
    result = await video_router.poll_video_generation({"provider": "minimax", "task_id": "mm-2", "model": "minimax_hailuo_2_3"})
    assert result.get("status") == "completed"
    assert "https://minimax.example/video.mp4" in (result.get("videos") or [result.get("video_url")])


@pytest.mark.asyncio
async def test_minimax_fail_status_returns_error(monkeypatch):
    monkeypatch.setattr(video_router, "_get_env", lambda *names: "test-key")
    monkeypatch.setattr(
        video_router, "_request_get",
        lambda url, headers: _FakeResponse(200, {"status": "Fail"}),
    )
    result = await video_router.poll_video_generation({"provider": "minimax", "task_id": "mm-3", "model": "minimax_hailuo_2_3"})
    assert result.get("ok") is False


@pytest.mark.asyncio
async def test_sora_in_progress_keeps_polling(monkeypatch):
    monkeypatch.setattr(video_router, "_get_env", lambda *names: "test-key")
    monkeypatch.setattr(
        video_router, "_request_get",
        lambda url, headers: _FakeResponse(200, {"status": "in_progress", "id": "video_1"}),
    )
    result = await video_router.poll_video_generation({"provider": "sora", "task_id": "video_1", "model": "sora_2"})
    assert result.get("status") == "processing"


@pytest.mark.asyncio
async def test_sora_completed_downloads_content_and_persists_to_r2(monkeypatch):
    monkeypatch.setattr(video_router, "_get_env", lambda *names: "test-key")
    monkeypatch.setattr(
        video_router, "_request_get",
        lambda url, headers: _FakeResponse(200, {"status": "completed", "id": "video_2"}),
    )
    monkeypatch.setattr(video_router, "safe_get", lambda url, headers=None, timeout=None: _FakeResponse(200, {}))
    monkeypatch.setattr(video_router, "storage_put_bytes", lambda content, key, mime: "https://r2.example/persisted-video.mp4")

    result = await video_router.poll_video_generation({"provider": "sora", "task_id": "video_2", "model": "sora_2"})
    assert result.get("status") == "completed"
    assert "https://r2.example/persisted-video.mp4" in (result.get("videos") or [result.get("video_url")])


@pytest.mark.asyncio
async def test_sora_failed_status_returns_error(monkeypatch):
    monkeypatch.setattr(video_router, "_get_env", lambda *names: "test-key")
    monkeypatch.setattr(
        video_router, "_request_get",
        lambda url, headers: _FakeResponse(200, {"status": "failed"}),
    )
    result = await video_router.poll_video_generation({"provider": "sora", "task_id": "video_3", "model": "sora_2"})
    assert result.get("ok") is False


@pytest.mark.asyncio
async def test_veo_not_done_keeps_polling(monkeypatch):
    monkeypatch.setattr(video_router, "_get_env", lambda *names: "test-key")
    monkeypatch.setattr(
        video_router, "_request_get",
        lambda url, headers: _FakeResponse(200, {"name": "models/veo-3.1/operations/abc", "done": False}),
    )
    result = await video_router.poll_video_generation({"provider": "veo", "task_id": "models/veo-3.1/operations/abc", "model": "veo_3_1"})
    assert result.get("status") == "processing"


@pytest.mark.asyncio
async def test_veo_done_downloads_video_and_completes(monkeypatch):
    monkeypatch.setattr(video_router, "_get_env", lambda *names: "test-key")
    veo_response = {
        "name": "models/veo-3.1/operations/abc",
        "done": True,
        "response": {
            "generateVideoResponse": {
                "generatedSamples": [{"video": {"uri": "https://generativelanguage.googleapis.com/v1beta/files/abc"}}],
            },
        },
    }
    monkeypatch.setattr(video_router, "_request_get", lambda url, headers: _FakeResponse(200, veo_response))
    monkeypatch.setattr(video_router, "safe_get", lambda url, headers=None, timeout=None: _FakeResponse(200, {}))
    monkeypatch.setattr(video_router, "storage_put_bytes", lambda content, key, mime: "https://r2.example/veo-video.mp4")

    result = await video_router.poll_video_generation({"provider": "veo", "task_id": "models/veo-3.1/operations/abc", "model": "veo_3_1"})
    assert result.get("status") == "completed"
    assert "https://r2.example/veo-video.mp4" in (result.get("videos") or [result.get("video_url")])


@pytest.mark.asyncio
async def test_veo_error_field_returns_failure(monkeypatch):
    monkeypatch.setattr(video_router, "_get_env", lambda *names: "test-key")
    monkeypatch.setattr(
        video_router, "_request_get",
        lambda url, headers: _FakeResponse(200, {"name": "op", "done": True, "error": {"message": "quota exceeded"}}),
    )
    result = await video_router.poll_video_generation({"provider": "veo", "task_id": "op", "model": "veo_3_1"})
    assert result.get("ok") is False
