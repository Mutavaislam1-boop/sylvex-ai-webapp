"""update_prostudio_generation_job must never let a late/duplicate callback
overwrite a job that has already reached a terminal state (completed or
failed) - otherwise a straggling poll response arriving after stale-job
recovery already failed+refunded a job could "revive" it as completed,
or a delayed retry could quietly flip an already-completed result."""
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent / "support"))


def _pglite_available():
    return bool(os.getenv("SYLVEX_TEST_NODE") and os.getenv("SYLVEX_PGLITE_MODULE"))


pytestmark = pytest.mark.skipif(
    not _pglite_available(),
    reason="Set SYLVEX_TEST_NODE and SYLVEX_PGLITE_MODULE to run real-SQL job lifecycle tests",
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

    with database.connect() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE prostudio_generation_jobs (
                    id TEXT PRIMARY KEY, status TEXT NOT NULL, conversation_id TEXT,
                    response_json JSONB, result_json JSONB, error_json JSONB,
                    cost INTEGER DEFAULT 0,
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    completed_at TIMESTAMPTZ
                )
            """)
            cur.execute("CREATE TABLE generation_reservations (generation_id TEXT PRIMARY KEY, telegram_id BIGINT NOT NULL, credits INTEGER NOT NULL, status TEXT NOT NULL DEFAULT 'reserved')")
            cur.execute("CREATE TABLE users (telegram_id BIGINT PRIMARY KEY, balance INTEGER NOT NULL DEFAULT 0)")
            cur.execute("INSERT INTO users (telegram_id, balance) VALUES (101, 0)")

    yield database, main
    database.close()


def _insert_job(db, job_id, status):
    with db.connect() as conn:
        with conn.cursor() as cur:
            cur.execute("INSERT INTO prostudio_generation_jobs (id, status) VALUES (%s, %s)", (job_id, status))


def _job_status(db, job_id):
    with db.connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT status FROM prostudio_generation_jobs WHERE id=%s", (job_id,))
            return cur.fetchone()[0]


def test_late_completed_callback_cannot_revive_a_failed_job(db):
    database, main = db
    _insert_job(database, "job-1", "failed")

    updated = main.update_prostudio_generation_job("job-1", "completed", result={"ok": True, "video_url": "https://example.com/v.mp4"})

    assert updated is False, "a late success callback must not overwrite a job already marked failed"
    assert _job_status(database, "job-1") == "failed"


def test_late_failed_callback_cannot_override_a_completed_job(db):
    database, main = db
    _insert_job(database, "job-1", "completed")

    updated = main.update_prostudio_generation_job("job-1", "failed", error={"ok": False, "error": "late timeout"})

    assert updated is False
    assert _job_status(database, "job-1") == "completed"


def test_reaffirming_the_same_terminal_status_is_allowed(db):
    database, main = db
    _insert_job(database, "job-1", "completed")

    updated = main.update_prostudio_generation_job("job-1", "completed", result={"ok": True, "video_url": "https://example.com/v2.mp4"})

    assert updated is True

    with database.connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT status, result_json FROM prostudio_generation_jobs WHERE id='job-1'")
            row = cur.fetchone()
            assert row[0] == "completed"


def test_non_terminal_to_terminal_transition_still_works(db):
    database, main = db
    _insert_job(database, "job-1", "provider_processing")
    with database.connect() as conn:
        with conn.cursor() as cur:
            cur.execute("INSERT INTO generation_reservations (generation_id, telegram_id, credits) VALUES ('job-1', 101, 15)")

    updated = main.update_prostudio_generation_job("job-1", "failed", error={"ok": False, "error": "provider error"})

    assert updated is True
    assert _job_status(database, "job-1") == "failed"
    with database.connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT balance FROM users WHERE telegram_id=101")
            assert cur.fetchone() == [15], "moving into failed must still release the reservation"
