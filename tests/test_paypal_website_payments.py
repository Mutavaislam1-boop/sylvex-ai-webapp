"""PayPal now covers every Website payment (SYLVEX Pro Monthly/Yearly
subscriptions and one-time credit purchases), replacing LemonSqueezy for
subscriptions. This exercises the reused PayPal backend machinery
(create_paypal_order/finalize_paypal_capture/save_paypal_subscription/
activate_paypal_subscription_from_event/verify_paypal_webhook) end to end
against a real embedded Postgres (pglite) - the point of these tests is the
DB-level guarantees (idempotent charge_id, backend-authoritative pricing,
atomic credit/subscription application), not application-level bookkeeping,
so mocks would defeat the purpose. Outbound PayPal HTTP calls (webhook
signature verification, order/subscription creation against PayPal itself)
are mocked - there's no real PayPal to talk to in a test run, sandbox or
not, and that surface is pre-existing, unmodified code anyway.

Route handlers are called directly (asyncio.run), same as
test_web_auth_config_endpoint.py - this sandbox's Python can't run
main.py's own startup lifecycle (see validate_runtime()).
"""
import asyncio
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).parent / "support"))
sys.path.insert(0, str(Path(__file__).parent.parent))


def _pglite_available():
    return bool(os.getenv("SYLVEX_TEST_NODE") and os.getenv("SYLVEX_PGLITE_MODULE"))


pytestmark = pytest.mark.skipif(
    not _pglite_available(),
    reason="Set SYLVEX_TEST_NODE and SYLVEX_PGLITE_MODULE to run real-SQL tests",
)


class FakeRequest:
    def __init__(self, payload=None, headers=None, raw_body=None, state=None):
        self._payload = payload if payload is not None else {}
        self.headers = headers or {}
        self._raw_body = raw_body if raw_body is not None else json.dumps(self._payload).encode()
        self.state = state if state is not None else SimpleNamespace()

    async def json(self):
        return dict(self._payload)

    async def body(self):
        return self._raw_body


class FakeResponse:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload
        self.text = json.dumps(payload)

    def json(self):
        return self._payload


VALID_WEBHOOK_HEADERS = {
    "paypal-auth-algo": "SHA256withRSA",
    "paypal-cert-url": "https://api-m.sandbox.paypal.com/cert",
    "paypal-transmission-id": "tx-1",
    "paypal-transmission-sig": "sig-1",
    "paypal-transmission-time": "2026-01-01T00:00:00Z",
}


@pytest.fixture
def env(monkeypatch):
    import main
    from pglite_adapter import Database

    database = Database()
    monkeypatch.setattr(main, "db_connect", lambda *a, **k: database.connect())
    monkeypatch.setattr(main, "DATABASE_URL", "pglite://test")
    monkeypatch.setattr(main, "PAYPAL_WEBHOOK_ID", "WH-TEST-ID")
    monkeypatch.setattr(main, "PAYPAL_CLIENT_ID", "test-client-id")
    monkeypatch.setattr(main, "PAYPAL_CLIENT_SECRET", "test-client-secret")
    monkeypatch.setattr(main, "PAYPAL_PRO_MONTHLY_PLAN_ID", "P-16M2575467314214JNKW33SQ")
    monkeypatch.setattr(main, "PAYPAL_PRO_YEARLY_PLAN_ID", "P-2V117840XB8907707NKW33SY")
    monkeypatch.setattr(main, "BOT_TOKEN", None)  # no Telegram congratulation messages in tests
    monkeypatch.setenv("MEDIA_SIGNING_SECRET", "test-signing-secret")  # services.security.signing_key()
    monkeypatch.setattr(main, "paypal_access_token", lambda api_base=None: "fake-access-token")
    monkeypatch.setattr(
        main.requests, "post",
        lambda url, **k: FakeResponse(200, {"verification_status": "SUCCESS"})
        if url.endswith("/v1/notifications/verify-webhook-signature")
        else (_ for _ in ()).throw(AssertionError(f"unexpected POST {url}")),
    )

    with database.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "CREATE TABLE users(telegram_id BIGINT PRIMARY KEY, first_name TEXT, "
                "username TEXT, balance INTEGER DEFAULT 0, subscription TEXT, created_at TEXT)"
            )
    yield main, database
    database.close()


def _run(coro):
    return asyncio.run(coro)


def _unwrap(response):
    # Route handlers return a plain dict on success (FastAPI's routing layer
    # normally wraps that into a 200 JSONResponse) but an explicit
    # JSONResponse on error paths - calling the handler directly, as these
    # tests do, means both shapes have to be normalized here.
    if isinstance(response, dict):
        return 200, response
    return response.status_code, json.loads(response.body)


def _balance(database, telegram_id):
    with database.connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COALESCE(balance, 0) FROM users WHERE telegram_id = %s", (telegram_id,))
            row = cur.fetchone()
            return int(row[0]) if row else None


def _capture_event(order_id, capture_id, amount_usd, status="COMPLETED", currency="USD"):
    return {
        "event_type": "PAYMENT.CAPTURE.COMPLETED",
        "resource": {
            "id": capture_id,
            "status": status,
            "amount": {"value": f"{amount_usd:.2f}", "currency_code": currency},
            "supplementary_data": {"related_ids": {"order_id": order_id}},
        },
    }


def _sale_event(subscription_id, sale_id, amount_usd, currency="USD"):
    return {
        "event_type": "PAYMENT.SALE.COMPLETED",
        "resource": {
            "id": sale_id,
            "billing_agreement_id": subscription_id,
            "amount": {"total": f"{amount_usd:.2f}", "currency": currency},
        },
    }


def _lifecycle_event(event_type, subscription_id):
    return {"event_type": event_type, "resource": {"id": subscription_id}}


def _fake_order_response(order_id="ORDER-TEST"):
    return FakeResponse(201, {
        "id": order_id,
        "status": "CREATED",
        "links": [{"rel": "payer-action", "href": f"https://www.sandbox.paypal.com/checkoutnow?token={order_id}"}],
    })


def _webhook_post(event):
    return FakeRequest(payload=event, headers=VALID_WEBHOOK_HEADERS, raw_body=json.dumps(event).encode())


def _activate_subscription(main, telegram_id, subscription_id, plan_id, plan_type):
    main.save_paypal_subscription(telegram_id, subscription_id, plan_id, plan_type)
    item = main.shop_item("sub_month" if plan_type == "month" else "sub_year")
    event = _sale_event(subscription_id, f"SALE-{subscription_id}", item["usd"])
    _, body = _unwrap(_run(main.public_paypal_webhook(_webhook_post(event))))
    assert body["created"] is True


# ---------------------------------------------------------------------------
# /api/public/config: public, non-secret PayPal fields for the Website
# ---------------------------------------------------------------------------

def test_public_config_reports_paypal_enabled_and_plan_ids(env):
    main, _ = env
    result = _run(main.public_config())
    assert result["paypal_enabled"] is True
    assert result["paypal_client_id"] == "test-client-id"
    assert result["paypal_pro_monthly_plan_id"] == main.PAYPAL_PRO_MONTHLY_PLAN_ID
    assert result["paypal_pro_yearly_plan_id"] == main.PAYPAL_PRO_YEARLY_PLAN_ID


def test_public_config_never_exposes_client_secret(env):
    main, _ = env
    serialized = str(_run(main.public_config()))
    assert "test-client-secret" not in serialized


def test_public_config_reports_disabled_without_credentials(env, monkeypatch):
    main, _ = env
    monkeypatch.setattr(main, "PAYPAL_CLIENT_ID", None)
    monkeypatch.setattr(main, "PAYPAL_CLIENT_SECRET", None)
    result = _run(main.public_config())
    assert result["paypal_enabled"] is False


# ---------------------------------------------------------------------------
# LemonSqueezy: fully removed from new Website payment flows
# ---------------------------------------------------------------------------

def test_lemonsqueezy_checkout_is_discontinued(env):
    main, _ = env
    response = _run(main.public_lemonsqueezy_checkout(FakeRequest({"pack_id": "sub_month", "telegram_id": 111})))
    assert response.status_code == 410
    body = json.loads(response.body)
    assert body == {"ok": False, "error": "lemonsqueezy_discontinued"}


# ---------------------------------------------------------------------------
# Webhook signature verification
# ---------------------------------------------------------------------------

def test_webhook_rejects_missing_signature_headers(env):
    main, _ = env
    event = _capture_event("O1", "C1", 5.0)
    response = _run(main.public_paypal_webhook(FakeRequest(payload=event, headers={}, raw_body=json.dumps(event).encode())))
    assert response.status_code == 401
    assert json.loads(response.body)["error"] == "invalid_signature"


def test_webhook_rejects_failed_verification(env, monkeypatch):
    main, _ = env
    monkeypatch.setattr(
        main.requests, "post",
        lambda url, **k: FakeResponse(200, {"verification_status": "FAILURE"}),
    )
    event = _capture_event("O1", "C1", 5.0)
    response = _run(main.public_paypal_webhook(
        FakeRequest(payload=event, headers=VALID_WEBHOOK_HEADERS, raw_body=json.dumps(event).encode())
    ))
    assert response.status_code == 401
    assert json.loads(response.body)["error"] == "invalid_signature"


# ---------------------------------------------------------------------------
# Token (credit) purchase: Orders + Capture
# ---------------------------------------------------------------------------

def test_token_purchase_credits_the_correct_account_with_backend_priced_amount(env):
    main, database = env
    telegram_id = 900000000101
    item = main.shop_item("pack_500")
    order = {"id": "ORDER-1", "status": "CREATED"}
    main.save_paypal_order(telegram_id, "pack_500", item, order, "https://paypal.example/approve/1")

    event = _capture_event("ORDER-1", "CAP-1", item["usd"])
    status, body = _unwrap(_run(main.public_paypal_webhook(
        FakeRequest(payload=event, headers=VALID_WEBHOOK_HEADERS, raw_body=json.dumps(event).encode())
    )))
    assert status == 200
    assert body["created"] is True
    # 500 credits, exactly SHOP_ITEMS["pack_500"]["credits"] - never a
    # client-supplied number, since nothing in this flow ever sent one.
    assert _balance(database, telegram_id) == item["credits"] == 500


def test_duplicate_capture_webhook_is_idempotent(env):
    main, database = env
    telegram_id = 900000000102
    item = main.shop_item("pack_100")
    order = {"id": "ORDER-2", "status": "CREATED"}
    main.save_paypal_order(telegram_id, "pack_100", item, order, "https://paypal.example/approve/2")

    event = _capture_event("ORDER-2", "CAP-2", item["usd"])

    _, first_body = _unwrap(_run(main.public_paypal_webhook(
        FakeRequest(payload=event, headers=VALID_WEBHOOK_HEADERS, raw_body=json.dumps(event).encode())
    )))
    _, second_body = _unwrap(_run(main.public_paypal_webhook(
        FakeRequest(payload=event, headers=VALID_WEBHOOK_HEADERS, raw_body=json.dumps(event).encode())
    )))
    assert first_body["created"] is True
    assert second_body["created"] is False
    # Credited exactly once despite the webhook firing twice (PayPal itself
    # can and does redeliver webhooks) - charge_id's UNIQUE constraint plus
    # apply_payment()'s ON CONFLICT DO NOTHING is what guarantees this.
    assert _balance(database, telegram_id) == item["credits"] == 100


def test_cancelled_or_failed_payment_never_credits(env):
    main, database = env
    telegram_id = 900000000103
    main.ensure_user_exists(telegram_id)
    item = main.shop_item("pack_100")
    order = {"id": "ORDER-3", "status": "CREATED"}
    main.save_paypal_order(telegram_id, "pack_100", item, order, "https://paypal.example/approve/3")

    event = _capture_event("ORDER-3", "CAP-3", item["usd"], status="DECLINED")
    status, body = _unwrap(_run(main.public_paypal_webhook(
        FakeRequest(payload=event, headers=VALID_WEBHOOK_HEADERS, raw_body=json.dumps(event).encode())
    )))
    assert status == 200
    assert body["created"] is False
    assert _balance(database, telegram_id) == 0


def test_capture_amount_mismatch_from_stored_order_is_ignored_not_trusted(env):
    # The order was created for pack_100 ($1.00); a capture event claiming a
    # different, larger amount must never be trusted at face value - the
    # credited amount always comes from finalize_shop_payment's own item
    # lookup keyed by the stored pack_id, never the webhook payload's amount.
    main, database = env
    telegram_id = 900000000104
    item = main.shop_item("pack_100")
    order = {"id": "ORDER-4", "status": "CREATED"}
    main.save_paypal_order(telegram_id, "pack_100", item, order, "https://paypal.example/approve/4")

    event = _capture_event("ORDER-4", "CAP-4", 999.00)  # forged amount
    status, body = _unwrap(_run(main.public_paypal_webhook(
        FakeRequest(payload=event, headers=VALID_WEBHOOK_HEADERS, raw_body=json.dumps(event).encode())
    )))
    assert status == 200
    assert body["created"] is True
    # Still exactly pack_100's 100 credits, not a penny/credit more.
    assert _balance(database, telegram_id) == 100


# ---------------------------------------------------------------------------
# Subscriptions: Monthly / Yearly
# ---------------------------------------------------------------------------

def test_monthly_subscription_activates_and_credits_bonus(env):
    main, database = env
    telegram_id = 900000000201
    subscription_id = "I-MONTHLY1"
    saved = main.save_paypal_subscription(telegram_id, subscription_id, main.PAYPAL_PRO_MONTHLY_PLAN_ID, "month")
    assert saved is True

    item = main.shop_item("sub_month")
    event = _sale_event(subscription_id, "SALE-1", item["usd"])
    status, body = _unwrap(_run(main.public_paypal_webhook(
        FakeRequest(payload=event, headers=VALID_WEBHOOK_HEADERS, raw_body=json.dumps(event).encode())
    )))
    assert status == 200
    assert body["created"] is True
    assert _balance(database, telegram_id) == item["bonus_credits"]

    with database.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT subscription_type, status FROM subscriptions WHERE telegram_id = %s",
                (telegram_id,),
            )
            row = cur.fetchone()
            assert list(row) == ["month", "active"]


def test_yearly_subscription_activates_and_credits_bonus(env):
    main, database = env
    telegram_id = 900000000202
    subscription_id = "I-YEARLY1"
    saved = main.save_paypal_subscription(telegram_id, subscription_id, main.PAYPAL_PRO_YEARLY_PLAN_ID, "year")
    assert saved is True

    item = main.shop_item("sub_year")
    event = _sale_event(subscription_id, "SALE-2", item["usd"])
    status, body = _unwrap(_run(main.public_paypal_webhook(
        FakeRequest(payload=event, headers=VALID_WEBHOOK_HEADERS, raw_body=json.dumps(event).encode())
    )))
    assert status == 200
    assert body["created"] is True
    assert _balance(database, telegram_id) == item["bonus_credits"]

    with database.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT subscription_type, status FROM subscriptions WHERE telegram_id = %s",
                (telegram_id,),
            )
            row = cur.fetchone()
            assert list(row) == ["year", "active"]


def test_duplicate_subscription_webhook_is_idempotent(env):
    main, database = env
    telegram_id = 900000000203
    subscription_id = "I-MONTHLY2"
    main.save_paypal_subscription(telegram_id, subscription_id, main.PAYPAL_PRO_MONTHLY_PLAN_ID, "month")
    item = main.shop_item("sub_month")
    event = _sale_event(subscription_id, "SALE-3", item["usd"])

    _, first_body = _unwrap(_run(main.public_paypal_webhook(
        FakeRequest(payload=event, headers=VALID_WEBHOOK_HEADERS, raw_body=json.dumps(event).encode())
    )))
    _, second_body = _unwrap(_run(main.public_paypal_webhook(
        FakeRequest(payload=event, headers=VALID_WEBHOOK_HEADERS, raw_body=json.dumps(event).encode())
    )))
    assert first_body["created"] is True
    assert second_body["created"] is False
    assert _balance(database, telegram_id) == item["bonus_credits"]


def test_subscription_payment_amount_mismatch_is_rejected(env):
    # A renewal event whose amount doesn't match what was recorded at
    # subscription-creation time (e.g. someone attempting to replay/forge a
    # cheaper renewal) must be rejected outright, never silently
    # discounted or accepted.
    import fastapi

    main, database = env
    telegram_id = 900000000204
    subscription_id = "I-MONTHLY3"
    main.save_paypal_subscription(telegram_id, subscription_id, main.PAYPAL_PRO_MONTHLY_PLAN_ID, "month")

    event = _sale_event(subscription_id, "SALE-4", 0.01)  # forged low amount
    with pytest.raises(fastapi.HTTPException) as exc_info:
        main.activate_paypal_subscription_from_event(event)
    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "paypal_payment_amount_mismatch"
    assert _balance(database, telegram_id) == 0


# ---------------------------------------------------------------------------
# Subscription-binding / subscription-created: website-session ownership
# ---------------------------------------------------------------------------

def test_subscription_binding_ties_custom_id_to_the_authenticated_uid(env):
    main, _ = env
    telegram_id = 900000000301
    request = FakeRequest(
        payload={"plan_id": main.PAYPAL_PRO_MONTHLY_PLAN_ID},
        state=SimpleNamespace(telegram_id=telegram_id),
    )
    result = _run(main.public_paypal_subscription_binding(request))
    assert result["ok"] is True
    from services.paypal_binding import read_binding
    assert read_binding(result["custom_id"], main.PAYPAL_PRO_MONTHLY_PLAN_ID) == telegram_id


def test_subscription_created_rejects_binding_for_a_different_account(env, monkeypatch):
    main, _ = env
    real_uid = 900000000302
    attacker_uid = 900000000303
    from services.paypal_binding import make_binding
    binding_for_real_uid = make_binding(real_uid, main.PAYPAL_PRO_MONTHLY_PLAN_ID)

    monkeypatch.setattr(main, "verified_paypal_subscription", lambda sub_id: {
        "id": sub_id, "plan_id": main.PAYPAL_PRO_MONTHLY_PLAN_ID, "status": "ACTIVE",
        "custom_id": binding_for_real_uid,
    })

    import fastapi
    request = FakeRequest(payload={
        "subscription_id": "I-ATTACK1",
        "plan_id": main.PAYPAL_PRO_MONTHLY_PLAN_ID,
        "plan_type": "month",
        "telegram_id": attacker_uid,  # claims someone else's binding
    })
    with pytest.raises(fastapi.HTTPException) as exc_info:
        _run(main.public_paypal_subscription_created(request))
    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == "paypal_owner_mismatch"


# ---------------------------------------------------------------------------
# Website vs Telegram return/cancel URLs (Orders/Capture, credit purchases)
# ---------------------------------------------------------------------------

def test_website_order_uses_website_return_and_cancel_urls(env, monkeypatch):
    main, _ = env
    captured = {}

    def fake_post(url, **kwargs):
        if url.endswith("/v1/notifications/verify-webhook-signature"):
            return FakeResponse(200, {"verification_status": "SUCCESS"})
        if url.endswith("/v2/checkout/orders"):
            captured["body"] = kwargs.get("json")
            return _fake_order_response()
        raise AssertionError(f"unexpected POST {url}")

    monkeypatch.setattr(main.requests, "post", fake_post)
    item = main.shop_item("pack_100")
    main.create_paypal_order(900000000401, "pack_100", item, is_website=True)

    experience = captured["body"]["payment_source"]["paypal"]["experience_context"]
    assert experience["return_url"] == "https://sylvex.ai/store.html?payment=success"
    assert experience["cancel_url"] == "https://sylvex.ai/store.html?payment=cancelled"


def test_telegram_order_return_urls_are_unchanged(env, monkeypatch):
    main, _ = env
    captured = {}

    def fake_post(url, **kwargs):
        if url.endswith("/v1/notifications/verify-webhook-signature"):
            return FakeResponse(200, {"verification_status": "SUCCESS"})
        if url.endswith("/v2/checkout/orders"):
            captured["body"] = kwargs.get("json")
            return _fake_order_response()
        raise AssertionError(f"unexpected POST {url}")

    monkeypatch.setattr(main.requests, "post", fake_post)
    item = main.shop_item("pack_100")
    # is_website defaults to False - the pre-existing Telegram Mini App path.
    main.create_paypal_order(555, "pack_100", item)

    experience = captured["body"]["payment_source"]["paypal"]["experience_context"]
    assert experience["return_url"].startswith(main.SHOP_WEBAPP_URL)
    assert experience["cancel_url"].startswith(main.SHOP_WEBAPP_URL)
    assert "sylvex.ai" not in experience["return_url"]
    assert "sylvex.ai" not in experience["cancel_url"]


def test_endpoint_routes_website_requests_to_website_return_url(env, monkeypatch):
    # The endpoint itself (not just create_paypal_order's own is_website
    # param) must derive is_website the same way public_lemonsqueezy_checkout
    # already did: absent Telegram initData on request.state means this
    # request came from the Website's session cookie, never a client-claimed
    # flag.
    main, _ = env
    captured = {}

    def fake_post(url, **kwargs):
        if url.endswith("/v1/notifications/verify-webhook-signature"):
            return FakeResponse(200, {"verification_status": "SUCCESS"})
        if url.endswith("/v2/checkout/orders"):
            captured["body"] = kwargs.get("json")
            return _fake_order_response()
        raise AssertionError(f"unexpected POST {url}")

    monkeypatch.setattr(main.requests, "post", fake_post)
    telegram_id = 900000000402
    request = FakeRequest(
        payload={"pack_id": "pack_100", "type": "tokens", "telegram_id": telegram_id},
        state=SimpleNamespace(telegram_id=telegram_id, telegram_init_data=""),
    )
    result = _run(main.public_paypal_create_order(request))
    assert result["ok"] is True
    experience = captured["body"]["payment_source"]["paypal"]["experience_context"]
    assert experience["return_url"] == "https://sylvex.ai/store.html?payment=success"


def test_endpoint_routes_telegram_requests_to_telegram_return_url(env, monkeypatch):
    main, _ = env
    captured = {}

    def fake_post(url, **kwargs):
        if url.endswith("/v1/notifications/verify-webhook-signature"):
            return FakeResponse(200, {"verification_status": "SUCCESS"})
        if url.endswith("/v2/checkout/orders"):
            captured["body"] = kwargs.get("json")
            return _fake_order_response()
        raise AssertionError(f"unexpected POST {url}")

    monkeypatch.setattr(main.requests, "post", fake_post)
    telegram_id = 900000000403
    request = FakeRequest(
        payload={"pack_id": "pack_100", "type": "tokens", "telegram_id": telegram_id},
        state=SimpleNamespace(telegram_id=telegram_id, telegram_init_data="real-signed-telegram-init-data"),
    )
    result = _run(main.public_paypal_create_order(request))
    assert result["ok"] is True
    experience = captured["body"]["payment_source"]["paypal"]["experience_context"]
    assert experience["return_url"].startswith(main.SHOP_WEBAPP_URL)
    assert "sylvex.ai" not in experience["return_url"]


# ---------------------------------------------------------------------------
# Missing PayPal plan env vars: subscriptions fail safely, Orders/Capture unaffected
# ---------------------------------------------------------------------------

def test_missing_plan_env_vars_are_reported_not_configured(env, monkeypatch):
    main, _ = env
    monkeypatch.setattr(main, "PAYPAL_PRO_MONTHLY_PLAN_ID", "")
    monkeypatch.setattr(main, "PAYPAL_PRO_YEARLY_PLAN_ID", "")
    assert main.paypal_subscriptions_configured() is False

    config = _run(main.public_config())
    assert config["paypal_subscriptions_enabled"] is False
    assert config["paypal_enabled"] is True  # Orders/Capture credit purchases unaffected

    status, body = _unwrap(_run(main.public_paypal_subscription_binding(
        FakeRequest(payload={"plan_id": "P-ANYTHING"}, state=SimpleNamespace(telegram_id=900000000501))
    )))
    assert status == 502
    assert body["error"] == "paypal_subscriptions_not_configured"

    status2, body2 = _unwrap(_run(main.public_paypal_subscription_created(
        FakeRequest(payload={"subscription_id": "I-X", "plan_id": "P-ANYTHING", "plan_type": "month", "telegram_id": 900000000501})
    )))
    assert status2 == 502
    assert body2["error"] == "paypal_subscriptions_not_configured"


def test_pack_for_plan_never_matches_empty_plan_id_against_unconfigured_env(env, monkeypatch):
    main, _ = env
    monkeypatch.setattr(main, "PAYPAL_PRO_MONTHLY_PLAN_ID", "")
    monkeypatch.setattr(main, "PAYPAL_PRO_YEARLY_PLAN_ID", "")
    assert main.paypal_subscription_pack_for_plan("") == ""


# ---------------------------------------------------------------------------
# Subscription lifecycle: cancelled / suspended / expired / payment failed
# ---------------------------------------------------------------------------

def test_cancelled_subscription_revokes_access(env):
    main, database = env
    telegram_id = 900000000601
    subscription_id = "I-CANCEL1"
    _activate_subscription(main, telegram_id, subscription_id, main.PAYPAL_PRO_MONTHLY_PLAN_ID, "month")

    event = _lifecycle_event("BILLING.SUBSCRIPTION.CANCELLED", subscription_id)
    status, body = _unwrap(_run(main.public_paypal_webhook(_webhook_post(event))))
    assert status == 200
    assert body["updated"] is True

    with database.connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT status FROM subscriptions WHERE telegram_id = %s", (telegram_id,))
            assert cur.fetchone()[0] == "cancelled"
            cur.execute("SELECT subscription FROM users WHERE telegram_id = %s", (telegram_id,))
            assert cur.fetchone()[0] is None
            cur.execute("SELECT status FROM paypal_subscriptions WHERE paypal_subscription_id = %s", (subscription_id,))
            assert cur.fetchone()[0] == "cancelled"


def test_suspended_subscription_revokes_access(env):
    main, database = env
    telegram_id = 900000000602
    subscription_id = "I-SUSPEND1"
    _activate_subscription(main, telegram_id, subscription_id, main.PAYPAL_PRO_YEARLY_PLAN_ID, "year")

    event = _lifecycle_event("BILLING.SUBSCRIPTION.SUSPENDED", subscription_id)
    status, body = _unwrap(_run(main.public_paypal_webhook(_webhook_post(event))))
    assert status == 200
    assert body["updated"] is True

    with database.connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT status FROM subscriptions WHERE telegram_id = %s", (telegram_id,))
            assert cur.fetchone()[0] == "suspended"
            cur.execute("SELECT subscription FROM users WHERE telegram_id = %s", (telegram_id,))
            assert cur.fetchone()[0] is None


def test_expired_subscription_revokes_access(env):
    main, database = env
    telegram_id = 900000000603
    subscription_id = "I-EXPIRE1"
    _activate_subscription(main, telegram_id, subscription_id, main.PAYPAL_PRO_MONTHLY_PLAN_ID, "month")

    event = _lifecycle_event("BILLING.SUBSCRIPTION.EXPIRED", subscription_id)
    status, body = _unwrap(_run(main.public_paypal_webhook(_webhook_post(event))))
    assert status == 200
    assert body["updated"] is True

    with database.connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT status FROM subscriptions WHERE telegram_id = %s", (telegram_id,))
            assert cur.fetchone()[0] == "expired"
            cur.execute("SELECT subscription FROM users WHERE telegram_id = %s", (telegram_id,))
            assert cur.fetchone()[0] is None


def test_payment_failed_is_recorded_without_revoking_access(env):
    # A single failed renewal charge is PayPal's own retry/dunning process
    # still in flight, not a final state - SYLVEX Pro access must continue
    # until PayPal itself actually suspends/cancels the subscription.
    main, database = env
    telegram_id = 900000000604
    subscription_id = "I-FAIL1"
    _activate_subscription(main, telegram_id, subscription_id, main.PAYPAL_PRO_MONTHLY_PLAN_ID, "month")

    event = _lifecycle_event("BILLING.SUBSCRIPTION.PAYMENT.FAILED", subscription_id)
    status, body = _unwrap(_run(main.public_paypal_webhook(_webhook_post(event))))
    assert status == 200
    assert body["updated"] is True

    with database.connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT status FROM subscriptions WHERE telegram_id = %s", (telegram_id,))
            assert cur.fetchone()[0] == "active"
            cur.execute("SELECT subscription FROM users WHERE telegram_id = %s", (telegram_id,))
            assert cur.fetchone()[0] == "month"
            cur.execute("SELECT status FROM paypal_subscriptions WHERE paypal_subscription_id = %s", (subscription_id,))
            assert cur.fetchone()[0] == "payment_failed"


def test_duplicate_lifecycle_webhook_delivery_is_idempotent(env):
    main, database = env
    telegram_id = 900000000605
    subscription_id = "I-DUPCANCEL1"
    _activate_subscription(main, telegram_id, subscription_id, main.PAYPAL_PRO_MONTHLY_PLAN_ID, "month")

    event = _lifecycle_event("BILLING.SUBSCRIPTION.CANCELLED", subscription_id)
    _, first_body = _unwrap(_run(main.public_paypal_webhook(_webhook_post(event))))
    _, second_body = _unwrap(_run(main.public_paypal_webhook(_webhook_post(event))))
    assert first_body["updated"] is True
    assert second_body["updated"] is False

    with database.connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT status FROM subscriptions WHERE telegram_id = %s", (telegram_id,))
            assert cur.fetchone()[0] == "cancelled"


def test_unknown_lifecycle_event_type_is_ignored(env):
    main, _ = env
    event = {"event_type": "BILLING.SUBSCRIPTION.RE-ACTIVATED", "resource": {"id": "I-UNKNOWN1"}}
    status, body = _unwrap(_run(main.public_paypal_webhook(_webhook_post(event))))
    assert status == 200
    assert body.get("ignored") == "BILLING.SUBSCRIPTION.RE-ACTIVATED"
