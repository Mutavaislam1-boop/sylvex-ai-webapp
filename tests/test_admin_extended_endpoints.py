"""Regression tests for the admin API surface added for the separate SYLVEX
Support Bot: user profiles, online users, generation history, subscribers,
top spenders, and broadcast messaging. These need real SQL (FILTER, GROUP BY,
window joins) so they run only when the PGlite real-Postgres test harness is
available."""
import hashlib
import hmac
import json
import os
import sys
import time
from pathlib import Path
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
    monkeypatch.setattr(main, "_PROSTUDIO_SCHEMA_READY", False)

    conn = database.connect()
    cursor = conn.cursor()
    # created_at is TEXT in the real `users` table too - every existing admin
    # query against it (e.g. admin_dashboard's new_users_today) wraps it in
    # NULLIF(created_at,'')::timestamp, which only works for a TEXT column.
    cursor.execute("""
        CREATE TABLE users (
            telegram_id BIGINT PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            balance INTEGER DEFAULT 0,
            subscription TEXT,
            created_at TEXT
        )
    """)
    cursor.execute("""
        CREATE TABLE user_profiles (
            telegram_id BIGINT PRIMARY KEY,
            display_name TEXT,
            custom_avatar_url TEXT,
            theme_preference JSONB DEFAULT '{}'::jsonb,
            updated_at TIMESTAMP DEFAULT NOW()
        )
    """)
    # The live production `subscriptions` table predates ensure_payment_tables()'s
    # own CREATE TABLE (which types expires_at/starts_at as TIMESTAMP) and was
    # never migrated - every admin query against it uses NULLIF(col,'')::timestamp,
    # which only works against a TEXT column (against a real TIMESTAMP column it
    # fails at parse time, even with zero rows). Pre-create it here with the
    # TEXT shape production actually has, so ensure_payment_tables() no-ops on
    # it (CREATE TABLE IF NOT EXISTS) exactly like it does in production.
    cursor.execute("""
        CREATE TABLE subscriptions (
            id SERIAL PRIMARY KEY,
            telegram_id BIGINT NOT NULL,
            subscription_type TEXT,
            payment_method TEXT,
            amount INTEGER DEFAULT 0,
            currency TEXT DEFAULT 'USD',
            starts_at TEXT,
            expires_at TEXT,
            status TEXT DEFAULT 'active',
            charge_id TEXT UNIQUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()

    main.ensure_admin_tables()
    main.ensure_payment_tables()
    main.ensure_prostudio_table()

    main.app.middleware_stack = None
    for mw in main.app.user_middleware:
        if mw.cls is SecurityMiddleware:
            mw.kwargs["quota_check"] = AsyncMock()

    main.app.state.test_db = database
    return main.app


@pytest.fixture
def client(app):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


def owner_call(user_id=OWNER_ID):
    return {"service_token": SERVICE_TOKEN, "telegram_id": user_id}


def _insert_user(app, telegram_id, username="alice", name="Alice", balance=100, subscription="free"):
    conn = app.state.test_db.connect()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO users (telegram_id, username, first_name, balance, subscription) VALUES (%s,%s,%s,%s,%s)",
        (telegram_id, username, name, balance, subscription),
    )
    conn.commit()


@pytest.mark.asyncio
async def test_dashboard_reports_purchase_and_generation_totals(app, client):
    _insert_user(app, 101)
    conn = app.state.test_db.connect()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO prostudio_generation_jobs (id, telegram_id, mode, model, provider, status, cost)
        VALUES ('job-ok',101,'image','flux','byteplus','completed',10),
               ('job-bad',101,'image','flux','byteplus','failed',10)
    """)
    cursor.execute("""
        INSERT INTO purchases (telegram_id, provider, credits, amount, currency, status, charge_id)
        VALUES (101,'stars',500,1500,'USD','completed','charge-dash')
    """)
    conn.commit()

    response = await client.post("/api/admin/dashboard", json=owner_call())
    assert response.status_code == 200, response.text
    stats = response.json()["stats"]
    assert stats["generations_success"] == 1
    assert stats["generations_failed"] == 1
    assert stats["purchases_total"] == 1
    assert stats["revenue_total"] == 1500
    assert stats["credits_purchased_total"] == 500
    assert stats["error_reports"] == 0
    assert response.json()["recent_errors"] == []


@pytest.mark.asyncio
async def test_user_detail_returns_full_profile(app, client):
    _insert_user(app, 202, username="bob", name="Bob", balance=50)
    conn = app.state.test_db.connect()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO purchases (telegram_id, provider, credits, amount, currency, status, charge_id)
        VALUES (202,'stars',100,500,'USD','completed','charge-1')
    """)
    conn.commit()

    response = await client.post("/api/admin/users/detail", json={**owner_call(), "user_id": 202})
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["account"]["telegram_id"] == 202
    assert data["account"]["username"] == "bob"
    assert data["account"]["name"] == "Bob"
    assert data["account"]["balance"] == 50
    assert data["account"]["subscription"] == "free"
    assert data["account"]["total_spent"] == 500
    assert len(data["purchases"]) == 1
    assert data["purchases"][0]["charge_id"] == "charge-1"


@pytest.mark.asyncio
async def test_user_detail_404_for_unknown_user(client):
    response = await client.post("/api/admin/users/detail", json={**owner_call(), "user_id": 999999})
    assert response.status_code == 404
    assert response.json()["detail"] == "user_not_found"


@pytest.mark.asyncio
async def test_users_online_lists_recent_presence(app, client):
    _insert_user(app, 303, username="carol", name="Carol")
    conn = app.state.test_db.connect()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO app_presence (telegram_id, current_view, platform, last_seen)
        VALUES (303,'home','telegram',NOW())
    """)
    conn.commit()

    response = await client.post("/api/admin/users/online", json=owner_call())
    assert response.status_code == 200, response.text
    items = response.json()["items"]
    assert len(items) == 1
    assert items[0]["telegram_id"] == 303
    assert items[0]["name"] == "Carol"
    assert items[0]["username"] == "carol"
    assert items[0]["view"] == "home"
    assert items[0]["platform"] == "telegram"
    assert items[0]["online"] is True


@pytest.mark.asyncio
async def test_generations_filters_by_mode_and_status(app, client):
    _insert_user(app, 404)
    conn = app.state.test_db.connect()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO prostudio_generation_jobs (id, telegram_id, mode, model, provider, status, cost)
        VALUES ('job-1',404,'image','flux','byteplus','completed',10),
               ('job-2',404,'video','sora','openai','failed',20)
    """)
    conn.commit()

    response = await client.post("/api/admin/generations", json={**owner_call(), "mode": "image"})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["id"] == "job-1"

    response = await client.post("/api/admin/generations", json={**owner_call(), "status": "failed"})
    assert response.json()["items"][0]["id"] == "job-2"


@pytest.mark.asyncio
async def test_subscribers_lists_active_and_expired(app, client):
    _insert_user(app, 505, username="dave")
    conn = app.state.test_db.connect()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO subscriptions (telegram_id, subscription_type, payment_method, amount, currency, status, charge_id)
        VALUES (505,'month','stars',999,'USD','active','sub-1')
    """)
    conn.commit()

    response = await client.post("/api/admin/subscribers", json=owner_call())
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["telegram_id"] == 505
    assert body["items"][0]["username"] == "dave"
    assert body["items"][0]["plan"] == "month"
    assert body["items"][0]["amount"] == 999
    assert body["items"][0]["total_subscription_purchases"] == 1


@pytest.mark.asyncio
async def test_top_spenders_ranks_and_breaks_down_subscription_vs_credit(app, client):
    _insert_user(app, 606, username="eve")
    conn = app.state.test_db.connect()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO purchases (telegram_id, provider, credits, amount, currency, status, charge_id)
        VALUES (606,'stars',0,1000,'USD','completed','sub-charge'),
               (606,'stars',500,200,'USD','completed','credit-charge')
    """)
    cursor.execute("""
        INSERT INTO subscriptions (telegram_id, subscription_type, payment_method, amount, currency, status, charge_id)
        VALUES (606,'month','stars',1000,'USD','active','sub-charge')
    """)
    conn.commit()

    response = await client.post("/api/admin/top-spenders", json=owner_call())
    assert response.status_code == 200, response.text
    items = response.json()["items"]
    assert items[0]["telegram_id"] == 606
    assert items[0]["username"] == "eve"
    assert items[0]["total_spent"] == 1200
    assert items[0]["subscription_purchases"] == 1
    assert items[0]["credit_purchases"] == 1
    assert items[0]["rank"] == 1


@pytest.mark.asyncio
async def test_broadcast_to_specific_user_ids(app, client, monkeypatch):
    _insert_user(app, 707)
    _insert_user(app, 708)
    import main

    def fake_post(url, json=None, timeout=None):
        class Resp:
            status_code = 200
            content = b'{"ok": true}'

            def json(self):
                return {"ok": True}

        return Resp()

    monkeypatch.setattr(main.requests, "post", fake_post)

    response = await client.post("/api/admin/messages/broadcast", json={
        **owner_call(), "message": "Hello everyone", "user_ids": [707, 708],
    })
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["recipients"] == 2
    assert body["sent"] == 2


@pytest.mark.asyncio
async def test_broadcast_requires_recipients(client):
    response = await client.post("/api/admin/messages/broadcast", json={**owner_call(), "message": "hi"})
    assert response.status_code == 400
    assert response.json()["detail"] == "no_recipients"


@pytest.mark.asyncio
async def test_non_admin_service_caller_denied_on_extended_endpoints(client):
    response = await client.post("/api/admin/top-spenders", json=owner_call(user_id=999888))
    assert response.status_code == 403
    assert response.json()["detail"] == "admin_access_denied"
