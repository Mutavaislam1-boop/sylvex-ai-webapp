"""_recover_stale_prostudio_job_once must never fail a job that still has a
live provider_slot lease (a job that's genuinely still running always
renews one), and must fail+refund a genuinely abandoned job (crashed or
redeployed worker, lease already gone) once it's past the stale threshold -
this is what stands between "one crash" and "a video stuck forever" or
"credits charged for nothing"."""
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent / "support"))


def _pglite_available():
    return bool(os.getenv("SYLVEX_TEST_NODE") and os.getenv("SYLVEX_PGLITE_MODULE"))


pytestmark = pytest.mark.skipif(
    not _pglite_available(),
    reason="Set SYLVEX_TEST_NODE and SYLVEX_PGLITE_MODULE to run real-SQL job recovery tests",
)


@pytest.fixture
def db(monkeypatch):
    from pglite_adapter import Database
    import main

    database = Database()

    monkeypatch.setattr(main, "DATABASE_URL", "pglite://test")
    monkeypatch.setattr(main, "db_connect", lambda *a, **k: database.connect())
    monkeypatch.setattr(main, "ensure_prostudio_table", lambda: None)
    monkeypatch.setattr(main, "ensure_reservations", lambda connect: None)
    monkeypatch.setattr(main, "ensure_provider_slot_table", lambda database_url: None)

    with database.connect() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE prostudio_generation_jobs (
                    id TEXT PRIMARY KEY, status TEXT NOT NULL, provider TEXT,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    heartbeat_at TIMESTAMPTZ, locked_at TIMESTAMPTZ,
                    provider_wait_until TIMESTAMPTZ, completed_at TIMESTAMPTZ,
                    error_json JSONB, result_json JSONB
                )
            """)
            cur.execute("""
                CREATE TABLE prostudio_provider_slots (
                    provider TEXT NOT NULL, job_id TEXT NOT NULL, worker_id TEXT NOT NULL,
                    acquired_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    heartbeat_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    lease_until TIMESTAMPTZ NOT NULL
                )
            """)
            cur.execute("CREATE TABLE generation_charges (generation_id TEXT PRIMARY KEY)")
            cur.execute("""
                CREATE TABLE generation_reservations (
                    generation_id TEXT PRIMARY KEY, telegram_id BIGINT NOT NULL,
                    credits INTEGER NOT NULL, status TEXT NOT NULL DEFAULT 'reserved'
                )
            """)
            cur.execute("CREATE TABLE users (telegram_id BIGINT PRIMARY KEY, balance INTEGER NOT NULL DEFAULT 0)")
            cur.execute("INSERT INTO users (telegram_id, balance) VALUES (101, 0)")
            cur.execute("INSERT INTO generation_reservations (generation_id, telegram_id, credits) VALUES ('job-1', 101, 20)")

    yield database, main
    database.close()


def _insert_job(db, job_id, status, age_minutes):
    with db.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO prostudio_generation_jobs (id, status, provider, created_at, updated_at, heartbeat_at)
                VALUES (%s, %s, 'kling', NOW() - (%s || ' minutes')::interval,
                        NOW() - (%s || ' minutes')::interval, NOW() - (%s || ' minutes')::interval)
                """,
                (job_id, status, age_minutes, age_minutes, age_minutes),
            )


def _insert_live_slot(db, job_id, lease_seconds_remaining):
    with db.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO prostudio_provider_slots (provider, job_id, worker_id, lease_until) "
                "VALUES ('kling', %s, 'worker-a', NOW() + (%s || ' seconds')::interval)",
                (job_id, lease_seconds_remaining),
            )


def test_job_with_live_slot_is_never_recovered_no_matter_how_old(db):
    database, main = db
    _insert_job(database, "job-1", "provider_processing", age_minutes=60)
    _insert_live_slot(database, "job-1", lease_seconds_remaining=60)

    outcome = main._recover_stale_prostudio_job_once("job-1")

    assert outcome["recovered"] is False
    assert outcome["reason"] == "live_provider_slot"
    with database.connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT status FROM prostudio_generation_jobs WHERE id='job-1'")
            assert cur.fetchone() == ["provider_processing"]
            cur.execute("SELECT balance FROM users WHERE telegram_id=101")
            assert cur.fetchone() == [0], "credits must stay reserved for a genuinely live job"


def test_job_within_threshold_and_no_slot_is_left_alone(db):
    database, main = db
    _insert_job(database, "job-1", "provider_processing", age_minutes=2)
    # No slot row at all - simulates a job whose dispatch attempt hasn't
    # reached the poll phase yet, well within the stale threshold.

    outcome = main._recover_stale_prostudio_job_once("job-1")

    assert outcome["recovered"] is False
    assert outcome["reason"] == "heartbeat_fresh"


def test_abandoned_job_past_threshold_with_no_live_slot_is_recovered(db):
    database, main = db
    _insert_job(database, "job-1", "provider_processing", age_minutes=10)
    # The lease already expired (in the past) - the DELETE inside recovery
    # will reap it, leaving no live slot.
    with database.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO prostudio_provider_slots (provider, job_id, worker_id, lease_until) "
                "VALUES ('kling', 'job-1', 'worker-a', NOW() - interval '5 minutes')"
            )

    outcome = main._recover_stale_prostudio_job_once("job-1", force=False)

    assert outcome["recovered"] is True
    assert outcome["reason"] == "stale_worker_recovered"
    with database.connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT status FROM prostudio_generation_jobs WHERE id='job-1'")
            assert cur.fetchone() == ["failed"]
            cur.execute("SELECT status FROM generation_reservations WHERE generation_id='job-1'")
            assert cur.fetchone() == ["released"]
            cur.execute("SELECT balance FROM users WHERE telegram_id=101")
            assert cur.fetchone() == [20], "the reserved credits must be refunded, not lost"
