"""Stripe Checkout for Website purchases: product/price sync, webhook
signatures, Checkout Sessions, one-time and subscription grants, renewals,
failures, cancellations and duplicate deliveries.

Stripe is the in-memory fake in tests/stripe_fake.py (no network, no real
payments). Ledger tests use a disposable PostgreSQL in
SYLVEX_TEST_DATABASE_URL (skipped otherwise)."""
import asyncio
import json
import os
import time

import pytest

import main
from services import shop_catalog as catalog
from services import shop_orders as orders
from services import stripe_billing as sb
from tests.stripe_fake import FakeStripe, event, sign, unflatten

DATABASE = os.getenv("SYLVEX_TEST_DATABASE_URL")
UID = 770044
OTHER = 770045
SECRET = "whsec_test_secret"
KEY = "sk_test_fake"


def client_for(fake):
    return sb.StripeClient(KEY, session=fake)


def creation_calls(fake):
    return [(m, p) for m, p, _b, _h in fake.calls if m == "POST" and p in {"/products", "/prices"}]


# ---------------------------------------------------------------------------
# Catalog sync (no database)
# ---------------------------------------------------------------------------

def test_sync_creates_every_product_and_price_once():
    fake = FakeStripe()
    mapping = sb.sync_catalog(client_for(fake))
    assert len(fake.products) == 5 + 8 + 1
    assert len(fake.prices) == 10 + 8
    expected = {
        "plan_starter": (500, 4800), "plan_pro": (1000, 9600), "plan_max": (2500, 24000),
        "plan_ultra": (5000, 48000), "plan_creator": (10000, 96000),
    }
    for product, (month, year) in expected.items():
        for period, amount in (("month", month), ("year", year)):
            entry = mapping[f"sylvex_{product}_{period}"]
            price = fake.prices[entry["stripe_price_id"]]
            assert entry["stripe_product_id"] == f"sylvex_{product}"
            assert price["unit_amount"] == amount and price["currency"] == "usd"
            assert price["recurring"] == {"interval": period, "interval_count": 1}
    for usd in catalog.CREDIT_PACK_USD:
        entry = mapping[f"sylvex_pack_{usd * 100}"]
        price = fake.prices[entry["stripe_price_id"]]
        assert price["unit_amount"] == usd * 100 and price["recurring"] is None
        assert fake.products[entry["stripe_product_id"]]["name"].startswith("SYLVEX")
    assert mapping["sylvex_credits_custom"]["stripe_product_id"] == "sylvex_credits_custom"
    assert sb.catalog_complete(mapping)
    assert not any("sk_test" in json.dumps(entry) for entry in mapping.values())


def test_sync_is_idempotent_and_never_duplicates():
    fake = FakeStripe()
    first = sb.sync_catalog(client_for(fake))
    created = len(creation_calls(fake))
    second = sb.sync_catalog(client_for(fake))
    assert len(creation_calls(fake)) == created
    assert len(fake.products) == 14 and len(fake.prices) == 18
    assert {k: v["stripe_price_id"] for k, v in first.items()} == {k: v["stripe_price_id"] for k, v in second.items()}
    assert {v["price_status"] for k, v in second.items() if k != "sylvex_credits_custom"} == {"reused"}


def test_a_changed_price_moves_the_lookup_key_and_keeps_the_old_price():
    fake = FakeStripe()
    first = sb.sync_catalog(client_for(fake))
    old_id = first["sylvex_plan_pro_month"]["stripe_price_id"]
    fake.prices[old_id]["unit_amount"] = 999  # e.g. edited by hand to a wrong amount
    second = sb.sync_catalog(client_for(fake))
    new_id = second["sylvex_plan_pro_month"]["stripe_price_id"]
    assert new_id != old_id and second["sylvex_plan_pro_month"]["price_status"] == "replaced"
    assert fake.prices[old_id]["active"] is True and fake.prices[old_id]["lookup_key"] is None
    assert fake.prices[new_id]["unit_amount"] == 1000
    assert all(not p.get("active") is False for p in fake.prices.values())  # nothing archived


def test_existing_products_are_reused_and_archived_ones_left_alone():
    fake = FakeStripe()
    fake.products["sylvex_plan_ultra"] = {"id": "sylvex_plan_ultra", "name": "Owner's name", "active": False, "metadata": {}}
    mapping = sb.sync_catalog(client_for(fake))
    assert fake.products["sylvex_plan_ultra"]["name"] == "Owner's name"
    assert fake.products["sylvex_plan_ultra"]["active"] is False
    assert mapping["sylvex_plan_ultra_month"]["price_status"] == "product_inactive"
    assert mapping["sylvex_plan_ultra_month"]["stripe_price_id"] is None
    assert not sb.catalog_complete(mapping)


def test_concurrent_price_creation_reuses_the_winner():
    fake = FakeStripe()
    sb.sync_catalog(client_for(fake))
    # Simulate a race: the lookup returned nothing, then creation conflicts.
    price = next(p for p in fake.prices.values() if p["lookup_key"] == "sylvex_pack_500")
    real_get = fake._get_prices
    calls = {"n": 0}

    def flaky_get(path, body):
        calls["n"] += 1
        if calls["n"] == 1:
            return real_get(path, {"lookup_keys": []})
        return real_get(path, body)

    fake._get_prices = flaky_get
    mapping = sb.sync_catalog(client_for(fake))
    assert mapping["sylvex_pack_500"]["stripe_price_id"] == price["id"]
    assert len(fake.prices) == 18


def test_form_encoding_round_trips_nested_params():
    params = {"a": 1, "b": {"c": "x", "d": [{"e": 2}, {"e": 3}]}, "f": True, "g": None}
    pairs = sb._flatten(params)
    assert ("b[d][1][e]", "3") in pairs and ("f", "true") in pairs and all(k != "g" for k, _ in pairs)
    assert unflatten(pairs) == {"a": "1", "b": {"c": "x", "d": [{"e": "2"}, {"e": "3"}]}, "f": "true"}


def test_client_errors_never_contain_the_secret_key():
    fake = FakeStripe()
    fake.fail_next.append(("GET", "/products", 401, "invalid_api_key"))
    with pytest.raises(sb.StripeError) as raised:
        client_for(fake).request("GET", "/products/x")
    assert KEY not in str(raised.value) and raised.value.status == 401
    assert sb.key_livemode("sk_live_abc") and not sb.key_livemode(KEY)


# ---------------------------------------------------------------------------
# Webhook signatures
# ---------------------------------------------------------------------------

def test_webhook_signature_verification():
    payload = json.dumps(event("invoice.paid", {"id": "in_1"})).encode()
    now = time.time()
    assert sb.verify_webhook(payload, sign(payload, SECRET, now), SECRET, now=now)["id"] == "evt_invoice.paid_in_1"
    # Several v1 signatures (secret rotation): any match is accepted.
    header = sign(payload, SECRET, now) + ",v1=" + "0" * 64
    assert sb.verify_webhook(payload, header, SECRET, now=now)
    for bad_header, bad_payload, at in (
        (sign(payload, "whsec_other", now), payload, now),
        (sign(payload, SECRET, now), payload + b" ", now),
        (sign(payload, SECRET, now - 1000), payload, now),
        ("", payload, now),
        ("t=abc,v1=00", payload, now),
    ):
        with pytest.raises(sb.SignatureError):
            sb.verify_webhook(bad_payload, bad_header, SECRET, now=at)
    with pytest.raises(sb.SignatureError):
        sb.verify_webhook(payload, sign(payload, SECRET, now), "", now=now)


# ---------------------------------------------------------------------------
# Checkout Session parameters
# ---------------------------------------------------------------------------

def order_for(product_id, usd=None, order_id="a" * 32, uid=UID):
    product = catalog.resolve_product(product_id, usd)
    return dict(product, order_id=order_id, telegram_id=uid)


def test_checkout_params_for_packs_plans_and_custom_amounts():
    pack = sb.checkout_session_params(order_for("pack_10000"), "price_pack", "sylvex_credits_custom", "https://s/ok", "https://s/no", now=1000)
    assert pack["mode"] == "payment" and pack["line_items"] == [{"price": "price_pack", "quantity": 1}]
    assert pack["client_reference_id"] == "a" * 32 and pack["metadata"]["sylvex_uid"] == str(UID)
    assert pack["payment_intent_data"]["metadata"]["sylvex_order_id"] == "a" * 32
    assert pack["customer_creation"] == "always" and pack["expires_at"] == 1000 + sb.CHECKOUT_TTL_SECONDS
    assert "10,000 ⚡" in pack["custom_text"]["submit"]["message"]

    plan = sb.checkout_session_params(order_for("plan_max_year"), "price_max_year", "c", "u", "v", customer_id="cus_1")
    assert plan["mode"] == "subscription" and plan["customer"] == "cus_1" and "customer_creation" not in plan
    assert plan["subscription_data"]["metadata"]["sylvex_plan_key"] == "max_year"
    assert "12,000 ⚡" in plan["custom_text"]["submit"]["message"] and "renews automatically" in plan["custom_text"]["submit"]["message"]

    custom = sb.checkout_session_params(order_for("credits_custom", "12.34"), None, "sylvex_credits_custom", "u", "v")
    assert custom["line_items"] == [{"price_data": {"currency": "usd", "unit_amount": 1234, "product": "sylvex_credits_custom"}, "quantity": 1}]


@pytest.mark.parametrize("usd,ok", [("0.99", False), ("1", True), ("1.00", True), ("999.99", True), ("1000", True),
                                    ("1000.01", False), ("12.345", False), ("abc", False), ("", False)])
def test_custom_amount_boundaries(usd, ok):
    if ok:
        assert catalog.resolve_product("credits_custom", usd)["credits"] == round(float(usd) * 100)
    else:
        with pytest.raises(catalog.CatalogError):
            catalog.resolve_product("credits_custom", usd)


# ---------------------------------------------------------------------------
# Ledger (PostgreSQL)
# ---------------------------------------------------------------------------

@pytest.fixture
def db(monkeypatch):
    if not DATABASE:
        pytest.skip("Set SYLVEX_TEST_DATABASE_URL to a disposable PostgreSQL database")
    import psycopg2

    def connect():
        return psycopg2.connect(DATABASE)

    conn = connect()
    with conn.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS shop_orders, purchases, subscriptions, users, stripe_catalog, stripe_customers, "
                    "stripe_subscriptions, stripe_events CASCADE")
        cur.execute("CREATE TABLE users (telegram_id BIGINT PRIMARY KEY, first_name TEXT, balance INTEGER DEFAULT 0, subscription TEXT DEFAULT 'free')")
        cur.execute("""CREATE TABLE purchases (id SERIAL PRIMARY KEY, telegram_id BIGINT NOT NULL, provider TEXT NOT NULL, credits INTEGER DEFAULT 0,
                       amount INTEGER DEFAULT 0, currency TEXT DEFAULT 'USD', payload TEXT, charge_id TEXT UNIQUE, status TEXT DEFAULT 'completed',
                       created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
        cur.execute("""CREATE TABLE subscriptions (id SERIAL PRIMARY KEY, telegram_id BIGINT NOT NULL, subscription_type TEXT, payment_method TEXT,
                       amount INTEGER DEFAULT 0, currency TEXT DEFAULT 'USD', starts_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, expires_at TIMESTAMP,
                       status TEXT DEFAULT 'active', charge_id TEXT UNIQUE, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
        cur.execute("INSERT INTO users (telegram_id, first_name, balance) VALUES (%s, 'Buyer', 50), (%s, 'Other', 0)", (UID, OTHER))
    conn.commit()
    conn.close()
    orders.ensure_order_tables(connect)
    sb.ensure_tables(connect)

    def query(sql, params=()):
        c = connect()
        try:
            with c.cursor() as cur:
                cur.execute(sql, params)
                return cur.fetchall()
        finally:
            c.close()

    return type("DB", (), {"connect": staticmethod(connect), "query": staticmethod(query)})


def balance(db, uid=UID):
    return db.query("SELECT balance FROM users WHERE telegram_id = %s", (uid,))[0][0]


def new_order(db, product_id, usd=None, uid=UID):
    return orders.create_order(db.connect, uid, catalog.resolve_product(product_id, usd), "stripe", 3600)


def finalizer(db):
    def finalize(order_id, currency, amount, charge_id):
        return orders.finalize_order(db.connect, order_id, "stripe", currency, amount, charge_id)
    return finalize


def paid_session(order, amount=None, payment_intent="pi_1", customer="cus_1", livemode=False):
    return {"id": "cs_" + order["order_id"][:6], "object": "checkout.session", "mode": "payment", "payment_status": "paid",
            "client_reference_id": order["order_id"], "amount_total": order["usd_cents"] if amount is None else amount,
            "currency": "usd", "total_details": {"amount_tax": 0}, "payment_intent": payment_intent, "customer": customer,
            "livemode": livemode, "metadata": {"sylvex_order_id": order["order_id"]}}


@pytest.mark.parametrize("usd", catalog.CREDIT_PACK_USD)
def test_every_pack_grants_its_credits_exactly_once(db, usd):
    fake = FakeStripe()
    order = new_order(db, f"pack_{usd * 100}")
    ev = event("checkout.session.completed", paid_session(order, payment_intent=f"pi_{usd}"))
    first = sb.handle_event(db.connect, client_for(fake), ev, finalizer(db))
    again = sb.handle_event(db.connect, client_for(fake), ev, finalizer(db))
    assert first["outcome"] == "granted" and again["outcome"] == "duplicate"
    assert balance(db) == 50 + usd * 100
    assert db.query("SELECT provider, amount, currency, charge_id FROM purchases") == [("stripe", usd * 100, "USD", f"pi_{usd}")]
    assert orders.get_order(db.connect, order["order_id"])["status"] == "paid"
    assert db.query("SELECT customer_id FROM stripe_customers WHERE telegram_id = %s", (UID,)) == [("cus_1",)]


@pytest.mark.parametrize("usd,credits", [("1", 100), ("12.34", 1234), ("1000", 100000)])
def test_custom_amount_grants_server_side_credits(db, usd, credits):
    order = new_order(db, "credits_custom", usd)
    result = sb.handle_event(db.connect, client_for(FakeStripe()), event("checkout.session.completed", paid_session(order)), finalizer(db))
    assert result["outcome"] == "granted" and balance(db) == 50 + credits


def test_wrong_amount_unpaid_or_unknown_sessions_grant_nothing(db):
    order = new_order(db, "pack_1000")
    fake = FakeStripe()
    assert sb.handle_event(db.connect, client_for(fake), event("checkout.session.completed", paid_session(order, amount=999)),
                           finalizer(db))["reason"] == "amount_mismatch"
    unpaid = dict(paid_session(order), payment_status="unpaid")
    assert sb.handle_event(db.connect, client_for(fake), event("checkout.session.completed", unpaid), finalizer(db))["outcome"] == "pending"
    stranger = dict(paid_session(order), client_reference_id="f" * 32, metadata={})
    assert sb.handle_event(db.connect, client_for(fake), event("checkout.session.completed", stranger), finalizer(db))["outcome"] == "ignored"
    from services import telegram_catalog
    stars_order = orders.create_order(db.connect, UID, telegram_catalog.resolve("pack_1000"), "telegram_stars", 3600)
    assert sb.handle_event(db.connect, client_for(fake), event("checkout.session.completed", paid_session(stars_order)),
                           finalizer(db))["outcome"] == "ignored"
    assert balance(db) == 50
    # The async success that follows a delayed payment still grants once.
    late = sb.handle_event(db.connect, client_for(fake), event("checkout.session.async_payment_succeeded", paid_session(order)), finalizer(db))
    assert late["outcome"] == "granted" and balance(db) == 1050


def test_expired_and_failed_checkouts_close_the_order(db):
    fake = FakeStripe()
    expired = new_order(db, "pack_500")
    failed = new_order(db, "pack_500")
    sb.handle_event(db.connect, client_for(fake), event("checkout.session.expired", {"id": "cs_x", "client_reference_id": expired["order_id"]}), finalizer(db))
    sb.handle_event(db.connect, client_for(fake), event("checkout.session.async_payment_failed", {"id": "cs_y", "client_reference_id": failed["order_id"]}), finalizer(db))
    assert orders.get_order(db.connect, expired["order_id"])["status"] == "expired"
    assert orders.get_order(db.connect, failed["order_id"])["status"] == "failed"
    assert balance(db) == 50


def subscription_invoice(sub_id, invoice_id, amount, reason, start, end, shape="2024"):
    invoice = {"id": invoice_id, "object": "invoice", "billing_reason": reason, "currency": "usd", "amount_paid": amount,
               "total": amount, "total_excluding_tax": amount, "customer": "cus_9",
               "lines": {"data": [{"period": {"start": start, "end": end}}]}}
    if shape == "2024":
        invoice["subscription"] = sub_id
    else:  # 2025+ API versions moved the subscription under parent
        invoice["parent"] = {"subscription_details": {"subscription": sub_id}}
    return invoice


def stripe_subscription(fake, sub_id, order, status="active", period_end=None):
    fake.subscriptions[sub_id] = {"id": sub_id, "object": "subscription", "status": status, "customer": "cus_9", "livemode": False,
                                  "cancel_at_period_end": False, "current_period_end": period_end,
                                  "metadata": {"sylvex_order_id": order["order_id"], "sylvex_plan_key": order["plan_key"]}}
    return fake.subscriptions[sub_id]


def active_rows(db, uid=UID):
    return db.query("""SELECT subscription_type, payment_method, expires_at FROM subscriptions
                       WHERE telegram_id = %s AND status = 'active'""", (uid,))


@pytest.mark.parametrize("plan,period", [(p[0], period) for p in catalog.PLANS for period in ("month", "year")])
def test_every_plan_activates_and_grants_its_allocation_once(db, plan, period):
    fake = FakeStripe()
    order = new_order(db, f"plan_{plan}_{period}")
    product = catalog.FIXED_PRODUCTS[f"plan_{plan}_{period}"]
    now = int(time.time())
    end = now + (30 if period == "month" else 365) * 86400
    stripe_subscription(fake, "sub_1", order, period_end=end)
    # Checkout completion only links the subscription; the invoice grants.
    session = {"id": "cs_1", "mode": "subscription", "client_reference_id": order["order_id"], "subscription": "sub_1",
               "customer": "cus_9", "livemode": False, "payment_status": "paid"}
    assert sb.handle_event(db.connect, client_for(fake), event("checkout.session.completed", session), finalizer(db))["outcome"] == "recorded"
    assert balance(db) == 50
    invoice = subscription_invoice("sub_1", "in_1", product["usd_cents"], "subscription_create", now, end)
    first = sb.handle_event(db.connect, client_for(fake), event("invoice.paid", invoice), finalizer(db))
    again = sb.handle_event(db.connect, client_for(fake), event("invoice.paid", invoice, event_id="evt_retry"), finalizer(db))
    assert first["outcome"] == "granted" and again["outcome"] == "duplicate"
    assert balance(db) == 50 + product["credits"]
    rows = active_rows(db)
    assert len(rows) == 1 and rows[0][0] == f"{plan}_{period}" and rows[0][1] == "stripe"
    days = (rows[0][2] - __import__("datetime").datetime.now()).total_seconds() / 86400
    assert (30 if period == "month" else 365) + sb.RENEWAL_GRACE_DAYS - 1 < days < (30 if period == "month" else 365) + sb.RENEWAL_GRACE_DAYS + 1
    assert db.query("SELECT status FROM stripe_subscriptions WHERE subscription_id = 'sub_1'") == [("active",)]


def test_invoice_before_checkout_completion_links_from_stripe_metadata(db):
    fake = FakeStripe()
    order = new_order(db, "plan_pro_month")
    now = int(time.time())
    stripe_subscription(fake, "sub_2", order)
    invoice = subscription_invoice("sub_2", "in_2", 1000, "subscription_create", now, now + 31 * 86400, shape="2025")
    assert sb.handle_event(db.connect, client_for(fake), event("invoice.paid", invoice), finalizer(db))["outcome"] == "granted"
    assert balance(db) == 350
    assert ("GET", "/subscriptions/sub_2") in [(m, p) for m, p, _b, _h in fake.calls]


def test_renewals_grant_again_extend_the_plan_and_ignore_repeats(db):
    fake = FakeStripe()
    order = new_order(db, "plan_starter_month")
    now = int(time.time())
    stripe_subscription(fake, "sub_3", order)
    first_end = now + 31 * 86400
    sb.handle_event(db.connect, client_for(fake), event("invoice.paid", subscription_invoice("sub_3", "in_a", 500, "subscription_create", now, first_end)), finalizer(db))
    expiry_1 = active_rows(db)[0][2]
    renewal = subscription_invoice("sub_3", "in_b", 500, "subscription_cycle", first_end, first_end + 30 * 86400)
    result = sb.handle_event(db.connect, client_for(fake), event("invoice.paid", renewal), finalizer(db))
    repeat = sb.handle_event(db.connect, client_for(fake), event("invoice.paid", renewal, event_id="evt_dup"), finalizer(db))
    assert result["outcome"] == "granted" and result["credits"] == 100 and repeat["outcome"] == "duplicate"
    assert balance(db) == 50 + 100 + 100
    rows = active_rows(db)
    assert len(rows) == 1
    assert abs((rows[0][2] - expiry_1).total_seconds() - 30 * 86400) < 5
    assert db.query("SELECT COUNT(*) FROM purchases WHERE provider = 'stripe'") == [(2,)]


def test_annual_renewal_grants_the_full_annual_allocation(db):
    fake = FakeStripe()
    order = new_order(db, "plan_creator_year")
    now = int(time.time())
    stripe_subscription(fake, "sub_y", order)
    sb.handle_event(db.connect, client_for(fake), event("invoice.paid", subscription_invoice("sub_y", "in_y1", 96000, "subscription_create", now, now + 365 * 86400)), finalizer(db))
    sb.handle_event(db.connect, client_for(fake), event("invoice.paid", subscription_invoice("sub_y", "in_y2", 96000, "subscription_cycle", now + 365 * 86400, now + 730 * 86400)), finalizer(db))
    assert balance(db) == 50 + 66000 * 2


def test_renewal_with_a_wrong_amount_or_proration_grants_nothing(db):
    fake = FakeStripe()
    order = new_order(db, "plan_pro_month")
    now = int(time.time())
    stripe_subscription(fake, "sub_4", order)
    sb.handle_event(db.connect, client_for(fake), event("invoice.paid", subscription_invoice("sub_4", "in_c", 1000, "subscription_create", now, now + 30 * 86400)), finalizer(db))
    wrong = sb.handle_event(db.connect, client_for(fake), event("invoice.paid", subscription_invoice("sub_4", "in_d", 1, "subscription_cycle", now, now + 60 * 86400)), finalizer(db))
    proration = sb.handle_event(db.connect, client_for(fake), event("invoice.paid", subscription_invoice("sub_4", "in_e", 700, "subscription_update", now, now + 30 * 86400)), finalizer(db))
    assert wrong["outcome"] == "rejected" and wrong["reason"] == "amount_mismatch"
    assert proration["outcome"] == "ignored"
    assert balance(db) == 50 + 300


def test_failed_payment_and_cancellation_keep_paid_access(db):
    fake = FakeStripe()
    order = new_order(db, "plan_max_month")
    now = int(time.time())
    stripe_subscription(fake, "sub_5", order)
    sb.handle_event(db.connect, client_for(fake), event("invoice.paid", subscription_invoice("sub_5", "in_f", 2500, "subscription_create", now, now + 30 * 86400)), finalizer(db))
    failed = sb.handle_event(db.connect, client_for(fake), event("invoice.payment_failed", subscription_invoice("sub_5", "in_g", 2500, "subscription_cycle", now, now + 60 * 86400)), finalizer(db))
    assert failed["outcome"] == "payment_failed" and failed["telegram_id"] == UID
    assert db.query("SELECT status FROM stripe_subscriptions WHERE subscription_id = 'sub_5'") == [("past_due",)]
    cancelled = dict(fake.subscriptions["sub_5"], status="canceled")
    out = sb.handle_event(db.connect, client_for(fake), event("customer.subscription.deleted", cancelled), finalizer(db))
    assert out["outcome"] == "subscription_canceled"
    assert db.query("SELECT status FROM stripe_subscriptions WHERE subscription_id = 'sub_5'") == [("canceled",)]
    assert len(active_rows(db)) == 1 and balance(db) == 50 + 1000
    assert not sb.has_live_subscription(db.connect, UID, False)


def test_cancel_at_period_end_and_reminder_exclusion(db):
    fake = FakeStripe()
    order = new_order(db, "plan_pro_month")
    stripe_subscription(fake, "sub_6", order)
    now = int(time.time())
    sb.handle_event(db.connect, client_for(fake), event("invoice.paid", subscription_invoice("sub_6", "in_h", 1000, "subscription_create", now, now + 30 * 86400)), finalizer(db))
    assert sb.has_live_subscription(db.connect, UID, False)
    sql = "SELECT COUNT(*) FROM subscriptions s WHERE " + sb.renews_automatically_sql("s", False)
    assert db.query(sql) == [(1,)]
    updated = dict(fake.subscriptions["sub_6"], cancel_at_period_end=True)
    sb.handle_event(db.connect, client_for(fake), event("customer.subscription.updated", updated), finalizer(db))
    assert db.query(sql) == [(0,)]  # a cancelled-at-period-end plan gets reminders again
    assert not sb.has_live_subscription(db.connect, UID, False)  # so a new plan may be bought


def test_events_for_other_subscriptions_are_ignored(db):
    fake = FakeStripe()
    fake.subscriptions["sub_x"] = {"id": "sub_x", "status": "active", "metadata": {}}
    out = sb.handle_event(db.connect, client_for(fake), event("invoice.paid", subscription_invoice("sub_x", "in_x", 500, "subscription_create", 1, 2)), finalizer(db))
    assert out["outcome"] == "ignored" and balance(db) == 50
    assert sb.handle_event(db.connect, client_for(fake), event("charge.refunded", {"id": "ch_1"}), finalizer(db))["outcome"] == "ignored"


def test_catalog_mapping_round_trips_per_mode(db):
    mapping = sb.sync_catalog(client_for(FakeStripe()))
    sb.save_catalog(db.connect, mapping, False)
    sb.save_catalog(db.connect, mapping, False)
    loaded = sb.load_catalog(db.connect, False)
    assert loaded.keys() == mapping.keys() and sb.catalog_complete(loaded)
    assert sb.load_catalog(db.connect, True) == {}


# ---------------------------------------------------------------------------
# HTTP endpoints (main.py)
# ---------------------------------------------------------------------------

class FakeRequest:
    def __init__(self, body=None, raw=None, headers=None, init_data=""):
        self._body = body
        self._raw = raw
        self.headers = headers or {}
        self.state = type("State", (), {"telegram_init_data": init_data})()

    async def json(self):
        return json.loads(json.dumps(self._body))

    async def body(self):
        return self._raw


def run(coro):
    return asyncio.run(coro)


def body_of(response):
    if isinstance(response, dict):
        return 200, response
    return response.status_code, json.loads(response.body)


@pytest.fixture
def app(db, monkeypatch):
    fake = FakeStripe()
    monkeypatch.setattr(main, "shop_db", db.connect)
    monkeypatch.setattr(main, "ensure_payment_tables", lambda: None)
    monkeypatch.setattr(main, "_SHOP_ORDERS_READY", False)
    monkeypatch.setattr(main, "_STRIPE_STATE", {"client": sb.StripeClient(KEY, session=fake), "tables": False, "catalog": None})
    monkeypatch.setattr(main, "STRIPE_SECRET_KEY", KEY)
    monkeypatch.setattr(main, "STRIPE_WEBHOOK_SECRET", SECRET)
    monkeypatch.setattr(main, "DATABASE_URL", DATABASE)
    monkeypatch.setattr(main, "WEBSITE_URL", "https://sylvex.ai")
    events = []
    monkeypatch.setattr(main, "log_user_event", lambda **kwargs: events.append(kwargs))
    monkeypatch.setattr(main, "send_subscription_congratulations", lambda *args, **kwargs: None)
    monkeypatch.setattr(main, "get_user_state", lambda telegram_id, **kwargs: {"telegram_id": telegram_id})
    return type("App", (), {"fake": fake, "events": events})


def checkout(body, init_data=""):
    return body_of(run(main.public_stripe_checkout(FakeRequest(dict({"telegram_id": UID}, **body), init_data=init_data))))


def deliver(payload_obj, secret=SECRET):
    raw = json.dumps(payload_obj).encode()
    return body_of(run(main.public_stripe_webhook(FakeRequest(raw=raw, headers={"stripe-signature": sign(raw, secret)}))))


def test_checkout_endpoint_creates_an_order_and_a_session(app, db):
    status, body = checkout({"product_id": "plan_ultra_month", "credits": 999999, "usd": "1"})
    assert status == 200 and body["ok"] and body["url"].startswith("https://checkout.stripe.com/")
    order = orders.get_order(db.connect, body["order_id"])
    assert order["provider"] == "stripe" and order["usd_cents"] == 5000 and order["credits"] == 2500
    session = next(iter(app.fake.sessions.values()))
    params = session["params"]
    assert order["provider_invoice_id"] == session["id"]
    assert params["mode"] == "subscription" and params["client_reference_id"] == order["order_id"]
    assert app.fake.prices[params["line_items"][0]["price"]]["unit_amount"] == 5000
    assert params["success_url"] == f"https://sylvex.ai/store.html?payment=success&provider=stripe&order_id={order['order_id']}"
    assert params["subscription_data"]["metadata"]["sylvex_uid"] == str(UID)
    idempotency = [h.get("Idempotency-Key") for m, p, _b, h in app.fake.calls if p == "/checkout/sessions"]
    assert idempotency == [f"sylvex-checkout-{order['order_id']}"]
    # The catalog synced once and is reused for the next checkout.
    created = len(creation_calls(app.fake))
    assert checkout({"product_id": "credits_custom", "usd": "250.50"})[0] == 200
    assert len(creation_calls(app.fake)) == created
    custom = list(app.fake.sessions.values())[-1]["params"]
    assert custom["line_items"][0]["price_data"]["unit_amount"] == "25050"


def test_checkout_endpoint_refusals(app, db, monkeypatch):
    assert checkout({"product_id": "pack_500"}, init_data="query_id=1&user=x")[1]["error"] == "stripe_not_available_in_telegram"
    assert checkout({"product_id": "pack_999"})[1]["error"] == "unknown_product"
    assert checkout({"product_id": "credits_custom", "usd": "1000.01"})[1]["error"] == "amount_out_of_range"
    assert checkout({"product_id": "credits_custom", "usd": "0.5"})[0] == 400
    # A live-mode subscription never blocks test mode (and vice versa).
    sb.upsert_subscription(db.connect, "sub_livemode", UID, "pro_month", None, "cus_live", "active", livemode=True)
    assert checkout({"product_id": "plan_max_month"})[0] == 200
    sb.upsert_subscription(db.connect, "sub_live", UID, "pro_month", None, "cus_1", "active", livemode=False)
    status, body = checkout({"product_id": "plan_max_month"})
    assert status == 409 and body["error"] == "stripe_subscription_active"
    assert checkout({"product_id": "pack_500"})[0] == 200  # credits are still allowed
    monkeypatch.setattr(main, "STRIPE_WEBHOOK_SECRET", "")
    assert checkout({"product_id": "pack_500"})[1]["error"] == "stripe_not_configured"
    assert body_of(run(main.public_stripe_checkout(FakeRequest({"product_id": "pack_500"}))))[0] == 400


def test_checkout_recovers_from_an_archived_price_and_deleted_customer(app, db):
    assert checkout({"product_id": "pack_1000"})[0] == 200
    price_id = main._STRIPE_STATE["catalog"]["sylvex_pack_1000"]["stripe_price_id"]
    app.fake.prices[price_id]["active"] = False  # archived by hand in the Dashboard
    sb.save_customer(db.connect, OTHER, "cus_deleted_1", False)
    status, body = body_of(run(main.public_stripe_checkout(FakeRequest({"telegram_id": OTHER, "product_id": "pack_1000"}))))
    assert status == 200
    params = list(app.fake.sessions.values())[-1]["params"]
    assert params["line_items"][0]["price"] != price_id and "customer" not in params


def test_webhook_endpoint_verifies_grants_and_deduplicates(app, db):
    status, body = checkout({"product_id": "pack_2000"})
    order = orders.get_order(db.connect, body["order_id"])
    completed = event("checkout.session.completed", paid_session(order, payment_intent="pi_web"), event_id="evt_web_1")
    assert deliver(completed, secret="whsec_wrong")[0] == 400
    assert balance(db) == 50
    assert deliver(completed) == (200, {"ok": True, "outcome": "granted"})
    assert deliver(completed) == (200, {"ok": True, "outcome": "duplicate_event"})
    redelivered = dict(completed, id="evt_web_2")
    assert deliver(redelivered) == (200, {"ok": True, "outcome": "duplicate"})
    assert balance(db) == 50 + 2000
    assert any(e["event_type"] == "credits_added" for e in app.events)
    # Order status (the Website's success page polls this) reports it paid.
    status_body = body_of(run(main.public_store_order_status(FakeRequest({"telegram_id": UID, "order_id": order["order_id"]}))))[1]
    assert status_body["order"]["status"] == "paid" and status_body["order"]["provider"] == "stripe"


def test_webhook_endpoint_ignores_other_modes_and_retries_on_errors(app, db, monkeypatch):
    status, body = checkout({"product_id": "pack_500"})
    order = orders.get_order(db.connect, body["order_id"])
    live = event("checkout.session.completed", paid_session(order), event_id="evt_live", livemode=True)
    assert deliver(live) == (200, {"ok": True, "outcome": "ignored"})
    assert balance(db) == 50

    def boom(*args, **kwargs):
        raise RuntimeError("db down")

    monkeypatch.setattr(sb, "handle_event", boom)
    assert deliver(event("checkout.session.completed", paid_session(order), event_id="evt_err"))[0] == 500
    monkeypatch.undo()


def test_renewal_through_the_webhook_logs_and_grants(app, db):
    status, body = checkout({"product_id": "plan_pro_month"})
    order = orders.get_order(db.connect, body["order_id"])
    stripe_subscription(app.fake, "sub_web", order)
    now = int(time.time())
    assert deliver(event("invoice.paid", subscription_invoice("sub_web", "in_w1", 1000, "subscription_create", now, now + 30 * 86400)))[1]["outcome"] == "granted"
    assert deliver(event("invoice.paid", subscription_invoice("sub_web", "in_w2", 1000, "subscription_cycle", now + 30 * 86400, now + 60 * 86400)))[1]["outcome"] == "granted"
    assert balance(db) == 50 + 300 + 300
    assert any(e["event_type"] == "credits_added" and (e.get("payload") or {}).get("renewal") for e in app.events)


def test_portal_endpoint(app, db):
    assert body_of(run(main.public_stripe_portal(FakeRequest({"telegram_id": UID}))))[1]["error"] == "no_stripe_customer"
    sb.save_customer(db.connect, UID, "cus_portal", False)
    status, body = body_of(run(main.public_stripe_portal(FakeRequest({"telegram_id": UID}))))
    assert status == 200 and body["url"].startswith("https://billing.stripe.com/")
    assert body_of(run(main.public_stripe_portal(FakeRequest({"telegram_id": UID}, init_data="x"))))[0] == 403


def test_public_config_reports_stripe_without_secrets(app):
    config = run(main.public_config())
    assert config["stripe_enabled"] is True
    assert KEY not in json.dumps(config) and SECRET not in json.dumps(config)


def test_webhook_is_registered_as_an_unauthenticated_raw_body_route():
    from services.security import WEBHOOKS
    assert "/api/public/payments/stripe/webhook" in WEBHOOKS


def test_sync_script_is_idempotent_and_saves_the_mapping(db, monkeypatch, capsys, tmp_path):
    import importlib.util
    spec = importlib.util.spec_from_file_location("stripe_sync_products", os.path.join(os.path.dirname(__file__), "..", "scripts", "stripe_sync_products.py"))
    script = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(script)
    fake = FakeStripe()
    real_client = sb.StripeClient
    monkeypatch.setattr(script.stripe_billing, "StripeClient", lambda key: real_client(key, session=fake))
    monkeypatch.setenv("STRIPE_SECRET_KEY", KEY)
    monkeypatch.setenv("DATABASE_URL", DATABASE)
    monkeypatch.delenv("DATABASE_PUBLIC_URL", raising=False)
    output = tmp_path / "ids.json"
    assert script.main(["--output", str(output)]) == 0
    first = capsys.readouterr().out
    assert "created 18, replaced 0, reused 0" in first and "saved to stripe_catalog" in first
    assert script.main([]) == 0
    assert "created 0, replaced 0, reused 18" in capsys.readouterr().out
    assert len(fake.products) == 14 and len(fake.prices) == 18
    saved = json.loads(output.read_text())
    assert saved["livemode"] is False and saved["products"]["sylvex_plan_creator_year"]["unit_amount"] == 96000
    assert sb.catalog_complete(sb.load_catalog(db.connect, False))
    monkeypatch.delenv("STRIPE_SECRET_KEY")
    assert script.main([]) == 2


def test_account_merge_moves_stripe_links_without_conflicts(db):
    # account_identity's merge runs this UPDATE for every telegram_id column.
    sb.save_customer(db.connect, UID, "cus_web", False)
    sb.save_customer(db.connect, OTHER, "cus_tg", False)
    sb.upsert_subscription(db.connect, "sub_m", UID, "pro_month", None, "cus_web", "active")
    conn = db.connect()
    with conn.cursor() as cur:
        for table in ("stripe_customers", "stripe_subscriptions"):
            cur.execute(f"UPDATE {table} SET telegram_id = %s WHERE telegram_id = %s", (OTHER, UID))
    conn.commit()
    conn.close()
    assert sb.get_subscription(db.connect, "sub_m")["telegram_id"] == OTHER
    assert sb.get_customer(db.connect, OTHER, False) in {"cus_web", "cus_tg"}
    assert sb.get_customer(db.connect, UID, False) is None


def test_test_mode_only_refuses_a_live_key(app, monkeypatch):
    monkeypatch.setattr(main, "STRIPE_TEST_MODE_ONLY", True)
    assert main.stripe_enabled()  # the fixture's key is a test key
    monkeypatch.setattr(main, "STRIPE_SECRET_KEY", "sk_live_fake")
    assert not main.stripe_enabled() and not main.stripe_key_allowed()
    assert checkout({"product_id": "pack_500"})[1]["error"] == "stripe_not_configured"
    assert run(main.public_config())["stripe_enabled"] is False
    raw = json.dumps(event("invoice.paid", {"id": "in_1"})).encode()
    status, body = body_of(run(main.public_stripe_webhook(FakeRequest(raw=raw, headers={"stripe-signature": sign(raw, SECRET)}))))
    assert status == 503
    status, body = body_of(run(main.public_stripe_status()))
    assert body["key_refused"] is True and body["mode"] == "live" and body["enabled"] is False and body["catalog"] is None
    monkeypatch.setattr(main, "STRIPE_TEST_MODE_ONLY", False)
    assert main.stripe_key_allowed()


def test_status_endpoint_reports_sync_without_secrets(app):
    status, body = body_of(run(main.public_stripe_status()))
    assert body["enabled"] and body["mode"] == "test" and body["webhook_secret_configured"]
    assert body["catalog"] == {"complete": False, "products": 0, "prices": 0, "unavailable": 0}
    main.ensure_stripe_catalog()
    body = body_of(run(main.public_stripe_status()))[1]
    assert body["catalog"] == {"complete": True, "products": 14, "prices": 18, "unavailable": 0}
    assert KEY not in json.dumps(body) and SECRET not in json.dumps(body)
    from services.security import PUBLIC_GETS
    assert "/api/public/payments/stripe/status" in PUBLIC_GETS


def test_test_clocks_attach_new_customers_in_test_mode_only(app, db, monkeypatch):
    monkeypatch.setattr(main, "STRIPE_TEST_CLOCKS", True)
    assert checkout({"product_id": "plan_starter_month"})[0] == 200
    customer = sb.get_customer(db.connect, UID, False)
    assert app.fake.customers[customer]["test_clock"] in app.fake.test_clocks
    assert list(app.fake.sessions.values())[-1]["params"]["customer"] == customer
    # Reused afterwards: no second clock for the same user.
    assert checkout({"product_id": "pack_500"})[0] == 200
    assert len(app.fake.test_clocks) == 1
    assert body_of(run(main.public_stripe_status()))[1]["test_clocks"] is True
    # Never with a live key.
    live = FakeStripe(livemode=True)
    monkeypatch.setattr(main, "_STRIPE_STATE", {"client": sb.StripeClient("sk_live_fake", session=live), "tables": True, "catalog": None})
    monkeypatch.setattr(main, "STRIPE_SECRET_KEY", "sk_live_fake")
    status, body = body_of(run(main.public_stripe_checkout(FakeRequest({"telegram_id": OTHER, "product_id": "pack_500"}))))
    assert status == 200 and not getattr(live, "test_clocks", None)


def test_test_mode_records_never_affect_live_mode(db):
    # Simulates the temporary Test Mode verification on production data:
    # a test subscription, customer and catalog stay invisible to live mode.
    sb.upsert_subscription(db.connect, "sub_test_1", UID, "pro_month", None, "cus_test", "active", livemode=False)
    sb.save_customer(db.connect, UID, "cus_test", False)
    sb.save_catalog(db.connect, sb.sync_catalog(client_for(FakeStripe())), False)
    assert sb.has_live_subscription(db.connect, UID, False)
    assert not sb.has_live_subscription(db.connect, UID, True)
    assert sb.get_customer(db.connect, UID, True) is None
    assert sb.load_catalog(db.connect, True) == {}
    conn = db.connect()
    with conn.cursor() as cur:
        cur.execute("INSERT INTO subscriptions (telegram_id, subscription_type, payment_method, expires_at, status, charge_id) "
                    "VALUES (%s, 'pro_month', 'stripe', NOW() + INTERVAL '5 days', 'active', 'in_test_1')", (UID,))
    conn.commit()
    conn.close()
    count = "SELECT COUNT(*) FROM subscriptions s WHERE " 
    assert db.query(count + sb.renews_automatically_sql("s", False)) == [(1,)]
    assert db.query(count + sb.renews_automatically_sql("s", True)) == [(0,)]  # live reminders unaffected
