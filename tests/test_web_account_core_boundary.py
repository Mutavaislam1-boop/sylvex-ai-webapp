import httpx
import pytest
from fastapi import FastAPI, Request

from services.security import SecurityMiddleware, create_web_session_token


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
