"""Stage 7 verification: video is the most latency-sensitive and most
expensive-to-test mode, and exactly the one the spec calls out by name
("Kling completes after 90 seconds... must not become 90s provider + 2min
storage + ... = 5-10 minute user wait"). Confirm the same decoupling that
test_generation_completion_storage_decoupling.py proved for image also
holds for video: generation_status commits to completed immediately from
the provider's own video URL, and R2's (large, slow) persistence runs
only in the background afterward."""
import pytest


@pytest.fixture
def app(monkeypatch):
    import main
    monkeypatch.setattr(main, "DATABASE_URL", "postgres://test")
    monkeypatch.setattr(main, "PROSTUDIO_MOCK_GENERATION", False)
    monkeypatch.setattr(main, "optimize_prompt_for_model", lambda *a, **k: {"ok": True, "optimized": False})
    monkeypatch.setattr(main, "resolve_prostudio_provider_for_slot", lambda *a, **k: "KLING")
    monkeypatch.setattr(main, "circuit_before_request", lambda *a, **k: {"allowed": True})
    monkeypatch.setattr(main, "circuit_release_probe", lambda *a, **k: None)
    monkeypatch.setattr(main, "heartbeat_prostudio_generation_job", lambda *a, **k: None)
    monkeypatch.setattr(main, "log_user_event", lambda *a, **k: None)
    monkeypatch.setattr(main, "save_generation", lambda *a, **k: None)
    monkeypatch.setattr(main, "build_prostudio_metadata", lambda *a, **k: {})
    monkeypatch.setattr(main, "save_prostudio_message", lambda *a, **k: "conv-1")
    monkeypatch.setattr(main, "charge_generation_balance", lambda *a, **k: {"charged": True, "balance_after": 100})

    async def fake_telegram(*a, **k):
        return True
    monkeypatch.setattr(main, "sync_completed_generation_to_telegram", fake_telegram)
    return main


class _InlineTask:
    def __init__(self, coro):
        self.coro = coro


@pytest.mark.asyncio
async def test_video_completion_does_not_wait_for_large_r2_upload(app, monkeypatch):
    job_updates = []

    def fake_update(job_id, status, result=None, error=None, conversation_id=""):
        job_updates.append({"status": status, "result": result})
        return True

    monkeypatch.setattr(app, "update_prostudio_generation_job", fake_update)

    async def fake_provider_request(*a, **k):
        return (
            {
                "ok": True, "type": "video", "status": "completed",
                "video_url": "https://kling.provider.example/tmp-video.mp4",
                "provider": "kling", "model": "kling-2-5",
            },
            "completed",
        )

    monkeypatch.setattr(app, "run_prostudio_provider_request", fake_provider_request)

    background_tasks = []
    monkeypatch.setattr(app.asyncio, "create_task", lambda coro: background_tasks.append(coro) or _InlineTask(coro))

    r2_upload_started = {"value": False}

    def slow_persist(result, mode):
        # If this ever runs on the critical path, the test's own event loop
        # would block here - proving it only runs via the background task
        # keeps this test both a correctness and a "not on the critical
        # path" check without needing a real slow upload.
        r2_upload_started["value"] = True
        return {**result, "video_url": "https://r2.example/permanent-video.mp4"}

    monkeypatch.setattr(app, "persist_generation_media", slow_persist)
    monkeypatch.setattr(app, "verify_persisted_generation_media", lambda result, mode: [result["video_url"]])

    payload = {
        "telegram_id": 900, "mode": "video", "prompt": "a dog running",
        "model": "kling-2-5", "provider": "kling",
        "price_snapshot": {"final_credits": 200},
    }
    await app.process_prostudio_generation("job-video-1", payload)

    assert r2_upload_started["value"] is False, "R2 persistence must not run before the job is committed completed"
    completed = [c for c in job_updates if c["status"] == "completed"]
    assert completed, "video generation must commit completed as soon as the provider responds"
    assert completed[0]["result"]["video_url"] == "https://kling.provider.example/tmp-video.mp4"
    assert completed[0]["result"]["storage_status"] == "pending"
    assert len(background_tasks) == 1

    merge_calls = []
    monkeypatch.setattr(
        app, "_merge_prostudio_storage_result",
        lambda job_id, fields, status: merge_calls.append((job_id, fields, status)),
    )
    await background_tasks[0]
    assert r2_upload_started["value"] is True, "the background task must still actually persist to R2"
    assert len(merge_calls) == 1
    job_id, fields, status = merge_calls[0]
    assert job_id == "job-video-1"
    assert status == "completed"
    assert fields["video_url"] == "https://r2.example/permanent-video.mp4"
