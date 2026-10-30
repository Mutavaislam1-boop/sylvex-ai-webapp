"""Admin sign-in security on top of the existing console auth
(services/admin_auth.py): the device a session came from, a sign-in history
read from the append-only audit log, and the rule for a suspicious sign-in.

A sign-in is suspicious when the admin has signed in before and now comes
from a device (browser and system) and network never seen with their
earlier sessions, or after repeated wrong 2FA codes. The admin (and the
owner, if it is someone else) is told at once; nothing is blocked beyond
what the existing auth already blocks.
"""
from __future__ import annotations

import re

LOGIN_ACTIONS = ("admin_login", "admin_login_failed", "admin_login_suspicious", "admin_logout", "admin_logout_all",
                 "admin_session_revoked", "admin_reauth")
FAILED_LIMIT = 3
FAILED_WINDOW_MINUTES = 15


def device_label(user_agent) -> str:
    """"Chrome · macOS", "Telegram · Android" - never the full string."""
    ua = str(user_agent or "")
    if not ua:
        return ""
    if "Telegram" in ua or "TelegramBot" in ua:
        app = "Telegram"
    else:
        app = next((name for key, name in (("Edg/", "Edge"), ("OPR/", "Opera"), ("YaBrowser", "Yandex"), ("Firefox/", "Firefox"),
                                           ("Chrome/", "Chrome"), ("Safari/", "Safari")) if key in ua), "Browser")
    system = next((name for key, name in (("iPhone", "iOS"), ("iPad", "iPadOS"), ("Android", "Android"), ("Mac OS X", "macOS"),
                                          ("Windows", "Windows"), ("Linux", "Linux")) if key in ua), "")
    return f"{app} · {system}" if system else app


def is_new_device(cur, admin_id, ip_hash, user_agent) -> bool:
    """True when the admin has earlier sessions and none of them shares this
    network or this kind of device."""
    cur.execute("SELECT ip_hash, user_agent FROM admin_sessions WHERE admin_id = %s ORDER BY id DESC LIMIT 200", (admin_id,))
    rows = cur.fetchall()
    if not rows:
        return False
    label = device_label(user_agent)
    return not any((ip_hash and r[0] == ip_hash) or (label and device_label(r[1]) == label) for r in rows)


def recent_failures(cur, admin_id) -> int:
    cur.execute(f"""
        SELECT COUNT(*) AS n FROM admin_audit_events
        WHERE actor_admin_id = %s AND action = 'admin_login_failed'
          AND at > NOW() - INTERVAL '{FAILED_WINDOW_MINUTES} minutes'
    """, (admin_id,))
    return int(cur.fetchone()[0] or 0)


def history(cur, admin_id, limit=60):
    cur.execute(f"""
        SELECT id, at, action, channel, after FROM admin_audit_events
        WHERE actor_admin_id = %s AND action IN ({", ".join(["%s"] * len(LOGIN_ACTIONS))})
        ORDER BY id DESC LIMIT %s
    """, (admin_id, *LOGIN_ACTIONS, int(limit)))
    out = []
    for r in cur.fetchall():
        after = r[4] if isinstance(r[4], dict) else {}
        out.append({"id": r[0], "at": r[1].isoformat() if hasattr(r[1], "isoformat") else str(r[1]), "action": r[2],
                    "channel": r[3], "device": str(after.get("device") or "")[:60],
                    "new_device": bool(after.get("new_device")), "detail": str(after.get("reason") or "")[:80]})
    return out


def alert_text(kind, device, channel) -> str:
    where = f"{device or 'неизвестное устройство'}, {'браузер' if channel == 'web' else 'Telegram Mini App'}"
    if kind == "failed":
        return (f"SYLVEX Admin: несколько неверных кодов 2FA подряд при входе в вашу учётную запись ({where}). "
                "Если это были не вы, завершите сессии в разделе «Аккаунт и безопасность» и сообщите владельцу.")
    return (f"SYLVEX Admin: вход в вашу учётную запись с нового устройства ({where}). "
            "Если это были не вы, завершите эту сессию в разделе «Аккаунт и безопасность».")


def clean_session_id(value):
    text = str(value or "")
    return int(text) if re.fullmatch(r"\d{1,18}", text) else None


# ---------------------------------------------------------------- audit log
# The sections of the console each logged action belongs to, for the
# audit log's filters and columns.
AUDIT_SECTIONS = {
    "users": ("user_blocked", "user_unblocked"),
    "finance": ("balance_changed", "subscription_changed", "generation_refunded"),
    "staff": ("admin_created", "admin_updated", "admin_access_changed", "admins_migrated_from_admin_users",
              "owner_bootstrapped", "owner_bootstrapped_from_email"),
    "content": ("reference_created", "reference_updated", "reference_published", "reference_unpublished", "reference_deleted"),
    "models": ("model_disabled", "model_enabled"),
    "messages": ("message_sent", "message_failed", "support_reply_sent", "support_status_changed", "support_assigned",
                 "support_attachments_changed", "broadcast_sent", "review_replied"),
    "generations": ("prostudio_job_recovered", "generation_recovered"),
    "security": LOGIN_ACTIONS + ("admin_totp_enabled", "admin_totp_enrollment_started"),
}
FAILED_RESULTS = ("admin_login_failed", "admin_login_suspicious", "message_failed")


def section_of(action) -> str:
    return next((name for name, actions in AUDIT_SECTIONS.items() if action in actions), "other")


def result_of(action, after) -> str:
    """"failed" for an action that records a failure, else "done" (only
    completed actions are written to the log)."""
    if action in FAILED_RESULTS or (isinstance(after, dict) and after.get("result") == "failed"):
        return "failed"
    return "done"


def object_of(action, after, before) -> str:
    """A short name of what the action changed (besides the target user)."""
    data = after if isinstance(after, dict) and after else (before if isinstance(before, dict) else {})
    for key in ("name", "model", "plan", "subscription", "review_id", "thread_id", "session_id", "id"):
        value = data.get(key)
        if value not in (None, "", [], {}):
            return f"{key}: {value}"[:80]
    return ""
