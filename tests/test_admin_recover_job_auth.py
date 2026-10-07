"""Audit item: the admin Object/Prostudio stale-job recovery endpoint
(POST /api/admin/prostudio/recover-job/{job_id}) used to run its OWN
standalone auth check - a single telegram_id configured via the legacy
ADMIN_ID env var (PROSTUDIO_ADMIN_ID), loosely cross-checked against
init_data "if BOT_TOKEN" was set - instead of the canonical _admin_actor()
mechanism every other /api/admin/* route already uses. That meant a second,
separate credential controlled the whole recovery surface, with neither
check actually enforced if BOT_TOKEN/ADMIN_ID happened to be unset.

The fix removes that standalone check entirely and routes through
_admin_actor(data, request, owner_only=True) - the exact same mechanism
admin_set()/admin_dashboard()/etc. use (see test_admin_service_token_auth.py
for that mechanism's own dedicated coverage). This file proves: (1) the
standard admin credential (Telegram initData for the owner, or a valid
service-token-authenticated owner) now works on this endpoint exactly as it
does on any other /api/admin/* route; (2) missing/invalid auth is still
rejected; (3) the OLD standalone ADMIN_ID-based identity is no longer an
alternate bypass - even with a perfectly valid, correctly signed initData
for that exact legacy id, the request is rejected unless that id is also a
real admin_users owner."""
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
LEGACY_ADMIN_ID = 777  # simulates the old ADMIN_ID env var's value
RANDOM_ID = 424242


def _pglite_available():
    return bool(os.getenv("SYLVEX_TEST_NODE") and os.getenv("SYLVEX_PGLITE_MODULE"))


class _FakeAuditCursor:
    def execute(self, sql, params=()):
        pass

    def fetchone(self):
        # No admin_users row ever matches in this fake DB - every caller
        # that reaches a real admin_users lookup (anyone but the owner
        # initData shortcut) is correctly denied, exactly as an empty real
        # table would deny them.
        return None

    def close(self):
        pass


class _FakeAuditConnection:
    """Stands in for db_connect() when no real DB is available in this run -
    swallows the admin_audit_log INSERT _admin_audit() issues without
    touching any real database, so the auth-only tests below don't need
    pglite just to exercise the (now unconditional) post-recovery audit
    write. See test_admin_recover_job_audit_log.py for the real-SQL proof
    that the INSERT itself is well-formed."""
    def cursor(self):
        return _FakeAuditCursor()

    def commit(self):
        pass

    def rollback(self):
        pass

    def close(self):
        pass


def signed(uid, age=0):
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
    # The legacy env-configured id this endpoint used to trust directly -
    # proven below to no longer grant anything by itself.
    monkeypatch.setattr(main, "PROSTUDIO_ADMIN_ID", LEGACY_ADMIN_ID)

    if _pglite_available():
        from pglite_adapter import Database

        database = Database()
        monkeypatch.setattr(main, "DATABASE_URL", "pglite://test")
        monkeypatch.setattr(main, "db_connect", lambda *a, **k: database.connect())
        monkeypatch.setattr(main, "ADMIN_SCHEMA_READY", False)
    else:
        # No real DB in this run - a successful recovery now also writes an
        # admin_audit_log entry (remediation item #15), so even the
        # auth-only tests below need *some* working db_connect/ensure_admin_tables
        # for that write to land on, not a real Postgres. A trivial in-memory
        # fake stands in; the dedicated real-SQL audit-log test file verifies
        # the actual INSERT against pglite instead.
        monkeypatch.setattr(main, "DATABASE_URL", "fake://test")
        monkeypatch.setattr(main, "ensure_admin_tables", lambda: None)
        monkeypatch.setattr(main, "db_connect", lambda *a, **k: _FakeAuditConnection())

    main.app.middleware_stack = None
    for mw in main.app.user_middleware:
        if mw.cls is SecurityMiddleware:
            mw.kwargs["quota_check"] = AsyncMock()

    return main.app


@pytest.fixture
def client(app):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


@pytest.fixture
def recovery_spy(monkeypatch):
    import main

    calls = []

    def fake_recover(job_id, force=False):
        calls.append((job_id, force))
        return {"recovered": True, "reason": "test_stub"}

    monkeypatch.setattr(main, "recover_stale_prostudio_job", fake_recover)
    return calls


# ---------------------------------------------------------------------------
# Valid standard admin auth must work exactly like every other /api/admin/*
# endpoint - both the Mini App initData path and the Support Bot service-
# token path.
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_owner_init_data_recovers_the_job(client, recovery_spy):
    response = await client.post(
        "/api/admin/prostudio/recover-job/job-123",
        headers={"X-Telegram-Init-Data": signed(uid=OWNER_ID)},
        json={"force": True},
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["ok"] is True
    assert data["recovered"] is True
    assert recovery_spy == [("job-123", True)]


@pytest.mark.asyncio
@pytest.mark.skipif(not _pglite_available(), reason="Set SYLVEX_TEST_NODE and SYLVEX_PGLITE_MODULE to run real-SQL tests")
async def test_owner_via_service_token_header_recovers_the_job(client, recovery_spy):
    """The Support Bot's own service-token transport, exactly as used on
    every other /api/admin/* route - never a special case for this one."""
    response = await client.post(
        "/api/admin/prostudio/recover-job/job-456",
        headers={"X-Admin-Service-Token": SERVICE_TOKEN},
        json={"telegram_id": OWNER_ID, "force": False},
    )
    assert response.status_code == 200, response.text
    assert response.json()["recovered"] is True
    assert recovery_spy == [("job-456", False)]


# ---------------------------------------------------------------------------
# Missing / invalid admin auth must remain rejected.
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_missing_auth_is_rejected(client, recovery_spy):
    response = await client.post("/api/admin/prostudio/recover-job/job-1", json={})
    assert response.status_code in (401, 403)
    assert recovery_spy == []


@pytest.mark.asyncio
async def test_invalid_init_data_signature_is_rejected(client, recovery_spy):
    response = await client.post(
        "/api/admin/prostudio/recover-job/job-1",
        headers={"X-Telegram-Init-Data": "user=%7B%22id%22%3A555%7D&auth_date=1&hash=not-a-real-hash"},
        json={},
    )
    assert response.status_code in (401, 403)
    assert recovery_spy == []


@pytest.mark.asyncio
@pytest.mark.skipif(not _pglite_available(), reason="Set SYLVEX_TEST_NODE and SYLVEX_PGLITE_MODULE to run real-SQL tests")
async def test_valid_telegram_user_with_no_admin_role_is_rejected(client, recovery_spy):
    """A real, correctly signed Telegram identity that simply isn't an
    admin at all must still be denied - proves this isn't just checking
    "is Telegram auth present" but the real admin_users role/ownership."""
    response = await client.post(
        "/api/admin/prostudio/recover-job/job-1",
        headers={"X-Telegram-Init-Data": signed(uid=RANDOM_ID)},
        json={},
    )
    assert response.status_code == 403
    assert response.json()["detail"] in ("admin_access_denied", "owner_access_required")
    assert recovery_spy == []


# ---------------------------------------------------------------------------
# The old standalone ADMIN_ID-based identity must no longer be an alternate
# bypass, even presented with a perfectly valid, correctly signed initData
# for that exact legacy id.
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_legacy_admin_id_init_data_no_longer_bypasses_auth(client, recovery_spy):
    """Before the fix, telegram_id == PROSTUDIO_ADMIN_ID (here 777, != the
    real owner 555) with signed init_data for that same id was enough to
    pass. After the fix it must be rejected exactly like any other
    non-admin caller - the legacy identity grants nothing by itself."""
    response = await client.post(
        "/api/admin/prostudio/recover-job/job-1",
        headers={"X-Telegram-Init-Data": signed(uid=LEGACY_ADMIN_ID)},
        json={"telegram_id": LEGACY_ADMIN_ID},
    )
    assert response.status_code != 200
    assert recovery_spy == []


@pytest.mark.asyncio
@pytest.mark.skipif(not _pglite_available(), reason="Set SYLVEX_TEST_NODE and SYLVEX_PGLITE_MODULE to run real-SQL tests")
async def test_legacy_admin_id_is_cleanly_rejected_as_admin_access_denied(client, recovery_spy):
    """Same as above, but with a real (empty) admin_users table available so
    the rejection reason is the ordinary, unambiguous admin_access_denied -
    not just an incidental database_unavailable."""
    response = await client.post(
        "/api/admin/prostudio/recover-job/job-1",
        headers={"X-Telegram-Init-Data": signed(uid=LEGACY_ADMIN_ID)},
        json={"telegram_id": LEGACY_ADMIN_ID},
    )
    assert response.status_code == 403
    assert response.json()["detail"] == "admin_access_denied"
    assert recovery_spy == []


@pytest.mark.asyncio
async def test_legacy_admin_id_via_old_body_shape_also_no_longer_works(client, recovery_spy):
    """The pre-fix handler granted access purely because telegram_id ==
    PROSTUDIO_ADMIN_ID, reading telegram_id/init_data straight out of the
    JSON body with no admin_users check at all. _admin_actor() also accepts
    init_data from the body (the same transport every other /api/admin/*
    route supports) - so this must still be verified as a *signature*, then
    checked against the real admin_users table, exactly like any other
    caller; naming the legacy id grants nothing extra and must never reach
    the recovery logic."""
    response = await client.post(
        "/api/admin/prostudio/recover-job/job-1",
        json={"telegram_id": LEGACY_ADMIN_ID, "init_data": signed(uid=LEGACY_ADMIN_ID), "force": True},
    )
    assert response.status_code != 200
    assert recovery_spy == []
