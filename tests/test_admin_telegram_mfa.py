"""B10: TOTP for administrators on every Telegram channel.

- Mini App console: initData + TOTP; an admin without TOTP gets an
  enrollment-only session that reaches nothing but TOTP setup.
- Bots (service token) and the legacy Mini App v1 (initData in the body):
  every admin action needs a TOTP confirmation made inside the Mini App
  within 30 minutes, a Critical one within 5 minutes.
- Critical console actions: a fresh TOTP re-authentication (5 minutes);
  Telegram alone no longer re-authenticates.
- No route reaches admin data without the second factor.

Real SQL (PGlite); no network, no Telegram message is sent.
"""
import pytest

from test_admin_console_auth import (  # noqa: F401  (fixtures)
    ADMIN_TG, FINANCE_TG, ORIGIN, OWNER_TG, SERVICE_TOKEN, SUPPORT_TG, USER_TG, _cookie, _totp, _without_totp, call,
    env, init_data, login, q, ready, tg_body, totp_for,
)

BOT = {"X-Admin-Service-Token": SERVICE_TOKEN}
TEST_SECRET = "JBSWY3DPEHPK3PXPJBSWY3DPEHPK3PXP"


def _code(offset=0):
    return _totp(TEST_SECRET, offset)


def _admin_of(env, uid):
    return q(env, "SELECT a.id FROM admin_accounts a JOIN sylvex_accounts s ON s.account_id = a.account_id "
                  "WHERE s.active_telegram_id = %s", (uid,))[0][0]


def _confirmed_ago(env, uid, minutes):
    q(env, "UPDATE admin_accounts SET telegram_confirmed_at = NOW() - make_interval(mins => %s) WHERE id = %s",
      (minutes, _admin_of(env, uid)))


def _unconfirmed(env, uid):
    q(env, "UPDATE admin_accounts SET telegram_confirmed_at = NULL WHERE id = %s", (_admin_of(env, uid),))


async def _miniapp(env, uid, **body):
    body.setdefault("initData", init_data(uid))
    body.setdefault("mode", "miniapp")
    return await call(env, "POST", "/api/admin/v2/auth/telegram", json_body=body)


async def _pending_session(env, uid):
    """Mini App sign-in of an admin without TOTP: an enrollment-only session."""
    _without_totp(env, uid)
    r = await _miniapp(env, uid)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["totp_enrollment_required"] is True and data["session"]["mfa_verified"] is False
    return {"X-Admin-Session": data["session_token"]}, data["csrf_token"]


# --- Mini App sign-in -------------------------------------------------------

@pytest.mark.asyncio
async def test_miniapp_login_needs_the_totp_code(ready):
    env = ready
    q(env, "UPDATE admin_accounts SET totp_last_step = NULL")
    r = await _miniapp(env, ADMIN_TG)
    assert r.status_code == 401 and r.json()["detail"] == "totp_required"
    assert _cookie(r)[0] is None and q(env, "SELECT COUNT(*) FROM admin_sessions") == [[0]]
    code = _code()
    r = await _miniapp(env, ADMIN_TG, totp=code)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["session"]["mfa_verified"] is True and data["totp_enrollment_required"] is False
    h = {"X-Admin-Session": data["session_token"]}
    me = (await call(env, "GET", "/api/admin/v2/auth/me", headers=h)).json()
    assert me["session"]["mfa_verified"] is True and me["telegram_confirmation"]["confirmed"] is True
    # The same code cannot be used twice.
    r = await _miniapp(env, ADMIN_TG, totp=code)
    assert r.status_code == 401 and r.json()["detail"] == "totp_invalid"


@pytest.mark.asyncio
async def test_wrong_expired_and_malformed_codes_are_refused_and_lock_out(ready):
    env = ready
    q(env, "UPDATE admin_accounts SET totp_last_step = NULL")
    for bad in ("000000", _code(-3), _code(3), "12345", "abcdef"):
        r = await _miniapp(env, FINANCE_TG, totp=bad)
        assert r.status_code == 401 and r.json()["detail"] == "totp_invalid", bad
    assert q(env, "SELECT COUNT(*) FROM admin_sessions") == [[0]]
    failed = q(env, "SELECT channel FROM admin_audit_events WHERE action = 'admin_login_failed'")
    assert failed and all(row == ["miniapp"] for row in failed)
    # Five or more failures lock the authenticator for 15 minutes: even the right code is refused.
    r = await _miniapp(env, FINANCE_TG, totp=_code())
    assert r.status_code == 429 and r.json()["detail"] == "totp_locked"


@pytest.mark.asyncio
async def test_forged_init_data_never_reaches_the_totp_check(ready):
    env = ready
    r = await _miniapp(env, OWNER_TG, initData=init_data(OWNER_TG, token="forged"), totp=_code())
    assert r.status_code == 401
    r = await _miniapp(env, USER_TG, totp=_code())  # not an admin
    assert r.status_code == 403 and r.json()["detail"] == "admin_access_denied"


# --- Admin without TOTP: safe enrollment -----------------------------------

@pytest.mark.asyncio
async def test_enrollment_only_session_reaches_nothing_but_setup(ready):
    env = ready
    h, csrf = await _pending_session(env, ADMIN_TG)
    me = await call(env, "GET", "/api/admin/v2/auth/me", headers=h)
    assert me.status_code == 200 and me.json()["session"]["mfa_verified"] is False
    for method, path, body in (("GET", "/api/admin/v2/admins", None), ("GET", "/api/admin/v2/auth/sessions", None),
                               ("GET", "/api/admin/v2/audit", None), ("POST", "/api/admin/dashboard", {}),
                               ("POST", "/api/admin/me", {}), ("POST", "/api/admin/users/search", {"query": ""})):
        r = await call(env, method, path, headers=h, csrf=csrf, json_body=body)
        assert r.status_code == 403 and r.json()["detail"] == "totp_enrollment_required", (path, r.text)
    # Setting up the authenticator: QR, a wrong code, then the right one.
    r = await call(env, "POST", "/api/admin/v2/auth/totp/enroll", headers=h, csrf=csrf)
    assert r.status_code == 200, r.text
    secret = r.json()["secret"]
    r = await call(env, "POST", "/api/admin/v2/auth/totp/confirm", headers=h, csrf=csrf, json_body={"code": "000000"})
    assert r.status_code == 401
    r = await call(env, "POST", "/api/admin/v2/auth/totp/confirm", headers=h, csrf=csrf, json_body={"code": _totp(secret)})
    assert r.status_code == 200 and r.json()["session"]["mfa_verified"] is True
    # The same session is now a full one, and the bots may act for this admin.
    r = await call(env, "GET", "/api/admin/v2/admins", headers=h)
    assert r.status_code == 200, r.text
    me = (await call(env, "GET", "/api/admin/v2/auth/me", headers=h)).json()
    assert me["admin"]["totp_enabled"] is True and me["telegram_confirmation"]["confirmed"] is True
    r = await call(env, "POST", "/api/admin/admins/list", headers=BOT, json_body={"telegram_id": ADMIN_TG})
    assert r.status_code == 200, r.text
    actions = [row[0] for row in q(env, "SELECT action FROM admin_audit_events ORDER BY id")]
    assert "admin_session_mfa_pending" in actions and "admin_totp_enabled" in actions


@pytest.mark.asyncio
async def test_every_admin_can_enroll_after_rollout_so_nobody_is_locked_out(ready):
    """MFA turned on while no admin had TOTP yet, the owner included."""
    env = ready
    q(env, "UPDATE admin_accounts SET totp_secret_enc = NULL, totp_enabled_at = NULL, telegram_confirmed_at = NULL")
    for uid in (OWNER_TG, ADMIN_TG, FINANCE_TG, SUPPORT_TG):
        r = await _miniapp(env, uid)
        assert r.status_code == 200 and r.json()["totp_enrollment_required"] is True
        h, csrf = {"X-Admin-Session": r.json()["session_token"]}, r.json()["csrf_token"]
        secret = (await call(env, "POST", "/api/admin/v2/auth/totp/enroll", headers=h, csrf=csrf)).json()["secret"]
        r = await call(env, "POST", "/api/admin/v2/auth/totp/confirm", headers=h, csrf=csrf, json_body={"code": _totp(secret)})
        assert r.status_code == 200, (uid, r.text)
        assert (await call(env, "GET", "/api/admin/v2/permissions", headers=h)).status_code == 200


@pytest.mark.asyncio
async def test_a_session_without_totp_cannot_replace_an_existing_authenticator(ready):
    """A Mini App session from before MFA was enforced (no TOTP passed) of
    an admin who has TOTP: Telegram alone may not rotate the secret."""
    env = ready
    token, csrf = await login(env, ADMIN_TG)
    q(env, "UPDATE admin_sessions SET mfa_at = NULL")
    r = await call(env, "GET", "/api/admin/v2/admins", cookie=token)
    assert r.status_code == 401 and r.json()["detail"] == "totp_required"
    for path in ("/api/admin/v2/auth/totp/enroll", "/api/admin/v2/auth/totp/confirm"):
        r = await call(env, "POST", path, cookie=token, csrf=csrf, json_body={"code": _code()})
        assert r.status_code == 401 and r.json()["detail"] == "totp_required", path
    r = await call(env, "POST", "/api/admin/v2/auth/reauth", cookie=token, csrf=csrf,
                   json_body={"initData": init_data(ADMIN_TG)})
    assert r.status_code == 401 and r.json()["detail"] == "totp_required"
    assert q(env, "SELECT COUNT(*) FROM admin_accounts WHERE totp_pending_enc IS NOT NULL") == [[0]]


@pytest.mark.asyncio
async def test_enrollment_needs_a_fresh_telegram_confirmation(ready):
    env = ready
    h, csrf = await _pending_session(env, SUPPORT_TG)
    q(env, "UPDATE admin_sessions SET reauth_at = NOW() - INTERVAL '6 minutes'")
    r = await call(env, "POST", "/api/admin/v2/auth/totp/enroll", headers=h, csrf=csrf)
    assert r.status_code == 403 and r.json()["detail"] == "reauth_required"
    r = await call(env, "POST", "/api/admin/v2/auth/reauth", headers=h, csrf=csrf,
                   json_body={"initData": init_data(ADMIN_TG)})  # someone else's Telegram
    assert r.status_code == 401
    r = await call(env, "POST", "/api/admin/v2/auth/reauth", headers=h, csrf=csrf,
                   json_body={"initData": init_data(SUPPORT_TG)})
    assert r.status_code == 200
    # It re-opened TOTP setup only - nothing else.
    assert (await call(env, "GET", "/api/admin/v2/admins", headers=h)).json()["detail"] == "totp_enrollment_required"
    assert (await call(env, "POST", "/api/admin/v2/auth/totp/enroll", headers=h, csrf=csrf)).status_code == 200


# --- Critical actions in the console ------------------------------------------

@pytest.mark.asyncio
async def test_critical_actions_need_a_fresh_totp_reauth_valid_five_minutes(ready):
    env = ready
    token, csrf = await login(env, OWNER_TG)
    path, body = f"/api/admin/v2/admins/{env.ids['support']}", {"status": "suspended", "reason": "test"}
    q(env, "UPDATE admin_sessions SET reauth_at = NOW() - INTERVAL '301 seconds'")
    r = await call(env, "PATCH", path, cookie=token, csrf=csrf, json_body=body)
    assert r.status_code == 403 and r.json()["detail"] == "reauth_required"
    q(env, "UPDATE admin_accounts SET totp_last_step = NULL")
    for bad in ({"initData": init_data(OWNER_TG)}, {}, {"totp": "000000"}, {"totp": _code(-3)}):
        r = await call(env, "POST", "/api/admin/v2/auth/reauth", cookie=token, csrf=csrf, json_body=bad)
        assert r.status_code == 401, bad
    r = await call(env, "POST", "/api/admin/v2/auth/reauth", cookie=token, csrf=csrf, json_body={"totp": _code()})
    assert r.status_code == 200 and r.json()["reauth_valid_seconds"] == 300
    r = await call(env, "PATCH", path, cookie=token, csrf=csrf, json_body=body)
    assert r.status_code == 200, r.text


# --- Bots and the legacy Mini App v1 -----------------------------------------

@pytest.mark.asyncio
async def test_bot_actions_need_a_recent_telegram_confirmation(ready):
    env = ready
    _unconfirmed(env, OWNER_TG)
    me = await call(env, "POST", "/api/admin/me", headers=BOT, json_body={"telegram_id": OWNER_TG})
    assert me.status_code == 200
    mfa = me.json()["admin"]["mfa"]
    assert mfa["confirmed"] is False and mfa["totp_enabled"] is True and mfa["confirm_window_seconds"] == 1800
    r = await call(env, "POST", "/api/admin/users/search", headers=BOT, json_body={"telegram_id": OWNER_TG, "query": ""})
    assert r.status_code == 403 and r.json()["detail"] == "totp_confirmation_required"
    _confirmed_ago(env, OWNER_TG, 31)
    r = await call(env, "POST", "/api/admin/users/search", headers=BOT, json_body={"telegram_id": OWNER_TG, "query": ""})
    assert r.status_code == 403 and r.json()["detail"] == "totp_confirmation_required"
    _confirmed_ago(env, OWNER_TG, 29)
    r = await call(env, "POST", "/api/admin/users/search", headers=BOT, json_body={"telegram_id": OWNER_TG, "query": ""})
    assert r.status_code == 200, r.text


@pytest.mark.asyncio
async def test_critical_bot_actions_need_a_confirmation_from_the_last_five_minutes(ready):
    env = ready
    q(env, "INSERT INTO users (telegram_id, first_name, balance) VALUES (%s, 'New', 10)", (USER_TG,))
    critical = {"telegram_id": OWNER_TG, "user_id": USER_TG, "permissions": ["view_users"]}
    _confirmed_ago(env, OWNER_TG, 6)
    r = await call(env, "POST", "/api/admin/admins/set", headers=BOT, json_body=critical)
    assert r.status_code == 403 and r.json()["detail"] == "critical_confirmation_required"
    # A High action is still fine within the 30 minutes.
    r = await call(env, "POST", "/api/admin/users/balance", headers=BOT,
                   json_body={"telegram_id": OWNER_TG, "user_id": USER_TG, "delta": 1, "reason": "test"})
    assert r.status_code == 200, r.text
    _confirmed_ago(env, OWNER_TG, 4)
    r = await call(env, "POST", "/api/admin/admins/set", headers=BOT, json_body=critical)
    assert r.status_code == 200, r.text


@pytest.mark.asyncio
async def test_bot_rbac_is_unchanged_and_checked_first(ready):
    env = ready
    q(env, "INSERT INTO users (telegram_id, first_name) VALUES (%s, 'New')", (USER_TG,))
    r = await call(env, "POST", "/api/admin/admins/set", headers=BOT,
                   json_body={"telegram_id": ADMIN_TG, "user_id": USER_TG, "permissions": ["view_users"]})
    assert r.status_code == 403 and r.json()["detail"] == "console_required_for_critical_action"
    r = await call(env, "POST", "/api/admin/users/balance", headers=BOT,
                   json_body={"telegram_id": SUPPORT_TG, "user_id": USER_TG, "delta": 1, "reason": "x"})
    assert r.status_code == 403 and r.json()["detail"] == "admin_permission_denied"
    r = await call(env, "POST", "/api/admin/users/search", headers=BOT, json_body={"telegram_id": USER_TG, "query": ""})
    assert r.status_code == 403 and r.json()["detail"] == "admin_access_denied"


@pytest.mark.asyncio
async def test_bot_admin_without_totp_must_enroll_first(ready):
    env = ready
    _without_totp(env, FINANCE_TG)
    q(env, "UPDATE admin_accounts SET telegram_confirmed_at = NOW()")  # a confirmation alone is not enough
    r = await call(env, "POST", "/api/admin/finance", headers=BOT, json_body={"telegram_id": FINANCE_TG})
    assert r.status_code == 403 and r.json()["detail"] == "totp_enrollment_required"


@pytest.mark.asyncio
async def test_legacy_mini_app_v1_init_data_needs_the_same_confirmation(ready):
    env = ready
    body = {"initData": init_data(ADMIN_TG), "query": ""}
    _unconfirmed(env, ADMIN_TG)
    assert (await call(env, "POST", "/api/admin/me", json_body={"initData": init_data(ADMIN_TG)})).status_code == 200
    r = await call(env, "POST", "/api/admin/users/search", json_body=body)
    assert r.status_code == 403 and r.json()["detail"] == "totp_confirmation_required"
    _confirmed_ago(env, ADMIN_TG, 1)
    r = await call(env, "POST", "/api/admin/users/search", json_body=body)
    assert r.status_code == 200, r.text
    r = await call(env, "POST", "/api/admin/users/search", json_body=dict(body, initData=init_data(ADMIN_TG, token="x")))
    assert r.status_code in (401, 403) and r.status_code != 200


@pytest.mark.asyncio
async def test_where_the_telegram_confirmation_comes_from_and_ends(ready):
    env = ready
    q(env, "UPDATE admin_accounts SET telegram_confirmed_at = NULL")
    # A browser (web) sign-in is not a Telegram confirmation...
    from test_admin_console_auth import _add_password
    _add_password(env, ADMIN_TG)
    r = await call(env, "POST", "/api/admin/v2/auth/web",
                   json_body={"email": "admin@test.com", "password": "correcthorsebattery", "totp": totp_for(env, ADMIN_TG)})
    assert r.status_code == 200, r.text
    web, web_csrf = _cookie(r)[0], r.json()["csrf_token"]
    q(env, "UPDATE admin_accounts SET totp_last_step = NULL")
    r = await call(env, "POST", "/api/admin/v2/auth/reauth", cookie=web, csrf=web_csrf, json_body={"totp": _code()})
    assert r.status_code == 200
    assert q(env, "SELECT telegram_confirmed_at IS NULL FROM admin_accounts WHERE id = %s", (_admin_of(env, ADMIN_TG),)) == [[True]]
    # ...a Mini App sign-in with TOTP is, and so is a TOTP reauth inside the Mini App.
    token, csrf = await login(env, ADMIN_TG)
    assert q(env, "SELECT telegram_confirmed_at IS NOT NULL FROM admin_accounts WHERE id = %s", (_admin_of(env, ADMIN_TG),)) == [[True]]
    _confirmed_ago(env, ADMIN_TG, 20)
    r = await call(env, "POST", "/api/admin/v2/auth/reauth", cookie=token, csrf=csrf, json_body={"totp": totp_for(env, ADMIN_TG)})
    assert r.status_code == 200
    me = await call(env, "POST", "/api/admin/me", headers=BOT, json_body={"telegram_id": ADMIN_TG})
    assert me.json()["admin"]["mfa"]["critical"] is True
    # "Sign out everywhere" also ends what the bots may do.
    assert (await call(env, "POST", "/api/admin/v2/auth/logout-all", cookie=token, csrf=csrf)).status_code == 200
    r = await call(env, "POST", "/api/admin/admins/list", headers=BOT, json_body={"telegram_id": ADMIN_TG})
    assert r.status_code == 403 and r.json()["detail"] == "totp_confirmation_required"


# --- Lost authenticator: owner reset -------------------------------------------

@pytest.mark.asyncio
async def test_owner_resets_a_lost_authenticator(ready):
    env = ready
    support_token, _ = await login(env, SUPPORT_TG)
    admin_token, admin_csrf = await login(env, ADMIN_TG)
    path = f"/api/admin/v2/admins/{env.ids['support']}/totp/reset"
    # Not the owner (even with admins.permissions.edit): refused.
    r = await call(env, "POST", path, cookie=admin_token, csrf=admin_csrf, json_body={"reason": "lost phone"})
    assert r.status_code == 403 and r.json()["detail"] == "owner_access_required"
    owner, owner_csrf = await login(env, OWNER_TG)
    r = await call(env, "POST", path, cookie=owner, csrf=owner_csrf, json_body={})
    assert r.status_code == 400
    r = await call(env, "POST", f"/api/admin/v2/admins/{env.ids['owner']}/totp/reset", cookie=owner, csrf=owner_csrf,
                   json_body={"reason": "x"})
    assert r.status_code == 403 and r.json()["detail"] == "cannot_modify_self"
    q(env, "UPDATE admin_sessions SET reauth_at = NOW() - INTERVAL '6 minutes'")
    r = await call(env, "POST", path, cookie=owner, csrf=owner_csrf, json_body={"reason": "lost phone"})
    assert r.status_code == 403 and r.json()["detail"] == "reauth_required"
    r = await call(env, "POST", "/api/admin/v2/auth/reauth", cookie=owner, csrf=owner_csrf, json_body={"totp": totp_for(env, OWNER_TG)})
    assert r.status_code == 200
    r = await call(env, "POST", path, cookie=owner, csrf=owner_csrf, json_body={"reason": "lost phone"})
    assert r.status_code == 200 and r.json()["admin"]["totp_enabled"] is False
    assert (await call(env, "GET", "/api/admin/v2/auth/me", cookie=support_token)).status_code == 401
    audit = q(env, "SELECT risk, reason FROM admin_audit_events WHERE action = 'admin_totp_reset'")
    assert audit == [["critical", "lost phone"]]
    # The admin enrolls again from the Mini App.
    r = await _miniapp(env, SUPPORT_TG)
    assert r.status_code == 200 and r.json()["totp_enrollment_required"] is True


# --- No way around the second factor ---------------------------------------------

def _admin_routes(env):
    for route in env.main.app.routes:
        path = getattr(route, "path", "")
        if path.startswith("/api/admin/"):
            for method in sorted(getattr(route, "methods", ()) - {"HEAD", "OPTIONS"}):
                yield method, path.replace("{admin_id}", "1").replace("{job_id}", "job-1").replace("{path:path}", "x")


SETUP_ROUTES = {"/api/admin/v2/auth/me", "/api/admin/v2/auth/totp/enroll", "/api/admin/v2/auth/totp/confirm",
                "/api/admin/v2/auth/reauth", "/api/admin/v2/auth/logout", "/api/admin/v2/auth/logout-all"}
SIGN_IN_ROUTES = {"/api/admin/v2/auth/telegram", "/api/admin/v2/auth/web"}


@pytest.mark.asyncio
async def test_no_admin_route_accepts_a_session_without_totp(ready):
    env = ready
    h, csrf = await _pending_session(env, OWNER_TG)
    routes = list(_admin_routes(env))
    assert len(routes) >= 60
    checked = 0
    for method, path in routes:
        if path in SETUP_ROUTES or path in SIGN_IN_ROUTES:
            continue
        r = await call(env, method, path, headers=h, csrf=csrf, json_body={} if method != "GET" else None)
        assert r.status_code in (401, 403), (method, path, r.status_code, r.text[:200])
        assert r.json().get("detail") == "totp_enrollment_required", (method, path, r.text[:200])
        checked += 1
    assert checked >= 55


@pytest.mark.asyncio
async def test_no_bot_route_acts_without_a_telegram_confirmation(ready):
    env = ready
    _unconfirmed(env, OWNER_TG)
    routes = [(m, p) for m, p in _admin_routes(env) if "/v2/" not in p and p != "/api/admin/me"]
    assert len(routes) > 30
    for method, path in routes:
        r = await call(env, method, path, headers=BOT, json_body={"telegram_id": OWNER_TG})
        assert r.status_code == 403, (method, path, r.status_code, r.text[:200])
        assert r.json().get("detail") == "totp_confirmation_required", (method, path, r.text[:200])
