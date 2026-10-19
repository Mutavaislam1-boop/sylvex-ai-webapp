import httpx
import pytest
from fastapi import FastAPI, Request

from services.security import SecurityMiddleware, create_web_session_token, web_session_account_id_from_cookie_header


def boundary_app():
    app = FastAPI()
    app.add_middleware(SecurityMiddleware)

    @app.post('/api/account-boundary-probe')
    async def probe(request: Request):
        return {
            'auth_kind': request.state.auth_kind,
            'account_id': request.state.account_id,
            'account_storage_id': request.state.account_storage_id,
            'telegram_user': request.state.telegram_user,
            'payload': await request.json(),
        }

    return app


def full_web_chain_app():
    app = FastAPI()
    app.add_middleware(SecurityMiddleware)

    @app.get('/api/web/session/me')
    async def session_me(request: Request):
        return {'authenticated': bool(request.cookies.get('sylvex_web_session'))}

    @app.post('/api/public/prostudio/generate')
    async def generate(request: Request):
        return {
            'ok': True,
            'auth_kind': request.state.auth_kind,
            'account_id': request.state.account_id,
            'owner': request.state.account_storage_id,
        }

    return app


@pytest.mark.asyncio
async def test_web_cookie_resolves_account_server_side_and_ignores_client_telegram_claims(monkeypatch):
    monkeypatch.setenv('WEB_SESSION_SECRET', 'web-boundary-test-secret')
    monkeypatch.setenv('WEBSITE_ORIGINS', 'https://sylvex.ai')
    monkeypatch.setattr('services.security.resolve_web_session_uid', lambda account_id: 9_000_000_000_777)
    monkeypatch.setattr('services.security.current_web_session_generation', lambda account_id: 0)
    token = create_web_session_token(123)
    transport = httpx.ASGITransport(app=boundary_app())
    async with httpx.AsyncClient(transport=transport, base_url='https://api.sylvex.ai') as client:
        response = await client.post(
            '/api/account-boundary-probe?telegram_id=999&initData=forged',
            json={'telegram_id': 999, 'initData': 'forged', 'prompt': 'hello'},
            headers={'Cookie': f'sylvex_web_session={token}', 'Origin': 'https://sylvex.ai'},
        )

    assert response.status_code == 200
    body = response.json()
    assert body['auth_kind'] == 'web'
    assert body['account_id'] == 123
    assert body['account_storage_id'] == 9_000_000_000_777
    assert body['telegram_user'] is None
    assert body['payload']['telegram_id'] == 9_000_000_000_777
    assert 'initData' not in body['payload']
    assert 'init_data' not in body['payload']


@pytest.mark.asyncio
async def test_session_me_then_generate_accepts_same_split_web_cookie(monkeypatch):
    monkeypatch.setenv('WEB_SESSION_SECRET', 'web-boundary-test-secret')
    monkeypatch.setenv('WEBSITE_ORIGINS', 'https://sylvex.ai')
    monkeypatch.setattr('services.security.resolve_web_session_uid', lambda account_id: 9_000_000_000_777)
    monkeypatch.setattr('services.security.current_web_session_generation', lambda account_id: 0)
    token = create_web_session_token(123)
    transport = httpx.ASGITransport(app=full_web_chain_app())
    split_cookies = [
        ('Cookie', f'sylvex_web_session={token}'),
        ('Cookie', 'legacy_cookie="unterminated'),
    ]
    async with httpx.AsyncClient(transport=transport, base_url='https://api.sylvex.ai') as client:
        session = await client.get('/api/web/session/me', headers=split_cookies)
        generated = await client.post(
            '/api/public/prostudio/generate',
            json={'prompt': 'hello', 'mode': 'image'},
            headers=split_cookies + [('Origin', 'https://sylvex.ai')],
        )

    assert session.status_code == 200
    assert session.json()['authenticated'] is True
    assert generated.status_code == 200
    assert generated.json() == {
        'ok': True,
        'auth_kind': 'web',
        'account_id': 123,
        'owner': 9_000_000_000_777,
    }


def test_web_cookie_parser_ignores_malformed_sibling_cookie(monkeypatch):
    monkeypatch.setenv('WEB_SESSION_SECRET', 'web-boundary-test-secret')
    token = create_web_session_token(321)
    assert web_session_account_id_from_cookie_header(
        f'legacy_cookie="unterminated; sylvex_web_session={token}'
    ) == (321, 0)
