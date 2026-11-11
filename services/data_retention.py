"""Scheduled retention of error logs and closed support conversations (B09, S8-08).

The published Privacy Policy and Deletion Policy promise:
- ordinary logs: 30 days;
- support records: up to 12 months after closure, unless an unresolved
  dispute or a legal duty requires longer.

This module removes only:
- prostudio_errors and prostudio_error_reports rows older than 30 days
  (technical error logs: provider responses, stack traces, the failed prompt);
- support conversations with status 'closed' and no change and no message for
  12 months, with their messages (ON DELETE CASCADE) and the files the person
  attached to them. A conversation of someone with an unresolved payment
  review stays;
- finished entries of sylvex_active_operations older than 1 day (the
  erasure fence; the bot writes one per Telegram update when erasure is on,
  and only 'active' entries are ever read).

Never touched: payments, purchases, subscriptions, refunds, wallets, the
admin audit log, generations, notifications in the person's bell, and any
other table. Batches are bounded and locked (one instance at a time); every
pass returns counts only.
"""
from __future__ import annotations

import json

ERROR_LOG_DAYS = 30
FINISHED_OPERATION_HOURS = 24
SUPPORT_CLOSED_MONTHS = 12
LOCK = (61184, 1)
ERROR_TABLES = ("prostudio_errors", "prostudio_error_reports")
ATTACHMENT_PREFIX = "generated/support-uploads/"


def _exists(cur, table):
    cur.execute("SELECT to_regclass(%s) IS NOT NULL", (table,))
    return bool(cur.fetchone()[0])


def _has_column(cur, table, column):
    cur.execute("SELECT 1 FROM information_schema.columns WHERE table_schema=current_schema() "
                "AND table_name=%s AND column_name=%s", (table, column))
    return cur.fetchone() is not None


def _dispute_clause(cur):
    """SQL excluding conversations of people with an unresolved payment review."""
    if _exists(cur, "financial_review_cases"):
        return (" AND NOT EXISTS (SELECT 1 FROM financial_review_cases f WHERE t.user_key IS NOT NULL "
                "AND f.telegram_id=t.user_key AND f.review_revision>f.resolved_revision)")
    return ""


def _support_candidates_sql(cur):
    return ("FROM support_threads t WHERE t.status='closed' "
            "AND t.updated_at < NOW() - make_interval(months => %s) "
            "AND t.last_message_at < NOW() - make_interval(months => %s)" + _dispute_clause(cur))


def preview(cur, *, days=ERROR_LOG_DAYS, months=SUPPORT_CLOSED_MONTHS):
    """What a pass would remove now - counts only, nothing is changed."""
    result = {"error_logs": {}, "support_threads": 0, "support_messages": 0, "finished_operations": 0,
              "rules": {"error_log_days": days, "support_closed_months": months}}
    if _exists(cur, "sylvex_active_operations"):
        cur.execute("SELECT COUNT(*) FROM sylvex_active_operations WHERE state='finished' "
                    "AND finished_at < NOW() - make_interval(hours => %s)", (FINISHED_OPERATION_HOURS,))
        result["finished_operations"] = int(cur.fetchone()[0])
    for table in ERROR_TABLES:
        if _exists(cur, table) and _has_column(cur, table, "created_at"):
            cur.execute(f"SELECT COUNT(*) FROM {table} WHERE created_at < NOW() - make_interval(days => %s)", (days,))
            result["error_logs"][table] = int(cur.fetchone()[0])
    if _exists(cur, "support_threads"):
        where = _support_candidates_sql(cur)
        cur.execute("SELECT COUNT(*) " + where, (months, months))
        result["support_threads"] = int(cur.fetchone()[0])
        if _exists(cur, "support_messages"):
            cur.execute("SELECT COUNT(*) FROM support_messages m WHERE m.thread_id IN (SELECT t.id " + where + ")",
                        (months, months))
            result["support_messages"] = int(cur.fetchone()[0])
    return result


def _attachment_keys(raw):
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except ValueError:
            return []
    keys = []
    for item in raw or []:
        key = str((item or {}).get("key") or "") if isinstance(item, dict) else ""
        # Only the person's own upload folder; never an admin image or any other object.
        if key.startswith(ATTACHMENT_PREFIX) and ".." not in key:
            keys.append(key)
    return keys


def purge_once(cur, *, days=ERROR_LOG_DAYS, months=SUPPORT_CLOSED_MONTHS, batch=500):
    """One bounded pass in the caller's transaction. Returns counts and the
    attachment keys to delete from storage after the commit."""
    cur.execute("SELECT pg_try_advisory_xact_lock(%s, %s)", LOCK)
    if not cur.fetchone()[0]:
        return {"skipped": "locked"}
    result = {"error_logs": {}, "support_threads": 0, "support_messages": 0, "finished_operations": 0,
              "attachment_keys": []}
    if _exists(cur, "sylvex_active_operations"):
        cur.execute("DELETE FROM sylvex_active_operations WHERE operation_id IN (SELECT operation_id "
                    "FROM sylvex_active_operations WHERE state='finished' "
                    "AND finished_at < NOW() - make_interval(hours => %s) LIMIT %s)",
                    (FINISHED_OPERATION_HOURS, int(batch) * 10))
        result["finished_operations"] = cur.rowcount
    for table in ERROR_TABLES:
        if not (_exists(cur, table) and _has_column(cur, table, "created_at")):
            continue
        cur.execute(f"DELETE FROM {table} WHERE id IN (SELECT id FROM {table} "
                    "WHERE created_at < NOW() - make_interval(days => %s) ORDER BY id LIMIT %s)", (days, int(batch)))
        result["error_logs"][table] = cur.rowcount
    if _exists(cur, "support_threads"):
        cur.execute("SELECT t.id " + _support_candidates_sql(cur) + " ORDER BY t.id LIMIT %s FOR UPDATE SKIP LOCKED",
                    (months, months, max(1, int(batch) // 5)))
        ids = [int(row[0]) for row in cur.fetchall()]
        if ids:
            marks = ",".join(["%s"] * len(ids))
            if _exists(cur, "support_messages"):
                if _has_column(cur, "support_messages", "attachments"):
                    cur.execute(f"SELECT attachments FROM support_messages WHERE thread_id IN ({marks}) "
                                "AND attachments IS NOT NULL", ids)
                    for (raw,) in cur.fetchall():
                        result["attachment_keys"].extend(_attachment_keys(raw))
                cur.execute(f"DELETE FROM support_messages WHERE thread_id IN ({marks})", ids)
                result["support_messages"] = cur.rowcount
            cur.execute(f"DELETE FROM support_threads WHERE id IN ({marks})", ids)
            result["support_threads"] = cur.rowcount
    return result


def delete_attachments(keys, delete):
    """Best effort after the commit: (deleted, failed). A failure leaves only an
    unreferenced file in the person's own folder; it is reported in the log."""
    deleted = failed = 0
    for key in keys:
        try:
            delete(key)
            deleted += 1
        except Exception:
            failed += 1
    return deleted, failed
