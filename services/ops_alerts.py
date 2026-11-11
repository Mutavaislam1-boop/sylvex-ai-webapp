"""Operational alerts (B11): the administrator hears about P0 problems inside
SYLVEX without anyone watching the logs.

Detectors only READ existing tables - generation jobs and provider circuits
are never changed here:

- workers_stalled     claimable queued generation jobs nobody has picked up
                      for STALL_SECONDS (workers stopped or saturated);
- workers_stale_jobs  'processing' jobs whose heartbeat is older than
                      STALE_HEARTBEAT_SECONDS (a worker died mid-job);
- generation_failures in the last FAILURE_WINDOW_SECONDS at least
                      FAILURE_MIN failed/timed-out jobs and at least
                      FAILURE_RATIO of all finished ones;
- provider_circuit:<p> a provider's circuit breaker is not CLOSED.

The API being down is not detected here (a dead process cannot report
itself): tools/ops_uptime_check.py runs outside Railway for that.

Every alert is a row in ops_alert_state: one "fire" message when it starts,
a reminder every REMINDER_SECONDS while it lasts, one "resolve" message once
it has been clear for RESOLVE_AFTER_SECONDS. A message that could not be
delivered stays pending and is retried on the next cycle. Every attempt is
recorded in ops_alert_deliveries (ok / error). A transaction-level advisory
lock makes concurrent evaluators (several API replicas) act once.

Messages carry counts, providers and times only - no user ids, prompts,
tokens or secrets.
"""
from __future__ import annotations

import os

LOCK_KEY = 61182  # pg advisory lock: one evaluator at a time

STALL_SECONDS = int(os.getenv("OPS_ALERT_STALL_SECONDS", "300") or 300)
STALE_HEARTBEAT_SECONDS = int(os.getenv("OPS_ALERT_STALE_HEARTBEAT_SECONDS", "600") or 600)
FAILURE_WINDOW_SECONDS = int(os.getenv("OPS_ALERT_FAILURE_WINDOW_SECONDS", "900") or 900)
FAILURE_MIN = int(os.getenv("OPS_ALERT_FAILURE_MIN", "5") or 5)
FAILURE_RATIO = float(os.getenv("OPS_ALERT_FAILURE_RATIO", "0.5") or 0.5)
REMINDER_SECONDS = int(os.getenv("OPS_ALERT_REMINDER_SECONDS", "21600") or 21600)
RESOLVE_AFTER_SECONDS = int(os.getenv("OPS_ALERT_RESOLVE_AFTER_SECONDS", "300") or 300)
FAILED_STATUSES = ("failed", "timeout", "timed_out")

TITLES = {
    "workers_stalled": "генерации не обрабатываются",
    "workers_stale_jobs": "воркер перестал отвечать во время генерации",
    "generation_failures": "массовые ошибки генераций",
    "provider_circuit": "провайдер отключён защитой (circuit breaker)",
    "database_unreachable": "база данных недоступна для API",
    "test": "тестовое сообщение",
}


def ensure_schema(cur):
    cur.execute("""
        CREATE TABLE IF NOT EXISTS ops_alert_state (
            alert_key TEXT PRIMARY KEY,
            kind TEXT NOT NULL,
            state TEXT NOT NULL CHECK (state IN ('firing', 'resolved')),
            summary TEXT NOT NULL DEFAULT '',
            first_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            last_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            last_notified_at TIMESTAMPTZ,
            notify_pending TEXT CHECK (notify_pending IN ('fire', 'reminder', 'resolve')),
            resolved_at TIMESTAMPTZ
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS ops_alert_deliveries (
            id BIGSERIAL PRIMARY KEY,
            alert_key TEXT NOT NULL,
            event TEXT NOT NULL CHECK (event IN ('fire', 'reminder', 'resolve', 'test')),
            channel TEXT NOT NULL,
            at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            ok BOOLEAN NOT NULL,
            error TEXT
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_ops_alert_deliveries_at ON ops_alert_deliveries (at DESC)")


def _table_exists(cur, name):
    cur.execute("SELECT to_regclass(%s) IS NOT NULL AS present", (name,))
    return bool(cur.fetchone()[0])


# --------------------------------------------------------------------------
# Detectors (read only)
# --------------------------------------------------------------------------

def detect(cur, max_attempts=3):
    """{alert_key: (kind, summary)} for everything wrong right now."""
    found = {}
    if _table_exists(cur, "prostudio_generation_jobs"):
        cur.execute("""
            SELECT COUNT(*) AS n, COALESCE(EXTRACT(EPOCH FROM (NOW() - MIN(created_at))), 0) AS oldest
            FROM prostudio_generation_jobs
            WHERE status = 'queued' AND COALESCE(attempts, 0) < %s
              AND (provider_wait_until IS NULL OR provider_wait_until <= NOW())
              AND created_at < NOW() - (%s * INTERVAL '1 second')
        """, (int(max_attempts), STALL_SECONDS))
        n, oldest = cur.fetchone()
        if int(n or 0) > 0:
            found["workers_stalled"] = ("workers_stalled",
                                        f"В очереди {int(n)} заданий, старейшее ждёт {int(float(oldest) // 60)} мин.")
        cur.execute("""
            SELECT COUNT(*) AS n FROM prostudio_generation_jobs
            WHERE status = 'processing' AND heartbeat_at IS NOT NULL
              AND heartbeat_at < NOW() - (%s * INTERVAL '1 second')
        """, (STALE_HEARTBEAT_SECONDS,))
        stale = int(cur.fetchone()[0] or 0)
        if stale:
            found["workers_stale_jobs"] = ("workers_stale_jobs",
                                           f"{stale} заданий в работе без сигнала воркера дольше "
                                           f"{STALE_HEARTBEAT_SECONDS // 60} мин.")
        failed_sql = "status IN (" + ", ".join("'" + s + "'" for s in FAILED_STATUSES) + ")"  # constants
        cur.execute(f"""
            SELECT COUNT(*) FILTER (WHERE {failed_sql}) AS failed,
                   COUNT(*) FILTER (WHERE {failed_sql} OR status = 'completed') AS finished
            FROM prostudio_generation_jobs
            WHERE COALESCE(completed_at, updated_at) >= NOW() - (%s * INTERVAL '1 second')
        """, (FAILURE_WINDOW_SECONDS,))
        failed, finished = (int(v or 0) for v in cur.fetchone())
        if failed >= FAILURE_MIN and finished and failed / finished >= FAILURE_RATIO:
            found["generation_failures"] = ("generation_failures",
                                            f"За {FAILURE_WINDOW_SECONDS // 60} мин.: {failed} ошибок из "
                                            f"{finished} завершённых генераций ({round(100 * failed / finished)}%).")
    if _table_exists(cur, "prostudio_provider_circuits"):
        cur.execute("SELECT provider, state, failure_count FROM prostudio_provider_circuits "
                    "WHERE state <> 'CLOSED' ORDER BY provider")
        for provider, state, failures in cur.fetchall():
            name = str(provider)[:60]
            found[f"provider_circuit:{name}"] = ("provider_circuit",
                                                f"Провайдер {name}: {state}, ошибок подряд: {int(failures or 0)}.")
    return found


# --------------------------------------------------------------------------
# State machine and delivery
# --------------------------------------------------------------------------

def message(event, kind, summary, duration_seconds=None):
    title = TITLES.get(kind, kind)
    if event == "resolve":
        head = f"✅ SYLVEX: восстановлено — {title}"
        tail = f"\nДлилось: {max(1, int(duration_seconds or 0) // 60)} мин." if duration_seconds is not None else ""
        return f"{head}{tail}"
    if event == "test":
        return "🧪 SYLVEX: тестовое оповещение. Канал критических уведомлений работает."
    head = "🔴 SYLVEX P0" if event == "fire" else "⏰ SYLVEX P0, всё ещё"
    return f"{head}: {title}\n{summary}"


def _record(cur, alert_key, event, channel, ok, error):
    cur.execute("INSERT INTO ops_alert_deliveries (alert_key, event, channel, ok, error) VALUES (%s, %s, %s, %s, %s)",
                (alert_key, event, channel, bool(ok), (str(error)[:300] if error else None)))


def _deliver(cur, send, channel, alert_key, event, text):
    try:
        ok, error = send(text)
    except Exception as exc:  # a broken channel never breaks the evaluator
        ok, error = False, f"send_failed:{type(exc).__name__}"
    _record(cur, alert_key, event, channel, ok, error)
    return ok


def evaluate(cur, send, *, channel="telegram", max_attempts=3):
    """One cycle. Returns {"skipped": bool, "sent": [...], "failed": [...]}.
    The caller owns the transaction (commit after)."""
    ensure_schema(cur)
    cur.execute("SELECT pg_try_advisory_xact_lock(%s) AS locked", (LOCK_KEY,))
    if not cur.fetchone()[0]:
        return {"skipped": True, "sent": [], "failed": []}
    now_found = detect(cur, max_attempts)
    cur.execute("SELECT alert_key, kind, state, summary, notify_pending, "
                "EXTRACT(EPOCH FROM (NOW() - COALESCE(last_notified_at, first_seen_at))) AS since_notice, "
                "EXTRACT(EPOCH FROM (NOW() - last_seen_at)) AS since_seen, "
                "EXTRACT(EPOCH FROM (COALESCE(resolved_at, NOW()) - first_seen_at)) AS duration "
                "FROM ops_alert_state FOR UPDATE")
    states = {r[0]: {"kind": r[1], "state": r[2], "summary": r[3], "pending": r[4], "since_notice": float(r[5] or 0),
                     "since_seen": float(r[6] or 0), "duration": float(r[7] or 0)} for r in cur.fetchall()}
    for key, (kind, summary) in now_found.items():
        old = states.get(key)
        if old is None or old["state"] == "resolved":
            cur.execute("""
                INSERT INTO ops_alert_state (alert_key, kind, state, summary, notify_pending)
                VALUES (%s, %s, 'firing', %s, 'fire')
                ON CONFLICT (alert_key) DO UPDATE SET state = 'firing', kind = EXCLUDED.kind, summary = EXCLUDED.summary,
                    first_seen_at = NOW(), last_seen_at = NOW(), last_notified_at = NULL, resolved_at = NULL,
                    notify_pending = 'fire'
            """, (key, kind, summary))
            states[key] = {"kind": kind, "state": "firing", "summary": summary, "pending": "fire",
                           "since_notice": 0.0, "since_seen": 0.0, "duration": 0.0}
        else:
            pending = old["pending"] or ("reminder" if old["since_notice"] >= REMINDER_SECONDS else None)
            cur.execute("UPDATE ops_alert_state SET last_seen_at = NOW(), summary = %s, notify_pending = %s "
                        "WHERE alert_key = %s", (summary, pending, key))
            old.update(summary=summary, pending=pending)
    for key, old in states.items():
        if old["state"] == "firing" and key not in now_found and old["since_seen"] >= RESOLVE_AFTER_SECONDS:
            cur.execute("UPDATE ops_alert_state SET state = 'resolved', resolved_at = NOW(), notify_pending = 'resolve' "
                        "WHERE alert_key = %s", (key,))
            old.update(state="resolved", pending="resolve")
    sent, failed = [], []
    for key, old in sorted(states.items()):
        event = old["pending"]
        if not event:
            continue
        text = message(event, old["kind"], old["summary"], old["duration"] if event == "resolve" else None)
        if _deliver(cur, send, channel, key, event, text):
            cur.execute("UPDATE ops_alert_state SET notify_pending = NULL, last_notified_at = NOW() WHERE alert_key = %s",
                        (key,))
            sent.append((key, event))
        else:
            failed.append((key, event))
    return {"skipped": False, "sent": sent, "failed": failed}


def send_test(cur, send, channel="telegram"):
    ensure_schema(cur)
    return _deliver(cur, send, channel, "test", "test", message("test", "test", ""))


def overview(cur, limit=20):
    """Current alerts and the last deliveries, for the admin console."""
    ensure_schema(cur)
    cur.execute("SELECT alert_key, kind, state, summary, first_seen_at, last_seen_at, last_notified_at, "
                "notify_pending, resolved_at FROM ops_alert_state ORDER BY (state = 'firing') DESC, last_seen_at DESC "
                "LIMIT 50")
    alerts = [{"alert_key": r[0], "kind": r[1], "state": r[2], "summary": r[3], "first_seen_at": _iso(r[4]),
               "last_seen_at": _iso(r[5]), "last_notified_at": _iso(r[6]), "notify_pending": r[7],
               "resolved_at": _iso(r[8])} for r in cur.fetchall()]
    cur.execute("SELECT alert_key, event, channel, at, ok, error FROM ops_alert_deliveries ORDER BY id DESC LIMIT %s",
                (max(1, min(int(limit), 100)),))
    deliveries = [{"alert_key": r[0], "event": r[1], "channel": r[2], "at": _iso(r[3]), "ok": bool(r[4]),
                   "error": r[5]} for r in cur.fetchall()]
    return {"alerts": alerts, "deliveries": deliveries}


def subscription_event_delivery(cur):
    """The existing payment-notification outbox (subscription_events): how
    many were delivered, are waiting or failing in the last 30 days.
    Aggregates only - no Telegram ids, amounts or payment references."""
    if not _table_exists(cur, "subscription_events"):
        return {"present": False}
    cur.execute("""
        SELECT COUNT(*) AS total,
               COUNT(*) FILTER (WHERE sent_at IS NOT NULL) AS delivered,
               COUNT(*) FILTER (WHERE sent_at IS NULL) AS pending,
               COUNT(*) FILTER (WHERE sent_at IS NULL AND last_error IS NOT NULL) AS failing,
               MAX(sent_at) AS last_delivered
        FROM subscription_events WHERE created_at > NOW() - INTERVAL '30 days'
    """)
    total, delivered, pending, failing, last = cur.fetchone()
    cur.execute("""
        SELECT LEFT(last_error, 120) AS error, COUNT(*) AS n FROM subscription_events
        WHERE sent_at IS NULL AND last_error IS NOT NULL AND created_at > NOW() - INTERVAL '30 days'
        GROUP BY 1 ORDER BY 2 DESC LIMIT 5
    """)
    errors = [{"error": r[0], "count": int(r[1])} for r in cur.fetchall()]
    return {"present": True, "total": int(total or 0), "delivered": int(delivered or 0), "pending": int(pending or 0),
            "failing": int(failing or 0), "last_delivered": _iso(last), "errors": errors}


def _iso(value):
    return value.isoformat() if hasattr(value, "isoformat") else (str(value) if value is not None else None)
