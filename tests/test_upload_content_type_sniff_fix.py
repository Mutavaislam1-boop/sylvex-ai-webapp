# Regression tests for the security audit's UPLOAD-2 / R2-1 finding:
#
# Both /api/admin/references/upload-media and /api/admin/sylvex-test/upload-file
# pick a stored object's content_type by (1) trusting a client-declared type
# against a small allowlist, else (2) magic-byte sniffing, else (3) a fallback
# that was written as `content_type or "application/octet-stream"` - which
# KEPT the original client-declared content_type (e.g. "text/html") whenever
# it was non-empty, only forcing the file extension to ".bin". Since the
# generic storage route (/api/public/storage/{object_key}) serves the object
# back with whatever Content-Type was stored, and had no
# X-Content-Type-Options: nosniff, a privileged-but-malicious upload
# declaring content_type="text/html" with arbitrary HTML/JS bytes could be
# rendered as a live page in the app's own origin - stored XSS via the
# public References catalog.
#
# Fix: force content_type = "application/octet-stream" (never the
# client-declared value) whenever sniffing fails, and add
# X-Content-Type-Options: nosniff to the generic storage response.
import base64
import hashlib
import hmac
import io
import json
import time
from unittest.mock import AsyncMock
from urllib.parse import urlencode

import httpx
import pytest

from services.security import SecurityMiddleware

TOKEN = "test-only-bot-token"
OWNER_ID = 555

MALICIOUS_HTML = b"<html><body><script>alert(document.cookie)</script></body></html>"


def signed(uid=OWNER_ID, age=0):
    fields = {"user": json.dumps({"id": uid, "first_name": "Test"}), "auth_date": str(int(time.time()) - age)}
    check = "\n".join(f"{k}={fields[k]}" for k in sorted(fields))
    fields["hash"] = hmac.new(
        hmac.new(b"WebAppData", TOKEN.encode(), hashlib.sha256).digest(), check.encode(), hashlib.sha256
    ).hexdigest()
    return urlencode(fields)


@pytest.fixture
def app(monkeypatch, tmp_path):
    monkeypatch.setenv("BOT_TOKEN", TOKEN)
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    import main

    monkeypatch.setattr(main, "TELEGRAM_AUTH_TOKENS", (TOKEN,))
    monkeypatch.setattr(main, "BOT_TOKEN", TOKEN)
    monkeypatch.setattr(main, "SUPERADMIN_TELEGRAM_ID", OWNER_ID)

    # storage.put_bytes needs R2 or falls back to local disk; force local
    # disk (into an isolated tmp dir) so uploads don't need real R2
    # credentials and don't touch webapp/generated.
    import services.storage as storage

    monkeypatch.setattr(storage, "R2_BUCKET", "")
    monkeypatch.setattr(storage, "DATABASE_URL", "")
    monkeypatch.setattr(storage, "LOCAL_GENERATED_DIR", tmp_path / "generated")

    main.app.middleware_stack = None
    for mw in main.app.user_middleware:
        if mw.cls is SecurityMiddleware:
            mw.kwargs["quota_check"] = AsyncMock()

    return main.app


@pytest.fixture
def client(app):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


# ---------------------------------------------------------------------------
# /api/admin/references/upload-media
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_references_upload_forces_octet_stream_when_sniff_fails_despite_malicious_declared_type(client):
    response = await client.post(
        "/api/admin/references/upload-media",
        json={
            "initData": signed(),
            "slot": "preview",
            "content_type": "text/html",
            "content_base64": base64.b64encode(MALICIOUS_HTML).decode(),
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["content_type"] == "application/octet-stream"
    assert body["url"].split("?")[0].endswith(".bin")


@pytest.mark.asyncio
async def test_references_upload_forces_octet_stream_when_sniff_fails_with_no_declared_type(client):
    response = await client.post(
        "/api/admin/references/upload-media",
        json={
            "initData": signed(),
            "slot": "preview",
            "content_base64": base64.b64encode(MALICIOUS_HTML).decode(),
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["content_type"] == "application/octet-stream"


@pytest.mark.asyncio
async def test_references_upload_still_sniffs_a_real_png_correctly(client):
    tiny_png = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
    )
    response = await client.post(
        "/api/admin/references/upload-media",
        json={"initData": signed(), "slot": "preview", "content_base64": base64.b64encode(tiny_png).decode()},
    )
    assert response.status_code == 200, response.text
    assert response.json()["content_type"] == "image/png"


# ---------------------------------------------------------------------------
# /api/admin/sylvex-test/upload-file
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_sylvex_test_upload_forces_octet_stream_when_sniff_fails_despite_malicious_declared_type(client):
    response = await client.post(
        "/api/admin/sylvex-test/upload-file",
        json={
            "initData": signed(),
            "content_type": "text/html",
            "content_base64": base64.b64encode(MALICIOUS_HTML).decode(),
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["content_type"] == "application/octet-stream"
    assert body["url"].split("?")[0].endswith(".bin")


@pytest.mark.asyncio
async def test_sylvex_test_upload_forces_octet_stream_when_sniff_fails_with_no_declared_type(client):
    response = await client.post(
        "/api/admin/sylvex-test/upload-file",
        json={"initData": signed(), "content_base64": base64.b64encode(MALICIOUS_HTML).decode()},
    )
    assert response.status_code == 200, response.text
    assert response.json()["content_type"] == "application/octet-stream"


# ---------------------------------------------------------------------------
# /api/public/storage/{object_key:path} - X-Content-Type-Options: nosniff
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_public_storage_object_sets_nosniff_header(client, monkeypatch):
    # services/security.py's SecurityMiddleware already unconditionally
    # stamps X-Content-Type-Options: nosniff onto every media_path response
    # (which /api/public/storage/* is) in its secured_send() wrapper - this
    # locks that guarantee in with a regression test for this exact route,
    # rather than adding a second, redundant nosniff header in the route
    # handler itself (which would send a malformed "nosniff, nosniff" value).
    import main
    from services.media_access import sign_media_url

    def fake_get_object_range(key, range_header):
        body = io.BytesIO(b"hello world")
        return body, "application/octet-stream", 11, 11, 0, 10

    monkeypatch.setattr(main, "storage_get_object_range", fake_get_object_range)
    url = sign_media_url("/api/public/storage/generated/references/preview/test.bin")

    response = await client.get(url)
    assert response.status_code == 200, response.text
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.content == b"hello world"


@pytest.mark.asyncio
async def test_public_storage_object_forces_safe_content_type_and_attachment_for_a_dot_bin_key(client, monkeypatch):
    # Belt-and-suspenders check for the exploit scenario itself: even if a
    # malicious content_type had been stored against a .bin key (the shape
    # the sniff-failure fallback always produces), the storage route must
    # serve it with a safe, non-renderable Content-Type and as an
    # attachment - never inline as text/html.
    import main
    from services.media_access import sign_media_url

    def fake_get_object_range(key, range_header):
        body = io.BytesIO(MALICIOUS_HTML)
        return body, "text/html", len(MALICIOUS_HTML), len(MALICIOUS_HTML), 0, len(MALICIOUS_HTML) - 1

    monkeypatch.setattr(main, "storage_get_object_range", fake_get_object_range)
    url = sign_media_url("/api/public/storage/generated/references/preview/evil.bin")

    response = await client.get(url)
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].split(";")[0] != "text/html"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers.get("content-disposition") == "attachment"
