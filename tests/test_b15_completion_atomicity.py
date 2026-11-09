"""B15: a queued job's charge and its completed status commit together.

Before the fix settle_generation committed the charge in its own
transaction and the completed write followed in another. A database error
in the second, or a worker that died between the two, left the job failed
with its credits kept (balance 100 -> 80, reservation 'charged').

These tests run the real billing, job and outbox code on a real PostgreSQL
schema built by the application's own ensure_* functions. Only the outside
world (provider, Telegram, history, prompt optimiser) is stubbed.
"""
import asyncio
import json
import os
import threading
from contextlib import contextmanager

import psycopg2
import pytest

import main

DSN = os.getenv("SYLVEX_TEST_DATABASE_URL", "")
pytestmark = pytest.mark.skipif(not DSN, reason="real PostgreSQL completion/billing atomicity")

UID = 4242
PRICE = 20
START = 100
PAYLOAD = {"telegram_id": UID, "mode": "image", "prompt": "A portrait", "model": "gpt-image-2",
           "provider": "openai", "price_snapshot": {"final_credits": PRICE}, "image_options": {"count": 1}}
PROVIDER_RESULT = {"ok": True, "type": "image", "status": "completed", "image_url": "https://cdn.example.test/r.png",
                   "images": ["https://cdn.example.test/r.png"], "provider": "openai", "model": "gpt-image-2"}


class _Conn:
    """psycopg2 connection whose close() is safe to call twice (like PooledConnection)."""

    def __init__(self):
        self._c = psycopg2.connect(DSN)

    def __getattr__(self, name):
        return getattr(self._c, name)

    def __enter__(self):
        return self._c.__enter__()

    def __exit__(self, *exc):
        return self._c.__exit__(*exc)

    def close(self):
        if not self._c.closed:
            self._c.close()


@contextmanager
def _db_connection(url="", timeout=None):
    conn = psycopg2.connect(DSN)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


@pytest.fixture
def db(monkeypatch):
    import provider_concurrency
    admin = psycopg2.connect(DSN)
    admin.autocommit = True
    with admin.cursor() as cur:
        cur.execute("DROP SCHEMA IF EXISTS public CASCADE; CREATE SCHEMA public")
        # users is created by the main bot in the shared database.
        cur.execute("""CREATE TABLE users (id SERIAL PRIMARY KEY, telegram_id BIGINT UNIQUE, username TEXT,
                       first_name TEXT, balance INTEGER DEFAULT 0, subscription TEXT DEFAULT 'Free', created_at TEXT)""")
        cur.execute("INSERT INTO users (telegram_id, first_name, balance) VALUES (%s, 'b15', %s)", (UID, START))
    admin.close()
    monkeypatch.setattr(main, "DATABASE_URL", DSN)
    monkeypatch.setattr(main, "db_connect", lambda *a, **k: _Conn())
    monkeypatch.setattr(main, "db_connection", _db_connection)
    monkeypatch.setattr(provider_concurrency, "db_connection", _db_connection)
    monkeypatch.setattr(main, "_PROSTUDIO_SCHEMA_READY", False)
    monkeypatch.setattr(provider_concurrency, "_SCHEMA_READY", False)
    monkeypatch.setattr(main, "PROSTUDIO_COMPLETION_ATTEMPTS", 3)
    main.ensure_prostudio_table()
    main.ensure_reservations(lambda: _Conn())
    provider_concurrency.ensure_provider_slot_table(DSN)
    yield


def q(sql, params=()):
    conn = psycopg2.connect(DSN)
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            rows = cur.fetchall() if cur.description else None
        conn.commit()
        return rows
    finally:
        conn.close()


def new_job(job_id, status="processing", minutes_old=0, reserve=PRICE):
    conn = psycopg2.connect(DSN)
    try:
        with conn.cursor() as cur:
            main.reserve_generation(cur, UID, job_id, reserve)
            cur.execute(
                """INSERT INTO prostudio_generation_jobs (id, telegram_id, status, mode, request_json,
                       created_at, updated_at, heartbeat_at)
                   VALUES (%s, %s, %s, 'image', %s::jsonb, NOW() - (%s || ' minutes')::interval,
                           NOW() - (%s || ' minutes')::interval, NOW() - (%s || ' minutes')::interval)""",
                (job_id, UID, status, json.dumps(PAYLOAD), minutes_old, minutes_old, minutes_old))
        conn.commit()
    finally:
        conn.close()


def age(job_id, minutes=60):
    q("UPDATE prostudio_generation_jobs SET heartbeat_at = NOW() - (%s || ' minutes')::interval, "
      "updated_at = NOW() - (%s || ' minutes')::interval WHERE id = %s", (minutes, minutes, job_id))


def state(job_id):
    job = q("SELECT status, result_json FROM prostudio_generation_jobs WHERE id=%s", (job_id,))[0]
    return {
        "job": job[0],
        "checkpoint": "completion_checkpoint" in (job[1] or {}),
        "reservation": q("SELECT status FROM generation_reservations WHERE generation_id=%s", (job_id,))[0][0],
        "charges": q("SELECT COUNT(*) FROM generation_charges WHERE generation_id=%s", (job_id,))[0][0],
        "outbox": q("SELECT COUNT(*) FROM prostudio_media_outbox WHERE job_id=%s", (job_id,))[0][0],
        "balance": q("SELECT balance FROM users WHERE telegram_id=%s", (UID,))[0][0],
    }


def assert_consistent(s):
    """Never failed with credits kept; never completed without its charge."""
    if s["job"] == "completed":
        assert s["charges"] == 1 and s["reservation"] == "charged", s
    if s["job"] == "failed":
        assert s["reservation"] in {"released", "refunded"}, s


@pytest.fixture
def worker(db, monkeypatch):
    calls = {"provider": 0, "failed_notice": 0, "telegram": 0}
    behaviour = {"mode": "ok"}
    monkeypatch.setattr(main, "PROSTUDIO_MOCK_GENERATION", False)
    monkeypatch.setattr(main, "optimize_prompt_for_model", lambda *a, **k: {"ok": True, "optimized": False})
    monkeypatch.setattr(main, "resolve_prostudio_provider_for_slot", lambda *a, **k: "OPENAI")
    monkeypatch.setattr(main, "circuit_before_request", lambda *a, **k: {"allowed": True})
    monkeypatch.setattr(main, "circuit_release_probe", lambda *a, **k: None)
    monkeypatch.setattr(main, "log_user_event", lambda *a, **k: None)
    monkeypatch.setattr(main, "save_generation", lambda *a, **k: None)
    monkeypatch.setattr(main, "save_prostudio_message", lambda *a, **k: "conv-1")
    monkeypatch.setattr(main, "record_character_generation_history", lambda *a, **k: None)
    monkeypatch.setattr(main.asyncio, "create_task", lambda coro: coro.close())

    async def telegram_sent(*a, **k):
        calls["telegram"] += 1
        return True

    async def failed_notice(*a, **k):
        calls["failed_notice"] += 1

    async def provider(*a, **k):
        calls["provider"] += 1
        if behaviour["mode"] == "timeout":
            raise asyncio.TimeoutError("provider timed out")
        if behaviour["mode"] == "error":
            return ({"ok": False, "error": "provider 500", "type": "image"}, "failed")
        return (dict(PROVIDER_RESULT), "completed")

    async def no_sleep(*a, **k):
        return None
    monkeypatch.setattr(main, "sync_completed_generation_to_telegram", telegram_sent)
    monkeypatch.setattr(main, "notify_telegram_generation_failed", failed_notice)
    monkeypatch.setattr(main, "run_prostudio_provider_request", provider)
    monkeypatch.setattr(main.asyncio, "sleep", no_sleep)
    return calls, behaviour


REAL_ENQUEUE = main.generation_storage.enqueue


def failing_enqueue(times):
    """generation_storage.enqueue raising a connection error `times` times."""
    real = REAL_ENQUEUE
    left = {"n": times}

    def enqueue(*a, **k):
        if left["n"] > 0:
            left["n"] -= 1
            raise psycopg2.OperationalError("synthetic: server closed the connection unexpectedly")
        return real(*a, **k)
    return enqueue


def run(job_id):
    asyncio.run(main.process_prostudio_generation(job_id, dict(PAYLOAD)))


# ------------------------------------------------------------------ success

def test_success_charges_once_with_the_completed_status_and_outbox(worker):
    calls, _ = worker
    new_job("ok")
    assert state("ok")["balance"] == START - PRICE  # held
    run("ok")
    s = state("ok")
    assert s == {"job": "completed", "checkpoint": False, "reservation": "charged", "charges": 1,
                 "outbox": 1, "balance": START - PRICE}
    assert calls["telegram"] == 1 and calls["failed_notice"] == 0
    result = q("SELECT result_json FROM prostudio_generation_jobs WHERE id='ok'")[0][0]
    assert result["balance_charged"] is True and result["balance_after"] == START - PRICE
    assert result["charge_id"] == "ok" and result["storage_status"] == "pending"


# --------------------------------------------------------------- DB errors

def test_transient_db_error_in_the_completion_write_is_retried_and_charged_once(worker, monkeypatch):
    calls, _ = worker
    monkeypatch.setattr(main.generation_storage, "enqueue", failing_enqueue(1))
    new_job("retry")
    run("retry")
    s = state("retry")
    assert s["job"] == "completed" and s["charges"] == 1 and s["balance"] == START - PRICE
    assert calls["failed_notice"] == 0 and calls["telegram"] == 1
    assert_consistent(s)


def test_persistent_db_error_keeps_the_result_and_charges_nothing_until_recovery(worker, monkeypatch):
    calls, _ = worker
    monkeypatch.setattr(main.generation_storage, "enqueue", failing_enqueue(99))
    new_job("defer")
    run("defer")
    s = state("defer")
    # The pre-fix code ended here with failed + charged + balance 80.
    assert s == {"job": "processing", "checkpoint": True, "reservation": "reserved", "charges": 0,
                 "outbox": 0, "balance": START - PRICE}
    assert calls["failed_notice"] == 0
    # The database recovers; the stale sweeper completes the job from its checkpoint.
    monkeypatch.setattr(main.generation_storage, "enqueue", REAL_ENQUEUE)
    age("defer")
    out = main.recover_stale_prostudio_job("defer")
    assert out["recovered"] is True and out["status"] == "completed"
    s = state("defer")
    assert s == {"job": "completed", "checkpoint": False, "reservation": "charged", "charges": 1,
                 "outbox": 1, "balance": START - PRICE}
    assert calls["provider"] == 1, "the provider is never asked again"


def test_db_error_with_no_checkpoint_fails_and_refunds_exactly_once(worker, monkeypatch):
    calls, _ = worker
    monkeypatch.setattr(main.generation_storage, "enqueue", failing_enqueue(99))
    monkeypatch.setattr(main, "checkpoint_prostudio_completion", lambda *a, **k: False)
    new_job("nockpt")
    run("nockpt")
    s = state("nockpt")
    assert s["job"] == "failed" and s["reservation"] == "released" and s["charges"] == 0
    assert s["balance"] == START and calls["failed_notice"] == 1
    assert main.update_prostudio_generation_job("nockpt", "failed", error={"ok": False}) is True
    assert state("nockpt")["balance"] == START, "a repeated failure does not refund twice"


def test_recovery_falls_back_to_failed_and_refund_when_the_checkpoint_cannot_complete(worker, monkeypatch):
    monkeypatch.setattr(main.generation_storage, "enqueue", failing_enqueue(99))
    new_job("stuck")
    run("stuck")
    age("stuck")
    out = main.recover_stale_prostudio_job("stuck")  # the database is still failing the completion
    s = state("stuck")
    assert out["recovered"] is True and out["status"] == "failed"
    assert s["job"] == "failed" and s["reservation"] == "released" and s["charges"] == 0 and s["balance"] == START


# ------------------------------------------------------- crash and restart

def test_worker_dies_after_the_checkpoint_and_the_restart_completes_the_job(worker, monkeypatch):
    calls, _ = worker

    def die(*a, **k):
        raise SystemExit("worker killed between checkpoint and completion")
    monkeypatch.setattr(main, "update_prostudio_generation_job", die)
    new_job("crash")
    with pytest.raises(SystemExit):
        run("crash")
    monkeypatch.undo()  # a fresh process: every real function back
    monkeypatch.setattr(main, "DATABASE_URL", DSN)
    monkeypatch.setattr(main, "db_connect", lambda *a, **k: _Conn())
    monkeypatch.setattr(main, "db_connection", _db_connection)
    import provider_concurrency
    monkeypatch.setattr(provider_concurrency, "db_connection", _db_connection)
    s = state("crash")
    assert s["job"] == "processing" and s["checkpoint"] and s["charges"] == 0 and s["reservation"] == "reserved"
    age("crash")
    main.requeue_stale_prostudio_jobs()
    s = state("crash")
    assert s == {"job": "completed", "checkpoint": False, "reservation": "charged", "charges": 1,
                 "outbox": 1, "balance": START - PRICE}


def test_a_pre_fix_charge_without_completion_is_refunded_once_by_recovery(db):
    """The old order (charge committed, completed never written) from a
    worker still running the previous release during the rollout."""
    new_job("legacy")
    assert main.charge_generation_balance(UID, "legacy", dict(PROVIDER_RESULT), dict(PAYLOAD))["charged"] is True
    assert state("legacy")["balance"] == START - PRICE
    age("legacy")
    out = main.recover_stale_prostudio_job("legacy")
    s = state("legacy")
    assert out["recovered"] is True and out["refunded_credits"] == PRICE
    assert s["job"] == "failed" and s["reservation"] == "refunded" and s["balance"] == START
    assert s["charges"] == 1, "the charge row stays as the audit record"
    assert main.recover_stale_prostudio_job("legacy")["recovered"] is False
    assert main.update_prostudio_generation_job("legacy", "failed", error={"ok": False}) is True
    assert state("legacy")["balance"] == START, "never refunded twice"


def test_pre_fix_charged_job_failed_by_its_own_worker_is_refunded_once(db):
    new_job("legacy2")
    main.charge_generation_balance(UID, "legacy2", dict(PROVIDER_RESULT), dict(PAYLOAD))
    assert main.update_prostudio_generation_job("legacy2", "failed", error={"ok": False}) is True
    assert main.update_prostudio_generation_job("legacy2", "failed", error={"ok": False}) is True
    s = state("legacy2")
    assert s["job"] == "failed" and s["reservation"] == "refunded" and s["balance"] == START


# ------------------------------------------------------- refusals / provider

def test_insufficient_balance_at_settlement_fails_and_releases_the_hold(worker, monkeypatch):
    calls, _ = worker
    new_job("short", reserve=5)  # held 5, final price 20, nothing left to debit the rest
    q("UPDATE users SET balance = 0 WHERE telegram_id=%s", (UID,))
    q("UPDATE user_credit_wallets SET purchased_credits = 0, subscription_credits = 0 WHERE telegram_id=%s", (UID,))
    run("short")
    s = state("short")
    assert s["job"] == "failed" and s["reservation"] == "released" and s["charges"] == 0
    assert s["balance"] == 5 and calls["failed_notice"] == 1


@pytest.mark.parametrize("mode", ["error", "timeout"])
def test_provider_error_or_timeout_fails_and_refunds_once(worker, mode):
    calls, behaviour = worker
    behaviour["mode"] = mode
    new_job("p-" + mode)
    run("p-" + mode)
    s = state("p-" + mode)
    assert s["job"] == "failed" and s["reservation"] == "released" and s["charges"] == 0 and s["balance"] == START
    assert calls["provider"] == 1 and calls["failed_notice"] == 1


# ----------------------------------------------------------- repeats

def test_repeated_completion_and_late_failure_change_nothing(worker):
    new_job("rep")
    run("rep")
    settle = main.queued_job_charge(UID, "rep", dict(PROVIDER_RESULT), dict(PAYLOAD))
    assert main.update_prostudio_generation_job("rep", "completed", result={"ok": True, "type": "image"}, settle=settle) is True
    assert settle.outcome == {}, "a re-affirmed completion does not settle again"
    assert main.charge_generation_balance(UID, "rep", {}, dict(PAYLOAD)).get("already_charged") is True
    assert main.update_prostudio_generation_job("rep", "failed", error={"ok": False}) is False
    assert main.complete_prostudio_job_from_checkpoint(
        "rep", UID, {"result": main.build_completed_job_result(dict(PROVIDER_RESULT), "image"),
                     "price_snapshot": {"final_credits": PRICE}}) is True
    s = state("rep")
    assert s["job"] == "completed" and s["charges"] == 1 and s["balance"] == START - PRICE


# ----------------------------------------------------------- concurrency

def _parallel(n, target):
    barrier = threading.Barrier(n)
    errors = []

    def body(i):
        try:
            barrier.wait()
            target(i)
        except Exception as exc:  # pragma: no cover - reported below
            errors.append(exc)
    threads = [threading.Thread(target=body, args=(i,)) for i in range(n)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert not errors, errors


def test_parallel_completions_of_one_job_charge_once(db):
    new_job("par")
    main.checkpoint_prostudio_completion("par", main.build_completed_job_result(dict(PROVIDER_RESULT), "image"), dict(PAYLOAD))
    checkpoint = q("SELECT result_json FROM prostudio_generation_jobs WHERE id='par'")[0][0]["completion_checkpoint"]

    def complete(_i):
        main.complete_prostudio_job_from_checkpoint("par", UID, checkpoint)
    _parallel(6, complete)
    s = state("par")
    assert s["job"] == "completed" and s["charges"] == 1 and s["balance"] == START - PRICE and s["outbox"] == 1


def test_worker_completion_racing_stale_recovery_stays_consistent(db):
    for i in range(8):
        job_id = "race-%d" % i
        q("UPDATE users SET balance = %s WHERE telegram_id=%s", (START, UID))
        q("UPDATE user_credit_wallets SET purchased_credits = %s, subscription_credits = 0 WHERE telegram_id=%s",
          (START, UID))
        new_job(job_id)
        age(job_id)
        settle = main.queued_job_charge(UID, job_id, dict(PROVIDER_RESULT), dict(PAYLOAD))
        result = main.build_completed_job_result(dict(PROVIDER_RESULT), "image")

        def act(k):
            if k == 0:
                main.update_prostudio_generation_job(job_id, "completed", result=dict(result), settle=settle)
            else:
                main.recover_stale_prostudio_job(job_id)
        _parallel(2, act)
        s = state(job_id)
        assert_consistent(s)
        assert s["balance"] == (START - PRICE if s["job"] == "completed" else START), s


# ------------------------------------------- late provider results (Kling case)
#
# A video job waits on its provider in provider_processing. The 480 s hard
# limit failed it and refunded the hold, then Kling reported "succeed" with a
# ready MP4 that SYLVEX never delivered: the failed write had also replaced
# result_json, discarding the provider task id.

KLING_PENDING = {"ok": True, "type": "video", "status": "provider_processing", "provider": "kling",
                 "model": "kling-v2-master", "task_id": "kling-task-1",
                 "poll_url": "https://api-singapore.klingai.com/v1/videos/text2video/kling-task-1"}
KLING_DONE = {"ok": True, "type": "video", "status": "completed", "provider": "kling", "model": "kling-v2-master",
              "task_id": "kling-task-1", "video_url": "https://cdn.klingai.test/out.mp4",
              "videos": ["https://cdn.klingai.test/out.mp4"]}
VIDEO_PAYLOAD = dict(PAYLOAD, mode="video", model="kling-v2-master", provider="kling", prompt="A wave")


@pytest.fixture
def late(worker, monkeypatch):
    """Provider polls, R2 persistence and post-completion delivery stubbed;
    the job table, billing, outbox and delivery bookkeeping are real."""
    calls, _ = worker
    calls.update(polls=0, history=0)
    poll_answer = {"value": dict(KLING_DONE)}

    async def poll_video_generation(ref):
        calls["polls"] += 1
        assert ref.get("task_id") == "kling-task-1"
        return dict(poll_answer["value"])

    def history(*a, **k):
        calls["history"] += 1
        return "conv-late"
    monkeypatch.setattr(main, "poll_video_generation", poll_video_generation)
    monkeypatch.setattr(main, "save_prostudio_message", history)
    monkeypatch.setattr(main, "_persist_outbox_media", lambda entry, verify_only=False: "https://cdn.sylvex.ai/" + entry["key"])
    monkeypatch.setattr(main, "verify_persisted_generation_media", lambda result, mode: result)
    return calls, poll_answer


def video_job_in_provider_processing(job_id):
    new_job(job_id)
    q("UPDATE prostudio_generation_jobs SET mode='video', request_json=%s::jsonb WHERE id=%s",
      (json.dumps(VIDEO_PAYLOAD), job_id))
    assert main.update_prostudio_generation_job(job_id, "provider_processing", result=dict(KLING_PENDING)) is True


def hard_timeout(job_id):
    """The exact write run_prostudio_generation_with_timeout makes at 480 s."""
    return main.update_prostudio_generation_job(job_id, "failed", error={
        "ok": False, "error_code": "generation_timeout",
        "error": "Generation exceeded the Pro Studio hard runtime limit"})


def watch(job_id):
    return (q("SELECT error_json FROM prostudio_generation_jobs WHERE id=%s", (job_id,))[0][0] or {}).get("late_result_watch")


REAL_CREATE_TASK = asyncio.create_task


def drain_outbox():
    """Run the real R2 outbox once over every pending job (the worker fixture
    stubs asyncio.create_task; the outbox needs the real one)."""
    queue = main._media_outbox()
    outcomes = []
    stub, main.asyncio.create_task = main.asyncio.create_task, REAL_CREATE_TASK
    try:
        while True:
            job = queue.claim()
            if not job:
                return outcomes
            outcomes.append(asyncio.run(main._run_media_outbox_claim(queue, job)))
    finally:
        main.asyncio.create_task = stub


def test_timeout_keeps_the_provider_task_and_a_late_result_is_delivered_free(late):
    calls, _ = late
    video_job_in_provider_processing("kling-1")
    assert hard_timeout("kling-1") is True
    s = state("kling-1")
    assert s["job"] == "failed" and s["reservation"] == "released" and s["balance"] == START
    w = watch("kling-1")
    assert w["provider_ref"]["task_id"] == "kling-task-1" and w["done"] is False

    assert asyncio.run(main.collect_late_provider_results()) == 1
    s = state("kling-1")
    # Completed with the late MP4, nothing charged after the refund.
    assert s == {"job": "completed", "checkpoint": False, "reservation": "released", "charges": 0,
                 "outbox": 1, "balance": START}
    result = q("SELECT result_json FROM prostudio_generation_jobs WHERE id='kling-1'")[0][0]
    assert result["late_delivery"] is True and result["balance_charged"] is False and result["cost_credits"] == 0
    assert result["delivery_pending"] is True and calls["telegram"] == 0  # after R2, not before
    assert watch("kling-1")["done"] is True and watch("kling-1")["delivered"] is True

    assert drain_outbox() == ["completed"]
    result = q("SELECT result_json, conversation_id FROM prostudio_generation_jobs WHERE id='kling-1'")[0]
    assert result[0]["video_url"].startswith("https://cdn.sylvex.ai/") and result[0]["storage_status"] == "completed"
    assert "delivery_pending" not in result[0] and result[1] == "conv-late"
    assert calls["history"] == 1 and calls["telegram"] == 1
    # Nothing is delivered or charged twice.
    assert asyncio.run(main.deliver_pending_prostudio_job("kling-1")) is False
    assert asyncio.run(main.collect_late_provider_results()) == 0
    assert calls["history"] == 1 and calls["telegram"] == 1 and calls["polls"] == 1
    assert state("kling-1")["balance"] == START and state("kling-1")["charges"] == 0


def test_a_task_still_running_is_polled_again_later_and_a_failing_one_stops(late, monkeypatch):
    calls, answer = late
    video_job_in_provider_processing("kling-2")
    hard_timeout("kling-2")
    answer["value"] = dict(KLING_PENDING, status="processing")
    assert asyncio.run(main.collect_late_provider_results()) == 0
    w = watch("kling-2")
    assert w["done"] is False and w["next_poll_at"] > time_now() and w["claimed_until"] == 0
    assert asyncio.run(main.collect_late_provider_results()) == 0 and calls["polls"] == 1, "waits for next_poll_at"
    answer["value"] = {"ok": False, "status": "failed", "error": "kling task failed"}
    for _ in range(5):
        q("""UPDATE prostudio_generation_jobs SET error_json = jsonb_set(error_json, '{late_result_watch,next_poll_at}', '0')
             WHERE id='kling-2'""")
        asyncio.run(main.collect_late_provider_results())
    assert watch("kling-2")["done"] is True and watch("kling-2")["outcome"] == "provider_failed"
    assert state("kling-2")["job"] == "failed" and state("kling-2")["balance"] == START


def time_now():
    import time
    return time.time()


def test_only_timeouts_of_accepted_provider_tasks_are_watched(late):
    video_job_in_provider_processing("kling-err")
    main.update_prostudio_generation_job("kling-err", "failed", error={"ok": False, "error": "provider 500"})
    assert watch("kling-err") is None
    new_job("queued-timeout")
    hard_timeout("queued-timeout")
    assert watch("queued-timeout") is None, "no provider task was ever accepted"
    assert asyncio.run(main.collect_late_provider_results()) == 0 and late[0]["polls"] == 0


def test_an_expired_watch_is_not_polled(late):
    video_job_in_provider_processing("kling-old")
    hard_timeout("kling-old")
    q("""UPDATE prostudio_generation_jobs SET error_json = jsonb_set(error_json, '{late_result_watch,expires_at}', '1')
         WHERE id='kling-old'""")
    assert asyncio.run(main.collect_late_provider_results()) == 0 and late[0]["polls"] == 0


def test_parallel_late_passes_deliver_once(late):
    video_job_in_provider_processing("kling-par")
    hard_timeout("kling-par")
    _parallel(4, lambda _i: asyncio.run(main.collect_late_provider_results()))
    s = state("kling-par")
    assert s["job"] == "completed" and s["outbox"] == 1 and s["charges"] == 0 and s["balance"] == START
    assert late[0]["polls"] == 1, "one claim, one provider poll"
    assert main.deliver_late_provider_result("kling-par", "video", dict(KLING_DONE)) is False


def test_worker_crash_while_polling_then_stale_recovery_keeps_the_task_for_late_delivery(late):
    calls, _ = late
    video_job_in_provider_processing("kling-crash")
    age("kling-crash")
    out = main.recover_stale_prostudio_job("kling-crash")
    assert out["recovered"] is True and out["status"] == "failed" and state("kling-crash")["balance"] == START
    assert watch("kling-crash")["provider_ref"]["task_id"] == "kling-task-1"
    assert asyncio.run(main.collect_late_provider_results()) == 1
    drain_outbox()
    s = state("kling-crash")
    assert s["job"] == "completed" and s["charges"] == 0 and s["balance"] == START
    assert calls["history"] == 1 and calls["telegram"] == 1


def test_completion_from_a_checkpoint_after_a_crash_reaches_history_and_telegram(late, monkeypatch):
    calls, _ = late
    monkeypatch.setattr(main.generation_storage, "enqueue", failing_enqueue(99))
    new_job("ckpt-deliver")
    run("ckpt-deliver")  # the completion cannot commit: deferred to recovery
    assert state("ckpt-deliver")["job"] == "processing" and calls["telegram"] == 0
    monkeypatch.setattr(main.generation_storage, "enqueue", REAL_ENQUEUE)
    age("ckpt-deliver")
    main.requeue_stale_prostudio_jobs()
    s = state("ckpt-deliver")
    assert s["job"] == "completed" and s["charges"] == 1 and s["balance"] == START - PRICE
    drain_outbox()
    result = q("SELECT result_json, conversation_id FROM prostudio_generation_jobs WHERE id='ckpt-deliver'")[0]
    assert "delivery_pending" not in result[0] and result[1] == "conv-late"
    assert calls["history"] == 1 and calls["telegram"] == 1
    assert state("ckpt-deliver")["charges"] == 1, "still one charge"


def test_a_normal_completion_is_delivered_once_by_its_worker_only(late):
    calls, _ = late
    new_job("normal")
    run("normal")
    assert calls["history"] == 1 and calls["telegram"] == 1
    drain_outbox()
    assert calls["history"] == 1 and calls["telegram"] == 1, "the outbox does not deliver it again"
    assert state("normal")["charges"] == 1
