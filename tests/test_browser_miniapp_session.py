# The Mini App opened in a plain browser signs in with the SYLVEX web
# session. The public response exposes only account_id; its legacy storage
# key remains private inside the Core.
import main


def summary(active_telegram_id):
    return {"active_telegram_id": active_telegram_id, "email": "a@example.com", "email_verified": True,
            "has_email": True, "has_password": True, "telegram_connected": False, "oauth": {}}


def test_session_payload_exposes_only_the_public_account_id(monkeypatch):
    monkeypatch.setattr(main.account_identity_service, "get_account_summary", lambda url, account_id: summary(9_000_000_000_123))
    monkeypatch.setattr(main, "get_user_state", lambda telegram_id: {"balance": 700, "first_name": "Ann"})
    body = main._web_session_payload(42)
    assert body["authenticated"] is True
    assert body["account_id"] == 42
    assert body["sylvex_user_id"] == 42
    assert body["identity_type"] == "web_account"
    assert "storage_id" not in body
    assert "telegram_id" not in body
    assert body["balance"] == 700


def test_session_payload_never_reveals_a_missing_storage_key(monkeypatch):
    monkeypatch.setattr(main.account_identity_service, "get_account_summary", lambda url, account_id: summary(None))
    monkeypatch.setattr(main, "get_user_state", lambda telegram_id: {})
    body = main._web_session_payload(42)
    assert body["account_id"] == 42
    assert "storage_id" not in body
