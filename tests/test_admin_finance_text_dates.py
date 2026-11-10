"""/api/admin/finance with purchases.created_at stored as TEXT.

In Production the main bot created `purchases` first (sylvex-ai-bot
app/database/db.py: created_at TEXT), so the API's own CREATE TABLE IF NOT
EXISTS (created_at TIMESTAMP) never applied and `created_at >= %s::timestamp`
failed with "operator does not exist: text >= timestamp without time zone".
The column holds what each writer put there:
- the bot: datetime.now().strftime("%Y-%m-%d %H:%M:%S");
- the API (shop orders, Stripe, billing safety): CURRENT_TIMESTAMP, which a
  TEXT column stores as "YYYY-MM-DD HH:MM:SS.ffffff+00";
- old rows without a date (SX-010): NULL or ''.

Real SQL (PGlite). Nothing in purchases is changed by the report.
"""
from datetime import datetime, timedelta

import pytest

from test_admin_console_auth import (  # noqa: F401  (fixtures)
    OWNER_TG, USER_TG, call, env, login, q, ready,
)

BOT_DDL = """
    CREATE TABLE purchases (
        id SERIAL PRIMARY KEY, telegram_id BIGINT, provider TEXT, credits INTEGER, amount INTEGER,
        currency TEXT, payload TEXT, charge_id TEXT UNIQUE, status TEXT DEFAULT 'completed', created_at TEXT
    )"""
OTHER_TG = 7000000077
VIEWER_TG = 559


def _bot_time(days_ago=0, hours_ago=0):
    return (datetime.utcnow() - timedelta(days=days_ago, hours=hours_ago)).strftime("%Y-%m-%d %H:%M:%S")


def _insert(env, uid, provider, credits, amount, currency, charge_id, status, created_at_sql, params=()):
    q(env, "INSERT INTO purchases (telegram_id, provider, credits, amount, currency, payload, charge_id, status, created_at) "
           f"VALUES (%s, %s, %s, %s, %s, '', %s, %s, {created_at_sql})",
      (uid, provider, credits, amount, currency, charge_id, status) + tuple(params))


@pytest.fixture
def text_purchases(ready, monkeypatch):
    """Production's shape: the bot's TEXT table exists before the API starts."""
    env = ready
    # Each test has a fresh database: the per-process "schema ready" caches must not carry over.
    monkeypatch.setattr(env.main, "_PROSTUDIO_SCHEMA_READY", False)
    monkeypatch.setattr(env.main, "_PAYMENT_SCHEMA_READY", False)
    q(env, BOT_DDL)
    env.main.ensure_payment_tables()  # IF NOT EXISTS: the TEXT column stays
    assert q(env, "SELECT data_type FROM information_schema.columns "
                  "WHERE table_name = 'purchases' AND column_name = 'created_at'") == [["text"]]
    for uid in (USER_TG, OTHER_TG):
        q(env, "INSERT INTO users (telegram_id, first_name, balance) VALUES (%s, 'Buyer', 0) "
               "ON CONFLICT (telegram_id) DO NOTHING", (uid,))
    # New purchases, both writers' formats, inside the last 30 days.
    _insert(env, USER_TG, "telegram_stars", 200, 250, "XTR", "bot_new", "completed", "%s", (_bot_time(2),))
    _insert(env, USER_TG, "stripe", 500, 999, "USD", "api_new", "completed", "CURRENT_TIMESTAMP")
    _insert(env, OTHER_TG, "stripe", 100, 199, "USD", "refund_new", "refunded", "%s", (_bot_time(1),))
    # An old purchase (dated, 200 days ago): the first payment of USER_TG.
    _insert(env, USER_TG, "telegram_stars", 50, 75, "XTR", "bot_old", "completed", "%s", (_bot_time(200),))
    # Old purchases without a usable date.
    _insert(env, OTHER_TG, "telegram_stars", 10, 15, "XTR", "undated_null", "completed", "NULL")
    _insert(env, OTHER_TG, "telegram_stars", 10, 15, "XTR", "undated_empty", "completed", "''")
    _insert(env, OTHER_TG, "telegram_stars", 10, 15, "XTR", "undated_junk", "completed", "'unknown'")
    return env


def _snapshot(env):
    return q(env, "SELECT id, telegram_id, provider, credits, amount, currency, charge_id, status, created_at "
                  "FROM purchases ORDER BY id")


async def _finance(env, body, who=OWNER_TG):
    token, csrf = await login(env, who)
    return await call(env, "POST", "/api/admin/finance", cookie=token, csrf=csrf, json_body=body)


@pytest.mark.asyncio
async def test_finance_reads_text_dates_from_both_writers(text_purchases):
    env = text_purchases
    before = _snapshot(env)
    r = await _finance(env, {"days": 30})
    assert r.status_code == 200, r.text
    data = r.json()
    # Both new purchases count, the old one (200 days ago) and the undated ones do not.
    assert data["revenue"] == {"USD": 9.99, "XTR": 250.0}
    assert data["credits"]["sold"] == 700
    assert data["refunds"] == [{"currency": "USD", "count": 1, "amount": 1.99}]
    # USER_TG first paid 200 days ago: a buyer in the period, but not a new one.
    assert data["buyers"] == 1 and data["new_buyers"] == 0
    by_day = {d["day"]: d["payments"] for d in data["days"]}
    assert by_day[_bot_time(2)[:10]] >= 1 and sum(by_day.values()) == 2
    assert _snapshot(env) == before  # the report changes nothing


@pytest.mark.asyncio
async def test_all_time_includes_old_dated_purchases_but_never_invents_dates(text_purchases):
    env = text_purchases
    data = (await _finance(env, {"days": 0})).json()
    # Three dated completed purchases (two new, one old); NULL, '' and junk dates stay out.
    assert data["revenue"] == {"USD": 9.99, "XTR": 325.0}
    assert data["credits"]["sold"] == 750
    assert data["buyers"] == 1 and data["new_buyers"] == 1


@pytest.mark.asyncio
async def test_explicit_period_and_an_empty_period(text_purchases):
    env = text_purchases
    old_day = _bot_time(200)[:10]
    data = (await _finance(env, {"from": old_day, "to": old_day})).json()
    assert data["revenue"] == {"XTR": 75.0} and data["buyers"] == 1 and data["new_buyers"] == 1
    data = (await _finance(env, {"from": "2001-01-01", "to": "2001-01-02"})).json()
    assert data["revenue"] == {} and data["refunds"] == [] and data["buyers"] == 0


@pytest.mark.asyncio
async def test_finance_still_needs_payments_view(text_purchases):
    env = text_purchases
    from admin_fixtures import enable_mfa, make_admin
    conn = env.db.connect()
    cur = conn.cursor()
    enable_mfa(cur, make_admin(cur, VIEWER_TG, role="read_only"))  # read_only has no payments.view
    conn.commit()
    r = await _finance(env, {"days": 30}, who=VIEWER_TG)
    assert r.status_code == 403 and r.json()["detail"] == "admin_permission_denied"
