"""GET /api/web/auth/config - the one value the static Website needs to
initialize Google Identity Services, since it can't read Railway env vars
directly. Exercises the route function directly (no TestClient/app
lifecycle - this sandbox's Python 3.11 can't run main.py's own startup
event, which requires 3.12; see validate_runtime()) plus its public-route
registration.
"""
import asyncio

import main
from services.security import PUBLIC_GETS


def test_returns_client_id_and_enabled_flag_when_configured(monkeypatch):
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_ID", "123-abc.apps.googleusercontent.com")
    result = asyncio.run(main.web_auth_config())
    assert result == {
        "google_client_id": "123-abc.apps.googleusercontent.com",
        "google_enabled": True,
    }


def test_reports_disabled_with_empty_client_id_when_not_configured(monkeypatch):
    monkeypatch.delenv("GOOGLE_OAUTH_CLIENT_ID", raising=False)
    result = asyncio.run(main.web_auth_config())
    assert result == {"google_client_id": "", "google_enabled": False}


def test_never_exposes_secrets(monkeypatch):
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_ID", "123-abc.apps.googleusercontent.com")
    monkeypatch.setenv("WEB_SESSION_SECRET", "super-secret-value")
    monkeypatch.setenv("BOT_TOKEN", "another-secret-value")
    result = asyncio.run(main.web_auth_config())
    assert set(result.keys()) == {"google_client_id", "google_enabled"}
    serialized = str(result)
    assert "super-secret-value" not in serialized
    assert "another-secret-value" not in serialized


def test_config_route_is_registered_as_public_get():
    assert "/api/web/auth/config" in PUBLIC_GETS
