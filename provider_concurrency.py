"""PostgreSQL-backed global concurrency leases for AI providers."""

from __future__ import annotations

import asyncio
import os
import socket
import threading
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Callable, Optional
from uuid import uuid4

from db_pool import db_connection


SUPPORTED_PROVIDERS = {
    "KLING", "RUNWAY", "BYTEPLUS", "QWEN", "OPENAI", "GEMINI",
    "ELEVENLABS", "HEYGEN", "HEDRA", "HIGGSFIELD", "LUMA", "FLUX",
    "IDEOGRAM", "RECRAFT", "FASHN", "GROK",
}

PROVIDER_ALIASES = {
    "BYTEDANCE": "BYTEPLUS",
    "ARK": "BYTEPLUS",
    "GOOGLE": "GEMINI",
    "XAI": "GROK",
    "BFL": "FLUX",
    "BLACK_FOREST_LABS": "FLUX",
    "ELEVEN_LABS": "ELEVENLABS",
}


def normalize_provider(value: str) -> str:
    name = str(value or "").strip().upper().replace("-", "_").replace(" ", "_")
    return PROVIDER_ALIASES.get(name, name)


def provider_limit(provider: str) -> int:
    """Return a bounded configured limit; missing values default safely to 1."""
    normalized = normalize_provider(provider)
    raw = os.getenv(f"PROVIDER_CONCURRENCY_{normalized}", "1")
    try:
        value = int(str(raw).strip())
    except (TypeError, ValueError):
        value = 1
    return max(1, min(1000, value))


def _positive_float(name: str, default: float, minimum: float) -> float:
    try:
        value = float(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        value = default
    return max(minimum, value)


PROVIDER_SLOT_TTL_SECONDS = _positive_float("PROVIDER_SLOT_TTL_SECONDS", 180.0, 30.0)
PROVIDER_SLOT_HEARTBEAT_SECONDS = min(
    _positive_float("PROVIDER_SLOT_HEARTBEAT_SECONDS", 30.0, 5.0),
    PROVIDER_SLOT_TTL_SECONDS / 2,
)
PROVIDER_SLOT_WAIT_SECONDS = _positive_float("PROVIDER_SLOT_WAIT_SECONDS", 2.0, 0.2)
WORKER_ID = (
    os.getenv("PROSTUDIO_WORKER_ID")
    or os.getenv("RAILWAY_REPLICA_ID")
    or f"{socket.gethostname()}:{os.getpid()}:{uuid4().hex[:8]}"
)
_SCHEMA_LOCK = threading.Lock()
_SCHEMA_READY = False


@dataclass(frozen=True)
class SlotResult:
    acquired: bool
    active: int
    recovered: tuple[dict, ...] = ()


class ProviderSlotUnavailable(RuntimeError):
    """The provider is at capacity; the queue may defer this job safely."""


def ensure_provider_slot_table(database_url: str) -> None:
    global _SCHEMA_READY
    if _SCHEMA_READY:
        return
    with _SCHEMA_LOCK:
        if _SCHEMA_READY:
            return
        with db_connection(database_url) as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT pg_advisory_xact_lock(%s)", (742193602,))
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS prostudio_provider_slots (
                        provider TEXT NOT NULL,
                        job_id TEXT NOT NULL,
                        worker_id TEXT NOT NULL,
                        acquired_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        heartbeat_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        lease_until TIMESTAMPTZ NOT NULL,
                        PRIMARY KEY (provider, job_id)
                    )
                """)
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_prostudio_provider_slots_lease
                    ON prostudio_provider_slots (provider, lease_until)
                """)
            _SCHEMA_READY = True


def try_acquire_slot(database_url: str, provider: str, job_id: str, limit: int, worker_id: str) -> SlotResult:
    normalized = normalize_provider(provider)
    with db_connection(database_url) as conn:
      with conn.cursor() as cursor:
        # Serializes count+insert for this provider across all worker processes.
        cursor.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (f"prostudio-provider:{normalized}",))
        cursor.execute("""
            DELETE FROM prostudio_provider_slots
            WHERE provider = %s AND lease_until <= NOW()
            RETURNING job_id, worker_id
        """, (normalized,))
        recovered = tuple({"job_id": row[0], "worker_id": row[1]} for row in cursor.fetchall())

        cursor.execute("""
            SELECT worker_id FROM prostudio_provider_slots
            WHERE provider = %s AND job_id = %s
        """, (normalized, job_id))
        existing = cursor.fetchone()
        already_owned = bool(existing and existing[0] == worker_id)
        occupied_by_other_worker = bool(existing and existing[0] != worker_id)
        if already_owned:
            cursor.execute("""
                UPDATE prostudio_provider_slots
                SET worker_id = %s, heartbeat_at = NOW(),
                    lease_until = NOW() + (%s * INTERVAL '1 second')
                WHERE provider = %s AND job_id = %s
            """, (worker_id, PROVIDER_SLOT_TTL_SECONDS, normalized, job_id))
            acquired = True
        elif occupied_by_other_worker:
            acquired = False
        else:
            cursor.execute("""
                SELECT COUNT(*) FROM prostudio_provider_slots
                WHERE provider = %s AND lease_until > NOW()
            """, (normalized,))
            active = int(cursor.fetchone()[0])
            acquired = active < limit
            if acquired:
                cursor.execute("""
                    INSERT INTO prostudio_provider_slots
                        (provider, job_id, worker_id, acquired_at, heartbeat_at, lease_until)
                    VALUES (%s, %s, %s, NOW(), NOW(), NOW() + (%s * INTERVAL '1 second'))
                    ON CONFLICT (provider, job_id) DO NOTHING
                """, (normalized, job_id, worker_id, PROVIDER_SLOT_TTL_SECONDS))

        cursor.execute("""
            SELECT COUNT(*) FROM prostudio_provider_slots
            WHERE provider = %s AND lease_until > NOW()
        """, (normalized,))
        active = int(cursor.fetchone()[0])
        return SlotResult(acquired=acquired, active=active, recovered=recovered)


def heartbeat_slot(database_url: str, provider: str, job_id: str, worker_id: str) -> bool:
    with db_connection(database_url) as conn:
      with conn.cursor() as cursor:
        cursor.execute("""
            UPDATE prostudio_provider_slots
            SET heartbeat_at = NOW(), lease_until = NOW() + (%s * INTERVAL '1 second')
            WHERE provider = %s AND job_id = %s AND worker_id = %s
              AND lease_until > NOW()
        """, (PROVIDER_SLOT_TTL_SECONDS, normalize_provider(provider), job_id, worker_id))
        updated = cursor.rowcount == 1
        return updated


def release_slot(database_url: str, provider: str, job_id: str, worker_id: str) -> int:
    normalized = normalize_provider(provider)
    with db_connection(database_url) as conn:
      with conn.cursor() as cursor:
        cursor.execute("""
            DELETE FROM prostudio_provider_slots
            WHERE provider = %s AND job_id = %s AND worker_id = %s
        """, (normalized, job_id, worker_id))
        cursor.execute("""
            SELECT COUNT(*) FROM prostudio_provider_slots
            WHERE provider = %s AND lease_until > NOW()
        """, (normalized,))
        active = int(cursor.fetchone()[0])
        return active


@asynccontextmanager
async def provider_slot(
    database_url: str,
    provider: str,
    job_id: str,
    log: Callable[..., None],
    worker_id: Optional[str] = None,
    wait_for_slot: bool = True,
):
    """Wait for and maintain one global provider lease."""
    normalized = normalize_provider(provider)
    owner = worker_id or WORKER_ID
    limit = provider_limit(normalized)
    await asyncio.to_thread(ensure_provider_slot_table, database_url)
    last_wait_log = 0.0
    while True:
        outcome = await asyncio.to_thread(
            try_acquire_slot, database_url, normalized, job_id, limit, owner
        )
        for stale in outcome.recovered:
            log(
                "PROVIDER_SLOT_RECOVERED", provider=normalized, job_id=stale["job_id"],
                active=outcome.active, limit=limit, worker_id=stale["worker_id"],
            )
        if outcome.acquired:
            log(
                "PROVIDER_SLOT_ACQUIRED", provider=normalized, job_id=job_id,
                active=outcome.active, limit=limit, worker_id=owner,
            )
            break
        now = asyncio.get_running_loop().time()
        if now - last_wait_log >= 10.0:
            log(
                "PROVIDER_SLOT_WAITING", provider=normalized, job_id=job_id,
                active=outcome.active, limit=limit, worker_id=owner,
            )
            last_wait_log = now
        if not wait_for_slot:
            raise ProviderSlotUnavailable(f"Provider {normalized} is at capacity")
        await asyncio.sleep(PROVIDER_SLOT_WAIT_SECONDS)

    stopped = asyncio.Event()

    async def maintain_lease() -> None:
        while not stopped.is_set():
            try:
                await asyncio.wait_for(stopped.wait(), timeout=PROVIDER_SLOT_HEARTBEAT_SECONDS)
                return
            except asyncio.TimeoutError:
                alive = await asyncio.to_thread(
                    heartbeat_slot, database_url, normalized, job_id, owner
                )
                if not alive:
                    raise RuntimeError(f"Provider slot lease lost: {normalized}/{job_id}")

    heartbeat_task = asyncio.create_task(maintain_lease(), name=f"provider-slot-{normalized}-{job_id}")
    try:
        yield normalized
        if heartbeat_task.done():
            heartbeat_task.result()
    finally:
        stopped.set()
        await asyncio.gather(heartbeat_task, return_exceptions=True)
        active = await asyncio.to_thread(release_slot, database_url, normalized, job_id, owner)
        log(
            "PROVIDER_SLOT_RELEASED", provider=normalized, job_id=job_id,
            active=active, limit=limit, worker_id=owner,
        )
