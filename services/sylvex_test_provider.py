"""SYLVEX Test: a mock provider that replaces only the external AI/provider
call for admin/developer-authorized requests. Everything before this point
(validation, balance/credit reservation, job creation, queueing) and after
(storage persistence, history, refund) is the real production pipeline - see
main.py's hooks into image_generation()/video_generation()/
poll_video_generation()/audio_generation()/call_text_provider(), all gated on
the caller already having set payload["_sylvex_test_authorized"] = True
(main.py's _sylvex_test_permitted(), checked once per request at the
platform-aware Telegram-vs-Website identity boundary - never re-derived
here).

Architecture: one shared "mailbox" table, sylvex_test_requests. submit()
inserts a row and pushes a notification to every sylvex_test-permitted admin
via the existing Support Bot's own Bot API token (SUPPORT_BOT_TOKEN - a
second shared secret alongside ADMIN_SERVICE_TOKEN, flowing the other
direction). wait_for_response()/wait_for_response_sync() then poll that same
row until a developer resolves it from the Support Bot - Success/Processing/
Failed/Moderation/Timeout. "Hanging" needs no code here: if nobody ever
responds, this keeps polling until the caller's own job-level stale/timeout
handling takes over, exactly like a real hung provider.
"""
from __future__ import annotations

import json
import os
import time
import uuid
from typing import Any, Optional

import requests

POLL_INTERVAL_SECONDS = 2.0
# Generous - a human has to notice the push, open the Support Bot and act.
# Longer than this and the job's own stale-job requeue/timeout handling
# takes over, exactly like a real provider that never responded ("Hanging").
MAX_WAIT_SECONDS = 30 * 60

SUPPORT_BOT_TOKEN = os.getenv("SUPPORT_BOT_TOKEN", "").strip()


def ensure_sylvex_test_table(connect) -> None:
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS sylvex_test_requests (
                    id TEXT PRIMARY KEY,
                    platform TEXT NOT NULL,
                    category TEXT NOT NULL,
                    requester_id BIGINT,
                    requester_account_id BIGINT,
                    job_id TEXT,
                    grid_run_id TEXT,
                    grid_node_id TEXT,
                    model TEXT,
                    original_prompt TEXT,
                    final_prompt TEXT,
                    parameters JSONB NOT NULL DEFAULT '{}'::jsonb,
                    reference_urls JSONB NOT NULL DEFAULT '[]'::jsonb,
                    status TEXT NOT NULL DEFAULT 'waiting',
                    outcome TEXT,
                    result_json JSONB,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    responded_at TIMESTAMPTZ
                )
            """)
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_sylvex_test_requests_status "
                "ON sylvex_test_requests(status, created_at)"
            )


def _notify_admins(connect, request_id: str, summary: dict) -> None:
    """Best-effort push to every sylvex_test-permitted admin's chat with the
    Support Bot. Never raises: a push failure must never block or fail the
    underlying generation - the manual queue view in the Support Bot still
    works even if this silently didn't arrive."""
    if not SUPPORT_BOT_TOKEN:
        return
    try:
        with connect() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT telegram_id FROM admin_users
                    WHERE active AND telegram_id IS NOT NULL
                      AND (role = 'owner' OR permissions ? 'all' OR permissions ? 'sylvex_test')
                """)
                admin_ids = [row[0] for row in cur.fetchall()]
    except Exception:
        return
    lines = [
        "🧪 <b>SYLVEX Test</b> — new request",
        f"Platform: {summary.get('platform')}",
        f"Category: {summary.get('category')}",
        f"Model: {summary.get('model') or '—'}",
    ]
    if summary.get("job_id"):
        lines.append(f"Job: <code>{summary['job_id']}</code>")
    if summary.get("grid_run_id"):
        lines.append(f"Grid Run: <code>{summary['grid_run_id']}</code>  Node: <code>{summary.get('grid_node_id') or ''}</code>")
    text = "\n".join(lines)
    keyboard = {"inline_keyboard": [[{"text": "Open", "callback_data": f"sylvex_test:open:{request_id}"}]]}
    for admin_id in admin_ids:
        try:
            requests.post(
                f"https://api.telegram.org/bot{SUPPORT_BOT_TOKEN}/sendMessage",
                json={"chat_id": admin_id, "text": text, "parse_mode": "HTML", "reply_markup": keyboard},
                timeout=10,
            )
        except Exception:
            pass


def submit(
    connect,
    *,
    platform: str,
    category: str,
    requester_id: int = 0,
    requester_account_id: int = 0,
    job_id: str = "",
    grid_run_id: str = "",
    grid_node_id: str = "",
    model: str = "",
    original_prompt: str = "",
    final_prompt: str = "",
    parameters: Optional[dict] = None,
    reference_urls: Optional[list] = None,
) -> str:
    """Inserts the mailbox row and pushes a notification. Returns the new
    request id - job_id, or f"{job_id}:{grid_node_id}" for a grid node so
    several nodes belonging to one job_id each get their own row."""
    ensure_sylvex_test_table(connect)
    request_id = f"{job_id}:{grid_node_id}" if grid_node_id else (job_id or str(uuid.uuid4()))
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO sylvex_test_requests
                    (id, platform, category, requester_id, requester_account_id, job_id,
                     grid_run_id, grid_node_id, model, original_prompt, final_prompt,
                     parameters, reference_urls)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb)
                ON CONFLICT (id) DO UPDATE SET
                    status='waiting', outcome=NULL, result_json=NULL,
                    responded_at=NULL, created_at=NOW()
            """, (
                request_id, platform, category, requester_id or None, requester_account_id or None,
                job_id or None, grid_run_id or None, grid_node_id or None, model,
                original_prompt, final_prompt,
                json.dumps(parameters or {}), json.dumps(reference_urls or []),
            ))
    _notify_admins(connect, request_id, {
        "platform": platform, "category": category, "model": model,
        "job_id": job_id, "grid_run_id": grid_run_id, "grid_node_id": grid_node_id,
    })
    return request_id


def _fetch(connect, request_id: str):
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT status, outcome, result_json FROM sylvex_test_requests WHERE id = %s",
                (request_id,),
            )
            return cur.fetchone()


def _timeout_result() -> dict:
    return {"ok": False, "error": "sylvex_test_timeout", "message": "SYLVEX Test: no response from the developer in time."}


async def wait_for_response(connect, request_id: str, timeout: float = MAX_WAIT_SECONDS) -> dict:
    """For async-def callers (image_generation/video_generation/
    poll_video_generation/audio_generation) - uses asyncio.sleep so it never
    blocks the event loop it's awaited on, whether that's the main loop or
    an off-loop worker thread's own loop."""
    import asyncio
    elapsed = 0.0
    while elapsed < timeout:
        row = await asyncio.to_thread(_fetch, connect, request_id)
        if row and row[0] == "responded":
            result = row[2] if isinstance(row[2], dict) else (json.loads(row[2]) if row[2] else {})
            return result
        await asyncio.sleep(POLL_INTERVAL_SECONDS)
        elapsed += POLL_INTERVAL_SECONDS
    return _timeout_result()


async def check_once(connect, request_id: str) -> Optional[dict]:
    """Single non-blocking check, for callers that themselves are already
    polled repeatedly by an outer loop on a timer (video's submit-then-poll
    shape) rather than expecting one call to block until resolved. Returns
    None while still waiting (caller reports its own "processing" status),
    or the developer's response dict once responded."""
    import asyncio
    row = await asyncio.to_thread(_fetch, connect, request_id)
    if row and row[0] == "responded":
        return row[2] if isinstance(row[2], dict) else (json.loads(row[2]) if row[2] else {})
    return None


def wait_for_response_sync(connect, request_id: str, timeout: float = MAX_WAIT_SECONDS) -> dict:
    """For plain-def callers (call_text_provider, run off the main loop via
    asyncio.to_thread already) - blocking time.sleep is correct here since
    there is no event loop in this thread to avoid blocking."""
    elapsed = 0.0
    while elapsed < timeout:
        row = _fetch(connect, request_id)
        if row and row[0] == "responded":
            result = row[2] if isinstance(row[2], dict) else (json.loads(row[2]) if row[2] else {})
            return result
        time.sleep(POLL_INTERVAL_SECONDS)
        elapsed += POLL_INTERVAL_SECONDS
    return _timeout_result()
