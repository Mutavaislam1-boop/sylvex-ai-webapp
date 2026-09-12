"""A provider concurrency slot must be held only while a real dispatch
attempt is in flight - not during a failed attempt's retry backoff sleep -
and then held continuously while the provider's own async job is polling,
since that job is genuinely still running at the provider regardless of
our poll cadence."""
import asyncio

import pytest


@pytest.fixture
def app(monkeypatch):
    monkeypatch.setenv("PROVIDER_RETRY_BASE_DELAY_SECONDS", "0.05")
    monkeypatch.setenv("PROVIDER_RETRY_MAX_DELAY_SECONDS", "0.2")
    monkeypatch.setenv("PROVIDER_CIRCUIT_FAILURE_THRESHOLD", "50")  # keep circuit CLOSED for this test
    import main
    monkeypatch.setattr(main, "DATABASE_URL", "postgres://test")
    monkeypatch.setattr(main, "ensure_provider_slot_table", lambda database_url: None)
    monkeypatch.setattr(main, "update_prostudio_generation_job", lambda *a, **k: True)
    monkeypatch.setattr(main, "heartbeat_prostudio_generation_job", lambda *a, **k: None)
    monkeypatch.setattr(main, "log_user_event", lambda *a, **k: None)
    monkeypatch.setattr(main, "circuit_record_outcome", lambda *a, **k: {"state": "CLOSED", "closed": False})

    import provider_concurrency as pc
    monkeypatch.setattr(pc, "PROVIDER_SLOT_HEARTBEAT_SECONDS", 5.0)
    # provider_slot() resolves these via provider_concurrency's own module
    # globals, not main's - patching main.ensure_provider_slot_table alone
    # would not stop it from hitting a real (fake) DSN.
    monkeypatch.setattr(pc, "ensure_provider_slot_table", lambda database_url: None)
    return main


def _track_slot_calls(monkeypatch):
    import provider_concurrency as pc
    events = []

    def fake_acquire(database_url, provider, job_id, limit, worker_id):
        events.append(("acquire", job_id))
        return pc.SlotResult(acquired=True, active=1)

    def fake_release(database_url, provider, job_id, worker_id):
        events.append(("release", job_id))
        return 0

    monkeypatch.setattr(pc, "try_acquire_slot", fake_acquire)
    monkeypatch.setattr(pc, "release_slot", fake_release)
    monkeypatch.setattr(pc, "heartbeat_slot", lambda *a, **k: True)
    return events


@pytest.mark.asyncio
async def test_slot_is_released_during_dispatch_retry_backoff(app, monkeypatch):
    events = _track_slot_calls(monkeypatch)
    attempts = {"n": 0}

    async def flaky_dispatch(job_id, payload, mode, selected_model, selected_provider, text_modes):
        attempts["n"] += 1
        if attempts["n"] < 3:
            raise TimeoutError("provider timed out")
        return {"ok": True, "text": "done"}

    monkeypatch.setattr(app, "dispatch_prostudio_provider_request", flaky_dispatch)

    result, status = await app.run_prostudio_provider_request(
        "job-a", {"telegram_id": 1}, "text", "gpt-5.5", "openai", {"text"}, "openai",
    )

    assert status == "completed"
    assert attempts["n"] == 3
    # One acquire+release pair per attempt, not one acquire held across all
    # three attempts and their backoff sleeps.
    assert [kind for kind, _ in events] == ["acquire", "release"] * 3


@pytest.mark.asyncio
async def test_slot_stays_held_continuously_while_provider_job_is_processing(app, monkeypatch):
    events = _track_slot_calls(monkeypatch)
    polls = {"n": 0}

    async def dispatch_once(job_id, payload, mode, selected_model, selected_provider, text_modes):
        return {"ok": True, "status": "processing", "task_id": "kling-123"}

    async def fake_poll(result):
        polls["n"] += 1
        if polls["n"] < 3:
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
        "job-b", {"telegram_id": 1}, "video", "kling-model", "kling", {"text"}, "kling",
    )

    assert status == "completed"
    assert polls["n"] == 3
    # One acquire for the dispatch attempt, one release once it returns
    # "processing", one acquire for the poll phase, held across all three
    # polls, released once at the very end - not acquired/released per poll.
    assert events == [
        ("acquire", "job-b"),
        ("release", "job-b"),
        ("acquire", "job-b"),
        ("release", "job-b"),
    ]
