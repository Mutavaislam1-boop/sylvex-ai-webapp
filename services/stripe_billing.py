"""Stripe Checkout for SYLVEX Website purchases.

Website-only: inside Telegram (the Mini App and the bot) digital goods must be
sold for Telegram Stars, so the checkout route refuses Telegram requests.

Everything Stripe sells comes from services/shop_catalog.py, the same
server-authoritative catalog the Mini App uses, and every purchase is a
services/shop_orders.py order. Grants reuse the existing tables (users.balance,
purchases, subscriptions) through shop_orders.finalize_order(); recurring
renewals use grant_renewal() below with the same idempotency rule: one
purchases row per Stripe charge id (payment intent or invoice id).

Products and prices are created or reused by sync_catalog(): plan and pack
products have deterministic Stripe product ids (sylvex_plan_pro,
sylvex_pack_1000, ...) and every price carries a lookup key
(sylvex_plan_pro_month, sylvex_pack_1000, ...), so re-running it never
creates duplicates. A price whose amount or interval no longer matches is
replaced by a new price that takes over the lookup key; the old price stays
active for the subscriptions already on it. Nothing is ever deleted or
archived.

This module never logs or returns the secret key.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import time

import requests

from services import shop_catalog, shop_orders

API_BASE = "https://api.stripe.com/v1"
# Pinned so API responses keep the shape this module reads. Webhook payloads
# use the endpoint's own API version, so event parsing accepts both the
# older and the 2025+ ("basil") object shapes.
API_VERSION = "2024-06-20"
PROVIDER = shop_catalog.PROVIDER_STRIPE
SIGNATURE_TOLERANCE_SECONDS = 300
# Stripe charges a renewal at (or shortly after) the end of a period and
# retries failed charges for some days. Access runs this long past the paid
# period end so a renewal that settles a little late never lapses the plan.
RENEWAL_GRACE_DAYS = 2
# Stripe's minimum Checkout Session lifetime.
CHECKOUT_TTL_SECONDS = 1800
# A user with a Stripe subscription in one of these states must manage it
# (Customer Portal) instead of starting a second, separately billed one.
LIVE_SUBSCRIPTION_STATUSES = ("active", "trialing", "past_due", "unpaid")

CUSTOM_STRIPE_PRODUCT = {
    "id": "sylvex_credits_custom",
    "name": "SYLVEX ⚡ credits",
    "description": "SYLVEX credits for a custom amount. $1 = 100 ⚡.",
    "metadata": {"sylvex_kind": "credits_custom"},
}


class StripeError(RuntimeError):
    def __init__(self, message: str, status: int | None = None, code: str | None = None):
        super().__init__(message)
        self.status = status
        self.code = code


class SignatureError(ValueError):
    pass


# ---------------------------------------------------------------------------
# REST client
# ---------------------------------------------------------------------------

def _flatten(params, prefix=""):
    """Stripe form encoding: a[b]=1, a[c][0][d]=2. None values are omitted."""
    pairs = []
    if isinstance(params, dict):
        items = params.items()
    elif isinstance(params, (list, tuple)):
        items = ((str(i), v) for i, v in enumerate(params))
    else:
        return [(prefix, params)]
    for key, value in items:
        name = f"{prefix}[{key}]" if prefix else str(key)
        if value is None:
            continue
        if isinstance(value, bool):
            pairs.append((name, "true" if value else "false"))
        elif isinstance(value, (dict, list, tuple)):
            pairs.extend(_flatten(value, name))
        else:
            pairs.append((name, str(value)))
    return pairs


def key_livemode(secret_key: str) -> bool:
    return str(secret_key or "").startswith(("sk_live_", "rk_live_"))


class StripeClient:
    def __init__(self, secret_key: str, session=None, api_base: str = API_BASE, timeout: int = 30):
        if not secret_key:
            raise StripeError("stripe_not_configured")
        self._key = secret_key
        self._session = session or requests.Session()
        self._base = api_base.rstrip("/")
        self._timeout = timeout
        self.livemode = key_livemode(secret_key)

    def request(self, method: str, path: str, params=None, idempotency_key: str | None = None) -> dict:
        headers = {"Authorization": f"Bearer {self._key}", "Stripe-Version": API_VERSION}
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key
        data = _flatten(params or {})
        url = self._base + path
        if method == "GET":
            response = self._session.request("GET", url, params=data, headers=headers, timeout=self._timeout)
        else:
            response = self._session.request(method, url, data=data, headers=headers, timeout=self._timeout)
        try:
            body = response.json() if response.content else {}
        except ValueError:
            body = {}
        if response.status_code >= 400:
            error = body.get("error") or {}
            raise StripeError(error.get("message") or f"stripe_http_{response.status_code}",
                              status=response.status_code, code=error.get("code"))
        return body


# ---------------------------------------------------------------------------
# Webhook signatures
# ---------------------------------------------------------------------------

def verify_webhook(payload: bytes, signature_header: str, secret: str, now: float | None = None,
                   tolerance: int = SIGNATURE_TOLERANCE_SECONDS) -> dict:
    """The parsed event, only if Stripe-Signature matches the endpoint secret."""
    if not secret:
        raise SignatureError("webhook_secret_not_configured")
    timestamp, signatures = None, []
    for part in str(signature_header or "").split(","):
        key, _, value = part.strip().partition("=")
        if key == "t":
            timestamp = value
        elif key == "v1" and value:
            signatures.append(value)
    if not timestamp or not timestamp.isdigit() or not signatures:
        raise SignatureError("signature_header_invalid")
    expected = hmac.new(secret.encode(), timestamp.encode() + b"." + payload, hashlib.sha256).hexdigest()
    if not any(hmac.compare_digest(expected, sig) for sig in signatures):
        raise SignatureError("signature_mismatch")
    if abs((now if now is not None else time.time()) - int(timestamp)) > tolerance:
        raise SignatureError("timestamp_outside_tolerance")
    try:
        event = json.loads(payload)
    except ValueError:
        raise SignatureError("payload_not_json")
    if not isinstance(event, dict) or not event.get("id") or not event.get("type"):
        raise SignatureError("payload_not_an_event")
    return event


# ---------------------------------------------------------------------------
# Catalog: Stripe products and prices for every SYLVEX product
# ---------------------------------------------------------------------------

def lookup_key(product_id: str) -> str:
    return "sylvex_" + product_id


def catalog_items() -> list:
    """One entry per fixed SYLVEX product, with the Stripe product it belongs to."""
    items = []
    for plan_id, name, _monthly, _annual, _credits in shop_catalog.PLANS:
        stripe_product = {
            "id": f"sylvex_plan_{plan_id}",
            "name": f"SYLVEX {name}",
            "description": f"SYLVEX {name} subscription with monthly or annual ⚡ credits.",
            "metadata": {"sylvex_kind": "plan", "sylvex_plan": plan_id},
        }
        for period in ("month", "year"):
            product = shop_catalog.FIXED_PRODUCTS[f"plan_{plan_id}_{period}"]
            items.append({
                "lookup_key": lookup_key(product["product_id"]),
                "product_id": product["product_id"],
                "stripe_product": stripe_product,
                "unit_amount": product["usd_cents"],
                "interval": period,
                "nickname": f"SYLVEX {name} · {'Monthly' if period == 'month' else 'Annual'}",
                "metadata": {"sylvex_product_id": product["product_id"], "credits": str(product["credits"])},
            })
    for usd in shop_catalog.CREDIT_PACK_USD:
        product = shop_catalog.FIXED_PRODUCTS[shop_catalog.pack_id_for_usd(usd)]
        credits = product["credits"]
        items.append({
            "lookup_key": lookup_key(product["product_id"]),
            "product_id": product["product_id"],
            "stripe_product": {
                "id": f"sylvex_{product['product_id']}",
                "name": f"SYLVEX {credits:,} ⚡ credits",
                "description": f"{credits:,} SYLVEX credits (⚡), added to your balance once.",
                "metadata": {"sylvex_kind": "credits", "sylvex_product_id": product["product_id"]},
            },
            "unit_amount": product["usd_cents"],
            "interval": None,
            "nickname": f"SYLVEX {credits:,} ⚡",
            "metadata": {"sylvex_product_id": product["product_id"], "credits": str(credits)},
        })
    return items


def _ensure_product(client: StripeClient, spec: dict):
    try:
        return client.request("GET", f"/products/{spec['id']}"), "reused"
    except StripeError as exc:
        if exc.status != 404:
            raise
    params = {key: spec[key] for key in ("id", "name", "description", "metadata")}
    try:
        return client.request("POST", "/products", params), "created"
    except StripeError as exc:
        if exc.code != "resource_already_exists":
            raise
        return client.request("GET", f"/products/{spec['id']}"), "reused"


def _price_product_id(price: dict) -> str:
    product = price.get("product")
    return product.get("id") if isinstance(product, dict) else str(product or "")


def _price_matches(price: dict, item: dict) -> bool:
    recurring = price.get("recurring") or None
    interval = recurring.get("interval") if recurring else None
    return (bool(price.get("active"))
            and str(price.get("currency") or "").lower() == "usd"
            and int(price.get("unit_amount") or -1) == item["unit_amount"]
            and _price_product_id(price) == item["stripe_product"]["id"]
            and interval == item["interval"]
            and (not recurring or int(recurring.get("interval_count") or 1) == 1))


def _prices_by_lookup_key(client: StripeClient, keys: list) -> dict:
    found = {}
    for start in range(0, len(keys), 10):
        # Archived prices keep their lookup key, so list regardless of
        # status: a new price must then take the key over explicitly.
        page = client.request("GET", "/prices", {"lookup_keys": keys[start:start + 10], "limit": 100})
        for price in page.get("data") or []:
            if price.get("lookup_key"):
                found[price["lookup_key"]] = price
    return found


def sync_catalog(client: StripeClient) -> dict:
    """Create or reuse every SYLVEX product and price. Safe to run repeatedly.

    Returns {lookup_key: {product_id, stripe_product_id, stripe_price_id,
    unit_amount, interval, product_status, price_status}}. A product someone
    archived in the Dashboard is left archived and reported with
    stripe_price_id None, so it cannot be sold until it is re-activated.
    """
    items = catalog_items()
    products = {}
    for spec in [item["stripe_product"] for item in items] + [CUSTOM_STRIPE_PRODUCT]:
        if spec["id"] not in products:
            products[spec["id"]] = _ensure_product(client, spec)
    existing = _prices_by_lookup_key(client, [item["lookup_key"] for item in items])
    result = {}
    for item in items:
        product, product_status = products[item["stripe_product"]["id"]]
        entry = {
            "product_id": item["product_id"],
            "stripe_product_id": product.get("id"),
            "stripe_price_id": None,
            "unit_amount": item["unit_amount"],
            "interval": item["interval"],
            "product_status": product_status,
            "price_status": None,
        }
        if product.get("active") is False:
            entry["price_status"] = "product_inactive"
            result[item["lookup_key"]] = entry
            continue
        price = existing.get(item["lookup_key"])
        if price and _price_matches(price, item):
            entry.update(stripe_price_id=price["id"], price_status="reused")
        else:
            params = {
                "product": item["stripe_product"]["id"],
                "currency": "usd",
                "unit_amount": item["unit_amount"],
                "lookup_key": item["lookup_key"],
                "nickname": item["nickname"],
                "metadata": item["metadata"],
                "recurring": {"interval": item["interval"]} if item["interval"] else None,
                # Move the key off an outdated price; that price stays active
                # for the subscriptions already billed on it.
                "transfer_lookup_key": True if price else None,
            }
            try:
                created = client.request("POST", "/prices", params)
            except StripeError:
                # Another process may have created it a moment ago.
                again = _prices_by_lookup_key(client, [item["lookup_key"]]).get(item["lookup_key"])
                if not again or not _price_matches(again, item):
                    raise
                created = again
            entry.update(stripe_price_id=created["id"], price_status="replaced" if price else "created")
        result[item["lookup_key"]] = entry
    custom, custom_status = products[CUSTOM_STRIPE_PRODUCT["id"]]
    result[lookup_key(shop_catalog.CUSTOM_PRODUCT_ID)] = {
        "product_id": shop_catalog.CUSTOM_PRODUCT_ID,
        "stripe_product_id": custom.get("id"),
        "stripe_price_id": None,
        "unit_amount": None,
        "interval": None,
        "product_status": custom_status,
        "price_status": "product_inactive" if custom.get("active") is False else "dynamic",
    }
    return result


# ---------------------------------------------------------------------------
# Database: catalog mapping, customers, subscriptions, processed events
# ---------------------------------------------------------------------------

STRIPE_DDL = (
    """
    CREATE TABLE IF NOT EXISTS stripe_catalog (
        lookup_key TEXT NOT NULL,
        livemode BOOLEAN NOT NULL,
        sylvex_product_id TEXT NOT NULL,
        stripe_product_id TEXT,
        stripe_price_id TEXT,
        unit_amount INTEGER,
        billing_interval TEXT,
        price_status TEXT,
        synced_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (lookup_key, livemode)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS stripe_customers (
        telegram_id BIGINT NOT NULL,
        livemode BOOLEAN NOT NULL,
        customer_id TEXT NOT NULL,
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (telegram_id, livemode)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS stripe_subscriptions (
        subscription_id TEXT PRIMARY KEY,
        telegram_id BIGINT NOT NULL,
        plan_key TEXT NOT NULL,
        order_id TEXT,
        customer_id TEXT,
        status TEXT NOT NULL,
        cancel_at_period_end BOOLEAN NOT NULL DEFAULT FALSE,
        current_period_end TIMESTAMP,
        livemode BOOLEAN,
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_stripe_subscriptions_user ON stripe_subscriptions (telegram_id)",
    """
    CREATE TABLE IF NOT EXISTS stripe_events (
        event_id TEXT PRIMARY KEY,
        event_type TEXT NOT NULL,
        outcome TEXT,
        processed_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
    """,
)


def ensure_tables(connect):
    conn = connect()
    try:
        with conn.cursor() as cur:
            for ddl in STRIPE_DDL:
                cur.execute(ddl)
        conn.commit()
    finally:
        conn.close()


def _run(connect, sql, params=(), fetch=None):
    conn = connect()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            rows = cur.fetchall() if fetch == "all" else (cur.fetchone() if fetch == "one" else None)
        conn.commit()
        return rows
    finally:
        conn.close()


def save_catalog(connect, mapping: dict, livemode: bool):
    for key, entry in mapping.items():
        _run(connect, """
            INSERT INTO stripe_catalog (lookup_key, livemode, sylvex_product_id, stripe_product_id, stripe_price_id,
                                        unit_amount, billing_interval, price_status, synced_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
            ON CONFLICT (lookup_key, livemode) DO UPDATE SET
                sylvex_product_id = EXCLUDED.sylvex_product_id, stripe_product_id = EXCLUDED.stripe_product_id,
                stripe_price_id = EXCLUDED.stripe_price_id, unit_amount = EXCLUDED.unit_amount,
                billing_interval = EXCLUDED.billing_interval, price_status = EXCLUDED.price_status,
                synced_at = CURRENT_TIMESTAMP
        """, (key, bool(livemode), entry["product_id"], entry["stripe_product_id"], entry["stripe_price_id"],
              entry["unit_amount"], entry["interval"], entry["price_status"]))


def load_catalog(connect, livemode: bool) -> dict:
    rows = _run(connect, """
        SELECT lookup_key, sylvex_product_id, stripe_product_id, stripe_price_id, unit_amount, billing_interval, price_status
          FROM stripe_catalog WHERE livemode = %s
    """, (bool(livemode),), fetch="all") or []
    return {row[0]: {"product_id": row[1], "stripe_product_id": row[2], "stripe_price_id": row[3],
                     "unit_amount": row[4], "interval": row[5], "price_status": row[6]} for row in rows}


def catalog_complete(mapping: dict) -> bool:
    """Every fixed product has a usable price and the custom product exists."""
    for item in catalog_items():
        entry = mapping.get(item["lookup_key"]) or {}
        if not entry.get("stripe_price_id") or entry.get("unit_amount") != item["unit_amount"]:
            return False
    custom = mapping.get(lookup_key(shop_catalog.CUSTOM_PRODUCT_ID)) or {}
    return bool(custom.get("stripe_product_id")) and custom.get("price_status") != "product_inactive"


def get_customer(connect, telegram_id: int, livemode: bool):
    row = _run(connect, "SELECT customer_id FROM stripe_customers WHERE telegram_id = %s AND livemode = %s",
               (int(telegram_id), bool(livemode)), fetch="one")
    return row[0] if row else None


def save_customer(connect, telegram_id: int, customer_id: str, livemode: bool):
    if not customer_id:
        return
    _run(connect, """
        INSERT INTO stripe_customers (telegram_id, livemode, customer_id) VALUES (%s, %s, %s)
        ON CONFLICT (telegram_id, livemode) DO NOTHING
    """, (int(telegram_id), bool(livemode), str(customer_id)))


_SUB_COLUMNS = ("subscription_id", "telegram_id", "plan_key", "order_id", "customer_id", "status",
                "cancel_at_period_end", "current_period_end", "livemode")


def get_subscription(connect, subscription_id: str):
    row = _run(connect, "SELECT " + ", ".join(_SUB_COLUMNS) + " FROM stripe_subscriptions WHERE subscription_id = %s",
               (str(subscription_id),), fetch="one")
    return dict(zip(_SUB_COLUMNS, row)) if row else None


def upsert_subscription(connect, subscription_id, telegram_id, plan_key, order_id, customer_id, status,
                        cancel_at_period_end=None, current_period_end=None, livemode=None):
    """Record or update the Stripe subscription -> SYLVEX user link.

    The user, plan and order are fixed by the first write (from our own
    order); later writes only update billing state.
    """
    _run(connect, """
        INSERT INTO stripe_subscriptions (subscription_id, telegram_id, plan_key, order_id, customer_id, status,
                                          cancel_at_period_end, current_period_end, livemode)
        VALUES (%s, %s, %s, %s, %s, %s, COALESCE(%s, FALSE), to_timestamp(%s)::timestamp, %s)
        ON CONFLICT (subscription_id) DO UPDATE SET
            customer_id = COALESCE(EXCLUDED.customer_id, stripe_subscriptions.customer_id),
            status = EXCLUDED.status,
            cancel_at_period_end = COALESCE(%s, stripe_subscriptions.cancel_at_period_end),
            current_period_end = COALESCE(EXCLUDED.current_period_end, stripe_subscriptions.current_period_end),
            livemode = COALESCE(EXCLUDED.livemode, stripe_subscriptions.livemode),
            updated_at = CURRENT_TIMESTAMP
    """, (str(subscription_id), int(telegram_id), plan_key, order_id, customer_id, status, cancel_at_period_end,
          current_period_end, livemode, cancel_at_period_end))
    return get_subscription(connect, subscription_id)


def has_live_subscription(connect, telegram_id: int) -> bool:
    """A Stripe plan that will bill again. One already set to cancel at the
    period end does not count, so a user can switch plans after cancelling."""
    row = _run(connect, """
        SELECT 1 FROM stripe_subscriptions
         WHERE telegram_id = %s AND status = ANY(%s) AND NOT cancel_at_period_end LIMIT 1
    """, (int(telegram_id), list(LIVE_SUBSCRIPTION_STATUSES)), fetch="one")
    return bool(row)


def renews_automatically_sql(alias: str = "s") -> str:
    """SQL condition: this subscriptions row is kept alive by a Stripe
    subscription that will renew (used to skip "renew manually" reminders)."""
    return (f"EXISTS (SELECT 1 FROM stripe_subscriptions ss WHERE ss.telegram_id = {alias}.telegram_id "
            f"AND ss.status IN ('active', 'trialing') AND NOT ss.cancel_at_period_end)")


def event_processed(connect, event_id: str) -> bool:
    return bool(_run(connect, "SELECT 1 FROM stripe_events WHERE event_id = %s", (str(event_id),), fetch="one"))


def record_event(connect, event: dict, outcome: str):
    _run(connect, """
        INSERT INTO stripe_events (event_id, event_type, outcome) VALUES (%s, %s, %s)
        ON CONFLICT (event_id) DO NOTHING
    """, (str(event["id"]), str(event["type"]), outcome))


# ---------------------------------------------------------------------------
# Checkout
# ---------------------------------------------------------------------------

def checkout_session_params(order: dict, price_id: str | None, custom_product_id: str | None,
                            success_url: str, cancel_url: str, customer_id: str | None = None,
                            now: float | None = None) -> dict:
    """Checkout Session parameters for an order. Amounts come from the order."""
    is_subscription = order["kind"] == "subscription"
    metadata = {
        "sylvex_order_id": order["order_id"],
        "sylvex_uid": str(order["telegram_id"]),
        "sylvex_product_id": order["product_id"],
    }
    if price_id:
        line_item = {"price": price_id, "quantity": 1}
    else:
        if not custom_product_id:
            raise StripeError("stripe_custom_product_missing")
        line_item = {"price_data": {"currency": "usd", "unit_amount": int(order["usd_cents"]),
                                    "product": custom_product_id}, "quantity": 1}
    credits = f"{int(order['credits']):,}"
    if is_subscription:
        period = "month" if str(order["plan_key"]).endswith("_month") else "year"
        message = (f"{credits} ⚡ are added to your SYLVEX balance after each {period}ly payment. "
                   "The plan renews automatically until you cancel.")
    else:
        message = f"{credits} ⚡ are added to your SYLVEX balance once the payment is confirmed."
    params = {
        "mode": "subscription" if is_subscription else "payment",
        "client_reference_id": order["order_id"],
        "metadata": metadata,
        "line_items": [line_item],
        "success_url": success_url,
        "cancel_url": cancel_url,
        "expires_at": int((now if now is not None else time.time()) + CHECKOUT_TTL_SECONDS),
        "custom_text": {"submit": {"message": message}},
        "customer": customer_id or None,
    }
    if is_subscription:
        params["subscription_data"] = {"metadata": dict(metadata, sylvex_plan_key=order["plan_key"])}
    else:
        params["payment_intent_data"] = {"metadata": metadata}
        if not customer_id:
            params["customer_creation"] = "always"
    return params


# ---------------------------------------------------------------------------
# Webhook processing
# ---------------------------------------------------------------------------

def _id(value):
    return value.get("id") if isinstance(value, dict) else value


def _invoice_subscription_id(invoice: dict):
    sub = invoice.get("subscription")
    if not sub:
        details = ((invoice.get("parent") or {}).get("subscription_details") or {})
        sub = details.get("subscription")
    return _id(sub)


def _invoice_period(invoice: dict):
    """(start, end) of the subscription period this invoice pays for."""
    starts, ends = [], []
    for line in ((invoice.get("lines") or {}).get("data") or []):
        period = line.get("period") or {}
        if period.get("start") and period.get("end"):
            starts.append(int(period["start"]))
            ends.append(int(period["end"]))
    if ends:
        return min(starts), max(ends)
    return invoice.get("period_start"), invoice.get("period_end")


def _subscription_period_end(subscription: dict):
    end = subscription.get("current_period_end")
    if not end:
        items = ((subscription.get("items") or {}).get("data") or [])
        ends = [int(item["current_period_end"]) for item in items if item.get("current_period_end")]
        end = max(ends) if ends else None
    return end


def _amount_before_tax(total, tax):
    return int(total or 0) - int(tax or 0)


def extend_to_period_end(connect, charge_id: str, period_end: int):
    """Stripe-billed rows stay active until the paid period end plus grace."""
    if not period_end:
        return
    _run(connect, """
        UPDATE subscriptions
           SET expires_at = GREATEST(expires_at::timestamp,
                                     to_timestamp(%s)::timestamp + (%s || ' days')::interval)
         WHERE charge_id = %s AND status = 'active'
    """, (int(period_end), RENEWAL_GRACE_DAYS, str(charge_id)))


def grant_renewal(connect, link: dict, invoice_id: str, amount_cents: int, currency: str,
                  period_start: int, period_end: int) -> dict:
    """One renewal payment: credits plus the next period, exactly once.

    Mirrors shop_orders.finalize_order: the purchases row keyed by the
    invoice id makes repeated deliveries harmless, and the new period stacks
    after the current expiry (never earlier than the Stripe period end).
    """
    product = shop_catalog.FIXED_PRODUCTS.get("plan_" + str(link["plan_key"]))
    if not product:
        return {"status": "rejected", "reason": "unknown_plan"}
    if str(currency).upper() != "USD" or int(amount_cents) != int(product["usd_cents"]):
        return {"status": "rejected", "reason": "amount_mismatch"}
    uid = int(link["telegram_id"])
    period_seconds = (int(period_end) - int(period_start)) if period_start and period_end else product["days"] * 86400
    conn = connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO users (telegram_id, first_name, balance, subscription) VALUES (%s, 'Telegram User', 0, 'free') "
                "ON CONFLICT (telegram_id) DO NOTHING", (uid,))
            cur.execute("SELECT telegram_id FROM users WHERE telegram_id = %s FOR UPDATE", (uid,))
            cur.execute("""
                INSERT INTO purchases (telegram_id, provider, credits, amount, currency, payload, charge_id, status)
                VALUES (%s, %s, %s, %s, 'USD', %s, %s, 'completed')
                ON CONFLICT (charge_id) DO NOTHING
                RETURNING id
            """, (uid, PROVIDER, int(product["credits"]), int(amount_cents), f"stripe_invoice:{invoice_id}", str(invoice_id)))
            if cur.fetchone() is None:
                conn.rollback()
                return {"status": "duplicate", "reason": "charge_already_recorded"}
            cur.execute("""
                INSERT INTO subscriptions (telegram_id, subscription_type, payment_method, amount, currency, expires_at, status, charge_id)
                VALUES (%s, %s, %s, %s, 'USD',
                        GREATEST(
                            (SELECT GREATEST(CURRENT_TIMESTAMP, COALESCE(MAX(expires_at::timestamp), CURRENT_TIMESTAMP))
                               FROM subscriptions
                              WHERE telegram_id = %s AND status = 'active' AND expires_at::timestamp > CURRENT_TIMESTAMP)
                                + (%s || ' seconds')::interval,
                            to_timestamp(%s)::timestamp + (%s || ' days')::interval),
                        'active', %s)
                RETURNING id
            """, (uid, link["plan_key"], PROVIDER, int(amount_cents), uid, int(period_seconds), int(period_end),
                  RENEWAL_GRACE_DAYS, str(invoice_id)))
            subscription_row = cur.fetchone()[0]
            cur.execute("UPDATE subscriptions SET status = 'cancelled' WHERE telegram_id = %s AND status = 'active' AND id <> %s",
                        (uid, subscription_row))
            cur.execute("UPDATE users SET subscription = %s, balance = COALESCE(balance, 0) + %s WHERE telegram_id = %s",
                        (link["plan_key"], int(product["credits"]), uid))
        conn.commit()
        return {"status": "granted", "reason": None, "credits": int(product["credits"]), "telegram_id": uid,
                "plan_key": link["plan_key"]}
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _order_for(connect, order_id):
    if not order_id or not shop_orders.parse_order_payload(shop_orders.order_payload(str(order_id))):
        return None
    order = shop_orders.get_order(connect, str(order_id))
    return order if order and order["provider"] == PROVIDER else None


def _link_from_stripe(connect, client: StripeClient, subscription_id: str):
    """The stored subscription link, created from our own order on first sight."""
    link = get_subscription(connect, subscription_id)
    if link:
        return link
    subscription = client.request("GET", f"/subscriptions/{subscription_id}")
    order = _order_for(connect, (subscription.get("metadata") or {}).get("sylvex_order_id"))
    if not order or order["kind"] != "subscription":
        return None
    return upsert_subscription(connect, subscription_id, order["telegram_id"], order["plan_key"], order["order_id"],
                               _id(subscription.get("customer")), subscription.get("status") or "incomplete",
                               bool(subscription.get("cancel_at_period_end")), _subscription_period_end(subscription),
                               subscription.get("livemode"))


def handle_event(connect, client: StripeClient, event: dict, finalize) -> dict:
    """Apply one verified Stripe event. Returns {"outcome": ..., ...}.

    `finalize(order_id, currency, amount_cents, charge_id)` settles an order
    through the app's finalize_store_order (grant + events + notification).
    Raising lets Stripe retry the delivery; every grant is idempotent.
    """
    event_type = event["type"]
    obj = (event.get("data") or {}).get("object") or {}

    if event_type in {"checkout.session.completed", "checkout.session.async_payment_succeeded"}:
        order = _order_for(connect, obj.get("client_reference_id") or (obj.get("metadata") or {}).get("sylvex_order_id"))
        if not order:
            return {"outcome": "ignored", "reason": "unknown_order"}
        customer = _id(obj.get("customer"))
        save_customer(connect, order["telegram_id"], customer, bool(obj.get("livemode")))
        if obj.get("mode") == "subscription":
            if obj.get("subscription"):
                link = get_subscription(connect, _id(obj["subscription"]))
                upsert_subscription(connect, _id(obj["subscription"]), order["telegram_id"], order["plan_key"],
                                    order["order_id"], customer, (link or {}).get("status") or "incomplete",
                                    livemode=bool(obj.get("livemode")))
            # Plans are granted from invoice.paid, which carries the period.
            return {"outcome": "recorded", "order_id": order["order_id"]}
        if obj.get("payment_status") != "paid":
            return {"outcome": "pending", "order_id": order["order_id"]}
        amount = _amount_before_tax(obj.get("amount_total"), (obj.get("total_details") or {}).get("amount_tax"))
        charge_id = _id(obj.get("payment_intent")) or obj.get("id")
        result = finalize(order["order_id"], str(obj.get("currency") or "").upper(), amount, charge_id)
        return {"outcome": result["status"], "reason": result.get("reason"), "order_id": order["order_id"]}

    if event_type == "checkout.session.expired":
        order = _order_for(connect, obj.get("client_reference_id"))
        if order:
            shop_orders.mark_order(connect, order["order_id"], shop_orders.STATUS_EXPIRED, "checkout_expired")
        return {"outcome": "expired" if order else "ignored"}

    if event_type == "checkout.session.async_payment_failed":
        order = _order_for(connect, obj.get("client_reference_id"))
        if order:
            shop_orders.mark_order(connect, order["order_id"], shop_orders.STATUS_FAILED, "payment_failed")
        return {"outcome": "failed" if order else "ignored"}

    if event_type in {"invoice.paid", "invoice.payment_failed"}:
        subscription_id = _invoice_subscription_id(obj)
        if not subscription_id:
            return {"outcome": "ignored", "reason": "not_a_subscription_invoice"}
        link = _link_from_stripe(connect, client, subscription_id)
        if not link:
            return {"outcome": "ignored", "reason": "unknown_subscription"}
        reason = obj.get("billing_reason")
        if event_type == "invoice.payment_failed":
            upsert_subscription(connect, subscription_id, link["telegram_id"], link["plan_key"], link["order_id"],
                                _id(obj.get("customer")), "past_due" if reason == "subscription_cycle" else link["status"])
            return {"outcome": "payment_failed", "telegram_id": link["telegram_id"], "billing_reason": reason,
                    "plan_key": link["plan_key"]}
        # The plan price itself: after discounts, before any Stripe Tax.
        amount = (int(obj["total_excluding_tax"]) if obj.get("total_excluding_tax") is not None
                  else int(obj.get("total") or 0))
        currency = str(obj.get("currency") or "").upper()
        period_start, period_end = _invoice_period(obj)
        if reason == "subscription_create":
            result = finalize(link["order_id"], currency, amount, obj["id"])
            if result["status"] in {"granted", "duplicate"}:
                extend_to_period_end(connect, obj["id"], period_end)
            outcome = {"outcome": result["status"], "reason": result.get("reason"), "order_id": link["order_id"]}
        elif reason == "subscription_cycle":
            result = grant_renewal(connect, link, obj["id"], amount, currency, period_start, period_end)
            outcome = {"outcome": result["status"], "reason": result.get("reason"), "renewal": True,
                       "telegram_id": link["telegram_id"], "plan_key": link["plan_key"],
                       "credits": result.get("credits")}
        else:
            # Proration or manual invoices: no plan change is sold this way.
            return {"outcome": "ignored", "reason": f"billing_reason_{reason}"}
        if outcome["outcome"] in {"granted", "duplicate"}:
            upsert_subscription(connect, subscription_id, link["telegram_id"], link["plan_key"], link["order_id"],
                                _id(obj.get("customer")), "active", current_period_end=period_end)
        return outcome

    if event_type in {"customer.subscription.created", "customer.subscription.updated", "customer.subscription.deleted"}:
        link = _link_from_stripe(connect, client, obj["id"]) if obj.get("id") else None
        if not link:
            return {"outcome": "ignored", "reason": "unknown_subscription"}
        status = "canceled" if event_type == "customer.subscription.deleted" else (obj.get("status") or link["status"])
        upsert_subscription(connect, obj["id"], link["telegram_id"], link["plan_key"], link["order_id"],
                            _id(obj.get("customer")), status, bool(obj.get("cancel_at_period_end")),
                            _subscription_period_end(obj), obj.get("livemode"))
        # Paid time already granted is kept; nothing is revoked here.
        return {"outcome": "subscription_" + status, "telegram_id": link["telegram_id"], "plan_key": link["plan_key"]}

    return {"outcome": "ignored", "reason": "unhandled_event_type"}
