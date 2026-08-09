"""Process-wide blocking PostgreSQL pool built on psycopg2's native pool."""

from __future__ import annotations

import os
import threading
import time
from contextlib import contextmanager
from typing import Optional

from psycopg2 import extensions
from psycopg2.pool import PoolError, ThreadedConnectionPool


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
_leases: dict[int, dict] = {}
_waiting = 0
_closing = False
_last_status_log = 0.0
_last_wait_log = 0.0
_invariant_since: Optional[float] = None
_last_invariant_log = 0.0


def _pool_size_locked() -> int:
    if _pool is None:
        return 0
    # psycopg2 does not expose metrics publicly. These two collections are the
    # driver's own idle and checked-out connection registries.
    return len(getattr(_pool, "_pool", ())) + len(getattr(_pool, "_used", {}))


def _snapshot_locked() -> dict:
    used = len(_leases)
    free = max(0, DB_POOL_MAX_SIZE - used)
    return {
        "min_size": DB_POOL_MIN_SIZE,
        "max_size": DB_POOL_MAX_SIZE,
        "used": used,
        "free": free,
        "waiting": _waiting,
        # There is intentionally no second semaphore anymore. This value is
        # the number of logical checkout permits derived from the sole source
        # of truth: actual checked-out driver connections.
        "semaphore_available": free,
        "pool_size": _pool_size_locked(),
    }


def _snapshot() -> dict:
    with _lock:
        return _snapshot_locked()


def _log(event: str) -> None:
    print(f"{event}:", _snapshot())


def _check_invariant_locked() -> None:
    global _invariant_since, _last_invariant_log
    status = _snapshot_locked()
    now = time.monotonic()
    if status["free"] > 0 and status["waiting"] > 0:
        if _invariant_since is None:
            _invariant_since = now
            _condition.notify_all()
        elif now - _invariant_since >= 0.5 and now - _last_invariant_log >= 5.0:
            _last_invariant_log = now
            print("DB_POOL_INVARIANT_WARNING:", {
                key: status[key]
                for key in ("used", "free", "waiting", "semaphore_available", "pool_size")
            })
            _condition.notify_all()
    else:
        _invariant_since = None


def _log_status_if_due(force: bool = False) -> None:
    global _last_status_log
    now = time.monotonic()
    with _condition:
        _check_invariant_locked()
        if not force and now - _last_status_log < 30.0:
            return
        _last_status_log = now
        status = _snapshot_locked()
    print("DB_POOL_STATUS:", status)


def _log_wait_if_due() -> None:
    global _last_wait_log
    now = time.monotonic()
    with _lock:
        if now - _last_wait_log < 1.0:
            return
        _last_wait_log = now
        status = _snapshot_locked()
    print("DB_POOL_WAIT:", status)


def start_db_pool(database_url: str) -> None:
    """Start the single pool for this process; safe to call repeatedly."""
    global _pool, _database_url, _closing
    global DB_POOL_MIN_SIZE, DB_POOL_MAX_SIZE, DB_POOL_TIMEOUT_SECONDS
    url = str(database_url or "").strip()
    if not url:
        return
    with _condition:
        if _pool is not None:
            if _database_url != url:
                raise RuntimeError("PostgreSQL pool is already configured with another DATABASE_URL")
            return
        DB_POOL_MAX_SIZE = _bounded_int("DB_POOL_MAX_SIZE", 10, 1, 100)
        DB_POOL_MIN_SIZE = min(_bounded_int("DB_POOL_MIN_SIZE", 2, 1, 100), DB_POOL_MAX_SIZE)
        DB_POOL_TIMEOUT_SECONDS = _positive_float("DB_POOL_TIMEOUT_SECONDS", 30.0, 0.1)
        _pool = ThreadedConnectionPool(DB_POOL_MIN_SIZE, DB_POOL_MAX_SIZE, dsn=url)
        _database_url = url
        _closing = False
        status = _snapshot_locked()
    print("DB_POOL_STARTED:", status)
    _log_status_if_due(force=True)


def _checkout_connection(database_url: str = "", timeout: Optional[float] = None):
    """Wait on the driver's actual capacity and register one checked-out connection."""
    global _waiting
    url = str(database_url or _database_url or "").strip()
    if not url:
        raise RuntimeError("DATABASE_URL is not configured")
    start_db_pool(url)
    wait_timeout = DB_POOL_TIMEOUT_SECONDS if timeout is None else max(0.1, float(timeout))
    deadline = time.monotonic() + wait_timeout
    registered_waiter = False
    try:
        with _condition:
            while True:
                if _closing or _pool is None:
                    raise RuntimeError("PostgreSQL pool is closing")
                try:
                    connection = _pool.getconn()
                except PoolError:
                    if not registered_waiter:
                        _waiting += 1
                        registered_waiter = True
                        _log_wait_if_due()
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        _log_status_if_due(force=True)
                        raise TimeoutError(
                            f"Timed out waiting {wait_timeout:g}s for a PostgreSQL connection"
                        )
                    _check_invariant_locked()
                    _condition.wait(timeout=min(0.25, remaining))
                    continue

                if registered_waiter:
                    _waiting = max(0, _waiting - 1)
                    registered_waiter = False
                _leases[id(connection)] = {
                    "connection": connection,
                    "checked_out_at": time.monotonic(),
                    "thread_id": threading.get_ident(),
                }
                _check_invariant_locked()
                break
    finally:
        if registered_waiter:
            with _condition:
                _waiting = max(0, _waiting - 1)
                _check_invariant_locked()
                _condition.notify_all()
    _log_status_if_due()
    return connection


def _return_connection(connection) -> None:
    """Rollback unfinished work, put the connection back, then wake waiters."""
    broken = bool(connection.closed)
    try:
        if not broken and connection.status != extensions.STATUS_READY:
            connection.rollback()
    except Exception:
        broken = True

    with _condition:
        lease = _leases.pop(id(connection), None)
        if lease is None:
            return
        pool = _pool
        try:
            if pool is None:
                if not connection.closed:
                    connection.close()
            else:
                pool.putconn(connection, close=broken)
        finally:
            _check_invariant_locked()
            _condition.notify_all()
    _log_status_if_due()


class PooledConnection:
    """Idempotent compatibility lease for existing conn.close() call sites."""

    def __init__(self, connection):
        self._connection = connection
        self._returned = False
        self._return_lock = threading.Lock()

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
        with self._return_lock:
            if self._returned:
                return
            self._returned = True
        _return_connection(self._connection)


def db_connect(database_url: str = "", timeout: Optional[float] = None) -> PooledConnection:
    """Compatibility helper for existing code; close() returns its lease once."""
    return PooledConnection(_checkout_connection(database_url, timeout))


@contextmanager
def db_connection(database_url: str = "", timeout: Optional[float] = None):
    """Preferred explicit transaction/return helper for new and migrated code."""
    connection = _checkout_connection(database_url, timeout)
    try:
        yield connection
        connection.commit()
    except BaseException:
        if not connection.closed:
            connection.rollback()
        raise
    finally:
        _return_connection(connection)


def db_pool_status() -> dict:
    with _condition:
        _check_invariant_locked()
        status = _snapshot_locked()
    print("DB_POOL_STATUS:", status)
    return status


def close_db_pool(timeout: Optional[float] = None) -> None:
    """Stop new checkouts, wait for borrowers, then close all driver connections."""
    global _pool, _database_url, _closing
    wait_timeout = DB_POOL_TIMEOUT_SECONDS if timeout is None else max(0.0, float(timeout))
    deadline = time.monotonic() + wait_timeout
    with _condition:
        if _pool is None:
            return
        _closing = True
        _condition.notify_all()
        while _leases and time.monotonic() < deadline:
            _condition.wait(timeout=min(0.25, max(0.0, deadline - time.monotonic())))
        pool = _pool
        status = _snapshot_locked()
        _pool = None
        _database_url = ""
    pool.closeall()
    print("DB_POOL_CLOSED:", status)
    with _condition:
        _closing = False
        _condition.notify_all()
