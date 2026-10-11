"""Mini App Store endpoints: catalog, Stars/Crypto order invoices, Crypto
settlement, order status and the Stars webhook order path.

Providers are always fakes (no network, no real payments). Ledger tests use
a disposable PostgreSQL in SYLVEX_TEST_DATABASE_URL (skipped otherwise)."""
import asyncio
import json
import os
from pathlib import Path

import pytest

import main
from services import shop_catalog as catalog
from services import shop_orders as orders

DATABASE = os.getenv("SYLVEX_TEST_DATABASE_URL")
UID = 990077
ROOT = Path(__file__).resolve().parent.parent


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


@pytest.fixture
def shop(monkeypatch):
    if not DATABASE:
        pytest.skip("Set SYLVEX_TEST_DATABASE_URL to a disposable PostgreSQL database")
    import psycopg2

    def connect():
        return psycopg2.connect(DATABASE)

    conn = connect()
    with conn.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS shop_orders, purchases, subscriptions, users CASCADE")
        cur.execute("CREATE TABLE users (telegram_id BIGINT PRIMARY KEY, first_name TEXT, balance INTEGER DEFAULT 0, subscription TEXT DEFAULT 'free')")
        cur.execute("""CREATE TABLE purchases (id SERIAL PRIMARY KEY, telegram_id BIGINT NOT NULL, provider TEXT NOT NULL, credits INTEGER DEFAULT 0,
                       amount INTEGER DEFAULT 0, currency TEXT DEFAULT 'USD', payload TEXT, charge_id TEXT UNIQUE, status TEXT DEFAULT 'completed',
                       created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
        cur.execute("""CREATE TABLE subscriptions (id SERIAL PRIMARY KEY, telegram_id BIGINT NOT NULL, subscription_type TEXT, payment_method TEXT,
                       amount INTEGER DEFAULT 0, currency TEXT DEFAULT 'USD', starts_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, expires_at TIMESTAMP,
                       status TEXT DEFAULT 'active', charge_id TEXT UNIQUE, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
        cur.execute("INSERT INTO users (telegram_id, first_name, balance) VALUES (%s, 'Buyer', 0)", (UID,))
    conn.commit()
    conn.close()

    monkeypatch.setattr(main, "shop_db", connect)
    monkeypatch.setattr(main, "ensure_payment_tables", lambda: None)
    monkeypatch.setattr(main, "_SHOP_ORDERS_READY", False)
    monkeypatch.setattr(main, "log_user_event", lambda **kwargs: None)
    congrats = []
    monkeypatch.setattr(main, "send_subscription_congratulations", lambda *args, **kwargs: congrats.append(args))
    monkeypatch.setattr(main, "get_user_state", lambda telegram_id, **kwargs: {"telegram_id": telegram_id})
    monkeypatch.setattr(main, "BOT_TOKEN", "123:TEST")
    monkeypatch.setattr(main, "CRYPTO_API_KEY", "crypto-test")
    tasks = []
    monkeypatch.setattr(main.asyncio, "create_task", lambda coro: (tasks.append(coro), coro.close()))

    def balance():
        c = connect()
        try:
            with c.cursor() as cur:
                cur.execute("SELECT balance FROM users WHERE telegram_id = %s", (UID,))
                return cur.fetchone()[0]
        finally:
            c.close()

    return type("Shop", (), {"connect": staticmethod(connect), "balance": staticmethod(balance), "congrats": congrats, "tasks": tasks})


class FakeTelegram:
    def __init__(self):
        self.invoices = []

    def post(self, url, json=None, timeout=None, **kwargs):
        assert url.endswith("/createInvoiceLink")
        self.invoices.append(json)
        return type("R", (), {"status_code": 200, "content": b"1", "json": lambda self: {"ok": True, "result": "https://t.me/$invoice"}})()


@pytest.mark.parametrize("product_id,usd,stars", [("plan_starter_month", None, 230), ("plan_pro_year", None, 4416),
                                                  ("pack_20000", None, 9200), ("credits_custom", "12.34", 568)])
def test_stars_invoice_for_a_store_product_creates_an_order(shop, monkeypatch, product_id, usd, stars):
    telegram = FakeTelegram()
    monkeypatch.setattr(main.requests, "post", telegram.post)
    status, body = body_of(run(main.public_stars_invoice(FakeRequest({"telegram_id": UID, "product_id": product_id, "usd": usd,
                                                                       "credits": 999999, "stars": 1}))))
    assert status == 200 and body["ok"] and body["invoice_url"]
    invoice = telegram.invoices[0]
    assert invoice["currency"] == "XTR" and invoice["prices"][0]["amount"] == stars
    assert invoice["payload"] == orders.order_payload(body["order_id"])
    assert len(invoice["title"]) <= 32
    order = orders.get_order(shop.connect, body["order_id"])
    # Client-sent credits/stars are ignored; the server catalog decides.
    expected = catalog.resolve_product(product_id, usd)
    assert (order["credits"], order["stars"], order["usd_cents"]) == (expected["credits"], stars, expected["usd_cents"])


@pytest.mark.parametrize("body,error", [
    ({"product_id": "plan_gold_month"}, "unknown_product"),
    ({"product_id": "plan_max_year"}, "stars_amount_above_limit"),
    ({"product_id": "credits_custom", "usd": "0.50"}, "amount_out_of_range"),
    ({"product_id": "credits_custom", "usd": "300"}, "stars_amount_above_limit"),
    ({"product_id": "credits_custom", "usd": "12.345"}, "invalid_amount"),
])
def test_stars_invoice_rejects_invalid_products(shop, monkeypatch, body, error):
    monkeypatch.setattr(main.requests, "post", lambda *a, **k: pytest.fail("no invoice may be created"))
    status, payload = body_of(run(main.public_stars_invoice(FakeRequest({"telegram_id": UID, **body}))))
    assert status == 400 and payload["error"] == error


def test_legacy_pack_requests_keep_their_original_flow(shop, monkeypatch):
    seen = {}

    def legacy(telegram_id, pack_id, item, charge_id):
        seen.update(pack_id=pack_id, stars=item["stars"])
        return "https://t.me/$legacy"
    monkeypatch.setattr(main, "create_telegram_stars_invoice_link", legacy)
    status, body = body_of(run(main.public_stars_invoice(FakeRequest({"telegram_id": UID, "pack_id": "sub_month"}))))
    assert status == 200 and body["invoice_url"] == "https://t.me/$legacy" and seen == {"pack_id": "sub_month", "stars": 230}


def test_stars_unconfigured_is_reported_before_any_order(shop, monkeypatch):
    monkeypatch.setattr(main, "BOT_TOKEN", "")
    status, body = body_of(run(main.public_stars_invoice(FakeRequest({"telegram_id": UID, "product_id": "pack_500"}))))
    assert status == 503 and body["error"] == "stars_not_configured"


class FakeCryptoPay:
    def __init__(self):
        self.created = []
        self.status = "active"
        self.amount = None
        self.asset = "USDT"
        self.payload = None

    def request(self, method, payload=None):
        if method == "createInvoice":
            self.created.append(payload)
            self.payload = payload["payload"]
            self.amount = payload["amount"]
            return {"invoice_id": 4242, "status": "active", "mini_app_invoice_url": "https://t.me/CryptoBot/app?startapp=x"}
        if method == "getInvoices":
            return {"items": [{"invoice_id": 4242, "status": self.status, "amount": self.amount, "asset": self.asset, "payload": self.payload}]}
        raise AssertionError(method)


@pytest.mark.parametrize("product_id,usd,credits", [("plan_creator_year", None, 66000), ("pack_10000", None, 10000),
                                                    ("credits_custom", "1000", 100000), ("credits_custom", "1", 100)])
def test_crypto_order_is_settled_once_after_the_provider_reports_paid(shop, monkeypatch, product_id, usd, credits):
    crypto = FakeCryptoPay()
    monkeypatch.setattr(main, "crypto_pay_request", crypto.request)
    status, body = body_of(run(main.public_crypto_invoice(FakeRequest({"telegram_id": UID, "product_id": product_id, "usd": usd}))))
    assert status == 200 and body["url"] and shop.tasks
    expected = catalog.resolve_product(product_id, usd)
    assert crypto.created[0]["asset"] == "USDT" and crypto.created[0]["amount"] == f"{expected['usd_cents'] / 100:.2f}"
    status_req = FakeRequest({"telegram_id": UID, "order_id": body["order_id"]})
    _, pending = body_of(run(main.public_store_order_status(status_req)))
    assert pending["order"]["status"] == "pending" and shop.balance() == 0
    crypto.status = "paid"
    _, paid = body_of(run(main.public_store_order_status(status_req)))
    assert paid["order"]["status"] == "paid" and shop.balance() == credits
    _, again = body_of(run(main.public_store_order_status(status_req)))
    assert again["order"]["status"] == "paid" and shop.balance() == credits
    if expected["kind"] == "subscription":
        assert shop.congrats and shop.congrats[0][1]["plan_key"] == expected["plan_key"]


def test_crypto_paid_invoice_with_a_wrong_amount_or_payload_grants_nothing(shop, monkeypatch):
    crypto = FakeCryptoPay()
    monkeypatch.setattr(main, "crypto_pay_request", crypto.request)
    _, body = body_of(run(main.public_crypto_invoice(FakeRequest({"telegram_id": UID, "product_id": "pack_500"}))))
    crypto.status, crypto.amount = "paid", "1.00"
    _, result = body_of(run(main.public_store_order_status(FakeRequest({"telegram_id": UID, "order_id": body["order_id"]}))))
    assert result["order"]["status"] == "pending" and shop.balance() == 0
    crypto.amount, crypto.payload = "5.00", orders.order_payload("f" * 32)
    _, result = body_of(run(main.public_store_order_status(FakeRequest({"telegram_id": UID, "order_id": body["order_id"]}))))
    assert result["order"]["status"] == "pending" and shop.balance() == 0


def test_expired_crypto_invoice_closes_the_order(shop, monkeypatch):
    crypto = FakeCryptoPay()
    monkeypatch.setattr(main, "crypto_pay_request", crypto.request)
    _, body = body_of(run(main.public_crypto_invoice(FakeRequest({"telegram_id": UID, "product_id": "pack_500"}))))
    crypto.status = "expired"
    _, result = body_of(run(main.public_store_order_status(FakeRequest({"telegram_id": UID, "order_id": body["order_id"]}))))
    assert result["order"]["status"] == "expired" and shop.balance() == 0


def test_order_status_is_private_to_its_buyer(shop, monkeypatch):
    crypto = FakeCryptoPay()
    monkeypatch.setattr(main, "crypto_pay_request", crypto.request)
    _, body = body_of(run(main.public_crypto_invoice(FakeRequest({"telegram_id": UID, "product_id": "pack_500"}))))
    status, result = body_of(run(main.public_store_order_status(FakeRequest({"telegram_id": UID + 1, "order_id": body["order_id"]}))))
    assert status == 404
    status, result = body_of(run(main.public_store_order_status(FakeRequest({"telegram_id": UID, "order_id": "../etc"}))))
    assert status == 400


def test_stars_webhook_validates_and_finalizes_orders(shop, monkeypatch):
    telegram = FakeTelegram()
    monkeypatch.setattr(main.requests, "post", telegram.post)
    _, body = body_of(run(main.public_stars_invoice(FakeRequest({"telegram_id": UID, "product_id": "plan_pro_month"}))))
    payload = orders.order_payload(body["order_id"])
    monkeypatch.setattr(main, "TELEGRAM_PAYMENT_WEBHOOK_SECRET", "hook")
    answers = []
    monkeypatch.setattr(main, "_answer_stars_pre_checkout", lambda qid, ok, msg="": answers.append(ok) or True)
    headers = {"X-Telegram-Bot-Api-Secret-Token": "hook"}
    pre = {"pre_checkout_query": {"id": "q", "from": {"id": UID}, "currency": "XTR", "total_amount": 460, "invoice_payload": payload}}
    run(main.public_stars_webhook(FakeRequest(pre, headers)))
    bad = {"pre_checkout_query": {"id": "q", "from": {"id": UID}, "currency": "XTR", "total_amount": 1, "invoice_payload": payload}}
    run(main.public_stars_webhook(FakeRequest(bad, headers)))
    assert answers == [True, False]
    paid = {"message": {"from": {"id": UID}, "successful_payment": {"currency": "XTR", "total_amount": 460, "invoice_payload": payload,
                                                                   "telegram_payment_charge_id": "tg-1"}}}
    _, first = body_of(run(main.public_stars_webhook(FakeRequest(paid, headers))))
    _, second = body_of(run(main.public_stars_webhook(FakeRequest(paid, headers))))
    assert first["status"] == "granted" and second["status"] == "duplicate"
    assert shop.balance() == 300


# ------------------------------------------------ generation examples

_EVAL_LIST_JS = r"""
const fs = require('fs'), vm = require('vm');
const lines = fs.readFileSync(process.argv[1], 'utf8').split('\n');
const name = process.argv[2];
const start = lines.findIndex(l => l.startsWith(`const ${name} = [`));
let end = start; while (!/^\];\s*$/.test(lines[end])) end++;
const body = lines.slice(start, end + 1).join('\n').replace(`const ${name} = `, '').replace(/;\s*$/, '');
const ctx = new Proxy({}, {has: () => true, get: (t, k) => k === Symbol.unscopables ? undefined : (k in globalThis ? globalThis[k] : [])});
console.log(JSON.stringify(vm.runInNewContext('with(ctx){(' + body + ')}', {ctx}).map(m => m.id)));
"""


def _frontend_list(name):
    import subprocess
    out = subprocess.run(["node", "-e", _EVAL_LIST_JS, str(ROOT / "webapp" / "js" / "cabinet.js"), name],
                         check=True, capture_output=True, text=True).stdout
    return json.loads(out)


@pytest.mark.parametrize("name,candidates", [
    ("IMAGE_MODEL_LIST", catalog.EXAMPLE_IMAGE_MODELS), ("VIDEO_MODELS", catalog.EXAMPLE_VIDEO_MODELS),
    ("MUSIC_MODEL_LIST", catalog.EXAMPLE_MUSIC_MODELS), ("VOICE_MODEL_LIST", catalog.EXAMPLE_VOICE_MODELS),
    ("TEXT_MODEL_LIST", catalog.EXAMPLE_TEXT_MODELS),
])
def test_example_candidates_are_exactly_the_mini_app_model_lists(name, candidates):
    assert [mid for mid, _ in candidates] == _frontend_list(name)


def test_examples_are_the_cheapest_priced_option_per_category(monkeypatch):
    monkeypatch.setitem(main._STORE_EXAMPLES_CACHE, "value", None)
    examples = main.store_generation_examples()
    assert set(examples) == {"photo", "video", "music", "voice", "text"}
    price = main.calculate_generation_price
    for mid, _ in catalog.EXAMPLE_IMAGE_MODELS:
        est = price({"mode": "image", "model": mid, "prompt": "x", "image_options": {"model": mid, "modelId": mid, "count": 1, "size": "auto"}})
        if est.get("pricing_available", True) and est.get("credits"):
            assert est["credits"] >= examples["photo"]["credits"]
    for mid, _ in catalog.EXAMPLE_MUSIC_MODELS:
        est = price({"mode": "music", "model": mid, "prompt": "x", "music_options": {"model": mid}})
        if est.get("credits"):
            assert est["credits"] >= examples["music"]["credits"]
    for mid, _ in catalog.EXAMPLE_TEXT_MODELS:
        if main.text_token_rates(mid):
            assert main.text_tokens_credits(mid, 1000, 1000) >= examples["text"]["credits"]
    # Every example is a real, priced generation of its model.
    assert price({"mode": "video", "model": examples["video"]["model"], "prompt": "x",
                  "video_options": {"model": examples["video"]["model"], "duration": 5,
                                    "resolution": examples["video"]["resolution"]}})["credits"] == examples["video"]["credits"]
    assert price({"mode": "voice", "model": examples["voice"]["model"], "prompt": "x" * 1000,
                  "voice_options": {"model": examples["voice"]["model"]}})["credits"] == examples["voice"]["credits"]
    assert examples["text"]["input_tokens"] == 1000 and examples["text"]["output_tokens"] == 1000
    assert examples["text"]["input_credits"] > 0 and examples["text"]["output_credits"] > 0


def test_video_example_excludes_avatar_edit_and_lip_sync_models(monkeypatch):
    monkeypatch.setitem(main._STORE_EXAMPLES_CACHE, "value", None)
    cap = main.model_capabilities_service.MODEL_CAPABILITIES[main.store_generation_examples()["video"]["model"]]
    assert not cap.avatar and {"text_to_video", "image_to_video"} & set(cap.modes)


def test_catalog_endpoint_is_public_and_complete(monkeypatch):
    from services.security import PUBLIC_GETS
    assert "/api/public/shop/catalog" in PUBLIC_GETS
    response = run(main.public_shop_catalog())
    data = json.loads(response.body)
    assert data["ok"] and data["renewal"] == "manual"
    assert len(data["products"]) == 18 and data["custom"]["min_cents"] == 100 and data["custom"]["max_cents"] == 100000
    assert set(data["examples"]) == {"photo", "video", "music", "voice", "text"}
