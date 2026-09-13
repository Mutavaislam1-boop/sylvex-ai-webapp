"""Unified SYLVEX account identity: website (email/Google/Apple) + Telegram.

Core rule (see the "Final Account Registration, Linking & Cross-Platform
Identity System" spec): Website and Telegram are two independent starting
points. Neither forces the other:

- A website registrant (email+password, Google, or Apple) gets a real,
  independent `sylvex_accounts.account_id` (the user-facing "SYLVEX ID"),
  generated automatically the moment registration succeeds - never a fake
  or negative Telegram id, and never something the user manages by hand.
- A Telegram user needs no account at all and never sees an id - they use
  the bot/Mini App via their real `telegram_id`, exactly as today.

The two are only ever joined by an explicit, verified, ONE-TIME merge
(`_do_merge` below), never silently. Until that happens they are two
completely separate accounts. Because every existing telegram_id-keyed
table (balance, generations, purchases, subscriptions, ...) is the actual
business-data store, a website account's data lives under a hidden
"storage" telegram_id (from `sylvex_web_storage_seq`, a distinct, always
positive range far outside any real Telegram id - never exposed to the
user or API) until/unless it merges with a real Telegram identity. A merge
always consolidates the final business data onto the TELEGRAM side's real
`users.telegram_id` row, because that is the only row the Mini App's own
(untouched) Telegram initData auth can ever reach - but the website
account's `account_id`/`account_emails` identity survives forever
unchanged; only its `active_telegram_id` pointer is updated, once.
"""
from __future__ import annotations
import hashlib
import hmac
import secrets
import threading
from psycopg2 import sql, errors as pg_errors
from db_pool import db_connect
from services.password_auth import (
    hash_password, verify_password, new_token, is_valid_email, normalize_email, password_strength_error,
)
from services.account_email import send_verification_email, send_password_reset_email, send_merge_code_email

VERIFICATION_TOKEN_TTL = "24 hours"
RESET_TOKEN_TTL = "1 hour"
LINK_CODE_TTL = "10 minutes"
LINK_CODE_MAX_ATTEMPTS = 5

# The real SYLVEX product currently has one subscription tier ("Pro") sold
# at two billing periods. `tier` is compared first (higher tier always wins,
# for if/when a second tier is ever added); equal tiers fall back to later
# expiry. Keep in sync with main.py's SHOP_ITEMS - duplicated locally to
# avoid a circular import (main.py imports this module).
_PLAN_PRICING = {
    "sub_month": {"usd": 5.0, "days": 30, "tier": 1},
    "sub_year": {"usd": 59.0, "days": 365, "tier": 1},
}
CREDITS_PER_USD = 100  # 1 SYLVEX credit (⚡) = $0.01, per the pricing-catalog endpoint's own constant.

# Columns outside the single, literal `telegram_id` name (found by auditing
# every CREATE TABLE in main.py) that also identify a SYLVEX account and
# must move with it when a website account merges with a real Telegram
# identity, so nothing is orphaned under the old storage id.
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


def _violates_constraint(exc, name_substring):
    try:
        return name_substring in (exc.diag.constraint_name or "")
    except Exception:
        return False


class AccountError(Exception):
    def __init__(self, code, status=400):
        self.code = code
        self.status = status
        super().__init__(code)


def _migrate_legacy_negative_id_accounts(cur):
    """One-time, defensive migration from the earlier synthetic-negative-id
    architecture (see git history), if this deployment ever ran it: wraps
    each existing account_emails row in a real sylvex_accounts row instead
    of discarding it, preserving every already-registered user. A row whose
    old id was already a real (positive) Telegram id - i.e. it had already
    been "linked" under the old model - is marked already-merged, matching
    the outcome it already had. Never runs on a fresh install (no legacy
    `telegram_id` column to find), and never runs twice."""
    cur.execute("SELECT to_regclass('account_emails')")
    if cur.fetchone()[0] is None:
        return
    cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name = 'account_emails'")
    cols = {row[0] for row in cur.fetchall()}
    if "account_id" in cols or "telegram_id" not in cols:
        return
    cur.execute("ALTER TABLE account_emails ADD COLUMN account_id BIGINT")
    cur.execute("SELECT telegram_id FROM account_emails")
    for (old_id,) in cur.fetchall():
        old_id = int(old_id)
        cur.execute("SELECT nextval('sylvex_account_id_seq')")
        new_account_id = int(cur.fetchone()[0])
        already_real = old_id > 0
        cur.execute(
            "INSERT INTO sylvex_accounts (account_id, active_telegram_id, merged_telegram_id, merged_at) "
            "VALUES (%s, %s, %s, CASE WHEN %s THEN NOW() ELSE NULL END) ON CONFLICT DO NOTHING",
            (new_account_id, old_id, old_id if already_real else None, already_real),
        )
        cur.execute("UPDATE account_emails SET account_id = %s WHERE telegram_id = %s", (new_account_id, old_id))
    cur.execute("ALTER TABLE account_emails ALTER COLUMN account_id SET NOT NULL")
    cur.execute("ALTER TABLE account_emails DROP COLUMN telegram_id")
    cur.execute("ALTER TABLE account_emails ADD PRIMARY KEY (account_id)")


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
            cur.execute("CREATE SEQUENCE IF NOT EXISTS sylvex_account_id_seq START 10000")
            # Distinct, always-positive range far outside any real Telegram
            # id, used only as an internal storage key for a website
            # account's business rows - never shown to the user or returned
            # by any API (only account_id, the "SYLVEX ID", ever is).
            cur.execute("CREATE SEQUENCE IF NOT EXISTS sylvex_web_storage_seq START 900000000000")
            cur.execute("""
                CREATE TABLE IF NOT EXISTS sylvex_accounts (
                    account_id BIGINT PRIMARY KEY DEFAULT nextval('sylvex_account_id_seq'),
                    active_telegram_id BIGINT NOT NULL,
                    merged_telegram_id BIGINT,
                    merged_at TIMESTAMP,
                    created_at TIMESTAMP DEFAULT NOW()
                )
            """)
            cur.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS sylvex_accounts_active_telegram_id_key "
                "ON sylvex_accounts(active_telegram_id)"
            )
            _migrate_legacy_negative_id_accounts(cur)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS account_emails (
                    account_id BIGINT PRIMARY KEY REFERENCES sylvex_accounts(account_id),
                    email TEXT UNIQUE NOT NULL,
                    password_hash TEXT,
                    email_verified BOOLEAN DEFAULT FALSE,
                    verification_token TEXT,
                    verification_token_expires_at TIMESTAMP,
                    reset_token TEXT,
                    reset_token_expires_at TIMESTAMP,
                    created_at TIMESTAMP DEFAULT NOW()
                )
            """)
            # NULL for Google/Apple-created accounts that never set a
            # website password. Idempotent - a no-op once already nullable.
            cur.execute("ALTER TABLE account_emails ALTER COLUMN password_hash DROP NOT NULL")
            cur.execute("""
                CREATE TABLE IF NOT EXISTS account_oauth (
                    account_id BIGINT NOT NULL REFERENCES sylvex_accounts(account_id),
                    provider TEXT NOT NULL,
                    subject TEXT NOT NULL,
                    email TEXT,
                    created_at TIMESTAMP DEFAULT NOW(),
                    PRIMARY KEY (provider, subject)
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS account_link_codes (
                    id SERIAL PRIMARY KEY,
                    account_id BIGINT NOT NULL,
                    code_hash TEXT NOT NULL,
                    purpose TEXT NOT NULL,
                    attempts INTEGER NOT NULL DEFAULT 0,
                    expires_at TIMESTAMP NOT NULL,
                    consumed_at TIMESTAMP,
                    created_at TIMESTAMP DEFAULT NOW()
                )
            """)
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
# Registration / login (email+password)
# ---------------------------------------------------------------------------

def _new_web_account(cur, display_name, email_hint=None):
    """Allocates a fresh account_id + hidden storage telegram_id and the
    `users` row backing it. Shared by email registration and OAuth
    first-time sign-in."""
    cur.execute("SELECT nextval('sylvex_account_id_seq')")
    account_id = int(cur.fetchone()[0])
    cur.execute("SELECT nextval('sylvex_web_storage_seq')")
    storage_id = int(cur.fetchone()[0])
    first_name = (display_name or (email_hint or "").split("@")[0] or "SYLVEX User").strip()[:64] or "SYLVEX User"
    cur.execute("INSERT INTO sylvex_accounts (account_id, active_telegram_id) VALUES (%s, %s)", (account_id, storage_id))
    cur.execute(
        "INSERT INTO users (telegram_id, first_name, balance, subscription, created_at) VALUES (%s, %s, 0, NULL, NOW()::text)",
        (storage_id, first_name),
    )
    return account_id


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
        account_id = _new_web_account(cur, display_name, email)
        token = new_token()
        cur.execute(
            "INSERT INTO account_emails (account_id, email, password_hash, verification_token, verification_token_expires_at) "
            f"VALUES (%s, %s, %s, %s, NOW() + INTERVAL '{VERIFICATION_TOKEN_TTL}')",
            (account_id, email, hash_password(password), token),
        )
        conn.commit()
    except pg_errors.UniqueViolation as exc:
        conn.rollback()
        # Only a real duplicate-email race is "already registered" - any
        # other unique-constraint hit here (e.g. a colliding internal
        # storage id) is a server-side problem, not a user-facing 409, and
        # must never be misreported as one.
        if _violates_constraint(exc, "email"):
            raise AccountError("email_already_registered", 409)
        raise AccountError("registration_failed", 500)
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
        cur.execute("SELECT account_id, password_hash FROM account_emails WHERE email = %s", (email,))
        row = cur.fetchone()
    finally:
        cur.close()
        conn.close()
    if not row or not row[1] or not verify_password(password or "", row[1]):
        raise AccountError("invalid_credentials", 401)
    return int(row[0])


# ---------------------------------------------------------------------------
# Google / Apple sign-in
# ---------------------------------------------------------------------------

def oauth_login_or_register(database_url, provider, subject, email, display_name):
    """Finds or creates the SYLVEX account for a verified Google/Apple
    identity. If the identity's email already belongs to a registered
    account, signs into that account instead of creating a duplicate."""
    ensure_account_tables(database_url)
    email_n = normalize_email(email) if email else None
    conn = db_connect(database_url)
    cur = conn.cursor()
    try:
        cur.execute("SELECT account_id FROM account_oauth WHERE provider = %s AND subject = %s", (provider, subject))
        row = cur.fetchone()
        if row:
            conn.commit()
            return int(row[0])

        account_id = None
        if email_n:
            cur.execute("SELECT account_id FROM account_emails WHERE email = %s", (email_n,))
            existing = cur.fetchone()
            if existing:
                account_id = int(existing[0])
        if account_id is None:
            account_id = _new_web_account(cur, display_name, email_n)
            if email_n and is_valid_email(email_n):
                cur.execute(
                    "INSERT INTO account_emails (account_id, email, password_hash, email_verified) "
                    "VALUES (%s, %s, NULL, TRUE) ON CONFLICT (email) DO NOTHING",
                    (account_id, email_n),
                )
        cur.execute(
            "INSERT INTO account_oauth (account_id, provider, subject, email) VALUES (%s, %s, %s, %s) "
            "ON CONFLICT (provider, subject) DO NOTHING",
            (account_id, provider, subject, email_n),
        )
        conn.commit()
    except pg_errors.UniqueViolation as exc:
        conn.rollback()
        if _violates_constraint(exc, "email") or _violates_constraint(exc, "provider"):
            raise AccountError("oauth_conflict", 409)
        raise AccountError("registration_failed", 500)
    finally:
        cur.close()
        conn.close()
    return account_id


def login_via_telegram_widget(database_url, real_telegram_id):
    """"Login with Telegram" on the website only ever signs into an account
    that has already completed the Connect Telegram merge - Telegram itself
    is never a website *registration* method (see spec requirement #1)."""
    real_telegram_id = int(real_telegram_id)
    conn = db_connect(database_url)
    cur = conn.cursor()
    try:
        cur.execute(
            "SELECT account_id FROM sylvex_accounts WHERE active_telegram_id = %s AND merged_at IS NOT NULL",
            (real_telegram_id,),
        )
        row = cur.fetchone()
    finally:
        cur.close()
        conn.close()
    if not row:
        raise AccountError("telegram_not_linked", 404)
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
        cur.execute("SELECT email, email_verified FROM account_emails WHERE account_id = %s", (account_id,))
        row = cur.fetchone()
    finally:
        cur.close()
        conn.close()
    if not row:
        return None
    return {"email": row[0], "email_verified": bool(row[1])}


def get_account_summary(database_url, account_id):
    """Everything the website's "Linked Accounts" panel and session payload
    need beyond balance/subscription (which still comes from get_user_state
    on the account's active_telegram_id)."""
    conn = db_connect(database_url)
    cur = conn.cursor()
    try:
        cur.execute("SELECT active_telegram_id, merged_telegram_id, merged_at FROM sylvex_accounts WHERE account_id = %s", (account_id,))
        acc = cur.fetchone()
        if not acc:
            return None
        cur.execute("SELECT email, email_verified FROM account_emails WHERE account_id = %s", (account_id,))
        email_row = cur.fetchone()
        cur.execute("SELECT provider, email FROM account_oauth WHERE account_id = %s", (account_id,))
        oauth_rows = cur.fetchall()
    finally:
        cur.close()
        conn.close()
    return {
        "active_telegram_id": int(acc[0]),
        "telegram_connected": acc[2] is not None,
        "telegram_username": None,
        "merged_at": acc[2].isoformat() if acc[2] else None,
        "email": email_row[0] if email_row else None,
        "email_verified": bool(email_row[1]) if email_row else False,
        "has_email": email_row is not None,
        "oauth": {provider: email for provider, email in oauth_rows},
    }


def verify_email_token(database_url, token):
    conn = db_connect(database_url)
    cur = conn.cursor()
    try:
        cur.execute(
            "SELECT account_id FROM account_emails WHERE verification_token = %s AND verification_token_expires_at > NOW()",
            (token,),
        )
        row = cur.fetchone()
        if not row:
            raise AccountError("invalid_or_expired_token", 400)
        cur.execute(
            "UPDATE account_emails SET email_verified = TRUE, verification_token = NULL, verification_token_expires_at = NULL "
            "WHERE account_id = %s",
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
        cur.execute("SELECT email, email_verified FROM account_emails WHERE account_id = %s", (account_id,))
        row = cur.fetchone()
        if not row:
            raise AccountError("no_email_on_file", 404)
        if row[1]:
            raise AccountError("already_verified", 400)
        token = new_token()
        cur.execute(
            f"UPDATE account_emails SET verification_token = %s, verification_token_expires_at = NOW() + INTERVAL '{VERIFICATION_TOKEN_TTL}' "
            "WHERE account_id = %s",
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
        cur.execute("SELECT account_id FROM account_emails WHERE email = %s", (email,))
        row = cur.fetchone()
        if row:
            token = new_token()
            cur.execute(
                f"UPDATE account_emails SET reset_token = %s, reset_token_expires_at = NOW() + INTERVAL '{RESET_TOKEN_TTL}' "
                "WHERE account_id = %s",
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
            "SELECT account_id FROM account_emails WHERE reset_token = %s AND reset_token_expires_at > NOW()",
            (token,),
        )
        row = cur.fetchone()
        if not row:
            raise AccountError("invalid_or_expired_token", 400)
        cur.execute(
            "UPDATE account_emails SET password_hash = %s, reset_token = NULL, reset_token_expires_at = NULL WHERE account_id = %s",
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
        cur.execute("SELECT password_hash FROM account_emails WHERE account_id = %s", (account_id,))
        row = cur.fetchone()
        if not row:
            raise AccountError("no_email_on_file", 404)
        if row[0] and not verify_password(current_password or "", row[0]):
            raise AccountError("incorrect_current_password", 401)
        cur.execute("UPDATE account_emails SET password_hash = %s WHERE account_id = %s", (hash_password(new_password), account_id))
        conn.commit()
    except AccountError:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()


def set_email_for_account(database_url, account_id, email, password):
    """Adds an email+password login to an account that doesn't have one yet
    (e.g. a Google/Apple-created account)."""
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
        cur.execute("SELECT 1 FROM account_emails WHERE account_id = %s", (account_id,))
        if cur.fetchone():
            raise AccountError("email_already_set", 409)
        cur.execute("SELECT 1 FROM account_emails WHERE email = %s", (email,))
        if cur.fetchone():
            raise AccountError("email_already_registered", 409)
        token = new_token()
        cur.execute(
            "INSERT INTO account_emails (account_id, email, password_hash, verification_token, verification_token_expires_at) "
            f"VALUES (%s, %s, %s, %s, NOW() + INTERVAL '{VERIFICATION_TOKEN_TTL}')",
            (account_id, email, hash_password(password), token),
        )
        conn.commit()
    except pg_errors.UniqueViolation as exc:
        conn.rollback()
        # Only a real duplicate-email race is "already registered" - any
        # other unique-constraint hit here (e.g. a colliding internal
        # storage id) is a server-side problem, not a user-facing 409, and
        # must never be misreported as one.
        if _violates_constraint(exc, "email"):
            raise AccountError("email_already_registered", 409)
        raise AccountError("registration_failed", 500)
    except AccountError:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()
    send_verification_email(email, token)


# ---------------------------------------------------------------------------
# Telegram merge: preview + confirm, shared by both directions
# ---------------------------------------------------------------------------

def _active_subscription(cur, telegram_id):
    cur.execute(
        "SELECT subscription_type, expires_at::timestamp, "
        "GREATEST(0, EXTRACT(EPOCH FROM (expires_at::timestamp - NOW())) / 86400.0) "
        "FROM subscriptions WHERE telegram_id = %s AND status = 'active' AND expires_at::timestamp > NOW() "
        "ORDER BY expires_at::timestamp DESC LIMIT 1",
        (telegram_id,),
    )
    row = cur.fetchone()
    if not row:
        return None
    return {"plan": row[0], "expires_at": row[1].isoformat() if row[1] else None, "remaining_days": float(row[2])}


def _resolve_subscription(website_sub, telegram_sub):
    """Implements spec rules #13-#17: only one subscription ever survives a
    merge (never stacked as time). Different tiers -> higher tier wins.
    Same tier -> later expiry wins. Either way the losing side's unused
    paid value converts to SYLVEX credits (⚡), never extra months."""
    if not website_sub and not telegram_sub:
        return {"both_active": False, "surviving_plan": None, "surviving_expires_at": None,
                "credits_from_conversion": 0, "converted_plan": None, "converted_remaining_days": 0, "loser_side": None}
    if not (website_sub and telegram_sub):
        winner = website_sub or telegram_sub
        return {"both_active": False, "surviving_plan": winner["plan"], "surviving_expires_at": winner["expires_at"],
                "credits_from_conversion": 0, "converted_plan": None, "converted_remaining_days": 0, "loser_side": None}

    w_tier = _PLAN_PRICING.get(website_sub["plan"], {}).get("tier", 1)
    t_tier = _PLAN_PRICING.get(telegram_sub["plan"], {}).get("tier", 1)
    website_wins = w_tier > t_tier if w_tier != t_tier else website_sub["expires_at"] >= telegram_sub["expires_at"]
    winner, loser, loser_side = (website_sub, telegram_sub, "telegram") if website_wins else (telegram_sub, website_sub, "website")

    loser_pricing = _PLAN_PRICING.get(loser["plan"], {"usd": 0.0, "days": 30})
    daily_credits = (loser_pricing["usd"] * CREDITS_PER_USD) / max(loser_pricing["days"], 1)
    credits_from_conversion = int(round(loser["remaining_days"] * daily_credits))
    return {
        "both_active": True,
        "surviving_plan": winner["plan"], "surviving_expires_at": winner["expires_at"],
        "credits_from_conversion": credits_from_conversion,
        "converted_plan": loser["plan"], "converted_remaining_days": round(loser["remaining_days"], 1),
        "loser_side": loser_side,
    }


def preview_merge(database_url, account_id, real_telegram_id):
    real_telegram_id = int(real_telegram_id)
    if real_telegram_id <= 0:
        raise AccountError("invalid_telegram_id")
    ensure_account_tables(database_url)
    conn = db_connect(database_url)
    cur = conn.cursor()
    try:
        cur.execute("SELECT active_telegram_id, merged_at FROM sylvex_accounts WHERE account_id = %s", (account_id,))
        row = cur.fetchone()
        if not row:
            raise AccountError("account_not_found", 404)
        storage_id, merged_at = row
        if storage_id == real_telegram_id:
            return {"status": "already_linked"}
        if merged_at is not None:
            return {"status": "conflict"}
        cur.execute("SELECT account_id FROM sylvex_accounts WHERE active_telegram_id = %s", (real_telegram_id,))
        if cur.fetchone():
            return {"status": "conflict"}
        cur.execute("SELECT COALESCE(balance, 0) FROM users WHERE telegram_id = %s", (storage_id,))
        website_row = cur.fetchone()
        website_balance = int(website_row[0]) if website_row else 0
        cur.execute("SELECT COALESCE(balance, 0) FROM users WHERE telegram_id = %s", (real_telegram_id,))
        telegram_row = cur.fetchone()
        telegram_balance = int(telegram_row[0]) if telegram_row else 0
        website_sub = _active_subscription(cur, storage_id)
        telegram_sub = _active_subscription(cur, real_telegram_id)
    finally:
        cur.close()
        conn.close()
    resolution = _resolve_subscription(website_sub, telegram_sub)
    return {
        "status": "ok",
        "website_balance": website_balance,
        "telegram_balance": telegram_balance,
        "combined_balance": website_balance + telegram_balance + resolution["credits_from_conversion"],
        "website_subscription": website_sub,
        "telegram_subscription": telegram_sub,
        "resolution": resolution,
        "requires_subscription_confirmation": resolution["both_active"],
    }


def _consolidate_business_data(cur, from_telegram_id, to_telegram_id):
    # `users` is handled separately by the caller (its telegram_id is the
    # primary key and the destination row already exists - this only moves
    # every *other* table's history/content rows).
    for table, column in _SECONDARY_ID_COLUMNS:
        cur.execute("SELECT to_regclass(%s)", (table,))
        if cur.fetchone()[0] is None:
            continue
        cur.execute(
            sql.SQL("UPDATE {table} SET {col} = %s WHERE {col} = %s").format(
                table=sql.Identifier(table), col=sql.Identifier(column)),
            (to_telegram_id, from_telegram_id),
        )
    for table, column in _telegram_id_columns(cur):
        if table == "users":
            continue
        cur.execute(
            sql.SQL("UPDATE {table} SET {col} = %s WHERE {col} = %s").format(
                table=sql.Identifier(table), col=sql.Identifier(column)),
            (to_telegram_id, from_telegram_id),
        )


def _do_merge(database_url, account_id, real_telegram_id, username, first_name, confirmed_subscription_merge):
    real_telegram_id = int(real_telegram_id)
    if real_telegram_id <= 0:
        raise AccountError("invalid_telegram_id")
    ensure_account_tables(database_url)
    conn = db_connect(database_url)
    cur = conn.cursor()
    try:
        cur.execute("SELECT active_telegram_id, merged_at FROM sylvex_accounts WHERE account_id = %s FOR UPDATE", (account_id,))
        row = cur.fetchone()
        if not row:
            raise AccountError("account_not_found", 404)
        storage_id, merged_at = row
        if storage_id == real_telegram_id:
            return {"status": "already_linked", "telegram_id": real_telegram_id}
        if merged_at is not None:
            raise AccountError("account_already_merged", 409)
        cur.execute("SELECT account_id FROM sylvex_accounts WHERE active_telegram_id = %s", (real_telegram_id,))
        if cur.fetchone():
            raise AccountError("telegram_already_linked", 409)

        cur.execute("SELECT 1 FROM users WHERE telegram_id = %s FOR UPDATE", (real_telegram_id,))
        if not cur.fetchone():
            cur.execute(
                "INSERT INTO users (telegram_id, first_name, balance, subscription, created_at) VALUES (%s, %s, 0, NULL, NOW()::text)",
                (real_telegram_id, first_name or "SYLVEX User"),
            )
        cur.execute("SELECT COALESCE(balance, 0) FROM users WHERE telegram_id = %s FOR UPDATE", (storage_id,))
        website_balance = int(cur.fetchone()[0])
        cur.execute("SELECT COALESCE(balance, 0) FROM users WHERE telegram_id = %s FOR UPDATE", (real_telegram_id,))
        telegram_balance = int(cur.fetchone()[0])

        website_sub = _active_subscription(cur, storage_id)
        telegram_sub = _active_subscription(cur, real_telegram_id)
        resolution = _resolve_subscription(website_sub, telegram_sub)
        if resolution["both_active"] and not confirmed_subscription_merge:
            raise AccountError("subscription_confirmation_required", 409)

        if resolution["both_active"]:
            losing_telegram_id = storage_id if resolution["loser_side"] == "website" else real_telegram_id
            cur.execute("UPDATE subscriptions SET status = 'cancelled' WHERE telegram_id = %s AND status = 'active'", (losing_telegram_id,))

        _consolidate_business_data(cur, storage_id, real_telegram_id)

        new_balance = website_balance + telegram_balance + resolution["credits_from_conversion"]
        cur.execute("UPDATE users SET balance = %s WHERE telegram_id = %s", (new_balance, real_telegram_id))
        cur.execute("UPDATE users SET balance = 0 WHERE telegram_id = %s", (storage_id,))
        cur.execute(
            "UPDATE users SET username = COALESCE(%s, username), first_name = COALESCE(%s, first_name) WHERE telegram_id = %s",
            (username, first_name, real_telegram_id),
        )
        cur.execute(
            "UPDATE sylvex_accounts SET active_telegram_id = %s, merged_telegram_id = %s, merged_at = NOW() WHERE account_id = %s",
            (real_telegram_id, real_telegram_id, account_id),
        )
        conn.commit()
    except pg_errors.UniqueViolation:
        conn.rollback()
        raise AccountError("telegram_already_linked", 409)
    except AccountError:
        conn.rollback()
        raise
    except Exception as exc:
        conn.rollback()
        print(f"ACCOUNT MERGE FAILED: account_id={account_id} real_telegram_id={real_telegram_id} error={type(exc).__name__}: {exc}")
        raise AccountError("merge_failed", 500)
    finally:
        cur.close()
        conn.close()
    return {"status": "linked", "telegram_id": real_telegram_id, "combined_balance": new_balance, "subscription_resolution": resolution}


def confirm_merge_via_widget(database_url, account_id, real_telegram_id, username=None, first_name=None, confirmed_subscription_merge=False):
    """Website-initiated direction (Connect Telegram in Settings). Ownership
    of `real_telegram_id` was already proven by the caller verifying a
    Telegram Login Widget payload (services.security.verify_telegram_login_widget)."""
    return _do_merge(database_url, account_id, real_telegram_id, username, first_name, confirmed_subscription_merge)


# ---------------------------------------------------------------------------
# Telegram merge: Mini-App-initiated direction ("Connect existing SYLVEX
# account" / "Connect Email"), verified by a one-time emailed code instead
# of the Telegram Login Widget (the Mini App already knows its own real
# telegram_id via initData - what it needs proven is the *email's* ownership).
# ---------------------------------------------------------------------------

def request_email_link_code(database_url, email):
    # Always returns normally (never reveals whether the email exists).
    email = normalize_email(email or "")
    if not email:
        return
    ensure_account_tables(database_url)
    conn = db_connect(database_url)
    cur = conn.cursor()
    row = None
    try:
        cur.execute("SELECT account_id FROM account_emails WHERE email = %s AND email_verified = TRUE", (email,))
        row = cur.fetchone()
        if row:
            account_id = int(row[0])
            cur.execute(
                "SELECT 1 FROM account_link_codes WHERE account_id = %s AND purpose = 'telegram_connect_email' "
                "AND created_at > NOW() - INTERVAL '60 seconds'",
                (account_id,),
            )
            if cur.fetchone():
                raise AccountError("code_recently_sent", 429)
            code = f"{secrets.randbelow(1000000):06d}"
            code_hash = hashlib.sha256(code.encode()).hexdigest()
            cur.execute(
                "DELETE FROM account_link_codes WHERE account_id = %s AND purpose = 'telegram_connect_email'",
                (account_id,),
            )
            cur.execute(
                f"INSERT INTO account_link_codes (account_id, code_hash, purpose, expires_at) "
                f"VALUES (%s, %s, 'telegram_connect_email', NOW() + INTERVAL '{LINK_CODE_TTL}')",
                (account_id, code_hash),
            )
            conn.commit()
    finally:
        cur.close()
        conn.close()
    if row:
        send_merge_code_email(email, code)


def _consume_email_link_code(database_url, email, code, consume):
    email = normalize_email(email or "")
    conn = db_connect(database_url)
    cur = conn.cursor()
    try:
        cur.execute(
            "SELECT c.id, c.account_id, c.code_hash, c.attempts "
            "FROM account_link_codes c JOIN account_emails e ON e.account_id = c.account_id "
            "WHERE e.email = %s AND c.purpose = 'telegram_connect_email' AND c.consumed_at IS NULL "
            "AND c.expires_at > NOW() ORDER BY c.created_at DESC LIMIT 1",
            (email,),
        )
        row = cur.fetchone()
        if not row:
            raise AccountError("invalid_or_expired_code", 400)
        code_id, account_id, code_hash, attempts = row
        if attempts >= LINK_CODE_MAX_ATTEMPTS:
            raise AccountError("invalid_or_expired_code", 400)
        if not hmac.compare_digest(hashlib.sha256((code or "").encode()).hexdigest(), code_hash):
            cur.execute("UPDATE account_link_codes SET attempts = attempts + 1 WHERE id = %s", (code_id,))
            conn.commit()
            raise AccountError("invalid_or_expired_code", 400)
        if consume:
            cur.execute("UPDATE account_link_codes SET consumed_at = NOW() WHERE id = %s", (code_id,))
            conn.commit()
    except AccountError:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()
    return int(account_id)


def resolve_email_link_code(database_url, email, code):
    """Validates a code without consuming it, for showing the merge preview
    before the user commits. Wrong guesses still count against the attempt
    limit."""
    return _consume_email_link_code(database_url, email, code, consume=False)


def confirm_merge_via_email_code(database_url, real_telegram_id, email, code, username=None, first_name=None, confirmed_subscription_merge=False):
    """Mini-App-initiated direction. Consumes the emailed code (single-use)
    and, only if that succeeds, performs the merge."""
    account_id = _consume_email_link_code(database_url, email, code, consume=True)
    return _do_merge(database_url, account_id, real_telegram_id, username, first_name, confirmed_subscription_merge)


def get_link_status_for_telegram(database_url, real_telegram_id):
    """For the Mini App's own account-settings panel (spec requirement
    #20), which only ever knows its real telegram_id, never an account_id."""
    ensure_account_tables(database_url)
    real_telegram_id = int(real_telegram_id)
    conn = db_connect(database_url)
    cur = conn.cursor()
    try:
        cur.execute("SELECT account_id FROM sylvex_accounts WHERE active_telegram_id = %s", (real_telegram_id,))
        row = cur.fetchone()
    finally:
        cur.close()
        conn.close()
    if not row:
        return {"connected": False}
    account_id = int(row[0])
    summary = get_account_summary(database_url, account_id) or {}
    return {"connected": True, "account_id": account_id, "email": summary.get("email"), "email_verified": summary.get("email_verified", False)}
