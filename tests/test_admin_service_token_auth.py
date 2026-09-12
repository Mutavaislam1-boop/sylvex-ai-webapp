"""The separate SYLVEX Support Bot runs under its own Telegram bot/token and
can never produce a valid Telegram-WebApp initData signature for this app's
BOT_TOKEN. ADMIN_SERVICE_TOKEN lets it authenticate /api/admin/* requests
with a shared secret instead - but must still go through the normal
admin_users role/permission lookup in _admin_actor for the telegram_id it
names, and must never work on a non-admin route or without the exact
secret."""
import hashlib
import hmac
import json
import os
import sys
import time
from pathlib import Path
from urllib.parse import urlencode
from unittest.mock import AsyncMock

import httpx
import pytest

from services.security import SecurityMiddleware

sys.path.insert(0, str(Path(__file__).parent / "support"))

TOKEN = "test-only-bot-token"
SERVICE_TOKEN = "test-only-service-token"


def _pglite_available():
    return bool(os.getenv("SYLVEX_TEST_NODE") and os.getenv("SYLVEX_PGLITE_MODULE"))


def signed(uid=101, age=0):
    fields = {"user": json.dumps({"id": uid, "first_name": "Test"}), "auth_date": str(int(time.time()) - age)}
    check = "\n".join(f"{k}={fields[k]}" for k in sorted(fields))
    fields["hash"] = hmac.new(hmac.new(b"WebAppData", TOKEN.encode(), hashlib.sha256).digest(), check.encode(), hashlib.sha256).hexdigest()
    return urlencode(fields)


@pytest.fixture
def app(monkeypatch):
    monkeypatch.setenv("BOT_TOKEN", TOKEN)
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.setenv("ADMIN_SERVICE_TOKEN", SERVICE_TOKEN)
    import main

    monkeypatch.setattr(main, "TELEGRAM_AUTH_TOKENS", (TOKEN,))
    monkeypatch.setattr(main, "BOT_TOKEN", TOKEN)
    monkeypatch.setattr(main, "ADMIN_SERVICE_TOKEN", SERVICE_TOKEN)
    monkeypatch.setattr(main, "SUPERADMIN_TELEGRAM_ID", 555)

    if _pglite_available():
        from pglite_adapter import Database

        database = Database()
        monkeypatch.setattr(main, "DATABASE_URL", "pglite://test")
        monkeypatch.setattr(main, "db_connect", lambda *a, **k: database.connect())
        monkeypatch.setattr(main, "ADMIN_SCHEMA_READY", False)

    main.app.middleware_stack = None
    for mw in main.app.user_middleware:
        if mw.cls is SecurityMiddleware:
            mw.kwargs["quota_check"] = AsyncMock()

    return main.app


@pytest.fixture
def client(app):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


@pytest.mark.asyncio
async def test_service_token_lets_the_named_owner_call_admin_me(client):
    response = await client.post(
        "/api/admin/me",
        json={"service_token": SERVICE_TOKEN, "telegram_id": 555},
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["admin"]["telegram_id"] == 555
    assert data["admin"]["role"] == "owner"


@pytest.mark.asyncio
@pytest.mark.skipif(not _pglite_available(), reason="Set SYLVEX_TEST_NODE and SYLVEX_PGLITE_MODULE to run real-SQL tests")
async def test_service_token_still_enforces_admin_users_lookup_for_non_owner(client):
    """A telegram_id that was never granted admin access must still be
    rejected - the service token only authenticates the caller as the
    trusted support-bot backend, it does not grant admin rights by itself."""
    response = await client.post(
        "/api/admin/me",
        json={"service_token": SERVICE_TOKEN, "telegram_id": 999999},
    )
    assert response.status_code == 403
    assert response.json()["detail"] == "admin_access_denied"


@pytest.mark.asyncio
async def test_wrong_service_token_falls_back_to_normal_telegram_auth_and_is_rejected(client):
    """An incorrect service_token must not be treated as "close enough" -
    the request falls back to requiring real Telegram initData, which is
    absent here, so it fails the same way an unauthenticated request would."""
    response = await client.post(
        "/api/admin/me",
        json={"service_token": "not-the-real-token", "telegram_id": 555},
    )
    assert response.status_code in (401, 403)


@pytest.mark.asyncio
async def test_service_token_has_no_effect_on_non_admin_routes(client):
    """The bypass is scoped to /api/admin/ paths only - it must not let a
    service_token field smuggle a caller past normal user-route auth."""
    response = await client.post(
        "/api/public/telegram/profile",
        json={"service_token": SERVICE_TOKEN, "telegram_id": 555},
    )
    assert response.status_code in (401, 403)


@pytest.mark.asyncio
async def test_admin_route_without_service_token_or_init_data_is_rejected(client):
    response = await client.post("/api/admin/me", json={})
    assert response.status_code in (401, 403)


@pytest.mark.asyncio
async def test_mini_app_init_data_path_still_works_unchanged(client):
    response = await client.post(
        "/api/admin/me",
        headers={"X-Telegram-Init-Data": signed(uid=555)},
        json={},
    )
    assert response.status_code == 200, response.text
    assert response.json()["admin"]["role"] == "owner"
