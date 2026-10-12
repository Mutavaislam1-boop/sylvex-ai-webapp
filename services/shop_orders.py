"""Store purchase orders: the server-side record of what a Mini App payment
buys, shared by the webapp (creates orders, finalizes Crypto Pay and Stripe) and
the polling Telegram bot (validates and finalizes Telegram Stars payments).

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

Recurring Telegram Stars subscriptions (monthly plans): the order snapshots
subscription_period, and Telegram charges the SAME invoice again every 30
days. Each charge arrives as a successful_payment for the same order with a
new telegram_payment_charge_id and is_recurring set. The first creates one
subscriptions row (is_recurring, renewal_status 'auto'); each later charge is
a renewal of that row: it grants the period's credits once (the charge id is
unique in purchases and subscription_payments) and moves expires_at to the
expiration date Telegram reports, never backwards. Nothing here ever extends
a subscription without a confirmed payment: if no renewal arrives, the row
simply expires. Renewal cancellation and re-enabling go through Telegram's
editUserStarSubscription (set_auto_renew) and change local state only after
Telegram confirms.
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

# Recurring subscriptions: additive, idempotent migrations. Existing rows keep
# is_recurring = FALSE / renewal_status = 'none' (one-time plans, unchanged).
RENEWAL_NONE = "none"          # one-time plan, never renews
RENEWAL_AUTO = "auto"          # Telegram renews it every 30 days
RENEWAL_CANCELED = "canceled"  # renewal cancelled via SYLVEX, confirmed by Telegram
RENEWAL_REPLACED = "replaced"  # superseded by another subscription; renewal must stop

RECURRING_MIGRATIONS = (
    "ALTER TABLE shop_orders ADD COLUMN IF NOT EXISTS subscription_period INTEGER",
    """ALTER TABLE IF EXISTS subscriptions
           ADD COLUMN IF NOT EXISTS order_id TEXT,
           ADD COLUMN IF NOT EXISTS is_recurring BOOLEAN NOT NULL DEFAULT FALSE,
           ADD COLUMN IF NOT EXISTS renewal_status TEXT NOT NULL DEFAULT 'none',
           ADD COLUMN IF NOT EXISTS subscription_charge_id TEXT,
           ADD COLUMN IF NOT EXISTS last_charge_id TEXT,
           ADD COLUMN IF NOT EXISTS last_payment_at TIMESTAMP,
           ADD COLUMN IF NOT EXISTS renewals_count INTEGER NOT NULL DEFAULT 0,
           ADD COLUMN IF NOT EXISTS canceled_at TIMESTAMP,
           ADD COLUMN IF NOT EXISTS pending_plan_key TEXT""",
    "CREATE INDEX IF NOT EXISTS idx_subscriptions_order ON subscriptions (order_id)",
    """CREATE TABLE IF NOT EXISTS subscription_payments (
           id SERIAL PRIMARY KEY,
           subscription_id INTEGER,
           telegram_id BIGINT NOT NULL,
           order_id TEXT NOT NULL,
           charge_id TEXT NOT NULL UNIQUE,
           payment_kind TEXT NOT NULL,
           amount INTEGER NOT NULL,
           currency TEXT NOT NULL,
           credits INTEGER NOT NULL,
           period_end TIMESTAMP,
           created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
       )""",
    "CREATE INDEX IF NOT EXISTS idx_subscription_payments_sub ON subscription_payments (subscription_id, created_at)",
)

# A renewal charge may come with a pre_checkout_query (not documented either
# way): accept one for an already-paid recurring order only around its
# renewal date, so an old invoice link re-opened mid-period cannot start a
# second subscription.
RENEWAL_CHECKOUT_WINDOW_BEFORE_HOURS = 24
RENEWAL_CHECKOUT_WINDOW_AFTER_HOURS = 72

_ORDER_COLUMNS = ("order_id", "telegram_id", "product_id", "kind", "title", "usd_cents", "credits",
                  "plan_key", "days", "provider", "stars", "provider_invoice_id", "status", "charge_id",
                  "expires_at", "paid_at", "subscription_period")

_SUBSCRIPTION_COLUMNS = ("id", "telegram_id", "subscription_type", "amount", "currency", "status",
                         "starts_at", "expires_at", "order_id", "is_recurring", "renewal_status",
                         "subscription_charge_id", "last_charge_id", "last_payment_at", "renewals_count",
                         "canceled_at", "pending_plan_key", "credits", "stars")
_SUBSCRIPTION_SELECT = """
    SELECT s.id, s.telegram_id, s.subscription_type, s.amount, s.currency, s.status,
           s.starts_at::timestamp, s.expires_at::timestamp, s.order_id, s.is_recurring, s.renewal_status,
           s.subscription_charge_id, s.last_charge_id, s.last_payment_at, s.renewals_count,
           s.canceled_at, s.pending_plan_key, o.credits, o.stars
      FROM subscriptions s
      LEFT JOIN shop_orders o ON o.order_id = s.order_id
"""


def ensure_order_tables(connect):
    conn = connect()
    try:
        with conn.cursor() as cur:
            cur.execute(ORDERS_DDL)
            cur.execute(ORDERS_INDEX_DDL)
            for statement in RECURRING_MIGRATIONS:
                cur.execute(statement)
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
                                         plan_key, days, provider, stars, status, expires_at, subscription_period)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'pending',
                        CURRENT_TIMESTAMP + (%s || ' seconds')::interval, %s)
                RETURNING """ + ", ".join(_ORDER_COLUMNS),
                (order_id, int(telegram_id), product["product_id"], product["kind"], product["title"],
                 int(product["usd_cents"]), int(product["credits"]), product.get("plan_key"), product.get("days"),
                 provider, int(product["stars"]) if provider == "telegram_stars" else None, int(ttl_seconds),
                 int(product["subscription_period"]) if provider == "telegram_stars" and product.get("subscription_period") else None),
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
    if order["provider"] == "stripe":
        # Stripe reports amounts as integer minor units (cents).
        return str(currency).upper() == "USD" and str(amount).isdigit() and int(amount) == int(order["usd_cents"])
    return False


def _renewal_checkout_open(cur, order_id):
    cur.execute(
        """
        SELECT 1 FROM subscriptions
         WHERE order_id = %s AND is_recurring AND renewal_status = 'auto'
           AND CURRENT_TIMESTAMP BETWEEN expires_at::timestamp - (%s || ' hours')::interval
                                     AND expires_at::timestamp + (%s || ' hours')::interval
         LIMIT 1
        """,
        (order_id, RENEWAL_CHECKOUT_WINDOW_BEFORE_HOURS, RENEWAL_CHECKOUT_WINDOW_AFTER_HOURS),
    )
    return cur.fetchone() is not None


def _renewing_subscription_id(cur, telegram_id, exclude_order_id=None):
    """id of the user's active, still auto-renewing subscription, if any."""
    cur.execute(
        """
        SELECT id FROM subscriptions
         WHERE telegram_id = %s AND status = 'active' AND is_recurring AND renewal_status = 'auto'
           AND expires_at::timestamp > CURRENT_TIMESTAMP
           AND (order_id IS DISTINCT FROM %s)
         ORDER BY expires_at::timestamp DESC LIMIT 1
        """,
        (int(telegram_id), exclude_order_id),
    )
    row = cur.fetchone()
    return row[0] if row else None


def checkout_check(connect, order_id, payer_id, provider, currency, amount):
    """Telegram pre_checkout_query: (ok, reason). Only live pending orders pass,
    plus a renewal charge of a paid recurring order around its renewal date."""
    order = get_order(connect, order_id)
    if not order:
        return False, "order_not_found"
    if order["provider"] != provider:
        return False, "provider_mismatch"
    if int(order["telegram_id"]) != int(payer_id or 0):
        return False, "payer_mismatch"
    conn = connect()
    try:
        with conn.cursor() as cur:
            if order["status"] == STATUS_PAID and order.get("subscription_period"):
                if not _amount_matches(order, currency, amount):
                    return False, "amount_mismatch"
                return (True, None) if _renewal_checkout_open(cur, order_id) else (False, "order_not_pending")
            if order["status"] != STATUS_PENDING:
                return False, "order_not_pending"
            if not _amount_matches(order, currency, amount):
                return False, "amount_mismatch"
            cur.execute("SELECT expires_at > CURRENT_TIMESTAMP FROM shop_orders WHERE order_id = %s", (order_id,))
            if not bool((cur.fetchone() or [False])[0]):
                return False, "order_expired"
            # Never let a second plan be paid while another one still renews.
            if order["kind"] == "subscription" and _renewing_subscription_id(cur, order["telegram_id"], order_id):
                return False, "subscription_renewing"
            return True, None
    finally:
        conn.close()


def _payment_mismatch(order, provider, payer_id, currency, amount):
    if order["provider"] != provider:
        return "provider_mismatch"
    if payer_id is not None and int(order["telegram_id"]) != int(payer_id):
        return "payer_mismatch"
    if not _amount_matches(order, currency, amount):
        return "amount_mismatch"
    return None


def _expiration_epoch(value):
    try:
        epoch = int(value)
    except (TypeError, ValueError):
        return None
    return epoch if epoch > 0 else None


def _lock_user(cur, uid):
    cur.execute(
        "INSERT INTO users (telegram_id, first_name, balance, subscription) VALUES (%s, 'Telegram User', 0, 'free') "
        "ON CONFLICT (telegram_id) DO NOTHING",
        (uid,),
    )
    cur.execute("SELECT telegram_id FROM users WHERE telegram_id = %s FOR UPDATE", (uid,))


def _record_purchase(cur, uid, order, provider, currency, charge_id):
    """Insert the payment into purchases; False if this charge is already recorded."""
    payment_amount = int(order["stars"]) if provider == "telegram_stars" else int(order["usd_cents"])
    cur.execute(
        """
        INSERT INTO purchases (telegram_id, provider, credits, amount, currency, payload, charge_id, status)
        VALUES (%s, %s, %s, %s, %s, %s, %s, 'completed')
        ON CONFLICT (charge_id) DO NOTHING
        RETURNING id
        """,
        (uid, provider, int(order["credits"]), payment_amount, currency, order_payload(order["order_id"]), str(charge_id)),
    )
    return cur.fetchone() is not None


def _mark_order_paid(cur, order, charge_id, amount, currency):
    cur.execute(
        """
        UPDATE shop_orders
           SET status = 'paid', charge_id = %s, paid_amount = %s, paid_currency = %s,
               paid_at = CURRENT_TIMESTAMP, failure_reason = NULL
         WHERE order_id = %s
        """,
        (str(charge_id), str(amount), currency, order["order_id"]),
    )
    order.update(status=STATUS_PAID, charge_id=str(charge_id))


def _supersede_active_subscriptions(cur, uid):
    """Close the user's other active subscriptions before a new one starts.
    Renewing ones are returned: their Telegram renewal must be cancelled."""
    cur.execute(
        """
        SELECT id, subscription_charge_id, last_charge_id FROM subscriptions
         WHERE telegram_id = %s AND status = 'active' AND is_recurring AND renewal_status = 'auto'
         FOR UPDATE
        """,
        (uid,),
    )
    cancel = [{"telegram_id": uid, "subscription_id": row[0], "charge_id": row[1], "fallback_charge_id": row[2]}
              for row in cur.fetchall() if row[1]]
    cur.execute(
        """
        UPDATE subscriptions
           SET status = 'cancelled',
               renewal_status = CASE WHEN renewal_status = 'auto' THEN 'replaced' ELSE renewal_status END
         WHERE telegram_id = %s AND status = 'active'
        """,
        (uid,),
    )
    return cancel


def _grant_one_time(cur, order, provider, currency, amount, charge_id):
    uid = int(order["telegram_id"])
    _lock_user(cur, uid)
    if not _record_purchase(cur, uid, order, provider, currency, charge_id):
        return {"status": "duplicate", "reason": "charge_already_recorded", "order": order}
    cancel = []
    if order["kind"] == "subscription":
        payment_amount = int(order["stars"]) if provider == "telegram_stars" else int(order["usd_cents"])
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
        cur.execute(
            """
            SELECT id, subscription_charge_id, last_charge_id FROM subscriptions
             WHERE telegram_id = %s AND status = 'active' AND is_recurring AND renewal_status = 'auto' AND id <> %s
            """,
            (uid, subscription_id),
        )
        cancel = [{"telegram_id": uid, "subscription_id": row[0], "charge_id": row[1], "fallback_charge_id": row[2]}
                  for row in cur.fetchall() if row[1]]
        cur.execute(
            """
            UPDATE subscriptions
               SET status = 'cancelled',
                   renewal_status = CASE WHEN renewal_status = 'auto' THEN 'replaced' ELSE renewal_status END
             WHERE telegram_id = %s AND status = 'active' AND id <> %s
            """,
            (uid, subscription_id),
        )
        cur.execute("UPDATE users SET subscription = %s WHERE telegram_id = %s", (order["plan_key"], uid))
    cur.execute("UPDATE users SET balance = COALESCE(balance, 0) + %s WHERE telegram_id = %s", (int(order["credits"]), uid))
    _mark_order_paid(cur, order, charge_id, amount, currency)
    return {"status": "granted", "reason": None, "order": order, "payment_kind": "one_time", "cancel_renewals": cancel}


def _period_end_sql(expiration):
    """SQL for the end of a paid 30-day period: Telegram's own expiration date
    when reported, otherwise the order's days from now."""
    if expiration:
        return "to_timestamp(%s)::timestamp", (expiration,)
    return "CURRENT_TIMESTAMP + (%s || ' days')::interval", None


def _grant_initial_recurring(cur, order, provider, currency, amount, charge_id, expiration):
    uid = int(order["telegram_id"])
    _lock_user(cur, uid)
    if not _record_purchase(cur, uid, order, provider, currency, charge_id):
        return {"status": "duplicate", "reason": "charge_already_recorded", "order": order}
    cancel = _supersede_active_subscriptions(cur, uid)
    end_sql, end_param = _period_end_sql(expiration)
    end_args = end_param or (int(order["days"]),)
    cur.execute(
        f"""
        INSERT INTO subscriptions (telegram_id, subscription_type, payment_method, amount, currency, starts_at, expires_at,
                                   status, charge_id, order_id, is_recurring, renewal_status, subscription_charge_id,
                                   last_charge_id, last_payment_at)
        VALUES (%s, %s, %s, %s, %s, CURRENT_TIMESTAMP, {end_sql}, 'active', %s, %s, TRUE, 'auto', %s, %s, CURRENT_TIMESTAMP)
        RETURNING id, expires_at::timestamp
        """,
        (uid, order["plan_key"], provider, int(order["stars"]), currency, *end_args,
         str(charge_id), order["order_id"], str(charge_id), str(charge_id)),
    )
    subscription_id, period_end = cur.fetchone()
    cur.execute(
        """
        INSERT INTO subscription_payments (subscription_id, telegram_id, order_id, charge_id, payment_kind, amount, currency, credits, period_end)
        VALUES (%s, %s, %s, %s, 'initial', %s, %s, %s, %s)
        """,
        (subscription_id, uid, order["order_id"], str(charge_id), int(order["stars"]), currency, int(order["credits"]), period_end),
    )
    cur.execute("UPDATE users SET subscription = %s, balance = COALESCE(balance, 0) + %s WHERE telegram_id = %s",
                (order["plan_key"], int(order["credits"]), uid))
    _mark_order_paid(cur, order, charge_id, amount, currency)
    return {"status": "granted", "reason": None, "order": order, "payment_kind": "initial",
            "subscription_id": subscription_id, "period_end": period_end, "cancel_renewals": cancel}


def _grant_renewal(cur, order, provider, currency, charge_id, expiration, first_of_new_subscription):
    """A further charge of a recurring order: Telegram renewed the subscription."""
    uid = int(order["telegram_id"])
    _lock_user(cur, uid)
    cur.execute(_SUBSCRIPTION_SELECT + " WHERE s.order_id = %s ORDER BY s.id LIMIT 1 FOR UPDATE OF s", (order["order_id"],))
    subscription = dict(zip(_SUBSCRIPTION_COLUMNS, cur.fetchone() or ())) or None
    if not subscription:
        return {"status": "rejected", "reason": "subscription_not_found", "order": order}
    if not _record_purchase(cur, uid, order, provider, currency, charge_id):
        return {"status": "duplicate", "reason": "charge_already_recorded", "order": order}
    if expiration:
        end_sql, end_args = "to_timestamp(%s)::timestamp", (expiration,)
    else:
        end_sql = "GREATEST(expires_at::timestamp, CURRENT_TIMESTAMP) + (%s || ' days')::interval"
        end_args = (int(order["days"]),)
    replaced = subscription["renewal_status"] == RENEWAL_REPLACED
    # A renewal proves Telegram is renewing: a cancel that did not take
    # effect (or a re-enable inside Telegram) is reflected as 'auto' again.
    # A second subscription on the same invoice keeps the existing state.
    new_renewal = subscription["renewal_status"] if (replaced or first_of_new_subscription) else RENEWAL_AUTO
    cur.execute(
        f"""
        UPDATE subscriptions
           SET expires_at = GREATEST(expires_at::timestamp, {end_sql}),
               status = 'active',
               renewals_count = renewals_count + 1,
               last_charge_id = %s,
               last_payment_at = CURRENT_TIMESTAMP,
               renewal_status = %s,
               canceled_at = CASE WHEN %s = 'auto' THEN NULL ELSE canceled_at END,
               pending_plan_key = CASE WHEN %s = 'auto' THEN NULL ELSE pending_plan_key END
         WHERE id = %s
        RETURNING expires_at::timestamp
        """,
        (*end_args, str(charge_id), new_renewal, new_renewal, new_renewal, subscription["id"]),
    )
    period_end = cur.fetchone()[0]
    cur.execute(
        """
        INSERT INTO subscription_payments (subscription_id, telegram_id, order_id, charge_id, payment_kind, amount, currency, credits, period_end)
        VALUES (%s, %s, %s, %s, 'renewal', %s, %s, %s, %s)
        """,
        (subscription["id"], uid, order["order_id"], str(charge_id), int(order["stars"]), currency, int(order["credits"]), period_end),
    )
    if replaced:
        cur.execute("UPDATE users SET balance = COALESCE(balance, 0) + %s WHERE telegram_id = %s", (int(order["credits"]), uid))
    else:
        cur.execute("UPDATE users SET subscription = %s, balance = COALESCE(balance, 0) + %s WHERE telegram_id = %s",
                    (order["plan_key"], int(order["credits"]), uid))
    cancel = []
    if replaced and subscription["subscription_charge_id"]:
        # Telegram still renewed a superseded subscription: honor the payment
        # and stop its renewal again.
        cancel.append({"telegram_id": uid, "subscription_id": subscription["id"],
                       "charge_id": subscription["subscription_charge_id"], "fallback_charge_id": str(charge_id)})
    if first_of_new_subscription:
        # The same invoice was paid again as a NEW subscription: honor this
        # payment, but stop that second subscription from renewing.
        cancel.append({"telegram_id": uid, "subscription_id": subscription["id"], "charge_id": str(charge_id),
                       "fallback_charge_id": None})
    return {"status": "granted", "reason": None, "order": order, "payment_kind": "renewal",
            "subscription_id": subscription["id"], "period_end": period_end, "cancel_renewals": cancel}


def finalize_order(connect, order_id, provider, currency, amount, charge_id, payer_id=None, recurring=None):
    """Grant a confirmed payment exactly once.

    recurring: the subscription fields of Telegram's successful_payment
    ({"is_recurring", "is_first_recurring", "subscription_expiration_date"}).

    Returns {"status": "granted" | "duplicate" | "rejected", "reason", "order",
    "payment_kind": "one_time" | "initial" | "renewal", "cancel_renewals"}.
    cancel_renewals lists Telegram subscriptions whose renewal the caller must
    cancel (editUserStarSubscription) because a newer one replaced them.
    A payment that arrives after the order expired is still honored: the
    money was taken against a quote this service issued.
    """
    if not charge_id:
        return {"status": "rejected", "reason": "charge_id_required", "order": None}
    recurring = recurring or {}
    expiration = _expiration_epoch(recurring.get("subscription_expiration_date"))
    conn = connect()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT " + ", ".join(_ORDER_COLUMNS) + " FROM shop_orders WHERE order_id = %s FOR UPDATE", (order_id,))
            order = _row_to_order(cur.fetchone())
            if not order:
                conn.rollback()
                return {"status": "rejected", "reason": "order_not_found", "order": None}
            recurring_order = bool(order.get("subscription_period"))
            if order["status"] == STATUS_PAID:
                same = order["charge_id"] == str(charge_id)
                if same or not (recurring_order and recurring.get("is_recurring")):
                    conn.rollback()
                    return {"status": "duplicate" if same else "rejected",
                            "reason": None if same else "order_already_paid", "order": order}
                reason = _payment_mismatch(order, provider, payer_id, currency, amount)
                result = None if reason else _grant_renewal(
                    cur, order, provider, currency, charge_id, expiration, bool(recurring.get("is_first_recurring")))
            else:
                reason = _payment_mismatch(order, provider, payer_id, currency, amount)
                if not reason and order["status"] not in {STATUS_PENDING, STATUS_EXPIRED}:
                    reason = "order_not_payable"
                result = None
                if not reason:
                    result = (_grant_initial_recurring(cur, order, provider, currency, amount, charge_id, expiration)
                              if recurring_order else _grant_one_time(cur, order, provider, currency, amount, charge_id))
            if reason:
                conn.rollback()
                return {"status": "rejected", "reason": reason, "order": order}
            if result["status"] != "granted":
                conn.rollback()
                return result
        conn.commit()
        return result
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ------------------------------------------------ recurring subscriptions


def _select_subscription(cur, where, params):
    cur.execute(_SUBSCRIPTION_SELECT + " WHERE " + where, params)
    row = cur.fetchone()
    return dict(zip(_SUBSCRIPTION_COLUMNS, row)) if row else None


def _active_subscription(cur, telegram_id):
    return _select_subscription(
        cur, "s.telegram_id = %s AND s.status = 'active' AND s.expires_at::timestamp > CURRENT_TIMESTAMP "
             "ORDER BY s.expires_at::timestamp DESC, s.id DESC LIMIT 1", (int(telegram_id),))


def _public_subscription(sub, active):
    recurring = bool(sub["is_recurring"])
    auto = active and recurring and sub["renewal_status"] == RENEWAL_AUTO
    price = sub["stars"] if sub["stars"] is not None else (sub["amount"] if sub["currency"] == "XTR" else None)
    return {
        "plan_key": sub["subscription_type"],
        "active": bool(active),
        "is_recurring": recurring,
        "renewal_status": sub["renewal_status"] or RENEWAL_NONE,
        "auto_renew": bool(auto),
        "started_at": sub["starts_at"],
        "expires_at": sub["expires_at"],
        "next_renewal_at": sub["expires_at"] if auto else None,
        "price_stars": int(price) if price is not None else None,
        "period_days": 30 if recurring else None,
        "period_credits": int(sub["credits"]) if sub["credits"] is not None else None,
        "pending_plan_key": sub["pending_plan_key"],
        "renewals_count": int(sub["renewals_count"] or 0),
        "canceled_at": sub["canceled_at"],
        "last_payment_at": sub["last_payment_at"],
        # The renewal date passed without a confirmed payment: access has ended.
        "renewal_missed": bool(not active and recurring and sub["renewal_status"] == RENEWAL_AUTO),
    }


def subscription_summary(connect, telegram_id):
    """The user's subscription for display: the active one, else the latest
    recurring one (so a missed renewal or a scheduled plan change shows)."""
    conn = connect()
    try:
        with conn.cursor() as cur:
            sub = _active_subscription(cur, telegram_id)
            if sub:
                return _public_subscription(sub, True)
            sub = _select_subscription(
                cur, "s.telegram_id = %s AND s.is_recurring AND s.status IN ('active', 'expired') "
                     "ORDER BY s.expires_at::timestamp DESC NULLS LAST, s.id DESC LIMIT 1", (int(telegram_id),))
            return _public_subscription(sub, False) if sub else None
    finally:
        conn.close()


def subscription_conflict(connect, telegram_id, product, confirm_replace=False):
    """Why a plan purchase must not start now (or None). Telegram allows
    several concurrent subscriptions per user; SYLVEX never lets a user pay
    for a second plan while one still renews, and asks before a new 30-day
    subscription replaces a paid plan that is not renewing."""
    if product.get("kind") != "subscription":
        return None
    conn = connect()
    try:
        with conn.cursor() as cur:
            sub = _active_subscription(cur, telegram_id)
    finally:
        conn.close()
    if not sub:
        return None
    summary = _public_subscription(sub, True)
    if summary["auto_renew"]:
        return {"error": "subscription_renewing", "subscription": summary}
    if product.get("recurring") and not confirm_replace:
        return {"error": "subscription_replace_confirmation_required", "subscription": summary}
    return None


def _edit_star_subscription(call_telegram, telegram_id, sub, cancel):
    """editUserStarSubscription with the subscription's first charge id (its
    identifier), then its latest charge id if Telegram refuses the first."""
    candidates = [c for c in (sub["subscription_charge_id"], sub["last_charge_id"]) if c]
    error = "charge_id_missing"
    for charge_id in dict.fromkeys(candidates):
        ok, error = call_telegram("editUserStarSubscription", {
            "user_id": int(telegram_id), "telegram_payment_charge_id": str(charge_id), "is_canceled": bool(cancel)})
        if ok:
            return True, None
    return False, error


def set_auto_renew(connect, telegram_id, cancel, call_telegram, pending_plan_key=None):
    """Cancel (cancel=True) or re-enable the renewal of the user's active
    recurring subscription through Telegram. Local state changes only after
    Telegram confirms; paid access always runs to expires_at.

    call_telegram(method, params) -> (ok: bool, error_description or None).
    """
    conn = connect()
    try:
        with conn.cursor() as cur:
            sub = _select_subscription(
                cur, "s.telegram_id = %s AND s.status = 'active' AND s.is_recurring "
                     "AND s.expires_at::timestamp > CURRENT_TIMESTAMP AND s.renewal_status IN ('auto', 'canceled') "
                     "ORDER BY s.expires_at::timestamp DESC, s.id DESC LIMIT 1", (int(telegram_id),))
    finally:
        conn.close()
    if not sub:
        return {"ok": False, "error": "no_recurring_subscription"}
    target = RENEWAL_CANCELED if cancel else RENEWAL_AUTO
    if sub["renewal_status"] == target:
        if cancel and pending_plan_key != sub["pending_plan_key"]:
            _update_renewal(connect, sub["id"], target, pending_plan_key)
        return {"ok": True, "status": "already_canceled" if cancel else "already_active",
                "subscription": subscription_summary(connect, telegram_id)}
    ok, error = _edit_star_subscription(call_telegram, telegram_id, sub, cancel)
    if not ok:
        return {"ok": False, "error": "telegram_refused", "telegram_error": error,
                "subscription": _public_subscription(sub, True)}
    _update_renewal(connect, sub["id"], target, pending_plan_key if cancel else None)
    return {"ok": True, "status": "canceled" if cancel else "reactivated",
            "subscription": subscription_summary(connect, telegram_id)}


def _update_renewal(connect, subscription_id, renewal_status, pending_plan_key):
    conn = connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE subscriptions
                   SET renewal_status = %s,
                       canceled_at = CASE WHEN %s = 'canceled' THEN COALESCE(canceled_at, CURRENT_TIMESTAMP) ELSE NULL END,
                       pending_plan_key = %s
                 WHERE id = %s AND renewal_status IN ('auto', 'canceled')
                """,
                (renewal_status, renewal_status, pending_plan_key, subscription_id),
            )
        conn.commit()
    finally:
        conn.close()


def schedule_plan_change(connect, telegram_id, plan_key, call_telegram):
    """Switch monthly plans at the end of the paid period: stop the current
    subscription's renewal (through Telegram) and remember the new plan, which
    the user then subscribes to when the current period ends. Nothing is
    charged now, and never two plans at once."""
    current = subscription_summary(connect, telegram_id)
    if not current or not current["active"] or not current["is_recurring"]:
        return {"ok": False, "error": "no_recurring_subscription"}
    if plan_key == current["plan_key"]:
        return {"ok": False, "error": "same_plan"}
    return set_auto_renew(connect, telegram_id, True, call_telegram, pending_plan_key=plan_key)


def mark_renewal_replaced(connect, subscription_id, cancelled):
    """Record the outcome of cancelling a replaced subscription's renewal."""
    conn = connect()
    try:
        with conn.cursor() as cur:
            cur.execute("UPDATE subscriptions SET canceled_at = CASE WHEN %s THEN CURRENT_TIMESTAMP ELSE canceled_at END "
                        "WHERE id = %s", (bool(cancelled), subscription_id))
        conn.commit()
    finally:
        conn.close()


def cancel_replaced_renewals(connect, cancel_renewals, call_telegram):
    """Stop the renewal of subscriptions a newer payment replaced. Returns
    [(subscription_id, cancelled, error)]; failures are reported, not hidden."""
    outcomes = []
    for item in cancel_renewals or ():
        sub = {"subscription_charge_id": item.get("charge_id"), "last_charge_id": item.get("fallback_charge_id")}
        ok, error = _edit_star_subscription(call_telegram, item["telegram_id"], sub, True)
        mark_renewal_replaced(connect, item["subscription_id"], ok)
        outcomes.append((item["subscription_id"], ok, error))
    return outcomes
