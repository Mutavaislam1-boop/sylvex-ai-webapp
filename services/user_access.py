"""Admin blocks on SYLVEX accounts.

A block belongs to the person: their SYLVEX account (every identity linked
to it - Telegram, email, Google, Apple - resolves to the same account) and
the account's storage key (users.telegram_id). A Telegram user with no
SYLVEX account yet is blocked by the storage key alone. Accounts that were
never linked are separate people and are never blocked together.

While a block is active the person keeps only what they need to understand
and contest it (see ALLOWED_WHEN_BLOCKED): their status, notifications and
the contact form. Everything else that needs an identity - generations,
purchases, profile, the bot - answers `account_blocked`.

Every function takes an open cursor; the caller commits.
"""
from __future__ import annotations

MAX_REASON = 500
MAX_NOTE = 2000

# Protected routes a blocked person still reaches: their own status (so
# every surface can explain the restriction), the notification bell (admins
# may write to them) and the contact form (to appeal).
ALLOWED_WHEN_BLOCKED = frozenset({
    "/api/public/account/status",
    "/api/public/notifications",
    "/api/public/notifications/read",
    "/api/public/notifications/awards",
    "/api/public/contact",
    "/api/web/auth/logout",
})


class AccessError(Exception):
    def __init__(self, code, status=400):
        super().__init__(code)
        self.code = code
        self.status = status


def ensure_table(cur):
    cur.execute("""
        CREATE TABLE IF NOT EXISTS user_access_blocks (
            id BIGSERIAL PRIMARY KEY,
            account_id BIGINT,
            user_key BIGINT,
            reason TEXT NOT NULL,
            note TEXT,
            admin_id BIGINT,
            created_at TIMESTAMP NOT NULL DEFAULT NOW(),
            lifted_at TIMESTAMP,
            lifted_by BIGINT,
            lift_reason TEXT
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_uab_account_active ON user_access_blocks(account_id) WHERE lifted_at IS NULL")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_uab_key_active ON user_access_blocks(user_key) WHERE lifted_at IS NULL")


def _iso(value):
    return value.isoformat() if hasattr(value, "isoformat") else value


def _row(r):
    return {"id": int(r[0]), "account_id": r[1], "user_key": r[2], "reason": r[3], "note": r[4] or "",
            "admin_id": r[5], "created_at": _iso(r[6]), "lifted_at": _iso(r[7]), "lifted_by": r[8],
            "lift_reason": r[9] or "", "active": r[7] is None}


_COLUMNS = "id, account_id, user_key, reason, note, admin_id, created_at, lifted_at, lifted_by, lift_reason"


def account_for_key(cur, user_key):
    if not user_key:
        return None
    cur.execute("SELECT to_regclass('sylvex_accounts')")
    if cur.fetchone()[0] is None:
        return None
    cur.execute("SELECT account_id FROM sylvex_accounts WHERE active_telegram_id = %s", (int(user_key),))
    row = cur.fetchone()
    return int(row[0]) if row else None


def _where(account_id, user_key):
    parts, params = [], []
    if account_id:
        parts.append("account_id = %s")
        params.append(int(account_id))
    if user_key:
        parts.append("user_key = %s")
        params.append(int(user_key))
    if not parts:
        raise AccessError("user_not_found", 404)
    return "(" + " OR ".join(parts) + ")", params


def active_block(cur, *, account_id=None, user_key=None):
    if not account_id and not user_key:
        return None
    where, params = _where(account_id, user_key)
    cur.execute(f"SELECT {_COLUMNS} FROM user_access_blocks WHERE {where} AND lifted_at IS NULL "
                "ORDER BY id DESC LIMIT 1", params)
    row = cur.fetchone()
    return _row(row) if row else None


def block_for_uid(cur, uid):
    """The active block of whoever is behind the storage key `uid` (the id
    SecurityMiddleware resolves for every protected request), or None."""
    if not uid:
        return None
    cur.execute("SELECT to_regclass('user_access_blocks')")
    if cur.fetchone()[0] is None:
        return None  # no admin ever blocked anyone here
    return active_block(cur, account_id=account_for_key(cur, uid), user_key=int(uid))


def block(cur, *, account_id, user_key, reason, note="", admin_id=None):
    reason = str(reason or "").strip()[:MAX_REASON]
    if not reason:
        raise AccessError("reason_required")
    if active_block(cur, account_id=account_id, user_key=user_key):
        raise AccessError("already_blocked", 409)
    cur.execute("""
        INSERT INTO user_access_blocks (account_id, user_key, reason, note, admin_id)
        VALUES (%s, %s, %s, NULLIF(%s, ''), %s) RETURNING id
    """, (account_id, user_key, reason, str(note or "").strip()[:MAX_NOTE], admin_id))
    return int(cur.fetchone()[0])


def unblock(cur, *, account_id, user_key, reason, admin_id=None):
    reason = str(reason or "").strip()[:MAX_REASON]
    if not reason:
        raise AccessError("reason_required")
    where, params = _where(account_id, user_key)
    cur.execute(f"""
        UPDATE user_access_blocks SET lifted_at = NOW(), lifted_by = %s, lift_reason = %s
        WHERE {where} AND lifted_at IS NULL RETURNING id
    """, [admin_id, reason] + params)
    lifted = [int(r[0]) for r in cur.fetchall()]
    if not lifted:
        raise AccessError("not_blocked", 409)
    return lifted


def history(cur, *, account_id=None, user_key=None, limit=20):
    if not account_id and not user_key:
        return []
    where, params = _where(account_id, user_key)
    cur.execute(f"SELECT {_COLUMNS} FROM user_access_blocks WHERE {where} ORDER BY id DESC LIMIT %s",
                params + [max(1, min(int(limit or 20), 100))])
    return [_row(r) for r in cur.fetchall()]


def public_status(block_row):
    """What the person themselves is told."""
    if not block_row:
        return {"blocked": False}
    return {"blocked": True, "reason": block_row["reason"], "since": block_row["created_at"]}
