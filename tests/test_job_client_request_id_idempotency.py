"""create_prostudio_generation_job must treat a repeated client_request_id
as an idempotent replay (reload, reconnect, retried POST after a dropped
response) and hand back the existing job instead of creating - and
charging for - a second one. The Mini App frontend already generates and
sends a fresh client_request_id on every callGenerate() call; this is the
backend half of that contract for image/video/music/voice job creation."""
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent / "support"))


def _pglite_available():
    return bool(os.getenv("SYLVEX_TEST_NODE") and os.getenv("SYLVEX_PGLITE_MODULE"))


pytestmark = pytest.mark.skipif(
    not _pglite_available(),
    reason="Set SYLVEX_TEST_NODE and SYLVEX_PGLITE_MODULE to run real-SQL tests",
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
                    id TEXT PRIMARY KEY, telegram_id BIGINT, status TEXT NOT NULL,
                    conversation_id TEXT, mode TEXT, model TEXT, provider TEXT, prompt TEXT,
                    request_json JSONB, response_json JSONB, result_json JSONB, error_json JSONB,
                    cost INTEGER DEFAULT 0,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    completed_at TIMESTAMPTZ
                )
            """)
            cur.execute("CREATE TABLE generation_reservations (generation_id TEXT PRIMARY KEY, telegram_id BIGINT NOT NULL, credits INTEGER NOT NULL, status TEXT NOT NULL DEFAULT 'reserved')")
            cur.execute("CREATE TABLE users (telegram_id BIGINT PRIMARY KEY, balance INTEGER NOT NULL DEFAULT 0)")
            cur.execute("INSERT INTO users (telegram_id, balance) VALUES (777, 1000)")

    yield database, main
    database.close()


def test_duplicate_client_request_id_returns_the_same_job_not_a_second_one(db, monkeypatch):
    database, main = db
    monkeypatch.setattr(main, "calculate_generation_price", lambda payload: {"price_snapshot": {"final_credits": 5}})

    payload = {
        "telegram_id": 777, "mode": "image", "model": "ideogram_3_0",
        "provider": "ideogram", "prompt": "cat", "client_request_id": "replay-abc",
    }
    first_job_id = main.create_prostudio_generation_job(dict(payload))
    second_job_id = main.create_prostudio_generation_job(dict(payload))

    assert first_job_id == second_job_id, "a repeated client_request_id must never create a second job"

    with database.connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM prostudio_generation_jobs WHERE telegram_id=777")
            assert cur.fetchone()[0] == 1

    with database.connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT credits FROM generation_reservations WHERE generation_id=%s", (first_job_id,))
            row = cur.fetchone()
            assert row is not None, "the original reservation must exist exactly once"


def test_different_client_request_ids_create_separate_jobs_after_the_first_completes(db, monkeypatch):
    database, main = db
    monkeypatch.setattr(main, "calculate_generation_price", lambda payload: {"price_snapshot": {"final_credits": 5}})

    first_id = main.create_prostudio_generation_job({
        "telegram_id": 777, "mode": "image", "model": "m", "provider": "p",
        "prompt": "a", "client_request_id": "req-1",
    })
    with database.connect() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE prostudio_generation_jobs SET status='completed' WHERE id=%s", (first_id,))

    second_id = main.create_prostudio_generation_job({
        "telegram_id": 777, "mode": "image", "model": "m", "provider": "p",
        "prompt": "b", "client_request_id": "req-2",
    })

    assert second_id != first_id
    with database.connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM prostudio_generation_jobs WHERE telegram_id=777")
            assert cur.fetchone()[0] == 2
