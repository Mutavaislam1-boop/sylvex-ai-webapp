"""Telegram Stars recurring subscriptions (monthly plans) end to end.

Drives the real endpoints and the Stars webhook against a disposable
PostgreSQL (SYLVEX_TEST_DATABASE_URL, skipped otherwise). Telegram is a fake:
createInvoiceLink, editUserStarSubscription, answerPreCheckoutQuery and
sendMessage are recorded, never sent. No real payments are made; the
"payments" below are the successful_payment updates Telegram would send.

Telegram behavior relied on (Bot API: createInvoiceLink.subscription_period,
SuccessfulPayment.is_recurring / is_first_recurring /
subscription_expiration_date, editUserStarSubscription): every renewal of a
subscription is a new successful_payment for the same invoice payload with a
new telegram_payment_charge_id. Whether Telegram sends a pre_checkout_query
before a renewal is not documented; both cases are handled.
"""
import asyncio
import json
import os
import time
from datetime import datetime, timedelta

import pytest

import main
from services import shop_orders as orders
from services import telegram_catalog as tg

DATABASE = os.getenv("SYLVEX_TEST_DATABASE_URL")
UID = 990088
OTHER = 990099
DAY = 86400
MONTHLY = {"starter": (499, 100), "pro": (998, 300), "max": (2495, 1000), "ultra": (4990, 2500), "creator": (9980, 5500)}


class FakeRequest:
    def __init__(self, body, headers=None):
        self._body = body
        self.headers = headers or {}

    async def json(self):
        return json.loads(json.dumps(self._body))


def run(coro):
    return asyncio.run(coro)


def body_of(response):
    if isinstance(response, dict):
        return 200, response
    return response.status_code, json.loads(response.body)


class FakeTelegram:
    """Records Bot API calls; editUserStarSubscription answers per `edit_ok`."""

    def __init__(self):
        self.calls = []
        self.edit_ok = True

    def post(self, url, json=None, timeout=None, **kwargs):
        method = url.rsplit("/", 1)[-1]
        self.calls.append((method, json))
        if method == "editUserStarSubscription" and not self.edit_ok:
            body, status = {"ok": False, "error_code": 400, "description": "Bad Request: SUBSCRIPTION_NOT_FOUND"}, 400
        elif method == "createInvoiceLink":
            body, status = {"ok": True, "result": "https://t.me/$invoice"}, 200
        else:
            body, status = {"ok": True, "result": True}, 200
        return type("R", (), {"status_code": status, "content": b"1", "json": lambda self: body})()

    def of(self, method):
        return [params for name, params in self.calls if name == method]


@pytest.fixture
def shop(monkeypatch):
    if not DATABASE:
        pytest.skip("Set SYLVEX_TEST_DATABASE_URL to a disposable PostgreSQL database")
    import psycopg2

    def connect():
        return psycopg2.connect(DATABASE)

    conn = connect()
    with conn.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS subscription_payments, shop_orders, purchases, subscriptions, users CASCADE")
        # Production shape (main.py ensure_payment_tables), before migration.
        cur.execute("CREATE TABLE users (telegram_id BIGINT PRIMARY KEY, first_name TEXT, balance INTEGER DEFAULT 0, subscription TEXT DEFAULT 'free')")
        cur.execute("""CREATE TABLE purchases (id SERIAL PRIMARY KEY, telegram_id BIGINT NOT NULL, provider TEXT NOT NULL, credits INTEGER DEFAULT 0,
                       amount INTEGER DEFAULT 0, currency TEXT DEFAULT 'USD', payload TEXT, charge_id TEXT UNIQUE, status TEXT DEFAULT 'completed',
                       created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
        cur.execute("""CREATE TABLE subscriptions (id SERIAL PRIMARY KEY, telegram_id BIGINT NOT NULL, subscription_type TEXT, payment_method TEXT,
                       amount INTEGER DEFAULT 0, currency TEXT DEFAULT 'USD', starts_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, expires_at TIMESTAMP,
                       status TEXT DEFAULT 'active', charge_id TEXT UNIQUE, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
        for uid in (UID, OTHER):
            cur.execute("INSERT INTO users (telegram_id, first_name, balance) VALUES (%s, 'Buyer', 40)", (uid,))
    conn.commit()
    conn.close()

    telegram = FakeTelegram()
    monkeypatch.setattr(main.requests, "post", telegram.post)
    monkeypatch.setattr(main, "shop_db", connect)
    monkeypatch.setattr(main, "ensure_payment_tables", lambda: None)
    monkeypatch.setattr(main, "_SHOP_ORDERS_READY", False)
    monkeypatch.setattr(main, "log_user_event", lambda **kwargs: None)
    monkeypatch.setattr(main, "send_subscription_congratulations", lambda *args, **kwargs: True)
    monkeypatch.setattr(main, "BOT_TOKEN", "123:TEST")
    monkeypatch.setattr(main, "TELEGRAM_PAYMENT_WEBHOOK_SECRET", "hook")

    def q(sql, params=()):
        c = connect()
        try:
            with c.cursor() as cur:
                cur.execute(sql, params)
                return cur.fetchall() if cur.description else None
        finally:
            c.commit()
            c.close()

    def balance(uid=UID):
        return q("SELECT balance FROM users WHERE telegram_id = %s", (uid,))[0][0]

    return type("Shop", (), {"connect": staticmethod(connect), "q": staticmethod(q), "balance": staticmethod(balance),
                             "telegram": telegram})


HOOK = {"X-Telegram-Bot-Api-Secret-Token": "hook"}


def invoice(product_id, uid=UID, **extra):
    return body_of(run(main.public_stars_invoice(FakeRequest({"telegram_id": uid, "product_id": product_id, **extra}))))


def pre_checkout(shop, payload, amount, uid=UID):
    answers = []
    original = main._answer_stars_pre_checkout
    main._answer_stars_pre_checkout = lambda qid, ok, msg="": answers.append(ok) or True
    try:
        update = {"pre_checkout_query": {"id": "q", "from": {"id": uid}, "currency": "XTR", "total_amount": amount,
                                         "invoice_payload": payload}}
        run(main.public_stars_webhook(FakeRequest(update, HOOK)))
    finally:
        main._answer_stars_pre_checkout = original
    return answers[0]


def paid(payload, amount, charge, expires_in_days=30, uid=UID, first=None, recurring=True, currency="XTR", headers=HOOK):
    payment = {"currency": currency, "total_amount": amount, "invoice_payload": payload, "telegram_payment_charge_id": charge}
    if recurring:
        payment["is_recurring"] = True
        payment["subscription_expiration_date"] = int(time.time()) + int(expires_in_days * DAY)
        if first:
            payment["is_first_recurring"] = True
    return body_of(run(main.public_stars_webhook(FakeRequest({"message": {"from": {"id": uid}, "successful_payment": payment}}, headers))))


def subscribe(shop, plan="pro", uid=UID, charge="first-1"):
    status, body = invoice(f"plan_{plan}_month", uid)
    assert status == 200, body
    payload = orders.order_payload(body["order_id"])
    stars = MONTHLY[plan][0]
    assert pre_checkout(shop, payload, stars, uid)
    _, result = paid(payload, stars, charge, uid=uid, first=True)
    assert result["status"] == "granted", result
    return payload


def status(uid=UID):
    return body_of(run(main.public_subscription_status(FakeRequest({"telegram_id": uid}))))[1]["subscription"]


def manage(action, uid=UID, **extra):
    handler = {"cancel": main.public_subscription_cancel, "reactivate": main.public_subscription_reactivate,
               "change": main.public_subscription_change}[action]
    return body_of(run(handler(FakeRequest({"telegram_id": uid, **extra}))))


def age(shop, days):
    """Move the user's subscriptions `days` into the past (time passing)."""
    shop.q("UPDATE subscriptions SET expires_at = expires_at - (%s || ' days')::interval, "
           "starts_at = starts_at - (%s || ' days')::interval", (days, days))


def iso_to_dt(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)


# 1, 9 ------------------------------------------------ initial purchase, amount and period


@pytest.mark.parametrize("plan", list(MONTHLY))
def test_monthly_invoice_is_a_30_day_stars_subscription_at_the_plan_price(shop, plan):
    stars, credits = MONTHLY[plan]
    status_code, body = invoice(f"plan_{plan}_month", stars=1, usd="0.01")
    assert status_code == 200
    link = shop.telegram.of("createInvoiceLink")[-1]
    assert link["currency"] == "XTR" and link["subscription_period"] == 2592000
    assert link["prices"] == [{"label": link["prices"][0]["label"], "amount": stars}]
    assert "provider_token" not in link
    assert "Автоматически продлевается каждые 30 дней" in link["description"]
    assert body["order"]["stars"] == stars and body["order"]["credits"] == credits


def test_initial_payment_grants_once_and_records_the_telegram_subscription(shop):
    payload = subscribe(shop, "pro")
    assert shop.balance() == 40 + 300
    row = shop.q("SELECT is_recurring, renewal_status, subscription_charge_id, last_charge_id, status, renewals_count "
                 "FROM subscriptions WHERE telegram_id = %s", (UID,))
    assert row == [(True, "auto", "first-1", "first-1", "active", 0)]
    assert shop.q("SELECT payment_kind, charge_id, amount, credits FROM subscription_payments") == [("initial", "first-1", 998, 300)]
    sub = status()
    assert sub["active"] and sub["auto_renew"] and sub["is_recurring"] and sub["plan_key"] == "pro_month"
    assert sub["price_stars"] == 998 and sub["period_credits"] == 300 and sub["period_days"] == 30
    assert sub["next_renewal_at"] == sub["expires_at"]
    assert abs(iso_to_dt(sub["expires_at"]) - (datetime.now() + timedelta(days=30))) < timedelta(minutes=5)
    # The same notification again grants nothing.
    _, again = paid(payload, 998, "first-1", first=True)
    assert again["status"] == "duplicate" and shop.balance() == 340


# 2, 3 ------------------------------------------------ renewals, duplicates, reordering


def test_each_renewal_grants_the_next_periods_credits_once(shop):
    payload = subscribe(shop, "max")
    for n, charge in enumerate(("renew-1", "renew-2"), start=1):
        _, result = paid(payload, 2495, charge, expires_in_days=30 * (n + 1))
        assert result["status"] == "granted"
        assert shop.balance() == 40 + 1000 * (n + 1)
    sub = status()
    assert sub["renewals_count"] == 2 and sub["auto_renew"]
    assert abs(iso_to_dt(sub["expires_at"]) - (datetime.now() + timedelta(days=90))) < timedelta(minutes=5)
    kinds = shop.q("SELECT payment_kind, charge_id FROM subscription_payments ORDER BY id")
    assert kinds == [("initial", "first-1"), ("renewal", "renew-1"), ("renewal", "renew-2")]
    assert shop.q("SELECT COUNT(*) FROM purchases WHERE telegram_id = %s", (UID,))[0][0] == 3
    # The renewal message goes to the user through the bot.
    assert any("продлена" in m["text"] for m in shop.telegram.of("sendMessage"))


def test_duplicate_and_reordered_renewal_notifications(shop):
    payload = subscribe(shop, "starter")
    assert paid(payload, 499, "renew-a", expires_in_days=60)[1]["status"] == "granted"
    for _ in range(3):
        assert paid(payload, 499, "renew-a", expires_in_days=60)[1]["status"] == "duplicate"
    assert shop.balance() == 40 + 200
    # A delayed notification for a different (older) charge still pays its
    # period once, but never moves the expiration date backwards.
    before = status()["expires_at"]
    assert paid(payload, 499, "renew-older", expires_in_days=30)[1]["status"] == "granted"
    assert shop.balance() == 40 + 300 and status()["expires_at"] == before


def test_late_renewal_after_expiry_restores_access(shop):
    payload = subscribe(shop, "pro")
    age(shop, 31)  # the renewal date passed, no payment yet
    assert status()["active"] is False and status()["renewal_missed"] is True
    _, result = paid(payload, 998, "renew-late", expires_in_days=29)
    assert result["status"] == "granted"
    sub = status()
    assert sub["active"] and sub["auto_renew"] and shop.balance() == 40 + 600


# 4, 6 ------------------------------------------------ failed renewal and expiry


def test_missing_renewal_never_extends_access_or_grants_credits(shop):
    subscribe(shop, "ultra")
    age(shop, 31)  # the renewal date passed and Telegram sent no payment
    sub = status()
    assert sub["active"] is False and sub["renewal_missed"] is True and sub["next_renewal_at"] is None
    assert shop.balance() == 40 + 2500
    assert shop.q("SELECT COUNT(*) FROM subscription_payments")[0][0] == 1
    active = shop.q("SELECT COUNT(*) FROM subscriptions WHERE status = 'active' AND expires_at > CURRENT_TIMESTAMP")[0][0]
    assert active == 0


def test_failed_renewal_payment_is_rejected_and_grants_nothing(shop):
    payload = subscribe(shop, "pro")
    for amount, currency, uid in ((1, "XTR", UID), (998, "USD", UID), (998, "XTR", OTHER)):
        _, result = paid(payload, amount, "renew-bad", currency=currency, uid=uid)
        assert result["status"] == "rejected"
    assert shop.balance() == 40 + 300 and shop.balance(OTHER) == 40
    assert status()["renewals_count"] == 0


# 5 ------------------------------------------------ cancellation


def test_cancel_stops_renewal_through_telegram_and_keeps_paid_access(shop):
    subscribe(shop, "pro")
    expires = status()["expires_at"]
    code, body = manage("cancel")
    assert code == 200 and body["ok"] and body["status"] == "canceled"
    edit = shop.telegram.of("editUserStarSubscription")
    assert edit == [{"user_id": UID, "telegram_payment_charge_id": "first-1", "is_canceled": True}]
    sub = body["subscription"]
    assert sub["active"] and not sub["auto_renew"] and sub["renewal_status"] == "canceled"
    assert sub["expires_at"] == expires and sub["next_renewal_at"] is None
    # Repeating the cancel is harmless and does not call Telegram again.
    code, body = manage("cancel")
    assert body["status"] == "already_canceled" and len(shop.telegram.of("editUserStarSubscription")) == 1


def test_cancel_refused_by_telegram_changes_nothing_and_says_so(shop):
    subscribe(shop, "pro")
    shop.telegram.edit_ok = False
    code, body = manage("cancel")
    assert code == 502 and body["ok"] is False and body["error"] == "telegram_refused"
    assert "SUBSCRIPTION_NOT_FOUND" in body["telegram_error"]
    assert status()["auto_renew"] is True


def test_cancelled_subscription_expires_at_the_end_of_the_paid_period(shop):
    subscribe(shop, "pro")
    manage("cancel")
    age(shop, 29)
    assert status()["active"] is True
    age(shop, 2)
    sub = status()
    assert sub["active"] is False and sub["renewal_missed"] is False and sub["renewal_status"] == "canceled"


# 7 ------------------------------------------------ reactivation


def test_reactivate_re_enables_renewal_before_the_period_ends(shop):
    subscribe(shop, "pro")
    manage("cancel")
    code, body = manage("reactivate")
    assert code == 200 and body["status"] == "reactivated" and body["subscription"]["auto_renew"]
    assert shop.telegram.of("editUserStarSubscription")[-1]["is_canceled"] is False


def test_after_expiry_resubscribing_is_a_new_purchase(shop):
    subscribe(shop, "pro")
    manage("cancel")
    age(shop, 31)
    code, body = manage("reactivate")
    assert code == 404 and body["error"] == "no_recurring_subscription"
    subscribe(shop, "pro", charge="second-1")
    assert status()["active"] and status()["auto_renew"] and shop.balance() == 40 + 600


def test_a_renewal_after_a_cancel_reflects_that_telegram_still_renews(shop):
    payload = subscribe(shop, "pro")
    manage("cancel")
    assert paid(payload, 998, "renew-1", expires_in_days=60)[1]["status"] == "granted"
    assert status()["auto_renew"] is True


# 8 ------------------------------------------------ plan changes


def test_no_second_plan_while_one_renews(shop):
    subscribe(shop, "pro")
    created = len(shop.telegram.of("createInvoiceLink"))
    for product_id in ("plan_max_month", "plan_pro_month", "plan_creator_year"):
        code, body = invoice(product_id, confirm_replace=True)
        assert code == 409 and body["error"] == "subscription_renewing" and body["subscription"]["plan_key"] == "pro_month"
    assert len(shop.telegram.of("createInvoiceLink")) == created
    # Credit packs stay available.
    assert invoice("pack_500")[0] == 200


def test_plan_change_is_scheduled_for_the_end_of_the_paid_period(shop):
    subscribe(shop, "pro")
    assert manage("change", plan_key="max_month")[1]["error"] == "confirmation_required"
    assert manage("change", plan_key="pro_month", confirm=True)[1]["error"] == "same_plan"
    assert manage("change", plan_key="max_year", confirm=True)[1]["error"] == "unknown_plan"
    assert not shop.telegram.of("editUserStarSubscription")
    code, body = manage("change", plan_key="max_month", confirm=True)
    assert code == 200 and body["ok"]
    sub = body["subscription"]
    assert sub["plan_key"] == "pro_month" and sub["active"] and not sub["auto_renew"]
    assert sub["pending_plan_key"] == "max_month" and sub["pending_product_id"] == "plan_max_month" and sub["pending_price_stars"] == 2495
    assert shop.telegram.of("editUserStarSubscription")[-1]["is_canceled"] is True
    balance = shop.balance()
    # Nothing is charged for the new plan until the user subscribes to it
    # after the current period ends.
    age(shop, 31)
    sub = status()
    assert not sub["active"] and sub["pending_plan_key"] == "max_month" and shop.balance() == balance
    subscribe(shop, "max", charge="max-1")
    sub = status()
    assert sub["plan_key"] == "max_month" and sub["auto_renew"] and shop.balance() == balance + 1000


def test_reactivating_drops_a_scheduled_plan_change(shop):
    subscribe(shop, "pro")
    manage("change", plan_key="starter_month", confirm=True)
    body = manage("reactivate")[1]
    assert body["subscription"]["auto_renew"] and body["subscription"]["pending_plan_key"] is None


def test_replacing_a_paid_one_time_plan_needs_explicit_confirmation(shop):
    shop.q("INSERT INTO subscriptions (telegram_id, subscription_type, payment_method, expires_at, status, charge_id) "
           "VALUES (%s, 'pro_year', 'telegram_stars', CURRENT_TIMESTAMP + INTERVAL '100 days', 'active', 'annual-1')", (UID,))
    code, body = invoice("plan_max_month")
    assert code == 409 and body["error"] == "subscription_replace_confirmation_required"
    assert body["subscription"]["plan_key"] == "pro_year" and body["subscription"]["is_recurring"] is False
    code, body = invoice("plan_max_month", confirm_replace=True)
    assert code == 200
    payload = orders.order_payload(body["order_id"])
    assert pre_checkout(shop, payload, 2495)
    assert paid(payload, 2495, "max-1", first=True)[1]["status"] == "granted"
    assert shop.q("SELECT status FROM subscriptions WHERE charge_id = 'annual-1'")[0][0] == "cancelled"
    assert status()["plan_key"] == "max_month"


def test_a_racing_second_subscription_is_refused_or_its_renewal_stopped(shop):
    first = invoice("plan_pro_month")[1]
    second = invoice("plan_max_month")[1]
    p1, p2 = orders.order_payload(first["order_id"]), orders.order_payload(second["order_id"])
    assert pre_checkout(shop, p1, 998)
    assert paid(p1, 998, "pro-1", first=True)[1]["status"] == "granted"
    # Pre-checkout of the second plan is refused: never two renewing plans.
    assert pre_checkout(shop, p2, 2495) is False
    # Had Telegram charged it anyway, the money is honored and the older
    # subscription's renewal is cancelled through Telegram.
    assert paid(p2, 2495, "max-1", first=True)[1]["status"] == "granted"
    assert shop.telegram.of("editUserStarSubscription")[-1] == {"user_id": UID, "telegram_payment_charge_id": "pro-1",
                                                                "is_canceled": True}
    rows = shop.q("SELECT subscription_type, status, renewal_status FROM subscriptions ORDER BY id")
    assert rows == [("pro_month", "cancelled", "replaced"), ("max_month", "active", "auto")]


def test_reopening_a_paid_invoice_never_creates_a_silent_second_subscription(shop):
    payload = subscribe(shop, "pro")
    # Mid-period, a pre-checkout for the already-paid invoice is refused.
    assert pre_checkout(shop, payload, 998) is False
    # Around the renewal date it is accepted (in case renewals send one).
    age(shop, 29.5)
    assert pre_checkout(shop, payload, 998) is True
    # If the same invoice was paid as a NEW subscription, that payment is
    # honored once and the new subscription's renewal is cancelled.
    assert paid(payload, 998, "dup-sub-1", first=True)[1]["status"] == "granted"
    assert shop.telegram.of("editUserStarSubscription")[-1]["telegram_payment_charge_id"] == "dup-sub-1"


# 10 ------------------------------------------------ the 10,000-Star recurring cap


def test_recurring_prices_above_10000_stars_are_rejected(shop, monkeypatch):
    with pytest.raises(tg.CatalogError) as err:
        tg.check_invoice_amount(10001, tg.SUBSCRIPTION_PERIOD_SECONDS)
    assert err.value.code == "subscription_amount_above_limit"
    assert tg.check_invoice_amount(10000, tg.SUBSCRIPTION_PERIOD_SECONDS) == 10000
    # An order snapshot above the cap never reaches Telegram as a subscription.
    calls = len(shop.telegram.calls)
    with pytest.raises(tg.CatalogError):
        main.create_store_stars_invoice_link({"order_id": "o", "title": "SYLVEX", "stars": 10001,
                                              "subscription_period": 2592000})
    assert len(shop.telegram.calls) == calls
    # A monthly plan priced above the cap would be unavailable, not split.
    expensive = dict(tg.PRODUCTS["plan_creator_month"], stars=10001)
    assert tg._with_availability(expensive)["unavailable_reason"] == "subscription_amount_above_limit"
    assert all(tg.resolve(f"plan_{plan}_month")["stars"] <= 10000 for plan in MONTHLY)


# 11, 12 ------------------------------------------------ annual plans and packs never renew


@pytest.mark.parametrize("product_id,stars", [("plan_pro_year", 9581), ("plan_creator_year", 95808), ("pack_1000", 998),
                                              ("credits_custom", 1232)])
def test_annual_plans_and_credit_packs_stay_one_time(shop, product_id, stars):
    extra = {"credits": "1234"} if product_id == "credits_custom" else {}
    code, body = invoice(product_id, **extra)
    assert code == 200
    assert "subscription_period" not in shop.telegram.of("createInvoiceLink")[-1]
    payload = orders.order_payload(body["order_id"])
    assert paid(payload, stars, "one-1", recurring=False)[1]["status"] == "granted"
    # A "recurring" charge for a one-time order is never accepted.
    assert paid(payload, stars, "one-2")[1]["status"] == "rejected"
    if product_id.startswith("plan_"):
        assert shop.q("SELECT is_recurring, renewal_status FROM subscriptions") == [(False, "none")]
        assert status() is None or status()["is_recurring"] is False


# 13 ------------------------------------------------ forged notifications


def test_forged_or_invalid_payment_notifications_grant_nothing(shop):
    payload = subscribe(shop, "pro")
    before = shop.balance()
    assert paid(payload, 998, "forged-1", headers={})[0] == 401
    assert paid(payload, 998, "forged-2", headers={"X-Telegram-Bot-Api-Secret-Token": "wrong"})[0] == 401
    assert paid(orders.order_payload("f" * 32), 998, "forged-3")[1]["status"] == "rejected"
    assert paid(payload, 998, "")[1]["status"] == "rejected"
    assert shop.balance() == before and status()["renewals_count"] == 0
    # Another user cannot manage this subscription: endpoints act only on
    # the caller's own (middleware-verified) telegram_id.
    assert manage("cancel", uid=OTHER)[1]["error"] == "no_recurring_subscription"
    assert status()["auto_renew"] is True


def test_management_routes_require_a_verified_telegram_user():
    from services.security import PUBLIC_POSTS, TELEGRAM_BLOCKED_PURCHASE_ROUTES
    for route in ("status", "cancel", "reactivate", "change"):
        path = f"/api/public/subscription/{route}"
        assert path not in PUBLIC_POSTS and path not in TELEGRAM_BLOCKED_PURCHASE_ROUTES


# 14 ------------------------------------------------ existing subscribers and history


def test_existing_subscribers_and_history_are_unchanged(shop):
    shop.q("INSERT INTO subscriptions (telegram_id, subscription_type, payment_method, amount, currency, expires_at, status, charge_id) "
           "VALUES (%s, 'month', 'telegram_stars_subscription', 499, 'XTR', CURRENT_TIMESTAMP + INTERVAL '10 days', 'active', 'legacy-1')", (UID,))
    shop.q("INSERT INTO purchases (telegram_id, provider, credits, amount, currency, payload, charge_id) "
           "VALUES (%s, 'crypto_pay', 500, 500, 'USDT', 'sylvex_order:x', 'crypto-old')", (UID,))
    orders.ensure_order_tables(shop.connect)
    orders.ensure_order_tables(shop.connect)  # the migration is idempotent
    sub = status()
    assert sub["active"] and sub["plan_key"] == "month" and sub["is_recurring"] is False
    assert sub["renewal_status"] == "none" and sub["auto_renew"] is False and sub["next_renewal_at"] is None
    assert manage("cancel")[1]["error"] == "no_recurring_subscription"
    assert not shop.telegram.of("editUserStarSubscription")
    assert shop.q("SELECT provider, credits FROM purchases WHERE charge_id = 'crypto-old'") == [("crypto_pay", 500)]
    assert shop.balance() == 40
