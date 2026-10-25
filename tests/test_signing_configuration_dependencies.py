"""Document current cutover behavior using dummy keys; production signing is unchanged."""
import hashlib
import hmac
import json
import time
from urllib.parse import urlencode

import pytest

from services import security
from services.paypal_binding import make_binding, read_binding
from services.media_access import sign_media_url, valid_media_url


@pytest.fixture(autouse=True)
def keys(monkeypatch):
    for name in ("BOT_TOKEN", "TELEGRAM_BOT_TOKEN", "MEDIA_SIGNING_SECRET", "WEB_SESSION_SECRET"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("BOT_TOKEN", "dummy-old-bot-token")


def signed(token):
    fields = {"user": json.dumps({"id": 101}), "auth_date": str(int(time.time()))}
    message = "\n".join(f"{key}={fields[key]}" for key in sorted(fields))
    fields["hash"] = hmac.new(hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest(),
                              message.encode(), hashlib.sha256).hexdigest()
    return urlencode(fields)


def test_bot_rotation_changes_media_and_fallback_session_signatures(monkeypatch):
    media_key = security.signing_key()
    web = security.create_web_session_token(101)
    tg = security.create_tg_session_token(101)
    binding = make_binding(101, "P-DUMMYPLAN")
    monkeypatch.setenv("BOT_TOKEN", "dummy-new-bot-token")
    assert security.signing_key() != media_key
    for verify, value in ((security.verify_web_session_token, web),
                          (security.verify_tg_session_token, tg)):
        with pytest.raises(security.SecurityError):
            verify(value)
    with pytest.raises(security.SecurityError):
        read_binding(binding, "P-DUMMYPLAN")


def test_independent_keys_preserve_sessions_and_paypal_binding_on_bot_rotation(monkeypatch):
    monkeypatch.setenv("MEDIA_SIGNING_SECRET", "dummy-independent-media-secret")
    monkeypatch.setenv("WEB_SESSION_SECRET", "dummy-independent-session-secret")
    media_key = security.signing_key()
    web = security.create_web_session_token(101)
    tg = security.create_tg_session_token(101)
    binding = make_binding(101, "P-DUMMYPLAN")
    monkeypatch.setenv("BOT_TOKEN", "dummy-new-bot-token")
    assert security.signing_key() == media_key
    assert security.verify_web_session_token(web) == (101, 0)
    assert security.verify_tg_session_token(tg) == (101, 0)
    assert read_binding(binding, "P-DUMMYPLAN") == 101


def test_introducing_media_secret_invalidates_existing_paypal_binding(monkeypatch):
    binding = make_binding(101, "P-DUMMYPLAN")
    monkeypatch.setenv("MEDIA_SIGNING_SECRET", "dummy-independent-media-secret")
    with pytest.raises(security.SecurityError):
        read_binding(binding, "P-DUMMYPLAN")
    assert read_binding(make_binding(101, "P-DUMMYPLAN"), "P-DUMMYPLAN") == 101


def test_old_bot_alias_keeps_old_init_data_valid_until_removed(monkeypatch):
    old = signed("dummy-old-bot-token")
    monkeypatch.setenv("BOT_TOKEN", "dummy-new-bot-token")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "dummy-old-bot-token")
    assert security.validated_user(old)["id"] == 101
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN")
    with pytest.raises(security.SecurityError):
        security.validated_user(old)
    assert security.validated_user(signed("dummy-new-bot-token"))["id"] == 101


def test_missing_all_signing_configuration_fails_closed(monkeypatch):
    monkeypatch.delenv("BOT_TOKEN")
    for fn in (security.signing_key, security.web_session_secret, security.tg_session_secret):
        with pytest.raises(security.SecurityError) as exc:
            fn()
        assert exc.value.status == 503


def test_existing_media_url_requires_reissue_when_fallback_bot_token_changes(monkeypatch):
    monkeypatch.setenv("WEBAPP_URL", "https://media.example.test")
    monkeypatch.delenv("R2_BUCKET", raising=False)
    value = sign_media_url("/generated/dummy-sx001.png")
    assert valid_media_url(value)
    monkeypatch.setenv("BOT_TOKEN", "dummy-new-bot-token")
    assert not valid_media_url(value)
    assert valid_media_url(sign_media_url("/generated/dummy-sx001.png"))
