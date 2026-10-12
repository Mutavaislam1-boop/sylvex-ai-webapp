"""Telegram Stars subscriptions end to end: monthly Telegram subscriptions,
annual one-time plans, switching, fallback, cancellation, expiry and the
administration notification outbox.

SIMULATED: the real endpoints, webhook, payment module and workers run
against a disposable PostgreSQL (SYLVEX_TEST_DATABASE_URL, skipped
otherwise), but Telegram is a fake - createInvoiceLink,
editUserStarSubscription, answerPreCheckoutQuery and sendMessage are
recorded, never sent, and "payments" are the successful_payment updates
Telegram would deliver. No real payment or renewal is involved.
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
ANNUAL = {"starter": (4791, 1200), "pro": (9581, 3600), "max": (23952, 12000), "ultra": (47904, 30000), "creator": (95808, 66000)}
START = 40


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
    """Records Bot API calls. editUserStarSubscription / sendMessage answer per
    edit_ok / send_ok."""

    def __init__(self):
        self.calls = []
        self.edit_ok = True
        self.send_ok = True

    def post(self, url, json=None, timeout=None, **kwargs):
        method = url.rsplit("/", 1)[-1]
        self.calls.append((method, json))
        if method == "editUserStarSubscription" and not self.edit_ok:
            body, status = {"ok": False, "error_code": 400, "description": "Bad Request: SUBSCRIPTION_NOT_FOUND"}, 400
        elif method == "sendMessage" and not self.send_ok:
            body, status = {"ok": False, "error_code": 429, "description": "Too Many Requests"}, 429
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
        cur.execute("DROP TABLE IF EXISTS payment_inbox, payment_reconcile_state, subscription_events, subscription_payments, subscription_agreements, shop_orders, "
                    "purchases, subscriptions, users CASCADE")
        # Production shape (main.py ensure_payment_tables), before migration.
        cur.execute("CREATE TABLE users (telegram_id BIGINT PRIMARY KEY, first_name TEXT, balance INTEGER DEFAULT 0, subscription TEXT DEFAULT 'free')")
        cur.execute("""CREATE TABLE purchases (id SERIAL PRIMARY KEY, telegram_id BIGINT NOT NULL, provider TEXT NOT NULL, credits INTEGER DEFAULT 0,
                       amount INTEGER DEFAULT 0, currency TEXT DEFAULT 'USD', payload TEXT, charge_id TEXT UNIQUE, status TEXT DEFAULT 'completed',
                       created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
        cur.execute("""CREATE TABLE subscriptions (id SERIAL PRIMARY KEY, telegram_id BIGINT NOT NULL, subscription_type TEXT, payment_method TEXT,
                       amount INTEGER DEFAULT 0, currency TEXT DEFAULT 'USD', starts_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, expires_at TIMESTAMP,
                       status TEXT DEFAULT 'active', charge_id TEXT UNIQUE, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
        for uid in (UID, OTHER):
            cur.execute("INSERT INTO users (telegram_id, first_name, balance) VALUES (%s, 'Buyer', %s)", (uid, START))
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
    monkeypatch.setattr(main, "SUBSCRIPTION_ADMIN_CHAT_ID", 4242)
    monkeypatch.setattr(main, "sylvex_account_id_for", lambda telegram_id: 110626010001 if telegram_id == UID else None)

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

    def events(event_type=None):
        rows = q("SELECT event_type, plan_key, status, amount, reference FROM subscription_events ORDER BY id")
        return [r for r in rows if event_type is None or r[0] == event_type]

    return type("Shop", (), {"connect": staticmethod(connect), "q": staticmethod(q), "balance": staticmethod(balance),
                             "events": staticmethod(events), "telegram": telegram})


HOOK = {"X-Telegram-Bot-Api-Secret-Token": "hook"}


def invoice(product_id, uid=UID, **extra):
    return body_of(run(main.public_stars_invoice(FakeRequest({"telegram_id": uid, "product_id": product_id, **extra}))))


def pre_checkout(payload, amount, uid=UID):
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


def paid(payload, amount, charge, expires_in_days=30, uid=UID, first=None, recurring=True, currency="XTR", headers=HOOK,
         paid_at=None):
    payment = {"currency": currency, "total_amount": amount, "invoice_payload": payload, "telegram_payment_charge_id": charge}
    if recurring:
        payment["is_recurring"] = True
        payment["subscription_expiration_date"] = int(time.time()) + int(expires_in_days * DAY)
        if first:
            payment["is_first_recurring"] = True
    message = {"from": {"id": uid}, "date": int(paid_at or time.time()), "successful_payment": payment}
    return body_of(run(main.public_stars_webhook(FakeRequest({"message": message}, headers))))


def buy(plan, period="month", charge=None, uid=UID, confirm=None):
    """Full purchase: invoice (confirming a change if needed), pre-checkout,
    successful_payment. Returns the invoice payload."""
    product_id = f"plan_{plan}_{period}"
    extra = {"confirm_change": True} if confirm else {}
    code, body = invoice(product_id, uid, **extra)
    assert code == 200, body
    payload = orders.order_payload(body["order_id"])
    stars = (MONTHLY if period == "month" else ANNUAL)[plan][0]
    assert pre_checkout(payload, stars, uid)
    _, result = paid(payload, stars, charge or f"{plan}-{period}-1", uid=uid, first=True, recurring=period == "month",
                     expires_in_days=30)
    assert result["status"] == "granted", result
    return payload


def status(uid=UID):
    return body_of(run(main.public_subscription_status(FakeRequest({"telegram_id": uid}))))[1]["subscription"]


def manage(action, uid=UID, **extra):
    handler = {"cancel": main.public_subscription_cancel, "reactivate": main.public_subscription_reactivate,
               "change": main.public_subscription_change}[action]
    return body_of(run(handler(FakeRequest({"telegram_id": uid, **extra}))))


def age(shop, days, plan_key=None):
    """Move subscriptions `days` into the past (time passing)."""
    where = " WHERE subscription_type = %s" if plan_key else ""
    shop.q("UPDATE subscriptions SET expires_at = expires_at - (%s || ' days')::interval, "
           "starts_at = starts_at - (%s || ' days')::interval" + where,
           (days, days, plan_key) if plan_key else (days, days))


def dt(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)


def near(value, days):
    return abs(dt(value) - (datetime.now() + timedelta(days=days))) < timedelta(minutes=10)


def edits(shop):
    return shop.telegram.of("editUserStarSubscription")


def users_plan(shop):
    return shop.q("SELECT subscription FROM users WHERE telegram_id = %s", (UID,))[0][0]


# 1 ------------------------------------------------ every monthly plan


@pytest.mark.parametrize("plan", list(MONTHLY))
def test_every_monthly_plan_is_a_30_day_telegram_subscription(shop, plan):
    stars, credits = MONTHLY[plan]
    code, body = invoice(f"plan_{plan}_month", stars=1, usd="0.01")
    assert code == 200
    link = shop.telegram.of("createInvoiceLink")[-1]
    assert link["currency"] == "XTR" and link["subscription_period"] == 2592000 and "provider_token" not in link
    assert link["prices"][0]["amount"] == stars and body["order"]["stars"] == stars
    payload = orders.order_payload(body["order_id"])
    assert pre_checkout(payload, stars)
    assert paid(payload, stars, "c1", first=True)[1]["status"] == "granted"
    assert shop.balance() == START + credits
    sub = status()
    assert sub["state"] == "active_recurring" and sub["auto_renew"] and sub["billing"] == "monthly"
    assert sub["price_stars"] == stars and sub["period_credits"] == credits and near(sub["expires_at"], 30)
    assert sub["next_renewal_at"] == sub["expires_at"] and sub["started_at"]
    assert shop.q("SELECT plan_key, renewal_status, subscription_charge_id FROM subscription_agreements") == [(f"{plan}_month", "auto", "c1")]
    assert users_plan(shop) == f"{plan}_month"
    assert shop.events("subscription_purchased")[0][1:4] == (f"{plan}_month", "active_recurring", stars)


# 2 ------------------------------------------------ every annual plan


@pytest.mark.parametrize("plan", list(ANNUAL))
def test_every_annual_plan_is_one_payment_for_365_days(shop, plan):
    stars, credits = ANNUAL[plan]
    buy(plan, "year")
    assert "subscription_period" not in shop.telegram.of("createInvoiceLink")[-1]
    assert shop.balance() == START + credits
    sub = status()
    assert sub["state"] == "active_annual" and sub["billing"] == "annual" and not sub["auto_renew"]
    assert near(sub["expires_at"], 365) and sub["next_renewal_at"] is None and sub["price_stars"] == stars
    assert shop.q("SELECT COUNT(*) FROM subscription_agreements")[0][0] == 0
    # A "recurring" charge on an annual order is never accepted: no extra charges.
    payload = shop.q("SELECT payload FROM purchases")[0][0]
    assert paid(payload, stars, "extra")[1]["status"] == "rejected"
    assert shop.balance() == START + credits


# 3, 4 ------------------------------------------------ renewals and duplicates


def test_each_renewal_extends_and_grants_the_monthly_credits_once(shop):
    payload = buy("max")
    for n in (1, 2):
        assert paid(payload, 2495, f"renew-{n}", expires_in_days=30 * (n + 1))[1]["status"] == "granted"
        assert shop.balance() == START + 1000 * (n + 1)
    sub = status()
    assert sub["renewals_count"] == 2 and sub["auto_renew"] and near(sub["expires_at"], 90)
    kinds = shop.q("SELECT payment_kind, charge_id FROM subscription_payments ORDER BY id")
    assert kinds == [("initial", "max-month-1"), ("renewal", "renew-1"), ("renewal", "renew-2")]
    assert [e[2] for e in shop.events("subscription_renewed")] == ["auto", "auto"]
    assert any("продлена" in m["text"] for m in shop.telegram.of("sendMessage"))


def test_duplicate_delayed_and_reordered_renewals_grant_once(shop):
    payload = buy("starter")
    assert paid(payload, 499, "renew-a", expires_in_days=60)[1]["status"] == "granted"
    for _ in range(3):
        assert paid(payload, 499, "renew-a", expires_in_days=60)[1]["status"] == "duplicate"
    assert shop.balance() == START + 200
    before = status()["expires_at"]
    assert paid(payload, 499, "renew-older", expires_in_days=30)[1]["status"] == "granted"
    assert shop.balance() == START + 300 and status()["expires_at"] == before  # never moves backwards
    assert len(shop.events("subscription_renewed")) == 2


def test_a_late_renewal_after_expiry_restores_access(shop):
    payload = buy("pro")
    age(shop, 31)
    assert status()["state"] == "expired"
    assert paid(payload, 998, "renew-late", expires_in_days=29)[1]["status"] == "granted"
    assert status()["state"] == "active_recurring" and shop.balance() == START + 600


# 5 ------------------------------------------------ cancellation and reactivation


def test_cancel_through_telegram_keeps_access_and_credits(shop):
    buy("pro")
    expires = status()["expires_at"]
    code, body = manage("cancel")
    assert code == 200 and body["ok"] and body["status"] == "canceled"
    assert edits(shop) == [{"user_id": UID, "telegram_payment_charge_id": "pro-month-1", "is_canceled": True}]
    sub = body["subscription"]
    assert sub["state"] == "renewal_canceled" and sub["active"] and not sub["auto_renew"]
    assert sub["expires_at"] == expires and sub["next_renewal_at"] is None and shop.balance() == START + 300
    assert shop.events("renewal_canceled")[0][2] == "canceled_by_user"
    assert manage("cancel")[1]["status"] == "already_canceled" and len(edits(shop)) == 1


def test_a_cancel_telegram_refuses_is_reported_and_changes_nothing(shop):
    buy("pro")
    shop.telegram.edit_ok = False
    code, body = manage("cancel")
    assert code == 502 and body["error"] == "telegram_refused" and "SUBSCRIPTION_NOT_FOUND" in body["telegram_error"]
    assert status()["auto_renew"] is True
    assert shop.events("management_error")[0][2] == "cancel_refused" and not shop.events("renewal_canceled")


def test_reactivation_through_telegram_and_its_failure(shop):
    buy("pro")
    manage("cancel")
    code, body = manage("reactivate")
    assert code == 200 and body["status"] == "reactivated" and body["subscription"]["state"] == "active_recurring"
    assert edits(shop)[-1]["is_canceled"] is False and shop.events("renewal_reactivated")
    manage("cancel")
    shop.telegram.edit_ok = False  # e.g. the user cancelled it inside Telegram
    code, body = manage("reactivate")
    assert code == 502 and body["error"] == "reactivation_unavailable"
    assert status()["state"] == "renewal_canceled"


def test_a_renewal_charged_after_a_confirmed_cancel_is_honored_and_flagged(shop):
    payload = buy("pro")
    manage("cancel")
    # A charge from before the cancellation, reported late: stays cancelled.
    assert paid(payload, 998, "renew-before", expires_in_days=60, paid_at=time.time() - 3600)[1]["status"] == "granted"
    assert status()["state"] == "renewal_canceled"
    # A charge after it (renewal re-enabled inside Telegram): renewing again.
    assert paid(payload, 998, "renew-after", expires_in_days=90, paid_at=time.time() + 60)[1]["status"] == "granted"
    assert status()["state"] == "active_recurring" and shop.balance() == START + 900
    assert ("payment_attention", "pro_month", "renewed_after_cancellation") == shop.events("payment_attention")[0][:3]


# 6 ------------------------------------------------ expiration


def test_missing_renewal_is_unconfirmed_then_expired_never_extended(shop):
    buy("ultra")
    age(shop, 30.1)  # 2.4 h past the renewal date, nothing received
    sub = status()
    assert sub["state"] == "renewal_unconfirmed" and not sub["active"] and sub["next_renewal_at"] is None
    assert main.run_subscription_sweep()["expired"] == 0  # still within the renewal grace
    age(shop, 0.5)
    assert main.run_subscription_sweep()["expired"] == 1
    assert status()["state"] == "expired" and status()["renewal_missed"]
    assert shop.q("SELECT renewal_status FROM subscription_agreements") == [("ended",)]
    assert shop.events("subscription_expired")[0][2] == "no_renewal"
    assert main.run_subscription_sweep()["expired"] == 0  # reported once
    assert shop.balance() == START + 2500 and users_plan(shop) is None


def test_cancelled_subscription_ends_at_its_paid_expiration(shop):
    buy("pro")
    manage("cancel")
    age(shop, 29)
    assert status()["state"] == "renewal_canceled"
    age(shop, 2)
    main.run_subscription_sweep()
    assert status()["state"] == "expired" and shop.events("subscription_expired")[0][2] == "renewal_canceled"
    assert shop.balance() == START + 300


# 7-11 ------------------------------------------------ switching rules


def test_monthly_to_monthly_upgrade_needs_confirmation_then_replaces_renewal(shop):
    buy("starter")
    code, body = invoice("plan_pro_month")
    assert code == 409 and body["error"] == "subscription_change_confirmation_required"
    change = body["change"]
    assert change["type"] == "upgrade" and change["price_stars"] == 998 and change["stops_renewal_of"] == "starter_month"
    assert change["becomes_primary_now"] is True
    buy("pro", confirm=True)
    sub = status()
    assert sub["plan_key"] == "pro_month" and sub["state"] == "active_recurring"
    assert sub["renewal"]["plan_key"] == "pro_month" and sub["next_renewal_at"] == sub["expires_at"]
    # Starter's renewal was stopped through Telegram; its paid period stays.
    assert edits(shop) == [{"user_id": UID, "telegram_payment_charge_id": "starter-month-1", "is_canceled": True}]
    agreements = shop.q("SELECT plan_key, renewal_status, cancel_reason FROM subscription_agreements ORDER BY id")
    assert agreements == [("starter_month", "canceled", "replaced"), ("pro_month", "auto", None)]
    assert [e["plan_key"] for e in sub["entitlements"]] == ["starter_month"]
    assert shop.balance() == START + 100 + 300  # full price, credits only added
    assert shop.events("primary_changed")[-1][1:3] == ("pro_month", "effective")


def test_annual_to_monthly_keeps_the_annual_and_falls_back_to_it(shop):
    buy("starter", "year")
    annual_expiry = status()["expires_at"]
    buy("pro", "month", confirm=True)
    sub = status()
    assert sub["plan_key"] == "pro_month" and sub["entitlements"][0]["plan_key"] == "starter_year"
    assert sub["entitlements"][0]["expires_at"] == annual_expiry  # not restarted, extended or frozen
    manage("cancel")
    age(shop, 31, "pro_month")
    main.run_subscription_sweep()
    sub = status()
    assert sub["plan_key"] == "starter_year" and sub["state"] == "active_annual" and sub["expires_at"] == annual_expiry
    assert users_plan(shop) == "starter_year"
    assert ("primary_changed", "starter_year", "fallback") == shop.events("primary_changed")[-1][:3]
    assert shop.balance() == START + 1200 + 300


def test_monthly_to_annual_stops_the_monthly_renewal(shop):
    buy("starter")
    buy("pro", "year", confirm=True)
    sub = status()
    assert sub["plan_key"] == "pro_year" and sub["state"] == "active_annual" and near(sub["expires_at"], 365)
    assert not sub["auto_renew"] and edits(shop)[-1]["telegram_payment_charge_id"] == "starter-month-1"
    assert shop.q("SELECT renewal_status FROM subscription_agreements") == [("canceled",)]
    assert shop.balance() == START + 100 + 3600


def test_annual_to_annual_keeps_both_entitlements_without_combining(shop):
    buy("starter", "year")
    starter_expiry = status()["expires_at"]
    code, body = invoice("plan_pro_year")
    assert code == 409 and body["change"]["type"] == "upgrade"
    buy("pro", "year", confirm=True)
    sub = status()
    assert sub["plan_key"] == "pro_year" and near(sub["expires_at"], 365)
    assert sub["entitlements"][0]["plan_key"] == "starter_year" and sub["entitlements"][0]["expires_at"] == starter_expiry
    assert shop.balance() == START + 1200 + 3600


def test_downgrade_keeps_the_higher_plan_until_it_ends(shop):
    buy("max")
    code, body = invoice("plan_starter_month")
    assert code == 409 and body["change"]["type"] == "downgrade" and body["change"]["becomes_primary_now"] is False
    buy("starter", confirm=True)
    sub = status()
    assert sub["plan_key"] == "max_month" and sub["state"] == "renewal_canceled"  # Max stays until it ends
    assert sub["renewal"]["plan_key"] == "starter_month" and sub["auto_renew"]  # only Starter renews
    assert edits(shop)[-1]["telegram_payment_charge_id"] == "max-month-1"
    age(shop, 31, "max_month")
    main.run_subscription_sweep()
    assert status()["plan_key"] == "starter_month" and users_plan(shop) == "starter_month"
    assert shop.balance() == START + 1000 + 100


def test_downgrade_can_be_scheduled_without_paying_now(shop):
    buy("pro")
    assert manage("change", plan_key="starter_month")[1]["error"] == "confirmation_required"
    code, body = manage("change", plan_key="starter_month", confirm=True)
    assert code == 200 and body["subscription"]["state"] == "renewal_canceled"
    assert body["subscription"]["pending_plan_key"] == "starter_month"
    assert body["subscription"]["pending_product_id"] == "plan_starter_month"
    assert shop.balance() == START + 300 and len(shop.telegram.of("createInvoiceLink")) == 1
    age(shop, 31)
    assert status()["pending_plan_key"] == "starter_month"
    buy("starter", charge="starter-1")  # nothing valid any more: no confirmation needed
    assert status()["plan_key"] == "starter_month"


# 12 ------------------------------------------------ credits are only ever added


def test_no_subscription_change_ever_reduces_the_balance(shop):
    observed = [shop.balance()]
    payload = buy("starter")
    observed.append(shop.balance())
    paid(payload, 499, "renew-1", expires_in_days=60)
    observed.append(shop.balance())
    buy("pro", confirm=True)
    observed.append(shop.balance())
    manage("cancel")
    observed.append(shop.balance())
    buy("starter", "year", confirm=True)
    observed.append(shop.balance())
    age(shop, 400)
    main.run_subscription_sweep()
    observed.append(shop.balance())
    assert observed == sorted(observed) and observed[-1] == START + 100 + 100 + 300 + 1200


# 14 ------------------------------------------------ no unwanted duplicate renewals


def test_the_same_monthly_plan_is_never_bought_twice(shop):
    buy("pro")
    for extra in ({}, {"confirm_change": True}):
        code, body = invoice("plan_pro_month", **extra)
        assert code == 409 and body["error"] == "already_subscribed"
    assert len(shop.telegram.of("createInvoiceLink")) == 1
    assert invoice("pack_500")[0] == 200  # credit packs stay available


def test_unconfirmed_or_stale_orders_are_refused_at_pre_checkout(shop):
    # Created while nothing was active, paid after another plan started.
    stale = orders.order_payload(invoice("plan_max_month")[1]["order_id"])
    buy("pro")
    assert pre_checkout(stale, 2495) is False
    # Same monthly plan, even confirmed: refused.
    same = orders.order_payload(invoice("plan_max_month", confirm_change=True)[1]["order_id"])
    buy("max", confirm=True, charge="max-1")
    assert pre_checkout(same, 2495) is False


def test_racing_purchases_leave_exactly_one_renewal(shop):
    a = orders.order_payload(invoice("plan_pro_month")[1]["order_id"])
    b = orders.order_payload(invoice("plan_max_month")[1]["order_id"])
    assert pre_checkout(a, 998) and pre_checkout(b, 2495)
    assert paid(a, 998, "pro-1", first=True)[1]["status"] == "granted"
    assert paid(b, 2495, "max-1", first=True)[1]["status"] == "granted"  # money taken: honored
    assert shop.q("SELECT plan_key, renewal_status FROM subscription_agreements ORDER BY id") == [
        ("pro_month", "canceled"), ("max_month", "auto")]
    assert status()["plan_key"] == "max_month"


def test_an_unstopped_replaced_renewal_is_honored_retried_and_flagged(shop):
    pro = buy("pro")
    shop.telegram.edit_ok = False
    buy("max", confirm=True)
    assert shop.q("SELECT plan_key, renewal_status FROM subscription_agreements ORDER BY id")[0] == ("pro_month", "stop_pending")
    assert shop.events("management_error")[0][2] == "replaced_renewal_not_stopped"
    assert status()["renewal"]["plan_key"] == "max_month"
    # Telegram still renews Pro: the payment is honored, flagged, stop retried.
    assert paid(pro, 998, "pro-renew", expires_in_days=60)[1]["status"] == "granted"
    assert shop.events("payment_attention")[0][2] == "replaced_subscription_renewed"
    shop.telegram.edit_ok = True
    main.run_subscription_sweep()
    assert shop.q("SELECT renewal_status FROM subscription_agreements ORDER BY id")[0] == ("canceled",)


def test_reopening_a_paid_invoice_never_starts_a_silent_second_subscription(shop):
    payload = buy("pro")
    assert pre_checkout(payload, 998) is False  # mid-period
    age(shop, 29.5)
    assert pre_checkout(payload, 998) is True  # around the renewal date
    assert paid(payload, 998, "dup-sub-1", first=True)[1]["status"] == "granted"
    assert edits(shop)[-1]["telegram_payment_charge_id"] == "dup-sub-1"
    assert shop.events("payment_attention")[0][2] == "second_subscription_on_one_invoice"


# 15 ------------------------------------------------ administration notifications


def test_admin_notifications_are_delivered_from_the_outbox_with_retries(shop):
    payload = buy("pro")
    paid(payload, 998, "renew-1", expires_in_days=60)
    manage("cancel")
    shop.telegram.send_ok = False
    result = main.deliver_subscription_events()
    assert result["sent"] == 0 and result["failed"] >= 3
    assert shop.q("SELECT COUNT(*) FROM subscription_events WHERE sent_at IS NULL")[0][0] == result["failed"]
    shop.telegram.send_ok = True
    assert main.deliver_subscription_events()["sent"] == 0  # backing off, not hammering
    shop.q("UPDATE subscription_events SET next_attempt_at = CURRENT_TIMESTAMP")
    assert main.deliver_subscription_events()["sent"] == result["failed"]
    texts = [m["text"] for m in shop.telegram.of("sendMessage") if m["chat_id"] == 4242]
    purchase = next(t for t in texts if t.startswith("🟢 Новая подписка"))
    for needle in ("SYLVEX ID: 110626010001", f"Telegram ID: {UID}", "Тариф: SYLVEX Pro", "Сумма: 998 XTR",
                   "Статус: active_recurring", "Время: ", "Транзакция: pro-month-1"):
        assert needle in purchase, needle
    assert any(t.startswith("🔁 Подписка продлена") for t in texts)
    assert any(t.startswith("⏹ Автопродление отменено") for t in texts)
    for text in texts:
        assert "123:TEST" not in text and "Buyer" not in text


def test_notification_failure_never_affects_payment_processing(shop, monkeypatch):
    shop.telegram.send_ok = False
    buy("pro")
    assert shop.balance() == START + 300 and status()["state"] == "active_recurring"
    # The delivery worker survives its own failures (one loop iteration with
    # the outbox unreachable), and payments never wait for it.
    monkeypatch.setattr(orders, "claim_events", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("db down")))
    errors = []
    monkeypatch.setattr(main, "prostudio_error", lambda name, exc, **kw: errors.append((name, str(exc))))

    async def stop(_seconds):
        raise asyncio.CancelledError

    monkeypatch.setattr(main.asyncio, "sleep", stop)
    with pytest.raises(asyncio.CancelledError):
        run(main.subscription_events_worker_loop())
    assert errors == [("SUBSCRIPTION_EVENTS_WORKER_FAILED", "db down")]
    assert shop.balance() == START + 300


# 16 ------------------------------------------------ database and Telegram failures


def test_a_failure_inside_the_payment_transaction_grants_nothing_and_is_replayed(shop, monkeypatch):
    code, body = invoice("plan_pro_month")
    payload = orders.order_payload(body["order_id"])
    original = orders._add_credits
    monkeypatch.setattr(orders, "_add_credits", lambda *a: (_ for _ in ()).throw(RuntimeError("db write failed")))
    _, result = paid(payload, 998, "c-1", first=True)
    assert result["status"] == "queued"  # durably in the inbox; acknowledged to Telegram
    assert shop.balance() == START and shop.q("SELECT COUNT(*) FROM purchases")[0][0] == 0
    assert shop.q("SELECT COUNT(*) FROM subscription_agreements")[0][0] == 0
    assert shop.q("SELECT status FROM payment_inbox WHERE charge_id = 'c-1'") == [("pending",)]
    assert shop.events("payment_error")[0][2] == "finalize_failed"
    monkeypatch.setattr(orders, "_add_credits", original)
    shop.q("UPDATE payment_inbox SET next_attempt_at = CURRENT_TIMESTAMP")
    assert main.replay_star_payments()["processed"] == 1  # automatic recovery
    assert paid(payload, 998, "c-1", first=True)[1]["status"] == "duplicate"  # Telegram redelivery
    assert shop.balance() == START + 300
    assert shop.q("SELECT status FROM payment_inbox WHERE charge_id = 'c-1'") == [("processed",)]


def test_rejected_star_payments_are_reported(shop):
    payload = buy("pro")
    for amount, currency, uid in ((1, "XTR", UID), (998, "XTR", OTHER)):
        assert paid(payload, amount, f"bad-{amount}-{uid}", currency=currency, uid=uid)[1]["status"] == "rejected"
    assert {e[2] for e in shop.events("payment_error")} == {"amount_mismatch", "payer_mismatch"}
    assert shop.balance() == START + 300 and shop.balance(OTHER) == START


def test_forged_notifications_grant_nothing(shop):
    payload = buy("pro")
    assert paid(payload, 998, "f1", headers={})[0] == 401
    assert paid(payload, 998, "f2", headers={"X-Telegram-Bot-Api-Secret-Token": "wrong"})[0] == 401
    assert paid(orders.order_payload("f" * 32), 998, "f3")[1]["status"] == "rejected"
    assert paid(payload, 998, "")[0] == 400  # no charge id: not a confirmed payment
    assert shop.balance() == START + 300
    assert manage("cancel", uid=OTHER)[1]["error"] == "no_recurring_subscription"


def test_management_routes_require_a_verified_telegram_user():
    from services.security import PUBLIC_POSTS, TELEGRAM_BLOCKED_PURCHASE_ROUTES
    for route in ("status", "cancel", "reactivate", "change"):
        path = f"/api/public/subscription/{route}"
        assert path not in PUBLIC_POSTS and path not in TELEGRAM_BLOCKED_PURCHASE_ROUTES


# limits ------------------------------------------------


def test_recurring_prices_above_10000_stars_never_reach_telegram(shop):
    with pytest.raises(tg.CatalogError) as err:
        tg.check_invoice_amount(10001, tg.SUBSCRIPTION_PERIOD_SECONDS)
    assert err.value.code == "subscription_amount_above_limit"
    calls = len(shop.telegram.calls)
    with pytest.raises(tg.CatalogError):
        main.create_store_stars_invoice_link({"order_id": "o", "title": "SYLVEX", "stars": 10001, "subscription_period": 2592000})
    assert len(shop.telegram.calls) == calls
    assert all(tg.resolve(f"plan_{plan}_month")["stars"] <= 10000 for plan in MONTHLY)


# 19 ------------------------------------------------ credit purchases stay one-time


@pytest.mark.parametrize("product_id,credits,stars", [("pack_1000", None, 998), ("pack_20000", None, 19960),
                                                      ("credits_custom", "1234", 1232)])
def test_credit_purchases_stay_one_time_even_with_a_subscription(shop, product_id, credits, stars):
    buy("pro")
    code, body = invoice(product_id, **({"credits": credits} if credits else {}))
    assert code == 200 and "subscription_period" not in shop.telegram.of("createInvoiceLink")[-1]
    payload = orders.order_payload(body["order_id"])
    before = shop.balance()
    assert paid(payload, stars, "pack-1", recurring=False)[1]["status"] == "granted"
    assert paid(payload, stars, "pack-2")[1]["status"] == "rejected"
    assert shop.balance() == before + (int(credits) if credits else int(product_id.split("_")[1]))
    assert status()["plan_key"] == "pro_month" and status()["auto_renew"]


# 14 (legacy) ------------------------------------------------ existing subscribers


def test_existing_subscribers_and_history_are_unchanged(shop):
    shop.q("INSERT INTO subscriptions (telegram_id, subscription_type, payment_method, amount, currency, expires_at, status, charge_id) "
           "VALUES (%s, 'month', 'telegram_stars_subscription', 499, 'XTR', CURRENT_TIMESTAMP + INTERVAL '10 days', 'active', 'legacy-1')", (UID,))
    shop.q("INSERT INTO purchases (telegram_id, provider, credits, amount, currency, payload, charge_id) "
           "VALUES (%s, 'crypto_pay', 500, 500, 'USDT', 'sylvex_order:x', 'crypto-old')", (UID,))
    orders.ensure_order_tables(shop.connect)
    orders.ensure_order_tables(shop.connect)  # idempotent
    sub = status()
    assert sub["state"] == "active_one_time" and sub["plan_key"] == "month" and not sub["auto_renew"]
    assert manage("cancel")[1]["error"] == "no_recurring_subscription" and not edits(shop)
    assert shop.q("SELECT provider, credits FROM purchases WHERE charge_id = 'crypto-old'") == [("crypto_pay", 500)]
    assert shop.balance() == START


# 5 (architecture) ------------------------------------------------ future plan benefits


def test_overlapping_entitlements_can_add_up_future_allowances(shop):
    buy("starter", "year")
    buy("pro", "month", confirm=True)
    plans = orders.valid_entitlement_plans(shop.connect, UID)
    assert plans == ["pro_month", "starter_year"]
    example = {"starter": {"saved_characters": 5}, "pro": {"saved_characters": 10}}
    assert orders.combined_allowance(plans, example, "saved_characters") == 15
    assert orders.combined_allowance(plans, {}, "saved_characters") == 0  # nothing defined or enforced yet
    assert tg.PLAN_ALLOWANCES == {}
