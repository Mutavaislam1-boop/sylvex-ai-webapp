"""Shared, cross-worker abuse protection for the website's email-based auth
endpoints (security audit finding RATE-1).

`/api/web/auth/login` was a PUBLIC_POST (exempt from the per-user quota
middleware in services/security.py), and login_email_account() had no
per-account failed-attempt counter or lockout at all - the only throttle
anywhere on it was the generic, process-local, per-IP request-rate guard,
which does nothing to slow down a password-guessing attack against one
specific account, from one IP or many. `/forgot-password` had no request
throttle either, which - since it always replies {"ok": true} regardless
of whether the email exists, specifically so the response body can't be
used to probe account existence - is instead an email-bombing /
timing-side-channel risk (sending the real reset email takes measurably
longer than the no-op "unknown email" path).

This module tracks attempts in Postgres, not a process-local dict, so the
limit is shared across every worker/replica - exactly like
provider_resilience.py's circuit-breaker tables already are for provider
calls, which this module deliberately mirrors (same advisory-lock-guarded
upsert pattern, same ready-flag-guarded schema setup).

Attempts are tracked by the identity string the caller passes in (e.g.
"login:<normalized-email>"), never by whether an account actually exists
for it - a non-existent email locks out on the exact same schedule as a
real one. That uniformity is what keeps the lockout itself from ever
being usable as an account-existence oracle: an attacker who sees
"too_many_attempts" after N tries learns nothing about whether the email
they tried is registered.
"""
from __future__ import annotations
import threading

from db_pool import db_connection

_SCHEMA_LOCK = threading.Lock()
_SCHEMA_READY = False

# Allow a handful of genuine typos before anything kicks in, then grow the
# lockout window exponentially (30s, 60s, 120s, ... capped at 1 hour) for
# each additional failure - the same exponential-backoff shape
# provider_resilience.retry_delay() already uses elsewhere in this codebase.
FAILURE_THRESHOLD = 5
BASE_LOCKOUT_SECONDS = 30.0
MAX_LOCKOUT_SECONDS = 3600.0


def ensure_rate_limit_table(database_url: str) -> None:
    global _SCHEMA_READY
    if _SCHEMA_READY or not database_url:
        return
    with _SCHEMA_LOCK:
        if _SCHEMA_READY:
            return
        with db_connection(database_url) as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT pg_advisory_xact_lock(%s)", (742193650,))
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS account_rate_limit_attempts (
                        identity TEXT PRIMARY KEY,
                        fail_count INTEGER NOT NULL DEFAULT 0,
                        locked_until TIMESTAMPTZ,
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                """)
        _SCHEMA_READY = True


def check_lockout(database_url: str, identity: str) -> dict:
    """Read-only: is `identity` currently locked out? Never mutates state,
    so checking alone never itself costs an attempt."""
    if not database_url or not identity:
        return {"locked": False, "retry_after": 0.0}
    ensure_rate_limit_table(database_url)
    with db_connection(database_url) as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT GREATEST(0, EXTRACT(EPOCH FROM (locked_until - NOW()))) "
                "FROM account_rate_limit_attempts WHERE identity = %s",
                (identity,),
            )
            row = cursor.fetchone()
    remaining = float(row[0]) if row and row[0] is not None else 0.0
    return {"locked": remaining > 0, "retry_after": remaining}


def record_failure(
    database_url: str,
    identity: str,
    threshold: int = FAILURE_THRESHOLD,
    base_seconds: float = BASE_LOCKOUT_SECONDS,
    max_seconds: float = MAX_LOCKOUT_SECONDS,
) -> dict:
    """Increments the failure counter for `identity` and, once `threshold`
    is reached, sets/extends an exponentially growing lockout window.
    Returns {"locked": bool, "retry_after": float, "fail_count": int}."""
    if not database_url or not identity:
        return {"locked": False, "retry_after": 0.0, "fail_count": 0}
    ensure_rate_limit_table(database_url)
    with db_connection(database_url) as conn:
        with conn.cursor() as cursor:
            # Per-identity advisory lock: two concurrent requests against
            # the same email (e.g. a parallelized brute-force) must not
            # race each other into under-counting failures.
            cursor.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (identity,))
            cursor.execute("""
                INSERT INTO account_rate_limit_attempts (identity, fail_count, updated_at)
                VALUES (%s, 1, NOW())
                ON CONFLICT (identity) DO UPDATE SET
                    fail_count = account_rate_limit_attempts.fail_count + 1,
                    updated_at = NOW()
                RETURNING fail_count
            """, (identity,))
            fail_count = int(cursor.fetchone()[0])
            retry_after = 0.0
            if fail_count >= threshold:
                retry_after = min(max_seconds, base_seconds * (2 ** (fail_count - threshold)))
                cursor.execute("""
                    UPDATE account_rate_limit_attempts
                    SET locked_until = NOW() + (%s * INTERVAL '1 second')
                    WHERE identity = %s
                """, (retry_after, identity))
    return {"locked": retry_after > 0, "retry_after": retry_after, "fail_count": fail_count}


def record_success(database_url: str, identity: str) -> None:
    """Clears any failure count/lockout for `identity` after a genuinely
    successful login - a real password typo elsewhere in the account's
    history must never keep counting against it once they get in."""
    if not database_url or not identity:
        return
    ensure_rate_limit_table(database_url)
    with db_connection(database_url) as conn:
        with conn.cursor() as cursor:
            cursor.execute("DELETE FROM account_rate_limit_attempts WHERE identity = %s", (identity,))
