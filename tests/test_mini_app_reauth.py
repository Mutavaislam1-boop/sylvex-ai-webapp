"""Mini App initData goes stale after TELEGRAM_AUTH_MAX_AGE_SECONDS with no
way for the Telegram WebApp SDK to reissue it in place (see
services/security.py's TG_SESSION_COOKIE block) - previously the only
recovery was the user manually closing and reopening the whole Mini App.
These tests verify the sliding sylvex_tg_session cookie fallback: a
successful signed request mints/refreshes it, and a later request whose
initData has gone stale is transparently authenticated off that cookie
instead of 401ing - except on /api/admin/ routes, which must never accept it."""
import hashlib
import hmac
import json
import time
from http.cookies import SimpleCookie
from urllib.parse import urlencode
from unittest.mock import AsyncMock

import httpx
import pytest

from services.security import SecurityMiddleware, TG_SESSION_COOKIE, create_tg_session_token

TOKEN = 'test-only-bot-token'


def signed(uid=101, age=0):
    fields = {'user': json.dumps({'id': uid, 'first_name': 'Test'}), 'auth_date': str(int(time.time()) - age)}
    check = '\n'.join(f'{k}={fields[k]}' for k in sorted(fields))
    fields['hash'] = hmac.new(hmac.new(b'WebAppData', TOKEN.encode(), hashlib.sha256).digest(), check.encode(), hashlib.sha256).hexdigest()
    return urlencode(fields)


@pytest.fixture
def app(monkeypatch):
    monkeypatch.setenv('BOT_TOKEN', TOKEN)
    monkeypatch.delenv('TELEGRAM_BOT_TOKEN', raising=False)
    monkeypatch.setenv('WEB_SESSION_SECRET', 'test-only-web-session-secret')
    monkeypatch.setenv('TELEGRAM_AUTH_MAX_AGE_SECONDS', '3600')
    import main
    monkeypatch.setattr(main, 'TELEGRAM_AUTH_TOKENS', (TOKEN,))
    monkeypatch.setattr(main, 'BOT_TOKEN', TOKEN)
    monkeypatch.setattr(main, 'sync_user_to_db', lambda user: user)
    main.app.middleware_stack = None
    for mw in main.app.user_middleware:
        if mw.cls is SecurityMiddleware:
            mw.kwargs['quota_check'] = AsyncMock()
    return main.app


@pytest.fixture
def client(app):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test')


def extract_cookie_value(response, name):
    for raw in response.headers.get_list('set-cookie'):
        jar = SimpleCookie()
        jar.load(raw)
        if name in jar:
            return jar[name].value
    return None


@pytest.mark.asyncio
async def test_successful_request_mints_tg_session_cookie(client):
    r = await client.post('/api/public/telegram/sync', headers={'X-Telegram-Init-Data': signed()}, json={})
    assert r.status_code == 200
    token = extract_cookie_value(r, TG_SESSION_COOKIE)
    assert token, 'expected a fresh sylvex_tg_session cookie on a successful signed request'


@pytest.mark.asyncio
async def test_stale_init_data_without_cookie_still_401s(client):
    r = await client.post('/api/public/telegram/sync', headers={'X-Telegram-Init-Data': signed(age=7200)}, json={})
    assert r.status_code == 401
    assert r.json()['error'] == 'expired_or_invalid_telegram_user'


@pytest.mark.asyncio
async def test_stale_init_data_with_valid_cookie_recovers_seamlessly(client):
    # Simulates a browser that already holds a cookie minted from an earlier
    # successful request in this same long-running Mini App session.
    token = create_tg_session_token(101)
    r = await client.post(
        '/api/public/telegram/sync',
        headers={'X-Telegram-Init-Data': signed(age=7200), 'Cookie': f'{TG_SESSION_COOKIE}={token}'},
        json={},
    )
    # This lightweight test harness has no DATABASE_URL configured, so the
    # DB-backed user lookup itself returns {} - what matters here is that
    # the request was authenticated and handled (200), not 401'd, proving
    # the fallback resolved telegram_id and the handler used it instead of
    # re-validating the now-stale raw initData.
    assert r.status_code == 200, r.text
    # Sliding renewal: still refreshed on the fallback path too.
    assert extract_cookie_value(r, TG_SESSION_COOKIE)


@pytest.mark.asyncio
async def test_tampered_cookie_is_rejected(client):
    bad = create_tg_session_token(101)[:-4] + 'aaaa'
    r = await client.post(
        '/api/public/telegram/sync',
        headers={'X-Telegram-Init-Data': signed(age=7200), 'Cookie': f'{TG_SESSION_COOKIE}={bad}'},
        json={},
    )
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_admin_route_never_accepts_cookie_fallback(client):
    token = create_tg_session_token(101)
    r = await client.post(
        '/api/admin/me',
        headers={'X-Telegram-Init-Data': signed(age=7200), 'Cookie': f'{TG_SESSION_COOKIE}={token}'},
        json={},
    )
    assert r.status_code in (401, 403)


@pytest.mark.asyncio
async def test_fresh_init_data_on_admin_route_is_unaffected(client):
    # Sanity check the fix didn't disturb the normal (non-stale) admin path.
    r = await client.post('/api/admin/me', headers={'X-Telegram-Init-Data': signed()}, json={})
    # 403 if this uid isn't seeded as an admin, 503 if this harness has no
    # DATABASE_URL configured - never 401 (that would mean the fix broke the
    # normal, non-stale admin path).
    assert r.status_code in (200, 403, 503)
