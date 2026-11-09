"""B15 probe: provider failures, terminal states, refunds and recovery on the
real application schema (ensure_* of the code itself) in a throwaway local
PostgreSQL. Not part of the repository; no Production access."""
import asyncio
import json
import os
from contextlib import contextmanager

import psycopg2
import pytest

import main

DSN = os.environ["B15_PROBE_DSN"]
UID = 4242
PRICE = 20
START_BALANCE = 100


@pytest.fixture
def db(monkeypatch):
    admin = psycopg2.connect(DSN)
    admin.autocommit = True
    with admin.cursor() as cur:
        cur.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public")
        # users is created by the bot in the shared database (app/database/db.py, b7e1b90)
        cur.execute("""CREATE TABLE users (id SERIAL PRIMARY KEY, telegram_id BIGINT UNIQUE, username TEXT,
                       first_name TEXT, balance INTEGER DEFAULT 0, subscription TEXT DEFAULT 'Free', created_at TEXT)""")
        cur.execute("INSERT INTO users (telegram_id, first_name, balance) VALUES (%s, 'probe', %s)", (UID, START_BALANCE))
    admin.close()
    monkeypatch.setattr(main, "DATABASE_URL", DSN)
    monkeypatch.setattr(main, "_PROSTUDIO_SCHEMA_READY", False)
    main.ensure_prostudio_table()
    main.ensure_reservations(lambda: main.db_connect(DSN))
    import provider_concurrency
    monkeypatch.setattr(provider_concurrency, "_SCHEMA_READY", False)
    provider_concurrency.ensure_provider_slot_table(DSN)
    yield DSN


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


def new_job(job_id, status="processing", mode="image", minutes_old=0):
    conn = main.db_connect(DSN)
    try:
        with conn.cursor() as cur:
            main.reserve_generation(cur, UID, job_id, PRICE)
            cur.execute(
                """INSERT INTO prostudio_generation_jobs (id, telegram_id, status, mode, request_json,
                       created_at, updated_at, heartbeat_at)
                   VALUES (%s, %s, %s, %s, %s::jsonb, NOW() - (%s || ' minutes')::interval,
                           NOW() - (%s || ' minutes')::interval, NOW() - (%s || ' minutes')::interval)""",
                (job_id, UID, status, mode, json.dumps(PAYLOAD), minutes_old, minutes_old, minutes_old))
        conn.commit()
    finally:
        conn.close()


def balance():
    return q("SELECT balance FROM users WHERE telegram_id=%s", (UID,))[0][0]


def job(job_id):
    return q("SELECT status FROM prostudio_generation_jobs WHERE id=%s", (job_id,))[0][0]


def reservation(job_id):
    return q("SELECT status FROM generation_reservations WHERE generation_id=%s", (job_id,))[0][0]


def charges(job_id):
    return q("SELECT COUNT(*) FROM generation_charges WHERE generation_id=%s", (job_id,))[0][0]


PAYLOAD = {"telegram_id": UID, "mode": "image", "prompt": "A portrait", "model": "gpt-image-2",
           "provider": "openai", "price_snapshot": {"final_credits": PRICE}, "image_options": {"count": 1}}


@pytest.fixture
def worker(db, monkeypatch):
    """process_prostudio_generation with only the outside world stubbed:
    the provider, Telegram, history and prompt optimisation. Billing, job
    updates, the outbox and the database are the real code."""
    calls = {"provider": 0, "failed_notice": 0}
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
        return True

    async def failed_notice(*a, **k):
        calls["failed_notice"] += 1
    monkeypatch.setattr(main, "sync_completed_generation_to_telegram", telegram_sent)
    monkeypatch.setattr(main, "notify_telegram_generation_failed", failed_notice)
    behaviour = {"mode": "ok"}

    async def provider(*a, **k):
        calls["provider"] += 1
        if behaviour["mode"] == "timeout":
            raise asyncio.TimeoutError("provider timed out")
        if behaviour["mode"] == "error":
            return ({"ok": False, "error": "provider 500", "type": "image"}, "failed")
        return ({"ok": True, "type": "image", "status": "completed", "image_url": "https://cdn.example.test/r.png",
                 "images": ["https://cdn.example.test/r.png"], "provider": "openai", "model": "gpt-image-2"}, "completed")
    monkeypatch.setattr(main, "run_prostudio_provider_request", provider)
    return calls, behaviour


# ---------------------------------------------------------------- controls

def test_success_charges_once_and_completes(worker):
    calls, _ = worker
    new_job("ok-1")
    assert balance() == START_BALANCE - PRICE  # held
    asyncio.run(main.process_prostudio_generation("ok-1", dict(PAYLOAD)))
    assert job("ok-1") == "completed" and reservation("ok-1") == "charged" and charges("ok-1") == 1
    assert balance() == START_BALANCE - PRICE
    again = main.charge_generation_balance(UID, "ok-1", {}, dict(PAYLOAD))
    assert again.get("already_charged") and charges("ok-1") == 1 and balance() == START_BALANCE - PRICE


@pytest.mark.parametrize("mode", ["error", "timeout"])
def test_provider_error_or_timeout_fails_and_refunds_once(worker, mode):
    calls, behaviour = worker
    behaviour["mode"] = mode
    new_job("fail-" + mode)
    asyncio.run(main.process_prostudio_generation("fail-" + mode, dict(PAYLOAD)))
    assert job("fail-" + mode) == "failed" and reservation("fail-" + mode) == "released"
    assert charges("fail-" + mode) == 0 and balance() == START_BALANCE
    assert calls["provider"] == 1, "no automatic re-dispatch of a failed provider request"
    assert calls["failed_notice"] == 1
    # a duplicate failure callback does not refund again
    assert main.update_prostudio_generation_job("fail-" + mode, "failed", error={"ok": False, "error": "dup"}) is True
    assert balance() == START_BALANCE


def test_terminal_states_cannot_be_overwritten(db):
    new_job("t-failed")
    assert main.update_prostudio_generation_job("t-failed", "failed", error={"ok": False}) is True
    assert main.update_prostudio_generation_job("t-failed", "completed", result={"ok": True, "image_url": "https://x/y.png"}) is False
    assert job("t-failed") == "failed" and balance() == START_BALANCE
    new_job("t-done", mode="text")
    assert main.update_prostudio_generation_job("t-done", "completed", result={"ok": True, "type": "text", "text": "hi"}) is True
    assert main.update_prostudio_generation_job("t-done", "failed", error={"ok": False}) is False
    assert job("t-done") == "completed"


def test_stale_recovery_refunds_abandoned_job_and_spares_live_one(db):
    new_job("stale-1", status="provider_processing", minutes_old=60)
    out = main._recover_stale_prostudio_job_once("stale-1")
    assert out["recovered"] is True and job("stale-1") == "failed" and reservation("stale-1") == "released"
    assert balance() == START_BALANCE
    new_job("live-1", status="provider_processing", minutes_old=60)
    q("INSERT INTO prostudio_provider_slots (provider, job_id, worker_id, lease_until) VALUES ('openai','live-1','w', NOW() + interval '60 seconds')")
    out = main._recover_stale_prostudio_job_once("live-1")
    assert out["recovered"] is False and out["reason"] == "live_provider_slot" and job("live-1") == "provider_processing"


# ------------------------------------------------ the charged-but-failed window

def test_db_error_on_completion_write_after_charge(worker, monkeypatch, capsys):
    """The charge commits in its own transaction; then the completion
    transaction hits a database error (here: inside the outbox insert)."""
    real_enqueue = main.generation_storage.enqueue

    def failing_enqueue(*a, **k):
        raise psycopg2.OperationalError("synthetic: server closed the connection unexpectedly")
    monkeypatch.setattr(main.generation_storage, "enqueue", failing_enqueue)
    new_job("win-1")
    asyncio.run(main.process_prostudio_generation("win-1", dict(PAYLOAD)))
    monkeypatch.setattr(main.generation_storage, "enqueue", real_enqueue)
    state = {"job": job("win-1"), "reservation": reservation("win-1"), "charges": charges("win-1"),
             "balance": balance(), "failed_notice": worker[0]["failed_notice"]}
    print("B15_WINDOW_DB_ERROR", json.dumps(state))
    # Correct outcome: either completed (and charged) or failed (and refunded).
    assert not (state["job"] == "failed" and state["charges"] == 1), state


def test_crash_after_charge_then_stale_recovery(db, capsys):
    """Worker dies after settle_generation committed and before the completed
    write; the stale sweeper later recovers the job."""
    new_job("win-2", status="processing", minutes_old=0)
    charged = main.charge_generation_balance(UID, "win-2", {"ok": True}, dict(PAYLOAD))
    assert charged.get("charged") is True
    q("UPDATE prostudio_generation_jobs SET heartbeat_at = NOW() - interval '60 minutes', updated_at = NOW() - interval '60 minutes' WHERE id='win-2'")
    out = main._recover_stale_prostudio_job_once("win-2")
    state = {"recovered": out.get("recovered"), "has_charge_logged": out.get("has_charge"), "job": job("win-2"),
             "reservation": reservation("win-2"), "charges": charges("win-2"), "balance": balance()}
    print("B15_WINDOW_CRASH", json.dumps(state))
    assert not (state["job"] == "failed" and state["charges"] == 1), state
