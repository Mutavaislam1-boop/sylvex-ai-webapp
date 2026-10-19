"""Process-wide blocking PostgreSQL pool built on psycopg2's native pool."""

from __future__ import annotations

import os
import re
import sys
import threading
import time
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
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
DB_POOL_DIAGNOSTICS = os.getenv("DB_POOL_DIAGNOSTICS", "0").lower() in {"1", "true", "yes"}

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
_trace_job_id: ContextVar[str] = ContextVar("db_trace_job_id", default="")


def set_db_trace_job(job_id: str):
    """Tag DB work in this async job, including asyncio.to_thread calls."""
    return _trace_job_id.set(str(job_id or ""))


def reset_db_trace_job(token) -> None:
    _trace_job_id.reset(token)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def _sql_label(statement) -> str:
    """Retain the SQL action and relation, never parameter values or literals."""
    if not isinstance(statement, str):
        return "sql:dynamic"
    compact = re.sub(r"\s+", " ", statement.strip())
    match = re.search(
        r"\b(SELECT|UPDATE|INSERT\s+INTO|DELETE\s+FROM|CREATE\s+TABLE|"
        r"ALTER\s+TABLE|WITH|COMMIT|ROLLBACK)\b(?:\s+([\w.\"]+))?",
        compact, re.IGNORECASE,
    )
    if not match:
        return "sql:other"
    verb = match.group(1).upper().replace(" ", "_")
    relation = (match.group(2) or "").strip('"')
    if verb == "SELECT":
        from_match = re.search(r"\bFROM\s+([\w.\"]+)", compact, re.IGNORECASE)
        relation = from_match.group(1).strip('"') if from_match else ""
    return f"sql:{verb}:{relation}" if relation else f"sql:{verb}"


def _caller_site() -> str:
    """Name the application caller without retaining a frame or its arguments."""
    frame = sys._getframe(1)
    try:
        while frame is not None:
            path = frame.f_code.co_filename
            if path != __file__ and not path.endswith("contextlib.py"):
                return f"{os.path.basename(path)}:{frame.f_code.co_name}:{frame.f_lineno}"
            frame = frame.f_back
        return "unknown"
    finally:
        del frame


def _active_leases_locked() -> list[dict]:
    now = time.monotonic()
    return [
        {
            "connection_id": connection_id,
            "backend_pid": lease["backend_pid"],
            "thread_id": lease["thread_id"],
            "checkout_at_utc": lease["checkout_at_utc"],
            "held_so_far_ms": round((now - lease["checked_out_at"]) * 1000),
            "operation": lease["operation"],
            "call_site": lease["call_site"],
            "job_id": lease["job_id"],
            "phase": lease["phase"],
        }
        for connection_id, lease in _leases.items()
    ]


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
        leases = (
            _active_leases_locked()
            if DB_POOL_DIAGNOSTICS and status["free"] == 0 and status["waiting"] > 0
            else None
        )
    print("DB_POOL_STATUS:", status)
    if leases is not None:
        print("DB_POOL_LEASES:", {"captured_at_utc": _utc_now(), "leases": leases})


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


def _checkout_connection(
    database_url: str = "", timeout: Optional[float] = None,
    *, operation: str = "", call_site: str = "",
):
    """Wait on the driver's actual capacity and register one checked-out connection."""
    global _waiting
    checkout_call_started = time.monotonic()
    checkout_requested_at_utc = _utc_now()
    operation = str(operation or call_site or "unknown")
    url = str(database_url or _database_url or "").strip()
    if not url:
        raise RuntimeError("DATABASE_URL is not configured")
    start_db_pool(url)
    wait_timeout = DB_POOL_TIMEOUT_SECONDS if timeout is None else max(0.1, float(timeout))
    deadline = time.monotonic() + wait_timeout
    registered_waiter = False
    wait_started_at: Optional[float] = None
    wait_snapshot = None
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
                        wait_started_at = time.monotonic()
                        if DB_POOL_DIAGNOSTICS:
                            wait_snapshot = {
                                "captured_at_utc": _utc_now(),
                                "leases": _active_leases_locked(),
                            }
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
                    "checkout_at_utc": _utc_now(),
                    "backend_pid": (
                        connection.get_backend_pid()
                        if hasattr(connection, "get_backend_pid") else None
                    ),
                    "thread_id": threading.get_ident(),
                    "operation": operation,
                    "call_site": call_site,
                    "job_id": _trace_job_id.get(),
                    "phase": "acquired",
                }
                _check_invariant_locked()
                break
    finally:
        if registered_waiter:
            with _condition:
                _waiting = max(0, _waiting - 1)
                _check_invariant_locked()
                _condition.notify_all()
    if wait_started_at is not None:
        if wait_snapshot is not None:
            print("DB_POOL_LEASES_AT_WAIT:", wait_snapshot)
        # Every acquisition that actually had to wait for the pool gets its
        # own timing line, not just the rate-limited DB_POOL_WAIT snapshot -
        # this is the concrete number that answers "was this specific slow
        # generation step blocked on DB pool contention".
        print("DB_CONNECTION_WAIT_MS:", {
            "wait_ms": round((time.monotonic() - wait_started_at) * 1000),
            "thread_id": threading.get_ident(),
        })
    # A connection is already leased at this point. The status logger also
    # needs the pool lock, so its delay must count as checkout time, not SQL.
    driver_checkout_ms = round((time.monotonic() - checkout_call_started) * 1000)
    _leases[id(connection)]["phase"] = "checkout:status_log"
    _log_status_if_due()
    ready_to_log_at = time.monotonic()
    _leases[id(connection)]["phase"] = "checkout:emit_log"
    print("DB_CHECKOUT_MS:", {
        "checkout_ms": round((ready_to_log_at - checkout_call_started) * 1000),
        "driver_checkout_ms": driver_checkout_ms,
        "post_acquire_ms": round((ready_to_log_at - _leases[id(connection)]["checked_out_at"]) * 1000),
        "connection_id": id(connection),
        "backend_pid": _leases[id(connection)]["backend_pid"],
        "thread_id": threading.get_ident(),
        "checkout_requested_at_utc": checkout_requested_at_utc,
        "checkout_at_utc": _leases[id(connection)]["checkout_at_utc"],
        "operation": operation,
        "call_site": call_site,
        "job_id": _trace_job_id.get(),
    })
    _leases[id(connection)]["ready_at"] = time.monotonic()
    _leases[id(connection)]["phase"] = "caller:before_sql"
    return connection


def _return_connection(connection) -> None:
    """Rollback unfinished work, put the connection back, then wake waiters."""
    release_started_at = time.monotonic()
    release_started_at_utc = _utc_now()
    broken = bool(connection.closed)
    try:
        if not broken and connection.status != extensions.STATUS_READY:
            connection.rollback()
    except Exception:
        broken = True

    held_ms = None
    checkout_thread_id = None
    lease_details = {}
    with _condition:
        lease = _leases.pop(id(connection), None)
        if lease is None:
            return
        lease_details = {
            "checkout_at_utc": lease["checkout_at_utc"],
            "backend_pid": lease["backend_pid"],
            "operation": lease["operation"],
            "call_site": lease["call_site"],
            "job_id": lease["job_id"],
            "phase": lease["phase"],
            "pre_caller_ms": round(
                (lease.get("ready_at", release_started_at) - lease["checked_out_at"]) * 1000
            ),
            "caller_hold_ms": round(
                (release_started_at - lease.get("ready_at", lease["checked_out_at"])) * 1000
            ),
        }
        # Total time this connection was checked out, start to finish -
        # includes every cursor.execute() the caller ran, plus its own
        # commit/rollback, plus this release-time rollback-of-unfinished-work
        # above. This is the single number that answers "was this specific
        # checkout the one stuck for 100-200s" - a leak shows as never
        # appearing here at all; a stuck query/lock-wait shows as one huge
        # value here. Computed here (cheap) but printed only after releasing
        # the lock below - stdout I/O must never happen while holding
        # _condition, since every other checkout/release in the process
        # blocks on that same lock.
        held_ms = round((release_started_at - lease["checked_out_at"]) * 1000)
        checkout_thread_id = lease.get("thread_id")
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
    print("DB_CONNECTION_HELD_MS:", {
        "held_ms": held_ms,
        "connection_id": id(connection),
        "checkout_thread_id": checkout_thread_id,
        "release_thread_id": threading.get_ident(),
        "broken": broken,
        "release_started_at_utc": release_started_at_utc,
        "released_at_utc": _utc_now(),
        "pool_return_wait_ms": round((time.monotonic() - release_started_at) * 1000),
        **lease_details,
    })
    _log_status_if_due()


class _TraceCursor:
    """Diagnostic cursor proxy, used only when DB_POOL_DIAGNOSTICS is enabled."""

    def __init__(self, cursor, connection):
        self._cursor = cursor
        self._connection = connection

    def __getattr__(self, name):
        return getattr(self._cursor, name)

    def __iter__(self):
        return iter(self._cursor)

    def __enter__(self):
        self._cursor.__enter__()
        return self

    def __exit__(self, exc_type, exc, traceback):
        return self._cursor.__exit__(exc_type, exc, traceback)

    def execute(self, statement, parameters=None):
        self._connection.set_trace_phase(_sql_label(statement))
        try:
            return self._cursor.execute(statement, parameters)
        finally:
            self._connection.set_trace_phase("after:" + _sql_label(statement))

    def executemany(self, statement, parameters):
        self._connection.set_trace_phase(_sql_label(statement) + ":many")
        try:
            return self._cursor.executemany(statement, parameters)
        finally:
            self._connection.set_trace_phase("after:" + _sql_label(statement))

    def callproc(self, name, parameters=None):
        label = "sql:CALLPROC:" + re.sub(r"[^\w.]", "", str(name))[:64]
        self._connection.set_trace_phase(label)
        try:
            return self._cursor.callproc(name, parameters)
        finally:
            self._connection.set_trace_phase("after:" + label)


class PooledConnection:
    """Idempotent compatibility lease for existing conn.close() call sites."""

    def __init__(self, connection):
        self._connection = connection
        self._returned = False
        self._return_lock = threading.Lock()

    def __getattr__(self, name):
        return getattr(self._connection, name)

    def cursor(self, *args, **kwargs):
        cursor = self._connection.cursor(*args, **kwargs)
        return _TraceCursor(cursor, self) if DB_POOL_DIAGNOSTICS else cursor

    def set_trace_phase(self, phase: str) -> None:
        """Temporary diagnostic marker for the current SQL/commit stage."""
        if not DB_POOL_DIAGNOSTICS:
            return
        with _lock:
            lease = _leases.get(id(self._connection))
            if lease is not None:
                lease["phase"] = str(phase)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        try:
            if exc_type is None:
                self.set_trace_phase("commit:connection_context")
                self._connection.commit()
            else:
                self.set_trace_phase("rollback:connection_context")
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


def db_connect(
    database_url: str = "", timeout: Optional[float] = None, *, operation: str = "",
) -> PooledConnection:
    """Compatibility helper for existing code; close() returns its lease once."""
    return PooledConnection(_checkout_connection(
        database_url, timeout, operation=operation, call_site=_caller_site(),
    ))


@contextmanager
def db_connection(
    database_url: str = "", timeout: Optional[float] = None, *, operation: str = "",
):
    """Preferred explicit transaction/return helper for new and migrated code."""
    connection = PooledConnection(_checkout_connection(
        database_url, timeout, operation=operation, call_site=_caller_site(),
    ))
    body_started = time.monotonic()
    try:
        yield connection
        body_ms = round((time.monotonic() - body_started) * 1000)
        commit_started = time.monotonic()
        connection.set_trace_phase("commit:db_connection")
        connection.commit()
        # Splits held-time into "running the caller's own queries" vs
        # "committing" - a stuck cursor.execute() shows up in body_ms, a
        # stuck COMMIT (e.g. waiting on another session's uncommitted lock)
        # shows up in commit_ms instead.
        print("DB_CONNECTION_BODY_MS:", {
            "body_ms": body_ms,
            "commit_ms": round((time.monotonic() - commit_started) * 1000),
            "connection_id": id(connection._connection),
            "thread_id": threading.get_ident(),
        })
    except BaseException:
        body_ms = round((time.monotonic() - body_started) * 1000)
        rollback_started = time.monotonic()
        connection.set_trace_phase("rollback:db_connection")
        if not connection.closed:
            connection.rollback()
        print("DB_CONNECTION_BODY_MS:", {
            "body_ms": body_ms,
            "rollback_ms": round((time.monotonic() - rollback_started) * 1000),
            "connection_id": id(connection._connection),
            "thread_id": threading.get_ident(),
            "raised": True,
        })
        raise
    finally:
        connection.close()


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
