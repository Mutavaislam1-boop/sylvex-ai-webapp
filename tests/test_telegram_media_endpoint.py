"""/api/internal/telegram-media: the Telegram bot re-hosts user photos and
videos here so providers get a signed SYLVEX URL instead of a Telegram file
URL (which embeds the bot token). Runs through the real SecurityMiddleware;
storage is an in-memory dict, no network."""
from unittest.mock import AsyncMock

import httpx
import pytest

from services.security import SecurityMiddleware

TOKEN = "test-only-bot-token"


def _jpeg():
    import io
    from PIL import Image
    buffer = io.BytesIO()
    Image.new("RGB", (64, 64), (200, 30, 30)).save(buffer, "JPEG")
    return buffer.getvalue()


JPEG = _jpeg()


@pytest.fixture
def app(monkeypatch):
    monkeypatch.setenv("BOT_TOKEN", TOKEN)
    import main
    stored = {}
    monkeypatch.setattr(main, "TELEGRAM_MEDIA_SERVICE_TOKEN", "media-secret")
    monkeypatch.setattr(main, "storage_put_bytes", lambda data, key, content_type="": stored.__setitem__(key, (data, content_type)) or f"https://webapp.test/api/public/storage/{key}?media_sig=x")
    main.app.middleware_stack = None
    for mw in main.app.user_middleware:
        if mw.cls is SecurityMiddleware:
            mw.kwargs["quota_check"] = AsyncMock()
    main.app.state.telegram_media_stored = stored
    return main.app


def _post(app, headers=None, name="telegram-photo.jpg", content=JPEG, content_type="image/jpeg"):
    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            return await client.post("/api/internal/telegram-media", headers=headers or {}, files={"file": (name, content, content_type)})
    import asyncio
    return asyncio.run(run())


def test_bot_upload_is_stored_in_sylvex_storage_and_returns_a_sylvex_url(app):
    response = _post(app, {"X-Sylvex-Media-Token": "media-secret"})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["url"].startswith("https://webapp.test/api/public/storage/generated/telegram-inputs/")
    (key, (data, content_type)), = app.state.telegram_media_stored.items()
    assert key.startswith("generated/telegram-inputs/") and key.endswith(".jpg")
    assert data == JPEG and content_type == "image/jpeg"
    assert "api.telegram.org" not in response.text and TOKEN not in response.text


@pytest.mark.parametrize("headers,status", [({}, 401), ({"X-Sylvex-Media-Token": "wrong"}, 401)])
def test_upload_without_the_service_token_is_refused(app, headers, status):
    assert _post(app, headers).status_code == status
    assert app.state.telegram_media_stored == {}


def test_route_is_closed_when_no_service_token_is_configured(app, monkeypatch):
    import main
    monkeypatch.setattr(main, "TELEGRAM_MEDIA_SERVICE_TOKEN", "")
    assert _post(app, {"X-Sylvex-Media-Token": ""}).status_code == 503
    assert app.state.telegram_media_stored == {}


@pytest.mark.parametrize("name,content", [("payload.html", b"<html>"), ("photo.jpg", b"<html>not a jpeg")])
def test_only_real_media_is_accepted(app, name, content):
    response = _post(app, {"X-Sylvex-Media-Token": "media-secret"}, name=name, content=content, content_type="text/html")
    assert response.status_code == 400
    assert app.state.telegram_media_stored == {}
