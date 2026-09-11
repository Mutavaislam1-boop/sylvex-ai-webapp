"""provider_slot()'s heartbeat must tolerate transient DB errors during a
long-running job without failing an otherwise-successful generation, but
must still surface a genuinely lost/stolen lease promptly."""
import asyncio
import importlib

import pytest

import provider_concurrency as pc


@pytest.fixture(autouse=True)
def fast_heartbeat(monkeypatch):
    # Real defaults (30s heartbeat / 90s TTL) are much too slow for a unit
    # test; shrink both by the same factor so the retry-budget math still
    # holds (heartbeat_errors * heartbeat_interval >= TTL to give up).
    monkeypatch.setattr(pc, "PROVIDER_SLOT_HEARTBEAT_SECONDS", 0.03)
    monkeypatch.setattr(pc, "PROVIDER_SLOT_TTL_SECONDS", 0.09)
    monkeypatch.setattr(pc, "ensure_provider_slot_table", lambda database_url: None)
    monkeypatch.setattr(pc, "try_acquire_slot", lambda *a, **k: pc.SlotResult(acquired=True, active=1))
    yield


def noop_log(*args, **kwargs):
    pass


@pytest.mark.asyncio
async def test_transient_heartbeat_errors_do_not_fail_a_successful_job(monkeypatch):
    calls = {"n": 0}

    def flaky_heartbeat(database_url, provider, job_id, worker_id):
        calls["n"] += 1
        if calls["n"] <= 2:
            raise ConnectionError("pool momentarily exhausted")
        return True

    released = []
    monkeypatch.setattr(pc, "heartbeat_slot", flaky_heartbeat)
    monkeypatch.setattr(pc, "release_slot", lambda *a, **k: released.append(a) or 0)

    async with pc.provider_slot("postgres://test", "kling", "job-1", noop_log):
        # Simulate a job that outlives several heartbeat cycles despite the
        # first two heartbeat attempts failing transiently.
        await asyncio.sleep(0.03 * 5)

    assert calls["n"] >= 3, "expected the heartbeat to keep retrying after transient errors"
    assert released, "slot must still be released once the job finishes successfully"


@pytest.mark.asyncio
async def test_genuinely_lost_lease_is_raised(monkeypatch):
    def stolen_heartbeat(database_url, provider, job_id, worker_id):
        return False  # DB call succeeded but confirms the row is gone

    monkeypatch.setattr(pc, "heartbeat_slot", stolen_heartbeat)
    monkeypatch.setattr(pc, "release_slot", lambda *a, **k: 0)

    with pytest.raises(RuntimeError, match="lease lost"):
        async with pc.provider_slot("postgres://test", "kling", "job-2", noop_log):
            await asyncio.sleep(0.03 * 3)


@pytest.mark.asyncio
async def test_heartbeat_failing_past_the_ttl_eventually_raises(monkeypatch):
    def always_broken(database_url, provider, job_id, worker_id):
        raise ConnectionError("db is down")

    monkeypatch.setattr(pc, "heartbeat_slot", always_broken)
    monkeypatch.setattr(pc, "release_slot", lambda *a, **k: 0)

    with pytest.raises(RuntimeError, match="risk lease loss"):
        async with pc.provider_slot("postgres://test", "kling", "job-3", noop_log):
            await asyncio.sleep(0.03 * 6)


def test_ttl_stays_a_safe_multiple_of_the_heartbeat_interval():
    importlib.reload(pc)
    assert pc.PROVIDER_SLOT_HEARTBEAT_SECONDS * 2 <= pc.PROVIDER_SLOT_TTL_SECONDS, (
        "the heartbeat must renew the lease at least twice before it can expire, "
        "or a single slow renewal looks like a dead worker"
    )
