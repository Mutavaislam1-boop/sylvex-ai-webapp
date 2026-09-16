"""Regression tests proving the event-loop-freeze fix: async route handlers
that used to run synchronous psycopg2 work directly on the coroutine body
(main.py, see the 53-handler sweep fixed alongside this file) now offload
that work via asyncio.to_thread(), so a single slow/stuck query can no
longer freeze the entire uvicorn process for every other in-flight request -
including ones needing zero DB access at all, like a CORS OPTIONS preflight
(the actual production symptom that led to this fix).

Each test here simulates a DB call that blocks for a controlled period (a
real time.sleep() inside a fake cursor.execute(), run on a real OS thread
via ThreadPoolExecutor - exactly what asyncio.to_thread() uses), invokes
the affected endpoint concurrently with a lightweight asyncio "heartbeat"
task, and asserts the heartbeat keeps ticking at its normal cadence while
the DB call is blocked. If the endpoint's DB work still ran directly on the
event loop (the pre-fix bug), the blocking time.sleep() would freeze that
thread - which for the *real* event loop's own thread would starve the
heartbeat; here it would instead have starved whichever thread the fake
pool's blocking call landed on. The fixed code guarantees that thread is
never the event loop's own thread, so the heartbeat's tick count during the
blocked window is the actual assertion: near the full expected count means
the loop stayed responsive, near zero would mean it froze.
"""
import asyncio
import os
import sys
import time
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent))

os.environ.setdefault("PYTHON_DOTENV_DISABLED", "1")
os.environ.setdefault("PROSTUDIO_WORKER_ENABLED", "0")
os.environ.setdefault("SUBSCRIPTION_REMINDER_WORKER_ENABLED", "0")
os.environ.setdefault("APP_ENV", "test")
os.environ.pop("DATABASE_URL", None)
os.environ.pop("DATABASE_PUBLIC_URL", None)

import db_pool

BLOCK_SECONDS = 0.4
HEARTBEAT_INTERVAL = 0.01
# A frozen loop ticks ~0 times during the block; a responsive one ticks
# close to BLOCK_SECONDS / HEARTBEAT_INTERVAL (~40). This threshold is
# comfortably below that while still far above what a freeze would allow.
MIN_EXPECTED_TICKS = 15


class FakeCursor:
    def __init__(self):
        self.rowcount = 0

    def execute(self, sql, params=None):
        # Simulates a slow/stuck query - a real synchronous DB driver call
        # blocks its OS thread exactly like this for its full duration.
        time.sleep(BLOCK_SECONDS)

    def fetchone(self):
        return None

    def fetchall(self):
        return []

    def close(self):
        pass


class FakeConnection:
    closed = 0
    status = db_pool.extensions.STATUS_READY

    def cursor(self):
        return FakeCursor()

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


async def _heartbeat_ticks_during(coro):
    """Runs `coro` concurrently with a fast asyncio heartbeat - the
    OPTIONS-preflight stand-in the task requires - and returns
    (endpoint_result, tick_count). A frozen event loop starves the
    heartbeat coroutine exactly as it would starve a real concurrent
    request; a responsive one lets it keep ticking on schedule."""
    ticks = 0
    stop = False

    async def heartbeat():
        nonlocal ticks
        while not stop:
            await asyncio.sleep(HEARTBEAT_INTERVAL)
            ticks += 1

    heartbeat_task = asyncio.ensure_future(heartbeat())
    try:
        result = await coro
    finally:
        stop = True
        heartbeat_task.cancel()
        try:
            await heartbeat_task
        except asyncio.CancelledError:
            pass
    return result, ticks


class EventLoopResponsivenessTests(unittest.TestCase):
    """Each test blocks a simulated DB call for BLOCK_SECONDS inside one of
    the fixed endpoints and proves a concurrent lightweight asyncio task -
    standing in for an unrelated request, like the production OPTIONS
    preflight that hung for ~300s - keeps making progress throughout."""

    @classmethod
    def setUpClass(cls):
        import main
        cls.main = main

    def setUp(self):
        self.environment = patch.dict(os.environ, {
            "DB_POOL_MIN_SIZE": "1",
            "DB_POOL_MAX_SIZE": "5",
            "DB_POOL_TIMEOUT_SECONDS": "5",
        })
        self.environment.start()
        self.pool_patch = patch.object(db_pool, "ThreadedConnectionPool", FakeThreadedPool)
        self.pool_patch.start()
        self.db_url_patch = patch.object(self.main, "DATABASE_URL", "mock-postgres")
        self.db_url_patch.start()
        self.ensure_table_patch = patch.object(self.main, "ensure_prostudio_table", lambda: None)
        self.ensure_table_patch.start()
        self.ensure_admin_tables_patch = patch.object(self.main, "ensure_admin_tables", lambda: None)
        self.ensure_admin_tables_patch.start()
        self.load_resources_patch = patch.object(self.main, "load_prostudio_resources", lambda tid: {})
        self.load_resources_patch.start()
        self.load_drafts_patch = patch.object(self.main, "load_prostudio_drafts", lambda tid: {})
        self.load_drafts_patch.start()

    def tearDown(self):
        self.load_drafts_patch.stop()
        self.load_resources_patch.stop()
        self.ensure_admin_tables_patch.stop()
        self.ensure_table_patch.stop()
        self.db_url_patch.stop()
        db_pool.close_db_pool(timeout=1)
        self.pool_patch.stop()
        self.environment.stop()

    def _assert_loop_stayed_responsive(self, ticks, started_at):
        elapsed = time.monotonic() - started_at
        self.assertGreaterEqual(
            elapsed, BLOCK_SECONDS * 0.9,
            "the simulated DB call did not actually block for the expected duration",
        )
        self.assertGreaterEqual(
            ticks, MIN_EXPECTED_TICKS,
            f"event loop heartbeat only ticked {ticks} times during a {BLOCK_SECONDS}s "
            "blocked DB call - the endpoint is freezing the event loop instead of "
            "offloading the blocking call via asyncio.to_thread()",
        )

    def test_presence_endpoint_does_not_freeze_event_loop(self):
        from starlette.requests import Request
        import json

        async def receive():
            body = json.dumps({"initData": "", "telegram_id": 101, "view": "home"}).encode()
            return {"type": "http.request", "body": body, "more_body": False}

        scope = {"type": "http", "method": "POST", "path": "/api/public/presence", "headers": []}
        request = Request(scope, receive)

        with patch.object(self.main, "_telegram_id_from_init_data", lambda s: 101):
            started_at = time.monotonic()
            result, ticks = asyncio.run(
                _heartbeat_ticks_during(self.main.public_presence(request))
            )
        self.assertEqual(result, {"ok": True})
        self._assert_loop_stayed_responsive(ticks, started_at)

    def test_gallery_endpoint_does_not_freeze_event_loop(self):
        started_at = time.monotonic()
        result, ticks = asyncio.run(
            _heartbeat_ticks_during(self.main.public_prostudio_gallery(telegram_id=101))
        )
        self.assertEqual(result, {"ok": True, "items": [], "limit": 80, "offset": 0})
        self._assert_loop_stayed_responsive(ticks, started_at)

    def test_sync_endpoint_does_not_freeze_event_loop(self):
        started_at = time.monotonic()
        result, ticks = asyncio.run(
            _heartbeat_ticks_during(self.main.public_prostudio_sync(telegram_id=101))
        )
        self.assertTrue(result["ok"])
        self._assert_loop_stayed_responsive(ticks, started_at)

    def test_generation_jobs_endpoint_does_not_freeze_event_loop(self):
        started_at = time.monotonic()
        result, ticks = asyncio.run(
            _heartbeat_ticks_during(self.main.public_prostudio_generation_jobs(telegram_id=101))
        )
        self.assertEqual(result, {"ok": True, "jobs": []})
        self._assert_loop_stayed_responsive(ticks, started_at)

    def test_conversations_endpoint_does_not_freeze_event_loop(self):
        started_at = time.monotonic()
        result, ticks = asyncio.run(
            _heartbeat_ticks_during(self.main.public_prostudio_conversations(telegram_id=101))
        )
        self.assertEqual(result, {"ok": True, "conversations": []})
        self._assert_loop_stayed_responsive(ticks, started_at)


if __name__ == "__main__":
    unittest.main()
