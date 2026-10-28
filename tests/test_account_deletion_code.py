# Deleting an account is confirmed by a code emailed to the account's
# address: start emails a 6-digit code, verify returns a confirm token, and
# delete_account refuses without that token. Same resend cooldown, hourly
# budget and wrong-guess limit as registration codes.
#
# Real SQL (pglite), like tests/test_email_registration_code.py.
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent / "support"))

PASSWORD = "correct horse battery"


@pytest.fixture
def env(monkeypatch):
    if not (os.getenv("SYLVEX_TEST_NODE") and os.getenv("SYLVEX_PGLITE_MODULE")):
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
    monkeypatch.setattr(ai, "send_account_deletion_code_email", lambda to, code: sent.append((to, code)))
    with database.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "CREATE TABLE users(telegram_id BIGINT PRIMARY KEY, first_name TEXT, "
                "username TEXT, balance INTEGER, subscription TEXT, created_at TEXT)"
            )
    ai.ensure_account_tables("pglite://test")
    account_id = ai.register_email_account("pglite://test", "Anna@Example.com", PASSWORD)
    yield database, ai, sent, account_id
    database.close()


def _query(database, sql, params=()):
    with database.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchall() if sql.lstrip().upper().startswith("SELECT") else None


def test_the_code_goes_to_the_account_email_and_deletes_only_once_confirmed(env):
    database, ai, sent, account_id = env
    result = ai.start_account_deletion("pglite://test", account_id)
    assert result == {"code_required": True, "email": "a•••@example.com", "expires_in": 600, "resend_in": 60}
    assert sent[0][0] == "anna@example.com" and len(sent[0][1]) == 6
    # Only hashes are stored.
    assert sent[0][1] not in _query(database, "SELECT code_hash FROM account_deletion_codes")[0]
    with pytest.raises(ai.AccountError) as exc:
        ai.delete_account("pglite://test", account_id)
    assert exc.value.code == "deletion_not_confirmed"
    with pytest.raises(ai.AccountError) as exc:
        ai.delete_account("pglite://test", account_id, "made-up-token")
    assert exc.value.code == "deletion_not_confirmed"
    token = ai.verify_account_deletion("pglite://test", account_id, sent[0][1])
    # The code is single-use.
    with pytest.raises(ai.AccountError) as exc:
        ai.verify_account_deletion("pglite://test", account_id, sent[0][1])
    assert exc.value.code == "code_expired"
    ai.delete_account("pglite://test", account_id, token)
    assert _query(database, "SELECT COUNT(*) FROM account_emails")[0][0] == 0
    assert _query(database, "SELECT COUNT(*) FROM sylvex_accounts WHERE account_id = %s", (account_id,))[0][0] == 0
    assert _query(database, "SELECT COUNT(*) FROM account_deletion_codes")[0][0] == 0


def test_wrong_codes_count_down_then_lock(env):
    database, ai, sent, account_id = env
    ai.start_account_deletion("pglite://test", account_id)
    wrong = "000000" if sent[0][1] != "000000" else "111111"
    for left in (4, 3, 2, 1):
        with pytest.raises(ai.AccountError) as exc:
            ai.verify_account_deletion("pglite://test", account_id, wrong)
        assert exc.value.code == "invalid_code" and exc.value.details["attempts_left"] == left
    with pytest.raises(ai.AccountError) as exc:
        ai.verify_account_deletion("pglite://test", account_id, wrong)
    assert exc.value.code == "too_many_attempts"
    with pytest.raises(ai.AccountError) as exc:
        ai.verify_account_deletion("pglite://test", account_id, sent[0][1])
    assert exc.value.code == "too_many_attempts"


def test_resend_cooldown_and_an_expired_confirmation(env):
    database, ai, sent, account_id = env
    ai.start_account_deletion("pglite://test", account_id)
    with pytest.raises(ai.AccountError) as exc:
        ai.start_account_deletion("pglite://test", account_id)
    assert exc.value.code == "code_recently_sent" and exc.value.details["retry_after"] > 0
    _query(database, "UPDATE account_deletion_codes SET last_sent_at = last_sent_at - INTERVAL '61 seconds'")
    ai.start_account_deletion("pglite://test", account_id)
    assert len(sent) == 2
    token = ai.verify_account_deletion("pglite://test", account_id, sent[-1][1])
    _query(database, "UPDATE account_deletion_codes SET confirm_expires_at = NOW() - INTERVAL '1 second'")
    with pytest.raises(ai.AccountError) as exc:
        ai.delete_account("pglite://test", account_id, token)
    assert exc.value.code == "deletion_not_confirmed"


def test_an_account_without_any_email_needs_no_code(env):
    database, ai, sent, account_id = env
    _query(database, "DELETE FROM account_emails WHERE account_id = %s", (account_id,))
    assert ai.start_account_deletion("pglite://test", account_id) == {"code_required": False}
    assert not sent
    ai.delete_account("pglite://test", account_id)
    assert _query(database, "SELECT COUNT(*) FROM sylvex_accounts WHERE account_id = %s", (account_id,))[0][0] == 0
