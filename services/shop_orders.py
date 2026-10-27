"""Store purchase orders: the server-side record of what a Mini App payment
buys, shared by the webapp (creates orders, finalizes Stripe) and
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

Telegram Stars plans (see the entitlement / billing-agreement notes below):
monthly plans are Telegram subscriptions (subscription_period=2592000);
Telegram charges the SAME invoice again every 30 days, each charge arriving
as a successful_payment for the same order with a new
telegram_payment_charge_id and is_recurring set. Every charge grants its
period's credits exactly once (charge ids are unique in purchases and
subscription_payments) and extends the agreement's entitlement to the
expiration date Telegram reports, never backwards. Nothing is ever extended
without a confirmed payment. Renewal cancellation and re-enabling go through
Telegram's editUserStarSubscription and change local state only after
Telegram confirms. Administration events are queued in subscription_events
inside the same transaction (an outbox) and delivered separately.
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

PROVIDER_STARS = "telegram_stars"

# ---------------------------------------------------------------------------
# Telegram Stars subscriptions keep two separate records:
#
# * Paid entitlements - rows of the existing `subscriptions` table. Each one
#   is a paid right to a plan from starts_at to expires_at. Entitlements are
#   never merged or shortened: overlapping ones simply coexist until their own
#   expiration dates, and the HIGHEST tier among the currently valid ones is
#   the user's single effective plan (users.subscription).
# * Billing agreements - `subscription_agreements`, one per Telegram Stars
#   subscription (monthly plans, subscription_period=2592000). Telegram
#   charges the same invoice every 30 days; each charge extends that
#   agreement's entitlement and grants the month's credits once.
#
# Switching (the user always confirms and pays the full listed price; no
# proration, refunds or discounts): a new plan becomes effective on its
# confirmed payment if its tier is the highest valid one; every other
# renewing agreement is stopped through Telegram (editUserStarSubscription),
# so at most one agreement renews; older entitlements stay valid until their
# own expiration and take over again by tier when the higher one ends.
# Credits are only ever added.
# ---------------------------------------------------------------------------
AGREEMENT_AUTO = "auto"                  # Telegram renews it every 30 days
AGREEMENT_CANCELED = "canceled"          # renewal cancelled, confirmed by Telegram
AGREEMENT_STOP_PENDING = "stop_pending"  # replaced; SYLVEX still has to get Telegram to stop it
AGREEMENT_ENDED = "ended"                # expired without a renewal payment

TIER_RANKS = {"starter": 1, "pro": 2, "max": 3, "ultra": 4, "creator": 5}  # legacy month/year plans rank 1

# Renewals are charged by Telegram around expires_at; until RENEWAL_GRACE_HOURS
# later a missing renewal is shown as "not confirmed" (access has still ended:
# nothing is ever extended without a payment), then the agreement is "ended".
RENEWAL_GRACE_HOURS = 6
EXPIRY_EVENT_LOOKBACK_DAYS = 7

# A renewal charge may come with a pre_checkout_query (not documented either
# way): accept one for an already-paid recurring order only around its
# renewal date, so an old invoice link re-opened mid-period cannot start a
# second subscription.
RENEWAL_CHECKOUT_WINDOW_BEFORE_HOURS = 24
RENEWAL_CHECKOUT_WINDOW_AFTER_HOURS = 72

SUBSCRIPTION_MIGRATIONS = (
    "ALTER TABLE shop_orders ADD COLUMN IF NOT EXISTS subscription_period INTEGER",
    "ALTER TABLE shop_orders ADD COLUMN IF NOT EXISTS change_confirmed BOOLEAN NOT NULL DEFAULT FALSE",
    """ALTER TABLE IF EXISTS subscriptions
           ADD COLUMN IF NOT EXISTS order_id TEXT,
           ADD COLUMN IF NOT EXISTS agreement_id INTEGER,
           ADD COLUMN IF NOT EXISTS expired_event_at TIMESTAMP""",
    "CREATE INDEX IF NOT EXISTS idx_subscriptions_order ON subscriptions (order_id)",
    "CREATE INDEX IF NOT EXISTS idx_subscriptions_agreement ON subscriptions (agreement_id)",
    """CREATE TABLE IF NOT EXISTS subscription_agreements (
           id SERIAL PRIMARY KEY,
           telegram_id BIGINT NOT NULL,
           order_id TEXT NOT NULL UNIQUE,
           plan_key TEXT NOT NULL,
           stars INTEGER NOT NULL,
           credits INTEGER NOT NULL,
           subscription_charge_id TEXT NOT NULL,
           last_charge_id TEXT,
           renewal_status TEXT NOT NULL DEFAULT 'auto',
           cancel_reason TEXT,
           canceled_at TIMESTAMP,
           pending_plan_key TEXT,
           renewals_count INTEGER NOT NULL DEFAULT 0,
           last_payment_at TIMESTAMP,
           created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
           updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
       )""",
    "CREATE INDEX IF NOT EXISTS idx_subscription_agreements_user ON subscription_agreements (telegram_id, renewal_status)",
    """CREATE TABLE IF NOT EXISTS subscription_payments (
           id SERIAL PRIMARY KEY,
           agreement_id INTEGER,
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
    "CREATE INDEX IF NOT EXISTS idx_subscription_payments_agreement ON subscription_payments (agreement_id, created_at)",
    # Administration notification outbox: written in the same transaction as
    # the payment it reports, delivered later by a worker with retries.
    """CREATE TABLE IF NOT EXISTS subscription_events (
           id SERIAL PRIMARY KEY,
           event_key TEXT NOT NULL UNIQUE,
           event_type TEXT NOT NULL,
           telegram_id BIGINT,
           plan_key TEXT,
           amount INTEGER,
           currency TEXT,
           status TEXT,
           reference TEXT,
           details TEXT,
           created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
           attempts INTEGER NOT NULL DEFAULT 0,
           next_attempt_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
           sent_at TIMESTAMP,
           last_error TEXT
       )""",
    "CREATE INDEX IF NOT EXISTS idx_subscription_events_pending ON subscription_events (next_attempt_at) WHERE sent_at IS NULL",
)

_ORDER_COLUMNS = ("order_id", "telegram_id", "product_id", "kind", "title", "usd_cents", "credits",
                  "plan_key", "days", "provider", "stars", "provider_invoice_id", "status", "charge_id",
                  "expires_at", "paid_at", "subscription_period", "change_confirmed")

# SQL over `subscriptions s` (works whether the date columns are TIMESTAMP,
# as in production, or TEXT, as in databases created by the bot's init_db).
_STARTS_SQL = "NULLIF(s.starts_at::text, '')::timestamp"
_TIER_SQL = ("CASE split_part(s.subscription_type, '_', 1) WHEN 'creator' THEN 5 WHEN 'ultra' THEN 4 "
             "WHEN 'max' THEN 3 WHEN 'pro' THEN 2 ELSE 1 END")
VALID_ENTITLEMENT_SQL = ("s.status = 'active' AND COALESCE(" + _STARTS_SQL + ", '-infinity'::timestamp) <= CURRENT_TIMESTAMP "
                         "AND s.expires_at::timestamp > CURRENT_TIMESTAMP")
EFFECTIVE_ORDER_SQL = _TIER_SQL + " DESC, s.expires_at::timestamp DESC, s.id DESC"

_ENT_COLUMNS = ("id", "telegram_id", "plan_key", "amount", "currency", "payment_method", "status", "starts_at",
                "expires_at", "order_id", "agreement_id", "tier", "valid", "order_credits", "order_stars")
_ENT_SELECT = (
    "SELECT s.id, s.telegram_id, s.subscription_type, s.amount, s.currency, s.payment_method, s.status, "
    + _STARTS_SQL + ", s.expires_at::timestamp, s.order_id, s.agreement_id, " + _TIER_SQL + ", ("
    + VALID_ENTITLEMENT_SQL + "), o.credits, o.stars FROM subscriptions s LEFT JOIN shop_orders o ON o.order_id = s.order_id "
)
_AGR_COLUMNS = ("id", "telegram_id", "order_id", "plan_key", "stars", "credits", "subscription_charge_id",
                "last_charge_id", "renewal_status", "cancel_reason", "canceled_at", "pending_plan_key",
                "renewals_count", "last_payment_at", "created_at")
_AGR_SELECT = "SELECT " + ", ".join("a." + c for c in _AGR_COLUMNS) + " FROM subscription_agreements a "


def ensure_order_tables(connect):
    conn = connect()
    try:
        with conn.cursor() as cur:
            cur.execute(ORDERS_DDL)
            cur.execute(ORDERS_INDEX_DDL)
            for statement in SUBSCRIPTION_MIGRATIONS:
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


def create_order(connect, telegram_id, product, provider, ttl_seconds, change_confirmed=False):
    """Persist a pending order for an already-resolved catalog product.
    change_confirmed: the user confirmed buying this plan while another paid
    plan is valid (checked again at pre-checkout)."""
    if provider == "crypto_pay":
        raise ValueError("crypto_retired")
    order_id = uuid.uuid4().hex
    conn = connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO shop_orders (order_id, telegram_id, product_id, kind, title, usd_cents, credits,
                                         plan_key, days, provider, stars, status, expires_at, subscription_period,
                                         change_confirmed)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'pending',
                        CURRENT_TIMESTAMP + (%s || ' seconds')::interval, %s, %s)
                RETURNING """ + ", ".join(_ORDER_COLUMNS),
                (order_id, int(telegram_id), product["product_id"], product["kind"], product["title"],
                 int(product["usd_cents"]), int(product["credits"]), product.get("plan_key"), product.get("days"),
                 provider, int(product["stars"]) if provider == "telegram_stars" else None, int(ttl_seconds),
                 int(product["subscription_period"]) if provider == "telegram_stars" and product.get("subscription_period") else None,
                 bool(change_confirmed)),
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
    if order["provider"] == "stripe":
        # Stripe reports amounts as integer minor units (cents).
        return str(currency).upper() == "USD" and str(amount).isdigit() and int(amount) == int(order["usd_cents"])
    return False




# ------------------------------------------------ administration events (outbox)


def record_event(cur, event_key, event_type, telegram_id, plan_key=None, amount=None, currency=None,
                 status=None, reference=None, details=None):
    """Queue an administration notification in the caller's transaction (it
    commits or rolls back with the payment it reports). Idempotent by key."""
    cur.execute(
        """
        INSERT INTO subscription_events (event_key, event_type, telegram_id, plan_key, amount, currency, status, reference, details)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (event_key) DO NOTHING
        """,
        (str(event_key)[:200], event_type, int(telegram_id) if telegram_id else None, plan_key,
         int(amount) if amount is not None else None, currency, status,
         str(reference)[:200] if reference else None, str(details)[:1000] if details else None),
    )


def record_event_now(connect, event_key, event_type, telegram_id, **fields):
    """record_event in its own transaction (for failures outside a payment
    transaction). Never raises: a notification must not break processing."""
    try:
        conn = connect()
        try:
            with conn.cursor() as cur:
                record_event(cur, event_key, event_type, telegram_id, **fields)
            conn.commit()
        finally:
            conn.close()
        return True
    except Exception:
        return False


EVENT_COLUMNS = ("id", "event_key", "event_type", "telegram_id", "plan_key", "amount", "currency", "status",
                 "reference", "details", "created_at", "attempts")


def claim_events(connect, limit=20, lease_seconds=120):
    """Claim undelivered events for delivery (safe with several workers)."""
    conn = connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT " + ", ".join(EVENT_COLUMNS) + " FROM subscription_events "
                "WHERE sent_at IS NULL AND next_attempt_at <= CURRENT_TIMESTAMP ORDER BY id LIMIT %s FOR UPDATE SKIP LOCKED",
                (int(limit),),
            )
            rows = [dict(zip(EVENT_COLUMNS, row)) for row in cur.fetchall()]
            if rows:
                cur.execute(
                    "UPDATE subscription_events SET attempts = attempts + 1, "
                    "next_attempt_at = CURRENT_TIMESTAMP + (%s || ' seconds')::interval WHERE id = ANY(%s)",
                    (int(lease_seconds), [row["id"] for row in rows]),
                )
        conn.commit()
        return rows
    finally:
        conn.close()


def mark_event_sent(connect, event_id):
    conn = connect()
    try:
        with conn.cursor() as cur:
            cur.execute("UPDATE subscription_events SET sent_at = CURRENT_TIMESTAMP, last_error = NULL WHERE id = %s", (event_id,))
        conn.commit()
    finally:
        conn.close()


def mark_event_failed(connect, event_id, error):
    """Retry later with exponential backoff (30 s doubling, at most 1 h)."""
    conn = connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE subscription_events SET last_error = %s, next_attempt_at = CURRENT_TIMESTAMP "
                "+ (LEAST(3600, 30 * POWER(2, LEAST(attempts, 7)))::int || ' seconds')::interval WHERE id = %s",
                (str(error or "")[:300], event_id),
            )
        conn.commit()
    finally:
        conn.close()


# ------------------------------------------------ entitlements and agreements


def plan_tier(plan_key):
    plan_id = str(plan_key or "").lower().rpartition("_")[0]
    return TIER_RANKS.get(plan_id, 1)


def _ent(row):
    return dict(zip(_ENT_COLUMNS, row)) if row else None


def _agr(row):
    return dict(zip(_AGR_COLUMNS, row)) if row else None


def _valid_entitlements(cur, telegram_id):
    cur.execute(_ENT_SELECT + "WHERE s.telegram_id = %s AND " + VALID_ENTITLEMENT_SQL + " ORDER BY " + EFFECTIVE_ORDER_SQL,
                (int(telegram_id),))
    return [_ent(row) for row in cur.fetchall()]


def _effective_plan(cur, telegram_id):
    """The single effective plan: the highest tier among valid entitlements."""
    cur.execute("SELECT s.subscription_type FROM subscriptions s WHERE s.telegram_id = %s AND " + VALID_ENTITLEMENT_SQL
                + " ORDER BY " + EFFECTIVE_ORDER_SQL + " LIMIT 1", (int(telegram_id),))
    row = cur.fetchone()
    return row[0] if row else None


def _sync_effective_plan(cur, uid, before, event_key, reference=None):
    after = _effective_plan(cur, uid)
    cur.execute("UPDATE users SET subscription = %s WHERE telegram_id = %s", (after, uid))
    if after != before:
        record_event(cur, event_key, "primary_changed", uid, plan_key=after, status="effective",
                     reference=reference, details=f"from={before or 'none'} to={after or 'none'}")
    return after


def _stop_other_agreements(cur, uid, keep_agreement_id):
    """Every other renewing agreement must stop: at most one plan renews.
    Marked stop_pending here; the caller asks Telegram after commit."""
    cur.execute(
        _AGR_SELECT + "WHERE a.telegram_id = %s AND a.renewal_status IN ('auto', 'stop_pending') "
        "AND a.id IS DISTINCT FROM %s FOR UPDATE",
        (uid, keep_agreement_id),
    )
    agreements = [_agr(row) for row in cur.fetchall()]
    if agreements:
        cur.execute(
            "UPDATE subscription_agreements SET renewal_status = 'stop_pending', cancel_reason = 'replaced', "
            "updated_at = CURRENT_TIMESTAMP WHERE id = ANY(%s)",
            ([a["id"] for a in agreements],),
        )
    return [{"telegram_id": uid, "agreement_id": a["id"], "plan_key": a["plan_key"],
             "charge_id": a["subscription_charge_id"], "fallback_charge_id": a["last_charge_id"]} for a in agreements]


def _purchase_conflict(cur, telegram_id, product):
    """None, or why buying this plan needs attention: 'already_subscribed'
    (this monthly plan already renews) or a required confirmation."""
    if product.get("kind") != "subscription":
        return None
    valid = _valid_entitlements(cur, telegram_id)
    if not valid:
        return None
    if product.get("subscription_period"):
        cur.execute(
            "SELECT 1 FROM subscription_agreements a JOIN subscriptions s ON s.agreement_id = a.id "
            "WHERE a.telegram_id = %s AND a.plan_key = %s AND a.renewal_status = 'auto' AND " + VALID_ENTITLEMENT_SQL + " LIMIT 1",
            (int(telegram_id), product.get("plan_key")),
        )
        if cur.fetchone():
            return "already_subscribed"
    return "subscription_change_confirmation_required"


def _renewal_checkout_open(cur, order_id):
    cur.execute(
        """
        SELECT 1 FROM subscription_agreements a JOIN subscriptions s ON s.agreement_id = a.id
         WHERE a.order_id = %s AND a.renewal_status = 'auto'
           AND CURRENT_TIMESTAMP BETWEEN s.expires_at::timestamp - (%s || ' hours')::interval
                                     AND s.expires_at::timestamp + (%s || ' hours')::interval
         LIMIT 1
        """,
        (order_id, RENEWAL_CHECKOUT_WINDOW_BEFORE_HOURS, RENEWAL_CHECKOUT_WINDOW_AFTER_HOURS),
    )
    return cur.fetchone() is not None


def checkout_check(connect, order_id, payer_id, provider, currency, amount):
    """Telegram pre_checkout_query: (ok, reason). Only live pending orders pass,
    plus a renewal charge of a paid recurring order around its renewal date."""
    if provider == "crypto_pay":
        return False, "crypto_retired"
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
            # Re-checked at payment time: a plan is never charged while the
            # same monthly plan already renews, nor next to another valid
            # plan without the user's confirmation.
            conflict = _purchase_conflict(cur, order["telegram_id"], order)
            if conflict == "already_subscribed" or (conflict and not order.get("change_confirmed")):
                return False, conflict
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


def _epoch(value):
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


def _payment_amount(order, provider):
    return int(order["stars"]) if provider == PROVIDER_STARS else int(order["usd_cents"])


def _record_purchase(cur, uid, order, provider, currency, charge_id):
    """Insert the payment into purchases; False if this charge is already recorded."""
    cur.execute(
        """
        INSERT INTO purchases (telegram_id, provider, credits, amount, currency, payload, charge_id, status)
        VALUES (%s, %s, %s, %s, %s, %s, %s, 'completed')
        ON CONFLICT (charge_id) DO NOTHING
        RETURNING id
        """,
        (uid, provider, int(order["credits"]), _payment_amount(order, provider), currency,
         order_payload(order["order_id"]), str(charge_id)),
    )
    return cur.fetchone() is not None


def _add_credits(cur, uid, credits):
    cur.execute("UPDATE users SET balance = COALESCE(balance, 0) + %s WHERE telegram_id = %s", (int(credits), uid))


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


def _grant_one_time(cur, order, provider, currency, amount, charge_id):
    uid = int(order["telegram_id"])
    _lock_user(cur, uid)
    if not _record_purchase(cur, uid, order, provider, currency, charge_id):
        return {"status": "duplicate", "reason": "charge_already_recorded", "order": order}
    result = {"status": "granted", "reason": None, "order": order, "payment_kind": "one_time", "cancel_renewals": []}
    if order["kind"] == "subscription" and provider == PROVIDER_STARS:
        # Annual (one-time) Telegram plan: its own entitlement of `days` from
        # now - durations are never combined with another plan. Re-buying the
        # SAME annual plan continues it from that entitlement's end.
        before = _effective_plan(cur, uid)
        cur.execute(
            "SELECT MAX(s.expires_at::timestamp) FROM subscriptions s WHERE s.telegram_id = %s AND s.subscription_type = %s "
            "AND s.agreement_id IS NULL AND s.status = 'active' AND s.expires_at::timestamp > CURRENT_TIMESTAMP",
            (uid, order["plan_key"]),
        )
        continue_from = cur.fetchone()[0]
        cur.execute(
            """
            INSERT INTO subscriptions (telegram_id, subscription_type, payment_method, amount, currency, starts_at, expires_at,
                                       status, charge_id, order_id)
            VALUES (%s, %s, %s, %s, %s, COALESCE(%s, CURRENT_TIMESTAMP),
                    COALESCE(%s, CURRENT_TIMESTAMP) + (%s || ' days')::interval, 'active', %s, %s)
            RETURNING id, expires_at::timestamp
            """,
            (uid, order["plan_key"], provider, _payment_amount(order, provider), currency, continue_from, continue_from,
             int(order["days"]), str(charge_id), order["order_id"]),
        )
        subscription_id, period_end = cur.fetchone()
        result["cancel_renewals"] = _stop_other_agreements(cur, uid, None)
        _add_credits(cur, uid, order["credits"])
        result.update(subscription_id=subscription_id, period_end=period_end,
                      effective_plan=_sync_effective_plan(cur, uid, before, f"primary:{charge_id}", charge_id))
        record_event(cur, f"purchase:{charge_id}", "subscription_purchased", uid, plan_key=order["plan_key"],
                     amount=order["stars"], currency=currency, status="active_annual", reference=charge_id,
                     details=f"order={order['order_id']} credits={order['credits']}")
    elif order["kind"] == "subscription":
        # Website Stripe plans keep their existing behavior: the
        # new plan replaces the active one and continues from its expiry. A
        # renewing Telegram subscription is stopped so it cannot charge too.
        payment_amount = _payment_amount(order, provider)
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
        result["cancel_renewals"] = _stop_other_agreements(cur, uid, None)
        _add_credits(cur, uid, order["credits"])
    else:
        _add_credits(cur, uid, order["credits"])
    _mark_order_paid(cur, order, charge_id, amount, currency)
    return result


def _period_end_sql(expiration, base_sql="CURRENT_TIMESTAMP"):
    """End of a paid 30-day period: Telegram's subscription_expiration_date
    when reported, else the order's days from base."""
    if expiration:
        return "to_timestamp(%s)::timestamp", (expiration,)
    return base_sql + " + (%s || ' days')::interval", None


def _grant_initial_recurring(cur, order, provider, currency, amount, charge_id, expiration):
    uid = int(order["telegram_id"])
    _lock_user(cur, uid)
    if not _record_purchase(cur, uid, order, provider, currency, charge_id):
        return {"status": "duplicate", "reason": "charge_already_recorded", "order": order}
    before = _effective_plan(cur, uid)
    cur.execute(
        """
        INSERT INTO subscription_agreements (telegram_id, order_id, plan_key, stars, credits, subscription_charge_id,
                                             last_charge_id, renewal_status, last_payment_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, 'auto', CURRENT_TIMESTAMP)
        RETURNING id
        """,
        (uid, order["order_id"], order["plan_key"], int(order["stars"]), int(order["credits"]), str(charge_id), str(charge_id)),
    )
    agreement_id = cur.fetchone()[0]
    end_sql, end_param = _period_end_sql(expiration)
    cur.execute(
        f"""
        INSERT INTO subscriptions (telegram_id, subscription_type, payment_method, amount, currency, starts_at, expires_at,
                                   status, charge_id, order_id, agreement_id)
        VALUES (%s, %s, %s, %s, %s, CURRENT_TIMESTAMP, {end_sql}, 'active', %s, %s, %s)
        RETURNING id, expires_at::timestamp
        """,
        (uid, order["plan_key"], provider, int(order["stars"]), currency, *(end_param or (int(order["days"]),)),
         str(charge_id), order["order_id"], agreement_id),
    )
    subscription_id, period_end = cur.fetchone()
    cur.execute(
        """
        INSERT INTO subscription_payments (agreement_id, subscription_id, telegram_id, order_id, charge_id, payment_kind,
                                           amount, currency, credits, period_end)
        VALUES (%s, %s, %s, %s, %s, 'initial', %s, %s, %s, %s)
        """,
        (agreement_id, subscription_id, uid, order["order_id"], str(charge_id), int(order["stars"]), currency,
         int(order["credits"]), period_end),
    )
    cancel = _stop_other_agreements(cur, uid, agreement_id)
    _add_credits(cur, uid, order["credits"])
    _mark_order_paid(cur, order, charge_id, amount, currency)
    effective = _sync_effective_plan(cur, uid, before, f"primary:{charge_id}", charge_id)
    record_event(cur, f"purchase:{charge_id}", "subscription_purchased", uid, plan_key=order["plan_key"],
                 amount=order["stars"], currency=currency, status="active_recurring", reference=charge_id,
                 details=f"order={order['order_id']} credits={order['credits']} renews_until_cancelled")
    return {"status": "granted", "reason": None, "order": order, "payment_kind": "initial", "agreement_id": agreement_id,
            "subscription_id": subscription_id, "period_end": period_end, "cancel_renewals": cancel,
            "effective_plan": effective}


def _grant_renewal(cur, order, provider, currency, charge_id, expiration, first_of_new_subscription, paid_at):
    """A further charge of a recurring order: Telegram renewed the subscription."""
    uid = int(order["telegram_id"])
    _lock_user(cur, uid)
    cur.execute(_AGR_SELECT + "WHERE a.order_id = %s FOR UPDATE", (order["order_id"],))
    agreement = _agr(cur.fetchone())
    if not agreement:
        return {"status": "rejected", "reason": "agreement_not_found", "order": order}
    cur.execute("SELECT id FROM subscriptions WHERE agreement_id = %s ORDER BY id LIMIT 1 FOR UPDATE", (agreement["id"],))
    row = cur.fetchone()
    if not row:
        return {"status": "rejected", "reason": "subscription_not_found", "order": order}
    subscription_id = row[0]
    if not _record_purchase(cur, uid, order, provider, currency, charge_id):
        return {"status": "duplicate", "reason": "charge_already_recorded", "order": order}
    before = _effective_plan(cur, uid)
    end_sql, end_param = _period_end_sql(expiration, "GREATEST(expires_at::timestamp, CURRENT_TIMESTAMP)")
    cur.execute(
        f"""
        UPDATE subscriptions
           SET expires_at = GREATEST(expires_at::timestamp, {end_sql}), status = 'active', expired_event_at = NULL
         WHERE id = %s
        RETURNING expires_at::timestamp
        """,
        (*(end_param or (int(order["days"]),)), subscription_id),
    )
    period_end = cur.fetchone()[0]
    status = agreement["renewal_status"]
    attention = None
    cancel = []
    if first_of_new_subscription:
        # The same invoice was paid again as a NEW Telegram subscription:
        # honor this payment once, and stop that second subscription.
        new_status = status
        attention = "second_subscription_on_one_invoice"
        cancel.append({"telegram_id": uid, "agreement_id": agreement["id"], "plan_key": agreement["plan_key"],
                       "charge_id": str(charge_id), "fallback_charge_id": None, "keep_status": True})
    elif status == AGREEMENT_STOP_PENDING:
        new_status = status
        attention = "replaced_subscription_renewed"
        cancel.append({"telegram_id": uid, "agreement_id": agreement["id"], "plan_key": agreement["plan_key"],
                       "charge_id": agreement["subscription_charge_id"], "fallback_charge_id": str(charge_id)})
    elif status == AGREEMENT_CANCELED:
        # A charge Telegram made after the confirmed cancellation means it
        # renews again (e.g. re-enabled inside Telegram); an older charge
        # reported late leaves the cancellation in place.
        after_cancel = False
        if paid_at and agreement["canceled_at"]:
            cur.execute("SELECT to_timestamp(%s)::timestamp > %s::timestamp", (paid_at, agreement["canceled_at"]))
            after_cancel = bool(cur.fetchone()[0])
        new_status = AGREEMENT_AUTO if after_cancel else status
        if after_cancel:
            attention = "renewed_after_cancellation"
    else:
        new_status = AGREEMENT_AUTO
    cur.execute(
        """
        UPDATE subscription_agreements
           SET renewal_status = %s, renewals_count = renewals_count + 1, last_charge_id = %s,
               last_payment_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP,
               canceled_at = CASE WHEN %s = 'auto' THEN NULL ELSE canceled_at END,
               cancel_reason = CASE WHEN %s = 'auto' THEN NULL ELSE cancel_reason END,
               pending_plan_key = CASE WHEN %s = 'auto' THEN NULL ELSE pending_plan_key END
         WHERE id = %s
        """,
        (new_status, str(charge_id), new_status, new_status, new_status, agreement["id"]),
    )
    cur.execute(
        """
        INSERT INTO subscription_payments (agreement_id, subscription_id, telegram_id, order_id, charge_id, payment_kind,
                                           amount, currency, credits, period_end)
        VALUES (%s, %s, %s, %s, %s, 'renewal', %s, %s, %s, %s)
        """,
        (agreement["id"], subscription_id, uid, order["order_id"], str(charge_id), int(order["stars"]), currency,
         int(order["credits"]), period_end),
    )
    _add_credits(cur, uid, order["credits"])
    effective = _sync_effective_plan(cur, uid, before, f"primary:{charge_id}", charge_id)
    record_event(cur, f"renewal:{charge_id}", "subscription_renewed", uid, plan_key=order["plan_key"],
                 amount=order["stars"], currency=currency, status=new_status, reference=charge_id,
                 details=f"agreement={agreement['id']} renewals={agreement['renewals_count'] + 1} credits={order['credits']}")
    if attention:
        record_event(cur, f"attention:{charge_id}", "payment_attention", uid, plan_key=order["plan_key"],
                     amount=order["stars"], currency=currency, status=attention, reference=charge_id,
                     details=f"agreement={agreement['id']}")
    return {"status": "granted", "reason": None, "order": order, "payment_kind": "renewal", "agreement_id": agreement["id"],
            "subscription_id": subscription_id, "period_end": period_end, "cancel_renewals": cancel,
            "effective_plan": effective}


def finalize_order(connect, order_id, provider, currency, amount, charge_id, payer_id=None, recurring=None):
    """Grant a confirmed payment exactly once, atomically.

    recurring: the subscription fields of Telegram's successful_payment
    ({"is_recurring", "is_first_recurring", "subscription_expiration_date"})
    plus "paid_at", the payment message date (Unix time).

    Returns {"status": "granted" | "duplicate" | "rejected", "reason", "order",
    "payment_kind": "one_time" | "initial" | "renewal", "cancel_renewals"}.
    cancel_renewals lists Telegram subscriptions the caller must stop with
    stop_renewals() after this returns. A payment that arrives after the
    order expired is still honored: the money was taken against a quote this
    service issued.
    """
    if provider == "crypto_pay":
        return {"status": "rejected", "reason": "crypto_retired", "order": None}
    if not charge_id:
        return {"status": "rejected", "reason": "charge_id_required", "order": None}
    recurring = recurring or {}
    expiration = _epoch(recurring.get("subscription_expiration_date"))
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
                    cur, order, provider, currency, charge_id, expiration,
                    bool(recurring.get("is_first_recurring")), _epoch(recurring.get("paid_at")))
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


# ------------------------------------------------ renewal management (Telegram)


def _edit_star_subscription(call_telegram, telegram_id, charge_ids, cancel):
    """editUserStarSubscription with the subscription's first charge id (its
    identifier), then its latest charge id if Telegram refuses the first."""
    error = "charge_id_missing"
    for charge_id in dict.fromkeys(c for c in charge_ids if c):
        ok, error = call_telegram("editUserStarSubscription", {
            "user_id": int(telegram_id), "telegram_payment_charge_id": str(charge_id), "is_canceled": bool(cancel)})
        if ok:
            return True, None
    return False, error


def _agreements_with_expiry(cur, telegram_id):
    cur.execute(
        _AGR_SELECT.replace(" FROM subscription_agreements a ", ", MAX(s.expires_at::timestamp), "
                            "BOOL_OR(" + VALID_ENTITLEMENT_SQL + "), MAX(" + _STARTS_SQL + ") "
                            "FROM subscription_agreements a LEFT JOIN subscriptions s ON s.agreement_id = a.id ")
        + "WHERE a.telegram_id = %s GROUP BY " + ", ".join("a." + c for c in _AGR_COLUMNS) + " ORDER BY a.id DESC",
        (int(telegram_id),),
    )
    out = []
    for row in cur.fetchall():
        agreement = _agr(row[:len(_AGR_COLUMNS)])
        agreement.update(expires_at=row[-3], valid=bool(row[-2]), started_at=row[-1])
        out.append(agreement)
    return out


def set_auto_renew(connect, telegram_id, cancel, call_telegram, pending_plan_key=None, reason="user"):
    """Cancel (cancel=True) or re-enable the renewal of the user's Telegram
    Stars subscription. Local state changes only for what Telegram confirms;
    paid access always runs to its expiration date and credits are kept.

    call_telegram(method, params) -> (ok: bool, error_description or None).
    """
    uid = int(telegram_id)
    conn = connect()
    try:
        with conn.cursor() as cur:
            agreements = _agreements_with_expiry(cur, uid)
    finally:
        conn.close()
    live = [a for a in agreements if a["valid"]]
    if cancel:
        targets = [a for a in live if a["renewal_status"] in (AGREEMENT_AUTO, AGREEMENT_STOP_PENDING)]
        if not targets:
            canceled = [a for a in live if a["renewal_status"] == AGREEMENT_CANCELED]
            if canceled:
                if pending_plan_key and canceled[0]["pending_plan_key"] != pending_plan_key:
                    _update_agreement(connect, canceled[0]["id"], AGREEMENT_CANCELED, canceled[0]["cancel_reason"],
                                      pending_plan_key, (AGREEMENT_CANCELED,))
                return {"ok": True, "status": "already_canceled", "subscription": subscription_summary(connect, uid)}
            return {"ok": False, "error": "no_recurring_subscription", "subscription": subscription_summary(connect, uid)}
        failures = []
        for agreement in targets:
            ok, error = _edit_star_subscription(
                call_telegram, uid, (agreement["subscription_charge_id"], agreement["last_charge_id"]), True)
            if ok:
                is_primary_target = agreement["renewal_status"] == AGREEMENT_AUTO
                _update_agreement(connect, agreement["id"], AGREEMENT_CANCELED,
                                  reason if is_primary_target else agreement["cancel_reason"] or "replaced",
                                  pending_plan_key if is_primary_target else None, (AGREEMENT_AUTO, AGREEMENT_STOP_PENDING))
                record_event_now(connect, f"cancel:{agreement['id']}:{uuid.uuid4().hex[:12]}", "renewal_canceled", uid,
                                 plan_key=agreement["plan_key"], amount=agreement["stars"], currency="XTR",
                                 status="canceled_by_user" if reason == "user" else reason,
                                 reference=agreement["subscription_charge_id"],
                                 details=(f"access_until={agreement['expires_at']:%Y-%m-%d %H:%M}"
                                          + (f" scheduled_change_to={pending_plan_key}" if pending_plan_key else "")))
            else:
                failures.append((agreement, error))
                record_event_now(connect, f"cancelfail:{agreement['id']}:{uuid.uuid4().hex[:12]}", "management_error", uid,
                                 plan_key=agreement["plan_key"], status="cancel_refused",
                                 reference=agreement["subscription_charge_id"], details=str(error)[:300])
        summary = subscription_summary(connect, uid)
        if failures:
            return {"ok": False, "error": "telegram_refused", "telegram_error": failures[0][1], "subscription": summary}
        return {"ok": True, "status": "canceled", "subscription": summary}
    # Re-enable: only a renewal that SYLVEX itself cancelled (Telegram's rule),
    # and never while another plan renews.
    targets = [a for a in live if a["renewal_status"] == AGREEMENT_CANCELED and a["cancel_reason"] in ("user", "plan_change")]
    if any(a["renewal_status"] == AGREEMENT_AUTO for a in live):
        if not targets:
            return {"ok": True, "status": "already_active", "subscription": subscription_summary(connect, uid)}
        return {"ok": False, "error": "another_subscription_renewing", "subscription": subscription_summary(connect, uid)}
    if not targets:
        return {"ok": False, "error": "no_recurring_subscription", "subscription": subscription_summary(connect, uid)}
    agreement = targets[0]
    ok, error = _edit_star_subscription(
        call_telegram, uid, (agreement["subscription_charge_id"], agreement["last_charge_id"]), False)
    if not ok:
        record_event_now(connect, f"reactivatefail:{agreement['id']}:{uuid.uuid4().hex[:12]}", "management_error", uid,
                         plan_key=agreement["plan_key"], status="reactivation_refused",
                         reference=agreement["subscription_charge_id"], details=str(error)[:300])
        return {"ok": False, "error": "reactivation_unavailable", "telegram_error": error,
                "subscription": subscription_summary(connect, uid)}
    _update_agreement(connect, agreement["id"], AGREEMENT_AUTO, None, None, (AGREEMENT_CANCELED,))
    record_event_now(connect, f"reactivate:{agreement['id']}:{uuid.uuid4().hex[:12]}", "renewal_reactivated", uid,
                     plan_key=agreement["plan_key"], amount=agreement["stars"], currency="XTR", status="auto",
                     reference=agreement["subscription_charge_id"],
                     details=f"next_renewal={agreement['expires_at']:%Y-%m-%d %H:%M}")
    return {"ok": True, "status": "reactivated", "subscription": subscription_summary(connect, uid)}


def _update_agreement(connect, agreement_id, renewal_status, cancel_reason, pending_plan_key, expected_statuses):
    conn = connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE subscription_agreements
                   SET renewal_status = %s, cancel_reason = %s, pending_plan_key = %s, updated_at = CURRENT_TIMESTAMP,
                       canceled_at = CASE WHEN %s = 'canceled' THEN COALESCE(canceled_at, CURRENT_TIMESTAMP) ELSE NULL END
                 WHERE id = %s AND renewal_status = ANY(%s)
                """,
                (renewal_status, cancel_reason, pending_plan_key, renewal_status, agreement_id, list(expected_statuses)),
            )
        conn.commit()
    finally:
        conn.close()


def schedule_plan_change(connect, telegram_id, plan_key, call_telegram):
    """Move to another monthly plan when the current period ends (e.g. a
    downgrade without paying now): the current renewal is cancelled through
    Telegram and the new plan is offered for purchase after the period."""
    conn = connect()
    try:
        with conn.cursor() as cur:
            renewing = [a for a in _agreements_with_expiry(cur, telegram_id)
                        if a["valid"] and a["renewal_status"] == AGREEMENT_AUTO]
    finally:
        conn.close()
    if not renewing:
        return {"ok": False, "error": "no_recurring_subscription", "subscription": subscription_summary(connect, telegram_id)}
    if plan_key == renewing[0]["plan_key"]:
        return {"ok": False, "error": "same_plan", "subscription": subscription_summary(connect, telegram_id)}
    return set_auto_renew(connect, telegram_id, True, call_telegram, pending_plan_key=plan_key, reason="plan_change")


def stop_renewals(connect, items, call_telegram):
    """Stop the renewal of subscriptions a newer purchase replaced. Returns
    [(agreement_id, stopped, error)]; a failure stays 'stop_pending' (retried
    by sweep_subscriptions) and is reported to the administration."""
    outcomes = []
    for item in items or ():
        ok, error = _edit_star_subscription(call_telegram, item["telegram_id"],
                                            (item.get("charge_id"), item.get("fallback_charge_id")), True)
        if ok and not item.get("keep_status"):
            _update_agreement(connect, item["agreement_id"], AGREEMENT_CANCELED, "replaced", None, (AGREEMENT_STOP_PENDING,))
        if not ok:
            record_event_now(connect, f"stopfail:{item['agreement_id']}:{item.get('charge_id')}", "management_error",
                             item["telegram_id"], plan_key=item.get("plan_key"), status="replaced_renewal_not_stopped",
                             reference=item.get("charge_id"), details=str(error)[:300])
        outcomes.append((item["agreement_id"], ok, error))
    return outcomes


# ------------------------------------------------ expiry sweep


def sweep_subscriptions(connect, grace_hours=RENEWAL_GRACE_HOURS, lookback_days=EXPIRY_EVENT_LOOKBACK_DAYS, limit=200):
    """Record Telegram Stars entitlements that ended: a renewing one only
    after the renewal grace without a payment ('ended'), cancelled and
    one-time ones at their expiration. Updates the effective plan (fallback
    to another still-valid entitlement) and queues administration events.
    Returns {"expired": n, "stop_pending": [...]} - replaced renewals that
    Telegram has not confirmed stopping yet, for the caller to retry."""
    expired = 0
    conn = connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT s.id, s.telegram_id, s.subscription_type, s.agreement_id, a.renewal_status, s.charge_id,
                       a.subscription_charge_id
                  FROM subscriptions s
                  LEFT JOIN subscription_agreements a ON a.id = s.agreement_id
                 WHERE s.expired_event_at IS NULL AND s.status IN ('active', 'expired')
                   AND s.payment_method = 'telegram_stars'
                   AND s.expires_at::timestamp > CURRENT_TIMESTAMP - (%s || ' days')::interval
                   AND s.expires_at::timestamp <= CURRENT_TIMESTAMP
                       - (CASE WHEN a.renewal_status = 'auto' THEN %s ELSE 0 END || ' hours')::interval
                 ORDER BY s.id LIMIT %s
                 FOR UPDATE OF s SKIP LOCKED
                """,
                (int(lookback_days), int(grace_hours), int(limit)),
            )
            rows = cur.fetchall()
            for sid, uid, plan_key, agreement_id, renewal_status, charge_id, sub_charge in rows:
                cur.execute("SELECT telegram_id FROM users WHERE telegram_id = %s FOR UPDATE", (uid,))
                cur.execute("UPDATE subscriptions SET status = 'expired', expired_event_at = CURRENT_TIMESTAMP WHERE id = %s", (sid,))
                if agreement_id and renewal_status == AGREEMENT_AUTO:
                    cur.execute("UPDATE subscription_agreements SET renewal_status = 'ended', updated_at = CURRENT_TIMESTAMP "
                                "WHERE id = %s AND renewal_status = 'auto'", (agreement_id,))
                why = ("no_renewal" if renewal_status == AGREEMENT_AUTO else
                       "renewal_canceled" if agreement_id else "period_end")
                record_event(cur, f"expired:{sid}", "subscription_expired", uid, plan_key=plan_key, status=why,
                             reference=sub_charge or charge_id)
                after = _effective_plan(cur, uid)
                cur.execute("UPDATE users SET subscription = %s WHERE telegram_id = %s", (after, uid))
                if after:
                    record_event(cur, f"fallback:{sid}", "primary_changed", uid, plan_key=after, status="fallback",
                                 reference=sub_charge or charge_id, details=f"from={plan_key} to={after}")
                expired += 1
            cur.execute(_AGR_SELECT + "JOIN subscriptions s ON s.agreement_id = a.id WHERE a.renewal_status = 'stop_pending' "
                        "AND s.expires_at::timestamp > CURRENT_TIMESTAMP LIMIT %s", (int(limit),))
            stop_pending = [{"telegram_id": a["telegram_id"], "agreement_id": a["id"], "plan_key": a["plan_key"],
                             "charge_id": a["subscription_charge_id"], "fallback_charge_id": a["last_charge_id"]}
                            for a in (_agr(row) for row in cur.fetchall())]
        conn.commit()
    finally:
        conn.close()
    return {"expired": expired, "stop_pending": stop_pending}


# ------------------------------------------------ display


def _billing(entitlement):
    plan = str(entitlement["plan_key"] or "")
    if entitlement["agreement_id"]:
        return "monthly"
    if plan == "year" or plan.endswith("_year"):
        return "annual"
    return "monthly_one_time"


def _entitlement_view(ent, agreement):
    auto = bool(agreement and agreement["renewal_status"] == AGREEMENT_AUTO and ent["valid"])
    price = ent["order_stars"] if ent["order_stars"] is not None else (ent["amount"] if ent["currency"] == "XTR" else None)
    return {
        "id": ent["id"],
        "plan_key": ent["plan_key"],
        "tier": ent["tier"],
        "billing": _billing(ent),
        "payment_method": ent["payment_method"],
        "price_stars": int(price) if price is not None else None,
        "period_credits": int(ent["order_credits"]) if ent["order_credits"] is not None else None,
        "started_at": ent["starts_at"],
        "expires_at": ent["expires_at"],
        "valid": bool(ent["valid"]),
        "agreement_id": ent["agreement_id"],
        "renewal_status": agreement["renewal_status"] if agreement else "none",
        "auto_renew": auto,
        "next_renewal_at": ent["expires_at"] if auto else None,
    }


def _agreement_view(agreement, others_renewing):
    return {
        "id": agreement["id"],
        "plan_key": agreement["plan_key"],
        "renewal_status": agreement["renewal_status"],
        "auto_renew": agreement["renewal_status"] == AGREEMENT_AUTO and agreement["valid"],
        "price_stars": agreement["stars"],
        "period_credits": agreement["credits"],
        "started_at": agreement["started_at"],
        "expires_at": agreement["expires_at"],
        "next_renewal_at": agreement["expires_at"] if agreement["renewal_status"] == AGREEMENT_AUTO else None,
        "cancel_reason": agreement["cancel_reason"],
        "canceled_at": agreement["canceled_at"],
        "pending_plan_key": agreement["pending_plan_key"],
        "renewals_count": int(agreement["renewals_count"] or 0),
        "reactivatable": bool(agreement["valid"] and agreement["renewal_status"] == AGREEMENT_CANCELED
                              and agreement["cancel_reason"] in ("user", "plan_change") and not others_renewing),
    }


def subscription_summary(connect, telegram_id):
    """Everything the subscription screens show: the single effective plan,
    the other still-valid paid entitlements, the renewing (or cancelled)
    Telegram billing agreement, and one display state:
    active_recurring | renewal_canceled | active_annual | active_one_time |
    renewal_unconfirmed | expired. None if the user never had a plan."""
    uid = int(telegram_id)
    conn = connect()
    try:
        with conn.cursor() as cur:
            valid = _valid_entitlements(cur, uid)
            agreements = _agreements_with_expiry(cur, uid)
            latest = None
            if not valid:
                cur.execute(_ENT_SELECT + "WHERE s.telegram_id = %s AND s.status IN ('active', 'expired') "
                            "ORDER BY s.expires_at::timestamp DESC NULLS LAST, s.id DESC LIMIT 1", (uid,))
                latest = _ent(cur.fetchone())
            cur.execute("SELECT CURRENT_TIMESTAMP::timestamp - (%s || ' hours')::interval", (RENEWAL_GRACE_HOURS,))
            grace_start = cur.fetchone()[0]
    finally:
        conn.close()
    by_id = {a["id"]: a for a in agreements}
    renewing = [a for a in agreements if a["valid"] and a["renewal_status"] == AGREEMENT_AUTO]
    stopping = [a for a in agreements if a["valid"] and a["renewal_status"] == AGREEMENT_STOP_PENDING]
    canceled = [a for a in agreements if a["valid"] and a["renewal_status"] == AGREEMENT_CANCELED]
    renewal_agreement = (renewing or stopping or canceled or [None])[0]
    primary = valid[0] if valid else None
    if primary:
        agreement = by_id.get(primary["agreement_id"])
        if agreement:
            state = {AGREEMENT_AUTO: "active_recurring", AGREEMENT_CANCELED: "renewal_canceled",
                     AGREEMENT_STOP_PENDING: "renewal_unconfirmed"}.get(agreement["renewal_status"], "active_recurring")
        else:
            state = "active_annual" if _billing(primary) == "annual" else "active_one_time"
        shown = primary
    elif latest:
        agreement = by_id.get(latest["agreement_id"])
        lapsed_recently = bool(agreement and agreement["renewal_status"] == AGREEMENT_AUTO
                               and latest["expires_at"] and latest["expires_at"] > grace_start)
        state = "renewal_unconfirmed" if lapsed_recently else "expired"
        shown = latest
        if not renewal_agreement and agreement:
            renewal_agreement = agreement
    else:
        if not agreements:
            return None
        state, shown, agreement = "expired", None, agreements[0]
        renewal_agreement = renewal_agreement or agreement
    view = _entitlement_view(shown, by_id.get(shown["agreement_id"])) if shown else {}
    renewal = _agreement_view(renewal_agreement, bool(renewing) and renewal_agreement not in renewing) if renewal_agreement else None
    pending = next((a["pending_plan_key"] for a in agreements if a["pending_plan_key"]
                    and a["renewal_status"] in (AGREEMENT_CANCELED, AGREEMENT_ENDED)), None)
    shown_agreement = by_id.get(shown["agreement_id"]) if shown else None
    return {
        "state": state,
        "active": bool(primary),
        "primary": view or None,
        "entitlements": [_entitlement_view(e, by_id.get(e["agreement_id"])) for e in valid[1:]],
        "renewal": renewal,
        # Flat fields: the effective plan, and the renewal agreement's status.
        "plan_key": view.get("plan_key") or (renewal_agreement or {}).get("plan_key"),
        "billing": view.get("billing"),
        "is_recurring": bool(view.get("agreement_id")),
        "started_at": view.get("started_at"),
        "expires_at": view.get("expires_at"),
        "price_stars": view.get("price_stars"),
        "period_credits": view.get("period_credits"),
        "auto_renew": bool(renewal and renewal["auto_renew"]),
        "renewal_status": renewal["renewal_status"] if renewal else "none",
        "next_renewal_at": renewal["next_renewal_at"] if renewal and renewal["auto_renew"] else None,
        "pending_plan_key": pending,
        "renewals_count": int((shown_agreement or {}).get("renewals_count") or 0),
        "renewal_missed": bool(not primary and shown_agreement
                               and shown_agreement["renewal_status"] in (AGREEMENT_AUTO, AGREEMENT_ENDED)),
    }


def subscription_conflict(connect, telegram_id, product, confirm_change=False):
    """Why a plan purchase must not start right now, or None.

    'already_subscribed': this monthly plan already renews (never a second
    renewal). 'subscription_change_confirmation_required': another paid plan
    is valid; the user must confirm the full price and its consequences
    (described in "change") before an invoice is created."""
    if product.get("kind") != "subscription":
        return None
    conn = connect()
    try:
        with conn.cursor() as cur:
            conflict = _purchase_conflict(cur, telegram_id, product)
    finally:
        conn.close()
    if not conflict or (conflict != "already_subscribed" and confirm_change):
        return None
    summary = subscription_summary(connect, telegram_id)
    primary = (summary or {}).get("primary") or {}
    renewal = (summary or {}).get("renewal") or {}
    new_tier = plan_tier(product.get("plan_key"))
    current_tier = primary.get("tier") or 0
    same_annual = next((e for e in [primary] + (summary or {}).get("entitlements", [])
                        if e and e.get("plan_key") == product.get("plan_key") and e.get("billing") == "annual"), None)
    change = {
        "type": ("renew_same_plan" if same_annual else "upgrade" if new_tier > current_tier
                 else "downgrade" if new_tier < current_tier else "same_tier"),
        "new_plan_key": product.get("plan_key"),
        "new_billing": "monthly" if product.get("subscription_period") else "annual",
        "price_stars": product.get("stars"),
        "credits": product.get("credits"),
        "starts_at": same_annual["expires_at"] if same_annual and not product.get("subscription_period") else None,
        "becomes_primary_now": new_tier >= current_tier and not same_annual,
        "current_plan_key": primary.get("plan_key"),
        "current_expires_at": primary.get("expires_at"),
        "stops_renewal_of": renewal.get("plan_key") if renewal.get("renewal_status") == AGREEMENT_AUTO else None,
    }
    return {"error": conflict, "subscription": summary, "change": change}


# ------------------------------------------------ future plan benefits


def valid_entitlement_plans(connect, telegram_id):
    """Plan keys of every currently valid paid entitlement (highest tier first)."""
    conn = connect()
    try:
        with conn.cursor() as cur:
            return [e["plan_key"] for e in _valid_entitlements(cur, telegram_id)]
    finally:
        conn.close()


def combined_allowance(plan_keys, allowances, benefit):
    """Additive quantitative benefits across overlapping paid entitlements:
    e.g. allowances={"starter": {"saved_characters": 5}, "pro": {...: 10}}
    gives 15 with both valid. No limits are defined or enforced yet."""
    total = 0
    for plan_key in plan_keys or ():
        plan_id = str(plan_key or "").lower().rpartition("_")[0] or str(plan_key or "").lower()
        total += int(((allowances or {}).get(plan_id) or {}).get(benefit) or 0)
    return total
