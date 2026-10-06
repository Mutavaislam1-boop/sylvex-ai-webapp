# Regression tests for the security audit's COOKIE-2 finding: both
# sylvex_web_session and sylvex_tg_session were pure stateless HMAC tokens
# with no server-side revocation - a copy captured elsewhere kept working
# for its full max-age even after the legitimate user logged out, changed
# their password, or deleted their account. This adds a per-subject
# "revoked before" timestamp (services/security.py's
# account_session_revoked_before()/revoke_web_sessions() for the web
# session, tg_session_revoked_before()/revoke_tg_sessions() for the Mini
# App's tg_session), checked against each token's own issued_at
# (services/security.py's verify_web_session_token()/verify_tg_session_token(),
# which now both return (subject_id, issued_at) instead of a bare id).
#
# Normal Telegram Mini App automatic authentication (live initData,
# requiring no cookie or server-side state at all) is untouched by any of
# this - only the stateless-HMAC fallback/bridge cookies are affected, and
# only once something actually calls the new revoke_*() functions.
import hashlib
import hmac as hmac_module
import time
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import FastAPI

from services.security import (
    SecurityMiddleware,
    SecurityError,
    create_web_session_token,
    verify_web_session_token,
    create_tg_session_token,
    verify_tg_session_token,
    web_session_secret,
    tg_session_secret,
)


def _client(app):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test')


def _manual_web_session_token(account_id, issued_at, exp):
    """Builds a sylvex_web_session token with an explicit issued_at/exp,
    bypassing create_web_session_token's use of the real wall clock - lets
    tests compare an old token's issued_at against a revocation timestamp
    with zero timing flakiness."""
    payload = f'{int(account_id)}.{int(issued_at)}.{int(exp)}'
    sig = hmac_module.new(web_session_secret(), payload.encode(), hashlib.sha256).hexdigest()
    return f'{payload}.{sig}'


def _manual_tg_session_token(telegram_id, issued_at, exp):
    payload = f'{int(telegram_id)}.{int(issued_at)}.{int(exp)}'
    sig = hmac_module.new(tg_session_secret(), payload.encode(), hashlib.sha256).hexdigest()
    return f'{payload}.{sig}'


# ---------------------------------------------------------------------------
# Unit: token format now carries issued_at.
# ---------------------------------------------------------------------------

def test_web_session_token_roundtrip_carries_issued_at(monkeypatch):
    monkeypatch.setenv('WEB_SESSION_SECRET', 'test-only-web-session-secret')
    before = int(time.time())
    token = create_web_session_token(42)
    account_id, issued_at = verify_web_session_token(token)
    assert account_id == 42
    assert before <= issued_at <= int(time.time()) + 1


def test_web_session_token_rejects_legacy_three_field_format(monkeypatch):
    # Before this fix, a token was "{account_id}.{exp}.{sig}" (3 fields,
    # no issued_at). Any already-issued cookie in that shape must fail
    # cleanly (a normal 401 that forces an ordinary re-login), never crash.
    monkeypatch.setenv('WEB_SESSION_SECRET', 'test-only-web-session-secret')
    exp = int(time.time()) + 3600
    legacy_payload = f'42.{exp}'
    sig = hmac_module.new(web_session_secret(), legacy_payload.encode(), hashlib.sha256).hexdigest()
    legacy_token = f'{legacy_payload}.{sig}'
    with pytest.raises(SecurityError):
        verify_web_session_token(legacy_token)


def test_tg_session_token_roundtrip_carries_issued_at(monkeypatch):
    monkeypatch.setenv('WEB_SESSION_SECRET', 'test-only-web-session-secret')
    before = int(time.time())
    token = create_tg_session_token(101)
    telegram_id, issued_at = verify_tg_session_token(token)
    assert telegram_id == 101
    assert before <= issued_at <= int(time.time()) + 1


# ---------------------------------------------------------------------------
# Unit: the revocation store itself (web session, account_id-keyed).
# ---------------------------------------------------------------------------

class _FakeCursor:
    def __init__(self, store):
        self.store = store  # {account_id: datetime-like or None}
        self._last = None

    def execute(self, sql, params=None):
        if 'ALTER TABLE' in sql or 'CREATE TABLE' in sql or 'CREATE UNIQUE INDEX' in sql or 'CREATE INDEX' in sql or 'CREATE SEQUENCE' in sql:
            self._last = None
        elif 'SELECT sessions_revoked_before FROM sylvex_accounts' in sql:
            (account_id,) = params
            value = self.store.get(account_id)
            self._last = (value,) if value is not None else (None,)
        elif 'UPDATE sylvex_accounts SET sessions_revoked_before' in sql:
            (account_id,) = params
            self.store[account_id] = _FakeNow()
            self._last = None
        elif 'SELECT revoked_before FROM sylvex_tg_session_revocations' in sql:
            (telegram_id,) = params
            value = self.store.get(telegram_id)
            self._last = (value,) if value is not None else None
        elif 'INSERT INTO sylvex_tg_session_revocations' in sql:
            (telegram_id,) = params
            self.store[telegram_id] = _FakeNow()
            self._last = None
        else:
            self._last = None

    def fetchone(self):
        return self._last

    def close(self):
        pass


class _FakeNow:
    """Stands in for a psycopg2 TIMESTAMPTZ column value - only
    .timestamp() is ever called on it by the code under test."""
    def timestamp(self):
        return time.time()


class _FakeConnection:
    def __init__(self, store):
        self.store = store

    def cursor(self):
        return _FakeCursor(self.store)

    def commit(self):
        pass

    def close(self):
        pass


@pytest.fixture
def fake_db(monkeypatch):
    import db_pool
    from services import account_identity as account_identity_module
    store = {}
    connection = _FakeConnection(store)
    monkeypatch.setattr(db_pool, 'db_connect', lambda *a, **k: connection)
    # Skip the real schema migration entirely - the fake connection has no
    # real sylvex_accounts table for it to touch.
    monkeypatch.setattr(account_identity_module, 'ensure_account_tables', lambda database_url: None)
    monkeypatch.setenv('DATABASE_URL', 'postgresql://fake/db')
    monkeypatch.delenv('DATABASE_PUBLIC_URL', raising=False)
    return store


def test_account_session_revoked_before_defaults_to_never_revoked(fake_db):
    import services.security as security
    security._account_revocation_cache.clear()
    assert security.account_session_revoked_before(42) == 0


def test_revoke_web_sessions_then_account_session_revoked_before_reflects_it(fake_db):
    import services.security as security
    security._account_revocation_cache.clear()
    security.revoke_web_sessions(42)
    revoked_before = security.account_session_revoked_before(42)
    assert revoked_before > 0
    assert abs(revoked_before - int(time.time())) < 5
    # A different account is never affected by someone else's revocation.
    assert security.account_session_revoked_before(43) == 0


def test_revoke_tg_sessions_then_tg_session_revoked_before_reflects_it(fake_db):
    import services.security as security
    security._tg_revocation_cache.clear()
    security._TG_REVOCATION_TABLE_READY = True  # the fake connection has no real table to create
    assert security.tg_session_revoked_before(101) == 0
    security.revoke_tg_sessions(101)
    revoked_before = security.tg_session_revoked_before(101)
    assert revoked_before > 0
    assert security.tg_session_revoked_before(102) == 0


# ---------------------------------------------------------------------------
# Integration: _web_session_account_id (main.py) rejects a token issued
# before the account's own revocation timestamp, and accepts one issued
# after it - exercised through the actual /api/web/session/me route so the
# whole chain (cookie -> verify -> revocation check) is proven, not just
# the pieces.
# ---------------------------------------------------------------------------

@pytest.fixture
def me_app(monkeypatch):
    monkeypatch.setenv('WEB_SESSION_SECRET', 'test-only-web-session-secret')
    import main
    main.app.middleware_stack = None
    for mw in main.app.user_middleware:
        if mw.cls is SecurityMiddleware:
            mw.kwargs['quota_check'] = AsyncMock()
    return main.app


@pytest.mark.asyncio
async def test_old_cookie_is_rejected_once_revoked(monkeypatch, me_app):
    import main
    monkeypatch.setattr(main, 'account_session_revoked_before', lambda account_id: 2_000_000_000)
    old_token = _manual_web_session_token(42, issued_at=1_000_000_000, exp=9_999_999_999)
    async with _client(me_app) as client:
        r = await client.get('/api/web/session/me', headers={'Cookie': f'sylvex_web_session={old_token}'})
        assert r.status_code == 200
        assert r.json()['authenticated'] is False


@pytest.mark.asyncio
async def test_cookie_issued_after_revocation_still_works(monkeypatch, me_app):
    import main
    monkeypatch.setattr(main, 'account_session_revoked_before', lambda account_id: 1_000_000_000)
    monkeypatch.setattr(main, '_web_session_payload', lambda account_id: {'authenticated': True, 'sylvex_user_id': account_id})
    fresh_token = _manual_web_session_token(42, issued_at=2_000_000_000, exp=9_999_999_999)
    async with _client(me_app) as client:
        r = await client.get('/api/web/session/me', headers={'Cookie': f'sylvex_web_session={fresh_token}'})
        assert r.status_code == 200
        assert r.json()['authenticated'] is True


@pytest.mark.asyncio
async def test_unrevoked_account_is_unaffected(monkeypatch, me_app):
    import main
    monkeypatch.setattr(main, 'account_session_revoked_before', lambda account_id: 0)
    monkeypatch.setattr(main, '_web_session_payload', lambda account_id: {'authenticated': True, 'sylvex_user_id': account_id})
    token = create_web_session_token(42)
    async with _client(me_app) as client:
        r = await client.get('/api/web/session/me', headers={'Cookie': f'sylvex_web_session={token}'})
        assert r.status_code == 200
        assert r.json()['authenticated'] is True


# ---------------------------------------------------------------------------
# Integration: the three routes actually call revoke_web_sessions with the
# right account_id - logout, password-change, account-delete.
# ---------------------------------------------------------------------------

@pytest.fixture
def account_routes_app(monkeypatch):
    monkeypatch.setenv('WEB_SESSION_SECRET', 'test-only-web-session-secret')
    import main
    main.app.middleware_stack = None
    for mw in main.app.user_middleware:
        if mw.cls is SecurityMiddleware:
            mw.kwargs['quota_check'] = AsyncMock()
    monkeypatch.setattr(main, 'account_session_revoked_before', lambda account_id: 0)
    return main.app


@pytest.mark.asyncio
async def test_logout_revokes_the_session(monkeypatch, account_routes_app):
    import main
    revoked = []
    monkeypatch.setattr(main, 'revoke_web_sessions', lambda account_id: revoked.append(account_id))
    token = create_web_session_token(42)
    async with _client(account_routes_app) as client:
        r = await client.post('/api/web/auth/logout', headers={'Cookie': f'sylvex_web_session={token}'})
        assert r.status_code == 200
    assert revoked == [42]


@pytest.mark.asyncio
async def test_logout_without_a_session_cookie_does_not_call_revoke(monkeypatch, account_routes_app):
    import main
    revoked = []
    monkeypatch.setattr(main, 'revoke_web_sessions', lambda account_id: revoked.append(account_id))
    async with _client(account_routes_app) as client:
        r = await client.post('/api/web/auth/logout')
        assert r.status_code == 200
    assert revoked == []


@pytest.mark.asyncio
async def test_password_change_revokes_old_sessions_and_reissues_a_fresh_cookie(monkeypatch, account_routes_app):
    import main
    revoked = []
    monkeypatch.setattr(main, 'revoke_web_sessions', lambda account_id: revoked.append(account_id))
    monkeypatch.setattr(main.account_identity_service, 'change_password', lambda *a, **k: None)
    # Minted far in the past (via the manual-token helper, not the real
    # wall clock) so it's unambiguously distinct from the fresh cookie the
    # route reissues a moment later - a real create_web_session_token()
    # call for the old token could otherwise land in the same integer
    # second as the reissued one and produce an identical string, making
    # the "got a fresh cookie" assertion flaky rather than meaningful.
    token = _manual_web_session_token(42, issued_at=1_000_000_000, exp=9_999_999_999)
    async with _client(account_routes_app) as client:
        r = await client.post(
            '/api/web/account/password/change',
            json={'current_password': 'old', 'new_password': 'NewPassword123!'},
            headers={'Cookie': f'sylvex_web_session={token}'},
        )
        assert r.status_code == 200, r.text
        assert r.json()['ok'] is True
        # A fresh cookie for the SAME account must be reissued - the
        # browser that just proved its identity by changing the password
        # must not be logged out by its own action.
        new_cookie = r.cookies.get('sylvex_web_session')
        assert new_cookie and new_cookie != token
        new_account_id, new_issued_at = verify_web_session_token(new_cookie)
        assert new_account_id == 42
        assert new_issued_at > 1_000_000_000
    assert revoked == [42]


@pytest.mark.asyncio
async def test_account_delete_revokes_the_session(monkeypatch, account_routes_app):
    import main
    revoked = []
    monkeypatch.setattr(main, 'revoke_web_sessions', lambda account_id: revoked.append(account_id))
    monkeypatch.setattr(main.account_identity_service, 'delete_account', lambda *a, **k: None)
    token = create_web_session_token(42)
    async with _client(account_routes_app) as client:
        r = await client.post(
            '/api/web/account/delete', json={'password': 'whatever'},
            headers={'Cookie': f'sylvex_web_session={token}'},
        )
        assert r.status_code == 200, r.text
    assert revoked == [42]


# ---------------------------------------------------------------------------
# Integration: the website-embedded Pro Studio bridge (no Telegram
# initData, only the sylvex_web_session cookie) also respects revocation -
# a revoked cookie must not resolve to a working telegram_id there either.
# ---------------------------------------------------------------------------

def _bridge_app():
    app = FastAPI()
    app.add_middleware(SecurityMiddleware)

    @app.post('/api/public/payments/paypal/create-order')
    async def create_order():
        return {'ok': True}

    return app


@pytest.mark.asyncio
async def test_bridge_rejects_a_revoked_web_session_cookie(monkeypatch):
    monkeypatch.setenv('WEB_SESSION_SECRET', 'test-only-web-session-secret')
    monkeypatch.delenv('WEBSITE_ORIGINS', raising=False)
    monkeypatch.setattr('services.security.resolve_web_session_uid', lambda account_id: 777)
    monkeypatch.setattr('services.security.account_session_revoked_before', lambda account_id: 2_000_000_000)
    old_token = _manual_web_session_token(123, issued_at=1_000_000_000, exp=9_999_999_999)
    async with _client(_bridge_app()) as client:
        r = await client.post(
            '/api/public/payments/paypal/create-order', json={},
            headers={'Cookie': f'sylvex_web_session={old_token}'},
        )
        assert r.status_code == 401
        assert r.json()['error'] == 'invalid_init_data'


@pytest.mark.asyncio
async def test_bridge_accepts_an_unrevoked_web_session_cookie(monkeypatch):
    monkeypatch.setenv('WEB_SESSION_SECRET', 'test-only-web-session-secret')
    monkeypatch.delenv('WEBSITE_ORIGINS', raising=False)
    monkeypatch.setattr('services.security.resolve_web_session_uid', lambda account_id: 777)
    monkeypatch.setattr('services.security.account_session_revoked_before', lambda account_id: 0)
    token = create_web_session_token(123)
    async with _client(_bridge_app()) as client:
        r = await client.post(
            '/api/public/payments/paypal/create-order', json={},
            headers={'Cookie': f'sylvex_web_session={token}'},
        )
        assert r.status_code == 200
        assert r.json() == {'ok': True}
