"""Store purchase orders: the server-side record of what a Mini App payment
buys, shared by the webapp (creates orders, finalizes Crypto Pay) and the
polling Telegram bot (validates and finalizes Telegram Stars payments).

Keep this file byte-identical in sylvex-ai-webapp/services/shop_orders.py
and sylvex-ai-bot/app/database/shop_orders.py. It depends only on a DB-API
`connect` callable (psycopg2), never on either application.

An order snapshots the product when it is created: price in USD cents,
expected Stars, credits to grant and, for plans, the subscription key and
duration. Invoices carry only "sylvex_order:<order_id>", so a payment can
never grant more than the order says. finalize_order() verifies payer,
provider, currency and amount, then records the purchase, grants credits and
activates the subscription in one transaction. The unique charge_id and the
order's own status make repeated callbacks harmless.
"""
import re
import uuid

ORDER_PAYLOAD_PREFIX = "sylvex_order:"
_ORDER_ID_RE = re.compile(r"[0-9a-f]{32}")

STATUS_PENDING = "pending"
STATUS_PAID = "paid"
STATUS_EXPIRED = "expired"
STATUS_FAILED = "failed"

ORDERS_DDL = """
CREATE TABLE IF NOT EXISTS shop_orders (
    order_id TEXT PRIMARY KEY,
    telegram_id BIGINT NOT NULL,
    product_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    title TEXT NOT NULL,
    usd_cents INTEGER NOT NULL,
    credits INTEGER NOT NULL DEFAULT 0,
    plan_key TEXT,
    days INTEGER,
    provider TEXT NOT NULL,
    stars INTEGER,
    provider_invoice_id TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    charge_id TEXT UNIQUE,
    paid_amount TEXT,
    paid_currency TEXT,
    failure_reason TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP NOT NULL,
    paid_at TIMESTAMP
)
"""
ORDERS_INDEX_DDL = "CREATE INDEX IF NOT EXISTS idx_shop_orders_user_created ON shop_orders (telegram_id, created_at DESC)"

_ORDER_COLUMNS = ("order_id", "telegram_id", "product_id", "kind", "title", "usd_cents", "credits",
                  "plan_key", "days", "provider", "stars", "provider_invoice_id", "status", "charge_id",
                  "expires_at", "paid_at")


def ensure_order_tables(connect):
    conn = connect()
    try:
        with conn.cursor() as cur:
            cur.execute(ORDERS_DDL)
            cur.execute(ORDERS_INDEX_DDL)
        conn.commit()
    finally:
        conn.close()


def order_payload(order_id):
    return ORDER_PAYLOAD_PREFIX + order_id


def parse_order_payload(payload):
    """order_id from an invoice payload, or None if it is not an order."""
    text = str(payload or "")
    if not text.startswith(ORDER_PAYLOAD_PREFIX):
        return None
    order_id = text[len(ORDER_PAYLOAD_PREFIX):]
    return order_id if _ORDER_ID_RE.fullmatch(order_id) else None


def _row_to_order(row):
    return dict(zip(_ORDER_COLUMNS, row)) if row else None


def create_order(connect, telegram_id, product, provider, ttl_seconds):
    """Persist a pending order for an already-resolved catalog product."""
    order_id = uuid.uuid4().hex
    conn = connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO shop_orders (order_id, telegram_id, product_id, kind, title, usd_cents, credits,
                                         plan_key, days, provider, stars, status, expires_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'pending',
                        CURRENT_TIMESTAMP + (%s || ' seconds')::interval)
                RETURNING """ + ", ".join(_ORDER_COLUMNS),
                (order_id, int(telegram_id), product["product_id"], product["kind"], product["title"],
                 int(product["usd_cents"]), int(product["credits"]), product.get("plan_key"), product.get("days"),
                 provider, int(product["stars"]) if provider == "telegram_stars" else None, int(ttl_seconds)),
            )
            order = _row_to_order(cur.fetchone())
        conn.commit()
        return order
    finally:
        conn.close()


def get_order(connect, order_id):
    conn = connect()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT " + ", ".join(_ORDER_COLUMNS) + " FROM shop_orders WHERE order_id = %s", (order_id,))
            return _row_to_order(cur.fetchone())
    finally:
        conn.close()


def set_provider_invoice(connect, order_id, invoice_id):
    conn = connect()
    try:
        with conn.cursor() as cur:
            cur.execute("UPDATE shop_orders SET provider_invoice_id = %s WHERE order_id = %s", (str(invoice_id), order_id))
        conn.commit()
    finally:
        conn.close()


def mark_order(connect, order_id, status, reason=None):
    """Move a still-pending order to expired/failed. Paid orders never change."""
    if status not in {STATUS_EXPIRED, STATUS_FAILED}:
        raise ValueError("unsupported order status")
    conn = connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE shop_orders SET status = %s, failure_reason = %s WHERE order_id = %s AND status = 'pending' RETURNING order_id",
                (status, reason, order_id),
            )
            changed = cur.fetchone() is not None
        conn.commit()
        return changed
    finally:
        conn.close()


def _amount_matches(order, currency, amount):
    if order["provider"] == "telegram_stars":
        return currency == "XTR" and order["stars"] is not None and str(amount).isdigit() and int(amount) == int(order["stars"])
    if order["provider"] == "crypto_pay":
        try:
            cents = round(float(str(amount)) * 100)
        except (TypeError, ValueError):
            return False
        return currency == "USDT" and cents == int(order["usd_cents"])
    return False


def checkout_check(connect, order_id, payer_id, provider, currency, amount):
    """Telegram pre_checkout_query: (ok, reason). Only live pending orders pass."""
    order = get_order(connect, order_id)
    if not order:
        return False, "order_not_found"
    if order["provider"] != provider:
        return False, "provider_mismatch"
    if int(order["telegram_id"]) != int(payer_id or 0):
        return False, "payer_mismatch"
    if order["status"] != STATUS_PENDING:
        return False, "order_not_pending"
    if not _amount_matches(order, currency, amount):
        return False, "amount_mismatch"
    conn = connect()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT expires_at > CURRENT_TIMESTAMP FROM shop_orders WHERE order_id = %s", (order_id,))
            live = bool((cur.fetchone() or [False])[0])
    finally:
        conn.close()
    return (True, None) if live else (False, "order_expired")


def finalize_order(connect, order_id, provider, currency, amount, charge_id, payer_id=None):
    """Grant a confirmed payment exactly once.

    Returns {"status": "granted" | "duplicate" | "rejected", "reason", "order"}.
    A payment that arrives after the order expired is still honored: the
    money was taken against a quote this service issued.
    """
    if not charge_id:
        return {"status": "rejected", "reason": "charge_id_required", "order": None}
    conn = connect()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT " + ", ".join(_ORDER_COLUMNS) + " FROM shop_orders WHERE order_id = %s FOR UPDATE", (order_id,))
            order = _row_to_order(cur.fetchone())
            if not order:
                conn.rollback()
                return {"status": "rejected", "reason": "order_not_found", "order": None}
            if order["status"] == STATUS_PAID:
                conn.rollback()
                same = order["charge_id"] == str(charge_id)
                return {"status": "duplicate" if same else "rejected",
                        "reason": None if same else "order_already_paid", "order": order}
            reason = None
            if order["provider"] != provider:
                reason = "provider_mismatch"
            elif payer_id is not None and int(order["telegram_id"]) != int(payer_id):
                reason = "payer_mismatch"
            elif order["status"] not in {STATUS_PENDING, STATUS_EXPIRED}:
                reason = "order_not_payable"
            elif not _amount_matches(order, currency, amount):
                reason = "amount_mismatch"
            if reason:
                conn.rollback()
                return {"status": "rejected", "reason": reason, "order": order}

            uid = int(order["telegram_id"])
            cur.execute(
                "INSERT INTO users (telegram_id, first_name, balance, subscription) VALUES (%s, 'Telegram User', 0, 'free') "
                "ON CONFLICT (telegram_id) DO NOTHING",
                (uid,),
            )
            cur.execute("SELECT telegram_id FROM users WHERE telegram_id = %s FOR UPDATE", (uid,))
            payment_amount = int(order["stars"]) if provider == "telegram_stars" else int(order["usd_cents"])
            cur.execute(
                """
                INSERT INTO purchases (telegram_id, provider, credits, amount, currency, payload, charge_id, status)
                VALUES (%s, %s, %s, %s, %s, %s, %s, 'completed')
                ON CONFLICT (charge_id) DO NOTHING
                RETURNING id
                """,
                (uid, provider, int(order["credits"]), payment_amount, currency, order_payload(order_id), str(charge_id)),
            )
            if cur.fetchone() is None:
                conn.rollback()
                return {"status": "duplicate", "reason": "charge_already_recorded", "order": order}
            if order["kind"] == "subscription":
                cur.execute(
                    """
                    INSERT INTO subscriptions (telegram_id, subscription_type, payment_method, amount, currency, expires_at, status, charge_id)
                    VALUES (%s, %s, %s, %s, %s,
                            (SELECT GREATEST(CURRENT_TIMESTAMP, COALESCE(MAX(expires_at::timestamp), CURRENT_TIMESTAMP))
                                    + (%s || ' days')::interval
                               FROM subscriptions
                              WHERE telegram_id = %s AND status = 'active' AND expires_at::timestamp > CURRENT_TIMESTAMP),
                            'active', %s)
                    RETURNING id
                    """,
                    (uid, order["plan_key"], provider, payment_amount, currency, int(order["days"]), uid, str(charge_id)),
                )
                subscription_id = cur.fetchone()[0]
                cur.execute("UPDATE subscriptions SET status = 'cancelled' WHERE telegram_id = %s AND status = 'active' AND id <> %s",
                            (uid, subscription_id))
                cur.execute("UPDATE users SET subscription = %s WHERE telegram_id = %s", (order["plan_key"], uid))
            cur.execute("UPDATE users SET balance = COALESCE(balance, 0) + %s WHERE telegram_id = %s", (int(order["credits"]), uid))
            cur.execute(
                """
                UPDATE shop_orders
                   SET status = 'paid', charge_id = %s, paid_amount = %s, paid_currency = %s,
                       paid_at = CURRENT_TIMESTAMP, failure_reason = NULL
                 WHERE order_id = %s
                """,
                (str(charge_id), str(amount), currency, order_id),
            )
            order.update(status=STATUS_PAID, charge_id=str(charge_id))
        conn.commit()
        return {"status": "granted", "reason": None, "order": order}
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
