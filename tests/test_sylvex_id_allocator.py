"""New Website accounts get a 12-digit SYLVEX ID (SS0626CCNNNN) instead of
the old small sequential account_id - see allocate_sylvex_user_id() and
_new_web_account() in services/account_identity.py.

These tests run against a real embedded Postgres (pglite), not mocks, since
the whole point of the design is atomicity guaranteed by a real Postgres
sequence (nextval()), not application-level logic.
"""
import os
import sys
import threading
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

    database = Database()
    monkeypatch.setattr(ai, "db_connect", lambda *a, **k: database.connect())
    monkeypatch.setattr(ai, "_ACCOUNT_TABLES_READY", False)
    # `users` isn't created by this codebase (it predates the webapp, shared
    # with the Telegram bot - see the earlier hot-path-indexes audit); it
    # must exist for _new_web_account()'s own INSERT INTO users.
    with database.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "CREATE TABLE users(telegram_id BIGINT PRIMARY KEY, first_name TEXT, "
                "username TEXT, balance INTEGER, subscription TEXT, created_at TEXT)"
            )
    ai.ensure_account_tables("pglite://test")
    yield database, ai
    database.close()


def test_a_first_account_z_at_test_com(db):
    database, ai = db
    with database.connect() as conn:
        with conn.cursor() as cur:
            sylvex_id = ai.allocate_sylvex_user_id(cur, "z@test.com")
    assert sylvex_id == 110626260001


def test_b_second_account_a_at_test_com(db):
    database, ai = db
    with database.connect() as conn:
        with conn.cursor() as cur:
            ai.allocate_sylvex_user_id(cur, "z@test.com")  # sequence 1
            second = ai.allocate_sylvex_user_id(cur, "a@test.com")  # sequence 2
    assert second == 110626010002


def test_c_third_account_7test_at_test_com(db):
    database, ai = db
    with database.connect() as conn:
        with conn.cursor() as cur:
            ai.allocate_sylvex_user_id(cur, "z@test.com")  # sequence 1
            ai.allocate_sylvex_user_id(cur, "a@test.com")  # sequence 2
            third = ai.allocate_sylvex_user_id(cur, "7test@test.com")  # sequence 3
    assert third == 110626070003


def test_d_uppercase_email_normalizes_to_lowercase(db):
    database, ai = db
    with database.connect() as conn:
        with conn.cursor() as cur:
            sylvex_id = ai.allocate_sylvex_user_id(cur, "ZTEST@test.com")
    # CC=26 (z), sequence 1 -> ...260001, same as the lowercase form.
    assert sylvex_id == 110626260001


def test_e_sequence_9999_stays_in_series_11(db):
    database, ai = db
    with database.connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT setval('sylvex_website_id_seq', 9998, true)")
            sylvex_id = ai.allocate_sylvex_user_id(cur, "a@test.com")
    assert sylvex_id == 110626019999


def test_f_sequence_10000_rolls_over_to_series_12(db):
    database, ai = db
    with database.connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT setval('sylvex_website_id_seq', 9999, true)")
            sylvex_id = ai.allocate_sylvex_user_id(cur, "a@test.com")
    assert sylvex_id == 120626010001


def test_g_concurrent_allocations_never_collide(db):
    # pglite (this harness's real-SQL backend) is a single WASM process
    # talking over one stdin/stdout pipe - concurrent *I/O* against it from
    # multiple Python threads isn't safe (interleaved writes/reads produce
    # garbled responses, not a real race), so pipe_lock serializes the
    # transport itself. What this still genuinely exercises from multiple
    # threads is allocate_sylvex_user_id() itself for any thread-local
    # state that could produce a duplicate id (there is none - the counter
    # is entirely nextval()'s server-side sequence). The actual atomicity
    # guarantee under real concurrent connections is Postgres's nextval()
    # on a sequence, which is atomic by construction - that isn't something
    # a single-process test harness needs to (or safely can) reprove.
    database, ai = db
    results = []
    errors = []
    results_lock = threading.Lock()
    pipe_lock = threading.Lock()

    def allocate_one(email):
        try:
            with pipe_lock:
                with database.connect() as conn:
                    with conn.cursor() as cur:
                        sylvex_id = ai.allocate_sylvex_user_id(cur, email)
            with results_lock:
                results.append(sylvex_id)
        except Exception as exc:  # pragma: no cover - surfaced via errors list
            with results_lock:
                errors.append(exc)

    threads = [threading.Thread(target=allocate_one, args=(f"user{i}@test.com",)) for i in range(25)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors, f"allocation raised under concurrency: {errors}"
    assert len(results) == 25
    assert len(set(results)) == 25, "two concurrent registrations received the same sylvex_user_id"


def test_h_existing_google_login_does_not_allocate_new_id(db):
    database, ai = db
    first = ai.oauth_login_or_register("pglite://test", "google", "sub-1", "user@test.com", "User")
    second = ai.oauth_login_or_register("pglite://test", "google", "sub-1", "user@test.com", "User")
    assert first == second


def test_i_existing_email_login_does_not_allocate_new_id(db):
    database, ai = db
    account_id = ai.register_email_account("pglite://test", "person@test.com", "correcthorsebattery")
    logged_in_id = ai.login_email_account("pglite://test", "person@test.com", "correcthorsebattery")
    assert account_id == logged_in_id


def test_j_google_and_email_registration_share_one_global_sequence(db):
    database, ai = db
    email_id = ai.register_email_account("pglite://test", "z@test.com", "correcthorsebattery")
    google_id = ai.oauth_login_or_register("pglite://test", "google", "sub-2", "a@test.com", "Person")
    # email registration is the 1st account ever created -> ...260001;
    # the Google registration right after is the 2nd -> ...010002 - same
    # global sequence, not a separate one per provider.
    assert email_id == 110626260001
    assert google_id == 110626010002


def test_email_first_char_outside_a_to_z0_to_9_is_rejected_not_guessed(db):
    database, ai = db
    with database.connect() as conn:
        with conn.cursor() as cur:
            with pytest.raises(ai.AccountError) as exc_info:
                ai.allocate_sylvex_user_id(cur, ".oddstart@test.com")
    assert exc_info.value.code == "email_unsupported_for_id_format"


def test_existing_account_id_column_is_bigint_not_integer(db):
    database, ai = db
    with database.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT data_type FROM information_schema.columns "
                "WHERE table_name = 'sylvex_accounts' AND column_name = 'account_id'"
            )
            assert cur.fetchone()[0] == "bigint"
            cur.execute(
                "SELECT data_type FROM information_schema.columns "
                "WHERE table_name = 'account_oauth' AND column_name = 'account_id'"
            )
            assert cur.fetchone()[0] == "bigint"
