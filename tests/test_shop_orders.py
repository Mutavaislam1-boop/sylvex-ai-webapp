"""Store purchase orders against a real PostgreSQL ledger.

Covers every subscription variant, every fixed credit package and custom
amounts through Telegram Stars and Crypto Pay: the authoritative grant,
duplicate callbacks, amount/payer/provider mismatches, expired orders and
rollback on failure. Runs only against a disposable database given by
SYLVEX_TEST_DATABASE_URL (skipped otherwise)."""
import os
import time
from datetime import datetime, timedelta

import pytest

from services import shop_catalog as catalog
from services import shop_orders as orders
from services import telegram_catalog as tg

DATABASE = os.getenv("SYLVEX_TEST_DATABASE_URL")
UID = 777001


@pytest.fixture
def connect():
    if not DATABASE:
        pytest.skip("Set SYLVEX_TEST_DATABASE_URL to a disposable PostgreSQL database")
    import psycopg2

    def factory():
        return psycopg2.connect(DATABASE)

    conn = factory()
    with conn.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS subscription_payments, shop_orders, purchases, subscriptions, users CASCADE")
        # Same shape as production (main.py ensure_payment_tables + users).
        cur.execute("CREATE TABLE users (telegram_id BIGINT PRIMARY KEY, first_name TEXT, balance INTEGER DEFAULT 0, subscription TEXT DEFAULT 'free')")
        cur.execute("""CREATE TABLE purchases (id SERIAL PRIMARY KEY, telegram_id BIGINT NOT NULL, provider TEXT NOT NULL, credits INTEGER DEFAULT 0,
                       amount INTEGER DEFAULT 0, currency TEXT DEFAULT 'USD', payload TEXT, charge_id TEXT UNIQUE, status TEXT DEFAULT 'completed',
                       created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
        cur.execute("""CREATE TABLE subscriptions (id SERIAL PRIMARY KEY, telegram_id BIGINT NOT NULL, subscription_type TEXT, payment_method TEXT,
                       amount INTEGER DEFAULT 0, currency TEXT DEFAULT 'USD', starts_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, expires_at TIMESTAMP,
                       status TEXT DEFAULT 'active', charge_id TEXT UNIQUE, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
        cur.execute("INSERT INTO users (telegram_id, first_name, balance) VALUES (%s, 'Buyer', 50)", (UID,))
    conn.commit()
    conn.close()
    orders.ensure_order_tables(factory)
    return factory


def q(connect, sql, params=()):
    conn = connect()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchall()
    finally:
        conn.close()


def balance(connect):
    return q(connect, "SELECT balance FROM users WHERE telegram_id = %s", (UID,))[0][0]


def stars_product(product_id, credits=None):
    """A Telegram catalog product as Stars orders snapshot it (ledger tests
    pay it directly, independent of the invoice limit)."""
    if product_id == tg.CUSTOM_PRODUCT_ID:
        return tg._credits_product(tg.parse_custom_credits(credits), tg.CUSTOM_PRODUCT_ID)
    return dict(tg.PRODUCTS[product_id])


def pay(connect, product, provider, charge_id, ttl=1800):
    order = orders.create_order(connect, UID, product, provider, ttl)
    if provider == catalog.PROVIDER_STARS:
        ok, reason = orders.checkout_check(connect, order["order_id"], UID, provider, "XTR", product["stars"])
        assert ok, reason
        # Monthly plans are Telegram Stars subscriptions: their first payment
        # carries Telegram's subscription fields.
        recurring = ({"is_recurring": True, "is_first_recurring": True,
                      "subscription_expiration_date": int(time.time()) + 30 * 86400}
                     if product.get("recurring") else None)
        result = orders.finalize_order(connect, order["order_id"], provider, "XTR", product["stars"], charge_id, payer_id=UID,
                                       recurring=recurring)
    else:
        result = orders.finalize_order(connect, order["order_id"], provider, "USDT", f"{product['usd_cents'] / 100:.2f}", charge_id)
    return order, result


PLAN_TABLE = {
    "starter": (5, 48, 100, 1200), "pro": (10, 96, 300, 3600), "max": (25, 240, 1000, 12000),
    "ultra": (50, 480, 2500, 30000), "creator": (100, 960, 5500, 66000),
}


def test_catalog_matches_the_approved_price_table():
    for plan_id, (monthly, annual, month_credits, year_credits) in PLAN_TABLE.items():
        month = catalog.resolve_product(f"plan_{plan_id}_month")
        year = catalog.resolve_product(f"plan_{plan_id}_year")
        assert (month["usd_cents"], month["credits"], month["days"], month["plan_key"]) == (monthly * 100, month_credits, 30, f"{plan_id}_month")
        assert (year["usd_cents"], year["credits"], year["days"], year["plan_key"]) == (annual * 100, year_credits, 365, f"{plan_id}_year")
    for usd in (5, 10, 20, 30, 40, 50, 100, 200):
        pack = catalog.resolve_product(f"pack_{usd * 100}")
        assert (pack["usd_cents"], pack["credits"], pack["kind"]) == (usd * 100, usd * 100, "credits")


STARS_TABLE = {
    # Telegram catalog: stars = ceil(usd * 499 / 5)
    "pack_100": 100, "pack_500": 499, "pack_1000": 998, "pack_2000": 1996, "pack_3000": 2994, "pack_4000": 3992,
    "pack_5000": 4990, "pack_10000": 9980, "pack_20000": 19960,
    "plan_starter_month": 499, "plan_starter_year": 4791, "plan_pro_month": 998, "plan_pro_year": 9581,
    "plan_max_month": 2495, "plan_max_year": 23952, "plan_ultra_month": 4990, "plan_ultra_year": 47904,
    "plan_creator_month": 9980, "plan_creator_year": 95808,
}


def test_telegram_catalog_prices_follow_the_499_per_5_usd_table():
    import main
    assert {pid: p["stars"] for pid, p in tg.PRODUCTS.items()} == STARS_TABLE
    for plan_id, (_m, _a, month_credits, year_credits) in PLAN_TABLE.items():
        assert tg.PRODUCTS[f"plan_{plan_id}_month"]["credits"] == month_credits
        assert tg.PRODUCTS[f"plan_{plan_id}_year"]["credits"] == year_credits
        assert (tg.PRODUCTS[f"plan_{plan_id}_month"]["days"], tg.PRODUCTS[f"plan_{plan_id}_year"]["days"]) == (30, 365)
    # Legacy items finishing old invoices use the same formula.
    assert {k: main.SHOP_ITEMS[k]["stars"] for k in ("sub_month", "sub_year", "pack_100", "pack_500")} == \
        {"sub_month": 499, "sub_year": 5889, "pack_100": 100, "pack_500": 499}
    # Rounding is always up: 1,234 credits = $12.34 -> 1231.53 -> 1232 Stars.
    assert tg.stars_for_cents(1234) == 1232 and tg.stars_for_cents(1) == 1 and tg.stars_for_cents(100000) == 99800
    for cents in range(1, 100001, 7):
        assert tg.stars_for_cents(cents) == -(-cents * 499 // 500)
    limit = tg.max_cents_for_stars(10000)
    assert tg.stars_for_cents(limit) <= 10000 < tg.stars_for_cents(limit + 1)
    # The Website/Stripe catalog carries no Stars prices at all.
    assert not any("stars" in product for product in catalog.FIXED_PRODUCTS.values())


@pytest.mark.parametrize("plan_id", list(PLAN_TABLE))
@pytest.mark.parametrize("period", ["month", "year"])
def test_every_subscription_variant_grants_its_credits_once(connect, plan_id, period):
    product = stars_product(f"plan_{plan_id}_{period}")
    provider = catalog.PROVIDER_STARS
    before = balance(connect)
    order, result = pay(connect, product, provider, f"charge-{plan_id}-{period}")
    assert result["status"] == "granted"
    expected_credits = PLAN_TABLE[plan_id][2] if period == "month" else PLAN_TABLE[plan_id][3]
    assert balance(connect) == before + expected_credits
    sub = q(connect, "SELECT subscription_type, status, expires_at FROM subscriptions WHERE telegram_id = %s", (UID,))
    assert len(sub) == 1 and sub[0][0] == f"{plan_id}_{period}" and sub[0][1] == "active"
    days = 30 if period == "month" else 365
    assert abs((sub[0][2] - datetime.now()) - timedelta(days=days)) < timedelta(minutes=5)
    assert q(connect, "SELECT subscription FROM users WHERE telegram_id = %s", (UID,))[0][0] == f"{plan_id}_{period}"
    # A repeated callback for the same payment changes nothing.
    again = orders.finalize_order(connect, order["order_id"], provider, "XTR" if provider == catalog.PROVIDER_STARS else "USDT",
                                  product["stars"] if provider == catalog.PROVIDER_STARS else f"{product['usd_cents'] / 100:.2f}",
                                  f"charge-{plan_id}-{period}", payer_id=UID if provider == catalog.PROVIDER_STARS else None)
    assert again["status"] == "duplicate"
    assert balance(connect) == before + expected_credits
    assert q(connect, "SELECT COUNT(*) FROM purchases")[0][0] == 1


# Verified with createInvoiceLink on the SYLVEX bot (invoice creation only,
# no payment completed): one-time 10,000 / 19,960 / 23,952 / 95,808 Stars
# accepted; recurring 30-day 10,000 accepted, 10,001 rejected.
@pytest.mark.parametrize("stars", [10000, 19960, 23952, 95808])
def test_verified_one_time_amounts_are_allowed(stars):
    assert tg.STARS_MAX_PER_INVOICE == 95808
    assert tg.check_invoice_amount(stars) == stars
    # The recurring-subscription cap is not applied to one-time invoices.
    if stars > tg.STARS_MAX_PER_SUBSCRIPTION:
        with pytest.raises(tg.CatalogError) as err:
            tg.check_invoice_amount(stars, tg.SUBSCRIPTION_PERIOD_SECONDS)
        assert err.value.code == "subscription_amount_above_limit"


def test_recurring_subscription_amounts_keep_the_10000_cap():
    assert (tg.STARS_MAX_PER_SUBSCRIPTION, tg.SUBSCRIPTION_PERIOD_SECONDS) == (10000, 2592000)
    assert tg.check_invoice_amount(10000, 2592000) == 10000
    for stars, period, code in ((10001, 2592000, "subscription_amount_above_limit"),
                                (499, 31536000, "unsupported_subscription_period"),
                                (0, 2592000, "invalid_amount")):
        with pytest.raises(tg.CatalogError) as err:
            tg.check_invoice_amount(stars, period)
        assert err.value.code == code
    for bad in (0, -1, 1.5, "100", True):
        with pytest.raises(tg.CatalogError):
            tg.check_invoice_amount(bad)


def test_every_telegram_product_is_sold_within_the_verified_one_time_amounts():
    for product_id, stars in STARS_TABLE.items():
        assert tg.resolve(product_id)["stars"] == stars
        assert tg.check_invoice_amount(stars) == stars
    # Only the monthly plans renew (30-day Telegram Stars subscriptions).
    recurring = {pid for pid, p in tg.PRODUCTS.items() if p["recurring"]}
    assert recurring == {f"plan_{plan}_month" for plan in PLAN_TABLE}
    assert all(tg.PRODUCTS[pid]["subscription_period"] == 2592000 for pid in recurring)
    assert all(p["subscription_period"] is None for pid, p in tg.PRODUCTS.items() if pid not in recurring)
    assert tg.public_catalog()["renewal"] == {"month": "auto_30_days", "year": "none", "credits": "none"}


def test_a_lower_one_time_limit_makes_products_unavailable_never_cheaper(monkeypatch):
    monkeypatch.setattr(tg, "STARS_MAX_PER_INVOICE", 10000)
    for product_id in ("plan_max_year", "plan_ultra_year", "plan_creator_year", "pack_20000"):
        with pytest.raises(tg.CatalogError) as err:
            tg.resolve(product_id)
        assert err.value.code == "stars_amount_above_limit"
    assert tg.pack_stars(20000) is None and tg.custom_max_credits() == 10020
    # Prices are never changed to fit the limit.
    assert tg.PRODUCTS["plan_creator_year"]["stars"] == 95808


@pytest.mark.parametrize("credits", [100, 500, 1000, 2000, 3000, 4000, 5000, 10000, 20000])
def test_every_telegram_credit_package_grants_once(connect, credits):
    product = stars_product(f"pack_{credits}")
    before = balance(connect)
    order, result = pay(connect, product, catalog.PROVIDER_STARS, f"pack-{credits}")
    assert result["status"] == "granted" and balance(connect) == before + credits
    row = q(connect, "SELECT provider, credits, amount, currency FROM purchases")[0]
    assert row == (catalog.PROVIDER_STARS, credits, STARS_TABLE[f"pack_{credits}"], "XTR")
    again = orders.finalize_order(connect, order["order_id"], catalog.PROVIDER_STARS, "XTR", product["stars"], f"pack-{credits}", payer_id=UID)
    assert again["status"] == "duplicate" and balance(connect) == before + credits


@pytest.mark.parametrize("usd", [5, 10, 20, 30, 40, 50, 100, 200])
def test_every_website_credit_package_through_crypto(connect, usd):
    # Crypto stays a Website-side USD method (refused for Telegram requests).
    provider = catalog.PROVIDER_CRYPTO
    product = catalog.resolve_product(f"pack_{usd * 100}")
    assert catalog.provider_availability(product)[provider]["available"]
    before = balance(connect)
    _, result = pay(connect, product, provider, f"pack-{usd}-{provider}")
    assert result["status"] == "granted"
    assert balance(connect) == before + usd * 100
    row = q(connect, "SELECT provider, credits, amount, currency, payload FROM purchases")[0]
    assert row[0] == provider and row[1] == usd * 100
    assert row[2] == usd * 100
    assert row[4].startswith("sylvex_order:")
    assert q(connect, "SELECT COUNT(*) FROM subscriptions")[0][0] == 0


@pytest.mark.parametrize("raw,cents", [("1", 100), ("1.00", 100), ("1000", 100000), ("12,5", 1250), (" 37.25 ", 3725)])
def test_custom_amount_bounds_accept(raw, cents):
    product = catalog.resolve_product(catalog.CUSTOM_PRODUCT_ID, raw)
    assert product["usd_cents"] == cents and product["credits"] == cents


@pytest.mark.parametrize("raw,code", [("", "amount_required"), ("0.99", "amount_out_of_range"), ("1000.01", "amount_out_of_range"),
                                      ("12.345", "invalid_amount"), ("-5", "invalid_amount"), ("abc", "invalid_amount"), ("1e3", "invalid_amount")])
def test_custom_amount_bounds_reject(raw, code):
    with pytest.raises(catalog.CatalogError) as err:
        catalog.resolve_product(catalog.CUSTOM_PRODUCT_ID, raw)
    assert err.value.code == code


def test_custom_amount_stars_ceiling_and_crypto_range():
    # Telegram: whole credits, within the one-time limit (96,000 credits = 95,808 Stars).
    assert tg.custom_max_credits() == 96000 and tg.public_catalog()["custom"]["max_credits"] == 96000
    assert tg.resolve(tg.CUSTOM_PRODUCT_ID, "96000")["stars"] == 95808
    assert tg.resolve(tg.CUSTOM_PRODUCT_ID, "10020")["stars"] == 10000
    assert tg.resolve(tg.CUSTOM_PRODUCT_ID, "100")["stars"] == 100
    for raw, code in (("96001", "stars_amount_above_limit"), ("99", "amount_out_of_range"), ("12.5", "invalid_amount"),
                      ("", "amount_required"), ("-5", "invalid_amount"), ("100001", "amount_out_of_range")):
        with pytest.raises(tg.CatalogError) as err:
            tg.resolve(tg.CUSTOM_PRODUCT_ID, raw)
        assert err.value.code == code, raw
    # Website (USD) custom amounts are unchanged.
    for raw in ("1", "1000"):
        product = catalog.resolve_product(catalog.CUSTOM_PRODUCT_ID, raw)
        assert catalog.provider_availability(product)[catalog.PROVIDER_CRYPTO]["available"]


@pytest.mark.parametrize("raw,provider", [("100", catalog.PROVIDER_STARS), ("10020", catalog.PROVIDER_STARS), ("1234", catalog.PROVIDER_STARS),
                                          ("1", catalog.PROVIDER_CRYPTO), ("1000", catalog.PROVIDER_CRYPTO), ("12.34", catalog.PROVIDER_CRYPTO)])
def test_custom_purchases_grant_the_server_computed_credits(connect, raw, provider):
    product = (stars_product(tg.CUSTOM_PRODUCT_ID, raw) if provider == catalog.PROVIDER_STARS
               else catalog.resolve_product(catalog.CUSTOM_PRODUCT_ID, raw))
    before = balance(connect)
    _, result = pay(connect, product, provider, f"custom-{raw}-{provider}")
    assert result["status"] == "granted"
    assert balance(connect) == before + product["usd_cents"]


def test_amount_currency_payer_and_provider_mismatches_grant_nothing(connect):
    product = stars_product("pack_1000")
    order = orders.create_order(connect, UID, product, catalog.PROVIDER_STARS, 1800)
    oid = order["order_id"]
    # 460 was the old 46-Stars-per-dollar price: a stale price is refused too.
    for stale_or_wrong in (997, 999, 460):
        assert orders.checkout_check(connect, oid, UID, catalog.PROVIDER_STARS, "XTR", stale_or_wrong) == (False, "amount_mismatch")
    assert orders.checkout_check(connect, oid, UID, catalog.PROVIDER_STARS, "USD", 998) == (False, "amount_mismatch")
    assert orders.checkout_check(connect, oid, UID + 1, catalog.PROVIDER_STARS, "XTR", 998) == (False, "payer_mismatch")
    assert orders.checkout_check(connect, oid, UID, catalog.PROVIDER_CRYPTO, "XTR", 998) == (False, "provider_mismatch")
    assert orders.checkout_check(connect, "0" * 32, UID, catalog.PROVIDER_STARS, "XTR", 998) == (False, "order_not_found")
    for kwargs in ({"amount": 1}, {"currency": "USD"}, {"payer_id": UID + 1}, {"provider": catalog.PROVIDER_CRYPTO}):
        args = {"provider": catalog.PROVIDER_STARS, "currency": "XTR", "amount": 998, "payer_id": UID, **kwargs}
        result = orders.finalize_order(connect, oid, args["provider"], args["currency"], args["amount"], "bad-charge", payer_id=args["payer_id"])
        assert result["status"] == "rejected"
    assert balance(connect) == 50
    assert q(connect, "SELECT COUNT(*) FROM purchases")[0][0] == 0
    assert orders.get_order(connect, oid)["status"] == "pending"


def test_crypto_amount_must_match_the_order(connect):
    product = catalog.resolve_product("pack_2000")
    order = orders.create_order(connect, UID, product, catalog.PROVIDER_CRYPTO, 1800)
    for amount, asset in (("19.99", "USDT"), ("20.00", "TON"), ("not-a-number", "USDT")):
        assert orders.finalize_order(connect, order["order_id"], catalog.PROVIDER_CRYPTO, asset, amount, "c1")["status"] == "rejected"
    assert orders.finalize_order(connect, order["order_id"], catalog.PROVIDER_CRYPTO, "USDT", "20", "c1")["status"] == "granted"
    assert balance(connect) == 50 + 2000


def test_second_payment_for_a_paid_order_is_rejected_and_checkout_closes(connect):
    product = stars_product("pack_500")
    order, first = pay(connect, product, catalog.PROVIDER_STARS, "first")
    assert first["status"] == "granted"
    assert orders.checkout_check(connect, order["order_id"], UID, catalog.PROVIDER_STARS, "XTR", 499) == (False, "order_not_pending")
    second = orders.finalize_order(connect, order["order_id"], catalog.PROVIDER_STARS, "XTR", 499, "second", payer_id=UID)
    assert second["status"] == "rejected" and second["reason"] == "order_already_paid"
    assert balance(connect) == 50 + 500


def test_charge_id_reused_across_orders_never_double_grants(connect):
    product = stars_product("pack_500")
    _, first = pay(connect, product, catalog.PROVIDER_STARS, "same-charge")
    _, second = pay(connect, product, catalog.PROVIDER_STARS, "same-charge")
    assert first["status"] == "granted" and second["status"] == "duplicate"
    assert balance(connect) == 50 + 500


def test_expired_order_cannot_start_checkout_but_a_completed_payment_is_honored(connect):
    product = stars_product("pack_1000")
    order = orders.create_order(connect, UID, product, catalog.PROVIDER_STARS, -1)
    assert orders.checkout_check(connect, order["order_id"], UID, catalog.PROVIDER_STARS, "XTR", 998) == (False, "order_expired")
    assert orders.mark_order(connect, order["order_id"], orders.STATUS_EXPIRED, "invoice_expired")
    result = orders.finalize_order(connect, order["order_id"], catalog.PROVIDER_STARS, "XTR", 998, "late", payer_id=UID)
    assert result["status"] == "granted"
    assert balance(connect) == 50 + 1000
    assert not orders.mark_order(connect, order["order_id"], orders.STATUS_FAILED)
    assert orders.get_order(connect, order["order_id"])["status"] == "paid"


def test_failed_or_cancelled_attempts_leave_no_trace(connect):
    product = catalog.resolve_product("plan_pro_month")
    order = orders.create_order(connect, UID, product, catalog.PROVIDER_CRYPTO, 1800)
    assert orders.mark_order(connect, order["order_id"], orders.STATUS_FAILED, "cancelled")
    result = orders.finalize_order(connect, order["order_id"], catalog.PROVIDER_CRYPTO, "USDT", "10.00", "after-fail")
    assert result["status"] == "rejected" and result["reason"] == "order_not_payable"
    assert balance(connect) == 50
    assert q(connect, "SELECT COUNT(*) FROM subscriptions")[0][0] == 0


def test_a_failure_mid_grant_rolls_everything_back(connect):
    product = stars_product("plan_pro_month")
    order = orders.create_order(connect, UID, product, catalog.PROVIDER_STARS, 1800)
    conn = connect()
    with conn.cursor() as cur:
        cur.execute("UPDATE shop_orders SET days = NULL WHERE order_id = %s", (order["order_id"],))
    conn.commit()
    conn.close()
    with pytest.raises(Exception):
        orders.finalize_order(connect, order["order_id"], catalog.PROVIDER_STARS, "XTR", product["stars"], "boom", payer_id=UID)
    assert balance(connect) == 50
    assert q(connect, "SELECT COUNT(*) FROM purchases")[0][0] == 0
    assert orders.get_order(connect, order["order_id"])["status"] == "pending"


def test_new_one_time_plan_keeps_the_remaining_time_of_an_active_subscription(connect):
    # An existing (e.g. legacy yearly) subscription is not migrated or
    # shortened: a one-time (annual) plan bought on top extends from its expiry.
    conn = connect()
    with conn.cursor() as cur:
        cur.execute("""INSERT INTO subscriptions (telegram_id, subscription_type, payment_method, expires_at, status, charge_id)
                       VALUES (%s, 'year', 'telegram_stars', CURRENT_TIMESTAMP + INTERVAL '100 days', 'active', 'legacy')""", (UID,))
    conn.commit()
    conn.close()
    _, result = pay(connect, stars_product("plan_starter_year"), catalog.PROVIDER_STARS, "stack")
    assert result["status"] == "granted"
    active = q(connect, "SELECT subscription_type, expires_at FROM subscriptions WHERE status = 'active'")
    assert len(active) == 1 and active[0][0] == "starter_year"
    assert abs((active[0][1] - datetime.now()) - timedelta(days=465)) < timedelta(minutes=5)
    assert q(connect, "SELECT status FROM subscriptions WHERE charge_id = 'legacy'")[0][0] == "cancelled"


def test_order_payload_parsing_is_strict():
    oid = "a" * 32
    assert orders.parse_order_payload(orders.order_payload(oid)) == oid
    for bad in ("sylvex_order:", "sylvex_order:" + "A" * 32, "sylvex_order:" + "a" * 31, "sylvex_stars:1:500:230", None, "sylvex_order:" + "a" * 32 + ":x"):
        assert orders.parse_order_payload(bad) is None
    assert len(orders.order_payload(oid).encode()) <= 128  # Telegram invoice payload limit

