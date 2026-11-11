"""B09 / S7-04: the admin console routes of the Telegram erasure intake.

Real SQL (PGlite) for the admin session, permissions and re-authentication;
the Bot API call and the B09 intake are replaced, nothing is sent or erased.
"""
import re

import pytest

from test_admin_console_auth import (  # noqa: F401  (fixtures)
    OWNER_TG, SUPPORT_TG, USER_TG, call, env, login, q, ready,
)

START = "/api/admin/v2/erasure/telegram/start"
CONFIRM = "/api/admin/v2/erasure/telegram/confirm"


@pytest.fixture
def tg(ready, monkeypatch):
    env = ready
    q(env, "INSERT INTO users(telegram_id, username) VALUES (%s, 'fixture')", (USER_TG,))
    env.ai_account = q(env, "SELECT sylvex_ensure_telegram_account(%s)", (USER_TG,))[0][0]
    env.sent, env.accepted = [], []
    monkeypatch.setattr(env.main, "telegram_bot_api",
                        lambda method, params: env.sent.append((method, params)) or (True, None))
    from services import account_erasure

    def fake_accept(cur, account_id, *, ecosystem="website", journal=None):
        env.accepted.append((account_id, ecosystem))
        return {"accepted": True, "complete": False, "request_id": "00000000-0000-4000-8000-000000000001",
                "state": "queued"}

    monkeypatch.setattr(account_erasure, "accept_confirmed_request", fake_accept)
    return env


def _code(env):
    return re.search(r"Код подтверждения: (\d{6})", env.sent[-1][1]["text"]).group(1)


@pytest.mark.asyncio
async def test_support_role_cannot_start_an_erasure(tg):
    token, csrf = await login(tg, SUPPORT_TG)
    r = await call(tg, "POST", START, cookie=token, csrf=csrf,
                   json_body={"telegram_id": USER_TG, "support_ref": "t#1", "reason": "x"})
    assert r.status_code == 403 and r.json()["detail"] == "admin_permission_denied"
    assert not tg.sent


@pytest.mark.asyncio
async def test_owner_needs_csrf_and_a_fresh_reauthentication(tg):
    token, csrf = await login(tg, OWNER_TG)
    body = {"telegram_id": USER_TG, "support_ref": "t#1", "reason": "user request"}
    r = await call(tg, "POST", START, cookie=token, json_body=body)
    assert r.status_code == 403 and r.json()["detail"] == "csrf_token_invalid"
    q(tg, "UPDATE admin_sessions SET reauth_at = NOW() - INTERVAL '6 minutes'")
    r = await call(tg, "POST", START, cookie=token, csrf=csrf, json_body=body)
    assert r.status_code == 403 and r.json()["detail"] == "reauth_required"
    assert not tg.sent


@pytest.mark.asyncio
async def test_owner_flow_sends_the_code_to_the_users_chat_and_accepts_after_it(tg):
    token, csrf = await login(tg, OWNER_TG)
    r = await call(tg, "POST", START, cookie=token, csrf=csrf,
                   json_body={"telegram_id": USER_TG, "support_ref": "ticket 42", "reason": "user request"})
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["ok"] and data["telegram_hint"] == "…0001"
    method, params = tg.sent[-1]
    assert method == "sendMessage" and params["chat_id"] == USER_TG
    code = _code(tg)
    assert code not in r.text
    # Wrong code: counted, committed, 400.
    r = await call(tg, "POST", CONFIRM, cookie=token, csrf=csrf,
                   json_body={"confirmation_id": data["confirmation_id"], "code": "000000" if code != "000000" else "111111",
                              "confirm_telegram_id": USER_TG})
    assert r.status_code == 400 and r.json()["error"] == "invalid_code" and r.json()["attempts_left"] == 4
    assert q(tg, "SELECT attempts FROM sylvex_tg_erasure_confirmations") == [[1]]
    r = await call(tg, "POST", CONFIRM, cookie=token, csrf=csrf,
                   json_body={"confirmation_id": data["confirmation_id"], "code": code, "confirm_telegram_id": USER_TG})
    assert r.status_code == 200, r.text
    assert r.json()["accepted"] and tg.accepted == [(tg.ai_account, "telegram")]
    actions = [row[0] for row in q(tg, "SELECT action FROM admin_audit_events WHERE action LIKE 'telegram_erasure%%' ORDER BY id")]
    assert actions == ["telegram_erasure_code_sent", "telegram_erasure_accepted"]
    risks = {row[0] for row in q(tg, "SELECT risk FROM admin_audit_events WHERE action LIKE 'telegram_erasure%%'")}
    assert risks == {"critical"}
    status = await call(tg, "GET", f"/api/admin/v2/erasure/telegram?telegram_id={USER_TG}", cookie=token)
    assert status.status_code == 200 and status.json()["codes"][0]["state"] == "confirmed"
    assert "code_hash" not in status.text


@pytest.mark.asyncio
async def test_status_needs_a_session(tg):
    r = await call(tg, "GET", f"/api/admin/v2/erasure/telegram?telegram_id={USER_TG}")
    assert r.status_code == 401
