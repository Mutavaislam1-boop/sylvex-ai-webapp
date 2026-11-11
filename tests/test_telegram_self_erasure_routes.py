"""S7-04: the Mini App routes for deleting one's own Telegram account.

Real SQL (PGlite) and the real security middleware with signed initData;
the B09 intake is replaced, nothing is erased.
"""
import pytest

from test_admin_console_auth import USER_TG, call, env, init_data, q, ready  # noqa: F401  (fixtures)

START = "/api/account/telegram-delete/start"
CONFIRM = "/api/account/telegram-delete/confirm"


@pytest.fixture
def tg(ready, monkeypatch):
    env = ready
    q(env, "INSERT INTO users(telegram_id, username, balance) VALUES (%s, 'fixture', 317)", (USER_TG,))
    env.account = q(env, "SELECT sylvex_ensure_telegram_account(%s)", (USER_TG,))[0][0]
    env.accepted = []
    from services import account_erasure
    monkeypatch.setattr(env.main, "_self_erasure_available", lambda: True)
    monkeypatch.setattr(env.main.shop_orders, "subscription_summary", lambda *a, **k: None)

    def fake_accept(cur, account_id, *, ecosystem="website", journal=None):
        env.accepted.append((account_id, ecosystem))
        return {"accepted": True, "complete": False, "request_id": "00000000-0000-4000-8000-000000000002", "state": "queued"}

    monkeypatch.setattr(account_erasure, "accept_confirmed_request", fake_accept)
    return env


def _h(uid=USER_TG, age=0):
    return {"X-Telegram-Init-Data": init_data(uid, age=age)}


@pytest.mark.asyncio
async def test_start_then_confirm_with_telegram_identity_only(tg):
    r = await call(tg, "POST", START, headers=_h(), json_body={})
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["blocker"] is None and data["balance"] == 317 and data["confirm_token"]
    r = await call(tg, "POST", CONFIRM, headers=_h(),
                   json_body={"confirm_token": data["confirm_token"], "erasure_scope": "telegram_account_content_v1"})
    assert r.status_code == 202, r.text
    assert r.json()["accepted"] and tg.accepted == [(tg.account, "telegram")]
    assert any(h.startswith("sylvex_tg_session=") and "Max-Age=0" in h for h in r.headers.get_list("set-cookie"))


@pytest.mark.asyncio
async def test_no_telegram_identity_no_deletion(tg):
    r = await call(tg, "POST", START, json_body={})
    assert r.status_code in (401, 403)
    r = await call(tg, "POST", START, headers=_h(age=10 ** 6), json_body={})  # stale initData, no session cookie
    assert r.status_code in (401, 403)
    assert not tg.accepted


@pytest.mark.asyncio
async def test_another_persons_token_or_claimed_id_is_refused(tg):
    other = 7000000777
    q(tg, "INSERT INTO users(telegram_id) VALUES (%s)", (other,))
    q(tg, "SELECT sylvex_ensure_telegram_account(%s)", (other,))
    token = (await call(tg, "POST", START, headers=_h(other), json_body={})).json()["confirm_token"]
    r = await call(tg, "POST", CONFIRM, headers=_h(),
                   json_body={"confirm_token": token, "erasure_scope": "telegram_account_content_v1"})
    assert r.status_code == 400 and r.json()["error"] == "confirmation_invalid"
    r = await call(tg, "POST", START, headers=_h(), json_body={"telegram_id": other})
    assert r.status_code == 403
    assert not tg.accepted


@pytest.mark.asyncio
async def test_unavailable_until_the_flags_are_on(tg, monkeypatch):
    monkeypatch.setattr(tg.main, "_self_erasure_available", lambda: False)
    r = await call(tg, "POST", START, headers=_h(), json_body={})
    assert r.status_code == 503 and r.json()["error"] == "telegram_erasure_unavailable"
