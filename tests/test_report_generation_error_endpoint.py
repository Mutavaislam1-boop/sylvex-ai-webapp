"""The Mini App's one-click "Report error" action must create an error
card tied to the *authenticated* Telegram user (actor_id from
SecurityMiddleware's validated init data), never a client-supplied
telegram_id, and must work without the user typing anything - all context
comes from the error message's own errorMeta."""
import hashlib
import hmac
import json
import os
import sys
import time
from pathlib import Path
from urllib.parse import urlencode

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).parent / "support"))

TOKEN = "test-only-bot-token"


def _pglite_available():
    return bool(os.getenv("SYLVEX_TEST_NODE") and os.getenv("SYLVEX_PGLITE_MODULE"))


pytestmark = pytest.mark.skipif(
    not _pglite_available(),
    reason="Set SYLVEX_TEST_NODE and SYLVEX_PGLITE_MODULE to run real-SQL tests",
)


def signed(uid=101, age=0):
    fields = {"user": json.dumps({"id": uid, "first_name": "Test"}), "auth_date": str(int(time.time()) - age)}
    check = "\n".join(f"{k}={fields[k]}" for k in sorted(fields))
    fields["hash"] = hmac.new(hmac.new(b"WebAppData", TOKEN.encode(), hashlib.sha256).digest(), check.encode(), hashlib.sha256).hexdigest()
    return urlencode(fields)


@pytest.fixture
def app(monkeypatch):
    from pglite_adapter import Database
    from unittest.mock import AsyncMock
    from services.security import SecurityMiddleware

    monkeypatch.setenv("BOT_TOKEN", TOKEN)
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    import main

    monkeypatch.setattr(main, "TELEGRAM_AUTH_TOKENS", (TOKEN,))
    monkeypatch.setattr(main, "BOT_TOKEN", TOKEN)

    database = Database()
    monkeypatch.setattr(main, "DATABASE_URL", "pglite://test")
    monkeypatch.setattr(main, "db_connect", lambda *a, **k: database.connect())
    monkeypatch.setattr(main, "_PROSTUDIO_SCHEMA_READY", False)

    main.app.middleware_stack = None
    for mw in main.app.user_middleware:
        if mw.cls is SecurityMiddleware:
            mw.kwargs["quota_check"] = AsyncMock()

    yield main.app
    database.close()


@pytest.fixture
def client(app):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


@pytest.mark.asyncio
async def test_report_error_creates_a_row_for_the_authenticated_user(client):
    response = await client.post(
        "/api/public/prostudio/report_error",
        headers={"X-Telegram-Init-Data": signed(uid=101)},
        json={
            "mode": "video",
            "provider": "wan",
            "model": "wan_2_7_edit",
            "job_id": "job-123",
            "prompt": "a dog running in the snow",
            "error_text": "Генерация не прошла. Попробуйте повторить немного позже.",
            "raw_error": "Wan video editing requires an input video",
        },
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data.get("ok") is True
    assert data.get("report_id")


@pytest.mark.asyncio
async def test_report_error_rejects_a_spoofed_telegram_id(client):
    """The security middleware refuses a client-supplied telegram_id that
    doesn't match the authenticated user before this handler ever runs -
    a report can never be filed on someone else's behalf."""
    response = await client.post(
        "/api/public/prostudio/report_error",
        headers={"X-Telegram-Init-Data": signed(uid=202)},
        json={"telegram_id": 999999, "mode": "image", "error_text": "failed"},
    )
    assert response.status_code == 403
    assert response.json().get("error") == "user_mismatch"


@pytest.mark.asyncio
async def test_report_error_uses_the_authenticated_id_when_body_omits_it(client):
    response = await client.post(
        "/api/public/prostudio/report_error",
        headers={"X-Telegram-Init-Data": signed(uid=303)},
        json={"mode": "image", "error_text": "failed"},
    )
    assert response.status_code == 200, response.text
    assert response.json().get("ok") is True


@pytest.mark.asyncio
async def test_report_error_requires_authentication(client):
    response = await client.post(
        "/api/public/prostudio/report_error",
        json={"mode": "image", "error_text": "failed"},
    )
    assert response.status_code in (401, 403)
