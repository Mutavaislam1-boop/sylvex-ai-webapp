"""POST /api/web/account/profile - the standalone browser app's profile save.

The account is the one behind the SYLVEX web session cookie, never a
telegram_id or Telegram initData sent by the client; nickname, avatar and
theme land in the same user_profiles row the rest of the app reads. Route
functions are called directly, like tests/test_web_auth_config_endpoint.py.
"""
import asyncio
import json

import main
from services.security import PUBLIC_POSTS

STORAGE_ID = 900000000042


class _Request:
    def __init__(self, body):
        self._body = body

    async def json(self):
        if isinstance(self._body, Exception):
            raise self._body
        return self._body


def _setup(monkeypatch, account_id=7001, stored=None):
    saved = []

    async def session(request):
        return account_id

    monkeypatch.setattr(main, "DATABASE_URL", "postgresql://unused")
    monkeypatch.setattr(main, "_web_session_account_id", session)
    monkeypatch.setattr(main.account_identity_service, "get_account_summary",
                        lambda dsn, acc: {"active_telegram_id": STORAGE_ID} if acc else None)
    monkeypatch.setattr(main, "get_user_profile", lambda tid: dict(stored or {}))

    def save(telegram_id, display_name=None, custom_avatar_url=None, theme_preference=None):
        saved.append({"telegram_id": telegram_id, "display_name": display_name,
                      "custom_avatar_url": custom_avatar_url, "theme_preference": theme_preference})
        return {"display_name": display_name, "custom_avatar_url": custom_avatar_url, "theme_preference": theme_preference or {}}

    monkeypatch.setattr(main, "save_user_profile", save)
    return saved


def _call(body):
    result = asyncio.run(main.web_account_profile(_Request(body)))
    if hasattr(result, "status_code"):
        return result.status_code, json.loads(result.body)
    return 200, result


def test_route_is_a_self_authenticating_web_post():
    assert "/api/web/account/profile" in PUBLIC_POSTS


def test_saves_to_the_session_account_and_ignores_client_telegram_ids(monkeypatch):
    saved = _setup(monkeypatch)
    status, body = _call({
        "display_name": "  Nova  ", "custom_avatar_url": "assets/avatars/a3.png",
        "theme_preference": {"id": "blue", "coverIndex": 1, "evil": "x"},
        "telegram_id": 123456, "initData": "query_id=forged",
    })
    assert status == 200 and body["ok"] is True
    assert saved == [{"telegram_id": STORAGE_ID, "display_name": "Nova", "custom_avatar_url": "assets/avatars/a3.png",
                      "theme_preference": {"id": "blue", "coverIndex": 1}}]
    assert body["profile"]["display_name"] == "Nova"


def test_without_a_session_nothing_is_saved(monkeypatch):
    saved = _setup(monkeypatch, account_id=None)
    status, body = _call({"display_name": "Nova"})
    assert (status, body["error"]) == (401, "not_authenticated")
    assert saved == []


def test_default_avatar_and_theme_only_saves(monkeypatch):
    saved = _setup(monkeypatch)
    assert _call({"custom_avatar_url": ""})[0] == 200
    assert _call({"theme_preference": {"id": "dark"}})[0] == 200
    assert saved[0] == {"telegram_id": STORAGE_ID, "display_name": None, "custom_avatar_url": "", "theme_preference": None}
    assert saved[1]["theme_preference"] == {"id": "dark"} and saved[1]["display_name"] is None


def test_invalid_input_is_refused(monkeypatch):
    saved = _setup(monkeypatch, stored={"custom_avatar_url": "assets/avatars/a1.png"})
    for payload, error in (
        ({"display_name": "   "}, "invalid_display_name"),
        ({"display_name": "x" * 61}, "invalid_display_name"),
        ({"custom_avatar_url": "https://evil.example/a.png"}, "invalid_avatar"),
        ({"custom_avatar_url": 5}, "invalid_avatar"),
        ({"theme_preference": "dark"}, "invalid_theme_preference"),
        ({"telegram_id": 1}, "nothing_to_save"),
        ([], "invalid_payload"),
    ):
        status, body = _call(payload)
        assert (status, body["error"]) == (400, error), payload
    assert _call(ValueError("bad json"))[1]["error"] == "invalid_json"
    assert saved == []


def test_an_existing_non_preset_avatar_may_be_kept(monkeypatch):
    saved = _setup(monkeypatch, stored={"custom_avatar_url": "https://cdn.example/old.png"})
    status, _ = _call({"display_name": "Nova", "custom_avatar_url": "https://cdn.example/old.png"})
    assert status == 200 and saved[0]["custom_avatar_url"] == "https://cdn.example/old.png"
