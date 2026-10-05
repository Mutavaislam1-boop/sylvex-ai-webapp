# Regression tests for the SYLVEX Mini App security audit, Phase 1, second
# requirement: an OAuth-only (Google/Apple) account has password_hash=NULL
# (see oauth_login_or_register() in services/account_identity.py), which
# means change_password()'s normal "verify the current password" check has
# nothing to check against. Before this fix, that meant holding the session
# cookie alone - which a CSRF-forged request, a leaked cookie, or any other
# session hijack already gives an attacker - was sufficient to permanently
# set a first password on someone else's account. change_password() must now
# require a freshly-verified Google/Apple ID token whose subject is one
# already linked to this exact account in account_oauth.
#
# DB layer is a minimal fake cursor/connection (same technique as
# tests/test_prostudio_connection_leak_fix.py and
# tests/test_character_reference_library.py) rather than a real
# Postgres/pglite, since these tests only need to prove change_password()'s
# own branching logic - not real SQL semantics.
import pytest

from services import account_identity as ai
from services import oauth_verify


class FakeCursor:
    def __init__(self, password_hash, oauth_rows):
        self.password_hash = password_hash
        self.oauth_rows = oauth_rows  # set of (account_id, provider, subject)
        self.executed = []
        self._last_result = None

    def execute(self, sql, params=None):
        self.executed.append((sql, params))
        if 'password_hash FROM account_emails' in sql:
            self._last_result = (self.password_hash,) if self.password_hash is not None else (None,)
        elif 'FROM account_oauth' in sql:
            account_id, provider, subject = params
            self._last_result = (1,) if (account_id, provider, subject) in self.oauth_rows else None
        elif 'UPDATE account_emails SET password_hash' in sql:
            self.new_password_hash = params[0]
            self._last_result = None
        else:
            self._last_result = None

    def fetchone(self):
        return self._last_result

    def close(self):
        pass


class FakeConnection:
    def __init__(self, cursor):
        self._cursor = cursor
        self.committed = False
        self.rolled_back = False

    def cursor(self):
        return self._cursor

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True

    def close(self):
        pass


def _patch_db(monkeypatch, password_hash, oauth_rows=frozenset()):
    cursor = FakeCursor(password_hash, oauth_rows)
    connection = FakeConnection(cursor)
    monkeypatch.setattr(ai, 'db_connect', lambda *a, **k: connection)
    return connection, cursor


# ---------------------------------------------------------------------------
# Baseline: an account that already has a password - unaffected by this fix.
# ---------------------------------------------------------------------------

def test_existing_password_holder_still_requires_the_correct_current_password(monkeypatch):
    connection, cursor = _patch_db(monkeypatch, password_hash=ai.hash_password('CorrectHorse123!'))
    with pytest.raises(ai.AccountError) as exc:
        ai.change_password('db', 1, 'WrongPassword!', 'NewPassword123!')
    assert exc.value.args[0] == 'incorrect_current_password'
    assert connection.rolled_back is True


def test_existing_password_holder_succeeds_with_no_reauth_tokens_needed(monkeypatch):
    connection, cursor = _patch_db(monkeypatch, password_hash=ai.hash_password('CorrectHorse123!'))
    ai.change_password('db', 1, 'CorrectHorse123!', 'NewPassword123!')
    assert connection.committed is True
    assert ai.verify_password('NewPassword123!', cursor.new_password_hash)


# ---------------------------------------------------------------------------
# OAuth-only account (password_hash IS NULL): the new requirement.
# ---------------------------------------------------------------------------

def test_oauth_only_account_rejects_setting_a_password_with_no_reauth_token_at_all(monkeypatch):
    connection, cursor = _patch_db(monkeypatch, password_hash=None)
    with pytest.raises(ai.AccountError) as exc:
        ai.change_password('db', 1, None, 'NewPassword123!')
    assert exc.value.args[0] == 'reauth_required'
    assert exc.value.status == 401
    assert connection.rolled_back is True
    assert connection.committed is False


def test_oauth_only_account_rejects_a_google_token_that_fails_verification(monkeypatch):
    connection, cursor = _patch_db(monkeypatch, password_hash=None)

    def _raise(_token):
        raise oauth_verify.OAuthVerifyError('invalid_google_token')
    monkeypatch.setattr(oauth_verify, 'verify_google_id_token', _raise)

    with pytest.raises(ai.AccountError) as exc:
        ai.change_password('db', 1, None, 'NewPassword123!', google_id_token='bad-token')
    assert exc.value.args[0] == 'reauth_failed'
    assert connection.committed is False


def test_oauth_only_account_rejects_a_valid_google_token_for_a_different_account(monkeypatch):
    # Critical case: the attacker's OWN, genuinely valid Google ID token
    # must not be accepted to set a password on SOMEONE ELSE's account -
    # the subject it proves must be one already linked to THIS account_id.
    connection, cursor = _patch_db(monkeypatch, password_hash=None, oauth_rows={(999, 'google', 'attacker-subject')})
    monkeypatch.setattr(oauth_verify, 'verify_google_id_token', lambda token: {'subject': 'attacker-subject'})

    with pytest.raises(ai.AccountError) as exc:
        ai.change_password('db', 1, None, 'NewPassword123!', google_id_token='attackers-own-valid-token')
    assert exc.value.args[0] == 'reauth_failed'
    assert connection.committed is False


def test_oauth_only_account_accepts_a_fresh_google_token_linked_to_this_account(monkeypatch):
    connection, cursor = _patch_db(monkeypatch, password_hash=None, oauth_rows={(1, 'google', 'victim-subject')})
    monkeypatch.setattr(oauth_verify, 'verify_google_id_token', lambda token: {'subject': 'victim-subject'})

    ai.change_password('db', 1, None, 'NewPassword123!', google_id_token='victims-fresh-token')
    assert connection.committed is True
    assert ai.verify_password('NewPassword123!', cursor.new_password_hash)


def test_oauth_only_account_accepts_a_fresh_apple_token_linked_to_this_account(monkeypatch):
    connection, cursor = _patch_db(monkeypatch, password_hash=None, oauth_rows={(1, 'apple', 'victim-subject')})
    monkeypatch.setattr(oauth_verify, 'verify_apple_id_token', lambda token: {'subject': 'victim-subject'})

    ai.change_password('db', 1, None, 'NewPassword123!', apple_id_token='victims-fresh-token')
    assert connection.committed is True
    assert ai.verify_password('NewPassword123!', cursor.new_password_hash)


def test_oauth_only_account_rejects_an_apple_token_that_fails_verification(monkeypatch):
    connection, cursor = _patch_db(monkeypatch, password_hash=None)

    def _raise(_token):
        raise oauth_verify.OAuthVerifyError('invalid_apple_token')
    monkeypatch.setattr(oauth_verify, 'verify_apple_id_token', _raise)

    with pytest.raises(ai.AccountError) as exc:
        ai.change_password('db', 1, None, 'NewPassword123!', apple_id_token='bad-token')
    assert exc.value.args[0] == 'reauth_failed'
    assert connection.committed is False


def test_weak_new_password_is_still_rejected_before_any_reauth_check(monkeypatch):
    # password_strength_error() runs first, regardless of account type -
    # confirm this fix didn't reorder that existing validation.
    connection, cursor = _patch_db(monkeypatch, password_hash=None)
    with pytest.raises(ai.AccountError):
        ai.change_password('db', 1, None, 'short')
    assert connection.committed is False
