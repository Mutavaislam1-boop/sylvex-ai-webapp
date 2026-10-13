"""Canonical user identity for every admin API response.

Business tables are keyed on users.telegram_id, which for a website-only
account is a hidden storage key (>= STORAGE_ID_FLOOR), not a Telegram id.
Admin responses must never present that key as a user's identity. This
module maps storage keys to the canonical identity block:

    {"sylvex_user_id": "110626130001", "telegram_id": 7000000001 | None,
     "email": ..., "username": ..., "display_name": ..., "status": "active",
     "account_origin": "website" | "telegram" | None,
     "linked": {"telegram": bool, "email": bool, "google": bool, "apple": bool},
     "created_at": ..., "technical": {...}  # owner only}

and resolves any admin-supplied identifier (SYLVEX ID, Telegram ID, email,
username, display name, payment/customer id) back to a storage key.
Read-only: nothing here creates or changes an account.
"""
from __future__ import annotations

import re
from datetime import datetime

from services.account_identity import STORAGE_ID_FLOOR, is_storage_id, real_telegram_id

# Exact-match payment references (each column is a primary key or unique,
# so every lookup is an index hit). Missing tables are skipped.
PAYMENT_REFERENCE_COLUMNS = (
    ("purchases", "charge_id"),
    ("shop_orders", "order_id"),
    ("shop_orders", "charge_id"),
    ("payment_inbox", "charge_id"),
    ("paypal_orders", "paypal_order_id"),
    ("paypal_orders", "paypal_capture_id"),
    ("paypal_subscriptions", "paypal_subscription_id"),
    ("stripe_customers", "customer_id"),
    ("stripe_subscriptions", "subscription_id"),
)
_ALIAS_HOPS = 3
_ID_LIKE = re.compile(r"^[A-Za-z0-9_:.\-]{6,200}$")


def _iso(value):
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value) or None


def _existing_tables(cur, names):
    found = set()
    for name in names:
        cur.execute("SELECT to_regclass(%s)", (name,))
        if cur.fetchone()[0] is not None:
            found.add(name)
    return found


def identities_for_keys(cur, keys, *, technical=False):
    """{storage_key: identity} for each users.telegram_id-style key given.
    One query for the core fields plus one each for OAuth and aliases."""
    keys = list(dict.fromkeys(int(k) for k in keys if k))
    if not keys:
        return {}
    tables = _existing_tables(cur, ("sylvex_accounts", "account_emails", "account_oauth", "user_profiles"))
    has_accounts = "sylvex_accounts" in tables
    account_cols = ("a.account_id, a.origin, a.merged_telegram_id, a.merged_at, a.storage_telegram_id, "
                    "a.created_at AS account_created_at" if has_accounts else
                    "NULL AS account_id, NULL AS origin, NULL AS merged_telegram_id, NULL AS merged_at, "
                    "NULL AS storage_telegram_id, NULL AS account_created_at")
    joins = ["LEFT JOIN users u ON u.telegram_id = k.key"]
    if has_accounts:
        joins.append("LEFT JOIN sylvex_accounts a ON a.active_telegram_id = k.key")
    name_col = "u.first_name"
    if "user_profiles" in tables:
        joins.append("LEFT JOIN user_profiles p ON p.telegram_id = k.key")
        name_col = "COALESCE(p.display_name, u.first_name)"
    email_col = "NULL::text"
    if has_accounts and "account_emails" in tables:
        joins.append("LEFT JOIN account_emails e ON e.account_id = a.account_id")
        email_col = "e.email"
    cur.execute(
        f"""
        SELECT k.key, {account_cols}, u.telegram_id IS NOT NULL AS user_exists, u.username,
               {name_col} AS display_name, u.created_at AS user_created_at, {email_col} AS email
        FROM unnest(%s::bigint[]) AS k(key)
        {' '.join(joins)}
        """,
        (keys,),
    )
    rows = cur.fetchall()
    account_ids = [int(r[1]) for r in rows if r[1] is not None]
    providers = {}
    if account_ids and "account_oauth" in tables:
        cur.execute("SELECT account_id, provider FROM account_oauth WHERE account_id = ANY(%s::bigint[])", (account_ids,))
        for account_id, provider in cur.fetchall():
            providers.setdefault(int(account_id), set()).add(str(provider))
    aliases = {}
    if technical and account_ids:
        cur.execute(
            "SELECT merged_into_account_id, account_id FROM sylvex_accounts "
            "WHERE merged_into_account_id = ANY(%s::bigint[]) ORDER BY account_id",
            (account_ids,),
        )
        for target, alias in cur.fetchall():
            aliases.setdefault(int(target), []).append(str(alias))

    result = {}
    for (key, account_id, origin, merged_tg, merged_at, storage_tg, account_created,
         user_exists, username, display_name, user_created, email) in rows:
        key = int(key)
        account_id = int(account_id) if account_id is not None else None
        account_providers = providers.get(account_id, set())
        tg = real_telegram_id(key)
        identity = {
            "sylvex_user_id": str(account_id) if account_id is not None else None,
            "telegram_id": tg,
            "email": email or None,
            "username": (username or None) if username not in ("none",) else None,
            "display_name": display_name or None,
            "status": "active",
            "account_origin": origin,
            "linked": {
                "telegram": tg is not None,
                "email": bool(email),
                "google": "google" in account_providers,
                "apple": "apple" in account_providers,
            },
            "created_at": _iso(account_created) or _iso(user_created),
        }
        if technical:
            storage_key = int(storage_tg) if storage_tg is not None else (key if is_storage_id(key) else None)
            identity["technical"] = {
                "internal_storage_id": storage_key,
                "storage_key": key,
                "merged_telegram_id": int(merged_tg) if merged_tg is not None else None,
                "merged_at": _iso(merged_at),
                "alias_sylvex_user_ids": aliases.get(account_id, []),
                "users_row_exists": bool(user_exists),
                "orphan_storage_row": is_storage_id(key) and account_id is None,
            }
        result[key] = identity
    return result


def is_ghost_key(identity):
    """A storage-range users row that no account points at: left behind by
    a merge (its data already moved to the Telegram side). Not a person."""
    return identity.get("sylvex_user_id") is None and identity.get("telegram_id") is None


def _follow_account(cur, account_id):
    """Storage key of an account, following retired aliases to the account
    they merged into. None if the account does not exist."""
    current = int(account_id)
    for _ in range(_ALIAS_HOPS):
        cur.execute(
            "SELECT active_telegram_id, merged_into_account_id FROM sylvex_accounts WHERE account_id = %s",
            (current,),
        )
        row = cur.fetchone()
        if not row:
            return None
        if row[0] is not None:
            return int(row[0])
        if row[1] is None:
            return None
        current = int(row[1])
    return None


def _as_int(value):
    try:
        text = str(value).strip()
    except Exception:
        return None
    if not text.isdigit():
        return None
    number = int(text)
    return number if number > 0 else None


def resolve_target(cur, *, sylvex_user_id=None, user_id=None):
    """Storage key for an admin action's target, or None.

    `sylvex_user_id` is matched only as a SYLVEX ID (aliases followed).
    Legacy `user_id` keeps its old meaning first - a users.telegram_id - and
    only falls back to a SYLVEX ID when no such users row exists, so old
    callers (Support Bot, /addbalance) never change target."""
    if sylvex_user_id not in (None, ""):
        account_id = _as_int(sylvex_user_id)
        if account_id is None or not _existing_tables(cur, ("sylvex_accounts",)):
            return None
        return _follow_account(cur, account_id)
    number = _as_int(user_id)
    if number is None:
        return None
    cur.execute("SELECT 1 FROM users WHERE telegram_id = %s", (number,))
    if cur.fetchone():
        return number
    if _existing_tables(cur, ("sylvex_accounts",)):
        return _follow_account(cur, number)
    return None


def search_keys(cur, query, *, limit=30, technical=False):
    """Storage keys of the people matching `query`, best matches first, one
    per person. Ghost storage rows never match; a storage key matches only
    for technical (owner) callers."""
    query = str(query or "").strip()[:200]
    limit = max(1, min(int(limit or 30), 100))
    tables = _existing_tables(cur, ("sylvex_accounts", "account_emails", "account_oauth", "user_profiles")
                              + tuple({t for t, _ in PAYMENT_REFERENCE_COLUMNS}))
    has_accounts = "sylvex_accounts" in tables
    ordered = []

    def add(values):
        for value in values:
            if value is not None and int(value) not in ordered:
                ordered.append(int(value))

    name_col = "COALESCE(p.display_name, u.first_name, '')" if "user_profiles" in tables else "COALESCE(u.first_name, '')"
    profile_join = "LEFT JOIN user_profiles p ON p.telegram_id = u.telegram_id" if "user_profiles" in tables else ""
    not_ghost = (
        f"(u.telegram_id < {STORAGE_ID_FLOOR} OR EXISTS (SELECT 1 FROM sylvex_accounts a "
        "WHERE a.active_telegram_id = u.telegram_id))"
    ) if has_accounts else f"u.telegram_id < {STORAGE_ID_FLOOR}"

    if not query:
        cur.execute(
            f"SELECT u.telegram_id FROM users u WHERE {not_ghost} "
            "ORDER BY NULLIF(u.created_at,'')::timestamp DESC NULLS LAST LIMIT %s",
            (limit,),
        )
        return [int(r[0]) for r in cur.fetchall()]

    number = _as_int(query)
    if number is not None:
        if has_accounts:
            add([_follow_account(cur, number)])
        if number < STORAGE_ID_FLOOR or technical:
            cur.execute("SELECT telegram_id FROM users WHERE telegram_id = %s", (number,))
            add(r[0] for r in cur.fetchall())
        if has_accounts:
            cur.execute(
                "SELECT active_telegram_id FROM sylvex_accounts WHERE active_telegram_id IS NOT NULL "
                "AND account_id::text LIKE %s ORDER BY account_id LIMIT %s",
                (f"{query}%", limit),
            )
            add(r[0] for r in cur.fetchall())
        cur.execute(
            f"SELECT u.telegram_id FROM users u WHERE u.telegram_id < {STORAGE_ID_FLOOR} "
            "AND u.telegram_id::text LIKE %s ORDER BY u.telegram_id LIMIT %s",
            (f"{query}%", limit),
        )
        add(r[0] for r in cur.fetchall())

    if has_accounts and "@" in query and "account_emails" in tables:
        cur.execute(
            "SELECT a.active_telegram_id FROM account_emails e JOIN sylvex_accounts a ON a.account_id = e.account_id "
            "WHERE a.active_telegram_id IS NOT NULL AND lower(e.email) LIKE lower(%s) ORDER BY e.email LIMIT %s",
            (f"%{query}%", limit),
        )
        add(r[0] for r in cur.fetchall())
        if "account_oauth" in tables:
            cur.execute(
                "SELECT a.active_telegram_id FROM account_oauth o JOIN sylvex_accounts a ON a.account_id = o.account_id "
                "WHERE a.active_telegram_id IS NOT NULL AND lower(o.email) = lower(%s) LIMIT %s",
                (query, limit),
            )
            add(r[0] for r in cur.fetchall())

    if _ID_LIKE.match(query):
        for table, column in PAYMENT_REFERENCE_COLUMNS:
            if table in tables:
                cur.execute(f"SELECT telegram_id FROM {table} WHERE {column} = %s LIMIT 5", (query,))
                add(r[0] for r in cur.fetchall())

    if number is None:
        pattern = f"%{query.lstrip('@')}%"
        cur.execute(
            f"SELECT u.telegram_id FROM users u {profile_join} WHERE {not_ghost} "
            f"AND (COALESCE(u.username,'') ILIKE %s OR {name_col} ILIKE %s) "
            "ORDER BY NULLIF(u.created_at,'')::timestamp DESC NULLS LAST LIMIT %s",
            (pattern, pattern, limit),
        )
        add(r[0] for r in cur.fetchall())

    if not technical:
        # A payment row can still point at a merged-away storage key.
        identities = identities_for_keys(cur, ordered, technical=False)
        ordered = [k for k in ordered if not is_ghost_key(identities.get(k, {}))]
    return ordered[:limit]


def decorate(cur, rows, *, technical=False, fields=("telegram_id",)):
    """In place, for each dict row: the canonical identity of each named
    key field is attached (`identity`, or `<prefix>_identity` for fields
    like actor_id/target_id), `sylvex_user_id` is added, and the raw key in
    that field is replaced by the real Telegram id (None for a storage
    key) - so no response ever carries a storage key outside `technical`."""
    keys = [row.get(field) for row in rows for field in fields]
    identities = identities_for_keys(cur, [k for k in keys if k], technical=technical)
    for row in rows:
        for field in fields:
            key = row.get(field)
            identity = identities.get(int(key)) if key else None
            name = "identity" if field == "telegram_id" else f"{field[:-3] if field.endswith('_id') else field}_identity"
            row[name] = identity
            if field == "telegram_id":
                row["sylvex_user_id"] = identity["sylvex_user_id"] if identity else None
            row[field] = real_telegram_id(key)
    return rows
