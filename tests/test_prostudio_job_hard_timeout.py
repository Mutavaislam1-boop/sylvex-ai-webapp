"""Local hard-deadline tests for Pro Studio provider jobs; no provider calls."""
import asyncio

import pytest

import provider_concurrency as pc
import main


@pytest.mark.asyncio
async def test_provider_timeout_fails_job_and_releases_slot(monkeypatch):
    monkeypatch.setattr(main, "DATABASE_URL", "postgres://test")
    monkeypatch.setattr(main, "PROSTUDIO_MAX_JOB_RUNTIME_SECONDS", 0.03)
    monkeypatch.setattr(main, "ensure_provider_slot_table", lambda *_: None)
    monkeypatch.setattr(pc, "ensure_provider_slot_table", lambda *_: None)
    monkeypatch.setattr(pc, "PROVIDER_SLOT_HEARTBEAT_SECONDS", 5.0)
    monkeypatch.setattr(pc, "try_acquire_slot", lambda *args, **kwargs: pc.SlotResult(acquired=True, active=1))
    monkeypatch.setattr(pc, "heartbeat_slot", lambda *args, **kwargs: True)
    released = []
    monkeypatch.setattr(pc, "release_slot", lambda *args, **kwargs: released.append(args[2]) or 0)
    monkeypatch.setattr(main, "circuit_record_outcome", lambda *args, **kwargs: {"state": "CLOSED"})
    monkeypatch.setattr(main, "prostudio_debug", lambda *args, **kwargs: None)
    monkeypatch.setattr(main, "log_prostudio_error", lambda *args, **kwargs: None)
    terminal_updates = []
    monkeypatch.setattr(
        main,
        "update_prostudio_generation_job",
        lambda job_id, status, **kwargs: terminal_updates.append((job_id, status, kwargs.get("error"))) or True,
    )

    async def hanging_provider(*args, **kwargs):
        await asyncio.Event().wait()

    monkeypatch.setattr(main, "dispatch_prostudio_provider_request", hanging_provider)
    # A priced job with its reservation held: the billing gate lets it dispatch.
    monkeypatch.setattr(main, "verify_job_reservation", lambda job_id, credits: None)

    async def process_with_provider_slot(job_id, payload):
        await main.run_prostudio_provider_request(
            job_id, payload, "image", "model", "openai", {"text"}, "openai"
        )

    monkeypatch.setattr(main, "process_prostudio_generation", process_with_provider_slot)
    await main.run_prostudio_generation_with_timeout("job-timeout", {"telegram_id": 1, "price_snapshot": {"final_credits": 5}})

    assert released == ["job-timeout"]
    assert len(terminal_updates) == 1
    job_id, status, error = terminal_updates[0]
    assert job_id == "job-timeout"
    assert status == "failed"
    assert error["error_code"] == "generation_timeout"


@pytest.mark.asyncio
async def test_provider_success_is_not_timed_out(monkeypatch):
    monkeypatch.setattr(main, "PROSTUDIO_MAX_JOB_RUNTIME_SECONDS", 1)
    completed = []

    async def quick_process(job_id, payload):
        completed.append(job_id)

    monkeypatch.setattr(main, "process_prostudio_generation", quick_process)
    await main.run_prostudio_generation_with_timeout("job-ok", {})
    assert completed == ["job-ok"]
