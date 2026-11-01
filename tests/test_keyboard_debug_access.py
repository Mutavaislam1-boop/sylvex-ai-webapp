"""POST /api/public/keyboard-debug/access - may this visitor open the Keyboard
Debug panel (webapp/js/keyboard-debug.js)? Calls the route function directly
(no TestClient/app lifecycle, see test_web_auth_config_endpoint.py)."""
import asyncio

import main
from services.security import PUBLIC_POSTS


class _Req:
    def __init__(self, body=None, cookies=None):
        self._body = body or {}
        self.cookies = cookies or {}

    async def json(self):
        return self._body


def _call(body=None, cookies=None):
    return asyncio.run(main.keyboard_debug_access(_Req(body, cookies)))


class _Cursor:
    def close(self):
        pass


class _Conn:
    def cursor(self):
        return _Cursor()

    def close(self):
        pass


def _production(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setattr(main, "DATABASE_URL", "postgres://test")
    monkeypatch.setattr(main, "ensure_admin_tables", lambda: None)
    monkeypatch.setattr(main, "db_connect", lambda url: _Conn())


def test_allowed_outside_production(monkeypatch):
    monkeypatch.setenv("APP_ENV", "development")
    assert _call() == {"ok": True, "allowed": True}


def test_production_without_credentials_is_refused(monkeypatch):
    _production(monkeypatch)
    monkeypatch.setattr(main, "_telegram_id_from_init_data", lambda s: 0)

    async def no_session(request):
        return None
    monkeypatch.setattr(main, "_web_session_account_id", no_session)
    assert _call() == {"ok": True, "allowed": False}
    assert _call({"initData": "forged"}) == {"ok": True, "allowed": False}


def test_production_telegram_admin_only(monkeypatch):
    _production(monkeypatch)
    monkeypatch.setattr(main, "_telegram_id_from_init_data", lambda s: 42 if s == "signed" else 0)
    admins = {42: {"status": "active"}}
    monkeypatch.setattr(main.admin_auth, "active_admin_for_telegram", lambda cur, tid: admins.get(tid))
    assert _call({"initData": "signed"}) == {"ok": True, "allowed": True}
    admins.clear()
    assert _call({"initData": "signed"}) == {"ok": True, "allowed": False}


def test_production_web_session_admin_only(monkeypatch):
    _production(monkeypatch)
    monkeypatch.setattr(main, "_telegram_id_from_init_data", lambda s: 0)

    async def session(request):
        return 7
    monkeypatch.setattr(main, "_web_session_account_id", session)
    status = {"value": "active"}
    monkeypatch.setattr(main.admin_auth, "load_admin", lambda cur, account_id=None: {"status": status["value"]} if account_id == 7 else None)
    assert _call() == {"ok": True, "allowed": True}
    status["value"] = "suspended"
    assert _call() == {"ok": True, "allowed": False}


def test_database_failure_refuses(monkeypatch):
    _production(monkeypatch)
    monkeypatch.setattr(main, "_telegram_id_from_init_data", lambda s: 42)

    def boom(url):
        raise RuntimeError("db down")
    monkeypatch.setattr(main, "db_connect", boom)
    assert _call({"initData": "signed"}) == {"ok": True, "allowed": False}


def test_answer_is_only_yes_or_no(monkeypatch):
    monkeypatch.setenv("APP_ENV", "development")
    assert set(_call().keys()) == {"ok", "allowed"}


def test_route_is_registered_as_public_post():
    assert "/api/public/keyboard-debug/access" in PUBLIC_POSTS
