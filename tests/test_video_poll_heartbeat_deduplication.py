"""The video/async-provider poll loop inside run_prostudio_provider_request
used to call heartbeat_prostudio_generation_job(job_id) directly (not
off-loop) on every 5-second poll tick. That was pure duplicate DB traffic:
_prostudio_job_heartbeat_loop already heartbeats the same job_id
independently every ~60s for as long as the worker slot is occupied
(see _run_prostudio_generation_pool), off-loop via asyncio.to_thread. The
inline call both wasted DB connections tied to the poll cadence instead of
a decoupled heartbeat cadence, and blocked the shared event loop with a
synchronous DB round trip - exactly the class of bug the very first
stability pass was meant to eliminate."""
import asyncio

import pytest


@pytest.fixture
def app(monkeypatch):
    monkeypatch.setenv("PROVIDER_CIRCUIT_FAILURE_THRESHOLD", "50")
    import main
    monkeypatch.setattr(main, "DATABASE_URL", "postgres://test")
    monkeypatch.setattr(main, "ensure_provider_slot_table", lambda database_url: None)
    monkeypatch.setattr(main, "update_prostudio_generation_job", lambda *a, **k: True)
    monkeypatch.setattr(main, "log_user_event", lambda *a, **k: None)
    monkeypatch.setattr(main, "circuit_record_outcome", lambda *a, **k: {"state": "CLOSED", "closed": False})

    import provider_concurrency as pc
    monkeypatch.setattr(pc, "PROVIDER_SLOT_HEARTBEAT_SECONDS", 5.0)
    monkeypatch.setattr(pc, "ensure_provider_slot_table", lambda database_url: None)
    monkeypatch.setattr(pc, "try_acquire_slot", lambda *a, **k: pc.SlotResult(acquired=True, active=1))
    monkeypatch.setattr(pc, "release_slot", lambda *a, **k: 0)
    monkeypatch.setattr(pc, "heartbeat_slot", lambda *a, **k: True)
    return main


@pytest.mark.asyncio
async def test_video_poll_loop_never_calls_job_heartbeat_directly(app, monkeypatch):
    heartbeat_calls = []
    monkeypatch.setattr(app, "heartbeat_prostudio_generation_job", lambda *a, **k: heartbeat_calls.append(a))

    async def dispatch_once(job_id, payload, mode, selected_model, selected_provider, text_modes):
        return {"ok": True, "status": "processing", "task_id": "kling-123"}

    polls = {"n": 0}

    async def fake_poll(result):
        polls["n"] += 1
        if polls["n"] < 4:
            return {"ok": True, "status": "processing"}
        return {"ok": True, "status": "completed", "video_url": "https://example.com/v.mp4"}

    monkeypatch.setattr(app, "dispatch_prostudio_provider_request", dispatch_once)
    monkeypatch.setattr(app, "poll_video_generation", fake_poll)
    monkeypatch.setattr(app, "run_provider_coroutine_off_loop", lambda factory: factory())

    real_sleep = asyncio.sleep

    async def fast_sleep(_seconds):
        await real_sleep(0.01)

    monkeypatch.setattr(app.asyncio, "sleep", fast_sleep)

    result, status = await app.run_prostudio_provider_request(
        "job-heartbeat-dedup", {"telegram_id": 1}, "video", "kling-model", "kling", {"text"}, "kling",
    )

    assert status == "completed"
    assert polls["n"] == 4
    assert heartbeat_calls == [], (
        "the poll loop must rely on the independent background heartbeat "
        "task, not call heartbeat_prostudio_generation_job itself"
    )
