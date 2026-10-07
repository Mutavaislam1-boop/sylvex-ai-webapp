"""Regression tests for remediation item #19 (BUG-4) immediate mitigation.

get_active_prostudio_job() is a plain synchronous DB call. Two hot-path
endpoints called it directly from their own `async def` handler body, with
no asyncio.to_thread() - every call blocked this process's single asyncio
event loop for the full duration of that DB round trip (worse under
Postgres lock contention, where recover_stale_prostudio_job()'s retry
backoff can add real time.sleep() on top), during which NO other request
from ANY user could be serviced at all:

  - GET  /api/public/prostudio/active-job  -> public_prostudio_active_job()
  - POST /api/public/prostudio/generate     -> public_prostudio_generate()'s
    own active-job pre-check

Fix: both call sites now go through `await asyncio.to_thread(...)`. This
file proves (1) the lookup actually runs on a worker thread, not the event
loop's own thread, for both endpoints; (2) every existing success/error
response shape is unchanged; and (3) concurrent/other work on the event
loop is no longer starved while the lookup is in flight (the loop stays
responsive, and multiple concurrent lookups overlap instead of serializing).

Reuses the exact app/FakeRequest/mock pattern already established in
tests/test_text_generation_route.py for public_prostudio_generate()."""
import asyncio
import json
import threading
import time

import pytest


class FakeRequest:
    def __init__(self, payload):
        self._payload = payload

    async def json(self):
        return dict(self._payload)


def _generate_payload(**overrides):
    payload = {
        "telegram_id": 42,
        "mode": "image",
        "prompt": "a cat wearing sunglasses",
        "model": "flux_2",
        "provider": "sylvex-router",
    }
    payload.update(overrides)
    return payload


@pytest.fixture
def app(monkeypatch):
    import main

    monkeypatch.setattr(main, "get_user_state", lambda telegram_id, **k: {"subscription_status": "active", "balance": 1000})
    monkeypatch.setattr(main, "calculate_generation_price", lambda payload: {
        "credits": 1, "pricing_available": True, "price_snapshot": {"final_credits": 1}, "generation_cost": "1 ⚡",
    })
    return main


def _thread_recording_lookup(result=None, raise_exc=None, delay=0.0):
    """A stand-in for get_active_prostudio_job() that records which thread
    actually called it, so tests can assert that thread is not the
    event loop's own thread."""
    seen_threads = []

    def spy(telegram_id):
        seen_threads.append(threading.get_ident())
        if delay:
            time.sleep(delay)
        if raise_exc:
            raise raise_exc
        return dict(result or {})

    return spy, seen_threads


# ---------------------------------------------------------------------------
# public_prostudio_active_job()
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_active_job_endpoint_runs_the_lookup_off_the_event_loop_thread(app, monkeypatch):
    main_thread_id = threading.get_ident()
    spy, seen_threads = _thread_recording_lookup(result={"id": "job-1", "status": "processing"})
    monkeypatch.setattr(app, "get_active_prostudio_job", spy)

    response = await app.public_prostudio_active_job(telegram_id=42)

    assert seen_threads, "the lookup must actually have run"
    assert seen_threads[0] != main_thread_id, "must run via asyncio.to_thread, not directly on the event loop"
    assert response == {
        "ok": True,
        "active": True,
        "active_job_id": "job-1",
        "status": "processing",
        "job": {"id": "job-1", "status": "processing"},
    }


@pytest.mark.asyncio
async def test_active_job_endpoint_no_active_job_response_is_unchanged(app, monkeypatch):
    spy, seen_threads = _thread_recording_lookup(result={})
    monkeypatch.setattr(app, "get_active_prostudio_job", spy)

    response = await app.public_prostudio_active_job(telegram_id=42)

    assert seen_threads
    assert response == {"ok": True, "active": False, "active_job_id": "", "status": "", "job": {}}


@pytest.mark.asyncio
async def test_active_job_endpoint_missing_telegram_id_is_still_rejected_without_any_lookup(app, monkeypatch):
    calls = []
    monkeypatch.setattr(app, "get_active_prostudio_job", lambda telegram_id: calls.append(telegram_id) or {})

    response = await app.public_prostudio_active_job(telegram_id=0)

    assert response.status_code == 400
    assert json.loads(response.body) == {"ok": False, "error": "telegram_id_required"}
    assert calls == [], "a request with no telegram_id must never reach the lookup at all"


@pytest.mark.asyncio
async def test_active_job_endpoint_lookup_failure_still_returns_the_same_500_error(app, monkeypatch):
    spy, seen_threads = _thread_recording_lookup(raise_exc=RuntimeError("db exploded"))
    monkeypatch.setattr(app, "get_active_prostudio_job", spy)

    response = await app.public_prostudio_active_job(telegram_id=42)

    assert seen_threads, "the lookup must actually have been attempted"
    assert response.status_code == 500
    assert json.loads(response.body) == {"ok": False, "error": "active_job_lookup_failed"}


# ---------------------------------------------------------------------------
# public_prostudio_generate()'s own active-job pre-check
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_generate_precheck_runs_the_lookup_off_the_event_loop_thread(app, monkeypatch):
    main_thread_id = threading.get_ident()
    spy, seen_threads = _thread_recording_lookup(result={"id": "job-77", "status": "queued"})
    monkeypatch.setattr(app, "get_active_prostudio_job", spy)

    response = await app.public_prostudio_generate(FakeRequest(_generate_payload(mode="image")))

    assert seen_threads, "the pre-check must actually have run"
    assert seen_threads[0] != main_thread_id, "must run via asyncio.to_thread, not directly on the event loop"
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_generate_precheck_blocks_a_non_text_mode_when_a_job_is_already_active(app, monkeypatch):
    spy, _ = _thread_recording_lookup(result={"id": "job-77", "status": "queued"})
    monkeypatch.setattr(app, "get_active_prostudio_job", spy)

    response = await app.public_prostudio_generate(FakeRequest(_generate_payload(mode="image")))

    assert response.status_code == 409
    assert json.loads(response.body) == {
        "ok": False,
        "error": "active_generation_exists",
        "message": "У пользователя уже есть активная генерация.",
        "active_job_id": "job-77",
        "status": "queued",
    }


@pytest.mark.asyncio
async def test_generate_precheck_failure_still_returns_the_same_503_error(app, monkeypatch):
    spy, seen_threads = _thread_recording_lookup(raise_exc=RuntimeError("db exploded"))
    monkeypatch.setattr(app, "get_active_prostudio_job", spy)

    response = await app.public_prostudio_generate(FakeRequest(_generate_payload(mode="image")))

    assert seen_threads, "the pre-check must actually have been attempted"
    assert response.status_code == 503
    assert json.loads(response.body) == {
        "ok": False,
        "error": "active_job_lookup_failed",
        "message": "Не удалось проверить активную генерацию.",
    }


@pytest.mark.asyncio
async def test_generate_precheck_does_not_block_text_mode_even_with_an_active_media_job(app, monkeypatch):
    """Direct text requests remain available while a media task is running -
    this pre-existing behavior (text_modes bypass the 409) must survive the
    to_thread change unchanged, end to end through a real successful call."""
    main_thread_id = threading.get_ident()
    spy, seen_threads = _thread_recording_lookup(result={"id": "job-99", "status": "processing"})
    monkeypatch.setattr(app, "get_active_prostudio_job", spy)
    monkeypatch.setattr(app, "reserve_direct_text_generation", lambda telegram_id, credits: "gen-1")
    monkeypatch.setattr(app, "release_direct_text_generation", lambda generation_id: None)
    monkeypatch.setattr(app, "charge_generation_balance", lambda telegram_id, generation_id, result, payload: {
        "charged": True, "balance_after": 999,
    })
    monkeypatch.setattr(app, "text_generation", lambda payload: {"ok": True, "text": "hi there"})
    monkeypatch.setattr(app, "save_prostudio_message", lambda payload, result: "conv-1")

    response = await app.public_prostudio_generate(FakeRequest(_generate_payload(mode="text", model="gpt-5.5")))

    assert seen_threads, "the pre-check must still run even for text mode"
    assert seen_threads[0] != main_thread_id
    assert isinstance(response, dict)
    assert response.get("ok") is True
    assert response.get("text") == "hi there"


# ---------------------------------------------------------------------------
# Concurrency / event-loop-responsiveness
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_concurrent_active_job_lookups_overlap_instead_of_serializing_on_the_event_loop(app, monkeypatch):
    delay = 0.2

    def slow_lookup(telegram_id):
        time.sleep(delay)
        return {}

    monkeypatch.setattr(app, "get_active_prostudio_job", slow_lookup)

    start = time.monotonic()
    await asyncio.gather(
        app.public_prostudio_active_job(telegram_id=1),
        app.public_prostudio_active_job(telegram_id=2),
        app.public_prostudio_active_job(telegram_id=3),
    )
    elapsed = time.monotonic() - start

    # Pre-fix, three 0.2s *synchronous* calls on the one event loop thread
    # would serialize to >= 0.6s. Off-thread via asyncio.to_thread, they
    # overlap - comfortably under 2x one delay.
    assert elapsed < delay * 2, f"lookups appear to have serialized on the event loop (elapsed={elapsed:.3f}s)"


@pytest.mark.asyncio
async def test_event_loop_stays_responsive_while_a_slow_active_job_lookup_is_in_flight(app, monkeypatch):
    """Deterministic ordering (unlike a bare asyncio.gather(), whose two
    coroutines' *first* turn order is not guaranteed and could happen to
    mask the very serialization this test exists to catch): the ticker
    task is created and given one explicit head-start tick via
    `await asyncio.sleep(0)` *before* the blocking lookup is awaited in
    this same task, so the gap between its first and second tick is
    guaranteed to span the lookup's own blocking window."""
    delay = 0.3

    def slow_lookup(telegram_id):
        time.sleep(delay)
        return {}

    monkeypatch.setattr(app, "get_active_prostudio_job", slow_lookup)

    tick_times = []

    async def ticker():
        for _ in range(5):
            tick_times.append(time.monotonic())
            await asyncio.sleep(0.02)

    ticker_task = asyncio.ensure_future(ticker())
    await asyncio.sleep(0)  # let the ticker log its first tick before the lookup starts
    assert len(tick_times) >= 1, "the ticker must have gotten at least one turn before the lookup starts"

    await app.public_prostudio_active_job(telegram_id=1)
    await ticker_task

    gaps = [b - a for a, b in zip(tick_times, tick_times[1:])]
    assert max(gaps) < delay, (
        "the event loop appears to have been frozen for the full duration of the "
        "synchronous lookup instead of letting the concurrent ticker run in the meantime "
        f"(largest gap between ticks = {max(gaps):.3f}s)"
    )
