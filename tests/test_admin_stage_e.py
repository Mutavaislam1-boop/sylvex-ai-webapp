"""Admin Console stage E: finance (real money apart from free grants), the
audit log by section with object and result, and admin sign-in security
(history, ending one session, suspicious sign-ins reported)."""
import pytest

from services import admin_security as sec

pglite = pytest.mark.skipif(not __import__("os").getenv("SYLVEX_PGLITE_MODULE"), reason="needs PGlite")

from test_admin_console_auth import (  # noqa: E402,F401  (fixtures)
    ORIGIN, OWNER_TG, SUPPORT_TG, USER_TG, _cookie, call, env, init_data, login, q, ready,
)


def test_devices_are_named_without_the_full_user_agent():
    assert sec.device_label("Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit Chrome/129 Safari/537") == "Chrome · macOS"
    assert sec.device_label("Mozilla/5.0 (iPhone; CPU iPhone OS 17_0) Telegram-iOS") == "Telegram · iOS"
    assert sec.device_label("") == ""


def test_audit_sections_and_results():
    assert sec.section_of("balance_changed") == "finance" and sec.section_of("model_disabled") == "models"
    assert sec.section_of("admin_login_suspicious") == "security" and sec.section_of("whatever") == "other"
    assert sec.result_of("admin_login_failed", {}) == "failed" and sec.result_of("user_blocked", {}) == "done"
    assert sec.object_of("model_disabled", {"model": "kling_3_0"}, {}) == "model: kling_3_0"


@pytest.fixture
def world(ready, monkeypatch):
    sent = []
    monkeypatch.setattr(ready.main, "_telegram_deliver_status", lambda chat, text, *a, **k: sent.append((chat, text)) or {"ok": True})
    ready.alerts = sent
    return ready


async def admin(env, path, body, who=OWNER_TG):
    token, csrf = await login(env, who)
    return await call(env, "POST", path, cookie=token, csrf=csrf, json_body=body)


@pglite
@pytest.mark.asyncio
async def test_finance_keeps_real_money_apart_from_free_grants(world):
    env = world
    env.main.ensure_payment_tables()
    q(env, "INSERT INTO users (telegram_id, first_name, balance) VALUES (%s, 'Buyer', 0) ON CONFLICT (telegram_id) DO NOTHING", (USER_TG,))
    q(env, """INSERT INTO purchases (telegram_id, provider, credits, amount, currency, payload, charge_id, status, created_at)
              VALUES (%s, 'stripe', 500, 999, 'USD', '', 'ch_1', 'completed', NOW()),
                     (%s, 'telegram_stars', 200, 250, 'XTR', '', 'ch_2', 'completed', NOW()),
                     (%s, 'stripe', 100, 199, 'USD', '', 'ch_3', 'refunded', NOW())""", (USER_TG, USER_TG, USER_TG))
    r = await admin(env, "/api/admin/users/balance", {"user_id": USER_TG, "delta": 50, "reason_code": "error_compensation"})
    assert r.status_code == 200, r.text
    data = (await admin(env, "/api/admin/finance", {"days": 30})).json()
    assert data["revenue"] == {"USD": 9.99, "XTR": 250.0}
    assert data["credits"]["sold"] == 700 and data["buyers"] == 1
    assert data["refunds"] == [{"currency": "USD", "count": 1, "amount": 1.99}]
    assert data["credits"]["granted"] == 50  # free credits are counted apart from sold ones
    assert data["compensations"][0]["reason_code"] == "error_compensation"
    # Only signed-in staff with payments.view.
    assert (await call(env, "POST", "/api/admin/finance", json_body={"days": 30})).status_code in (401, 403)


@pglite
@pytest.mark.asyncio
async def test_sign_in_history_new_device_alert_and_ending_one_session(world):
    env = world
    token, csrf = await login(env, OWNER_TG)  # the first sign-in is never "new"
    assert env.alerts == []
    # Earlier sessions came from another network; now a new kind of device signs in.
    q(env, "UPDATE admin_sessions SET ip_hash = 'elsewhere'")
    r = await call(env, "POST", "/api/admin/v2/auth/telegram", json_body={"initData": init_data(OWNER_TG)},
                   headers={"User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0) Telegram-iOS"})
    assert r.status_code == 200
    assert len(env.alerts) == 1 and "нового устройства" in env.alerts[0][1] and "Telegram · iOS" in env.alerts[0][1]
    second, _ = _cookie(r)
    history = (await call(env, "GET", "/api/admin/v2/auth/logins", cookie=token)).json()["items"]
    assert [h["action"] for h in history][:2] == ["admin_login_suspicious", "admin_login"]
    assert history[1]["device"] == "Telegram · iOS" and history[1]["new_device"] is True
    sessions = (await call(env, "GET", "/api/admin/v2/auth/sessions", cookie=token)).json()["items"]
    other = next(s for s in sessions if not s["current"])
    assert other["device"] == "Telegram · iOS"
    r = await call(env, "POST", "/api/admin/v2/auth/sessions/revoke", cookie=token, csrf=csrf, json_body={"session_id": other["session_id"]})
    assert r.status_code == 200 and r.json()["signed_out"] is False
    assert (await call(env, "GET", "/api/admin/v2/auth/me", cookie=second)).status_code == 401
    # Someone else's session cannot be ended by a non-owner.
    s_token, s_csrf = await login(env, SUPPORT_TG)
    r = await call(env, "POST", "/api/admin/v2/auth/sessions/revoke", cookie=s_token, csrf=s_csrf,
                   json_body={"session_id": sessions[0]["session_id"]})
    assert r.status_code == 404
    # The audit log lists it under security, with its result.
    items = (await call(env, "GET", "/api/admin/v2/audit?section=security", cookie=token)).json()["items"]
    assert {i["section"] for i in items} == {"security"}
    assert any(i["action"] == "admin_session_revoked" and i["result"] == "done" for i in items)
    assert any(i["action"] == "admin_login_suspicious" and i["result"] == "failed" for i in items)
