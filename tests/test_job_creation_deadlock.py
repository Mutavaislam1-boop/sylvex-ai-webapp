"""Real PostgreSQL lock regression; pip install pgserver pytest psycopg2-binary.

Loads the production functions without importing the API and its background
workers. Every connection points to a temporary local PostgreSQL instance.
"""
import ast
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import threading
import time
from types import SimpleNamespace
from uuid import uuid4

import psycopg2
from psycopg2.extensions import cursor as PgCursor
import pytest

pgserver = pytest.importorskip("pgserver")
ROOT = Path(__file__).resolve().parents[1]


def load_functions(path, names, namespace, legacy=False):
    source = path.read_text()
    if legacy:
        source = source.replace(
            'cursor.execute("LOCK TABLE prostudio_generation_jobs IN ROW EXCLUSIVE MODE")',
            'pass  # reproduce the original SELECT-then-INSERT lock upgrade',
        )
    nodes = [node for node in ast.parse(source).body if getattr(node, "name", None) in names]
    assert len(nodes) == len(names)
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(path), "exec"), namespace)


@pytest.fixture
def database(tmp_path):
    pg = pgserver.get_server(tmp_path / "pgdata", cleanup_mode="stop")
    uri = pg.get_uri()
    statements = []
    hooks = {"after": None, "before": None}

    class Cursor(PgCursor):
        def execute(self, query, params=None):
            text = " ".join(str(query).split())
            statements.append(text)
            if hooks["before"]:
                hooks["before"](text)
            result = super().execute(query, params)
            if hooks["after"]:
                hooks["after"](text)
            return result

    def connect(*args):
        return psycopg2.connect(uri, cursor_factory=Cursor, options="-c statement_timeout=10000 -c deadlock_timeout=100")

    ns = {
        "DATABASE_URL": uri, "db_connect": connect,
        "PROSTUDIO_SCHEMA_LOCK": threading.Lock(), "_PROSTUDIO_SCHEMA_READY": False,
        "uuid4": uuid4, "_safe_json_dumps": json.dumps,
        "prostudio_debug": lambda *a, **k: None, "prostudio_error": lambda *a, **k: None,
        "calculate_generation_price": lambda payload: {"price_snapshot": {"final_credits": 2}},
        "SecurityError": RuntimeError,
    }
    load_functions(ROOT / "services/billing_safety.py", {"ensure_reservations", "reserve_generation"}, ns)
    load_functions(ROOT / "main.py", {"ensure_prostudio_table", "create_prostudio_generation_job", "ActiveProstudioJobError"}, ns)
    ns["ensure_prostudio_table"]()
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute("CREATE TABLE users (telegram_id BIGINT PRIMARY KEY, balance INTEGER)")
            cur.execute("INSERT INTO users VALUES (777, 100)")
    try:
        yield ns, connect, statements, hooks
    finally:
        pg.cleanup()


def payload(request_id="one-click"):
    return {"telegram_id": 777, "mode": "image", "model": "sylvex_test",
            "prompt": "deadlock regression", "client_request_id": request_id,
            "_sylvex_test_authorized": True}


def test_restart_skips_unnecessary_job_column_alters(database):
    ns, connect, statements, hooks = database
    statements.clear()
    ns["_PROSTUDIO_SCHEMA_READY"] = False
    ns["ensure_prostudio_table"]()
    assert not any(q.startswith("ALTER TABLE prostudio_generation_jobs") for q in statements)
    statements.clear()
    ns["ensure_prostudio_table"]()
    assert statements == []


def test_existing_database_missing_job_column_is_migrated(database):
    ns, connect, statements, hooks = database
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute("ALTER TABLE prostudio_generation_jobs DROP COLUMN provider_wait_until")
    ns["_PROSTUDIO_SCHEMA_READY"] = False
    ns["ensure_prostudio_table"]()
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT provider_wait_until FROM prostudio_generation_jobs")
            assert cur.fetchall() == []


def test_schema_failure_releases_advisory_lock(database):
    ns, connect, statements, hooks = database
    # A production lease's close() returns its physical session to the pool.
    # Keep that session alive so this catches leaked session advisory locks.
    pooled_session = connect()
    ns["db_connect"] = lambda *args: SimpleNamespace(
        cursor=pooled_session.cursor, commit=pooled_session.commit,
        rollback=pooled_session.rollback, close=lambda: None,
    )
    def fail(query):
        if query.startswith("CREATE TABLE"):
            raise RuntimeError("injected migration failure")
    hooks["before"] = fail
    ns["_PROSTUDIO_SCHEMA_READY"] = False
    try:
        with pytest.raises(RuntimeError, match="injected"):
            ns["ensure_prostudio_table"]()
        hooks["before"] = None
        assert not ns["_PROSTUDIO_SCHEMA_READY"]
        with connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT pg_try_advisory_xact_lock(742193601)")
                assert cur.fetchone()[0]
    finally:
        hooks["before"] = None
        ns["db_connect"] = connect
        pooled_session.close()
    ns["ensure_prostudio_table"]()


@pytest.mark.parametrize("legacy", [True, False], ids=["reproduce-original", "fixed"])
def test_job_creation_during_schema_lock_upgrade(database, legacy):
    ns, connect, statements, hooks = database
    if legacy:
        load_functions(ROOT / "main.py", {"create_prostudio_generation_job"}, ns, legacy=True)
    read_done, continue_insert, schema_started = threading.Event(), threading.Event(), threading.Event()
    schema_pid = []
    def after(query):
        if query.startswith("SELECT id, status FROM prostudio_generation_jobs"):
            read_done.set()
            assert continue_insert.wait(8)
    hooks["after"] = after
    def migrate():
        with connect() as conn:
            schema_pid.append(conn.get_backend_pid())
            schema_started.set()
            with conn.cursor() as cur:
                # CREATE INDEX holds this lock before the production ALTER.
                cur.execute("LOCK TABLE prostudio_generation_jobs IN SHARE MODE")
                cur.execute("ALTER TABLE prostudio_generation_jobs ADD COLUMN IF NOT EXISTS attempts INTEGER DEFAULT 0")
    with ThreadPoolExecutor(max_workers=2) as pool:
        job = pool.submit(ns["create_prostudio_generation_job"], payload())
        try:
            assert read_done.wait(5)
            migration = pool.submit(migrate)
            assert schema_started.wait(5)
            deadline = time.monotonic() + 5
            waiting = False
            while time.monotonic() < deadline:
                with connect() as conn:
                    with conn.cursor() as cur:
                        cur.execute("SELECT 1 FROM pg_locks WHERE pid=%s AND NOT granted", (schema_pid[0],))
                        waiting = cur.fetchone() is not None
                if waiting:
                    break
                time.sleep(0.01)
            assert waiting, "schema transaction must be waiting on the job before INSERT"
        finally:
            continue_insert.set()
        errors = []
        for future in (job, migration):
            try:
                future.result(timeout=8)
            except Exception as exc:
                errors.append(exc)
        if legacy:
            assert any(isinstance(exc, psycopg2.errors.DeadlockDetected) for exc in errors), errors
        else:
            assert errors == []
            with connect() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT COUNT(*) FROM prostudio_generation_jobs")
                    assert cur.fetchone()[0] == 1
                    cur.execute("SELECT balance FROM users WHERE telegram_id=777")
                    assert cur.fetchone()[0] == 98
                    cur.execute("SELECT COUNT(*) FROM generation_reservations")
                    assert cur.fetchone()[0] == 1


def test_concurrent_replays_reserve_and_create_only_once(database):
    ns, connect, statements, hooks = database
    ns["ensure_reservations"](connect)
    with ThreadPoolExecutor(max_workers=4) as pool:
        ids = list(pool.map(lambda _: ns["create_prostudio_generation_job"](payload()), range(4)))
    assert len(set(ids)) == 1
    with pytest.raises(ns["ActiveProstudioJobError"]):
        ns["create_prostudio_generation_job"](payload("different-click"))
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM prostudio_generation_jobs")
            assert cur.fetchone()[0] == 1
            cur.execute("SELECT balance FROM users WHERE telegram_id=777")
            assert cur.fetchone()[0] == 98
