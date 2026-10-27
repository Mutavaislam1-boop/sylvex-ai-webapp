"""Retired Crypto has no network, financial or user-visible purchase path."""
import asyncio
import json
from unittest.mock import AsyncMock

import httpx
import pytest

import main
from services import security, shop_catalog
from tests.test_security_boundaries import signed, TOKEN


class UnreadableRequest:
    async def json(self):
        pytest.fail("retired checkout must not parse a purchase")


@pytest.mark.parametrize("variable", [None, "CRYPTO_API_KEY", "CRIPTO_API_KEY"])
def test_retired_invoice_rejects_before_parsing_network_or_financial_access(monkeypatch, variable):
    if variable:
        monkeypatch.setenv(variable, "dummy-revoked-test-only")
    def forbidden(*args, **kwargs):
        pytest.fail("retired provider attempted network or a financial write")
    for name in ("db_connect", "shop_db", "ensure_shop_orders", "finalize_shop_payment", "finalize_store_order", "log_user_event"):
        monkeypatch.setattr(main, name, forbidden)
    monkeypatch.setattr(main.requests, "post", forbidden)
    response = asyncio.run(main.public_crypto_invoice(UnreadableRequest()))
    assert response.status_code == 410
    assert json.loads(response.body) == {"ok": False, "error": "crypto_retired"}


def test_public_catalog_offers_no_crypto_at_any_price():
    for product_id in shop_catalog.FIXED_PRODUCTS:
        assert "crypto_pay" not in shop_catalog.provider_availability(shop_catalog.resolve_product(product_id))
    for amount in ("1", "12.34", "1000"):
        assert "crypto_pay" not in shop_catalog.provider_availability(shop_catalog.resolve_product("credits_custom", amount))
    assert "crypto" not in json.dumps(shop_catalog.public_catalog()).lower()
    assert main.shop_provider_configured("crypto_pay") is False


@pytest.fixture
def authenticated_http(monkeypatch):
    monkeypatch.setenv("WEB_SESSION_SECRET", "dummy-c3-independent-session-secret")
    monkeypatch.setenv("BOT_TOKEN", TOKEN)
    monkeypatch.setattr(main, "BOT_TOKEN", TOKEN)
    monkeypatch.setattr(main, "TELEGRAM_AUTH_TOKENS", (TOKEN,))
    monkeypatch.setattr(main, "sync_user_to_db", lambda user: user)
    monkeypatch.setattr(security, "resolve_web_session_uid", lambda account_id: 101)
    main.app.middleware_stack = None
    for middleware in main.app.user_middleware:
        if middleware.cls is security.SecurityMiddleware:
            monkeypatch.setitem(middleware.kwargs, "quota_check", AsyncMock())
    yield
    main.app.middleware_stack = None


@pytest.mark.parametrize("identity,expected", [("website", 410), ("telegram", 403), ("anonymous", 401)])
def test_http_crypto_invoice_is_unavailable_for_every_supported_identity(authenticated_http, identity, expected):
    headers = {}
    if identity == "website":
        headers["Cookie"] = "sylvex_web_session=" + security.create_web_session_token(101)
    elif identity == "telegram":
        headers["X-Telegram-Init-Data"] = signed()
    async def request():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app), base_url="https://api.example.test") as client:
            return await client.post("/api/public/payments/crypto/invoice", json={"product_id": "pack_500"}, headers=headers)
    response = asyncio.run(request())
    assert response.status_code == expected
    assert "invoice_id" not in response.json() and "invoice_url" not in response.json()


@pytest.mark.parametrize("path", ["/api/public/payments/crypto/webhook", "/api/public/payments/crypto/checkout",
                                  "/api/web/payments/crypto/checkout", "/api/public/payments/cryptopay/invoice"])
def test_unregistered_legacy_crypto_handlers_cannot_accept_a_payment(authenticated_http, path):
    headers = {"Cookie": "sylvex_web_session=" + security.create_web_session_token(101)}
    async def request():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app), base_url="https://api.example.test") as client:
            return await client.post(path, json={"status": "paid", "product_id": "pack_500"}, headers=headers)
    assert asyncio.run(request()).status_code == 404


def test_telegram_catalog_still_advertises_only_stars(monkeypatch):
    monkeypatch.setattr(main, "BOT_TOKEN", TOKEN)
    monkeypatch.setattr(main, "store_generation_examples", lambda: {})
    response = asyncio.run(main.public_shop_catalog())
    data = json.loads(response.body)
    assert data["providers"] == {"telegram_stars": True}
    assert "crypto_pay" not in json.dumps(data)
