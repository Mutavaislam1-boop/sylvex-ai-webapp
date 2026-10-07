"""Remediation item #15: POST /api/admin/prostudio/recover-job/{job_id}
already uses the canonical _admin_actor(..., owner_only=True) auth (see
test_admin_recover_job_auth.py), but - unlike every other /api/admin/*
mutation (balance_changed, subscription_changed, admin_access_changed,
reference_created, ...) - it never wrote a standard admin_audit_log entry.

Fix: a successful recovery now also calls the existing _admin_audit()
helper against the existing admin_audit_log table (no new audit system),
recording the authenticated actor, job_id, force, and the recovery
result/status as structured after_data - written only once recovery has
actually succeeded, never on an auth failure or a recovery exception.

These tests exercise the real endpoint end-to-end against a real Postgres
(pglite), verifying the actual admin_audit_log row rather than mocking the
audit mechanism away."""
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
OWNER_ID = 555
RANDOM_ID = 424242


def _pglite_available():
    return bool(os.getenv("SYLVEX_TEST_NODE") and os.getenv("SYLVEX_PGLITE_MODULE"))


pytestmark = pytest.mark.skipif(
    not _pglite_available(),
    reason="Set SYLVEX_TEST_NODE and SYLVEX_PGLITE_MODULE to run real-SQL audit-log tests",
)


def signed(uid, age=0):
    fields = {"user": json.dumps({"id": uid, "first_name": "Test"}), "auth_date": str(int(time.time()) - age)}
    check = "\n".join(f"{k}={fields[k]}" for k in sorted(fields))
    fields["hash"] = hmac.new(hmac.new(b"WebAppData", TOKEN.encode(), hashlib.sha256).digest(), check.encode(), hashlib.sha256).hexdigest()
    return urlencode(fields)


@pytest.fixture
def db(monkeypatch):
    from pglite_adapter import Database
    import main

    database = Database()
    monkeypatch.setenv("BOT_TOKEN", TOKEN)
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.setattr(main, "TELEGRAM_AUTH_TOKENS", (TOKEN,))
    monkeypatch.setattr(main, "BOT_TOKEN", TOKEN)
    monkeypatch.setattr(main, "SUPERADMIN_TELEGRAM_ID", OWNER_ID)
    monkeypatch.setattr(main, "DATABASE_URL", "pglite://test")
    monkeypatch.setattr(main, "db_connect", lambda *a, **k: database.connect())
    monkeypatch.setattr(main, "ADMIN_SCHEMA_READY", False)

    main.app.middleware_stack = None
    for mw in main.app.user_middleware:
        if mw.cls is SecurityMiddleware:
            mw.kwargs["quota_check"] = AsyncMock()

    yield database, main
    database.close()


@pytest.fixture
def client(db):
    _, main = db
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app), base_url="http://test")


def _audit_rows(database, action="prostudio_job_recovered"):
    with database.connect() as conn:
        with conn.cursor() as cur:
            # A rejected/failed call never reaches ensure_admin_tables() at
            # all (auth is checked, or the recovery call raises, before any
            # DB table is touched) - the table may simply not exist yet,
            # which is itself proof no audit entry was ever written.
            cur.execute("SELECT to_regclass('admin_audit_log')")
            if cur.fetchone()[0] is None:
                return []
            cur.execute(
                "SELECT actor_telegram_id, action, target_telegram_id, after_data FROM admin_audit_log WHERE action = %s ORDER BY id",
                (action,),
            )
            return cur.fetchall()


@pytest.mark.asyncio
async def test_successful_recovery_writes_one_audit_entry_with_actor_job_id_force_and_result(db, client, monkeypatch):
    database, main = db

    def fake_recover(job_id, force=False):
        return {"recovered": True, "reason": "stale_worker_recovered"}

    monkeypatch.setattr(main, "recover_stale_prostudio_job", fake_recover)

    response = await client.post(
        "/api/admin/prostudio/recover-job/job-999",
        headers={"X-Telegram-Init-Data": signed(uid=OWNER_ID)},
        json={"force": True},
    )
    assert response.status_code == 200, response.text
    assert response.json() == {"ok": True, "recovered": True, "reason": "stale_worker_recovered"}

    rows = _audit_rows(database)
    assert len(rows) == 1
    actor_telegram_id, action, target_telegram_id, after_data = rows[0]
    assert actor_telegram_id == OWNER_ID
    assert action == "prostudio_job_recovered"
    assert target_telegram_id is None  # no target user for this action
    after = json.loads(after_data) if isinstance(after_data, str) else after_data
    assert after["job_id"] == "job-999"
    assert after["force"] is True
    assert after["recovery"] == {"recovered": True, "reason": "stale_worker_recovered"}


@pytest.mark.asyncio
async def test_a_second_successful_recovery_writes_its_own_separate_entry(db, client, monkeypatch):
    database, main = db

    def fake_recover(job_id, force=False):
        return {"recovered": True, "reason": "stale_worker_recovered"}

    monkeypatch.setattr(main, "recover_stale_prostudio_job", fake_recover)

    for job_id, force in (("job-a", False), ("job-b", True)):
        response = await client.post(
            f"/api/admin/prostudio/recover-job/{job_id}",
            headers={"X-Telegram-Init-Data": signed(uid=OWNER_ID)},
            json={"force": force},
        )
        assert response.status_code == 200, response.text

    rows = _audit_rows(database)
    assert len(rows) == 2
    after_payloads = [json.loads(row[3]) if isinstance(row[3], str) else row[3] for row in rows]
    assert {(p["job_id"], p["force"]) for p in after_payloads} == {("job-a", False), ("job-b", True)}


@pytest.mark.asyncio
async def test_a_recovery_that_reports_not_recovered_still_writes_the_audit_entry_with_that_status(db, client, monkeypatch):
    """"Succeeds" here means the endpoint call itself completed without
    raising - recover_stale_prostudio_job() legitimately returns
    recovered=False for a job that's still within its heartbeat threshold
    (see tests/test_stale_job_recovery.py). That is a successful recovery
    *attempt*, and the audit trail must record the actual outcome, not
    silently claim recovered=True."""
    database, main = db

    def fake_recover(job_id, force=False):
        return {"recovered": False, "reason": "heartbeat_fresh"}

    monkeypatch.setattr(main, "recover_stale_prostudio_job", fake_recover)

    response = await client.post(
        "/api/admin/prostudio/recover-job/job-fresh",
        headers={"X-Telegram-Init-Data": signed(uid=OWNER_ID)},
        json={},
    )
    assert response.status_code == 200, response.text
    assert response.json()["recovered"] is False

    rows = _audit_rows(database)
    assert len(rows) == 1
    after = json.loads(rows[0][3]) if isinstance(rows[0][3], str) else rows[0][3]
    assert after["recovery"] == {"recovered": False, "reason": "heartbeat_fresh"}
    assert after["force"] is False


@pytest.mark.asyncio
async def test_a_recovery_exception_writes_no_audit_entry(db, client, monkeypatch):
    database, main = db

    def failing_recover(job_id, force=False):
        raise RuntimeError("boom")

    monkeypatch.setattr(main, "recover_stale_prostudio_job", failing_recover)

    response = await client.post(
        "/api/admin/prostudio/recover-job/job-broken",
        headers={"X-Telegram-Init-Data": signed(uid=OWNER_ID)},
        json={},
    )
    assert response.status_code == 500

    assert _audit_rows(database) == []


@pytest.mark.asyncio
async def test_unauthenticated_request_writes_no_audit_entry_and_never_calls_recovery(db, client, monkeypatch):
    database, main = db
    calls = []
    monkeypatch.setattr(main, "recover_stale_prostudio_job", lambda job_id, force=False: calls.append((job_id, force)))

    response = await client.post("/api/admin/prostudio/recover-job/job-1", json={})
    assert response.status_code in (401, 403)

    assert calls == []
    assert _audit_rows(database) == []


@pytest.mark.asyncio
async def test_authenticated_but_non_admin_request_writes_no_audit_entry(db, client, monkeypatch):
    database, main = db
    calls = []
    monkeypatch.setattr(main, "recover_stale_prostudio_job", lambda job_id, force=False: calls.append((job_id, force)))

    response = await client.post(
        "/api/admin/prostudio/recover-job/job-1",
        headers={"X-Telegram-Init-Data": signed(uid=RANDOM_ID)},
        json={},
    )
    assert response.status_code == 403

    assert calls == []
    assert _audit_rows(database) == []
