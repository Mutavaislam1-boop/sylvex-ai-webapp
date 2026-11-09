"""S7-05: a failed stage write is logged, never turned into a failed generation.

record_prostudio_job_stage passed stage= to prostudio_error, whose first
parameter is already named stage, so its own error handler raised
TypeError; the provider result had arrived, yet the job was marked failed.
"""
import os
from contextlib import contextmanager

import psycopg2
import pytest

import main


def _failing_db(monkeypatch):
    @contextmanager
    def db_connection(url):
        raise psycopg2.OperationalError("synthetic database outage")
        yield  # pragma: no cover

    monkeypatch.setattr(main, "DATABASE_URL", "postgres://synthetic-outage")
    monkeypatch.setattr(main, "db_connection", db_connection)


class _Cursor:
    def __init__(self, log):
        self.log = log

    def execute(self, sql, params=None):
        self.log.append((sql, params))

    def close(self):
        pass


def _working_db(monkeypatch, log):
    class Conn:
        def cursor(self):
            return _Cursor(log)

        def commit(self):
            log.append(("COMMIT", None))

    @contextmanager
    def db_connection(url):
        yield Conn()

    monkeypatch.setattr(main, "DATABASE_URL", "postgres://synthetic-ok")
    monkeypatch.setattr(main, "db_connection", db_connection)


def test_stage_write_failure_is_logged_and_not_raised(monkeypatch, capsys):
    _failing_db(monkeypatch)
    assert main.record_prostudio_job_stage("job-outage", "result") is None
    out = capsys.readouterr().out
    assert "PROSTUDIO ERROR JOB_STAGE_RECORD_FAILED" in out
    assert "'job_stage': 'result'" in out and "synthetic database outage" in out


@pytest.fixture
def app(monkeypatch):
    statuses = []
    monkeypatch.setattr(main, "PROSTUDIO_MOCK_GENERATION", False)
    monkeypatch.setattr(main, "optimize_prompt_for_model", lambda *a, **k: {"ok": True, "optimized": False})
    monkeypatch.setattr(main, "resolve_prostudio_provider_for_slot", lambda *a, **k: "OPENAI")
    monkeypatch.setattr(main, "circuit_before_request", lambda *a, **k: {"allowed": True})
    monkeypatch.setattr(main, "circuit_release_probe", lambda *a, **k: None)
    monkeypatch.setattr(main, "heartbeat_prostudio_generation_job", lambda *a, **k: None)
    monkeypatch.setattr(main, "log_user_event", lambda *a, **k: None)
    monkeypatch.setattr(main, "save_generation", lambda *a, **k: None)
    monkeypatch.setattr(main, "save_prostudio_message", lambda *a, **k: "conv-1")
    monkeypatch.setattr(main, "charge_generation_balance", lambda *a, **k: {"charged": True, "balance_after": 100})
    monkeypatch.setattr(main, "update_prostudio_generation_job",
                        lambda job_id, status, *a, **k: statuses.append(status) or True)
    monkeypatch.setattr(main, "verify_persisted_generation_media", lambda result, mode: result)
    monkeypatch.setattr(main, "persist_generation_media", lambda result, mode: result)
    monkeypatch.setattr(main, "record_character_generation_history", lambda *a, **k: None)
    monkeypatch.setattr(main.asyncio, "create_task", lambda coro: coro.close())
    failed_notices = []

    async def telegram_sent(*a, **k):
        return True

    async def failed_notice(*a, **k):
        failed_notices.append(a)
    monkeypatch.setattr(main, "sync_completed_generation_to_telegram", telegram_sent)
    monkeypatch.setattr(main, "notify_telegram_generation_failed", failed_notice)

    async def provider(*a, **k):
        return ({"ok": True, "type": "image", "status": "completed", "image_url": "https://cdn.sylvex.ai/r.png",
                 "images": ["https://cdn.sylvex.ai/r.png"], "provider": "openai", "model": "gpt-image-2"}, "completed")
    monkeypatch.setattr(main, "run_prostudio_provider_request", provider)
    main._s705_statuses, main._s705_failed = statuses, failed_notices
    return main


PAYLOAD = {"telegram_id": 42, "mode": "image", "prompt": "A portrait", "model": "gpt-image-2",
           "provider": "openai", "price_snapshot": {"final_credits": 5}, "image_options": {"count": 1}}


@pytest.mark.asyncio
async def test_provider_result_completes_when_the_stage_write_fails(app, monkeypatch, capsys):
    _failing_db(monkeypatch)
    await app.process_prostudio_generation("job-outage", dict(PAYLOAD))
    out = capsys.readouterr().out
    assert "JOB_STAGE_RECORD_FAILED" in out
    assert "JOB_PROCESS_EXCEPTION" not in out and "got multiple values" not in out
    assert "failed" not in app._s705_statuses and "completed" in app._s705_statuses
    assert app._s705_failed == []


@pytest.mark.asyncio
async def test_normal_generation_records_the_result_stage_and_completes(app, monkeypatch, capsys):
    log = []
    _working_db(monkeypatch, log)
    await app.process_prostudio_generation("job-ok", dict(PAYLOAD))
    out = capsys.readouterr().out
    stage_writes = [params for sql, params in log if sql and "stage_json" in str(sql)]
    assert ("result", "job-ok", "result") in stage_writes
    assert "JOB_STAGE_RECORD_FAILED" not in out and "JOB_PROCESS_EXCEPTION" not in out
    assert "failed" not in app._s705_statuses and "completed" in app._s705_statuses


@pytest.mark.skipif(not os.getenv("SYLVEX_TEST_DATABASE_URL"), reason="real PostgreSQL stage write")
def test_stage_write_on_real_postgres_is_unchanged(monkeypatch):
    dsn = os.environ["SYLVEX_TEST_DATABASE_URL"]
    schema = "s705_stage_" + os.urandom(4).hex()
    with psycopg2.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute('CREATE SCHEMA "%s"' % schema)
        cur.execute('CREATE TABLE "%s".prostudio_generation_jobs(id TEXT PRIMARY KEY,status TEXT,stage_json JSONB)' % schema)
        cur.execute('INSERT INTO "%s".prostudio_generation_jobs VALUES(%%s,%%s,NULL),(%%s,%%s,NULL)' % schema,
                    ("job-live", "processing", "job-done", "completed"))

    @contextmanager
    def db_connection(url):
        conn = psycopg2.connect(dsn, options="-c search_path=" + schema)
        try:
            yield conn
        finally:
            conn.close()
    monkeypatch.setattr(main, "DATABASE_URL", dsn)
    monkeypatch.setattr(main, "db_connection", db_connection)
    try:
        main.record_prostudio_job_stage("job-live", "result")
        main.record_prostudio_job_stage("job-live", "result")  # first timestamp is kept
        main.record_prostudio_job_stage("job-done", "result")  # terminal jobs are not touched
        with psycopg2.connect(dsn, options="-c search_path=" + schema) as conn, conn.cursor() as cur:
            cur.execute("SELECT id,stage_json ? 'result' FROM prostudio_generation_jobs ORDER BY id")
            assert cur.fetchall() == [("job-done", None), ("job-live", True)]
    finally:
        with psycopg2.connect(dsn) as conn, conn.cursor() as cur:
            cur.execute('DROP SCHEMA "%s" CASCADE' % schema)
