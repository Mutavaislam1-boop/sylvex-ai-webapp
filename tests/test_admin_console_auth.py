"""Admin Console Phase 2: admin authentication, RBAC and audit.

Real SQL (PGlite): sessions, the append-only trigger, the one-time
migration and the last-owner lock are database behaviour. No network: the
Telegram signatures are computed locally and no message is ever sent.
"""
import hashlib
import hmac
import json
import os
import sys
import time
from pathlib import Path
from unittest.mock import AsyncMock
from urllib.parse import urlencode

import httpx
import pytest

from services.security import SecurityMiddleware

sys.path.insert(0, str(Path(__file__).parent / "support"))

TOKEN = "test-only-bot-token"
SUPPORT_TOKEN = "test-only-support-bot-token"
SERVICE_TOKEN = "test-only-service-token"
ORIGIN = "https://admin.test"
OWNER_TG = 555
ADMIN_TG = 556
FINANCE_TG = 557
SUPPORT_TG = 558
USER_TG = 7000000001


def _pglite_available():
    return bool(os.getenv("SYLVEX_TEST_NODE") and os.getenv("SYLVEX_PGLITE_MODULE"))


pytestmark = pytest.mark.skipif(not _pglite_available(), reason="Set SYLVEX_TEST_NODE and SYLVEX_PGLITE_MODULE to run real-SQL tests")


class _PlainSQL(str):
    def format(self, **parts):
        return _PlainSQL(str.format(self, **parts))


def init_data(uid, token=TOKEN, age=0):
    fields = {"user": json.dumps({"id": uid, "first_name": "T"}), "auth_date": str(int(time.time()) - age)}
    check = "\n".join(f"{k}={fields[k]}" for k in sorted(fields))
    fields["hash"] = hmac.new(hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest(),
                              check.encode(), hashlib.sha256).hexdigest()
    return urlencode(fields)


@pytest.fixture
def env(monkeypatch):
    from types import SimpleNamespace
    from pglite_adapter import Database
    from services import account_identity as ai

    monkeypatch.setenv("BOT_TOKEN", TOKEN)
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.setenv("ADMIN_SERVICE_TOKEN", SERVICE_TOKEN)
    monkeypatch.setenv("SUPPORT_BOT_TOKEN", SUPPORT_TOKEN)
    monkeypatch.setenv("WEB_SESSION_SECRET", "test-only-web-session-secret")
    import main

    database = Database()
    monkeypatch.setattr(main, "TELEGRAM_AUTH_TOKENS", (TOKEN,))
    monkeypatch.setattr(main, "BOT_TOKEN", TOKEN)
    monkeypatch.setattr(main, "ADMIN_SERVICE_TOKEN", SERVICE_TOKEN)
    monkeypatch.setattr(main, "SUPERADMIN_TELEGRAM_ID", OWNER_TG)
    monkeypatch.setattr(main, "ADMIN_CONSOLE_ORIGINS", (ORIGIN,))
    monkeypatch.setattr(main, "DATABASE_URL", "pglite://test")
    monkeypatch.setattr(main, "db_connect", lambda *a, **k: database.connect())
    monkeypatch.setattr(main, "ADMIN_SCHEMA_READY", False)
    monkeypatch.setattr(ai, "db_connect", lambda *a, **k: database.connect())
    monkeypatch.setattr(ai, "sql", SimpleNamespace(SQL=_PlainSQL, Identifier=lambda n: '"' + n + '"'))
    monkeypatch.setattr(ai, "send_verification_email", lambda *a, **k: None)
    for name in ("_check_rate_limit_lockout", "_record_rate_limit_failure", "_record_rate_limit_success"):
        monkeypatch.setattr(ai, name, lambda *a, **k: {})
    conn = database.connect()
    cur = conn.cursor()
    cur.execute("CREATE TABLE users (telegram_id BIGINT PRIMARY KEY, username TEXT, first_name TEXT, balance INTEGER DEFAULT 0, "
                "subscription TEXT, created_at TEXT)")
    cur.execute("CREATE TABLE user_profiles (telegram_id BIGINT PRIMARY KEY, display_name TEXT)")
    conn.commit()
    main.app.middleware_stack = None
    for mw in main.app.user_middleware:
        if mw.cls is SecurityMiddleware:
            mw.kwargs["quota_check"] = AsyncMock()
    yield SimpleNamespace(main=main, db=database, ai=ai)
    database.close()


def q(env, sql, params=()):
    conn = env.db.connect()
    cur = conn.cursor()
    cur.execute(sql, params)
    rows = cur.fetchall()
    conn.commit()
    return rows


@pytest.fixture
def ready(env):
    """Admin schema in place, owner bootstrapped from SUPERADMIN_TELEGRAM_ID,
    plus an administrator, a finance admin and a support admin."""
    from admin_fixtures import make_admin
    env.main.ensure_admin_tables()
    conn = env.db.connect()
    cur = conn.cursor()
    # The approved role table gives administrators only admins.view; this
    # one was also granted admin management so the escalation rules (not
    # just the missing permission) are what stop it below.
    env.ids = {"admin": make_admin(cur, ADMIN_TG, role="administrator",
                                   grants=["admins.create", "admins.permissions.edit"]),
               "finance": make_admin(cur, FINANCE_TG, role="finance"),
               "support": make_admin(cur, SUPPORT_TG, role="support")}
    cur.execute("SELECT a.id FROM admin_accounts a JOIN sylvex_accounts s ON s.account_id = a.account_id "
                "WHERE s.active_telegram_id = %s", (OWNER_TG,))
    env.ids["owner"] = int(cur.fetchone()[0])
    conn.commit()
    return env


async def call(env, method, path, *, cookie=None, csrf=None, origin=ORIGIN, json_body=None, headers=None):
    h = dict(headers or {})
    if cookie:
        h["Cookie"] = f"__Host-sylvex_admin={cookie}"
    if csrf:
        h["X-Admin-CSRF"] = csrf
    if origin:
        h["Origin"] = origin
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=env.main.app), base_url="https://admin.test") as c:
        return await c.request(method, path, json=json_body, headers=h)


def _cookie(response):
    for header in response.headers.get_list("set-cookie"):
        if header.startswith("__Host-sylvex_admin="):
            return header.split(";", 1)[0].split("=", 1)[1], header
    return None, None


async def login(env, uid):
    r = await call(env, "POST", "/api/admin/v2/auth/telegram", json_body={"initData": init_data(uid)})
    assert r.status_code == 200, r.text
    token, _ = _cookie(r)
    return token, r.json()["csrf_token"]


# --- migration and owner bootstrap ----------------------------------------

def _legacy_admin_users(env, rows):
    q(env, "CREATE TABLE admin_users (id BIGSERIAL PRIMARY KEY, telegram_id BIGINT UNIQUE, account_id BIGINT UNIQUE, "
           "role TEXT NOT NULL DEFAULT 'admin', permissions JSONB NOT NULL DEFAULT '[]'::jsonb, active BOOLEAN NOT NULL DEFAULT TRUE, "
           "granted_by BIGINT, created_at TIMESTAMP DEFAULT NOW(), updated_at TIMESTAMP DEFAULT NOW())")
    for tg, role, perms, active in rows:
        q(env, "INSERT INTO admin_users (telegram_id, role, permissions, active) VALUES (%s, %s, %s::jsonb, %s)",
          (tg, role, json.dumps(perms), active))


@pytest.mark.asyncio
async def test_legacy_admins_migrate_with_exactly_their_permissions(env):
    _legacy_admin_users(env, [(OWNER_TG, "owner", ["all"], True), (ADMIN_TG, "admin", ["view_dashboard", "manage_balance"], True),
                              (FINANCE_TG, "admin", ["view_users"], False)])
    env.main.ensure_admin_tables()
    rows = {r[0]: r[1:] for r in q(env, "SELECT s.active_telegram_id, a.role, a.status FROM admin_accounts a "
                                        "JOIN sylvex_accounts s ON s.account_id = a.account_id")}
    assert rows[OWNER_TG] == ["owner", "active"]
    assert rows[FINANCE_TG] == ["read_only", "revoked"]
    r = await call(env, "POST", "/api/admin/me", headers={"X-Admin-Service-Token": SERVICE_TOKEN}, json_body={"telegram_id": ADMIN_TG})
    assert r.status_code == 200, r.text
    me = r.json()["admin"]
    assert sorted(me["permissions"]) == ["manage_balance", "view_dashboard"]
    assert sorted(me["effective_permissions"]) == ["dashboard.view", "users.balance.adjust"]
    # it really cannot do anything else it never had
    r = await call(env, "POST", "/api/admin/users/search", headers={"X-Admin-Service-Token": SERVICE_TOKEN},
                   json_body={"telegram_id": ADMIN_TG, "query": ""})
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_migration_runs_once(env):
    _legacy_admin_users(env, [(ADMIN_TG, "admin", ["view_users"], True)])
    env.main.ensure_admin_tables()
    q(env, "UPDATE admin_users SET permissions = '[\"all\"]'::jsonb")  # later edits to the frozen table change nothing
    env.main.ADMIN_SCHEMA_READY = False
    env.main.ensure_admin_tables()
    assert q(env, "SELECT a.role FROM admin_accounts a JOIN sylvex_accounts s ON s.account_id = a.account_id "
                  "WHERE s.active_telegram_id = %s", (ADMIN_TG,)) == [["read_only"]]
    assert q(env, "SELECT COUNT(*) FROM admin_schema_migrations WHERE name = 'legacy_admin_users'") == [[1]]


def test_owner_is_bootstrapped_once_and_never_reseeded(ready):
    env = ready
    from services import admin_auth
    conn = env.db.connect()
    cur = conn.cursor()
    # The console never hands out the owner role; a second owner is set up
    # directly in the database.
    cur.execute("UPDATE admin_accounts SET role = 'owner' WHERE id = %s", (env.ids["admin"],))
    second = admin_auth.load_admin(cur, admin_id=env.ids["admin"])
    admin_auth.update_admin(cur, second, env.ids["owner"], role="read_only", reason="test")
    conn.commit()
    env.main.ADMIN_SCHEMA_READY = False
    env.main.ensure_admin_tables()  # SUPERADMIN_TELEGRAM_ID is still configured...
    assert q(env, "SELECT role FROM admin_accounts WHERE id = %s", (env.ids["owner"],)) == [["read_only"]]


@pytest.mark.asyncio
async def test_v1_superadmin_shortcut_is_gone(ready):
    env = ready
    q(env, "UPDATE admin_accounts SET status = 'revoked' WHERE id = %s", (env.ids["admin"],))
    r = await call(env, "POST", "/api/admin/me", headers={"X-Telegram-Init-Data": init_data(ADMIN_TG)}, json_body={})
    assert r.status_code == 403


# --- Telegram login and sessions -------------------------------------------

@pytest.mark.asyncio
async def test_forged_or_stale_init_data_is_rejected(ready):
    env = ready
    for data in (init_data(OWNER_TG, token="not-the-bot-token"), init_data(OWNER_TG, age=10 ** 6),
                 init_data(OWNER_TG).replace("hash=", "hash=0")):
        r = await call(env, "POST", "/api/admin/v2/auth/telegram", json_body={"initData": data})
        assert r.status_code == 401, data
        assert _cookie(r)[0] is None


@pytest.mark.asyncio
async def test_non_admin_telegram_user_gets_no_session(ready):
    env = ready
    r = await call(env, "POST", "/api/admin/v2/auth/telegram", json_body={"initData": init_data(USER_TG)})
    assert r.status_code == 403 and _cookie(r)[0] is None


@pytest.mark.asyncio
async def test_support_bot_signed_init_data_is_accepted(ready):
    r = await call(ready, "POST", "/api/admin/v2/auth/telegram",
                   json_body={"initData": init_data(SUPPORT_TG, token=SUPPORT_TOKEN)})
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_session_cookie_is_strict_and_only_its_hash_is_stored(ready):
    env = ready
    r = await call(env, "POST", "/api/admin/v2/auth/telegram", json_body={"initData": init_data(OWNER_TG)})
    token, header = _cookie(r)
    lower = header.lower()
    assert "httponly" in lower and "secure" in lower and "samesite=strict" in lower and "path=/" in lower
    assert "domain=" not in lower
    assert r.headers["cache-control"] == "no-store"
    stored = q(env, "SELECT token_hash FROM admin_sessions")
    assert stored == [[hashlib.sha256(token.encode()).hexdigest()]]
    assert token not in json.dumps(q(env, "SELECT * FROM admin_sessions"), default=str)


@pytest.mark.asyncio
async def test_me_requires_a_live_session(ready):
    env = ready
    token, csrf = await login(env, ADMIN_TG)
    r = await call(env, "GET", "/api/admin/v2/auth/me", cookie=token)
    assert r.status_code == 200 and r.json()["admin"]["role"] == "administrator"
    assert (await call(env, "GET", "/api/admin/v2/auth/me")).status_code == 401
    assert (await call(env, "GET", "/api/admin/v2/auth/me", cookie="made-up-token")).status_code == 401


@pytest.mark.asyncio
async def test_idle_and_absolute_expiry(ready):
    env = ready
    token, _ = await login(env, ADMIN_TG)
    q(env, "UPDATE admin_sessions SET last_seen_at = NOW() - INTERVAL '31 minutes'")
    assert (await call(env, "GET", "/api/admin/v2/auth/me", cookie=token)).status_code == 401
    token, _ = await login(env, ADMIN_TG)
    q(env, "UPDATE admin_sessions SET expires_at = NOW() - INTERVAL '1 second' WHERE revoked_at IS NULL")
    assert (await call(env, "GET", "/api/admin/v2/auth/me", cookie=token)).status_code == 401


@pytest.mark.asyncio
async def test_logout_and_logout_all_revoke(ready):
    env = ready
    first, csrf1 = await login(env, ADMIN_TG)
    second, csrf2 = await login(env, ADMIN_TG)
    r = await call(env, "POST", "/api/admin/v2/auth/logout", cookie=first, csrf=csrf1)
    assert r.status_code == 200
    assert (await call(env, "GET", "/api/admin/v2/auth/me", cookie=first)).status_code == 401
    assert (await call(env, "GET", "/api/admin/v2/auth/me", cookie=second)).status_code == 200
    third, csrf3 = await login(env, ADMIN_TG)
    r = await call(env, "POST", "/api/admin/v2/auth/logout-all", cookie=third, csrf=csrf3)
    assert r.json()["sessions_revoked"] == 2
    for t in (second, third):
        assert (await call(env, "GET", "/api/admin/v2/auth/me", cookie=t)).status_code == 401


@pytest.mark.asyncio
async def test_suspending_an_admin_ends_their_sessions(ready):
    env = ready
    owner, owner_csrf = await login(env, OWNER_TG)
    target, _ = await login(env, FINANCE_TG)
    r = await call(env, "PATCH", f"/api/admin/v2/admins/{env.ids['finance']}", cookie=owner, csrf=owner_csrf,
                   json_body={"status": "suspended", "reason": "left the team"})
    assert r.status_code == 200, r.text
    assert (await call(env, "GET", "/api/admin/v2/auth/me", cookie=target)).status_code == 401
    r = await call(env, "POST", "/api/admin/v2/auth/telegram", json_body={"initData": init_data(FINANCE_TG)})
    assert r.status_code == 403


# --- CSRF / Origin ------------------------------------------------------------

@pytest.mark.asyncio
async def test_state_changes_need_csrf_and_the_console_origin(ready):
    env = ready
    token, csrf = await login(env, ADMIN_TG)
    assert (await call(env, "POST", "/api/admin/v2/auth/logout", cookie=token)).status_code == 403
    assert (await call(env, "POST", "/api/admin/v2/auth/logout", cookie=token, csrf="wrong")).status_code == 403
    r = await call(env, "POST", "/api/admin/v2/auth/logout", cookie=token, csrf=csrf, origin="https://evil.example")
    assert r.status_code == 403 and r.json()["detail"] == "origin_not_allowed"
    assert (await call(env, "GET", "/api/admin/v2/auth/me", cookie=token)).status_code == 200


# --- Critical actions: reauth -----------------------------------------------

@pytest.mark.asyncio
async def test_critical_action_requires_fresh_reauth(ready):
    env = ready
    token, csrf = await login(env, OWNER_TG)
    q(env, "UPDATE admin_sessions SET reauth_at = NOW() - INTERVAL '6 minutes'")
    body = {"status": "suspended", "reason": "test"}
    r = await call(env, "PATCH", f"/api/admin/v2/admins/{env.ids['support']}", cookie=token, csrf=csrf, json_body=body)
    assert r.status_code == 403 and r.json()["detail"] == "reauth_required"
    r = await call(env, "POST", "/api/admin/v2/auth/reauth", cookie=token, csrf=csrf,
                   json_body={"initData": init_data(ADMIN_TG)})  # someone else's Telegram
    assert r.status_code == 401
    r = await call(env, "POST", "/api/admin/v2/auth/reauth", cookie=token, csrf=csrf,
                   json_body={"initData": init_data(OWNER_TG)})
    assert r.status_code == 200
    r = await call(env, "PATCH", f"/api/admin/v2/admins/{env.ids['support']}", cookie=token, csrf=csrf, json_body=body)
    assert r.status_code == 200, r.text


@pytest.mark.asyncio
async def test_critical_admin_change_requires_a_reason(ready):
    env = ready
    token, csrf = await login(env, OWNER_TG)
    r = await call(env, "PATCH", f"/api/admin/v2/admins/{env.ids['support']}", cookie=token, csrf=csrf,
                   json_body={"status": "suspended"})
    assert r.status_code == 400 and r.json()["detail"] == "reason_required"


# --- privilege escalation ----------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.parametrize("who,target,body,code", [
    # Only the owner assigns and changes admin roles, even below their own.
    ("admin", "support", {"role": "analyst"}, "owner_access_required"),
    ("admin", "support", {"role": "owner"}, "owner_access_required"),
    ("admin", "support", {"grants": ["pricing.edit"]}, "owner_access_required"),
    ("admin", "owner", {"status": "suspended"}, "owner_access_required"),
    ("admin", "admin", {"grants": ["pricing.edit"]}, "cannot_modify_self"),
])
async def test_no_privilege_escalation(ready, who, target, body, code):
    env = ready
    token, csrf = await login(env, {"admin": ADMIN_TG}[who])
    r = await call(env, "PATCH", f"/api/admin/v2/admins/{env.ids[target]}", cookie=token, csrf=csrf,
                   json_body=dict(body, reason="test"))
    assert r.status_code == 403 and r.json()["detail"] == code, r.text


@pytest.mark.asyncio
async def test_the_owner_role_is_never_handed_out_through_the_console(ready):
    env = ready
    token, csrf = await login(env, OWNER_TG)
    r = await call(env, "PATCH", f"/api/admin/v2/admins/{env.ids['admin']}", cookie=token, csrf=csrf,
                   json_body={"role": "owner", "reason": "co-owner"})
    assert r.status_code == 403 and r.json()["detail"] == "owner_role_not_assignable", r.text


@pytest.mark.asyncio
async def test_admin_without_admins_permission_cannot_manage_admins(ready):
    env = ready
    token, csrf = await login(env, FINANCE_TG)
    r = await call(env, "PATCH", f"/api/admin/v2/admins/{env.ids['support']}", cookie=token, csrf=csrf,
                   json_body={"status": "suspended", "reason": "x"})
    assert r.status_code == 403 and r.json()["detail"] == "admin_permission_denied"
    assert (await call(env, "GET", "/api/admin/v2/admins", cookie=token)).status_code == 403


@pytest.mark.asyncio
async def test_owner_creates_admin_by_sylvex_id_with_exact_rights(ready):
    env = ready
    q(env, "INSERT INTO users (telegram_id, first_name) VALUES (%s, 'New')", (USER_TG,))
    account = q(env, "SELECT account_id FROM sylvex_accounts WHERE active_telegram_id = %s", (USER_TG,))[0][0]
    token, csrf = await login(env, OWNER_TG)
    r = await call(env, "POST", "/api/admin/v2/admins", cookie=token, csrf=csrf,
                   json_body={"sylvex_user_id": str(account), "role": "support", "denies": ["messages.send"], "reason": "hire"})
    assert r.status_code == 200, r.text
    created = r.json()["admin"]
    assert created["role"] == "support" and "messages.send" not in created["permissions"]
    r = await call(env, "POST", "/api/admin/v2/admins", cookie=token, csrf=csrf,
                   json_body={"sylvex_user_id": str(account), "role": "support", "reason": "again"})
    assert r.status_code == 409


# --- last owner ---------------------------------------------------------------

@pytest.mark.asyncio
async def test_last_owner_cannot_be_removed(ready):
    env = ready
    # A second owner only comes from outside the console (bootstrap / data).
    q(env, "UPDATE admin_accounts SET role = 'owner' WHERE id = %s", (env.ids["admin"],))
    second_token, second_csrf = await login(env, ADMIN_TG)
    r = await call(env, "PATCH", f"/api/admin/v2/admins/{env.ids['owner']}", cookie=second_token, csrf=second_csrf,
                   json_body={"role": "administrator", "reason": "hand over"})
    assert r.status_code == 200, r.text
    # the second owner is now the only one: nobody can demote or suspend them
    from services import admin_auth
    conn = env.db.connect()
    cur = conn.cursor()
    remaining = admin_auth.load_admin(cur, admin_id=env.ids["admin"])
    for change in ({"role": "administrator"}, {"status": "suspended"}, {"status": "revoked"}):
        with pytest.raises(admin_auth.AdminAuthError) as exc:
            # an owner acting through code, not the HTTP self-edit path
            admin_auth.update_admin(cur, dict(remaining, admin_id=-1), env.ids["admin"], reason="x", **change)
        assert exc.value.code == "last_owner_protected"
    conn.rollback()


# --- audit ----------------------------------------------------------------------

@pytest.mark.asyncio
async def test_audit_log_is_append_only(ready):
    env = ready
    await login(env, OWNER_TG)
    for statement in ("UPDATE admin_audit_events SET action = 'x'", "DELETE FROM admin_audit_events",
                      "TRUNCATE admin_audit_events"):
        conn = env.db.connect()
        with pytest.raises(RuntimeError, match="append-only"):
            conn.cursor().execute(statement)
        conn.rollback()
    assert q(env, "SELECT COUNT(*) FROM admin_audit_events WHERE action = 'admin_login'")[0][0] == 1


@pytest.mark.asyncio
async def test_admin_changes_are_audited_with_before_and_after(ready):
    env = ready
    token, csrf = await login(env, OWNER_TG)
    await call(env, "PATCH", f"/api/admin/v2/admins/{env.ids['support']}", cookie=token, csrf=csrf,
               json_body={"grants": ["payments.view"], "reason": "needs refunds view"})
    r = await call(env, "GET", "/api/admin/v2/audit?action=admin_updated", cookie=token)
    item, = r.json()["items"]
    assert item["risk"] == "critical" and item["reason"] == "needs refunds view" and item["channel"] == "miniapp"
    assert "payments.view" not in item["before"]["grants"] and "payments.view" in item["after"]["grants"]


# --- TOTP and web login ---------------------------------------------------------

def _totp(secret, offset=0):
    from services.admin_auth import totp_code
    return totp_code(secret, time.time(), offset)[0]


async def _enable_totp(env, uid):
    token, csrf = await login(env, uid)
    r = await call(env, "POST", "/api/admin/v2/auth/totp/enroll", cookie=token, csrf=csrf)
    assert r.status_code == 200, r.text
    secret = r.json()["secret"]
    assert (await call(env, "POST", "/api/admin/v2/auth/totp/confirm", cookie=token, csrf=csrf,
                       json_body={"code": "000000"})).status_code in (401, 200)
    r = await call(env, "POST", "/api/admin/v2/auth/totp/confirm", cookie=token, csrf=csrf, json_body={"code": _totp(secret)})
    assert r.status_code == 200, r.text
    q(env, "UPDATE admin_accounts SET totp_last_step = NULL")  # let the next test code be used right away
    return secret


def _add_password(env, uid, email="admin@test.com"):
    account = q(env, "SELECT account_id FROM sylvex_accounts WHERE active_telegram_id = %s", (uid,))[0][0]
    env.ai.set_email_for_account("pglite://test", account, email, "correcthorsebattery")


@pytest.mark.asyncio
async def test_web_login_needs_password_and_totp(ready):
    env = ready
    _add_password(env, ADMIN_TG)
    r = await call(env, "POST", "/api/admin/v2/auth/web", json_body={"email": "admin@test.com", "password": "correcthorsebattery", "totp": "123456"})
    assert r.status_code == 403 and r.json()["error"] == "totp_enrollment_required"
    secret = await _enable_totp(env, ADMIN_TG)
    r = await call(env, "POST", "/api/admin/v2/auth/web", json_body={"email": "admin@test.com", "password": "wrong-password", "totp": _totp(secret)})
    assert r.status_code == 401 and _cookie(r)[0] is None
    code = _totp(secret)
    r = await call(env, "POST", "/api/admin/v2/auth/web", json_body={"email": "admin@test.com", "password": "correcthorsebattery", "totp": code})
    assert r.status_code == 200, r.text
    assert r.json()["session"]["channel"] == "web" and _cookie(r)[0]
    # the same code cannot be replayed
    r = await call(env, "POST", "/api/admin/v2/auth/web", json_body={"email": "admin@test.com", "password": "correcthorsebattery", "totp": code})
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_totp_failures_lock_out(ready):
    env = ready
    _add_password(env, ADMIN_TG)
    secret = await _enable_totp(env, ADMIN_TG)
    for _ in range(5):
        r = await call(env, "POST", "/api/admin/v2/auth/web", json_body={"email": "admin@test.com", "password": "correcthorsebattery", "totp": "000000"})
        assert r.status_code == 401
    r = await call(env, "POST", "/api/admin/v2/auth/web", json_body={"email": "admin@test.com", "password": "correcthorsebattery", "totp": _totp(secret)})
    assert r.status_code == 429 and r.json()["error"] == "totp_locked"


@pytest.mark.asyncio
async def test_totp_cannot_be_enrolled_from_a_web_session_or_without_reauth(ready):
    env = ready
    _add_password(env, ADMIN_TG)
    secret = await _enable_totp(env, ADMIN_TG)
    r = await call(env, "POST", "/api/admin/v2/auth/web", json_body={"email": "admin@test.com", "password": "correcthorsebattery", "totp": _totp(secret)})
    web_token, web_csrf = _cookie(r)[0], r.json()["csrf_token"]
    r = await call(env, "POST", "/api/admin/v2/auth/totp/enroll", cookie=web_token, csrf=web_csrf)
    assert r.status_code == 403 and r.json()["detail"] == "totp_enroll_requires_miniapp"
    token, csrf = await login(env, ADMIN_TG)
    q(env, "UPDATE admin_sessions SET reauth_at = NOW() - INTERVAL '10 minutes'")
    r = await call(env, "POST", "/api/admin/v2/auth/totp/enroll", cookie=token, csrf=csrf)
    assert r.status_code == 403 and r.json()["detail"] == "reauth_required"


def test_totp_secret_is_stored_encrypted(ready):
    env = ready
    from services import admin_auth
    conn = env.db.connect()
    cur = conn.cursor()
    admin = admin_auth.load_admin(cur, admin_id=env.ids["admin"])
    secret, _ = admin_auth.begin_totp_enrollment(cur, admin)
    conn.commit()
    stored = q(env, "SELECT totp_pending_enc FROM admin_accounts WHERE id = %s", (env.ids["admin"],))[0][0]
    assert secret not in stored and stored.startswith("gAAAA")


# --- v1 / bot channel ------------------------------------------------------------

@pytest.mark.asyncio
async def test_v1_admins_set_obeys_the_same_rules(ready):
    env = ready
    headers = {"X-Admin-Service-Token": SERVICE_TOKEN}
    q(env, "INSERT INTO users (telegram_id, first_name) VALUES (%s, 'New')", (USER_TG,))
    # a non-owner admin cannot use a Critical action over the bot channel
    r = await call(env, "POST", "/api/admin/admins/set", headers=headers,
                   json_body={"telegram_id": ADMIN_TG, "user_id": USER_TG, "permissions": ["view_users"]})
    assert r.status_code == 403 and r.json()["detail"] == "console_required_for_critical_action"
    r = await call(env, "POST", "/api/admin/admins/set", headers=headers,
                   json_body={"telegram_id": OWNER_TG, "user_id": USER_TG, "permissions": ["view_users", "view_errors"]})
    assert r.status_code == 200, r.text
    r = await call(env, "POST", "/api/admin/admins/list", headers=headers, json_body={"telegram_id": OWNER_TG})
    row = next(i for i in r.json()["items"] if i["telegram_id"] == USER_TG)
    assert sorted(row["permissions"]) == ["view_errors", "view_users"] and row["active"] is True
    # the owner cannot be targeted through it either (last owner)
    r = await call(env, "POST", "/api/admin/admins/set", headers=headers,
                   json_body={"telegram_id": OWNER_TG, "user_id": OWNER_TG, "active": False})
    assert r.status_code == 403 and r.json()["detail"] == "cannot_modify_self"


@pytest.mark.asyncio
async def test_bot_channel_allows_high_but_audits_the_channel(ready):
    env = ready
    q(env, "INSERT INTO users (telegram_id, first_name, balance) VALUES (%s, 'U', 10)", (USER_TG,))
    r = await call(env, "POST", "/api/admin/users/balance", headers={"X-Admin-Service-Token": SERVICE_TOKEN},
                   json_body={"telegram_id": FINANCE_TG, "user_id": USER_TG, "delta": 5, "reason": "goodwill"})
    assert r.status_code == 200, r.text
    row = q(env, "SELECT channel, risk, action FROM admin_audit_events WHERE action = 'balance_changed'")
    assert row == [["bot", "high", "balance_changed"]]


# --- Admin Console UI: v1 data routes with the console session ----------------

@pytest.mark.asyncio
async def test_console_session_drives_v1_routes_with_rbac_and_audit(ready):
    env = ready
    q(env, "INSERT INTO users (telegram_id, first_name, balance) VALUES (%s, 'U', 10)", (USER_TG,))
    token, csrf = await login(env, FINANCE_TG)
    body = {"user_id": USER_TG, "delta": 7, "reason": "console goodwill", "source": "admin_console"}
    r = await call(env, "POST", "/api/admin/users/balance", cookie=token, csrf=csrf, json_body=body)
    assert r.status_code == 200, r.text
    assert q(env, "SELECT balance FROM users WHERE telegram_id = %s", (USER_TG,)) == [[17]]
    channel = q(env, "SELECT channel FROM admin_sessions WHERE revoked_at IS NULL")[0][0]
    rows = q(env, "SELECT channel, risk, reason FROM admin_audit_events WHERE action = 'balance_changed'")
    assert rows == [[channel, "high", "console goodwill"]]
    # Support has no balance permission: the session's role decides.
    token, csrf = await login(env, SUPPORT_TG)
    r = await call(env, "POST", "/api/admin/users/balance", cookie=token, csrf=csrf, json_body=body)
    assert r.status_code == 403 and r.json()["detail"] == "admin_permission_denied"


@pytest.mark.asyncio
async def test_console_session_on_v1_needs_csrf_and_origin(ready):
    env = ready
    token, csrf = await login(env, OWNER_TG)
    assert (await call(env, "POST", "/api/admin/dashboard", cookie=token, json_body={})).json()["detail"] == "csrf_token_invalid"
    r = await call(env, "POST", "/api/admin/dashboard", cookie=token, csrf=csrf, origin="https://evil.example", json_body={})
    assert r.status_code == 403 and r.json()["detail"] == "origin_not_allowed"
    r = await call(env, "POST", "/api/admin/dashboard", cookie="made-up", csrf=csrf, json_body={})
    assert r.status_code == 401
    # Nothing at all: still refused (no Telegram, no service token, no session).
    assert (await call(env, "POST", "/api/admin/dashboard", json_body={})).status_code in (401, 403)


@pytest.mark.asyncio
async def test_console_session_needs_reauth_for_critical_v1_actions(ready):
    env = ready
    token, csrf = await login(env, OWNER_TG)
    q(env, "UPDATE admin_sessions SET reauth_at = NOW() - INTERVAL '6 minutes'")
    r = await call(env, "POST", "/api/admin/messages/broadcast", cookie=token, csrf=csrf,
                   json_body={"message": "hi", "all": True})
    assert r.status_code == 403 and r.json()["detail"] == "reauth_required"


@pytest.mark.asyncio
async def test_mini_app_login_returns_a_header_token_only_in_miniapp_mode(ready):
    env = ready
    r = await call(env, "POST", "/api/admin/v2/auth/telegram", json_body={"initData": init_data(OWNER_TG)})
    assert "session_token" not in r.json()
    r = await call(env, "POST", "/api/admin/v2/auth/telegram", json_body={"initData": init_data(OWNER_TG), "mode": "miniapp"})
    token, csrf = r.json()["session_token"], r.json()["csrf_token"]
    assert token
    h = {"X-Admin-Session": token}
    assert (await call(env, "GET", "/api/admin/v2/auth/me", headers=h)).status_code == 200
    r = await call(env, "POST", "/api/admin/me", csrf=csrf, headers=h, json_body={})
    assert r.status_code == 200, r.text
    assert r.json()["admin"]["role"] == "owner"


@pytest.mark.asyncio
async def test_console_served_from_the_api_host_is_an_allowed_origin(ready, monkeypatch):
    env = ready
    monkeypatch.setattr(env.main, "ADMIN_CONSOLE_ORIGINS", ())
    token, csrf = await login(env, OWNER_TG)
    r = await call(env, "POST", "/api/admin/me", cookie=token, csrf=csrf, origin="https://admin.test", json_body={})
    assert r.status_code == 200, r.text
    r = await call(env, "POST", "/api/admin/me", cookie=token, csrf=csrf, origin="https://other.test", json_body={})
    assert r.status_code == 403


# --- Browser bootstrap owner (ADMIN_OWNER_EMAIL) ---------------------------------

DEV_EMAIL = "developer@gmail.com"
DEV_PASSWORD = "correcthorsebattery"


def _web_account(env, email, verified=True, password=DEV_PASSWORD):
    account_id = env.ai.register_email_account("pglite://test", email, password)
    if verified:
        q(env, "UPDATE account_emails SET email_verified = TRUE WHERE account_id = %s", (account_id,))
    return account_id


async def _web(env, **body):
    return await call(env, "POST", "/api/admin/v2/auth/web", json_body=body)


@pytest.mark.asyncio
async def test_bootstrap_owner_sets_up_2fa_in_the_browser_then_needs_the_code(ready, monkeypatch):
    env = ready
    monkeypatch.setenv("ADMIN_OWNER_EMAIL", DEV_EMAIL)
    account_id = _web_account(env, DEV_EMAIL)
    # Step 1: email + password -> QR (no session yet), owner record created once.
    r = await _web(env, email=DEV_EMAIL, password=DEV_PASSWORD)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["totp_setup_required"] and data["otpauth_uri"].startswith("otpauth://totp/") and _cookie(r)[0] is None
    assert q(env, "SELECT role, status FROM admin_accounts WHERE account_id = %s", (account_id,)) == [["owner", "active"]]
    assert q(env, "SELECT COUNT(*) FROM admin_audit_events WHERE action = 'owner_bootstrapped_from_email'") == [[1]]
    # Step 2: a wrong code is refused, the right one turns 2FA on and signs in.
    r = await _web(env, email=DEV_EMAIL, password=DEV_PASSWORD, setup_code="000000")
    assert r.status_code == 401 and _cookie(r)[0] is None
    r = await _web(env, email=DEV_EMAIL, password=DEV_PASSWORD, setup_code=_totp(data["secret"]))
    assert r.status_code == 200, r.text
    assert r.json()["admin"]["role"] == "owner" and r.json()["session"]["channel"] == "web" and _cookie(r)[0]
    # From now on: no QR, the 6-digit code is required.
    q(env, "UPDATE admin_accounts SET totp_last_step = NULL")
    r = await _web(env, email=DEV_EMAIL, password=DEV_PASSWORD)
    assert r.status_code == 401 and r.json()["error"] == "totp_required" and "secret" not in r.text
    r = await _web(env, email=DEV_EMAIL, password=DEV_PASSWORD, setup_code=_totp(data["secret"]))
    assert r.status_code == 401
    r = await _web(env, email=DEV_EMAIL, password=DEV_PASSWORD, totp=_totp(data["secret"]))
    assert r.status_code == 200, r.text
    # Signing in again never re-creates or re-promotes anything.
    assert q(env, "SELECT COUNT(*) FROM admin_audit_events WHERE action = 'owner_bootstrapped_from_email'") == [[1]]


@pytest.mark.asyncio
async def test_other_users_are_rejected_before_any_qr(ready, monkeypatch):
    env = ready
    monkeypatch.setenv("ADMIN_OWNER_EMAIL", DEV_EMAIL)
    _web_account(env, "someone@gmail.com")
    r = await _web(env, email="someone@gmail.com", password=DEV_PASSWORD)
    assert r.status_code == 403 and r.json()["error"] == "admin_access_denied" and "secret" not in r.text
    # An existing admin without 2FA gets no browser QR either (Mini App only, as before).
    _add_password(env, ADMIN_TG)
    r = await _web(env, email="admin@test.com", password="correcthorsebattery")
    assert r.status_code == 403 and r.json()["error"] == "totp_enrollment_required" and "secret" not in r.text
    assert q(env, "SELECT COUNT(*) FROM admin_accounts WHERE role = 'owner'") == [[1]]  # only the Telegram owner


@pytest.mark.asyncio
async def test_owner_email_must_be_verified_and_configured(ready, monkeypatch):
    env = ready
    account_id = _web_account(env, DEV_EMAIL, verified=False)
    monkeypatch.setenv("ADMIN_OWNER_EMAIL", DEV_EMAIL)
    r = await _web(env, email=DEV_EMAIL, password=DEV_PASSWORD)
    assert r.status_code == 403 and "secret" not in r.text
    q(env, "UPDATE account_emails SET email_verified = TRUE WHERE account_id = %s", (account_id,))
    monkeypatch.setenv("ADMIN_OWNER_EMAIL", "")
    r = await _web(env, email=DEV_EMAIL, password=DEV_PASSWORD)
    assert r.status_code == 403
    monkeypatch.setenv("ADMIN_OWNER_EMAIL", "other.dev@gmail.com")
    r = await _web(env, email=DEV_EMAIL, password=DEV_PASSWORD)
    assert r.status_code == 403
    r = await _web(env, email=DEV_EMAIL, password="wrong-password-123")
    assert r.status_code == 401
    assert q(env, "SELECT COUNT(*) FROM admin_accounts WHERE account_id = %s", (account_id,)) == [[0]]


@pytest.mark.asyncio
async def test_bootstrap_never_revives_a_suspended_owner_and_setup_codes_lock_out(ready, monkeypatch):
    env = ready
    monkeypatch.setenv("ADMIN_OWNER_EMAIL", DEV_EMAIL)
    account_id = _web_account(env, DEV_EMAIL)
    r = await _web(env, email=DEV_EMAIL, password=DEV_PASSWORD)
    secret = r.json()["secret"]
    for _ in range(5):
        assert (await _web(env, email=DEV_EMAIL, password=DEV_PASSWORD, setup_code="000000")).status_code == 401
    r = await _web(env, email=DEV_EMAIL, password=DEV_PASSWORD, setup_code=_totp(secret))
    assert r.status_code == 429 and r.json()["error"] == "totp_locked"
    q(env, "UPDATE admin_accounts SET status = 'suspended' WHERE account_id = %s", (account_id,))
    r = await _web(env, email=DEV_EMAIL, password=DEV_PASSWORD)
    assert r.status_code == 403 and r.json()["error"] == "admin_access_denied"
    assert q(env, "SELECT status FROM admin_accounts WHERE account_id = %s", (account_id,)) == [["suspended"]]


@pytest.mark.asyncio
async def test_owner_adds_an_admin_by_verified_email(ready):
    env = ready
    token, csrf = await login(env, OWNER_TG)
    verified = _web_account(env, "helper@gmail.com")
    _web_account(env, "unverified@gmail.com", verified=False)
    body = {"role": "support", "reason": "new support teammate"}
    r = await call(env, "POST", "/api/admin/v2/admins", cookie=token, csrf=csrf, json_body={**body, "email": "unverified@gmail.com"})
    assert r.status_code == 409 and r.json()["detail"] == "email_not_verified"
    r = await call(env, "POST", "/api/admin/v2/admins", cookie=token, csrf=csrf, json_body={**body, "email": "nobody@gmail.com"})
    assert r.status_code == 404
    r = await call(env, "POST", "/api/admin/v2/admins", cookie=token, csrf=csrf, json_body={**body, "email": " Helper@Gmail.com "})
    assert r.status_code == 200, r.text
    assert r.json()["admin"]["sylvex_user_id"] == str(verified) and r.json()["admin"]["role"] == "support"
