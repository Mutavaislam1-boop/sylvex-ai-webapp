# Regression tests for the security audit's RATE-1 finding: /api/web/auth/login
# was a PUBLIC_POST (exempt from the per-user quota middleware), and
# login_email_account() had no per-account failed-attempt counter or lockout
# at all - the only throttle anywhere on it was the generic, process-local,
# per-IP request-rate guard in services/security.py, which does nothing to
# slow a password-guessing attack against one specific account.
#
# Fix: services/login_rate_limit.py tracks failures in a real Postgres table
# (shared across every worker/replica, unlike a process-local dict), keyed by
# the normalized identity string the caller supplies - never by whether an
# account actually exists for it, so the lockout itself can never be used to
# probe account existence. login_email_account() checks/records against it,
# and request_password_reset() reuses the same mechanism to throttle request
# volume (its own abuse surface: email-bombing / a timing side channel,
# since sending the real reset email takes measurably longer than the no-op
# "unknown email" path - not brute force, since reset-password's token is a
# cryptographically random 256-bit secrets.token_urlsafe(32) value, already
# infeasible to guess regardless of any rate limit, so reset_password_with_token
# itself is intentionally left untouched here).
#
# These tests run against a real embedded Postgres (pglite), not mocks - the
# same harness tests/test_sylvex_id_allocator.py and
# tests/test_sql4_ready_flag_guards.py already use - since the whole point of
# "shared across workers" is a real, independently-queryable Postgres table,
# not application-level state.
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent / "support"))


def _pglite_available():
    return bool(os.getenv("SYLVEX_TEST_NODE") and os.getenv("SYLVEX_PGLITE_MODULE"))


pytestmark = pytest.mark.skipif(
    not _pglite_available(),
    reason="Set SYLVEX_TEST_NODE and SYLVEX_PGLITE_MODULE to run real-SQL tests",
)


@pytest.fixture
def db(monkeypatch):
    from pglite_adapter import Database
    from services import account_identity as ai
    from services import login_rate_limit as rl

    database = Database()
    monkeypatch.setattr(ai, "db_connect", lambda *a, **k: database.connect())
    monkeypatch.setattr(ai, "_ACCOUNT_TABLES_READY", False)
    # login_rate_limit.py uses db_connection() (a context-manager style
    # helper, not db_connect()'s plain lease) - pglite's own Connection
    # already implements __enter__/__exit__ (commit/rollback), so handing
    # back a fresh one per call is a drop-in substitute.
    monkeypatch.setattr(rl, "db_connection", lambda *a, **k: database.connect())
    monkeypatch.setattr(rl, "_SCHEMA_READY", False)
    # `users` isn't created by this codebase (predates the webapp); it must
    # exist for _new_web_account()'s own INSERT INTO users during registration.
    with database.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "CREATE TABLE users(telegram_id BIGINT PRIMARY KEY, first_name TEXT, "
                "username TEXT, balance INTEGER, subscription TEXT, created_at TEXT)"
            )
    ai.ensure_account_tables("pglite://test")

    yield database, ai, rl
    database.close()


def _raw_row(database, identity):
    with database.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT fail_count, GREATEST(0, EXTRACT(EPOCH FROM (locked_until - NOW()))) "
                "FROM account_rate_limit_attempts WHERE identity = %s",
                (identity,),
            )
            return cur.fetchone()


# ---------------------------------------------------------------------------
# login_rate_limit.py in isolation.
# ---------------------------------------------------------------------------

def test_repeated_failures_lock_after_the_threshold(db):
    database, ai, rl = db
    identity = "login:nobody@test.com"
    outcome = None
    for _ in range(rl.FAILURE_THRESHOLD):
        outcome = rl.record_failure("pglite://test", identity)
    assert outcome["locked"] is True
    assert outcome["retry_after"] > 0
    assert rl.check_lockout("pglite://test", identity)["locked"] is True


def test_fewer_than_threshold_failures_do_not_lock(db):
    database, ai, rl = db
    identity = "login:almost@test.com"
    for _ in range(rl.FAILURE_THRESHOLD - 1):
        outcome = rl.record_failure("pglite://test", identity)
    assert outcome["locked"] is False
    assert rl.check_lockout("pglite://test", identity)["locked"] is False


def test_lockout_backoff_grows_with_each_further_failure(db):
    database, ai, rl = db
    identity = "login:grows@test.com"
    first = None
    for _ in range(rl.FAILURE_THRESHOLD):
        first = rl.record_failure("pglite://test", identity)
    second = rl.record_failure("pglite://test", identity)
    assert second["retry_after"] > first["retry_after"], (
        "each additional failure past the threshold must extend the lockout further "
        "(exponential backoff), not reuse the same fixed window forever"
    )


def test_success_clears_the_failure_count_and_lockout(db):
    database, ai, rl = db
    identity = "login:recovers@test.com"
    for _ in range(rl.FAILURE_THRESHOLD):
        rl.record_failure("pglite://test", identity)
    assert rl.check_lockout("pglite://test", identity)["locked"] is True

    rl.record_success("pglite://test", identity)

    assert rl.check_lockout("pglite://test", identity)["locked"] is False
    # A fresh run of failures afterward must start from zero again, not
    # pick up where the cleared count left off.
    outcome = rl.record_failure("pglite://test", identity)
    assert outcome["fail_count"] == 1


def test_different_identities_are_tracked_independently(db):
    database, ai, rl = db
    for _ in range(rl.FAILURE_THRESHOLD):
        rl.record_failure("pglite://test", "login:victim-a@test.com")
    assert rl.check_lockout("pglite://test", "login:victim-a@test.com")["locked"] is True
    assert rl.check_lockout("pglite://test", "login:victim-b@test.com")["locked"] is False


# ---------------------------------------------------------------------------
# login_email_account(): real brute-force simulation.
# ---------------------------------------------------------------------------

def test_repeated_wrong_passwords_lock_out_a_real_account(db):
    database, ai, rl = db
    ai.register_email_account("pglite://test", "real@test.com", "correcthorsebattery")

    last_error = None
    for _ in range(rl.FAILURE_THRESHOLD):
        with pytest.raises(ai.AccountError) as exc_info:
            ai.login_email_account("pglite://test", "real@test.com", "wrong-password")
        last_error = exc_info.value
    assert last_error.code == "invalid_credentials"

    with pytest.raises(ai.AccountError) as exc_info:
        ai.login_email_account("pglite://test", "real@test.com", "correcthorsebattery")  # even the real password
    assert exc_info.value.code == "too_many_attempts"
    assert exc_info.value.status == 429


def test_unknown_email_locks_out_on_the_exact_same_schedule_as_a_real_one(db):
    # The core anti-enumeration property: an attacker probing an email that
    # was never registered must see IDENTICAL behavior (same error code,
    # same threshold, same lockout) to probing a real one - otherwise the
    # lockout itself becomes an oracle for account existence.
    database, ai, rl = db
    for _ in range(rl.FAILURE_THRESHOLD):
        with pytest.raises(ai.AccountError) as exc_info:
            ai.login_email_account("pglite://test", "nobody-registered@test.com", "whatever")
        assert exc_info.value.code == "invalid_credentials"

    with pytest.raises(ai.AccountError) as exc_info:
        ai.login_email_account("pglite://test", "nobody-registered@test.com", "whatever")
    assert exc_info.value.code == "too_many_attempts"
    assert exc_info.value.status == 429


def test_successful_login_resets_the_lockout_state(db):
    database, ai, rl = db
    ai.register_email_account("pglite://test", "comeback@test.com", "correcthorsebattery")

    for _ in range(rl.FAILURE_THRESHOLD - 1):
        with pytest.raises(ai.AccountError):
            ai.login_email_account("pglite://test", "comeback@test.com", "wrong-password")

    # One more wrong attempt would lock it out - log in correctly instead.
    account_id = ai.login_email_account("pglite://test", "comeback@test.com", "correcthorsebattery")
    assert account_id

    # Now the user can fail FAILURE_THRESHOLD more times before locking
    # again - proving the earlier near-miss count was actually cleared,
    # not merely paused.
    for _ in range(rl.FAILURE_THRESHOLD - 1):
        with pytest.raises(ai.AccountError) as exc_info:
            ai.login_email_account("pglite://test", "comeback@test.com", "wrong-password")
        assert exc_info.value.code == "invalid_credentials"


def test_locked_account_login_never_reaches_the_password_check(db, monkeypatch):
    # Once locked, login_email_account must short-circuit before touching
    # verify_password() at all - confirms the lockout gate runs first.
    database, ai, rl = db
    ai.register_email_account("pglite://test", "gated@test.com", "correcthorsebattery")
    for _ in range(rl.FAILURE_THRESHOLD):
        with pytest.raises(ai.AccountError):
            ai.login_email_account("pglite://test", "gated@test.com", "wrong-password")

    called = {"n": 0}
    real_verify = ai.verify_password

    def counting_verify(*a, **k):
        called["n"] += 1
        return real_verify(*a, **k)

    monkeypatch.setattr(ai, "verify_password", counting_verify)
    with pytest.raises(ai.AccountError) as exc_info:
        ai.login_email_account("pglite://test", "gated@test.com", "correcthorsebattery")
    assert exc_info.value.code == "too_many_attempts"
    assert called["n"] == 0


# ---------------------------------------------------------------------------
# request_password_reset(): request-volume throttling, not brute force.
# ---------------------------------------------------------------------------

def test_forgot_password_throttles_repeated_requests_for_the_same_email(db, monkeypatch):
    database, ai, rl = db
    ai.register_email_account("pglite://test", "resetme@test.com", "correcthorsebattery")
    sent = {"n": 0}
    monkeypatch.setattr(ai, "send_password_reset_email", lambda email, token: sent.__setitem__("n", sent["n"] + 1))

    for _ in range(rl.FAILURE_THRESHOLD):
        ai.request_password_reset("pglite://test", "resetme@test.com")
    assert sent["n"] == rl.FAILURE_THRESHOLD

    # The next request within the lockout window must not send another
    # email, but must still return normally (never raises).
    ai.request_password_reset("pglite://test", "resetme@test.com")
    assert sent["n"] == rl.FAILURE_THRESHOLD


def test_forgot_password_never_reveals_whether_the_email_exists_even_while_throttled(db, monkeypatch):
    database, ai, rl = db
    sent = {"n": 0}
    monkeypatch.setattr(ai, "send_password_reset_email", lambda email, token: sent.__setitem__("n", sent["n"] + 1))

    # An email that was never registered: every call must return None
    # (never raise), exactly like a registered one, both before and after
    # the throttle kicks in.
    for _ in range(rl.FAILURE_THRESHOLD + 2):
        result = ai.request_password_reset("pglite://test", "never-registered@test.com")
        assert result is None
    assert sent["n"] == 0


# ---------------------------------------------------------------------------
# Shared, cross-worker state: the lockout lives in a real Postgres table
# that any worker/replica can read directly - not a process-local dict.
# ---------------------------------------------------------------------------

def test_failure_state_is_durably_visible_via_a_direct_sql_query(db):
    # Bypasses login_rate_limit.py's own functions entirely and reads the
    # table directly, the way a second worker process querying the same
    # shared Postgres instance would - proving the state lives in the
    # database, not in any in-process Python variable.
    database, ai, rl = db
    identity = "login:cross-worker@test.com"
    rl.record_failure("pglite://test", identity)
    rl.record_failure("pglite://test", identity)

    fail_count, retry_after = _raw_row(database, identity)
    assert int(fail_count) == 2


def test_two_independent_connections_see_the_same_accumulated_count(db):
    # Each call below opens its own brand-new connection (exactly what
    # db_connection() does per-call, and what a separate worker process
    # would do) - no Python object is shared between them except the
    # underlying database, simulating independent workers.
    database, ai, rl = db
    identity = "login:worker-a-then-b@test.com"

    for _ in range(3):
        outcome = rl.record_failure("pglite://test", identity)
    assert outcome["fail_count"] == 3

    # A "different worker" checking the same identity, with no shared
    # Python state at all beyond the module-level functions themselves.
    lock_state = rl.check_lockout("pglite://test", identity)
    assert lock_state["locked"] is False  # below threshold still

    for _ in range(rl.FAILURE_THRESHOLD - 3):
        outcome = rl.record_failure("pglite://test", identity)
    assert rl.check_lockout("pglite://test", identity)["locked"] is True


def test_module_holds_no_per_identity_state_of_its_own(db):
    # The one thing that WOULD make this process-local: a module-level
    # dict/cache keyed by identity. Only the schema-ready bookkeeping
    # (_SCHEMA_READY/_SCHEMA_LOCK) is allowed to live in the module itself.
    database, ai, rl = db
    allowed = {
        "_SCHEMA_LOCK", "_SCHEMA_READY", "FAILURE_THRESHOLD", "BASE_LOCKOUT_SECONDS", "MAX_LOCKOUT_SECONDS",
        "annotations",  # `from __future__ import annotations` binds this name to a _Feature object
    }
    suspicious = [
        name for name, value in vars(rl).items()
        if not name.startswith("__") and not callable(value) and not isinstance(value, type(rl))
        and name not in allowed
    ]
    assert suspicious == [], f"found unexpected module-level state that would make this process-local: {suspicious}"
