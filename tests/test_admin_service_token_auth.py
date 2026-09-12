"""The separate SYLVEX Support Bot runs under its own Telegram bot/token and
can never produce a valid Telegram-WebApp initData signature for this app's
BOT_TOKEN. ADMIN_SERVICE_TOKEN lets it authenticate /api/admin/* requests
with a shared secret instead, sent as a header (X-Admin-Service-Token or
Authorization: Bearer) - never inside the JSON body. It must still go
through the normal admin_users role/permission lookup in _admin_actor for
the telegram_id it names (with no SUPERADMIN_TELEGRAM_ID shortcut, unlike
the Mini App's own initData path), and must never work on a non-admin
route, via the JSON body, or without the exact secret."""
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
OWNER_ID = 555


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
    monkeypatch.setattr(main, "SUPERADMIN_TELEGRAM_ID", OWNER_ID)

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
@pytest.mark.skipif(not _pglite_available(), reason="Set SYLVEX_TEST_NODE and SYLVEX_PGLITE_MODULE to run real-SQL tests")
async def test_service_token_header_lets_the_owner_call_admin_me(client):
    """The owner's admin_users row is auto-seeded, so a service-authenticated
    request naming SUPERADMIN_TELEGRAM_ID still succeeds - but via the real
    DB lookup below, not a shortcut (see the no-database test further down
    for direct proof the shortcut itself is gone for this path)."""
    response = await client.post(
        "/api/admin/me",
        headers={"X-Admin-Service-Token": SERVICE_TOKEN},
        json={"telegram_id": OWNER_ID},
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["admin"]["telegram_id"] == OWNER_ID
    assert data["admin"]["role"] == "owner"


@pytest.mark.asyncio
@pytest.mark.skipif(not _pglite_available(), reason="Set SYLVEX_TEST_NODE and SYLVEX_PGLITE_MODULE to run real-SQL tests")
async def test_service_token_via_bearer_authorization_header_also_works(client):
    response = await client.post(
        "/api/admin/me",
        headers={"Authorization": f"Bearer {SERVICE_TOKEN}"},
        json={"telegram_id": OWNER_ID},
    )
    assert response.status_code == 200, response.text
    assert response.json()["admin"]["role"] == "owner"


@pytest.mark.asyncio
async def test_service_token_in_json_body_no_longer_authenticates(client):
    """The whole point of this change: a presented service_token field
    inside the JSON body (the old transport) must be ignored entirely - only
    a header counts now. Falls back to requiring initData, absent here, so
    it fails the same way an unauthenticated request would."""
    response = await client.post(
        "/api/admin/me",
        json={"service_token": SERVICE_TOKEN, "telegram_id": OWNER_ID},
    )
    assert response.status_code in (401, 403)


@pytest.mark.asyncio
@pytest.mark.skipif(not _pglite_available(), reason="Set SYLVEX_TEST_NODE and SYLVEX_PGLITE_MODULE to run real-SQL tests")
async def test_service_token_still_enforces_admin_users_lookup_for_non_owner(client):
    """A telegram_id that was never granted admin access must still be
    rejected - the service token only authenticates the caller as the
    trusted support-bot backend, it does not grant admin rights by itself."""
    response = await client.post(
        "/api/admin/me",
        headers={"X-Admin-Service-Token": SERVICE_TOKEN},
        json={"telegram_id": 999999},
    )
    assert response.status_code == 403
    assert response.json()["detail"] == "admin_access_denied"


@pytest.mark.asyncio
async def test_service_authenticated_superadmin_id_without_database_is_denied_not_shortcut(monkeypatch):
    """Direct proof the SUPERADMIN_TELEGRAM_ID shortcut is gone for the
    service-authenticated path, independent of whether PGlite happens to be
    available in this environment: with no database wired at all, the old
    shortcut would have returned 200 owner immediately without ever
    checking DATABASE_URL; now it must reach (and fail on) the same
    'database required' guard as any other DB-backed lookup."""
    monkeypatch.setenv("BOT_TOKEN", TOKEN)
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.setenv("ADMIN_SERVICE_TOKEN", SERVICE_TOKEN)
    import main

    monkeypatch.setattr(main, "TELEGRAM_AUTH_TOKENS", (TOKEN,))
    monkeypatch.setattr(main, "BOT_TOKEN", TOKEN)
    monkeypatch.setattr(main, "ADMIN_SERVICE_TOKEN", SERVICE_TOKEN)
    monkeypatch.setattr(main, "SUPERADMIN_TELEGRAM_ID", OWNER_ID)
    monkeypatch.setattr(main, "DATABASE_URL", "")

    main.app.middleware_stack = None
    for mw in main.app.user_middleware:
        if mw.cls is SecurityMiddleware:
            mw.kwargs["quota_check"] = AsyncMock()

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app), base_url="http://test") as client:
        response = await client.post(
            "/api/admin/me",
            headers={"X-Admin-Service-Token": SERVICE_TOKEN},
            json={"telegram_id": OWNER_ID},
        )
    assert response.status_code == 503
    assert response.json()["detail"] == "database_unavailable"


@pytest.mark.asyncio
async def test_wrong_service_token_header_falls_back_to_normal_telegram_auth_and_is_rejected(client):
    """An incorrect service token must not be treated as "close enough" -
    the request falls back to requiring real Telegram initData, which is
    absent here, so it fails the same way an unauthenticated request would."""
    response = await client.post(
        "/api/admin/me",
        headers={"X-Admin-Service-Token": "not-the-real-token"},
        json={"telegram_id": OWNER_ID},
    )
    assert response.status_code in (401, 403)


@pytest.mark.asyncio
async def test_service_token_header_has_no_effect_on_non_admin_routes(client):
    """The bypass is scoped to /api/admin/ paths only - it must not let the
    service-token header smuggle a caller past normal user-route auth."""
    response = await client.post(
        "/api/public/telegram/profile",
        headers={"X-Admin-Service-Token": SERVICE_TOKEN},
        json={"telegram_id": OWNER_ID},
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
        headers={"X-Telegram-Init-Data": signed(uid=OWNER_ID)},
        json={},
    )
    assert response.status_code == 200, response.text
    assert response.json()["admin"]["role"] == "owner"
