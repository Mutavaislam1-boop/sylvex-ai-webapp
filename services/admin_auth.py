"""Admin Console authentication, sessions and audit (Phase 2).

Authority comes from an admin record bound to a SYLVEX account
(admin_accounts.account_id), never from a Telegram id alone:

- Mini App: verified initData -> real Telegram id -> the SYLVEX account that
  owns it -> active admin_accounts row -> short-lived session.
- Web: email + password -> account -> active admin -> TOTP (required) ->
  session. TOTP is enrolled from a Mini App session, so a stolen website
  password alone can never set up admin web access.
- Sessions: random token in an HttpOnly Secure SameSite=Strict cookie; only
  its SHA-256 is stored. 30 min idle, 8 h absolute, revocable one by one or
  all at once. Critical actions additionally need a re-authentication
  within the last 5 minutes.
- Audit: admin_audit_events is append-only (a trigger rejects UPDATE,
  DELETE and TRUNCATE).

Every function here takes an open cursor; callers own the transaction.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import struct
import time

from cryptography.fernet import Fernet, InvalidToken

from services import admin_rbac as rbac
from services.account_identity import ensure_telegram_account, real_telegram_id

SESSION_COOKIE = "__Host-sylvex_admin"
CSRF_HEADER = "x-admin-csrf"
SESSION_IDLE_SECONDS = 30 * 60
SESSION_MAX_SECONDS = 8 * 3600
REAUTH_WINDOW_SECONDS = 5 * 60
TOTP_STEP = 30
TOTP_DIGITS = 6
TOTP_MAX_FAILURES = 5
TOTP_LOCK_SECONDS = 15 * 60
CHANNELS = ("miniapp", "web", "bot", "miniapp_legacy", "system")


class AdminAuthError(Exception):
    def __init__(self, code, status=403):
        self.code = code
        self.status = status
        super().__init__(code)


# --------------------------------------------------------------------------
# Schema
# --------------------------------------------------------------------------

def ensure_schema(cur):
    cur.execute("""
        CREATE TABLE IF NOT EXISTS admin_accounts (
            id BIGSERIAL PRIMARY KEY,
            account_id BIGINT NOT NULL UNIQUE,
            role TEXT NOT NULL,
            grants JSONB NOT NULL DEFAULT '[]'::jsonb,
            denies JSONB NOT NULL DEFAULT '[]'::jsonb,
            status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'suspended', 'revoked')),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            created_by BIGINT,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            last_login_at TIMESTAMPTZ,
            last_activity_at TIMESTAMPTZ,
            totp_secret_enc TEXT,
            totp_pending_enc TEXT,
            totp_enabled_at TIMESTAMPTZ,
            totp_last_step BIGINT,
            totp_failures INTEGER NOT NULL DEFAULT 0,
            totp_locked_until TIMESTAMPTZ
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS admin_sessions (
            id BIGSERIAL PRIMARY KEY,
            token_hash TEXT NOT NULL UNIQUE,
            admin_id BIGINT NOT NULL REFERENCES admin_accounts(id),
            channel TEXT NOT NULL,
            csrf_token TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            expires_at TIMESTAMPTZ NOT NULL,
            last_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            reauth_at TIMESTAMPTZ,
            revoked_at TIMESTAMPTZ,
            ip_hash TEXT,
            user_agent TEXT
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_admin_sessions_admin ON admin_sessions (admin_id) WHERE revoked_at IS NULL")
    cur.execute("""
        CREATE TABLE IF NOT EXISTS admin_audit_events (
            id BIGSERIAL PRIMARY KEY,
            at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            actor_admin_id BIGINT,
            actor_account_id BIGINT,
            channel TEXT NOT NULL,
            action TEXT NOT NULL,
            risk TEXT NOT NULL,
            target_account_id BIGINT,
            target_ref TEXT,
            reason TEXT NOT NULL DEFAULT '',
            before JSONB NOT NULL DEFAULT '{}'::jsonb,
            after JSONB NOT NULL DEFAULT '{}'::jsonb,
            request_id TEXT,
            ip_hash TEXT
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_admin_audit_events_target ON admin_audit_events (target_account_id, id DESC)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_admin_audit_events_actor ON admin_audit_events (actor_admin_id, id DESC)")
    cur.execute("""
        CREATE OR REPLACE FUNCTION admin_audit_events_append_only() RETURNS trigger AS $fn$
        BEGIN
            RAISE EXCEPTION 'admin_audit_events is append-only';
        END
        $fn$ LANGUAGE plpgsql
    """)
    for name, timing in (("admin_audit_events_no_change", "BEFORE UPDATE OR DELETE ON admin_audit_events FOR EACH ROW"),
                         ("admin_audit_events_no_truncate", "BEFORE TRUNCATE ON admin_audit_events FOR EACH STATEMENT")):
        cur.execute("SELECT 1 FROM pg_trigger WHERE tgname = %s AND NOT tgisinternal", (name,))
        if not cur.fetchone():
            cur.execute(f"CREATE TRIGGER {name} {timing} EXECUTE FUNCTION admin_audit_events_append_only()")
    cur.execute("""
        CREATE TABLE IF NOT EXISTS admin_schema_migrations (
            name TEXT PRIMARY KEY,
            applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            detail JSONB NOT NULL DEFAULT '{}'::jsonb
        )
    """)


def _migration_done(cur, name):
    cur.execute("SELECT 1 FROM admin_schema_migrations WHERE name = %s", (name,))
    return cur.fetchone() is not None


def _mark_migration(cur, name, detail):
    cur.execute("INSERT INTO admin_schema_migrations (name, detail) VALUES (%s, %s::jsonb) ON CONFLICT (name) DO NOTHING",
                (name, json.dumps(detail)))


def migrate_legacy_admins(cur):
    """One time: every admin_users row becomes an admin_accounts row with
    exactly the permissions it had. Returns a report (also stored)."""
    if _migration_done(cur, "legacy_admin_users"):
        return None
    cur.execute("SELECT to_regclass('admin_users')")
    report = {"migrated": [], "unmapped": []}
    if cur.fetchone()[0] is not None:
        cur.execute("SELECT id, telegram_id, account_id, role, permissions, active FROM admin_users ORDER BY id")
        for row_id, telegram_id, account_id, role, permissions, active in cur.fetchall():
            if isinstance(permissions, str):
                try:
                    permissions = json.loads(permissions)
                except ValueError:
                    permissions = []
            if not account_id and telegram_id:
                account_id = ensure_telegram_account(cur, telegram_id)
            if not account_id:
                report["unmapped"].append({"admin_users_id": row_id})
                continue
            if role == "owner" or "all" in (permissions or []):
                new_role, grants, denies = rbac.OWNER, [], []
            else:
                new_role, grants, denies = rbac.exact_role_for_legacy(permissions or [])
            cur.execute("""
                INSERT INTO admin_accounts (account_id, role, grants, denies, status)
                VALUES (%s, %s, %s::jsonb, %s::jsonb, %s)
                ON CONFLICT (account_id) DO NOTHING
            """, (int(account_id), new_role, json.dumps(grants), json.dumps(denies), "active" if active else "revoked"))
            report["migrated"].append({"admin_users_id": row_id, "account_id": int(account_id), "role": new_role})
    _mark_migration(cur, "legacy_admin_users", report)
    audit(cur, None, "admins_migrated_from_admin_users", risk=rbac.CRITICAL, after=report)
    return report


def copy_legacy_audit(cur):
    """One time: old admin_audit_log rows are copied (never moved) into the
    append-only table, marked with their original ids."""
    if _migration_done(cur, "legacy_admin_audit_log"):
        return 0
    cur.execute("SELECT to_regclass('admin_audit_log')")
    copied = 0
    if cur.fetchone()[0] is not None:
        cur.execute("""
            INSERT INTO admin_audit_events (at, actor_account_id, channel, action, risk, target_account_id,
                                            target_ref, reason, before, after)
            SELECT l.created_at, actor.account_id, 'legacy', l.action, 'unknown', target.account_id,
                   'legacy_audit_id:' || l.id, COALESCE(l.reason, ''), l.before_data, l.after_data
            FROM admin_audit_log l
            LEFT JOIN sylvex_accounts actor ON actor.active_telegram_id = l.actor_telegram_id
            LEFT JOIN sylvex_accounts target ON target.active_telegram_id = l.target_telegram_id
            ORDER BY l.id
        """)
        copied = cur.rowcount if cur.rowcount and cur.rowcount > 0 else 0
    _mark_migration(cur, "legacy_admin_audit_log", {"copied": copied})
    return copied


def bootstrap_owner(cur, owner_account_id=None, owner_telegram_id=None):
    """Only when there is no active owner at all: make the configured
    account the owner. Never re-applied over a later change."""
    cur.execute("SELECT 1 FROM admin_accounts WHERE role = 'owner' AND status = 'active' LIMIT 1")
    if cur.fetchone():
        return None
    account_id = int(owner_account_id) if owner_account_id else None
    if not account_id and owner_telegram_id:
        account_id = ensure_telegram_account(cur, owner_telegram_id)
    if not account_id:
        return None
    cur.execute("""
        INSERT INTO admin_accounts (account_id, role, status) VALUES (%s, 'owner', 'active')
        ON CONFLICT (account_id) DO UPDATE SET role = 'owner', status = 'active', grants = '[]'::jsonb,
            denies = '[]'::jsonb, updated_at = NOW()
        RETURNING id
    """, (account_id,))
    admin_id = int(cur.fetchone()[0])
    audit(cur, None, "owner_bootstrapped", risk=rbac.CRITICAL, target_account_id=account_id,
          after={"admin_id": admin_id, "account_id": account_id})
    return admin_id


# --------------------------------------------------------------------------
# Admin records
# --------------------------------------------------------------------------

_ADMIN_COLUMNS = ("a.id, a.account_id, a.role, a.grants, a.denies, a.status, "
                  "a.totp_enabled_at IS NOT NULL AS totp_enabled, s.active_telegram_id")


def _json_list(value):
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError:
            value = []
    return list(value or [])


def _admin_from_row(row):
    admin_id, account_id, role, grants, denies, status, totp_enabled, active_tg = row
    grants, denies = _json_list(grants), _json_list(denies)
    return {
        "admin_id": int(admin_id), "account_id": int(account_id), "role": role, "grants": grants, "denies": denies,
        "status": status, "totp_enabled": bool(totp_enabled), "telegram_id": real_telegram_id(active_tg),
        "permissions_set": rbac.effective_permissions(role, grants, denies),
    }


def owner_email_setting():
    """ADMIN_OWNER_EMAIL, normalized; empty disables the browser
    bootstrap-owner path entirely."""
    from services.account_identity import normalize_email
    return normalize_email(os.getenv("ADMIN_OWNER_EMAIL", "") or "")


def is_bootstrap_owner_email(cur, email, account_id):
    """True only when `email` is exactly ADMIN_OWNER_EMAIL (after the same
    normalization signup uses), it is a *verified* email, and it belongs to
    `account_id`. An unverified address never qualifies: otherwise anyone
    could register the developer's Gmail first and claim the console."""
    from services.account_identity import normalize_email
    owner = owner_email_setting()
    email = normalize_email(email or "")
    if not owner or not email or not hmac.compare_digest(owner, email):
        return False
    cur.execute("SELECT account_id, email_verified FROM account_emails WHERE email = %s", (email,))
    row = cur.fetchone()
    return bool(row and int(row[0]) == int(account_id) and row[1])


def bootstrap_email_owner(cur, account_id, email):
    """Makes the ADMIN_OWNER_EMAIL account an owner the first time it signs
    in, and only if it has no admin record yet: a later suspension or
    revocation by another owner is never undone by this path."""
    if load_admin(cur, account_id=account_id):
        return None
    cur.execute("""
        INSERT INTO admin_accounts (account_id, role, status) VALUES (%s, 'owner', 'active')
        ON CONFLICT (account_id) DO NOTHING RETURNING id
    """, (account_id,))
    row = cur.fetchone()
    if not row:
        return None
    admin_id = int(row[0])
    audit(cur, None, "owner_bootstrapped_from_email", risk=rbac.CRITICAL, target_account_id=account_id,
          channel="web", after={"admin_id": admin_id, "account_id": account_id, "source": "ADMIN_OWNER_EMAIL"})
    return admin_id


def account_for_email(cur, email):
    """(account_id, verified) for a registered email, or (None, False)."""
    from services.account_identity import normalize_email
    email = normalize_email(email or "")
    if not email:
        return None, False
    cur.execute("SELECT account_id, email_verified FROM account_emails WHERE email = %s", (email,))
    row = cur.fetchone()
    if not row:
        return None, False
    return canonical_account(cur, row[0]) or int(row[0]), bool(row[1])


def load_admin(cur, *, admin_id=None, account_id=None):
    where, value = ("a.id = %s", admin_id) if admin_id is not None else ("a.account_id = %s", account_id)
    cur.execute(f"SELECT {_ADMIN_COLUMNS} FROM admin_accounts a "
                f"LEFT JOIN sylvex_accounts s ON s.account_id = a.account_id WHERE {where}", (int(value),))
    row = cur.fetchone()
    return _admin_from_row(row) if row else None


def canonical_account(cur, sylvex_user_id):
    """The live account a SYLVEX ID (or a retired alias of it) refers to."""
    try:
        current = int(str(sylvex_user_id).strip())
    except (TypeError, ValueError):
        return None
    for _ in range(3):
        cur.execute("SELECT active_telegram_id, merged_into_account_id FROM sylvex_accounts WHERE account_id = %s",
                    (current,))
        row = cur.fetchone()
        if not row:
            return None
        if row[0] is not None:
            return current
        if row[1] is None:
            return None
        current = int(row[1])
    return None


def account_for_telegram(cur, telegram_id):
    if real_telegram_id(telegram_id) is None:
        return None
    cur.execute("SELECT account_id FROM sylvex_accounts WHERE active_telegram_id = %s", (int(telegram_id),))
    row = cur.fetchone()
    return int(row[0]) if row else None


def active_admin_for_telegram(cur, telegram_id):
    """The active admin behind a real Telegram id, or None. Never creates."""
    account_id = account_for_telegram(cur, telegram_id)
    if account_id is None:
        return None
    admin = load_admin(cur, account_id=account_id)
    return admin if admin and admin["status"] == "active" else None


def public_admin(admin):
    return {
        "admin_id": admin["admin_id"], "sylvex_user_id": str(admin["account_id"]), "role": admin["role"],
        "status": admin["status"], "grants": admin["grants"], "denies": admin["denies"],
        "permissions": sorted(admin["permissions_set"]), "totp_enabled": admin.get("totp_enabled", False),
    }


# --------------------------------------------------------------------------
# Sessions
# --------------------------------------------------------------------------

def _hash(value):
    return hashlib.sha256(value.encode()).hexdigest()


def hash_ip(ip):
    if not ip:
        return None
    return hmac.new(_secret_material().encode(), str(ip).encode(), hashlib.sha256).hexdigest()[:32]


def create_session(cur, admin, channel, ip=None, user_agent=None, reauthenticated=True):
    if channel not in CHANNELS:
        raise ValueError("unknown channel")
    token = secrets.token_urlsafe(32)
    csrf = secrets.token_urlsafe(24)
    cur.execute(f"""
        INSERT INTO admin_sessions (token_hash, admin_id, channel, csrf_token, expires_at, reauth_at, ip_hash, user_agent)
        VALUES (%s, %s, %s, %s, NOW() + INTERVAL '{SESSION_MAX_SECONDS} seconds',
                CASE WHEN %s THEN NOW() ELSE NULL END, %s, %s)
        RETURNING id
    """, (_hash(token), admin["admin_id"], channel, csrf, bool(reauthenticated), hash_ip(ip), (user_agent or "")[:300]))
    session_id = int(cur.fetchone()[0])
    cur.execute("UPDATE admin_accounts SET last_login_at = NOW(), last_activity_at = NOW() WHERE id = %s",
                (admin["admin_id"],))
    return token, csrf, session_id


def resolve_session(cur, token):
    """(admin, session) for a live session token, else raises. Touches
    last_seen_at (the idle timer)."""
    if not token:
        raise AdminAuthError("admin_session_required", 401)
    cur.execute(f"""
        SELECT id, admin_id, channel, csrf_token,
               (reauth_at IS NOT NULL AND reauth_at > NOW() - INTERVAL '{REAUTH_WINDOW_SECONDS} seconds') AS fresh
        FROM admin_sessions
        WHERE token_hash = %s AND revoked_at IS NULL AND expires_at > NOW()
          AND last_seen_at > NOW() - INTERVAL '{SESSION_IDLE_SECONDS} seconds'
    """, (_hash(token),))
    row = cur.fetchone()
    if not row:
        raise AdminAuthError("admin_session_invalid", 401)
    session = {"session_id": int(row[0]), "admin_id": int(row[1]), "channel": row[2], "csrf_token": row[3],
               "reauth_fresh": bool(row[4])}
    admin = load_admin(cur, admin_id=session["admin_id"])
    if not admin or admin["status"] != "active":
        raise AdminAuthError("admin_access_denied", 403)
    cur.execute("UPDATE admin_sessions SET last_seen_at = NOW() WHERE id = %s", (session["session_id"],))
    cur.execute("UPDATE admin_accounts SET last_activity_at = NOW() WHERE id = %s", (admin["admin_id"],))
    return admin, session


def revoke_session(cur, session_id):
    cur.execute("UPDATE admin_sessions SET revoked_at = NOW() WHERE id = %s AND revoked_at IS NULL", (session_id,))


def revoke_all_sessions(cur, admin_id):
    cur.execute("UPDATE admin_sessions SET revoked_at = NOW() WHERE admin_id = %s AND revoked_at IS NULL", (admin_id,))
    return cur.rowcount


def mark_reauth(cur, session_id):
    cur.execute("UPDATE admin_sessions SET reauth_at = NOW() WHERE id = %s", (session_id,))


def list_sessions(cur, admin_id):
    cur.execute("""
        SELECT id, channel, created_at, last_seen_at, expires_at, user_agent
        FROM admin_sessions WHERE admin_id = %s AND revoked_at IS NULL AND expires_at > NOW()
        ORDER BY id DESC LIMIT 50
    """, (admin_id,))
    return [{"session_id": r[0], "channel": r[1], "created_at": _iso(r[2]), "last_seen_at": _iso(r[3]),
             "expires_at": _iso(r[4]), "user_agent": r[5] or ""} for r in cur.fetchall()]


def _iso(value):
    return value.isoformat() if hasattr(value, "isoformat") else (str(value) if value is not None else None)


# --------------------------------------------------------------------------
# TOTP (RFC 6238, SHA-1, 30 s, 6 digits) with encrypted secrets
# --------------------------------------------------------------------------

def _secret_material():
    """Same derivation chain the web session secret uses; a dedicated
    ADMIN_TOTP_ENCRYPTION_KEY wins when it is set."""
    for name in ("ADMIN_TOTP_ENCRYPTION_KEY", "WEB_SESSION_SECRET", "BOT_TOKEN", "TELEGRAM_BOT_TOKEN"):
        value = os.getenv(name, "").strip()
        if value:
            return value
    raise AdminAuthError("admin_totp_not_configured", 503)


def _fernet():
    digest = hmac.new(_secret_material().encode(), b"SYLVEX admin totp v1", hashlib.sha256).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def totp_code(secret_b32, for_time=None, step_offset=0):
    key = base64.b32decode(secret_b32.upper() + "=" * (-len(secret_b32) % 8))
    counter = int((for_time if for_time is not None else time.time()) // TOTP_STEP) + step_offset
    digest = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    value = (struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF) % (10 ** TOTP_DIGITS)
    return f"{value:0{TOTP_DIGITS}d}", counter


def begin_totp_enrollment(cur, admin, issuer="SYLVEX Admin"):
    secret = base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")
    cur.execute("UPDATE admin_accounts SET totp_pending_enc = %s WHERE id = %s",
                (_fernet().encrypt(secret.encode()).decode(), admin["admin_id"]))
    label = f"{issuer}:{admin['account_id']}"
    uri = f"otpauth://totp/{label}?secret={secret}&issuer={issuer.replace(' ', '%20')}&digits={TOTP_DIGITS}&period={TOTP_STEP}"
    return secret, uri


def _check_code(secret, code, last_step):
    code = str(code or "").strip()
    if not (code.isdigit() and len(code) == TOTP_DIGITS):
        return None
    now = time.time()
    for offset in (-1, 0, 1):
        expected, counter = totp_code(secret, now, offset)
        if hmac.compare_digest(expected, code) and (last_step is None or counter > int(last_step)):
            return counter
    return None


def confirm_totp_enrollment(cur, admin, code):
    cur.execute("SELECT totp_pending_enc FROM admin_accounts WHERE id = %s FOR UPDATE", (admin["admin_id"],))
    row = cur.fetchone()
    if not row or not row[0]:
        raise AdminAuthError("totp_enrollment_not_started", 409)
    secret = _decrypt(row[0])
    counter = _check_code(secret, code, None)
    if counter is None:
        raise AdminAuthError("totp_invalid", 401)
    cur.execute("""
        UPDATE admin_accounts SET totp_secret_enc = totp_pending_enc, totp_pending_enc = NULL,
            totp_enabled_at = NOW(), totp_last_step = %s, totp_failures = 0, totp_locked_until = NULL
        WHERE id = %s
    """, (counter, admin["admin_id"]))


def confirm_totp_enrollment_limited(cur, admin, code):
    """confirm_totp_enrollment for the browser bootstrap-owner setup, where
    the caller is not yet holding a session: wrong codes count towards the
    same lockout as verify_totp, so the pending secret cannot be guessed."""
    cur.execute("""
        SELECT totp_failures, (totp_locked_until IS NOT NULL AND totp_locked_until > NOW())
        FROM admin_accounts WHERE id = %s FOR UPDATE
    """, (admin["admin_id"],))
    row = cur.fetchone()
    if row and row[1]:
        raise AdminAuthError("totp_locked", 429)
    try:
        confirm_totp_enrollment(cur, admin, code)
    except AdminAuthError as exc:
        if exc.code == "totp_invalid":
            failures = int((row or [0])[0] or 0) + 1
            cur.execute(f"""
                UPDATE admin_accounts SET totp_failures = %s,
                    totp_locked_until = CASE WHEN %s >= {TOTP_MAX_FAILURES}
                        THEN NOW() + INTERVAL '{TOTP_LOCK_SECONDS} seconds' ELSE totp_locked_until END
                WHERE id = %s
            """, (failures, failures, admin["admin_id"]))
        raise


def _decrypt(token):
    try:
        return _fernet().decrypt(token.encode()).decode()
    except InvalidToken:
        raise AdminAuthError("admin_totp_unreadable", 503)


def verify_totp(cur, admin, code):
    """Checks a TOTP code for an enrolled admin: one use per time step, and
    a lockout after repeated failures. Raises on failure."""
    cur.execute("""
        SELECT totp_secret_enc, totp_last_step, totp_failures,
               (totp_locked_until IS NOT NULL AND totp_locked_until > NOW()) AS locked
        FROM admin_accounts WHERE id = %s FOR UPDATE
    """, (admin["admin_id"],))
    row = cur.fetchone()
    if not row or not row[0]:
        raise AdminAuthError("totp_enrollment_required", 403)
    if row[3]:
        raise AdminAuthError("totp_locked", 429)
    counter = _check_code(_decrypt(row[0]), code, row[1])
    if counter is None:
        failures = int(row[2] or 0) + 1
        cur.execute(f"""
            UPDATE admin_accounts SET totp_failures = %s,
                totp_locked_until = CASE WHEN %s >= {TOTP_MAX_FAILURES}
                    THEN NOW() + INTERVAL '{TOTP_LOCK_SECONDS} seconds' ELSE totp_locked_until END
            WHERE id = %s
        """, (failures, failures, admin["admin_id"]))
        raise AdminAuthError("totp_invalid", 401)
    cur.execute("UPDATE admin_accounts SET totp_last_step = %s, totp_failures = 0, totp_locked_until = NULL WHERE id = %s",
                (counter, admin["admin_id"]))


# --------------------------------------------------------------------------
# Audit (append-only)
# --------------------------------------------------------------------------

def audit(cur, actor, action, *, risk, target_account_id=None, target_ref=None, before=None, after=None,
          reason="", request_id=None, ip=None, channel=None):
    cur.execute("""
        INSERT INTO admin_audit_events (actor_admin_id, actor_account_id, channel, action, risk, target_account_id,
                                        target_ref, reason, before, after, request_id, ip_hash)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s, %s)
        RETURNING id
    """, ((actor or {}).get("admin_id"), (actor or {}).get("account_id"),
          channel or (actor or {}).get("channel") or "system", action, risk,
          int(target_account_id) if target_account_id else None, str(target_ref)[:200] if target_ref else None,
          str(reason or "")[:500], json.dumps(before or {}, default=str), json.dumps(after or {}, default=str),
          request_id, hash_ip(ip) if ip else None))
    return int(cur.fetchone()[0])


def list_audit(cur, *, actor_admin_id=None, target_account_id=None, action=None, risk=None, before_id=None, limit=50,
               actions=None, since=None, until=None):
    conditions, params = [], []
    if actions:
        conditions.append(f"action IN ({', '.join(['%s'] * len(actions))})")
        params.extend(actions)
    if since:
        conditions.append("at >= %s::timestamptz")
        params.append(since)
    if until:
        conditions.append("at < %s::timestamptz")
        params.append(until)
    for column, value in (("actor_admin_id", actor_admin_id), ("target_account_id", target_account_id),
                          ("action", action), ("risk", risk)):
        if value not in (None, ""):
            conditions.append(f"{column} = %s")
            params.append(value)
    if before_id:
        conditions.append("id < %s")
        params.append(int(before_id))
    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    limit = max(1, min(int(limit or 50), 100))
    cur.execute(f"""
        SELECT id, at, actor_admin_id, actor_account_id, channel, action, risk, target_account_id, target_ref,
               reason, before, after
        FROM admin_audit_events {where} ORDER BY id DESC LIMIT %s
    """, params + [limit])
    items = []
    for r in cur.fetchall():
        items.append({"id": int(r[0]), "at": _iso(r[1]), "actor_admin_id": r[2],
                      "actor_sylvex_user_id": str(r[3]) if r[3] else None, "channel": r[4], "action": r[5],
                      "risk": r[6], "target_sylvex_user_id": str(r[7]) if r[7] else None,
                      "reason": r[9] or "", "before": _json_obj(r[10]), "after": _json_obj(r[11])})
    next_before = items[-1]["id"] if len(items) == limit else None
    return items, next_before


def _json_obj(value):
    if isinstance(value, str):
        try:
            return json.loads(value)
        except ValueError:
            return {}
    return value or {}


# --------------------------------------------------------------------------
# Admin management
# --------------------------------------------------------------------------

def list_admins(cur):
    cur.execute(f"SELECT {_ADMIN_COLUMNS} FROM admin_accounts a "
                "LEFT JOIN sylvex_accounts s ON s.account_id = a.account_id ORDER BY a.role = 'owner' DESC, a.id")
    return [_admin_from_row(r) for r in cur.fetchall()]


def _lock_owners(cur):
    cur.execute("SELECT id FROM admin_accounts WHERE role = 'owner' AND status = 'active' FOR UPDATE")
    return {int(r[0]) for r in cur.fetchall()}


def create_admin(cur, actor, account_id, role, grants=(), denies=(), reason=""):
    cur.execute("SELECT 1 FROM sylvex_accounts WHERE account_id = %s AND active_telegram_id IS NOT NULL", (account_id,))
    if not cur.fetchone():
        raise AdminAuthError("account_not_found", 404)
    if load_admin(cur, account_id=account_id):
        raise AdminAuthError("already_admin", 409)
    try:
        rbac.check_admin_change(actor, None, role, grants, denies)
    except rbac.EscalationError as exc:
        raise AdminAuthError(exc.code, 403)
    cur.execute("""
        INSERT INTO admin_accounts (account_id, role, grants, denies, status, created_by)
        VALUES (%s, %s, %s::jsonb, %s::jsonb, 'active', %s) RETURNING id
    """, (account_id, role, json.dumps(sorted(set(grants))), json.dumps(sorted(set(denies))), actor["admin_id"]))
    admin_id = int(cur.fetchone()[0])
    audit(cur, actor, "admin_created", risk=rbac.CRITICAL, target_account_id=account_id, reason=reason,
          after={"admin_id": admin_id, "role": role, "grants": sorted(set(grants)), "denies": sorted(set(denies))})
    return load_admin(cur, admin_id=admin_id)


def update_admin(cur, actor, admin_id, *, role=None, grants=None, denies=None, status=None, reason=""):
    owners = _lock_owners(cur)
    target = load_admin(cur, admin_id=admin_id)
    if not target:
        raise AdminAuthError("admin_not_found", 404)
    new_role = role if role is not None else target["role"]
    new_grants = sorted(set(grants)) if grants is not None else target["grants"]
    new_denies = sorted(set(denies)) if denies is not None else target["denies"]
    new_status = status if status is not None else target["status"]
    if new_status not in ("active", "suspended", "revoked"):
        raise AdminAuthError("invalid_status", 400)
    try:
        rbac.check_admin_change(actor, target, new_role, new_grants, new_denies)
    except rbac.EscalationError as exc:
        raise AdminAuthError(exc.code, 403)
    loses_owner = target["role"] == rbac.OWNER and target["status"] == "active" and (
        new_role != rbac.OWNER or new_status != "active")
    if loses_owner and owners <= {target["admin_id"]}:
        raise AdminAuthError("last_owner_protected", 409)
    before = public_admin(target)
    cur.execute("""
        UPDATE admin_accounts SET role = %s, grants = %s::jsonb, denies = %s::jsonb, status = %s, updated_at = NOW()
        WHERE id = %s
    """, (new_role, json.dumps(new_grants), json.dumps(new_denies), new_status, admin_id))
    # Any change to what an admin may do takes effect at once.
    revoke_all_sessions(cur, admin_id)
    updated = load_admin(cur, admin_id=admin_id)
    audit(cur, actor, "admin_updated", risk=rbac.CRITICAL, target_account_id=target["account_id"], reason=reason,
          before=before, after=public_admin(updated))
    return updated
