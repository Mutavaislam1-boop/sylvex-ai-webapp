# Code-verified email registration (the standalone browser Mini App's
# sign-up): /api/web/auth/register/start emails a 6-digit code and creates no
# account; only /verify with that code (and the registration token the
# starting tab got) creates the SYLVEX account, with its email already
# verified. Resend cooldown, an hourly code budget, code expiry and a
# wrong-guess limit protect the flow.
#
# Real SQL (pglite), like tests/test_rate1_login_lockout.py.
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent / "support"))


def _pglite_available():
    return bool(os.getenv("SYLVEX_TEST_NODE") and os.getenv("SYLVEX_PGLITE_MODULE"))



PASSWORD = "correct horse battery"


@pytest.fixture
def env(monkeypatch):
    if not _pglite_available():
        pytest.skip("Set SYLVEX_TEST_NODE and SYLVEX_PGLITE_MODULE to run real-SQL tests")
    from pglite_adapter import Database
    from services import account_identity as ai
    from services import login_rate_limit as rl

    database = Database()
    monkeypatch.setattr(ai, "db_connect", lambda *a, **k: database.connect())
    monkeypatch.setattr(rl, "db_connection", lambda *a, **k: database.connect())
    monkeypatch.setattr(rl, "_SCHEMA_READY", False)
    monkeypatch.setattr(ai, "_ACCOUNT_TABLES_READY", False)
    sent = []
    monkeypatch.setattr(ai, "send_registration_code_email", lambda to, code: sent.append((to, code)))
    with database.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "CREATE TABLE users(telegram_id BIGINT PRIMARY KEY, first_name TEXT, "
                "username TEXT, balance INTEGER, subscription TEXT, created_at TEXT)"
            )
    ai.ensure_account_tables("pglite://test")
    yield database, ai, sent
    database.close()


def _query(database, sql, params=()):
    with database.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchall() if sql.lstrip().upper().startswith("SELECT") else None


def _age(database, email, seconds, *columns):
    sets = ", ".join(f"{col} = {col} - (%s * INTERVAL '1 second')" for col in columns)
    _query(database, f"UPDATE account_pending_registrations SET {sets} WHERE email = %s", (seconds,) * len(columns) + (email,))


def test_start_sends_a_code_and_creates_no_account(env):
    database, ai, sent = env
    result = ai.start_email_registration("pglite://test", " New@Example.com ", PASSWORD, "Nova")
    assert result["email"] == "new@example.com"
    assert result["expires_in"] == 600 and result["resend_in"] == 60
    assert len(result["registration_token"]) > 20
    assert len(sent) == 1 and sent[0][0] == "new@example.com" and len(sent[0][1]) == 6 and sent[0][1].isdigit()
    assert _query(database, "SELECT COUNT(*) FROM account_emails")[0][0] == 0
    assert _query(database, "SELECT COUNT(*) FROM sylvex_accounts")[0][0] == 0
    assert _query(database, "SELECT COUNT(*) FROM users")[0][0] == 0
    # Only hashes are stored - never the code, token or plain password.
    row = _query(database, "SELECT password_hash, code_hash, token_hash FROM account_pending_registrations")[0]
    assert sent[0][1] not in row and result["registration_token"] not in row and PASSWORD not in row[0]
    # An unverified pending registration cannot sign in.
    with pytest.raises(ai.AccountError) as exc:
        ai.login_email_account("pglite://test", "new@example.com", PASSWORD)
    assert exc.value.code == "invalid_credentials"


def test_verify_creates_a_verified_account_that_can_sign_in(env):
    database, ai, sent = env
    result = ai.start_email_registration("pglite://test", "new@example.com", PASSWORD, "Nova")
    account_id = ai.verify_email_registration("pglite://test", "new@example.com", result["registration_token"], sent[-1][1])
    assert _query(database, "SELECT email, email_verified FROM account_emails WHERE account_id = %s", (account_id,)) == [["new@example.com", True]]
    assert _query(database, "SELECT origin FROM sylvex_accounts WHERE account_id = %s", (account_id,)) == [["website"]]
    assert _query(database, "SELECT first_name FROM users")[0][0] == "Nova"
    assert _query(database, "SELECT COUNT(*) FROM account_pending_registrations")[0][0] == 0
    assert ai.login_email_account("pglite://test", "new@example.com", PASSWORD) == account_id
    # The code is single-use: the pending registration is gone.
    with pytest.raises(ai.AccountError) as exc:
        ai.verify_email_registration("pglite://test", "new@example.com", result["registration_token"], sent[-1][1])
    assert exc.value.code == "registration_expired"


def test_existing_email_is_refused(env):
    database, ai, sent = env
    ai.register_email_account("pglite://test", "taken@example.com", PASSWORD)
    with pytest.raises(ai.AccountError) as exc:
        ai.start_email_registration("pglite://test", "taken@example.com", PASSWORD)
    assert (exc.value.code, exc.value.status) == ("email_already_registered", 409)
    assert sent == []


def test_wrong_code_counts_attempts_then_locks_the_code(env):
    database, ai, sent = env
    result = ai.start_email_registration("pglite://test", "new@example.com", PASSWORD)
    token, code = result["registration_token"], sent[-1][1]
    wrong = "000000" if code != "000000" else "111111"
    lefts = []
    for _ in range(4):
        with pytest.raises(ai.AccountError) as exc:
            ai.verify_email_registration("pglite://test", "new@example.com", token, wrong)
        assert exc.value.code == "invalid_code"
        lefts.append(exc.value.details["attempts_left"])
    assert lefts == [4, 3, 2, 1]
    with pytest.raises(ai.AccountError) as exc:
        ai.verify_email_registration("pglite://test", "new@example.com", token, wrong)
    assert (exc.value.code, exc.value.status) == ("too_many_attempts", 429)
    # Even the right code no longer works for this code; a resend does.
    with pytest.raises(ai.AccountError) as exc:
        ai.verify_email_registration("pglite://test", "new@example.com", token, code)
    assert exc.value.code == "too_many_attempts"
    _age(database, "new@example.com", 61, "last_sent_at")
    ai.resend_registration_code("pglite://test", "new@example.com", token)
    assert ai.verify_email_registration("pglite://test", "new@example.com", token, sent[-1][1])


def test_expired_code_is_reported_and_resend_replaces_it(env):
    database, ai, sent = env
    result = ai.start_email_registration("pglite://test", "new@example.com", PASSWORD)
    token, first = result["registration_token"], sent[-1][1]
    _age(database, "new@example.com", 601, "code_expires_at", "last_sent_at")
    with pytest.raises(ai.AccountError) as exc:
        ai.verify_email_registration("pglite://test", "new@example.com", token, first)
    assert exc.value.code == "code_expired"
    ai.resend_registration_code("pglite://test", "new@example.com", token)
    second = sent[-1][1]
    if first != second:
        with pytest.raises(ai.AccountError):
            ai.verify_email_registration("pglite://test", "new@example.com", token, first)
    assert ai.verify_email_registration("pglite://test", "new@example.com", token, second)


def test_resend_cooldown_and_hourly_budget(env):
    database, ai, sent = env
    result = ai.start_email_registration("pglite://test", "new@example.com", PASSWORD)
    token = result["registration_token"]
    with pytest.raises(ai.AccountError) as exc:
        ai.resend_registration_code("pglite://test", "new@example.com", token)
    assert (exc.value.code, exc.value.status) == ("code_recently_sent", 429)
    assert 55 <= exc.value.details["retry_after"] <= 60
    # A fresh start for the same email shares the cooldown too.
    with pytest.raises(ai.AccountError) as exc:
        ai.start_email_registration("pglite://test", "new@example.com", PASSWORD)
    assert exc.value.code == "code_recently_sent"
    for _ in range(4):
        _age(database, "new@example.com", 61, "last_sent_at")
        ai.resend_registration_code("pglite://test", "new@example.com", token)
    assert len(sent) == 5
    _age(database, "new@example.com", 61, "last_sent_at")
    with pytest.raises(ai.AccountError) as exc:
        ai.resend_registration_code("pglite://test", "new@example.com", token)
    assert exc.value.code == "too_many_codes" and exc.value.details["retry_after"] > 0
    # The hourly window rolls over.
    _age(database, "new@example.com", 3600, "send_window_started_at")
    ai.resend_registration_code("pglite://test", "new@example.com", token)
    assert len(sent) == 6


def test_a_newer_start_invalidates_the_older_token(env):
    database, ai, sent = env
    first = ai.start_email_registration("pglite://test", "new@example.com", "first password")
    _age(database, "new@example.com", 61, "last_sent_at")
    second = ai.start_email_registration("pglite://test", "new@example.com", "second password")
    code = sent[-1][1]
    for token in (first["registration_token"], "forged-token", ""):
        with pytest.raises(ai.AccountError) as exc:
            ai.verify_email_registration("pglite://test", "new@example.com", token, code)
        assert exc.value.code == "registration_expired"
    account_id = ai.verify_email_registration("pglite://test", "new@example.com", second["registration_token"], code)
    assert ai.login_email_account("pglite://test", "new@example.com", "second password") == account_id


def test_validation_errors(env):
    database, ai, sent = env
    for email, password, code in (("not-an-email", PASSWORD, "invalid_email"), ("ok@example.com", "short", "password_too_short")):
        with pytest.raises(ai.AccountError) as exc:
            ai.start_email_registration("pglite://test", email, password)
        assert exc.value.code == code
    assert sent == []


def test_email_taken_while_pending_is_reported_on_verify(env):
    database, ai, sent = env
    result = ai.start_email_registration("pglite://test", "race@example.com", PASSWORD)
    # e.g. a Google sign-in with the same email in between
    ai.oauth_login_or_register("pglite://test", "google", "sub-1", "race@example.com", "Race")
    with pytest.raises(ai.AccountError) as exc:
        ai.verify_email_registration("pglite://test", "race@example.com", result["registration_token"], sent[-1][1])
    assert exc.value.code == "email_already_registered"
    assert _query(database, "SELECT COUNT(*) FROM sylvex_accounts")[0][0] == 1


# --- HTTP routes (called directly, like tests/test_web_auth_config_endpoint.py) ---

class _Request:
    def __init__(self, body):
        self._body = body

    async def json(self):
        return self._body


def _routes(monkeypatch):
    import main
    monkeypatch.setattr(main, "DATABASE_URL", "postgresql://unused")
    return main


def test_routes_are_public_posts():
    from services.security import PUBLIC_POSTS
    assert {"/api/web/auth/register/start", "/api/web/auth/register/resend", "/api/web/auth/register/verify"} <= PUBLIC_POSTS


def test_route_errors_carry_retry_after_and_attempts(monkeypatch):
    import asyncio
    import json
    from services import account_identity as ai
    main = _routes(monkeypatch)

    def cooldown(*_):
        raise ai.RegistrationError("code_recently_sent", 429, retry_after=42)

    monkeypatch.setattr(main.account_identity_service, "resend_registration_code", cooldown)
    response = asyncio.run(main.web_auth_register_resend(_Request({"email": "a@b.co", "registration_token": "t"})))
    assert response.status_code == 429 and response.headers["retry-after"] == "42"
    assert json.loads(response.body) == {"ok": False, "error": "code_recently_sent", "retry_after": 42}

    def wrong(*_):
        raise ai.RegistrationError("invalid_code", 400, attempts_left=3)

    monkeypatch.setattr(main.account_identity_service, "verify_email_registration", wrong)
    response = asyncio.run(main.web_auth_register_verify(_Request({"email": "a@b.co", "registration_token": "t", "code": "1"})))
    assert response.status_code == 400 and json.loads(response.body)["attempts_left"] == 3

    monkeypatch.setattr(main.account_identity_service, "start_email_registration",
                        lambda *a: {"email": "a@b.co", "registration_token": "tok", "expires_in": 600, "resend_in": 60})
    result = asyncio.run(main.web_auth_register_start(_Request({"email": "a@b.co", "password": "x" * 8})))
    assert result == {"ok": True, "email": "a@b.co", "registration_token": "tok", "expires_in": 600, "resend_in": 60}


def test_verify_route_signs_the_new_account_in(monkeypatch):
    import asyncio
    main = _routes(monkeypatch)
    monkeypatch.setattr(main.account_identity_service, "verify_email_registration", lambda *a: 4242)
    monkeypatch.setattr(main, "_web_session_payload", lambda account_id: {"authenticated": True, "account_id": account_id})
    cookies = []

    async def set_cookie(response, account_id):
        cookies.append(account_id)

    monkeypatch.setattr(main, "_set_web_session_cookie", set_cookie)
    response = asyncio.run(main.web_auth_register_verify(_Request({"email": "a@b.co", "registration_token": "t", "code": "123456"})))
    assert response.status_code == 200 and cookies == [4242]
