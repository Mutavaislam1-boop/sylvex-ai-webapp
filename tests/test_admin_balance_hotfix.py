"""Admin balance changes (Support Bot, the main bot's /addbalance, and
later the Admin Console) all go through /api/admin/users/balance. Every
change must be visible: no silent clamp at zero, no implicit creation of a
user row for a mistyped id, and an audit row that records the delta and
where the change came from."""
import json
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
FINANCE_ID = 556
VIEWER_ID = 557
HEADERS = {"X-Admin-Service-Token": SERVICE_TOKEN}


def _pglite_available():
    return bool(os.getenv("SYLVEX_TEST_NODE") and os.getenv("SYLVEX_PGLITE_MODULE"))


pytestmark = pytest.mark.skipif(not _pglite_available(), reason="Set SYLVEX_TEST_NODE and SYLVEX_PGLITE_MODULE to run real-SQL tests")


@pytest.fixture
def db(monkeypatch):
    monkeypatch.setenv("BOT_TOKEN", TOKEN)
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.setenv("ADMIN_SERVICE_TOKEN", SERVICE_TOKEN)
    import main
    from pglite_adapter import Database

    monkeypatch.setattr(main, "TELEGRAM_AUTH_TOKENS", (TOKEN,))
    monkeypatch.setattr(main, "BOT_TOKEN", TOKEN)
    monkeypatch.setattr(main, "ADMIN_SERVICE_TOKEN", SERVICE_TOKEN)
    monkeypatch.setattr(main, "SUPERADMIN_TELEGRAM_ID", OWNER_ID)
    database = Database()
    monkeypatch.setattr(main, "DATABASE_URL", "pglite://test")
    monkeypatch.setattr(main, "db_connect", lambda *a, **k: database.connect())
    monkeypatch.setattr(main, "ADMIN_SCHEMA_READY", False)
    conn = database.connect()
    cur = conn.cursor()
    cur.execute("CREATE TABLE users (telegram_id BIGINT PRIMARY KEY, username TEXT, first_name TEXT, balance INTEGER DEFAULT 0, subscription TEXT, created_at TEXT)")
    cur.execute("INSERT INTO users (telegram_id, balance) VALUES (1001, 50)")
    conn.commit()
    main.ensure_admin_tables()
    cur.execute("""INSERT INTO admin_users (telegram_id, role, permissions, active)
                   VALUES (%s,'admin','["manage_balance"]'::jsonb,TRUE), (%s,'admin','["view_users"]'::jsonb,TRUE)""",
                (FINANCE_ID, VIEWER_ID))
    conn.commit()
    main.app.middleware_stack = None
    for mw in main.app.user_middleware:
        if mw.cls is SecurityMiddleware:
            mw.kwargs["quota_check"] = AsyncMock()
    return main, cur


async def _post(main, body):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app), base_url="http://test") as client:
        return await client.post("/api/admin/users/balance", headers=HEADERS, json=body)


def _balance(cur, uid):
    cur.execute("SELECT balance FROM users WHERE telegram_id=%s", (uid,))
    row = cur.fetchone()
    return None if row is None else int(row[0])


def _audit_rows(cur):
    cur.execute("SELECT actor_telegram_id, action, target_telegram_id, before_data, after_data, reason FROM admin_audit_log ORDER BY id")
    return cur.fetchall()


@pytest.mark.asyncio
async def test_credit_is_applied_and_audited_with_delta_and_source(db):
    main, cur = db
    r = await _post(main, {"telegram_id": FINANCE_ID, "user_id": 1001, "delta": 25, "reason": "goodwill", "source": "telegram_bot_addbalance"})
    assert r.status_code == 200, r.text
    assert r.json()["balance"] == 75
    assert _balance(cur, 1001) == 75
    (actor, action, target, before, after, reason), = _audit_rows(cur)
    after = after if isinstance(after, dict) else json.loads(after)
    before = before if isinstance(before, dict) else json.loads(before)
    assert (actor, action, target, reason) == (FINANCE_ID, "balance_changed", 1001, "goodwill")
    assert before == {"balance": 50}
    assert after == {"balance": 75, "delta": 25, "source": "telegram_bot_addbalance"}


@pytest.mark.asyncio
async def test_unknown_source_is_recorded_as_admin_api(db):
    main, cur = db
    r = await _post(main, {"telegram_id": FINANCE_ID, "user_id": 1001, "delta": 1, "source": "anything-else"})
    assert r.status_code == 200
    after = _audit_rows(cur)[0][4]
    after = after if isinstance(after, dict) else json.loads(after)
    assert after["source"] == "admin_api"


@pytest.mark.asyncio
async def test_debit_below_zero_is_refused_not_clamped(db):
    main, cur = db
    r = await _post(main, {"telegram_id": FINANCE_ID, "user_id": 1001, "delta": -51})
    assert r.status_code == 409
    assert r.json()["detail"] == "balance_would_go_negative"
    assert _balance(cur, 1001) == 50
    assert _audit_rows(cur) == []


@pytest.mark.asyncio
async def test_unknown_user_is_404_and_no_row_is_created(db):
    main, cur = db
    r = await _post(main, {"telegram_id": FINANCE_ID, "user_id": 424242, "delta": 500})
    assert r.status_code == 404
    assert _balance(cur, 424242) is None
    assert _audit_rows(cur) == []


@pytest.mark.asyncio
async def test_admin_without_manage_balance_is_refused(db):
    main, cur = db
    r = await _post(main, {"telegram_id": VIEWER_ID, "user_id": 1001, "delta": 10})
    assert r.status_code == 403
    assert _balance(cur, 1001) == 50


@pytest.mark.asyncio
async def test_non_admin_telegram_id_with_service_token_is_refused(db):
    main, cur = db
    r = await _post(main, {"telegram_id": 1001, "user_id": 1001, "delta": 10})
    assert r.status_code == 403
    assert _balance(cur, 1001) == 50
