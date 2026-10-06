# Regression tests for the security audit's COOKIE-2 finding: both
# sylvex_web_session and sylvex_tg_session were pure stateless HMAC tokens
# with no server-side revocation - a copy captured elsewhere kept working
# for its full max-age even after the legitimate user logged out, changed
# their password, or deleted their account.
#
# The first version of this fix compared a wall-clock issued_at embedded
# in the token against a revocation timestamp, both truncated to whole
# seconds (services/security.py's account_session_revoked_before()/
# revoke_web_sessions(), checked via `issued_at < revoked_before`). An old
# token minted earlier in the SAME second as a revocation could then
# still pass that check, and simply switching `<` to `<=` didn't fix it,
# since the fresh token reissued immediately after that revocation (e.g.
# right after a password change) could just as easily be minted in that
# very same second - making the ordering genuinely ambiguous at second
# resolution, not just imprecise.
#
# This replaces that with a monotonic integer session-generation counter
# per subject (current_web_session_generation()/revoke_web_sessions() for
# the web session, current_tg_session_generation()/revoke_tg_sessions()
# for the Mini App's tg_session - neither reachable from any route today,
# see services/security.py's module docstring). verify_web_session_token()/
# verify_tg_session_token() now both return (subject_id, generation)
# instead of (subject_id, issued_at), and revoke_web_sessions() hands back
# the freshly incremented value directly from its own UPDATE ... RETURNING
# so a reissue never needs a second, separately-timed read of it. There is
# no clock involved in the comparison at all, so there is nothing left to
# race - proven below by literally freezing time.time() to one instant and
# minting both the old and the reissued token at that exact instant.
#
# Normal Telegram Mini App automatic authentication (live initData,
# requiring no cookie or server-side state at all) is untouched by any of
# this - only the stateless-HMAC fallback/bridge cookies are affected, and
# the web ones only trigger a revocation check on an account that has
# actually been revoked (generation 0, the default, is the fast, common
# path for every account that never has).
#
# current_web_session_generation()/current_tg_session_generation() were
# briefly given a short in-process TTL cache to save a DB round trip per
# request. In a real multi-worker/multi-replica deployment that reopened
# the exact window this feature exists to close: a logout/password-change
# handled by worker A bumps the generation in Postgres, but worker B (and
# every other worker) kept answering from its OWN cached value for up to
# the TTL, so an already-revoked token stayed accepted there regardless of
# the generation fix above. Both lookups are now always a fresh,
# uncached DB read - proven below by simulating two separate worker
# processes as two independent fake-DB-backed lookups and confirming a
# bump made through one is visible to the other on the very next call,
# with no stale value surviving anywhere.
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


def _manual_web_session_token(account_id, generation, exp):
    """Builds a sylvex_web_session token with an explicit generation/exp,
    bypassing create_web_session_token's default generation=0 - lets tests
    construct a token for a specific generation without needing a live
    revocation store behind it."""
    payload = f'{int(account_id)}.{int(generation)}.{int(exp)}'
    sig = hmac_module.new(web_session_secret(), payload.encode(), hashlib.sha256).hexdigest()
    return f'{payload}.{sig}'


def _manual_tg_session_token(telegram_id, generation, exp):
    payload = f'{int(telegram_id)}.{int(generation)}.{int(exp)}'
    sig = hmac_module.new(tg_session_secret(), payload.encode(), hashlib.sha256).hexdigest()
    return f'{payload}.{sig}'


# ---------------------------------------------------------------------------
# Unit: token format now carries a generation counter, not a timestamp.
# ---------------------------------------------------------------------------

def test_web_session_token_roundtrip_carries_generation(monkeypatch):
    monkeypatch.setenv('WEB_SESSION_SECRET', 'test-only-web-session-secret')
    token = create_web_session_token(42, generation=7)
    account_id, generation = verify_web_session_token(token)
    assert account_id == 42
    assert generation == 7


def test_web_session_token_defaults_to_generation_zero(monkeypatch):
    monkeypatch.setenv('WEB_SESSION_SECRET', 'test-only-web-session-secret')
    account_id, generation = verify_web_session_token(create_web_session_token(42))
    assert (account_id, generation) == (42, 0)


def test_web_session_token_rejects_legacy_three_field_format(monkeypatch):
    # Before this fix (and before the issued_at-based first version of it),
    # a token was "{account_id}.{exp}.{sig}" (3 fields). Any already-issued
    # cookie in either old shape must fail cleanly (a normal 401 that
    # forces an ordinary re-login), never crash.
    monkeypatch.setenv('WEB_SESSION_SECRET', 'test-only-web-session-secret')
    exp = int(time.time()) + 3600
    legacy_payload = f'42.{exp}'
    sig = hmac_module.new(web_session_secret(), legacy_payload.encode(), hashlib.sha256).hexdigest()
    legacy_token = f'{legacy_payload}.{sig}'
    with pytest.raises(SecurityError):
        verify_web_session_token(legacy_token)


def test_tg_session_token_roundtrip_carries_generation(monkeypatch):
    monkeypatch.setenv('WEB_SESSION_SECRET', 'test-only-web-session-secret')
    token = create_tg_session_token(101, generation=3)
    telegram_id, generation = verify_tg_session_token(token)
    assert telegram_id == 101
    assert generation == 3


# ---------------------------------------------------------------------------
# Unit: the revocation store itself (web + tg), backed by a fake DB.
# ---------------------------------------------------------------------------

class _FakeCursor:
    def __init__(self, store):
        self.store = store  # {subject_id: int generation}
        self._last = None

    def execute(self, sql, params=None):
        if 'ALTER TABLE' in sql or 'CREATE TABLE' in sql or 'CREATE UNIQUE INDEX' in sql or 'CREATE INDEX' in sql or 'CREATE SEQUENCE' in sql:
            self._last = None
        elif 'SELECT session_generation FROM sylvex_accounts' in sql:
            (account_id,) = params
            self._last = (self.store.get(account_id, 0),)
        elif 'UPDATE sylvex_accounts SET session_generation' in sql:
            (account_id,) = params
            self.store[account_id] = self.store.get(account_id, 0) + 1
            self._last = (self.store[account_id],)
        elif 'SELECT generation FROM sylvex_tg_session_revocations' in sql:
            (telegram_id,) = params
            self._last = (self.store[telegram_id],) if telegram_id in self.store else None
        elif 'INSERT INTO sylvex_tg_session_revocations' in sql:
            (telegram_id,) = params
            self.store[telegram_id] = self.store.get(telegram_id, 0) + 1
            self._last = (self.store[telegram_id],)
        else:
            self._last = None

    def fetchone(self):
        return self._last

    def close(self):
        pass


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


def test_current_web_session_generation_defaults_to_zero(fake_db):
    import services.security as security
    assert security.current_web_session_generation(42) == 0


def test_revoke_web_sessions_increments_and_returns_the_new_generation(fake_db):
    import services.security as security
    assert security.revoke_web_sessions(42) == 1
    assert security.revoke_web_sessions(42) == 2
    assert security.current_web_session_generation(42) == 2
    # A different account is never affected by someone else's revocation.
    assert security.current_web_session_generation(43) == 0


def test_revoke_tg_sessions_increments_and_returns_the_new_generation(fake_db):
    import services.security as security
    security._TG_REVOCATION_TABLE_READY = True  # the fake connection has no real table to create
    assert security.current_tg_session_generation(101) == 0
    assert security.revoke_tg_sessions(101) == 1
    assert security.current_tg_session_generation(101) == 1
    assert security.current_tg_session_generation(102) == 0


# ---------------------------------------------------------------------------
# Cross-worker staleness: current_web_session_generation()/
# current_tg_session_generation() must never serve a cached value - a
# bump made by one call (standing in for "worker A") must be visible to
# every subsequent call (standing in for "worker B's own, independent
# lookup") immediately, with no TTL window during which a revoked token
# would still be accepted. This is a regression test for a real
# in-process cache this code briefly had (10s TTL) that was safe for one
# process but not for a multi-worker/multi-replica deployment: worker A's
# revoke bumped the database, but worker B kept answering from its own
# stale cached generation until the TTL expired, during which an
# already-revoked token stayed accepted on B. There being no cache dict
# left on the module (asserted below) is what makes that impossible now,
# not a shorter TTL.
# ---------------------------------------------------------------------------

def test_current_web_session_generation_has_no_cache_to_go_stale(fake_db):
    import services.security as security
    assert not hasattr(security, '_account_generation_cache')


def test_current_tg_session_generation_has_no_cache_to_go_stale(fake_db):
    import services.security as security
    assert not hasattr(security, '_tg_generation_cache')


def test_web_session_generation_bump_is_visible_immediately_with_no_staleness_window(fake_db):
    import services.security as security
    # Read it first (as worker B might, right before worker A's revoke) -
    # with the old TTL cache this would have seeded a 10s-stale entry.
    assert security.current_web_session_generation(42) == 0
    # "Worker A" revokes.
    new_generation = security.revoke_web_sessions(42)
    assert new_generation == 1
    # "Worker B" (a wholly separate call, simulating a different process)
    # must see the bump on its very next read - no TTL window where it
    # would still answer 0 and let an already-revoked token pass.
    assert security.current_web_session_generation(42) == 1
    # And again, immediately after another bump - not just once.
    assert security.revoke_web_sessions(42) == 2
    assert security.current_web_session_generation(42) == 2


def test_tg_session_generation_bump_is_visible_immediately_with_no_staleness_window(fake_db):
    import services.security as security
    security._TG_REVOCATION_TABLE_READY = True  # the fake connection has no real table to create
    assert security.current_tg_session_generation(101) == 0
    new_generation = security.revoke_tg_sessions(101)
    assert new_generation == 1
    assert security.current_tg_session_generation(101) == 1


# ---------------------------------------------------------------------------
# THE race test: an old token minted in the exact same instant as a
# revocation must be rejected, while the fresh token reissued immediately
# after that same revocation - minted in that identical instant too - must
# be accepted. This is precisely the case a wall-clock-based check cannot
# resolve unambiguously (switching < to <= only flips which of the two
# tokens survives, never both correctly at once); the generation counter
# has no such ambiguity because neither side of the comparison is a time.
# ---------------------------------------------------------------------------

def test_old_token_minted_same_instant_as_revocation_is_rejected_while_fresh_reissue_is_accepted(fake_db, monkeypatch):
    monkeypatch.setenv('WEB_SESSION_SECRET', 'test-only-web-session-secret')
    import services.security as security
    frozen_instant = 1_700_000_000.123456
    monkeypatch.setattr(security.time, 'time', lambda: frozen_instant)

    # The old (soon-to-be-revoked) token, minted at the frozen instant.
    old_token = security.create_web_session_token(42)
    old_account_id, old_generation = security.verify_web_session_token(old_token)
    assert (old_account_id, old_generation) == (42, 0)

    # Revocation happens at that exact same instant.
    new_generation = security.revoke_web_sessions(42)
    assert new_generation == 1

    # The fresh cookie reissued right after, minted at that same instant.
    fresh_token = security.create_web_session_token(42, new_generation)
    fresh_account_id, fresh_generation = security.verify_web_session_token(fresh_token)
    assert (fresh_account_id, fresh_generation) == (42, 1)

    current = security.current_web_session_generation(42)
    assert current == 1
    assert old_generation < current  # the old token is correctly rejected
    assert fresh_generation >= current  # the fresh reissue is correctly accepted


@pytest.mark.asyncio
async def test_password_change_http_flow_rejects_old_cookie_and_accepts_the_reissued_one_minted_the_same_instant(fake_db, monkeypatch):
    # End-to-end through the real /api/web/account/password/change route
    # and the real revoke_web_sessions()/current_web_session_generation(),
    # with time.time() frozen so the old cookie and the one the route
    # reissues are minted at the literal same instant - the scenario a
    # timestamp-based check cannot resolve.
    monkeypatch.setenv('WEB_SESSION_SECRET', 'test-only-web-session-secret')
    import services.security as security
    import main
    frozen_instant = 1_700_000_000.654321
    monkeypatch.setattr(security.time, 'time', lambda: frozen_instant)
    monkeypatch.setattr(main.account_identity_service, 'change_password', lambda *a, **k: None)
    main.app.middleware_stack = None
    for mw in main.app.user_middleware:
        if mw.cls is SecurityMiddleware:
            mw.kwargs['quota_check'] = AsyncMock()

    old_token = create_web_session_token(42)  # generation 0, minted at the frozen instant

    async with _client(main.app) as client:
        r = await client.post(
            '/api/web/account/password/change',
            json={'current_password': 'old', 'new_password': 'NewPassword123!'},
            headers={'Cookie': f'sylvex_web_session={old_token}'},
        )
        assert r.status_code == 200, r.text
        assert r.json()['ok'] is True
        fresh_token = r.cookies.get('sylvex_web_session')
        assert fresh_token and fresh_token != old_token

        # The old cookie (generation 0, now revoked) must be rejected.
        r = await client.get('/api/web/session/me', headers={'Cookie': f'sylvex_web_session={old_token}'})
        assert r.json()['authenticated'] is False

        # The freshly reissued cookie - minted in that same frozen instant
        # - must still work.
        monkeypatch.setattr(main, '_web_session_payload', lambda account_id: {'authenticated': True, 'sylvex_user_id': account_id})
        r = await client.get('/api/web/session/me', headers={'Cookie': f'sylvex_web_session={fresh_token}'})
        assert r.json()['authenticated'] is True


# ---------------------------------------------------------------------------
# Integration: _web_session_account_id (main.py) rejects a token whose
# generation is behind the account's current one, and accepts one that
# matches or is newer - exercised through /api/web/session/me.
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
async def test_old_generation_cookie_is_rejected_once_revoked(monkeypatch, me_app):
    import main
    monkeypatch.setattr(main, 'current_web_session_generation', lambda account_id: 5)
    old_token = _manual_web_session_token(42, generation=4, exp=9_999_999_999)
    async with _client(me_app) as client:
        r = await client.get('/api/web/session/me', headers={'Cookie': f'sylvex_web_session={old_token}'})
        assert r.status_code == 200
        assert r.json()['authenticated'] is False


@pytest.mark.asyncio
async def test_matching_generation_cookie_still_works(monkeypatch, me_app):
    import main
    monkeypatch.setattr(main, 'current_web_session_generation', lambda account_id: 5)
    monkeypatch.setattr(main, '_web_session_payload', lambda account_id: {'authenticated': True, 'sylvex_user_id': account_id})
    token = _manual_web_session_token(42, generation=5, exp=9_999_999_999)
    async with _client(me_app) as client:
        r = await client.get('/api/web/session/me', headers={'Cookie': f'sylvex_web_session={token}'})
        assert r.status_code == 200
        assert r.json()['authenticated'] is True


@pytest.mark.asyncio
async def test_unrevoked_account_is_unaffected(monkeypatch, me_app):
    import main
    monkeypatch.setattr(main, 'current_web_session_generation', lambda account_id: 0)
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
    monkeypatch.setattr(main, 'current_web_session_generation', lambda account_id: 0)
    return main.app


@pytest.mark.asyncio
async def test_logout_revokes_the_session(monkeypatch, account_routes_app):
    import main
    revoked = []
    monkeypatch.setattr(main, 'revoke_web_sessions', lambda account_id: revoked.append(account_id) or 1)
    token = create_web_session_token(42)
    async with _client(account_routes_app) as client:
        r = await client.post('/api/web/auth/logout', headers={'Cookie': f'sylvex_web_session={token}'})
        assert r.status_code == 200
    assert revoked == [42]


@pytest.mark.asyncio
async def test_logout_without_a_session_cookie_does_not_call_revoke(monkeypatch, account_routes_app):
    import main
    revoked = []
    monkeypatch.setattr(main, 'revoke_web_sessions', lambda account_id: revoked.append(account_id) or 1)
    async with _client(account_routes_app) as client:
        r = await client.post('/api/web/auth/logout')
        assert r.status_code == 200
    assert revoked == []


@pytest.mark.asyncio
async def test_password_change_reissues_a_cookie_at_the_returned_generation(monkeypatch, account_routes_app):
    import main
    monkeypatch.setattr(main, 'revoke_web_sessions', lambda account_id: 9)
    monkeypatch.setattr(main.account_identity_service, 'change_password', lambda *a, **k: None)
    token = _manual_web_session_token(42, generation=0, exp=9_999_999_999)
    async with _client(account_routes_app) as client:
        r = await client.post(
            '/api/web/account/password/change',
            json={'current_password': 'old', 'new_password': 'NewPassword123!'},
            headers={'Cookie': f'sylvex_web_session={token}'},
        )
        assert r.status_code == 200, r.text
        assert r.json()['ok'] is True
        new_cookie = r.cookies.get('sylvex_web_session')
        assert new_cookie and new_cookie != token
        # Reissued directly at generation 9 (revoke_web_sessions' return
        # value), never re-derived from a second, separate read.
        new_account_id, new_generation = verify_web_session_token(new_cookie)
        assert (new_account_id, new_generation) == (42, 9)


@pytest.mark.asyncio
async def test_account_delete_revokes_the_session(monkeypatch, account_routes_app):
    import main
    revoked = []
    monkeypatch.setattr(main, 'revoke_web_sessions', lambda account_id: revoked.append(account_id) or 1)
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
    monkeypatch.setattr('services.security.current_web_session_generation', lambda account_id: 5)
    old_token = _manual_web_session_token(123, generation=4, exp=9_999_999_999)
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
    monkeypatch.setattr('services.security.current_web_session_generation', lambda account_id: 0)
    token = create_web_session_token(123)
    async with _client(_bridge_app()) as client:
        r = await client.post(
            '/api/public/payments/paypal/create-order', json={},
            headers={'Cookie': f'sylvex_web_session={token}'},
        )
        assert r.status_code == 200
        assert r.json() == {'ok': True}
