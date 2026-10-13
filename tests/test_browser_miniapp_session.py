# The Mini App opened in a plain browser (no Telegram) signs in with the
# SYLVEX web session and sends the account's internal storage key as
# telegram_id on API calls - the same key SecurityMiddleware resolves the
# cookie to. /api/web/session/me hands that key over as storage_id.
import main


def summary(active_telegram_id):
    return {"active_telegram_id": active_telegram_id, "email": "a@example.com", "email_verified": True,
            "has_email": True, "has_password": True, "telegram_connected": False, "oauth": {}}


def test_session_payload_carries_the_storage_key(monkeypatch):
    monkeypatch.setattr(main.account_identity_service, "get_account_summary", lambda url, account_id: summary(9_000_000_000_123))
    monkeypatch.setattr(main, "get_user_state", lambda telegram_id: {"balance": 700, "first_name": "Ann"})
    body = main._web_session_payload(42)
    assert body["authenticated"] is True
    assert body["sylvex_user_id"] == 42
    assert body["storage_id"] == 9_000_000_000_123
    assert body["balance"] == 700


def test_session_payload_without_a_storage_key(monkeypatch):
    monkeypatch.setattr(main.account_identity_service, "get_account_summary", lambda url, account_id: summary(None))
    monkeypatch.setattr(main, "get_user_state", lambda telegram_id: {})
    assert main._web_session_payload(42)["storage_id"] is None
