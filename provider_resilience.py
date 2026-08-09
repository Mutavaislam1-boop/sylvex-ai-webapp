"""Global PostgreSQL circuit breaker and provider retry classification."""

from __future__ import annotations

import asyncio
import inspect
import os
import random
import re
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Optional

import requests

from db_pool import db_connection
from provider_concurrency import normalize_provider


TRANSIENT_HTTP_STATUSES = {429, 500, 502, 503, 504}
PERMANENT_HTTP_STATUSES = {400, 401, 402, 403, 404}
_SCHEMA_LOCK = threading.Lock()
_SCHEMA_READY = False


def _bounded_int(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(str(os.getenv(name, default)).strip())
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(maximum, value))


def _positive_float(name: str, default: float, minimum: float, maximum: float) -> float:
    try:
        value = float(str(os.getenv(name, default)).strip())
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(maximum, value))


def retry_max_attempts() -> int:
    return _bounded_int("PROVIDER_RETRY_MAX_ATTEMPTS", 3, 1, 10)


def retry_base_delay() -> float:
    return _positive_float("PROVIDER_RETRY_BASE_DELAY_SECONDS", 2.0, 0.0, 300.0)


def retry_max_delay() -> float:
    return _positive_float("PROVIDER_RETRY_MAX_DELAY_SECONDS", 30.0, 0.1, 600.0)


def circuit_failure_threshold() -> int:
    return _bounded_int("PROVIDER_CIRCUIT_FAILURE_THRESHOLD", 5, 1, 100)


def circuit_open_seconds() -> float:
    return _positive_float("PROVIDER_CIRCUIT_OPEN_SECONDS", 60.0, 1.0, 86400.0)


def circuit_half_open_probes() -> int:
    return _bounded_int("PROVIDER_CIRCUIT_HALF_OPEN_PROBES", 1, 1, 20)


@dataclass(frozen=True)
class FailureClassification:
    transient: bool
    status_code: Optional[int]
    retry_after: Optional[float]
    reason: str


def _walk_values(value: Any, depth: int = 0):
    if depth > 5:
        return
    if isinstance(value, dict):
        for key, item in value.items():
            yield str(key).lower(), item
            yield from _walk_values(item, depth + 1)
    elif isinstance(value, (list, tuple)):
        for item in value[:30]:
            yield from _walk_values(item, depth + 1)


def _status_code(value: Any) -> Optional[int]:
    if isinstance(value, requests.HTTPError) and value.response is not None:
        return int(value.response.status_code)
    for key, item in _walk_values(value):
        if key not in {"status", "status_code", "http_status", "http_code", "code"}:
            continue
        try:
            code = int(item)
        except (TypeError, ValueError):
            continue
        if 100 <= code <= 599:
            return code
    text = str(value or "")
    match = re.search(r"(?:HTTP(?:\s+status)?[ :=]|status[ :=])\s*(\d{3})", text, re.I)
    return int(match.group(1)) if match else None


def _retry_after(value: Any) -> Optional[float]:
    def parse(raw: Any) -> Optional[float]:
        try:
            return max(0.0, float(raw))
        except (TypeError, ValueError):
            pass
        try:
            retry_at = parsedate_to_datetime(str(raw))
            if retry_at.tzinfo is None:
                retry_at = retry_at.replace(tzinfo=timezone.utc)
            return max(0.0, (retry_at - datetime.now(timezone.utc)).total_seconds())
        except (TypeError, ValueError, OverflowError):
            return None

    if isinstance(value, requests.HTTPError) and value.response is not None:
        parsed = parse(value.response.headers.get("Retry-After"))
        if parsed is not None:
            return parsed
    for key, item in _walk_values(value):
        if key.replace("-", "_") not in {"retry_after", "retry_after_seconds"}:
            continue
        parsed = parse(item)
        if parsed is not None:
            return parsed
    return None


def classify_provider_failure(value: Any) -> FailureClassification:
    status = _status_code(value)
    retry_after = _retry_after(value)
    text = str(value or "").lower()
    if isinstance(value, dict):
        text = " ".join(str(item).lower() for _, item in _walk_values(value))

    if status in TRANSIENT_HTTP_STATUSES:
        return FailureClassification(True, status, retry_after, f"http_{status}")
    if status in PERMANENT_HTTP_STATUSES:
        return FailureClassification(False, status, None, f"http_{status}")
    if isinstance(value, (TimeoutError, requests.Timeout)):
        return FailureClassification(True, status, retry_after, "timeout")
    if isinstance(value, (ConnectionError, requests.ConnectionError)):
        return FailureClassification(True, status, retry_after, "connection_error")

    permanent_markers = (
        "insufficient balance", "insufficient_balance", "payment required",
        "billing hard limit", "invalid parameter", "invalid_parameter",
        "validation error", "validation_error", "unauthorized", "forbidden",
        "not found", "unsupported model", "payload is not valid",
    )
    if any(marker in text for marker in permanent_markers):
        return FailureClassification(False, status, None, "permanent_provider_error")
    transient_markers = (
        "readtimeout", "connecttimeout", "timed out", "timeout",
        "connection reset", "connection refused", "connection aborted",
        "temporarily unavailable", "temporary error", "service unavailable",
        "too many requests", "rate limit", "rate_limit", "server error",
        "bad gateway", "gateway timeout",
    )
    if any(marker in text for marker in transient_markers):
        return FailureClassification(True, status, retry_after, "temporary_provider_error")
    return FailureClassification(False, status, None, "unclassified_permanent_error")


def retry_delay(attempt: int, retry_after: Optional[float] = None) -> float:
    maximum = retry_max_delay()
    base = retry_base_delay()
    raw = retry_after if retry_after is not None else base * (2 ** max(0, attempt - 1))
    bounded = min(maximum, max(0.0, float(raw)))
    jitter = random.uniform(0.0, min(1.0, bounded * 0.25)) if bounded else 0.0
    return min(maximum, bounded + jitter)


async def run_with_provider_retry(
    provider: str,
    job_id: str,
    operation,
    record_outcome,
    log,
    worker_id: str,
    sleep=asyncio.sleep,
) -> dict:
    """Execute a provider operation with retry; dependencies are injectable for tests."""
    # The setting is the number of retries after the initial request. Three
    # retries therefore produce attempts 1..4 and delays 2s, 4s, 8s.
    attempts = retry_max_attempts() + 1
    circuit_state = "CLOSED"
    failure_count = 0

    async def record(transient: bool) -> dict:
        value = record_outcome(transient)
        return await value if inspect.isawaitable(value) else value

    for attempt in range(1, attempts + 1):
        log(
            "PROVIDER_RETRY_ATTEMPT", provider=provider, job_id=job_id,
            attempt=attempt, status_code="", delay=0,
            circuit_state=circuit_state, failure_count=failure_count,
            worker_id=worker_id,
        )
        try:
            result = await operation()
        except Exception as exc:
            result = {"ok": False, "error": str(exc), "exception_type": type(exc).__name__}
            classification = classify_provider_failure(exc)
        else:
            classification = classify_provider_failure(result)

        if isinstance(result, dict) and result.get("ok"):
            outcome = await record(False)
            if outcome.get("closed"):
                log(
                    "PROVIDER_CIRCUIT_CLOSED", provider=provider, job_id=job_id,
                    attempt=attempt, status_code=classification.status_code or "",
                    delay=0, circuit_state=outcome.get("state") or "CLOSED",
                    failure_count=int(outcome.get("failure_count") or 0), worker_id=worker_id,
                )
            return result

        if not classification.transient:
            outcome = await record(False)
            if outcome.get("closed"):
                log(
                    "PROVIDER_CIRCUIT_CLOSED", provider=provider, job_id=job_id,
                    attempt=attempt, status_code=classification.status_code or "",
                    delay=0, circuit_state=outcome.get("state") or "CLOSED",
                    failure_count=int(outcome.get("failure_count") or 0), worker_id=worker_id,
                )
            return result

        outcome = await record(True)
        circuit_state = outcome.get("state") or "CLOSED"
        failure_count = int(outcome.get("failure_count") or 0)
        if outcome.get("opened"):
            log(
                "PROVIDER_CIRCUIT_OPENED", provider=provider, job_id=job_id,
                attempt=attempt, status_code=classification.status_code or "",
                delay=0, circuit_state=circuit_state, failure_count=failure_count,
                worker_id=worker_id,
            )
        if attempt >= attempts or circuit_state == "OPEN":
            return result

        delay = retry_delay(attempt, classification.retry_after)
        log(
            "PROVIDER_RETRY_SCHEDULED", provider=provider, job_id=job_id,
            attempt=attempt, status_code=classification.status_code or "",
            delay=round(delay, 3), circuit_state=circuit_state,
            failure_count=failure_count, worker_id=worker_id,
        )
        await sleep(delay)
    return {"ok": False, "error": "Provider retry attempts exhausted"}


def ensure_provider_circuit_tables(database_url: str) -> None:
    global _SCHEMA_READY
    if _SCHEMA_READY:
        return
    with _SCHEMA_LOCK:
        if _SCHEMA_READY:
            return
        with db_connection(database_url) as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT pg_advisory_xact_lock(%s)", (742193603,))
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS prostudio_provider_circuits (
                        provider TEXT PRIMARY KEY,
                        state TEXT NOT NULL DEFAULT 'CLOSED',
                        failure_count INTEGER NOT NULL DEFAULT 0,
                        opened_until TIMESTAMPTZ,
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                """)
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS prostudio_provider_circuit_probes (
                        provider TEXT NOT NULL,
                        job_id TEXT NOT NULL,
                        worker_id TEXT NOT NULL,
                        lease_until TIMESTAMPTZ NOT NULL,
                        PRIMARY KEY (provider, job_id)
                    )
                """)
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_provider_circuit_probe_lease
                    ON prostudio_provider_circuit_probes (provider, lease_until)
                """)
        _SCHEMA_READY = True


def circuit_before_request(database_url: str, provider: str, job_id: str, worker_id: str) -> dict:
    normalized = normalize_provider(provider)
    ensure_provider_circuit_tables(database_url)
    probes = circuit_half_open_probes()
    probe_ttl = max(30.0, circuit_open_seconds() * 2)
    with db_connection(database_url) as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (f"prostudio-circuit:{normalized}",))
            cursor.execute("""
                INSERT INTO prostudio_provider_circuits (provider)
                VALUES (%s) ON CONFLICT (provider) DO NOTHING
            """, (normalized,))
            cursor.execute("""
                DELETE FROM prostudio_provider_circuit_probes
                WHERE provider = %s AND lease_until <= NOW()
            """, (normalized,))
            cursor.execute("""
                SELECT state, failure_count,
                       GREATEST(0, COALESCE(EXTRACT(EPOCH FROM (opened_until - NOW())), 0))
                FROM prostudio_provider_circuits WHERE provider = %s FOR UPDATE
            """, (normalized,))
            state, failure_count, remaining = cursor.fetchone()
            transition = ""
            if state == "OPEN" and float(remaining or 0) <= 0:
                state = "HALF_OPEN"
                transition = "HALF_OPEN"
                cursor.execute("""
                    UPDATE prostudio_provider_circuits
                    SET state = 'HALF_OPEN', opened_until = NULL, updated_at = NOW()
                    WHERE provider = %s
                """, (normalized,))
            if state == "OPEN":
                return {"allowed": False, "state": state, "failure_count": failure_count, "wait_seconds": max(1.0, float(remaining or 1)), "transition": transition, "probe": False}
            if state == "HALF_OPEN":
                cursor.execute("""
                    SELECT COUNT(*) FROM prostudio_provider_circuit_probes
                    WHERE provider = %s AND lease_until > NOW()
                """, (normalized,))
                active_probes = int(cursor.fetchone()[0])
                cursor.execute("""
                    SELECT 1 FROM prostudio_provider_circuit_probes
                    WHERE provider = %s AND job_id = %s
                """, (normalized, job_id))
                owns_probe = cursor.fetchone() is not None
                if not owns_probe and active_probes >= probes:
                    return {"allowed": False, "state": state, "failure_count": failure_count, "wait_seconds": 1.0, "transition": transition, "probe": False}
                cursor.execute("""
                    INSERT INTO prostudio_provider_circuit_probes
                        (provider, job_id, worker_id, lease_until)
                    VALUES (%s, %s, %s, NOW() + (%s * INTERVAL '1 second'))
                    ON CONFLICT (provider, job_id) DO UPDATE SET
                        worker_id = EXCLUDED.worker_id,
                        lease_until = EXCLUDED.lease_until
                """, (normalized, job_id, worker_id, probe_ttl))
                return {"allowed": True, "state": state, "failure_count": failure_count, "wait_seconds": 0.0, "transition": transition, "probe": True}
            return {"allowed": True, "state": "CLOSED", "failure_count": failure_count, "wait_seconds": 0.0, "transition": transition, "probe": False}


def circuit_record_outcome(database_url: str, provider: str, job_id: str, transient_failure: bool) -> dict:
    normalized = normalize_provider(provider)
    threshold = circuit_failure_threshold()
    open_seconds = circuit_open_seconds()
    with db_connection(database_url) as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (f"prostudio-circuit:{normalized}",))
            cursor.execute("""
                INSERT INTO prostudio_provider_circuits (provider)
                VALUES (%s) ON CONFLICT (provider) DO NOTHING
            """, (normalized,))
            cursor.execute("""
                SELECT state, failure_count FROM prostudio_provider_circuits
                WHERE provider = %s FOR UPDATE
            """, (normalized,))
            previous_state, failure_count = cursor.fetchone()
            cursor.execute("""
                DELETE FROM prostudio_provider_circuit_probes
                WHERE provider = %s AND job_id = %s
            """, (normalized, job_id))
            if not transient_failure:
                cursor.execute("""
                    UPDATE prostudio_provider_circuits
                    SET state = 'CLOSED', failure_count = 0,
                        opened_until = NULL, updated_at = NOW()
                    WHERE provider = %s
                """, (normalized,))
                return {"state": "CLOSED", "previous_state": previous_state, "failure_count": 0, "opened": False, "closed": previous_state != "CLOSED"}

            new_count = int(failure_count or 0) + 1
            should_open = previous_state == "HALF_OPEN" or new_count >= threshold
            if should_open:
                cursor.execute("""
                    UPDATE prostudio_provider_circuits
                    SET state = 'OPEN', failure_count = %s,
                        opened_until = NOW() + (%s * INTERVAL '1 second'),
                        updated_at = NOW()
                    WHERE provider = %s
                """, (new_count, open_seconds, normalized))
                return {"state": "OPEN", "previous_state": previous_state, "failure_count": new_count, "opened": previous_state != "OPEN", "closed": False}
            cursor.execute("""
                UPDATE prostudio_provider_circuits
                SET failure_count = %s, updated_at = NOW()
                WHERE provider = %s
            """, (new_count, normalized))
            return {"state": previous_state, "previous_state": previous_state, "failure_count": new_count, "opened": False, "closed": False}


def circuit_release_probe(database_url: str, provider: str, job_id: str) -> None:
    """Release a HALF_OPEN probe when a job exits before recording an outcome."""
    with db_connection(database_url) as conn:
        with conn.cursor() as cursor:
            cursor.execute("""
                DELETE FROM prostudio_provider_circuit_probes
                WHERE provider = %s AND job_id = %s
            """, (normalize_provider(provider), job_id))
