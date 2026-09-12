"""_merge_prostudio_storage_result may only ever update a completed job's
media URLs and storage_status - it must never touch the status column,
and it must never clobber fields another writer (history) already
committed to result_json (read-merge-write under a row lock, not a
blind overwrite from a stale in-memory copy)."""
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

    with database.connect() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE prostudio_generation_jobs (
                    id TEXT PRIMARY KEY, status TEXT NOT NULL, result_json JSONB
                )
            """)

    yield database, main
    database.close()


def _insert_completed_job(db, job_id, result_json):
    import json
    with db.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO prostudio_generation_jobs (id, status, result_json) VALUES (%s, 'completed', %s)",
                (job_id, json.dumps(result_json)),
            )


def _job_row(db, job_id):
    with db.connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT status, result_json FROM prostudio_generation_jobs WHERE id=%s", (job_id,))
            return cur.fetchone()


def test_storage_merge_upgrades_urls_without_touching_status_or_history_fields(db):
    database, main = db
    _insert_completed_job(database, "job-1", {
        "ok": True, "status": "completed", "image_url": "https://provider.example/tmp.png",
        "conversation_id": "conv-42", "metadata": {"provider": "ideogram"},
    })

    main._merge_prostudio_storage_result(
        "job-1", {"image_url": "https://r2.example/permanent.png"}, "completed",
    )

    status, result = _job_row(database, "job-1")
    assert status == "completed"
    assert result["image_url"] == "https://r2.example/permanent.png"
    assert result["storage_status"] == "completed"
    # History's own contribution (written before the background merge ran)
    # must survive a read-merge-write, not get clobbered by a blind replace.
    assert result["conversation_id"] == "conv-42"
    assert result["metadata"] == {"provider": "ideogram"}


def test_storage_merge_failure_only_sets_storage_status_leaves_urls_and_status_alone(db):
    database, main = db
    _insert_completed_job(database, "job-2", {
        "ok": True, "status": "completed", "image_url": "https://provider.example/tmp.png",
    })

    main._merge_prostudio_storage_result("job-2", {}, "failed")

    status, result = _job_row(database, "job-2")
    assert status == "completed", "a storage failure must never move the job out of completed"
    assert result["image_url"] == "https://provider.example/tmp.png"
    assert result["storage_status"] == "failed"


def test_storage_merge_is_noop_for_a_non_completed_job(db):
    database, main = db
    with database.connect() as conn:
        with conn.cursor() as cur:
            cur.execute("INSERT INTO prostudio_generation_jobs (id, status, result_json) VALUES ('job-3', 'failed', '{}')")

    main._merge_prostudio_storage_result("job-3", {"image_url": "https://r2.example/x.png"}, "completed")

    status, result = _job_row(database, "job-3")
    assert status == "failed"
    assert "storage_status" not in (result or {})
