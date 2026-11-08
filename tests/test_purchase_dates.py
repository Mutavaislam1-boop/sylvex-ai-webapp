"""SX-010: every confirmed purchase keeps the moment it was recorded.

Production may hold either purchases schema: the API's (created_at TIMESTAMP
DEFAULT CURRENT_TIMESTAMP) or the bot's (created_at TEXT, no default). Each
writer sets created_at itself, a repeated delivery keeps the first date and
grants nothing, and the history lists rows recorded without a date only in
the 1Y view, as their own group outside the charts and totals. Real SQL needs
a disposable PostgreSQL in SYLVEX_TEST_DATABASE_URL (skipped otherwise)."""
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from services import account_usage
from services import billing_safety
from services import shop_catalog as catalog
from services import shop_orders as orders
from services import stripe_billing

DATABASE = os.getenv("SYLVEX_TEST_DATABASE_URL")
UID = 880011
SCHEMAS = {
    "api_timestamp_default": "created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
    "bot_text_no_default": "created_at TEXT",
}


@pytest.fixture(params=sorted(SCHEMAS))
def connect(request):
    if not DATABASE:
        pytest.skip("Set SYLVEX_TEST_DATABASE_URL to a disposable PostgreSQL database")
    import psycopg2

    def factory():
        return psycopg2.connect(DATABASE)

    conn = factory()
    with conn.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS payment_inbox, payment_reconcile_state, subscription_events, subscription_agreements, "
                    "subscription_payments, shop_orders, purchases, subscriptions, user_credit_wallets, generation_charges, users CASCADE")
        cur.execute("CREATE TABLE users (telegram_id BIGINT PRIMARY KEY, first_name TEXT, balance INTEGER DEFAULT 0, subscription TEXT DEFAULT 'free')")
        cur.execute(f"""CREATE TABLE purchases (id SERIAL PRIMARY KEY, telegram_id BIGINT NOT NULL, provider TEXT NOT NULL,
                        credits INTEGER DEFAULT 0, amount INTEGER DEFAULT 0, currency TEXT DEFAULT 'USD', payload TEXT,
                        charge_id TEXT UNIQUE, status TEXT DEFAULT 'completed', {SCHEMAS[request.param]})""")
        cur.execute("""CREATE TABLE subscriptions (id SERIAL PRIMARY KEY, telegram_id BIGINT NOT NULL, subscription_type TEXT, payment_method TEXT,
                       amount INTEGER DEFAULT 0, currency TEXT DEFAULT 'USD', starts_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, expires_at TIMESTAMP,
                       status TEXT DEFAULT 'active', charge_id TEXT UNIQUE, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
        cur.execute("""CREATE TABLE generation_charges (id SERIAL PRIMARY KEY, generation_id TEXT UNIQUE, telegram_id BIGINT, mode TEXT,
                       model TEXT, provider TEXT, credits INTEGER, balance_after INTEGER, created_at TIMESTAMPTZ DEFAULT NOW())""")
        cur.execute("""CREATE TABLE user_credit_wallets (telegram_id BIGINT PRIMARY KEY REFERENCES users(telegram_id) ON DELETE CASCADE,
                       purchased_credits INTEGER NOT NULL DEFAULT 0 CHECK (purchased_credits >= 0),
                       subscription_credits INTEGER NOT NULL DEFAULT 0 CHECK (subscription_credits >= 0),
                       subscription_expires_at TIMESTAMPTZ, updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW())""")
        cur.execute("INSERT INTO users (telegram_id, first_name, balance) VALUES (%s, 'Buyer', 0)", (UID,))
    conn.commit()
    conn.close()
    orders.ensure_order_tables(factory)
    factory.schema = request.param
    return factory


def q(connect, sql, params=()):
    conn = connect()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchall()
    finally:
        conn.close()


def recorded(connect, charge_id):
    rows = q(connect, "SELECT NULLIF(created_at::text, '')::timestamptz FROM purchases WHERE charge_id = %s", (charge_id,))
    assert len(rows) == 1
    return rows[0][0]


def balance(connect):
    return q(connect, "SELECT balance FROM users WHERE telegram_id = %s", (UID,))[0][0]


def assert_recent(stamp):
    assert stamp is not None, "purchase recorded without a date"
    assert abs((datetime.now(timezone.utc) - stamp).total_seconds()) < 120


def age(connect, charge_id):
    """Push a recorded date into the past, so a retry provably keeps it."""
    q_exec(connect, "UPDATE purchases SET created_at = created_at::timestamptz - INTERVAL '3 days' WHERE charge_id = %s", (charge_id,))
    return recorded(connect, charge_id)


def q_exec(connect, sql, params=()):
    conn = connect()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params)
        conn.commit()
    finally:
        conn.close()


def test_every_writer_names_created_at():
    root = Path(__file__).resolve().parents[1]
    sources = [p for p in root.rglob("*.py") if "tests" not in p.parts and ".venv" not in p.parts]
    inserts = []
    for path in sources:
        text = path.read_text(encoding="utf-8", errors="ignore")
        for match in re.finditer(r"INSERT INTO purchases\s*\(([^)]*)\)", text):
            inserts.append((path.name, match.group(1)))
    assert {name for name, _ in inserts} >= {"main.py", "billing_safety.py", "shop_orders.py", "stripe_billing.py"}
    assert all("created_at" in columns for _, columns in inserts), inserts


def test_shop_order_payment_is_dated_and_a_retry_keeps_the_date_and_grants_once(connect):
    product = catalog.resolve_product("pack_500")
    order = orders.create_order(connect, UID, product, catalog.PROVIDER_STRIPE, 1800)
    first = orders.finalize_order(connect, order["order_id"], catalog.PROVIDER_STRIPE, "USD", product["usd_cents"], "pi_sx010_1")
    assert first["status"] == "granted"
    assert_recent(recorded(connect, "pi_sx010_1"))
    stamp, credits = age(connect, "pi_sx010_1"), balance(connect)
    again = orders.finalize_order(connect, order["order_id"], catalog.PROVIDER_STRIPE, "USD", product["usd_cents"], "pi_sx010_1")
    assert again["status"] != "granted"
    assert recorded(connect, "pi_sx010_1") == stamp and balance(connect) == credits


def test_apply_payment_is_dated_and_a_retry_keeps_the_date_and_grants_once(connect):
    item = {"kind": "credits", "credits": 300}
    assert billing_safety.apply_payment(connect, UID, "telegram_stars", item, 300, "XTR", "pack", "stars_sx010_1") is True
    assert_recent(recorded(connect, "stars_sx010_1"))
    stamp, credits = age(connect, "stars_sx010_1"), balance(connect)
    assert billing_safety.apply_payment(connect, UID, "telegram_stars", item, 300, "XTR", "pack", "stars_sx010_1") is False
    assert recorded(connect, "stars_sx010_1") == stamp and balance(connect) == credits


def test_stripe_renewal_is_dated_and_a_redelivery_keeps_the_date_and_grants_once(connect):
    product = catalog.resolve_product("plan_starter_month")
    link = {"telegram_id": UID, "plan_key": "starter_month"}
    now = int(datetime.now(timezone.utc).timestamp())
    first = stripe_billing.grant_renewal(connect, link, "in_sx010_1", product["usd_cents"], "usd", now, now + 30 * 86400)
    assert first["status"] == "granted"
    assert_recent(recorded(connect, "in_sx010_1"))
    stamp, credits = age(connect, "in_sx010_1"), balance(connect)
    again = stripe_billing.grant_renewal(connect, link, "in_sx010_1", product["usd_cents"], "usd", now, now + 30 * 86400)
    assert again["status"] == "duplicate"
    assert recorded(connect, "in_sx010_1") == stamp and balance(connect) == credits


def test_create_purchase_once_is_dated_and_a_retry_keeps_the_date(connect, monkeypatch):
    import main
    from urllib.parse import urlparse  # noqa: F401  (DATABASE is a libpq URL)
    monkeypatch.setattr(main, "DATABASE_URL", DATABASE)
    monkeypatch.setattr(main, "db_connect", lambda _url: connect())
    monkeypatch.setattr(main, "ensure_payment_tables", lambda: None)
    assert main.create_purchase_once(UID, "crypto", 100, 500, "USD", "legacy", "legacy_sx010_1") is True
    assert_recent(recorded(connect, "legacy_sx010_1"))
    stamp = age(connect, "legacy_sx010_1")
    assert main.create_purchase_once(UID, "crypto", 100, 500, "USD", "legacy", "legacy_sx010_1") is False
    assert recorded(connect, "legacy_sx010_1") == stamp


def seed_history(connect):
    """A dated purchase today, one 40 days ago and two legacy rows without a date
    (NULL and, on the TEXT schema, an empty string)."""
    item = {"kind": "credits", "credits": 300}
    billing_safety.apply_payment(connect, UID, "telegram_stars", item, 300, "XTR", "pack", "stars_today")
    billing_safety.apply_payment(connect, UID, "telegram_stars", {"kind": "credits", "credits": 200}, 200, "XTR", "pack", "stars_old")
    q_exec(connect, "UPDATE purchases SET created_at = created_at::timestamptz - INTERVAL '40 days' WHERE charge_id = 'stars_old'")
    q_exec(connect, "INSERT INTO purchases (telegram_id, provider, credits, amount, currency, payload, charge_id, status, created_at) "
                    "VALUES (%s, 'telegram_stars', 70, 70, 'XTR', 'legacy', 'legacy_null', 'completed', NULL)", (UID,))
    empty = "''" if connect.schema == "bot_text_no_default" else "NULL"
    q_exec(connect, "INSERT INTO purchases (telegram_id, provider, credits, amount, currency, payload, charge_id, status, created_at) "
                    f"VALUES (%s, 'telegram_stars', 30, 30, 'XTR', 'legacy', 'legacy_empty', 'completed', {empty})", (UID,))
    q_exec(connect, "INSERT INTO purchases (telegram_id, provider, credits, amount, currency, payload, charge_id, status, created_at) "
                    "VALUES (%s, 'telegram_stars', 999, 999, 'XTR', 'legacy', 'legacy_refunded', 'refunded', NULL)", (UID,))


def test_history_30d_lists_dated_purchases_only(connect):
    seed_history(connect)
    data = account_usage.load_usage_snapshot(connect, UID, "30d")
    assert [p["credits"] for p in data["payments"]] == [300]
    assert data["undated_payments"] == [] and data["summary"]["undated_payments"] == 0
    assert data["summary"]["added_credits"] == 300


def test_history_365d_adds_an_undated_group_outside_charts_and_totals(connect):
    seed_history(connect)
    data = account_usage.load_usage_snapshot(connect, UID, "365d")
    assert sorted(p["credits"] for p in data["payments"]) == [200, 300]
    assert all(p["created_at"] for p in data["payments"])
    undated = data["undated_payments"]
    assert sorted(p["credits"] for p in undated) == [30, 70]  # the refunded row stays out
    assert all(p["created_at"] is None for p in undated)
    assert data["summary"]["payments"] == 2 and data["summary"]["undated_payments"] == 2
    assert data["summary"]["added_credits"] == 500
    assert sum(point["credits"] for point in data["payment_timeline"]) == 500


def test_build_snapshot_keeps_undated_rows_out_of_the_timeline():
    now = datetime(2026, 11, 8, 12, tzinfo=timezone.utc)
    dated = [(1, "stripe", 100, 500, "usd", "completed", now - timedelta(days=2), None)]
    undated = [(2, "telegram_stars", 70, 70, "xtr", "completed", "starter_month")]
    data = account_usage.build_usage_snapshot([], [], dated, [], 0, "365d", now, undated_purchases=undated)
    assert data["undated_payments"] == [{"id": 2, "provider": "telegram_stars", "credits": 70, "amount": 70, "currency": "XTR",
                                         "status": "completed", "created_at": None, "kind": "subscription", "plan": "starter_month"}]
    assert sum(point["credits"] for point in data["payment_timeline"]) == 100
    assert data["summary"]["added_credits"] == 100 and data["summary"]["undated_payments"] == 1
