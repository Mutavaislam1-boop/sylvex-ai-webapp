# Regression tests for the CSRF fix (SYLVEX Mini App security audit,
# Phase 1): every /api/web/* mutating route, and the website-session
# cookie-fallback path used by /api/public/* when there's no Telegram
# initData at all, must reject a state-changing request whose Origin (or
# Referer) isn't one of WEBSITE_ORIGINS - closing the account-merge-takeover
# and arbitrary-password-set CSRF findings. WEBSITE_ORIGINS is unset in the
# rest of this suite (see conftest.py), so this file is the only place that
# exercises the guard with it configured; other tests proving the guard is a
# no-op by default are covered implicitly by every existing test in
# test_security_boundaries.py still passing unchanged.
import time
import pytest
import httpx
from fastapi import FastAPI
from services.security import SecurityMiddleware, origin_allowed, website_origins, create_web_session_token


def _app():
    app = FastAPI()
    app.add_middleware(SecurityMiddleware)

    @app.post('/api/web/account/password/change')
    async def web_password_change():
        return {'ok': True}

    @app.post('/api/public/payments/paypal/create-order')
    async def public_create_order():
        return {'ok': True}

    return app


def _client(app):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test')


# ---------------------------------------------------------------------------
# Unit-level: origin_allowed()/website_origins() in isolation.
# ---------------------------------------------------------------------------

def test_website_origins_parses_comma_separated_list_trims_trailing_slash(monkeypatch):
    monkeypatch.setenv('WEBSITE_ORIGINS', 'https://sylvex.ai/, https://www.sylvex.ai')
    assert website_origins() == ['https://sylvex.ai', 'https://www.sylvex.ai']


def test_origin_allowed_is_a_noop_when_website_origins_unset(monkeypatch):
    monkeypatch.delenv('WEBSITE_ORIGINS', raising=False)
    assert origin_allowed({}) is True
    assert origin_allowed({b'origin': b'https://evil.example'}) is True


def test_origin_allowed_matches_origin_header(monkeypatch):
    monkeypatch.setenv('WEBSITE_ORIGINS', 'https://sylvex.ai')
    assert origin_allowed({b'origin': b'https://sylvex.ai'}) is True
    assert origin_allowed({b'origin': b'https://evil.example'}) is False


def test_origin_allowed_falls_back_to_referer_when_origin_missing(monkeypatch):
    monkeypatch.setenv('WEBSITE_ORIGINS', 'https://sylvex.ai')
    assert origin_allowed({b'referer': b'https://sylvex.ai/account/settings'}) is True
    assert origin_allowed({b'referer': b'https://evil.example/trap'}) is False


def test_origin_allowed_rejects_when_neither_header_present(monkeypatch):
    monkeypatch.setenv('WEBSITE_ORIGINS', 'https://sylvex.ai')
    assert origin_allowed({}) is False


# ---------------------------------------------------------------------------
# Integration: the /api/web/* blanket guard (CSRF-1/2/3).
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_forged_cross_origin_post_to_web_account_route_is_rejected(monkeypatch):
    monkeypatch.setenv('WEBSITE_ORIGINS', 'https://sylvex.ai')
    async with _client(_app()) as client:
        r = await client.post('/api/web/account/password/change', json={}, headers={'Origin': 'https://evil.example'})
        assert r.status_code == 403
        assert r.json()['error'] == 'origin_not_allowed'


@pytest.mark.asyncio
async def test_forged_cross_origin_post_with_no_origin_or_referer_is_rejected(monkeypatch):
    monkeypatch.setenv('WEBSITE_ORIGINS', 'https://sylvex.ai')
    async with _client(_app()) as client:
        r = await client.post('/api/web/account/password/change', json={})
        assert r.status_code == 403
        assert r.json()['error'] == 'origin_not_allowed'


@pytest.mark.asyncio
async def test_real_website_origin_still_reaches_the_web_account_route(monkeypatch):
    monkeypatch.setenv('WEBSITE_ORIGINS', 'https://sylvex.ai')
    async with _client(_app()) as client:
        r = await client.post('/api/web/account/password/change', json={}, headers={'Origin': 'https://sylvex.ai'})
        assert r.status_code == 200
        assert r.json() == {'ok': True}


@pytest.mark.asyncio
async def test_guard_is_a_noop_when_website_origins_unset(monkeypatch):
    monkeypatch.delenv('WEBSITE_ORIGINS', raising=False)
    async with _client(_app()) as client:
        r = await client.post('/api/web/account/password/change', json={})
        assert r.status_code == 200


# ---------------------------------------------------------------------------
# Integration: the website-session cookie-fallback path (CSRF-4) - any
# /api/public/* POST reached with no Telegram initData, only the
# sylvex_web_session cookie (the website-embedded Pro Studio path).
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_forged_cross_origin_post_via_web_session_cookie_fallback_is_rejected(monkeypatch):
    monkeypatch.setenv('WEBSITE_ORIGINS', 'https://sylvex.ai')
    monkeypatch.setenv('WEB_SESSION_SECRET', 'test-only-web-session-secret')
    monkeypatch.setattr('services.security.resolve_web_session_uid', lambda account_id: 777)
    token = create_web_session_token(123)
    async with _client(_app()) as client:
        r = await client.post(
            '/api/public/payments/paypal/create-order', json={},
            headers={'Cookie': f'sylvex_web_session={token}', 'Origin': 'https://evil.example'},
        )
        assert r.status_code == 403
        assert r.json()['error'] == 'origin_not_allowed'


@pytest.mark.asyncio
async def test_real_website_origin_still_reaches_the_cookie_fallback_route(monkeypatch):
    monkeypatch.setenv('WEBSITE_ORIGINS', 'https://sylvex.ai')
    monkeypatch.setenv('WEB_SESSION_SECRET', 'test-only-web-session-secret')
    monkeypatch.setattr('services.security.resolve_web_session_uid', lambda account_id: 777)
    token = create_web_session_token(123)
    async with _client(_app()) as client:
        r = await client.post(
            '/api/public/payments/paypal/create-order', json={},
            headers={'Cookie': f'sylvex_web_session={token}', 'Origin': 'https://sylvex.ai'},
        )
        assert r.status_code == 200
        assert r.json() == {'ok': True}


@pytest.mark.asyncio
async def test_cookie_fallback_get_request_is_unaffected_by_the_guard(monkeypatch):
    # The CSRF threat model is state-changing requests; a GET reached via
    # the cookie-fallback path must never be blocked by this guard.
    monkeypatch.setenv('WEBSITE_ORIGINS', 'https://sylvex.ai')
    monkeypatch.setenv('WEB_SESSION_SECRET', 'test-only-web-session-secret')
    monkeypatch.setattr('services.security.resolve_web_session_uid', lambda account_id: 777)
    token = create_web_session_token(123)
    app = FastAPI()
    app.add_middleware(SecurityMiddleware)

    @app.get('/api/public/prostudio/active-job')
    async def active_job():
        return {'ok': True}

    async with _client(app) as client:
        r = await client.get(
            '/api/public/prostudio/active-job',
            headers={'Cookie': f'sylvex_web_session={token}', 'Origin': 'https://evil.example'},
        )
        assert r.status_code == 200
