"""Unified SYLVEX account identity: email/password + Telegram, one account.

Core rule (see sylvex-website's account architecture task): there is only
one internal SYLVEX account, identified by its `users.telegram_id` row -
the same row/column the Telegram Mini App has always used for balance,
subscription and every generation table. Email and Telegram are only ways
to *reach* that account, never a second business identity.

An email-only registrant is assigned a synthetic NEGATIVE telegram_id (real
Telegram ids are always positive - see services/security.py's
verify_telegram_login_widget), via `sylvex_email_account_seq`. Every
existing telegram_id-keyed code path (get_user_state, ensure_user_exists,
generation/pricing/history) therefore works for an email account completely
unmodified - it's just another (negative) id. Linking a real Telegram
identity later migrates that same account's rows onto the real positive id
(link_telegram) rather than creating a second account; if that real id
already has its own history, linking is refused with a conflict instead of
merging two independent accounts.
"""
from __future__ import annotations
import threading
from psycopg2 import sql, errors as pg_errors
from db_pool import db_connect
from services.password_auth import (
    hash_password, verify_password, new_token, is_valid_email, normalize_email, password_strength_error,
)
from services.account_email import send_verification_email, send_password_reset_email

VERIFICATION_TOKEN_TTL = "24 hours"
RESET_TOKEN_TTL = "1 hour"

# Columns outside the single, literal `telegram_id` name (found by auditing
# every CREATE TABLE in main.py) that also identify a SYLVEX account and
# must move with it when a real Telegram id is linked, so nothing is
# orphaned under the old synthetic id.
_SECONDARY_ID_COLUMNS = (
    ("referral_attributions", "inviter_telegram_id"),
    ("referral_attributions", "invited_telegram_id"),
    ("community_friendships", "requester_id"),
    ("community_friendships", "addressee_id"),
    ("community_messages", "sender_id"),
    ("community_messages", "recipient_id"),
    ("community_notifications", "actor_id"),
    ("admin_users", "granted_by"),
    ("admin_audit_log", "actor_telegram_id"),
    ("admin_audit_log", "target_telegram_id"),
    ("admin_messages", "admin_telegram_id"),
    ("admin_messages", "user_telegram_id"),
    ("prostudio_references", "created_by"),
)

_ACCOUNT_TABLES_LOCK = threading.Lock()
_ACCOUNT_TABLES_READY = False


class AccountError(Exception):
    def __init__(self, code, status=400):
        self.code = code
        self.status = status
        super().__init__(code)


def ensure_account_tables(database_url):
    global _ACCOUNT_TABLES_READY
    if _ACCOUNT_TABLES_READY or not database_url:
        return
    with _ACCOUNT_TABLES_LOCK:
        if _ACCOUNT_TABLES_READY:
            return
        conn = db_connect(database_url)
        cur = conn.cursor()
        try:
            cur.execute("CREATE SEQUENCE IF NOT EXISTS sylvex_email_account_seq START 1")
            cur.execute("""
                CREATE TABLE IF NOT EXISTS account_emails (
                    telegram_id BIGINT PRIMARY KEY,
                    email TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    email_verified BOOLEAN DEFAULT FALSE,
                    verification_token TEXT,
                    verification_token_expires_at TIMESTAMP,
                    reset_token TEXT,
                    reset_token_expires_at TIMESTAMP,
                    created_at TIMESTAMP DEFAULT NOW()
                )
            """)
            # Website-only: whether the Telegram Login Widget may sign in as
            # this account. Never read by the Mini App's own Telegram
            # initData auth (services/security.py), which is untouched -
            # "disconnecting" only ever removes a website sign-in option,
            # never Mini App access to the same account.
            cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS telegram_web_login_enabled BOOLEAN DEFAULT TRUE")
            conn.commit()
        finally:
            cur.close()
            conn.close()
        _ACCOUNT_TABLES_READY = True


def _telegram_id_columns(cur):
    cur.execute("""
        SELECT table_name, column_name FROM information_schema.columns
        WHERE table_schema = current_schema() AND column_name = 'telegram_id'
    """)
    return cur.fetchall()


# ---------------------------------------------------------------------------
# Registration / login
# ---------------------------------------------------------------------------

def register_email_account(database_url, email, password, display_name=None):
    email = normalize_email(email or "")
    if not is_valid_email(email):
        raise AccountError("invalid_email")
    pw_error = password_strength_error(password)
    if pw_error:
        raise AccountError(pw_error)
    ensure_account_tables(database_url)

    conn = db_connect(database_url)
    cur = conn.cursor()
    try:
        cur.execute("SELECT 1 FROM account_emails WHERE email = %s", (email,))
        if cur.fetchone():
            raise AccountError("email_already_registered", 409)

        cur.execute("SELECT nextval('sylvex_email_account_seq')")
        account_id = -int(cur.fetchone()[0])
        first_name = (display_name or email.split("@")[0]).strip()[:64] or "SYLVEX User"
        cur.execute(
            "INSERT INTO users (telegram_id, first_name, balance, subscription, created_at) "
            "VALUES (%s, %s, 0, NULL, NOW()::text)",
            (account_id, first_name),
        )
        token = new_token()
        cur.execute(
            "INSERT INTO account_emails (telegram_id, email, password_hash, verification_token, verification_token_expires_at) "
            f"VALUES (%s, %s, %s, %s, NOW() + INTERVAL '{VERIFICATION_TOKEN_TTL}')",
            (account_id, email, hash_password(password), token),
        )
        conn.commit()
    except pg_errors.UniqueViolation:
        conn.rollback()
        raise AccountError("email_already_registered", 409)
    except AccountError:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()

    send_verification_email(email, token)
    return account_id


def login_email_account(database_url, email, password):
    email = normalize_email(email or "")
    conn = db_connect(database_url)
    cur = conn.cursor()
    try:
        cur.execute("SELECT telegram_id, password_hash FROM account_emails WHERE email = %s", (email,))
        row = cur.fetchone()
    finally:
        cur.close()
        conn.close()
    if not row or not verify_password(password or "", row[1]):
        raise AccountError("invalid_credentials", 401)
    return int(row[0])


# ---------------------------------------------------------------------------
# Email identity lookups / verification / password reset
# ---------------------------------------------------------------------------

def get_email_identity(database_url, account_id):
    if not database_url:
        return None
    conn = db_connect(database_url)
    cur = conn.cursor()
    try:
        cur.execute(
            "SELECT email, email_verified FROM account_emails WHERE telegram_id = %s",
            (account_id,),
        )
        row = cur.fetchone()
    finally:
        cur.close()
        conn.close()
    if not row:
        return None
    return {"email": row[0], "email_verified": bool(row[1])}


def is_telegram_web_login_enabled(database_url, account_id):
    conn = db_connect(database_url)
    cur = conn.cursor()
    try:
        cur.execute("SELECT telegram_web_login_enabled FROM users WHERE telegram_id = %s", (account_id,))
        row = cur.fetchone()
    finally:
        cur.close()
        conn.close()
    return bool(row[0]) if row and row[0] is not None else True


def verify_email_token(database_url, token):
    conn = db_connect(database_url)
    cur = conn.cursor()
    try:
        cur.execute(
            "SELECT telegram_id FROM account_emails WHERE verification_token = %s AND verification_token_expires_at > NOW()",
            (token,),
        )
        row = cur.fetchone()
        if not row:
            raise AccountError("invalid_or_expired_token", 400)
        cur.execute(
            "UPDATE account_emails SET email_verified = TRUE, verification_token = NULL, verification_token_expires_at = NULL "
            "WHERE telegram_id = %s",
            (row[0],),
        )
        conn.commit()
    except AccountError:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()
    return int(row[0])


def resend_verification(database_url, account_id):
    conn = db_connect(database_url)
    cur = conn.cursor()
    try:
        cur.execute("SELECT email, email_verified FROM account_emails WHERE telegram_id = %s", (account_id,))
        row = cur.fetchone()
        if not row:
            raise AccountError("no_email_on_file", 404)
        if row[1]:
            raise AccountError("already_verified", 400)
        token = new_token()
        cur.execute(
            f"UPDATE account_emails SET verification_token = %s, verification_token_expires_at = NOW() + INTERVAL '{VERIFICATION_TOKEN_TTL}' "
            "WHERE telegram_id = %s",
            (token, account_id),
        )
        conn.commit()
    except AccountError:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()
    send_verification_email(row[0], token)


def request_password_reset(database_url, email):
    # Always returns normally (never reveals whether the email exists) -
    # only sends mail when it actually finds an account.
    email = normalize_email(email or "")
    if not email:
        return
    conn = db_connect(database_url)
    cur = conn.cursor()
    row = None
    try:
        cur.execute("SELECT telegram_id FROM account_emails WHERE email = %s", (email,))
        row = cur.fetchone()
        if row:
            token = new_token()
            cur.execute(
                f"UPDATE account_emails SET reset_token = %s, reset_token_expires_at = NOW() + INTERVAL '{RESET_TOKEN_TTL}' "
                "WHERE telegram_id = %s",
                (token, row[0]),
            )
            conn.commit()
    finally:
        cur.close()
        conn.close()
    if row:
        send_password_reset_email(email, token)


def reset_password_with_token(database_url, token, new_password):
    pw_error = password_strength_error(new_password)
    if pw_error:
        raise AccountError(pw_error)
    conn = db_connect(database_url)
    cur = conn.cursor()
    try:
        cur.execute(
            "SELECT telegram_id FROM account_emails WHERE reset_token = %s AND reset_token_expires_at > NOW()",
            (token,),
        )
        row = cur.fetchone()
        if not row:
            raise AccountError("invalid_or_expired_token", 400)
        cur.execute(
            "UPDATE account_emails SET password_hash = %s, reset_token = NULL, reset_token_expires_at = NULL WHERE telegram_id = %s",
            (hash_password(new_password), row[0]),
        )
        conn.commit()
    except AccountError:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()


def change_password(database_url, account_id, current_password, new_password):
    pw_error = password_strength_error(new_password)
    if pw_error:
        raise AccountError(pw_error)
    conn = db_connect(database_url)
    cur = conn.cursor()
    try:
        cur.execute("SELECT password_hash FROM account_emails WHERE telegram_id = %s", (account_id,))
        row = cur.fetchone()
        if not row:
            raise AccountError("no_email_on_file", 404)
        if not verify_password(current_password or "", row[0]):
            raise AccountError("incorrect_current_password", 401)
        cur.execute("UPDATE account_emails SET password_hash = %s WHERE telegram_id = %s", (hash_password(new_password), account_id))
        conn.commit()
    except AccountError:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()


def set_email_for_account(database_url, account_id, email, password):
    """Adds an email+password login to an account that doesn't have one yet
    (e.g. a Telegram-first account) - required so that account can later
    satisfy "keep at least one login method" when disconnecting Telegram."""
    email = normalize_email(email or "")
    if not is_valid_email(email):
        raise AccountError("invalid_email")
    pw_error = password_strength_error(password)
    if pw_error:
        raise AccountError(pw_error)
    ensure_account_tables(database_url)

    conn = db_connect(database_url)
    cur = conn.cursor()
    try:
        cur.execute("SELECT 1 FROM account_emails WHERE telegram_id = %s", (account_id,))
        if cur.fetchone():
            raise AccountError("email_already_set", 409)
        cur.execute("SELECT 1 FROM account_emails WHERE email = %s", (email,))
        if cur.fetchone():
            raise AccountError("email_already_registered", 409)
        token = new_token()
        cur.execute(
            "INSERT INTO account_emails (telegram_id, email, password_hash, verification_token, verification_token_expires_at) "
            f"VALUES (%s, %s, %s, %s, NOW() + INTERVAL '{VERIFICATION_TOKEN_TTL}')",
            (account_id, email, hash_password(password), token),
        )
        conn.commit()
    except pg_errors.UniqueViolation:
        conn.rollback()
        raise AccountError("email_already_registered", 409)
    except AccountError:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()
    send_verification_email(email, token)


# ---------------------------------------------------------------------------
# Telegram linking
# ---------------------------------------------------------------------------

def link_telegram(database_url, current_account_id, real_telegram_id, username, first_name):
    """Attaches a real Telegram identity to the currently signed-in account.

    - If `real_telegram_id` is already this account's id, just (re-)enable
      website sign-in via Telegram (covers reconnecting after a disconnect).
    - If `real_telegram_id` has never had a `users` row, this account's
      entire business history is migrated onto that real id (see module
      docstring) - the account's id changes, but it is still one account.
    - If `real_telegram_id` already belongs to a different, pre-existing
      account, nothing is merged or overwritten - a conflict is returned.
    """
    real_telegram_id = int(real_telegram_id)
    if real_telegram_id <= 0:
        raise AccountError("invalid_telegram_id")

    conn = db_connect(database_url)
    cur = conn.cursor()
    try:
        if real_telegram_id == current_account_id:
            cur.execute(
                "UPDATE users SET telegram_web_login_enabled = TRUE, username = COALESCE(%s, username), "
                "first_name = COALESCE(%s, first_name) WHERE telegram_id = %s",
                (username, first_name, real_telegram_id),
            )
            conn.commit()
            return {"status": "linked", "telegram_id": real_telegram_id}

        cur.execute("SELECT 1 FROM users WHERE telegram_id = %s", (real_telegram_id,))
        if cur.fetchone():
            # A different, pre-existing account already owns this Telegram
            # identity's history - never silently merge two real accounts.
            return {"status": "conflict", "telegram_id": real_telegram_id}

        ensure_account_tables(database_url)
        # The dynamic list only ever names tables/columns information_schema
        # confirms exist. _SECONDARY_ID_COLUMNS is a fixed list audited
        # against this codebase's CREATE TABLE statements, but some of those
        # tables (community/admin/referrals) are optional features that may
        # not have been provisioned in every deployment - skip, don't fail,
        # a migration over a table that was never created.
        for table, column in _SECONDARY_ID_COLUMNS:
            cur.execute("SELECT to_regclass(%s)", (table,))
            if cur.fetchone()[0] is None:
                continue
            cur.execute(
                sql.SQL("UPDATE {table} SET {col} = %s WHERE {col} = %s").format(
                    table=sql.Identifier(table), col=sql.Identifier(column),
                ),
                (real_telegram_id, current_account_id),
            )
        for table, column in _telegram_id_columns(cur):
            cur.execute(
                sql.SQL("UPDATE {table} SET {col} = %s WHERE {col} = %s").format(
                    table=sql.Identifier(table), col=sql.Identifier(column),
                ),
                (real_telegram_id, current_account_id),
            )
        cur.execute(
            "UPDATE users SET telegram_web_login_enabled = TRUE, username = COALESCE(%s, username), "
            "first_name = COALESCE(%s, first_name) WHERE telegram_id = %s",
            (username, first_name, real_telegram_id),
        )
        conn.commit()
    except Exception as exc:
        conn.rollback()
        print(f"TELEGRAM LINK FAILED: account_id={current_account_id} real_id={real_telegram_id} error={type(exc).__name__}: {exc}")
        raise AccountError("telegram_link_failed", 500)
    finally:
        cur.close()
        conn.close()
    return {"status": "linked", "telegram_id": real_telegram_id}


def disconnect_telegram(database_url, account_id):
    if account_id <= 0:
        raise AccountError("no_telegram_connected")
    identity = get_email_identity(database_url, account_id)
    if not identity or not identity.get("email_verified"):
        raise AccountError("verified_email_required", 400)
    conn = db_connect(database_url)
    cur = conn.cursor()
    try:
        cur.execute("UPDATE users SET telegram_web_login_enabled = FALSE WHERE telegram_id = %s", (account_id,))
        conn.commit()
    finally:
        cur.close()
        conn.close()
