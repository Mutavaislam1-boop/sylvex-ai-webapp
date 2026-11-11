"""Support-assisted erasure of a Telegram-origin SYLVEX account (B09, S7-04).

The Telegram bot and Mini App have no self-service deletion; the published
Deletion Policy routes the request through support. This module only adds a
safe intake for such a request; the erasure itself is the existing confirmed
request processor of B09-WEB (account_erasure.accept_confirmed_request with
ecosystem='telegram': durable journal, session revocation, bot cache clear,
financial records kept).

1. start   - an administrator with the Critical permission users.delete
             (fresh TOTP re-authentication) starts a request from the user's
             card with the support reference. After the scope checks the bot
             sends the account's own Telegram chat a one-time 6-digit code.
             Only the person who controls that Telegram account can read it;
             the console never sees it.
2. The person gives the code to support only if they asked for deletion.
3. confirm - the administrator enters the code and retypes the Telegram ID.
             The scope is checked again and the request is accepted.

Wrong codes are counted (5 at most), a code lives 24 hours, at most 3 codes
a day per account. Every step is written to the admin audit log. Nothing is
deleted here.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
from uuid import UUID, uuid4

TABLE = "sylvex_tg_erasure_confirmations"
CODE_TTL_SECONDS = 24 * 3600
MAX_ATTEMPTS = 5
MAX_STARTS_PER_DAY = 3
TELEGRAM_ID_CEILING = 900000000000  # account_erasure.WEB_STORAGE_FLOOR
LOCK_NAMESPACE = 61183

MESSAGE = (
    "SYLVEX: в поддержку поступил запрос на удаление вашего аккаунта SYLVEX в Telegram. "
    "История, файлы, баланс и подписка будут удалены без возможности восстановления.\n\n"
    "Код подтверждения: {code}\n\n"
    "Сообщите этот код поддержке, только если удаление запросили вы. Код действует 24 часа. "
    "Если вы ничего не запрашивали, просто не отвечайте: без кода аккаунт не будет удалён."
)


class TelegramErasureError(Exception):
    def __init__(self, code, status=409, **extra):
        self.code, self.status, self.extra = code, status, extra
        super().__init__(code)


def ensure_schema(cur):
    cur.execute(f"""
        CREATE TABLE IF NOT EXISTS {TABLE} (
            confirmation_id UUID PRIMARY KEY,
            account_id BIGINT NOT NULL,
            telegram_id BIGINT NOT NULL,
            code_hash TEXT NOT NULL DEFAULT '',
            attempts INTEGER NOT NULL DEFAULT 0,
            state TEXT NOT NULL CHECK (state IN ('sent','confirmed','cancelled','expired','failed')),
            support_ref TEXT NOT NULL DEFAULT '',
            created_by_admin_id BIGINT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            expires_at TIMESTAMPTZ NOT NULL,
            closed_at TIMESTAMPTZ,
            closed_by_admin_id BIGINT,
            close_reason TEXT NOT NULL DEFAULT '',
            request_id UUID
        )
    """)
    cur.execute(f"CREATE UNIQUE INDEX IF NOT EXISTS tg_erasure_one_open ON {TABLE}(telegram_id) WHERE state='sent'")
    cur.execute(f"CREATE INDEX IF NOT EXISTS tg_erasure_by_telegram ON {TABLE}(telegram_id, created_at DESC)")


def _iso(value):
    return value.isoformat() if hasattr(value, "isoformat") else (str(value) if value is not None else None)


def _hash(confirmation_id, code):
    return hashlib.pbkdf2_hmac("sha256", str(code).encode(), str(confirmation_id).encode(), 200_000).hex()


def _telegram_id(value):
    try:
        value = int(str(value).strip())
    except (TypeError, ValueError):
        raise TelegramErasureError("invalid_telegram_id", 400) from None
    if not 0 < value < TELEGRAM_ID_CEILING:
        raise TelegramErasureError("invalid_telegram_id", 400)
    return value


def _table_exists(cur, name):
    cur.execute("SELECT to_regclass(%s) IS NOT NULL", (name,))
    return bool(cur.fetchone()[0])


def check_scope(cur, telegram_id, actor=None):
    """account_id of a Telegram-origin account that can be erased now, or an error.

    Refused: a website or merged account (those have their own flow), an
    account with a request already, a team member, and a Telegram Stars
    subscription that still renews (support stops the renewal first, with
    the existing "Cancel subscription" action; erasure never touches it).
    """
    telegram_id = _telegram_id(telegram_id)
    cur.execute("SELECT account_id, origin, storage_telegram_id, merged_telegram_id, merged_into_account_id, merged_at "
                "FROM sylvex_accounts WHERE active_telegram_id=%s", (telegram_id,))
    row = cur.fetchone()
    if not row:
        raise TelegramErasureError("telegram_account_not_found", 404)
    account_id, origin, storage, merged, merged_into, merged_at = row
    if origin != "telegram":
        raise TelegramErasureError("not_a_telegram_account")
    if merged or merged_into or merged_at or (storage is not None and int(storage) != telegram_id):
        raise TelegramErasureError("telegram_scope_requires_review")
    if actor and int(actor.get("account_id") or 0) == int(account_id):
        raise TelegramErasureError("cannot_erase_self", 403)
    if _table_exists(cur, "sylvex_erasure_requests"):
        cur.execute("SELECT 1 FROM sylvex_erasure_requests WHERE account_id=%s OR subject_key=%s",
                    (int(account_id), telegram_id))
        if cur.fetchone():
            raise TelegramErasureError("erasure_already_requested")
    if _table_exists(cur, "admin_accounts"):
        cur.execute("SELECT 1 FROM admin_accounts WHERE account_id=%s AND status<>'revoked'", (int(account_id),))
        if cur.fetchone():
            raise TelegramErasureError("staff_account_requires_handover")
    if _table_exists(cur, "subscription_agreements"):
        cur.execute("SELECT 1 FROM subscription_agreements WHERE telegram_id=%s "
                    "AND renewal_status IN ('auto','stop_pending') LIMIT 1", (telegram_id,))
        if cur.fetchone():
            raise TelegramErasureError("stars_renewal_active")
    return int(account_id), telegram_id


def _audit(audit, cur, actor, action, account_id, telegram_id, reason, after):
    from services import admin_rbac
    audit(cur, actor, action, risk=admin_rbac.CRITICAL, target_account_id=account_id,
          target_ref=f"telegram:{telegram_id}", reason=reason, after=after)


def start(cur, actor, telegram_id, *, support_ref, reason, send, audit):
    """Send the one-time code to the account's Telegram chat. Returns a dict;
    a failed delivery is returned (and audited), not raised, so it is kept."""
    support_ref = str(support_ref or "").strip()[:200]
    if not support_ref:
        raise TelegramErasureError("support_reference_required", 400)
    if not str(reason or "").strip():
        raise TelegramErasureError("reason_required", 400)
    ensure_schema(cur)
    account_id, telegram_id = check_scope(cur, telegram_id, actor)
    cur.execute("SELECT pg_advisory_xact_lock(%s, hashtext(%s))", (LOCK_NAMESPACE, str(telegram_id)))
    cur.execute(f"UPDATE {TABLE} SET state='expired', closed_at=NOW(), close_reason='expired' "
                "WHERE telegram_id=%s AND state='sent' AND expires_at<=NOW()", (telegram_id,))
    cur.execute(f"SELECT confirmation_id FROM {TABLE} WHERE telegram_id=%s AND state='sent'", (telegram_id,))
    open_row = cur.fetchone()
    if open_row:
        raise TelegramErasureError("code_already_sent", 409, confirmation_id=str(open_row[0]))
    cur.execute(f"SELECT COUNT(*) FROM {TABLE} WHERE telegram_id=%s AND created_at>NOW()-INTERVAL '1 day'",
                (telegram_id,))
    if int(cur.fetchone()[0]) >= MAX_STARTS_PER_DAY:
        raise TelegramErasureError("too_many_codes", 429)
    confirmation_id = str(uuid4())
    code = f"{secrets.randbelow(10 ** 6):06d}"
    cur.execute(f"INSERT INTO {TABLE}(confirmation_id, account_id, telegram_id, code_hash, state, support_ref, "
                "created_by_admin_id, expires_at) VALUES (%s,%s,%s,%s,'sent',%s,%s,NOW()+(%s*INTERVAL '1 second')) "
                "RETURNING expires_at",
                (confirmation_id, account_id, telegram_id, _hash(confirmation_id, code), support_ref,
                 actor.get("admin_id"), CODE_TTL_SECONDS))
    expires_at = cur.fetchone()[0]
    ok, error = send(telegram_id, MESSAGE.format(code=code))
    del code
    after = {"confirmation_id": confirmation_id, "support_ref": support_ref, "delivered": bool(ok)}
    if not ok:
        cur.execute(f"UPDATE {TABLE} SET state='failed', code_hash='', closed_at=NOW(), close_reason=%s "
                    "WHERE confirmation_id=%s", (str(error or "delivery_failed")[:120], confirmation_id))
        _audit(audit, cur, actor, "telegram_erasure_code_failed", account_id, telegram_id, reason,
               dict(after, error=str(error or "")[:120]))
        return {"ok": False, "error": "code_delivery_failed", "status": 502,
                "telegram_error": str(error or "")[:120]}
    _audit(audit, cur, actor, "telegram_erasure_code_sent", account_id, telegram_id, reason, after)
    return {"ok": True, "confirmation_id": confirmation_id, "expires_at": _iso(expires_at),
            "telegram_hint": "…" + str(telegram_id)[-4:]}


def _confirmation(cur, confirmation_id):
    try:
        confirmation_id = str(UUID(str(confirmation_id)))
    except (TypeError, ValueError):
        raise TelegramErasureError("confirmation_not_found", 404) from None
    ensure_schema(cur)
    cur.execute(f"SELECT confirmation_id, account_id, telegram_id, code_hash, attempts, state, support_ref, "
                f"expires_at<=NOW() FROM {TABLE} WHERE confirmation_id=%s FOR UPDATE", (confirmation_id,))
    row = cur.fetchone()
    if not row:
        raise TelegramErasureError("confirmation_not_found", 404)
    keys = ("confirmation_id", "account_id", "telegram_id", "code_hash", "attempts", "state", "support_ref", "expired")
    return dict(zip(keys, row))


def confirm(cur, actor, confirmation_id, *, code, confirm_telegram_id, reason, accept, audit):
    """Accept the erasure request after the person's code. Returns a dict; a
    wrong code is counted and returned (committed), not raised."""
    item = _confirmation(cur, confirmation_id)
    if item["state"] != "sent":
        raise TelegramErasureError("confirmation_closed")
    try:
        typed = int(str(confirm_telegram_id or "").strip())
    except ValueError:
        typed = 0
    if typed != int(item["telegram_id"]):
        raise TelegramErasureError("telegram_id_mismatch", 400)
    if item["expired"]:
        cur.execute(f"UPDATE {TABLE} SET state='expired', code_hash='', closed_at=NOW(), close_reason='expired' "
                    "WHERE confirmation_id=%s", (item["confirmation_id"],))
        return {"ok": False, "error": "code_expired", "status": 400}
    code = str(code or "").strip()
    if not (len(code) == 6 and code.isdigit()
            and hmac.compare_digest(_hash(item["confirmation_id"], code), item["code_hash"])):
        attempts = int(item["attempts"]) + 1
        left = MAX_ATTEMPTS - attempts
        if left <= 0:
            cur.execute(f"UPDATE {TABLE} SET attempts=%s, state='cancelled', code_hash='', closed_at=NOW(), "
                        "closed_by_admin_id=%s, close_reason='too_many_attempts' WHERE confirmation_id=%s",
                        (attempts, actor.get("admin_id"), item["confirmation_id"]))
            _audit(audit, cur, actor, "telegram_erasure_code_locked", item["account_id"], item["telegram_id"],
                   reason or "too many wrong codes", {"confirmation_id": item["confirmation_id"]})
            return {"ok": False, "error": "too_many_attempts", "status": 429}
        cur.execute(f"UPDATE {TABLE} SET attempts=%s WHERE confirmation_id=%s", (attempts, item["confirmation_id"]))
        return {"ok": False, "error": "invalid_code", "status": 400, "attempts_left": left}
    if not str(reason or "").strip():
        raise TelegramErasureError("reason_required", 400)
    # The state may have changed since the code was sent (a renewal, a team role).
    account_id, telegram_id = check_scope(cur, item["telegram_id"], actor)
    if account_id != int(item["account_id"]):
        raise TelegramErasureError("telegram_scope_requires_review")
    result = accept(cur, account_id, ecosystem="telegram")
    cur.execute(f"UPDATE {TABLE} SET state='confirmed', code_hash='', closed_at=NOW(), closed_by_admin_id=%s, "
                "close_reason='confirmed', request_id=%s WHERE confirmation_id=%s",
                (actor.get("admin_id"), result["request_id"], item["confirmation_id"]))
    _audit(audit, cur, actor, "telegram_erasure_accepted", account_id, telegram_id, reason,
           {"confirmation_id": item["confirmation_id"], "support_ref": item["support_ref"],
            "request_id": result["request_id"], "state": result["state"]})
    return {"ok": True, "accepted": True, "request_id": result["request_id"], "state": result["state"]}


def cancel(cur, actor, confirmation_id, *, reason, audit):
    item = _confirmation(cur, confirmation_id)
    if item["state"] != "sent":
        raise TelegramErasureError("confirmation_closed")
    cur.execute(f"UPDATE {TABLE} SET state='cancelled', code_hash='', closed_at=NOW(), closed_by_admin_id=%s, "
                "close_reason='cancelled' WHERE confirmation_id=%s", (actor.get("admin_id"), item["confirmation_id"]))
    _audit(audit, cur, actor, "telegram_erasure_cancelled", item["account_id"], item["telegram_id"],
           reason or "cancelled", {"confirmation_id": item["confirmation_id"]})
    return {"ok": True}


def status(cur, telegram_id):
    """The latest codes and the erasure request for one Telegram account (no codes)."""
    telegram_id = _telegram_id(telegram_id)
    ensure_schema(cur)
    cur.execute(f"SELECT confirmation_id, state, attempts, support_ref, created_at, expires_at, closed_at, close_reason, "
                f"request_id FROM {TABLE} WHERE telegram_id=%s ORDER BY created_at DESC LIMIT 5", (telegram_id,))
    keys = ("confirmation_id", "state", "attempts", "support_ref", "created_at", "expires_at", "closed_at",
            "close_reason", "request_id")
    codes = [{k: (str(v) if k in ("confirmation_id", "request_id") and v else _iso(v) if k.endswith("_at") else v)
              for k, v in zip(keys, row)} for row in cur.fetchall()]
    request = None
    if _table_exists(cur, "sylvex_erasure_requests"):
        cur.execute("SELECT request_id, state, hold_code, requested_at, completed_at FROM sylvex_erasure_requests "
                    "WHERE subject_key=%s", (telegram_id,))
        row = cur.fetchone()
        if row:
            request = {"request_id": str(row[0]), "state": row[1], "hold_code": row[2],
                       "requested_at": _iso(row[3]), "completed_at": _iso(row[4])}
    blocker = None
    try:
        check_scope(cur, telegram_id)
    except TelegramErasureError as exc:
        blocker = exc.code
    return {"codes": codes, "request": request, "blocker": blocker, "max_attempts": MAX_ATTEMPTS}


# --- Self-service: the person deletes their own Telegram account -----------
# The same intake and processor; identity is the verified Telegram initData of
# the Mini App request (no administrator, no 2FA). Two calls:
#   self_preview(): what will be lost + whether anything blocks it, and a
#                   short-lived confirmation token bound to this account;
#   self_confirm(): the person's explicit confirmation with that token.
# A Telegram Stars subscription that still renews blocks it until the person
# turns renewal off (the Mini App offers that first).
SELF_SCOPE = "telegram_account_content_v1"
SELF_TOKEN_TTL_SECONDS = 600


def _self_token_key(secret):
    if not secret:
        raise TelegramErasureError("erasure_not_configured", 503)
    return hmac.new(str(secret).encode(), b"SYLVEX telegram self erasure v1", hashlib.sha256).digest()


def self_token(secret, telegram_id, account_id, now):
    exp = int(now) + SELF_TOKEN_TTL_SECONDS
    payload = f"{int(telegram_id)}.{int(account_id)}.{exp}"
    return payload + "." + hmac.new(_self_token_key(secret), payload.encode(), hashlib.sha256).hexdigest()


def check_self_token(secret, token, telegram_id, account_id, now):
    try:
        uid, acc, exp, sig = str(token or "").split(".")
        payload = f"{int(uid)}.{int(acc)}.{int(exp)}"
    except ValueError:
        raise TelegramErasureError("confirmation_invalid", 400) from None
    good = hmac.new(_self_token_key(secret), payload.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(good, sig) or int(uid) != int(telegram_id) or int(acc) != int(account_id):
        raise TelegramErasureError("confirmation_invalid", 400)
    if int(exp) < int(now):
        raise TelegramErasureError("confirmation_expired", 400)


def self_preview(cur, telegram_id, *, secret, now):
    """What the person loses, what blocks it, and the confirmation token."""
    telegram_id = _telegram_id(telegram_id)
    cur.execute("SELECT balance FROM users WHERE telegram_id=%s", (telegram_id,))
    row = cur.fetchone()
    balance = int(row[0] or 0) if row else 0
    try:
        account_id, _ = check_scope(cur, telegram_id)
    except TelegramErasureError as exc:
        if exc.code != "stars_renewal_active":
            return {"ok": False, "error": exc.code, "status": exc.status, "balance": balance}
        return {"ok": True, "blocker": "stars_renewal_active", "balance": balance}
    return {"ok": True, "blocker": None, "balance": balance,
            "confirm_token": self_token(secret, telegram_id, account_id, now),
            "expires_in": SELF_TOKEN_TTL_SECONDS}


def self_confirm(cur, telegram_id, *, token, scope, secret, now, accept):
    """Accept the person's own, explicitly confirmed request (B09 intake)."""
    if scope != SELF_SCOPE:
        raise TelegramErasureError("erasure_scope_confirmation_required", 409)
    telegram_id = _telegram_id(telegram_id)
    cur.execute("SELECT pg_advisory_xact_lock(%s, hashtext(%s))", (LOCK_NAMESPACE, str(telegram_id)))
    account_id, telegram_id = check_scope(cur, telegram_id)  # again: renewal or a team role may have changed
    check_self_token(secret, token, telegram_id, account_id, now)
    result = accept(cur, account_id, ecosystem="telegram")
    return {"ok": True, "accepted": True, "request_id": result["request_id"], "state": result["state"]}
