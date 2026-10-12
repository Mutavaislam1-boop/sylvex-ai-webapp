"""Durable processing of confirmed Telegram Stars payments in the webapp.

SIMULATED: the real webhook, payment inbox, payment module, replay and
reconciliation run against a disposable PostgreSQL
(SYLVEX_TEST_DATABASE_URL, skipped otherwise). Telegram is a fake: webhook
deliveries are calls to the endpoint (Telegram redelivers anything not
answered with 2xx), getStarTransactions serves a fake transaction history.
Database outages are simulated by making shop_db fail; durations are the
number of Telegram redelivery attempts they would span.
"""
import asyncio
import json
import os
import threading
import time

import pytest

import main
from services import payment_inbox as inbox
from services import shop_orders as orders
from services import telegram_catalog as tg

DATABASE = os.getenv("SYLVEX_TEST_DATABASE_URL")
UID = 990111
DAY = 86400
HOOK = {"X-Telegram-Bot-Api-Secret-Token": "hook"}


class FakeRequest:
    def __init__(self, body, headers=None):
        self._body = body
        self.headers = headers or {}

    async def json(self):
        return json.loads(json.dumps(self._body))


def body_of(response):
    if isinstance(response, dict):
        return 200, response
    return response.status_code, json.loads(response.body)


class FakeTelegram:
    def __init__(self):
        self.calls = []
        self.transactions = []

    def post(self, url, json=None, timeout=None, **kwargs):
        method = url.rsplit("/", 1)[-1]
        self.calls.append((method, json))
        if method == "getStarTransactions":
            page = self.transactions[json["offset"]:json["offset"] + json["limit"]]
            body = {"ok": True, "result": {"transactions": page}}
        elif method == "createInvoiceLink":
            body = {"ok": True, "result": "https://t.me/$invoice"}
        else:
            body = {"ok": True, "result": True}
        return type("R", (), {"status_code": 200, "content": b"1", "json": lambda self: body})()


@pytest.fixture
def shop(monkeypatch, tmp_path):
    if not DATABASE:
        pytest.skip("Set SYLVEX_TEST_DATABASE_URL to a disposable PostgreSQL database")
    import psycopg2

    state = {"down": False}

    def raw_connect():
        return psycopg2.connect(DATABASE)

    def connect():
        if state["down"]:
            raise psycopg2.OperationalError("could not connect to server: Connection refused")
        return raw_connect()

    conn = raw_connect()
    with conn.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS payment_inbox, payment_reconcile_state, subscription_events, subscription_payments, "
                    "subscription_agreements, shop_orders, purchases, subscriptions, users CASCADE")
        cur.execute("CREATE TABLE users (telegram_id BIGINT PRIMARY KEY, first_name TEXT, balance INTEGER DEFAULT 0, subscription TEXT DEFAULT 'free')")
        cur.execute("""CREATE TABLE purchases (id SERIAL PRIMARY KEY, telegram_id BIGINT NOT NULL, provider TEXT NOT NULL, credits INTEGER DEFAULT 0,
                       amount INTEGER DEFAULT 0, currency TEXT DEFAULT 'USD', payload TEXT, charge_id TEXT UNIQUE, status TEXT DEFAULT 'completed',
                       created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
        cur.execute("""CREATE TABLE subscriptions (id SERIAL PRIMARY KEY, telegram_id BIGINT NOT NULL, subscription_type TEXT, payment_method TEXT,
                       amount INTEGER DEFAULT 0, currency TEXT DEFAULT 'USD', starts_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, expires_at TIMESTAMP,
                       status TEXT DEFAULT 'active', charge_id TEXT UNIQUE, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
        cur.execute("INSERT INTO users (telegram_id, first_name, balance) VALUES (%s, 'Buyer', 10)", (UID,))
    conn.commit()
    conn.close()
    orders.ensure_order_tables(raw_connect)
    inbox.ensure_inbox_tables(raw_connect)

    telegram = FakeTelegram()
    monkeypatch.setattr(main.requests, "post", telegram.post)
    monkeypatch.setattr(main, "shop_db", connect)
    monkeypatch.setattr(main, "ensure_payment_tables", lambda: None)
    monkeypatch.setattr(main, "_SHOP_ORDERS_READY", True)
    monkeypatch.setattr(main, "log_user_event", lambda **kwargs: None)
    monkeypatch.setattr(main, "send_subscription_congratulations", lambda *args, **kwargs: True)
    monkeypatch.setattr(main, "BOT_TOKEN", "123:TEST")
    monkeypatch.setattr(main, "TELEGRAM_PAYMENT_WEBHOOK_SECRET", "hook")
    monkeypatch.setattr(main, "PAYMENT_SPOOL", inbox.Spool(""))

    def q(sql, params=()):
        c = raw_connect()
        try:
            with c.cursor() as cur:
                cur.execute(sql, params)
                return cur.fetchall() if cur.description else None
        finally:
            c.commit()
            c.close()

    def balance():
        return q("SELECT balance FROM users WHERE telegram_id = %s", (UID,))[0][0]

    def order(product_id, confirmed=False):
        product = tg.resolve(product_id)
        return orders.create_order(raw_connect, UID, product, "telegram_stars", 3600, confirmed), product

    def grants(charge):
        return q("SELECT COUNT(*) FROM purchases WHERE charge_id = %s", (charge,))[0][0]

    return type("Shop", (), {"state": state, "raw_connect": staticmethod(raw_connect), "q": staticmethod(q),
                             "balance": staticmethod(balance), "order": staticmethod(order),
                             "grants": staticmethod(grants), "telegram": telegram, "tmp": tmp_path})


def update(order_row, product, charge, recurring=True, first=True, expires_in_days=30, paid_at=None):
    payment = {"currency": "XTR", "total_amount": product["stars"], "invoice_payload": f"sylvex_order:{order_row['order_id']}",
               "telegram_payment_charge_id": charge, "provider_payment_charge_id": ""}
    if recurring:
        payment.update(is_recurring=True, subscription_expiration_date=int(time.time()) + expires_in_days * DAY)
        if first:
            payment["is_first_recurring"] = True
    return {"message": {"from": {"id": UID}, "date": int(paid_at or time.time()), "successful_payment": payment}}


def deliver(upd):
    """One Telegram webhook delivery; returns (http status, body)."""
    return body_of(asyncio.run(main.public_stars_webhook(FakeRequest(upd, HOOK))))


def deliver_until_acknowledged(upd, attempts=50):
    """Telegram redelivers until it gets a 2xx."""
    for n in range(1, attempts + 1):
        code, body = deliver(upd)
        if code < 300:
            return n, body
    return attempts, None


def star_tx(charge, order_row, product, date, period=None):
    source = {"type": "user", "transaction_type": "invoice_payment", "user": {"id": UID, "is_bot": False, "first_name": "B"},
              "invoice_payload": f"sylvex_order:{order_row['order_id']}"}
    if period:
        source["subscription_period"] = period
    return {"id": charge, "amount": product["stars"], "date": int(date), "source": source}


# Database outages during webhook delivery


@pytest.mark.parametrize("failed_deliveries", [2, 6, 30], ids=["10_seconds", "1_minute", "extended_within_retention"])
def test_webhook_payment_during_an_outage_is_refused_until_recorded_then_granted_once(shop, failed_deliveries):
    order_row, product = shop.order("plan_pro_month")
    upd = update(order_row, product, "w-outage")
    shop.state["down"] = True
    for _ in range(failed_deliveries):
        code, body = deliver(upd)
        assert code == 503 and body["error"] == "payment_not_recorded"  # not acknowledged
    shop.state["down"] = False
    code, body = deliver(upd)
    assert code == 200 and body["status"] == "granted"
    assert shop.balance() == 10 + 300 and shop.grants("w-outage") == 1
    assert deliver(upd)[1]["status"] == "duplicate"
    assert shop.q("SELECT status, source FROM payment_inbox") == [("processed", "webhook")]


def test_webhook_spool_acknowledges_during_an_outage_and_survives_a_restart(shop, monkeypatch):
    monkeypatch.setattr(main, "PAYMENT_SPOOL", inbox.Spool(str(shop.tmp)))
    order_row, product = shop.order("pack_10000")
    upd = update(order_row, product, "w-spool", recurring=False)
    shop.state["down"] = True
    code, body = deliver(upd)
    assert code == 200 and body["status"] == "spooled"
    assert main.replay_star_payments()["error"] == "OperationalError"  # still down: nothing lost
    monkeypatch.setattr(main, "PAYMENT_SPOOL", inbox.Spool(str(shop.tmp)))  # webapp restart
    shop.state["down"] = False
    counts = main.replay_star_payments()
    assert counts["spooled"] == 1 and counts["processed"] == 1
    assert shop.balance() == 10 + 10000 and shop.grants("w-spool") == 1
    assert list(shop.tmp.glob("payment-*.json")) == []


def test_beyond_telegram_retention_reconciliation_recovers_the_payment(shop):
    monthly, monthly_product = shop.order("plan_max_month")
    annual, annual_product = shop.order("plan_starter_year")
    pack, pack_product = shop.order("pack_500")
    shop.state["down"] = True
    for upd in (update(monthly, monthly_product, "lost-m"), update(annual, annual_product, "lost-a", recurring=False),
                update(pack, pack_product, "lost-p", recurring=False)):
        assert deliver(upd)[0] == 503
    # Telegram gave up redelivering; its transaction history still has them.
    old = time.time() - 3 * DAY
    shop.telegram.transactions = [
        star_tx("lost-m", monthly, monthly_product, old, period=2592000),
        star_tx("lost-a", annual, annual_product, old + 10),
        star_tx("lost-p", pack, pack_product, old + 20),
        {"id": "outgoing", "amount": 5, "date": int(old), "receiver": {"type": "fragment"}},
    ]
    shop.state["down"] = False
    assert main.reconcile_star_payments() == {"examined": 4, "ingested": 3}
    counts = main.replay_star_payments()
    assert counts["processed"] == 3
    assert shop.balance() == 10 + 1000 + 1200 + 500
    assert all(shop.grants(c) == 1 for c in ("lost-m", "lost-a", "lost-p"))
    # Re-running finds nothing new (cursor), and a late delivery is a duplicate.
    assert main.reconcile_star_payments()["ingested"] == 0
    assert deliver(update(pack, pack_product, "lost-p", recurring=False))[1]["status"] == "duplicate"
    assert shop.balance() == 10 + 1000 + 1200 + 500


def test_reconciliation_waits_for_recent_payments_and_skips_known_and_refunded(shop):
    a, a_product = shop.order("pack_1000")
    b, b_product = shop.order("pack_2000")
    deliver(update(a, a_product, "known-1", recurring=False))  # received live
    now = time.time()
    shop.telegram.transactions = [
        star_tx("known-1", a, a_product, now - 3600),
        star_tx("refunded-1", b, b_product, now - 3500),
        {"id": "refunded-1", "amount": b_product["stars"], "date": int(now - 3400), "receiver": {"type": "user", "user": {"id": UID}}},
        star_tx("too-recent", b, b_product, now - 30),
    ]
    assert main.reconcile_star_payments() == {"examined": 3, "ingested": 0}
    assert shop.q("SELECT next_offset FROM payment_reconcile_state") == [(3,)]
    assert shop.q("SELECT COUNT(*) FROM payment_inbox WHERE charge_id = 'too-recent'") == [(0,)]


# Restarts and partial failures


def test_webapp_restart_during_processing_is_recovered_by_redelivery_or_replay(shop, monkeypatch):
    order_row, product = shop.order("plan_pro_month")
    upd = update(order_row, product, "w-crash")

    class Crash(BaseException):
        pass

    real = main.process_star_payment_record
    monkeypatch.setattr(main, "process_star_payment_record", lambda record: (_ for _ in ()).throw(Crash()))
    with pytest.raises(Crash):
        deliver(upd)  # the process dies after storing; Telegram got no answer
    assert shop.q("SELECT status FROM payment_inbox") == [("pending",)] and shop.balance() == 10
    monkeypatch.setattr(main, "process_star_payment_record", real)
    shop.q("UPDATE payment_inbox SET next_attempt_at = CURRENT_TIMESTAMP")
    assert main.replay_star_payments()["processed"] == 1  # the restarted webapp's worker
    assert deliver(upd)[1]["status"] == "duplicate"  # Telegram's redelivery
    assert shop.balance() == 10 + 300 and shop.grants("w-crash") == 1


def test_failure_after_commit_before_acknowledgement(shop, monkeypatch):
    order_row, product = shop.order("plan_ultra_month")
    upd = update(order_row, product, "w-commit")
    real_mark = inbox._mark
    monkeypatch.setattr(inbox, "_mark", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("lost after commit")))
    assert deliver(upd)[1]["status"] == "granted"
    assert shop.q("SELECT status FROM payment_inbox") == [("pending",)]
    monkeypatch.setattr(inbox, "_mark", real_mark)
    assert deliver(upd)[1]["status"] == "duplicate"  # response lost: Telegram redelivers
    shop.q("UPDATE payment_inbox SET next_attempt_at = CURRENT_TIMESTAMP")
    main.replay_star_payments()
    assert shop.balance() == 10 + 2500 and shop.grants("w-commit") == 1
    assert shop.q("SELECT COUNT(*) FROM subscriptions") == [(1,)]


def test_duplicate_deliveries_grant_once(shop):
    order_row, product = shop.order("pack_3000")
    upd = update(order_row, product, "w-dup", recurring=False)
    statuses = [deliver(upd)[1]["status"] for _ in range(4)]
    assert statuses == ["granted", "duplicate", "duplicate", "duplicate"]
    assert shop.balance() == 10 + 3000


def test_renewal_during_an_outage_extends_once(shop):
    order_row, product = shop.order("plan_pro_month")
    assert deliver(update(order_row, product, "first-1"))[1]["status"] == "granted"
    before = shop.q("SELECT expires_at FROM subscriptions")[0][0]
    renewal = update(order_row, product, "renew-1", first=False, expires_in_days=60)
    shop.state["down"] = True
    attempts, body = deliver_until_acknowledged(renewal, attempts=5)
    assert body is None  # all refused during the outage
    shop.state["down"] = False
    attempts, body = deliver_until_acknowledged(renewal)
    assert body["status"] == "granted"
    deliver(renewal)
    after = shop.q("SELECT expires_at FROM subscriptions")[0][0]
    assert 29 < (after - before).total_seconds() / DAY < 31
    assert shop.balance() == 10 + 600 and shop.grants("renew-1") == 1


def test_concurrent_webhook_and_bot_processing_grant_once(shop):
    """The webhook and the polling bot (same shared modules) process the same
    charges at the same moment."""
    charges = []
    for n in range(8):
        order_row, product = shop.order("pack_1000")
        charges.append((order_row, product, f"race-{n}"))

    def bot_side(order_row, product, charge, barrier):
        record = inbox.payment_record(UID, {"currency": "XTR", "total_amount": product["stars"],
                                            "invoice_payload": f"sylvex_order:{order_row['order_id']}",
                                            "telegram_payment_charge_id": charge}, paid_at=int(time.time()))
        barrier.wait()
        inbox.record_durably(shop.raw_connect, record, "bot")
        inbox.process(shop.raw_connect, record, lambda r: orders.finalize_order(
            shop.raw_connect, r["order_id"], "telegram_stars", "XTR", r["amount"], r["charge_id"], UID,
            inbox.recurring_fields(r)))

    def webhook_side(order_row, product, charge, barrier):
        barrier.wait()
        deliver(update(order_row, product, charge, recurring=False))

    for order_row, product, charge in charges:
        barrier = threading.Barrier(3)
        threads = [threading.Thread(target=fn, args=(order_row, product, charge, barrier))
                   for fn in (bot_side, webhook_side, webhook_side)]
        [t.start() for t in threads]
        [t.join() for t in threads]
    assert shop.balance() == 10 + 8 * 1000
    assert all(shop.grants(charge) == 1 for _, _, charge in charges)
    assert shop.q("SELECT COUNT(*) FROM payment_inbox WHERE status = 'processed'") == [(8,)]


def test_recovery_never_depends_on_administration_notifications(shop, monkeypatch):
    order_row, product = shop.order("plan_pro_month")
    monkeypatch.setattr(orders, "record_event_now", lambda *a, **k: False)  # notifications unavailable
    original = orders._add_credits
    monkeypatch.setattr(orders, "_add_credits", lambda *a: (_ for _ in ()).throw(RuntimeError("flaky")))
    assert deliver(update(order_row, product, "w-noadmin"))[1]["status"] == "queued"
    monkeypatch.setattr(orders, "_add_credits", original)
    monkeypatch.setattr(main, "deliver_subscription_events", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("never called")))
    shop.q("UPDATE payment_inbox SET next_attempt_at = CURRENT_TIMESTAMP")
    assert main.replay_star_payments()["processed"] == 1
    assert shop.balance() == 10 + 300 and shop.grants("w-noadmin") == 1


def test_pending_payments_are_retried_with_backoff_until_the_database_returns(shop):
    order_row, product = shop.order("pack_1000")
    record = inbox.payment_record(UID, {"currency": "XTR", "total_amount": product["stars"],
                                        "invoice_payload": f"sylvex_order:{order_row['order_id']}",
                                        "telegram_payment_charge_id": "w-backoff"}, paid_at=int(time.time()))
    inbox.store(shop.raw_connect, record, "webhook")
    shop.state["down"] = True
    for _ in range(3):
        assert main.replay_star_payments()["error"] == "OperationalError"
    shop.state["down"] = False
    assert main.replay_star_payments()["processed"] == 1
    assert shop.balance() == 10 + 1000 and inbox.pending_count(shop.raw_connect) == 0
