"""ensure_prostudio_table() ran its full ~25-statement DDL batch (CREATE
TABLE/INDEX + ALTER TABLE ADD COLUMN across half a dozen tables) behind a
global process-wide lock AND a Postgres session advisory lock on every
single call - and it is called from nearly every hot-path function (job
claim, job create, active-job check, heartbeat...). With N concurrent
workers that serializes all of them behind one Python lock for a full DB
round trip each time, on every job, which is a plausible dominant cause of
"generation is randomly slow" under real concurrency. The schema only
ever needs to be ensured once per process lifetime - this matches the
existing, already-correct caching pattern in ensure_provider_slot_table."""
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
    # Force a real first run regardless of what earlier tests in this
    # process already marked ready.
    monkeypatch.setattr(main, "_PROSTUDIO_SCHEMA_READY", False)

    yield database, main
    database.close()


def test_schema_setup_runs_its_ddl_batch_at_most_once_per_process(db, monkeypatch):
    database, main = db
    call_count = {"n": 0}
    real_db_connect = main.db_connect

    def counting_connect(*a, **k):
        call_count["n"] += 1
        return real_db_connect(*a, **k)

    monkeypatch.setattr(main, "db_connect", counting_connect)

    main.ensure_prostudio_table()
    assert call_count["n"] == 1, "the first call must actually run the DDL batch"

    main.ensure_prostudio_table()
    main.ensure_prostudio_table()
    main.ensure_prostudio_table()

    assert call_count["n"] == 1, (
        "a job already knowing the schema is ready must never pay for another "
        "DB round trip and advisory lock just to re-run idempotent DDL"
    )

    with database.connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM prostudio_generation_jobs")
            assert cur.fetchone()[0] == 0
