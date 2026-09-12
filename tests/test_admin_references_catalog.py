"""Regression tests for the References catalog - the brand-new
ready-made-template feature the Support Bot manages end to end (create,
edit, publish/unpublish, delete, media upload) with no code changes or
deploys, per admin task #10."""
import base64
import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock

import httpx
import pytest

from services.security import SecurityMiddleware

sys.path.insert(0, str(Path(__file__).parent / "support"))

TOKEN = "test-only-bot-token"
SERVICE_TOKEN = "test-only-service-token"
OWNER_ID = 555

TINY_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


def _pglite_available():
    return bool(os.getenv("SYLVEX_TEST_NODE") and os.getenv("SYLVEX_PGLITE_MODULE"))


pytestmark = pytest.mark.skipif(not _pglite_available(), reason="Set SYLVEX_TEST_NODE and SYLVEX_PGLITE_MODULE to run real-SQL tests")


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

    from pglite_adapter import Database

    database = Database()
    monkeypatch.setattr(main, "DATABASE_URL", "pglite://test")
    monkeypatch.setattr(main, "db_connect", lambda *a, **k: database.connect())
    monkeypatch.setattr(main, "ADMIN_SCHEMA_READY", False)
    monkeypatch.setattr(main, "REFERENCES_SCHEMA_READY", False)
    # storage.put_bytes needs R2 or falls back to local disk; force local disk
    # so the media-upload test doesn't need real R2 credentials.
    import services.storage as storage

    monkeypatch.setattr(storage, "R2_BUCKET", "")
    monkeypatch.setattr(storage, "DATABASE_URL", "")

    main.ensure_admin_tables()
    main.ensure_references_table()

    main.app.middleware_stack = None
    for mw in main.app.user_middleware:
        if mw.cls is SecurityMiddleware:
            mw.kwargs["quota_check"] = AsyncMock()

    return main.app


@pytest.fixture
def client(app):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


def owner_call(**extra):
    return {"service_token": SERVICE_TOKEN, "telegram_id": OWNER_ID, **extra}


@pytest.mark.asyncio
async def test_create_list_and_get_reference(client):
    response = await client.post("/api/admin/references/create", json=owner_call(
        category="photo_styles", kind="photo", name="Cyberpunk Portrait",
        description="Neon-lit character portrait", prompt="cyberpunk portrait, neon lights",
        model="flux-pro", workflow="image_edit",
    ))
    assert response.status_code == 200, response.text
    created = response.json()["item"]
    assert created["category"] == "photo_styles"
    assert created["kind"] == "photo"
    assert created["published"] is False

    response = await client.post("/api/admin/references/list", json=owner_call())
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["name"] == "Cyberpunk Portrait"


@pytest.mark.asyncio
async def test_create_rejects_invalid_kind(client):
    response = await client.post("/api/admin/references/create", json=owner_call(
        category="photo_styles", kind="audio", name="Bad Kind",
    ))
    assert response.status_code == 400
    assert response.json()["detail"] == "invalid_reference"


@pytest.mark.asyncio
async def test_update_and_publish_flow(client):
    created = (await client.post("/api/admin/references/create", json=owner_call(
        category="video_templates", kind="video", name="Product Ad",
    ))).json()["item"]
    reference_id = created["id"]

    response = await client.post("/api/admin/references/update", json=owner_call(
        id=reference_id, description="Fast-paced product advertisement", model="veo-3",
    ))
    assert response.status_code == 200, response.text
    updated = response.json()["item"]
    assert updated["description"] == "Fast-paced product advertisement"
    assert updated["model"] == "veo-3"
    assert updated["published"] is False

    response = await client.post("/api/admin/references/publish", json=owner_call(id=reference_id, published=True))
    assert response.status_code == 200, response.text
    assert response.json()["published"] is True

    response = await client.post("/api/admin/references/list", json=owner_call(published=True))
    assert response.json()["total"] == 1

    response = await client.get(f"/api/public/prostudio/references?kind=video")
    assert response.status_code == 200, response.text
    public_items = response.json()["items"]
    assert len(public_items) == 1
    assert public_items[0]["name"] == "Product Ad"
    # Unpublished references must never leak into the public catalog.
    await client.post("/api/admin/references/publish", json=owner_call(id=reference_id, published=False))
    response = await client.get("/api/public/prostudio/references")
    assert response.json()["items"] == []


@pytest.mark.asyncio
async def test_update_unknown_reference_returns_404(client):
    response = await client.post("/api/admin/references/update", json=owner_call(id=999999, name="Nope"))
    assert response.status_code == 404
    assert response.json()["detail"] == "reference_not_found"


@pytest.mark.asyncio
async def test_delete_reference(client):
    created = (await client.post("/api/admin/references/create", json=owner_call(
        category="try_on", kind="photo", name="Clothing Try-On",
    ))).json()["item"]

    response = await client.post("/api/admin/references/delete", json=owner_call(id=created["id"]))
    assert response.status_code == 200, response.text

    response = await client.post("/api/admin/references/list", json=owner_call())
    assert response.json()["total"] == 0


@pytest.mark.asyncio
async def test_upload_media_stores_preview_and_returns_url(client):
    response = await client.post("/api/admin/references/upload-media", json=owner_call(
        content_base64=base64.b64encode(TINY_PNG).decode(), content_type="image/png", slot="preview",
    ))
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["url"]
    assert body["content_type"] == "image/png"


@pytest.mark.asyncio
async def test_upload_media_rejects_invalid_slot(client):
    response = await client.post("/api/admin/references/upload-media", json=owner_call(
        content_base64=base64.b64encode(TINY_PNG).decode(), slot="thumbnail",
    ))
    assert response.status_code == 400
    assert response.json()["detail"] == "invalid_slot"


@pytest.mark.asyncio
async def test_non_admin_cannot_manage_references(client):
    response = await client.post("/api/admin/references/create", json={
        "service_token": SERVICE_TOKEN, "telegram_id": 424242,
        "category": "photo_styles", "kind": "photo", "name": "Hack Attempt",
    })
    assert response.status_code == 403
    assert response.json()["detail"] == "admin_access_denied"
