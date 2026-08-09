"""Process-wide blocking PostgreSQL pool built on psycopg2's native pool."""

from __future__ import annotations

import os
import threading
import time
from typing import Optional

from psycopg2 import extensions
from psycopg2.pool import ThreadedConnectionPool


def _bounded_int(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(str(os.getenv(name, default)).strip())
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(maximum, value))


def _positive_float(name: str, default: float, minimum: float) -> float:
    try:
        value = float(str(os.getenv(name, default)).strip())
    except (TypeError, ValueError):
        value = default
    return max(minimum, value)


DB_POOL_MAX_SIZE = _bounded_int("DB_POOL_MAX_SIZE", 10, 1, 100)
DB_POOL_MIN_SIZE = min(_bounded_int("DB_POOL_MIN_SIZE", 2, 1, 100), DB_POOL_MAX_SIZE)
DB_POOL_TIMEOUT_SECONDS = _positive_float("DB_POOL_TIMEOUT_SECONDS", 30.0, 0.1)

_lock = threading.RLock()
_condition = threading.Condition(_lock)
_pool: Optional[ThreadedConnectionPool] = None
_database_url = ""
_capacity: Optional[threading.BoundedSemaphore] = None
_used = 0
_waiting = 0
_closing = False
_last_status_log = 0.0
_last_wait_log = 0.0


def _snapshot() -> dict:
    with _lock:
        return {
            "min_size": DB_POOL_MIN_SIZE,
            "max_size": DB_POOL_MAX_SIZE,
            "used": _used,
            "free": max(0, DB_POOL_MAX_SIZE - _used),
            "waiting": _waiting,
        }


def _log(event: str) -> None:
    print(f"{event}:", _snapshot())


def _log_status_if_due(force: bool = False) -> None:
    global _last_status_log
    now = time.monotonic()
    with _lock:
        if not force and now - _last_status_log < 30.0:
            return
        _last_status_log = now
    _log("DB_POOL_STATUS")


def _log_wait_if_due() -> None:
    global _last_wait_log
    now = time.monotonic()
    with _lock:
        if now - _last_wait_log < 1.0:
            return
        _last_wait_log = now
    _log("DB_POOL_WAIT")


def start_db_pool(database_url: str) -> None:
    """Start the single pool for this process; safe to call repeatedly."""
    global _pool, _database_url, _capacity, _closing
    global DB_POOL_MIN_SIZE, DB_POOL_MAX_SIZE, DB_POOL_TIMEOUT_SECONDS
    url = str(database_url or "").strip()
    if not url:
        return
    with _lock:
        if _pool is not None:
            if _database_url != url:
                raise RuntimeError("PostgreSQL pool is already configured with another DATABASE_URL")
            return
        DB_POOL_MAX_SIZE = _bounded_int("DB_POOL_MAX_SIZE", 10, 1, 100)
        DB_POOL_MIN_SIZE = min(_bounded_int("DB_POOL_MIN_SIZE", 2, 1, 100), DB_POOL_MAX_SIZE)
        DB_POOL_TIMEOUT_SECONDS = _positive_float("DB_POOL_TIMEOUT_SECONDS", 30.0, 0.1)
        _pool = ThreadedConnectionPool(DB_POOL_MIN_SIZE, DB_POOL_MAX_SIZE, dsn=url)
        _database_url = url
        _capacity = threading.BoundedSemaphore(DB_POOL_MAX_SIZE)
        _closing = False
    _log("DB_POOL_STARTED")
    _log_status_if_due(force=True)


class PooledConnection:
    """Compatibility proxy whose close() returns the connection to the pool."""

    def __init__(self, connection, pool: ThreadedConnectionPool, capacity: threading.BoundedSemaphore):
        self._connection = connection
        self._pool = pool
        self._capacity = capacity
        self._returned = False

    def __getattr__(self, name):
        return getattr(self._connection, name)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        try:
            if exc_type is None:
                self._connection.commit()
            else:
                self._connection.rollback()
        finally:
            self.close()
        return False

    def close(self) -> None:
        global _used
        if self._returned:
            return
        self._returned = True
        broken = bool(self._connection.closed)
        try:
            if not broken and self._connection.status != extensions.STATUS_READY:
                self._connection.rollback()
        except Exception:
            broken = True
        finally:
            try:
                self._pool.putconn(self._connection, close=broken)
            finally:
                self._capacity.release()
                with _condition:
                    _used = max(0, _used - 1)
                    _condition.notify_all()
                _log_status_if_due()


def db_connect(database_url: str = "", timeout: Optional[float] = None) -> PooledConnection:
    """Wait for a free pooled connection and return a close-compatible proxy."""
    global _used, _waiting
    url = str(database_url or _database_url or "").strip()
    if not url:
        raise RuntimeError("DATABASE_URL is not configured")
    start_db_pool(url)
    with _lock:
        if _closing or _pool is None or _capacity is None:
            raise RuntimeError("PostgreSQL pool is closing")
        pool = _pool
        capacity = _capacity

    wait_timeout = DB_POOL_TIMEOUT_SECONDS if timeout is None else max(0.1, float(timeout))
    if not capacity.acquire(blocking=False):
        with _condition:
            _waiting += 1
        _log_wait_if_due()
        try:
            acquired = capacity.acquire(timeout=wait_timeout)
        finally:
            with _condition:
                _waiting = max(0, _waiting - 1)
                _condition.notify_all()
        if not acquired:
            _log_status_if_due(force=True)
            raise TimeoutError(f"Timed out waiting {wait_timeout:g}s for a PostgreSQL connection")

    try:
        connection = pool.getconn()
    except Exception:
        capacity.release()
        raise
    with _condition:
        _used += 1
        _condition.notify_all()
    _log_status_if_due()
    return PooledConnection(connection, pool, capacity)


def db_pool_status() -> dict:
    status = _snapshot()
    _log("DB_POOL_STATUS")
    return status


def close_db_pool(timeout: Optional[float] = None) -> None:
    """Stop new checkouts, wait for borrowers, then close every idle connection."""
    global _pool, _database_url, _capacity, _closing
    wait_timeout = DB_POOL_TIMEOUT_SECONDS if timeout is None else max(0.0, float(timeout))
    deadline = time.monotonic() + wait_timeout
    with _condition:
        if _pool is None:
            return
        _closing = True
        while _used and time.monotonic() < deadline:
            _condition.wait(timeout=min(0.25, max(0.0, deadline - time.monotonic())))
        pool = _pool
        _pool = None
        _database_url = ""
        _capacity = None
    pool.closeall()
    _log("DB_POOL_CLOSED")
    with _lock:
        _closing = False
