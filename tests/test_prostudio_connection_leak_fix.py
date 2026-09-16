"""Regression tests for the DB-connection-pool leak fixed across the Pro
Studio gallery/sync/conversations/jobs endpoints (and several other
db_connect() call sites) in main.py: many of them acquired a pooled
connection via db_connect() inside a bare try/except with no finally, so
cursor.close()/conn.close() only ran on the happy path. Any exception
raised between checkout and that close() - a transient DB error, a lock
timeout, a malformed row during processing - leaked that connection out
of the fixed-size pool forever. In production this is exactly what
produced `DB_POOL_WAIT: used=10, free=0, waiting=1` and 100-300s hangs on
unrelated endpoints sharing the same pool (including
/api/web/session/me, whose own code was already leak-free but starved
once the shared pool was exhausted).

Fixed sites now use the db_connection() context manager (db_pool.py),
which guarantees release via its own finally even when the wrapped code
raises. These tests directly exercise several of the fixed main.py call
sites with a cursor.execute() that raises mid-call - the "force an
exception after acquiring a connection" scenario - and verify pool usage
returns to its previous level afterward, i.e. no leak. No real Postgres
or pglite is needed: psycopg2's ThreadedConnectionPool is replaced with an
in-memory fake, the same technique tests/test_db_pool.py already uses.
"""
import asyncio
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent))

# Never touch the real environment/DB/background workers when main.py is
# imported below (mirrors tests/conftest.py, kept explicit here too since
# this file must also work when run standalone).
os.environ.setdefault("PYTHON_DOTENV_DISABLED", "1")
os.environ.setdefault("PROSTUDIO_WORKER_ENABLED", "0")
os.environ.setdefault("SUBSCRIPTION_REMINDER_WORKER_ENABLED", "0")
os.environ.setdefault("APP_ENV", "test")
os.environ.pop("DATABASE_URL", None)
os.environ.pop("DATABASE_PUBLIC_URL", None)

import db_pool


class FakeCursor:
    def __init__(self, raise_on_execute=None):
        self.rowcount = 0
        self._raise_on_execute = raise_on_execute

    def execute(self, sql, params=None):
        if self._raise_on_execute is not None:
            raise self._raise_on_execute

    def fetchone(self):
        return None

    def fetchall(self):
        return []

    def close(self):
        pass


class FakeConnection:
    closed = 0
    status = db_pool.extensions.STATUS_READY
    # Class-level switch: every connection minted while this is set raises
    # from its cursor's execute(), simulating a transient DB failure partway
    # through one of the fixed functions' queries.
    raise_on_execute = None

    def cursor(self):
        return FakeCursor(raise_on_execute=FakeConnection.raise_on_execute)

    def commit(self):
        pass

    def rollback(self):
        pass

    def close(self):
        self.closed = 1


class FakeThreadedPool:
    def __init__(self, minconn, maxconn, dsn):
        self.maximum = maxconn
        self.created = minconn
        self._pool = [FakeConnection() for _ in range(minconn)]
        self._used = {}

    def getconn(self):
        if self._pool:
            connection = self._pool.pop()
        elif self.created < self.maximum:
            connection = FakeConnection()
            self.created += 1
        else:
            raise db_pool.PoolError("connection pool exhausted")
        self._used[id(connection)] = connection
        return connection

    def putconn(self, connection, close=False):
        self._used.pop(id(connection), None)
        if close:
            connection.close()
            self.created -= 1
        else:
            self._pool.append(connection)

    def closeall(self):
        for connection in self._pool + list(self._used.values()):
            connection.close()


class ProstudioEndpointConnectionLeakTests(unittest.TestCase):
    """Each test calls one of the fixed main.py functions while its
    cursor.execute() raises, then asserts db_pool's `used` count came back
    to zero - proving the connection was returned, not leaked."""

    @classmethod
    def setUpClass(cls):
        import main
        cls.main = main

    def setUp(self):
        self.environment = patch.dict(os.environ, {
            "DB_POOL_MIN_SIZE": "1",
            "DB_POOL_MAX_SIZE": "5",
            "DB_POOL_TIMEOUT_SECONDS": "2",
        })
        self.environment.start()
        self.pool_patch = patch.object(db_pool, "ThreadedConnectionPool", FakeThreadedPool)
        self.pool_patch.start()
        self.db_url_patch = patch.object(self.main, "DATABASE_URL", "mock-postgres")
        self.db_url_patch.start()
        # Isolate each test to just the target function's own db_connect()
        # usage - ensure_prostudio_table() has its own, unrelated DDL-DB
        # round trip that would otherwise also need a working fake schema.
        self.ensure_table_patch = patch.object(self.main, "ensure_prostudio_table", lambda: None)
        self.ensure_table_patch.start()
        FakeConnection.raise_on_execute = RuntimeError("simulated transient DB failure")

    def tearDown(self):
        FakeConnection.raise_on_execute = None
        self.ensure_table_patch.stop()
        self.db_url_patch.stop()
        db_pool.close_db_pool(timeout=1)
        self.pool_patch.stop()
        self.environment.stop()

    def _assert_pool_returned_to_baseline(self):
        status = db_pool.db_pool_status()
        self.assertEqual(status["used"], 0, "a connection leaked out of the pool")
        self.assertEqual(status["waiting"], 0)

    def test_save_generation_does_not_leak_on_db_error(self):
        # Existing behavior preserved: the error is caught and logged, the
        # function never raises out to its caller.
        self.main.save_generation(101, "image", "a cat", "done")
        self._assert_pool_returned_to_baseline()

    def test_log_prostudio_error_does_not_leak_on_db_error(self):
        self.main.log_prostudio_error(
            {"telegram_id": 101, "provider": "openai"},
            {"error": "boom"},
            job_id="job-1",
        )
        self._assert_pool_returned_to_baseline()

    def test_gallery_endpoint_does_not_leak_on_db_error(self):
        result = asyncio.run(self.main.public_prostudio_gallery(telegram_id=101))
        self.assertEqual(result, {"ok": True, "items": []})
        self._assert_pool_returned_to_baseline()

    def test_delete_gallery_item_does_not_leak_on_db_error(self):
        result = asyncio.run(
            self.main.delete_public_prostudio_gallery_item(message_id=5, telegram_id=101)
        )
        self.assertEqual(result, {"ok": True})
        self._assert_pool_returned_to_baseline()

    def test_conversations_endpoint_does_not_leak_on_db_error(self):
        result = asyncio.run(self.main.public_prostudio_conversations(telegram_id=101))
        self.assertEqual(result, {"ok": True, "conversations": [], "messages": []})
        self._assert_pool_returned_to_baseline()

    def test_delete_conversation_does_not_leak_on_db_error(self):
        result = asyncio.run(
            self.main.delete_public_prostudio_conversation(telegram_id=101, conversation_id="conv-1")
        )
        self.assertEqual(result, {"ok": True})
        self._assert_pool_returned_to_baseline()

    def test_generation_jobs_endpoint_does_not_leak_on_db_error(self):
        result = asyncio.run(self.main.public_prostudio_generation_jobs(telegram_id=101))
        self.assertEqual(result, {"ok": True, "jobs": []})
        self._assert_pool_returned_to_baseline()

    def test_sync_endpoint_does_not_leak_on_db_error(self):
        # Exercises load_prostudio_resources()/load_prostudio_drafts() too,
        # since public_prostudio_sync() calls both before its own queries -
        # both were separately fixed and are covered by this one call.
        result = asyncio.run(self.main.public_prostudio_sync(telegram_id=101))
        self.assertTrue(result["ok"])
        self._assert_pool_returned_to_baseline()

    def test_job_endpoint_does_not_leak_on_db_error(self):
        response = asyncio.run(self.main.public_prostudio_job(job_id="job-1"))
        # actor_id is a contextvar the SecurityMiddleware normally sets;
        # unset here, which is fine - the query still runs and still fails.
        self.assertEqual(response.status_code, 500)
        self._assert_pool_returned_to_baseline()

    def test_report_error_endpoint_does_not_leak_on_db_error(self):
        async def call():
            from starlette.requests import Request

            async def receive():
                import json
                body = json.dumps({"telegram_id": 101, "mode": "image", "error_text": "failed"}).encode()
                return {"type": "http.request", "body": body, "more_body": False}

            scope = {
                "type": "http",
                "method": "POST",
                "path": "/api/public/prostudio/report_error",
                "headers": [],
            }
            request = Request(scope, receive)
            return await self.main.public_prostudio_report_error(request)

        response = asyncio.run(call())
        self.assertEqual(response.status_code, 500)
        self._assert_pool_returned_to_baseline()

    def test_delete_resource_endpoint_does_not_leak_on_db_error(self):
        response = asyncio.run(
            self.main.public_prostudio_delete_resource(resource_id="custom_character_1", telegram_id=101)
        )
        self.assertEqual(response.status_code, 500)
        self._assert_pool_returned_to_baseline()


if __name__ == "__main__":
    unittest.main()
