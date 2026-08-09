"""Read-only publication layer for completed Pro Studio generations."""

from __future__ import annotations

import json
import secrets
import threading
from datetime import datetime
from typing import Any, Callable


_SCHEMA_LOCK = threading.Lock()
_SCHEMA_READY = False


def _obj(value: Any) -> dict:
    if isinstance(value, dict):
        return value
    if not value:
        return {}
    try:
        parsed = json.loads(value)
        return parsed if isinstance(parsed, dict) else {}
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}


def _iso(value: Any) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value or "")


def ensure_share_table(connect: Callable[[], Any]) -> None:
    global _SCHEMA_READY
    if _SCHEMA_READY:
        return
    with _SCHEMA_LOCK:
        if _SCHEMA_READY:
            return
        conn = connect()
        cursor = conn.cursor()
        try:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS prostudio_generation_shares (
                    id BIGSERIAL PRIMARY KEY,
                    share_id TEXT UNIQUE NOT NULL,
                    job_id TEXT UNIQUE NOT NULL,
                    owner_telegram_id BIGINT NOT NULL,
                    owner_username TEXT,
                    mode TEXT NOT NULL,
                    provider TEXT,
                    model TEXT,
                    prompt TEXT DEFAULT '',
                    cost JSONB DEFAULT '{}'::jsonb,
                    generation_time DOUBLE PRECISION,
                    media_url TEXT NOT NULL,
                    thumbnail_url TEXT,
                    public_metadata JSONB DEFAULT '{}'::jsonb,
                    created_at TIMESTAMP DEFAULT NOW(),
                    downloads BIGINT DEFAULT 0,
                    views BIGINT DEFAULT 0,
                    allow_download BOOLEAN DEFAULT TRUE,
                    allow_reference BOOLEAN DEFAULT TRUE,
                    is_public BOOLEAN DEFAULT TRUE,
                    is_deleted BOOLEAN DEFAULT FALSE
                )
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_prostudio_shares_public
                ON prostudio_generation_shares (share_id)
                WHERE is_public = TRUE AND is_deleted = FALSE
            """)
            conn.commit()
            _SCHEMA_READY = True
        except Exception:
            conn.rollback()
            raise
        finally:
            cursor.close()
            conn.close()


def _new_share_id() -> str:
    return secrets.token_urlsafe(12).replace("-", "").replace("_", "")[:18]


def create_or_get_share(
    connect: Callable[[], Any],
    *,
    job_id: str,
    owner_telegram_id: int,
    owner_username: str,
    mode: str,
    provider: str,
    model: str,
    prompt: str,
    cost: dict,
    generation_time: float | None,
    media_url: str,
    thumbnail_url: str,
    public_metadata: dict,
) -> dict:
    ensure_share_table(connect)
    conn = connect()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT share_id FROM prostudio_generation_shares
            WHERE job_id = %s AND owner_telegram_id = %s
            LIMIT 1
        """, (job_id, owner_telegram_id))
        existing = cursor.fetchone()
        if existing:
            return {"share_id": existing[0], "created": False}

        for _ in range(5):
            share_id = _new_share_id()
            try:
                cursor.execute("""
                    INSERT INTO prostudio_generation_shares (
                        share_id, job_id, owner_telegram_id, owner_username,
                        mode, provider, model, prompt, cost, generation_time,
                        media_url, thumbnail_url, public_metadata
                    ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s,%s,%s::jsonb)
                    ON CONFLICT (job_id) DO NOTHING
                    RETURNING share_id
                """, (
                    share_id, job_id, owner_telegram_id, owner_username or None,
                    mode, provider, model, prompt,
                    json.dumps(cost or {}, ensure_ascii=False), generation_time,
                    media_url, thumbnail_url or None,
                    json.dumps(public_metadata or {}, ensure_ascii=False),
                ))
                inserted = cursor.fetchone()
                conn.commit()
                if inserted:
                    return {"share_id": inserted[0], "created": True}
                cursor.execute("SELECT share_id FROM prostudio_generation_shares WHERE job_id = %s", (job_id,))
                existing = cursor.fetchone()
                if existing:
                    return {"share_id": existing[0], "created": False}
            except Exception as exc:
                conn.rollback()
                if getattr(exc, "pgcode", "") != "23505":
                    raise
        raise RuntimeError("share_id_generation_failed")
    finally:
        cursor.close()
        conn.close()


def get_public_share(connect: Callable[[], Any], share_id: str, increment_views: bool = False) -> dict | None:
    ensure_share_table(connect)
    conn = connect()
    cursor = conn.cursor()
    try:
        if increment_views:
            cursor.execute("""
                UPDATE prostudio_generation_shares
                SET views = views + 1
                WHERE share_id = %s AND is_public = TRUE AND is_deleted = FALSE
            """, (share_id,))
        cursor.execute("""
            SELECT share_id, owner_username, mode, provider, model, prompt, cost,
                   generation_time, media_url, thumbnail_url, public_metadata,
                   created_at, downloads, views, allow_download, allow_reference
            FROM prostudio_generation_shares
            WHERE share_id = %s AND is_public = TRUE AND is_deleted = FALSE
            LIMIT 1
        """, (share_id,))
        row = cursor.fetchone()
        if increment_views:
            conn.commit()
        if not row:
            return None
        return {
            "share_id": row[0],
            "author": f"@{row[1].lstrip('@')}" if row[1] else "",
            "mode": row[2], "provider": row[3] or "", "model": row[4] or "",
            "prompt": row[5] or "", "cost": _obj(row[6]),
            "generation_time": row[7], "media_url": row[8],
            "thumbnail_url": row[9] or "", "metadata": _obj(row[10]),
            "created_at": _iso(row[11]), "downloads": int(row[12] or 0),
            "views": int(row[13] or 0), "allow_download": bool(row[14]),
            "allow_reference": bool(row[15]),
        }
    finally:
        cursor.close()
        conn.close()


def increment_downloads(connect: Callable[[], Any], share_id: str) -> None:
    conn = connect()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            UPDATE prostudio_generation_shares SET downloads = downloads + 1
            WHERE share_id = %s AND is_public = TRUE AND is_deleted = FALSE
        """, (share_id,))
        conn.commit()
    finally:
        cursor.close()
        conn.close()
