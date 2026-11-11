"""B11: ops_alerts on real PostgreSQL - two evaluators at once act once
(transaction advisory lock), and the detectors work on the production
column types (TIMESTAMP job times compared with NOW()).

Needs SYLVEX_OPS_ALERT_TEST_DB: a PostgreSQL DSN where a throw-away
database may be created."""
import os
import uuid

import pytest

DSN = os.getenv("SYLVEX_OPS_ALERT_TEST_DB")
pytestmark = pytest.mark.skipif(not DSN, reason="Set SYLVEX_OPS_ALERT_TEST_DB to run real-PostgreSQL tests")


@pytest.fixture
def connect():
    import psycopg2
    from psycopg2.extensions import make_dsn, parse_dsn
    name = "ops_alerts_test_" + uuid.uuid4().hex[:10]
    admin = psycopg2.connect(DSN)
    admin.autocommit = True
    admin.cursor().execute(f'CREATE DATABASE "{name}"')
    dsn = make_dsn(**dict(parse_dsn(DSN), dbname=name))
    conn = psycopg2.connect(dsn)
    conn.cursor().execute("""CREATE TABLE prostudio_generation_jobs (id TEXT PRIMARY KEY, telegram_id BIGINT NOT NULL,
        mode TEXT NOT NULL, status TEXT, attempts INTEGER DEFAULT 0, created_at TIMESTAMP DEFAULT NOW(),
        heartbeat_at TIMESTAMP, provider_wait_until TIMESTAMP, updated_at TIMESTAMP DEFAULT NOW(), completed_at TIMESTAMP)""")
    conn.cursor().execute("INSERT INTO prostudio_generation_jobs (id, telegram_id, mode, status, created_at) "
                          "VALUES ('q1', 1, 'image', 'queued', NOW() - INTERVAL '12 minutes')")
    conn.commit()
    conn.close()
    yield lambda: psycopg2.connect(dsn)
    admin.cursor().execute(f'DROP DATABASE "{name}" WITH (FORCE)')
    admin.close()


def test_two_evaluators_send_once(connect):
    from services import ops_alerts
    sent = []
    holder = connect()
    hcur = holder.cursor()
    ops_alerts.ensure_schema(hcur)
    holder.commit()
    hcur.execute("SELECT pg_advisory_xact_lock(%s)", (ops_alerts.LOCK_KEY,))   # another evaluator mid-cycle
    other = connect()
    result = ops_alerts.evaluate(other.cursor(), lambda t: sent.append(t) or (True, None))
    other.commit()
    assert result["skipped"] is True and sent == []
    holder.rollback()                                                         # releases the lock
    result = ops_alerts.evaluate(other.cursor(), lambda t: sent.append(t) or (True, None))
    other.commit()
    assert result["sent"] == [("workers_stalled", "fire")] and len(sent) == 1
    again = ops_alerts.evaluate(other.cursor(), lambda t: sent.append(t) or (True, None))
    other.commit()
    assert again["sent"] == [] and len(sent) == 1
    other.close()
    holder.close()
