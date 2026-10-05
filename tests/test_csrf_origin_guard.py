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


def test_origin_allowed_is_a_noop_when_website_origins_unset_outside_production(monkeypatch):
    monkeypatch.delenv('WEBSITE_ORIGINS', raising=False)
    monkeypatch.delenv('RAILWAY_ENVIRONMENT_ID', raising=False)
    monkeypatch.setenv('APP_ENV', 'test')
    assert origin_allowed({}) is True
    assert origin_allowed({b'origin': b'https://evil.example'}) is True


def test_origin_allowed_fails_closed_in_production_when_website_origins_unset(monkeypatch):
    # A misconfigured production deploy (WEBSITE_ORIGINS simply never set)
    # must never silently disable this guard - CORS being unconfigured does
    # NOT stop the browser from sending a forged state-changing request or
    # the server from executing it, only from letting the attacker's JS
    # read the response, which a pure CSRF attack never needed anyway. So
    # with nothing configured to check a request's Origin against, the
    # guard must reject every request, not wave everything through.
    monkeypatch.delenv('WEBSITE_ORIGINS', raising=False)
    monkeypatch.delenv('RAILWAY_ENVIRONMENT_ID', raising=False)
    monkeypatch.setenv('APP_ENV', 'production')
    assert origin_allowed({}) is False
    # Even a header that looks like the real website must not be trusted -
    # there is no allowlist to check it against, so it proves nothing.
    assert origin_allowed({b'origin': b'https://sylvex.ai'}) is False
    assert origin_allowed({b'referer': b'https://sylvex.ai/account'}) is False


def test_origin_allowed_also_fails_closed_when_railway_environment_id_marks_production(monkeypatch):
    # is_production() treats RAILWAY_ENVIRONMENT_ID as production too, even
    # without APP_ENV explicitly set to 'production' - the guard must agree.
    monkeypatch.delenv('WEBSITE_ORIGINS', raising=False)
    monkeypatch.delenv('APP_ENV', raising=False)
    monkeypatch.setenv('RAILWAY_ENVIRONMENT_ID', 'prod-123')
    assert origin_allowed({}) is False


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


# ---------------------------------------------------------------------------
# Integration: production fail-closed when WEBSITE_ORIGINS is unset - a
# misconfigured prod deploy must refuse these routes outright, not silently
# run with the CSRF guard disabled.
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_web_account_route_fails_closed_in_production_without_website_origins(monkeypatch):
    monkeypatch.delenv('WEBSITE_ORIGINS', raising=False)
    monkeypatch.delenv('RAILWAY_ENVIRONMENT_ID', raising=False)
    monkeypatch.setenv('APP_ENV', 'production')
    async with _client(_app()) as client:
        # Even a header that looks like the real website must not get
        # through - there is no allowlist configured to check it against.
        r = await client.post('/api/web/account/password/change', json={}, headers={'Origin': 'https://sylvex.ai'})
        assert r.status_code == 403
        assert r.json()['error'] == 'origin_not_allowed'


@pytest.mark.asyncio
async def test_cookie_fallback_route_fails_closed_in_production_without_website_origins(monkeypatch):
    monkeypatch.delenv('WEBSITE_ORIGINS', raising=False)
    monkeypatch.delenv('RAILWAY_ENVIRONMENT_ID', raising=False)
    monkeypatch.setenv('APP_ENV', 'production')
    monkeypatch.setenv('WEB_SESSION_SECRET', 'test-only-web-session-secret')
    monkeypatch.setattr('services.security.resolve_web_session_uid', lambda account_id: 777)
    token = create_web_session_token(123)
    async with _client(_app()) as client:
        r = await client.post(
            '/api/public/payments/paypal/create-order', json={},
            headers={'Cookie': f'sylvex_web_session={token}', 'Origin': 'https://sylvex.ai'},
        )
        assert r.status_code == 403
        assert r.json()['error'] == 'origin_not_allowed'


# ---------------------------------------------------------------------------
# runtime_checks.validate_runtime(): startup must refuse to even start in
# production when WEBSITE_ORIGINS is unset, as the second, independent
# backstop for the same misconfiguration.
# ---------------------------------------------------------------------------

@pytest.fixture
def runtime_module(monkeypatch):
    import importlib.util
    from pathlib import Path
    path = Path(__file__).resolve().parents[1] / 'services/runtime_checks.py'
    spec = importlib.util.spec_from_file_location('runtime_checks_under_test_for_website_origins', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    # This sandbox may run on an older Python than the project targets;
    # neutralize that unrelated gate so only the WEBSITE_ORIGINS check
    # under test here is exercised (see tests/test_runtime_checks.py,
    # whose own tests are skipped/failing in this sandbox for that exact
    # pre-existing, unrelated reason).
    monkeypatch.setattr(module.sys, 'version_info', (3, 12, 0))
    values = {
        'APP_ENV': 'production', 'R2_BUCKET': 'test', 'R2_ENDPOINT': 'https://storage.example.com',
        'R2_ACCESS_KEY_ID': 'test', 'R2_SECRET_ACCESS_KEY': 'test', 'DATABASE_URL': 'postgresql://test',
        'BOT_TOKEN': 'test', 'WEBAPP_URL': 'https://app.example.com', 'ENABLE_DEV_PAYMENTS': '0',
        'PROSTUDIO_MOCK_GENERATION': '0', 'TELEGRAM_PAYMENT_WEBHOOK_SECRET': 'test-secret',
        'WEBSITE_ORIGINS': 'https://sylvex.ai',
    }
    for key, value in values.items():
        monkeypatch.setenv(key, value)
    return module


def test_validate_runtime_refuses_to_start_in_production_without_website_origins(runtime_module, monkeypatch):
    monkeypatch.delenv('WEBSITE_ORIGINS')
    with pytest.raises(RuntimeError, match='WEBSITE_ORIGINS'):
        runtime_module.validate_runtime()


def test_validate_runtime_starts_fine_in_production_with_website_origins_configured(runtime_module):
    runtime_module.validate_runtime()


def test_validate_runtime_does_not_require_website_origins_outside_production(monkeypatch):
    import importlib.util
    from pathlib import Path
    path = Path(__file__).resolve().parents[1] / 'services/runtime_checks.py'
    spec = importlib.util.spec_from_file_location('runtime_checks_under_test_dev_mode', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module.sys, 'version_info', (3, 12, 0))
    monkeypatch.delenv('WEBSITE_ORIGINS', raising=False)
    monkeypatch.delenv('RAILWAY_ENVIRONMENT_ID', raising=False)
    monkeypatch.setenv('APP_ENV', 'development')
    module.validate_runtime()
