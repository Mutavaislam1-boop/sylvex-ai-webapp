# Regression tests for the security audit's HDR-1/HDR-2/HDR-3 findings:
# missing Content-Security-Policy, missing Strict-Transport-Security, and no
# frame-ancestors policy at all (so any third-party site could iframe the
# real Pro Studio page and clickjack it).
#
# Fix: services/security.py's security_response_headers() computes a CSP
# (frame-ancestors scoped to 'self' + the real Telegram Web App embedding
# origins + WEBSITE_ORIGINS, plus object-src 'none'/base-uri 'self') and, in
# production only, Strict-Transport-Security. It must reach EVERY response -
# not just /api/* ones - because SecurityMiddleware.__call__ only runs its
# existing secured_send header-injection closure for "protected" paths
# (/api/*, /save-settings, media_path); everything else, including the
# actual Pro Studio HTML page served from the /webapp/ static mount (the one
# response frame-ancestors actually has to protect), takes an early return
# that bypassed all header injection before this fix. So this file covers
# both the secured_send path (via a protected route) and the early-return
# path (via an unprotected one), not just one of them.
import pytest
import httpx
from fastapi import FastAPI

from services.security import SecurityMiddleware, security_response_headers


def _app():
    app = FastAPI()
    app.add_middleware(SecurityMiddleware)

    @app.get('/api/public/prostudio/pricing-catalog')
    async def protected_route():
        return {'ok': True}

    @app.get('/webapp/index.html')
    async def unprotected_static_page():
        return {'ok': True}

    return app


def _client(app):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test')


# ---------------------------------------------------------------------------
# Unit-level: security_response_headers() in isolation.
# ---------------------------------------------------------------------------

def test_csp_frame_ancestors_includes_self_and_telegram_and_falls_back_to_sylvex_ai(monkeypatch):
    monkeypatch.delenv('WEBSITE_ORIGINS', raising=False)
    headers = dict(security_response_headers())
    csp = headers[b'content-security-policy'].decode()
    assert "frame-ancestors 'self' https://web.telegram.org https://*.telegram.org https://sylvex.ai" in csp
    assert "object-src 'none'" in csp
    assert "base-uri 'self'" in csp


def test_csp_frame_ancestors_reflects_configured_website_origins(monkeypatch):
    monkeypatch.setenv('WEBSITE_ORIGINS', 'https://sylvex.ai, https://www.sylvex.ai')
    headers = dict(security_response_headers())
    csp = headers[b'content-security-policy'].decode()
    assert 'https://sylvex.ai' in csp
    assert 'https://www.sylvex.ai' in csp
    # The hardcoded fallback must not silently appear alongside a real,
    # explicitly configured origin list - that would widen the policy
    # beyond what the operator actually configured.
    assert csp.count('https://sylvex.ai') == 1


def test_hstd_absent_outside_production(monkeypatch):
    monkeypatch.delenv('RAILWAY_ENVIRONMENT_ID', raising=False)
    monkeypatch.setenv('APP_ENV', 'test')
    headers = dict(security_response_headers())
    assert b'strict-transport-security' not in headers


def test_hsts_present_in_production_with_long_max_age_and_subdomains(monkeypatch):
    monkeypatch.setenv('APP_ENV', 'production')
    headers = dict(security_response_headers())
    hsts = headers[b'strict-transport-security'].decode()
    assert 'max-age=63072000' in hsts
    assert 'includeSubDomains' in hsts
    # preload is a one-way, hard-to-reverse browser-hardcoded-list
    # commitment that needs explicit site-owner opt-in - out of scope here.
    assert 'preload' not in hsts


# ---------------------------------------------------------------------------
# Integration: a "protected" route (goes through secured_send).
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_protected_route_response_carries_csp_header(monkeypatch):
    monkeypatch.delenv('WEBSITE_ORIGINS', raising=False)
    async with _client(_app()) as client:
        r = await client.get('/api/public/prostudio/pricing-catalog')
        assert r.status_code == 200
        assert "frame-ancestors 'self' https://web.telegram.org https://*.telegram.org https://sylvex.ai" in r.headers['content-security-policy']


@pytest.mark.asyncio
async def test_protected_route_has_no_hsts_outside_production(monkeypatch):
    monkeypatch.setenv('APP_ENV', 'test')
    async with _client(_app()) as client:
        r = await client.get('/api/public/prostudio/pricing-catalog')
        assert 'strict-transport-security' not in r.headers


@pytest.mark.asyncio
async def test_protected_route_has_hsts_in_production(monkeypatch):
    monkeypatch.setenv('APP_ENV', 'production')
    async with _client(_app()) as client:
        r = await client.get('/api/public/prostudio/pricing-catalog')
        assert 'max-age=63072000' in r.headers['strict-transport-security']


# ---------------------------------------------------------------------------
# Integration: an unprotected/static route - this is the gap that would have
# made the fix a near no-op (it's where the real Pro Studio HTML page is
# actually served from) if headers were only wired into secured_send.
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_unprotected_static_route_still_carries_csp_header(monkeypatch):
    monkeypatch.delenv('WEBSITE_ORIGINS', raising=False)
    async with _client(_app()) as client:
        r = await client.get('/webapp/index.html')
        assert r.status_code == 200
        assert "frame-ancestors 'self' https://web.telegram.org https://*.telegram.org https://sylvex.ai" in r.headers['content-security-policy']


@pytest.mark.asyncio
async def test_unprotected_static_route_has_hsts_in_production(monkeypatch):
    monkeypatch.setenv('APP_ENV', 'production')
    async with _client(_app()) as client:
        r = await client.get('/webapp/index.html')
        assert 'max-age=63072000' in r.headers['strict-transport-security']


@pytest.mark.asyncio
async def test_unprotected_static_route_reflects_configured_website_origins(monkeypatch):
    monkeypatch.setenv('WEBSITE_ORIGINS', 'https://sylvex.ai')
    async with _client(_app()) as client:
        r = await client.get('/webapp/index.html')
        assert 'https://sylvex.ai' in r.headers['content-security-policy']
