"""Canonical SYLVEX identity (Admin Console Phase 1).

- Every Telegram user gets a SYLVEX ID with CC=99 (SS 0626 99 NNNN), from a
  users trigger for new users and a batch backfill for existing ones.
- A SYLVEX ID never changes when another identity is linked. Merging two
  accounts that both have an ID keeps the OLDER one; the other becomes a
  permanent alias (still resolves, never reused), and deleting a login
  never changes or flips the canonical ID.
- Admin APIs present the canonical identity block and never a 900... storage
  key outside the owner-only `technical` section.

Real SQL (PGlite) - the trigger, sequences and unique index are the point.
"""
import json
import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from services.security import SecurityMiddleware

sys.path.insert(0, str(Path(__file__).parent / "support"))

TOKEN = "test-only-bot-token"
SERVICE_TOKEN = "test-only-service-token"
OWNER_ID = 555
SUPPORT_ID = 556
HEADERS = {"X-Admin-Service-Token": SERVICE_TOKEN}
FLOOR = 900_000_000_000


def _pglite_available():
    return bool(os.getenv("SYLVEX_TEST_NODE") and os.getenv("SYLVEX_PGLITE_MODULE"))


pytestmark = pytest.mark.skipif(not _pglite_available(), reason="Set SYLVEX_TEST_NODE and SYLVEX_PGLITE_MODULE to run real-SQL tests")


def _create_users(cur):
    cur.execute("CREATE TABLE users (telegram_id BIGINT PRIMARY KEY, username TEXT, first_name TEXT, "
                "balance INTEGER DEFAULT 0, subscription TEXT, created_at TEXT)")
    cur.execute("CREATE TABLE user_profiles (telegram_id BIGINT PRIMARY KEY, display_name TEXT)")
    # Production's subscriptions table stores its dates as TEXT.
    cur.execute("CREATE TABLE subscriptions (id SERIAL PRIMARY KEY, telegram_id BIGINT, subscription_type TEXT, "
                "payment_method TEXT, amount INTEGER, currency TEXT, starts_at TEXT, expires_at TEXT, status TEXT, "
                "charge_id TEXT UNIQUE, created_at TIMESTAMP DEFAULT NOW())")


class _PlainSQL(str):
    """Stand-in for psycopg2.sql in the merge path: the PGlite adapter takes
    plain strings, not Composed objects (identifiers here are our own)."""
    def format(self, **parts):
        return _PlainSQL(str.format(self, **parts))


def _identifier(name):
    return '"' + str(name).replace('"', '""') + '"'


@pytest.fixture
def database(monkeypatch):
    from types import SimpleNamespace
    from pglite_adapter import Database
    from services import account_identity as ai

    db = Database()
    monkeypatch.setattr(ai, "db_connect", lambda *a, **k: db.connect())
    monkeypatch.setattr(ai, "sql", SimpleNamespace(SQL=_PlainSQL, Identifier=_identifier))
    monkeypatch.setattr(ai, "_ACCOUNT_TABLES_READY", False)
    yield db
    db.close()


@pytest.fixture
def ai(database):
    from services import account_identity as ai
    conn = database.connect()
    _create_users(conn.cursor())
    conn.commit()
    ai.ensure_account_tables("pglite://test")
    return ai


def q(database, sql, params=()):
    conn = database.connect()
    cur = conn.cursor()
    cur.execute(sql, params)
    rows = cur.fetchall()
    conn.commit()
    return rows


def add_user(database, telegram_id, username=None, first_name="User", balance=0):
    q(database, "INSERT INTO users (telegram_id, username, first_name, balance, created_at) VALUES (%s,%s,%s,%s,NOW()::text)",
      (telegram_id, username, first_name, balance))


def account_of(database, telegram_id):
    rows = q(database, "SELECT account_id, origin FROM sylvex_accounts WHERE active_telegram_id = %s", (telegram_id,))
    return (int(rows[0][0]), rows[0][1]) if rows else None


def new_website_account(database, ai, email):
    conn = database.connect()
    cur = conn.cursor()
    account_id = ai._new_web_account(cur, "Web Person", email)
    cur.execute("INSERT INTO account_emails (account_id, email, password_hash, email_verified) VALUES (%s,%s,NULL,TRUE)",
                (account_id, email))
    conn.commit()
    storage = q(database, "SELECT active_telegram_id FROM sylvex_accounts WHERE account_id = %s", (account_id,))[0][0]
    return account_id, int(storage)


# --- allocation and the users trigger ------------------------------------

def test_new_telegram_users_get_cc99_ids_in_order(ai, database):
    add_user(database, 7000000001)
    add_user(database, 7000000002)
    assert account_of(database, 7000000001) == (110626990001, "telegram")
    assert account_of(database, 7000000002) == (110626990002, "telegram")


def test_conflicting_users_insert_does_not_allocate_again(ai, database):
    add_user(database, 7000000001)
    q(database, "INSERT INTO users (telegram_id, first_name) VALUES (7000000001, 'x') ON CONFLICT (telegram_id) DO NOTHING")
    assert q(database, "SELECT COUNT(*) FROM sylvex_accounts")[0][0] == 1
    assert ai.ensure_telegram_account(database.connect().cursor(), 7000000001) == 110626990001


def test_storage_key_users_row_gets_no_telegram_account(ai, database):
    account_id, storage = new_website_account(database, ai, "zed@test.com")
    assert storage >= FLOOR
    rows = q(database, "SELECT account_id, origin, storage_telegram_id FROM sylvex_accounts")
    assert rows == [[account_id, "website", storage]]


def test_website_ids_keep_their_own_sequence_and_cc(ai, database):
    add_user(database, 7000000001)
    account_id, _ = new_website_account(database, ai, "zed@test.com")
    assert account_id == 110626260001
    assert account_of(database, 7000000001)[0] == 110626990001


def test_telegram_allocator_never_produces_an_email_cc(ai, database):
    cur = database.connect().cursor()
    ids = [ai.allocate_telegram_sylvex_user_id(cur) for _ in range(3)]
    assert ids == [110626990001, 110626990002, 110626990003]
    assert all(str(i)[6:8] == "99" for i in ids)


def test_ensure_telegram_account_ignores_storage_and_invalid_ids(ai, database):
    cur = database.connect().cursor()
    assert ai.ensure_telegram_account(cur, FLOOR + 5) is None
    assert ai.ensure_telegram_account(cur, 0) is None
    assert ai.ensure_telegram_account(cur, -4) is None


def test_trigger_failure_never_blocks_user_creation(ai, database):
    q(database, "ALTER SEQUENCE sylvex_telegram_id_seq RESTART WITH 900000")  # series > 99 -> allocator raises
    add_user(database, 7000000009)
    assert q(database, "SELECT COUNT(*) FROM users WHERE telegram_id = 7000000009")[0][0] == 1
    assert account_of(database, 7000000009) is None


# --- backfill -------------------------------------------------------------

def test_backfill_assigns_existing_telegram_users_once(database):
    from services import account_identity as ai
    conn = database.connect()
    cur = conn.cursor()
    _create_users(cur)
    for tid in (7000000003, 7000000001, 7000000002):
        cur.execute("INSERT INTO users (telegram_id, first_name) VALUES (%s, 'old')", (tid,))
    conn.commit()
    ai.ensure_account_tables("pglite://test")  # trigger created after these users existed
    cur = database.connect().cursor()
    assert ai.count_telegram_accounts_missing(cur) == 3
    assert ai.backfill_telegram_accounts(cur, batch_size=2) == 2
    assert ai.backfill_telegram_accounts(cur, batch_size=2) == 1
    assert ai.backfill_telegram_accounts(cur, batch_size=2) == 0
    cur.connection.commit() if hasattr(cur, "connection") else None
    assert account_of(database, 7000000001)[0] == 110626990001
    assert account_of(database, 7000000003)[0] == 110626990003


def test_backfill_script_dry_run_writes_nothing_and_execute_assigns(database):
    from services import account_identity as ai
    from scripts.backfill_telegram_sylvex_ids import run
    conn = database.connect()
    cur = conn.cursor()
    _create_users(cur)
    cur.execute("INSERT INTO users (telegram_id, first_name) VALUES (7000000001, 'old'), (%s, 'storage')", (FLOOR + 1,))
    conn.commit()
    ai.ensure_account_tables("pglite://test")
    logs = []
    assert run(database.connect(), execute=False, log=logs.append) == {"missing": 1, "created": 0}
    assert account_of(database, 7000000001) is None
    result = run(database.connect(), execute=True, pause=0, log=logs.append)
    assert result == {"missing": 1, "created": 1, "remaining": 0}
    assert account_of(database, 7000000001) == (110626990001, "telegram")
    assert account_of(database, FLOOR + 1) is None


def test_backfill_script_refuses_before_schema_is_deployed(database):
    from scripts.backfill_telegram_sylvex_ids import run
    conn = database.connect()
    _create_users(conn.cursor())
    conn.commit()
    q(database, "CREATE TABLE sylvex_accounts (account_id BIGINT PRIMARY KEY, active_telegram_id BIGINT)")
    assert run(database.connect(), execute=True, log=lambda *_: None) is None


# --- merge, link status, deletion ----------------------------------------

def set_created(database, account_id, when):
    q(database, "UPDATE sylvex_accounts SET created_at = %s::timestamp WHERE account_id = %s", (when, account_id))


def alias_row(database, account_id):
    return q(database, "SELECT active_telegram_id, merged_into_account_id, merged_telegram_id FROM sylvex_accounts "
                       "WHERE account_id = %s", (account_id,))[0]


def no_email(monkeypatch, ai):
    monkeypatch.setattr(ai, "send_verification_email", lambda *a, **k: None)


def test_telegram_account_later_adds_email_keeps_its_id(ai, database, monkeypatch):
    no_email(monkeypatch, ai)
    add_user(database, 7000000001)
    tg_id = account_of(database, 7000000001)[0]
    ai.set_email_for_account("pglite://test", tg_id, "late@test.com", "correcthorsebattery")
    assert account_of(database, 7000000001) == (tg_id, "telegram")
    assert q(database, "SELECT account_id FROM account_emails WHERE email = 'late@test.com'") == [[tg_id]]
    assert ai.get_link_status_for_telegram("pglite://test", 7000000001)["sylvex_user_id"] == str(tg_id)
    assert ai.login_via_telegram_widget("pglite://test", 7000000001) == tg_id


def test_website_account_later_adds_new_telegram_keeps_its_id(ai, database):
    web_id, _ = new_website_account(database, ai, "zed@test.com")
    result = ai._do_merge("pglite://test", web_id, 7000000077, None, "New", False)
    assert result["sylvex_user_id"] == str(web_id) and result["retired_sylvex_user_id"] is None
    assert account_of(database, 7000000077) == (web_id, "website")
    # No Telegram-origin ID was minted for a Telegram id that only ever
    # existed as part of this account.
    assert q(database, "SELECT COUNT(*) FROM sylvex_accounts") == [[1]]
    assert ai.allocate_telegram_sylvex_user_id(database.connect().cursor()) == 110626990001


def test_website_account_adds_telegram_user_whose_account_is_newer(ai, database):
    web_id, _ = new_website_account(database, ai, "zed@test.com")
    set_created(database, web_id, "2025-01-01 00:00:00")
    add_user(database, 7000000001)
    tg_id = account_of(database, 7000000001)[0]
    set_created(database, tg_id, "2026-06-01 00:00:00")
    preview = ai.preview_merge("pglite://test", web_id, 7000000001)
    assert (preview["surviving_sylvex_user_id"], preview["retired_sylvex_user_id"]) == (str(web_id), str(tg_id))
    ai._do_merge("pglite://test", web_id, 7000000001, None, None, False)
    assert account_of(database, 7000000001) == (web_id, "website")
    assert alias_row(database, tg_id) == [None, web_id, 7000000001]


def test_merge_two_existing_accounts_older_id_survives(ai, database):
    add_user(database, 7000000001, balance=10)
    tg_id = account_of(database, 7000000001)[0]
    set_created(database, tg_id, "2024-03-01 00:00:00")
    web_id, storage = new_website_account(database, ai, "zed@test.com")
    q(database, "UPDATE users SET balance = 5 WHERE telegram_id = %s", (storage,))
    q(database, "UPDATE sylvex_accounts SET session_generation = 3 WHERE account_id = %s", (web_id,))
    result = ai._do_merge("pglite://test", web_id, 7000000001, None, None, False)
    assert (result["sylvex_user_id"], result["retired_sylvex_user_id"]) == (str(tg_id), str(web_id))
    # The older (Telegram) ID survives, unchanged; the website ID is a
    # permanent alias whose login moved to the survivor.
    assert account_of(database, 7000000001) == (tg_id, "telegram")
    assert alias_row(database, web_id) == [None, tg_id, 7000000001]
    assert q(database, "SELECT account_id FROM account_emails WHERE email = 'zed@test.com'") == [[tg_id]]
    assert ai.login_via_telegram_widget("pglite://test", 7000000001) == tg_id
    # The alias's web sessions are revoked; business data is consolidated.
    assert q(database, "SELECT session_generation FROM sylvex_accounts WHERE account_id = %s", (web_id,)) == [[4]]
    assert q(database, "SELECT balance FROM users WHERE telegram_id = 7000000001") == [[15]]
    assert q(database, "SELECT storage_telegram_id FROM sylvex_accounts WHERE account_id = %s", (tg_id,)) == [[storage]]


def test_search_by_retired_alias_resolves_to_the_same_final_user(ai, database):
    from services import admin_identity
    add_user(database, 7000000001)
    tg_id = account_of(database, 7000000001)[0]
    set_created(database, tg_id, "2024-03-01 00:00:00")
    web_id, _ = new_website_account(database, ai, "zed@test.com")
    ai._do_merge("pglite://test", web_id, 7000000001, None, None, False)
    cur = _cur(database)
    for query in (str(tg_id), str(web_id), "zed@test.com", "7000000001"):
        assert admin_identity.search_keys(cur, query)[:1] == [7000000001], query
    assert admin_identity.resolve_target(cur, sylvex_user_id=str(web_id)) == 7000000001
    identity = admin_identity.identities_for_keys(cur, [7000000001], technical=True)[7000000001]
    assert identity["sylvex_user_id"] == str(tg_id)
    assert identity["technical"]["alias_sylvex_user_ids"] == [str(web_id)]


@pytest.mark.parametrize("telegram_is_older", [True, False])
def test_deleting_the_website_login_never_changes_the_canonical_id(ai, database, telegram_is_older):
    add_user(database, 7000000001)
    tg_id = account_of(database, 7000000001)[0]
    web_id, _ = new_website_account(database, ai, "zed@test.com")
    set_created(database, tg_id, "2024-01-01 00:00:00" if telegram_is_older else "2026-06-01 00:00:00")
    set_created(database, web_id, "2025-01-01 00:00:00")
    ai._do_merge("pglite://test", web_id, 7000000001, None, None, False)
    canonical, alias = (tg_id, web_id) if telegram_is_older else (web_id, tg_id)
    assert account_of(database, 7000000001)[0] == canonical

    ai.delete_account("pglite://test", canonical)
    # Website login gone; the same ID keeps serving Telegram; alias stays retired.
    assert account_of(database, 7000000001)[0] == canonical
    assert q(database, "SELECT COUNT(*) FROM account_emails") == [[0]]
    assert alias_row(database, alias)[:2] == [None, canonical]
    status = ai.get_link_status_for_telegram("pglite://test", 7000000001)
    assert status == {"connected": False, "sylvex_user_id": str(canonical)}
    with pytest.raises(ai.AccountError):
        ai.login_via_telegram_widget("pglite://test", 7000000001)

    # Connecting a fresh website account later does not flip it back either:
    # the surviving account is older, so the new website ID is the alias.
    new_web, _ = new_website_account(database, ai, "again@test.com")
    ai._do_merge("pglite://test", new_web, 7000000001, None, None, False)
    assert account_of(database, 7000000001)[0] == canonical
    assert alias_row(database, new_web)[:2] == [None, canonical]
    assert alias_row(database, alias)[:2] == [None, canonical]


def test_retired_alias_cannot_be_merged_or_reused(ai, database):
    add_user(database, 7000000001)
    tg_id = account_of(database, 7000000001)[0]
    set_created(database, tg_id, "2024-01-01 00:00:00")
    web_id, _ = new_website_account(database, ai, "zed@test.com")
    ai._do_merge("pglite://test", web_id, 7000000001, None, None, False)
    with pytest.raises(ai.AccountError) as exc:
        ai._do_merge("pglite://test", web_id, 7000000099, None, None, False)
    assert exc.value.code == "account_already_merged"
    assert ai.preview_merge("pglite://test", web_id, 7000000099) == {"status": "conflict"}
    add_user(database, 7000000002)
    assert account_of(database, 7000000002)[0] not in (tg_id, web_id)


def test_telegram_only_user_is_not_linked_but_has_an_id(ai, database):
    add_user(database, 7000000001)
    assert ai.get_link_status_for_telegram("pglite://test", 7000000001) == {"connected": False, "sylvex_user_id": "110626990001"}
    with pytest.raises(ai.AccountError) as exc:
        ai.login_via_telegram_widget("pglite://test", 7000000001)
    assert exc.value.code == "telegram_not_linked"


def test_telegram_user_with_a_website_login_conflicts_with_another_website_account(ai, database):
    add_user(database, 7000000001)
    first, _ = new_website_account(database, ai, "zed@test.com")
    second, _ = new_website_account(database, ai, "amy@test.com")
    ai._do_merge("pglite://test", first, 7000000001, None, None, False)
    assert ai.preview_merge("pglite://test", second, 7000000001)["status"] == "conflict"
    with pytest.raises(ai.AccountError) as exc:
        ai._do_merge("pglite://test", second, 7000000001, None, None, False)
    assert exc.value.code == "telegram_already_linked"


def test_deleting_unlinked_website_account_creates_nothing(ai, database):
    web_account, _ = new_website_account(database, ai, "zed@test.com")
    ai.delete_account("pglite://test", web_account)
    assert q(database, "SELECT COUNT(*) FROM sylvex_accounts")[0][0] == 0


def test_backfilled_accounts_are_dated_from_the_users_first_seen_time(database):
    from services import account_identity as ai
    conn = database.connect()
    cur = conn.cursor()
    _create_users(cur)
    cur.execute("INSERT INTO users (telegram_id, first_name, created_at) VALUES "
                "(7000000001, 'old', '2024-02-03 04:05:06'), (7000000002, 'odd', 'not a date')")
    conn.commit()
    ai.ensure_account_tables("pglite://test")
    ai.backfill_telegram_accounts(database.connect().cursor())
    rows = dict(q(database, "SELECT active_telegram_id, created_at::date::text FROM sylvex_accounts"))
    assert rows[7000000001] == "2024-02-03"
    assert rows[7000000002] is not None  # unreadable -> backfill time, never an error


# --- admin identity resolver ---------------------------------------------

@pytest.fixture
def people(ai, database):
    """A Telegram-only user, a website-only user, a merged user (with the
    ghost storage row the merge leaves behind) and a payment reference."""
    add_user(database, 7000000001, username="tguser", first_name="Tele Gram", balance=5)
    web_only, web_storage = new_website_account(database, ai, "webby@test.com")
    add_user(database, 7000000002, username="merged", first_name="Merged Person")
    merged_canonical = account_of(database, 7000000002)[0]
    set_created(database, merged_canonical, "2024-01-01 00:00:00")
    merged_web, merged_storage = new_website_account(database, ai, "merged@test.com")
    # Telegram account is older: it keeps its ID, the website ID is retired.
    ai._do_merge("pglite://test", merged_web, 7000000002, None, None, False)
    q(database, "CREATE TABLE purchases (id SERIAL PRIMARY KEY, telegram_id BIGINT, provider TEXT, credits INTEGER, "
                "amount INTEGER, currency TEXT, payload TEXT, charge_id TEXT UNIQUE, status TEXT, created_at TIMESTAMP DEFAULT NOW())")
    q(database, "INSERT INTO purchases (telegram_id, provider, credits, amount, currency, charge_id, status) VALUES "
                "(%s, 'stars', 100, 50, 'XTR', 'stars_charge_abc123', 'completed'), "
                "(%s, 'paypal', 500, 500, 'USD', 'pp_capture_xyz789', 'completed')", (7000000001, web_storage))
    return {"tg": 7000000001, "tg_id": 110626990001, "web_only": web_only, "web_storage": web_storage,
            "merged_canonical": merged_canonical, "merged_storage": merged_storage, "merged_alias": merged_web}


def _cur(database):
    return database.connect().cursor()


def test_identity_block_for_each_kind_of_user(people, database):
    from services import admin_identity
    ids = admin_identity.identities_for_keys(_cur(database), [people["tg"], people["web_storage"], 7000000002])
    tg = ids[people["tg"]]
    assert tg["sylvex_user_id"] == "110626990001" and tg["telegram_id"] == 7000000001
    assert tg["account_origin"] == "telegram" and tg["linked"]["email"] is False
    web = ids[people["web_storage"]]
    assert web["sylvex_user_id"] == str(people["web_only"]) and web["telegram_id"] is None
    assert web["email"] == "webby@test.com" and web["linked"]["telegram"] is False
    merged = ids[7000000002]
    assert merged["sylvex_user_id"] == str(people["merged_canonical"]) and merged["telegram_id"] == 7000000002
    assert merged["linked"] == {"telegram": True, "email": True, "google": False, "apple": False}
    assert all("technical" not in v for v in ids.values())
    blocks = json.dumps(list(ids.values()))  # the map's keys are internal lookup keys
    assert str(people["web_storage"]) not in blocks
    assert str(people["merged_storage"]) not in blocks


def test_technical_section_only_when_requested(people, database):
    from services import admin_identity
    ids = admin_identity.identities_for_keys(_cur(database), [people["web_storage"], 7000000002], technical=True)
    assert ids[people["web_storage"]]["technical"]["internal_storage_id"] == people["web_storage"]
    merged_tech = ids[7000000002]["technical"]
    assert merged_tech["internal_storage_id"] == people["merged_storage"]
    assert merged_tech["alias_sylvex_user_ids"] == [str(people["merged_alias"])]


def test_ghost_storage_row_is_flagged_and_never_searchable(people, database):
    from services import admin_identity
    cur = _cur(database)
    ghost = admin_identity.identities_for_keys(cur, [people["merged_storage"]])[people["merged_storage"]]
    assert admin_identity.is_ghost_key(ghost)
    assert people["merged_storage"] not in admin_identity.search_keys(cur, "")
    assert admin_identity.search_keys(cur, str(people["merged_storage"])) == []
    assert admin_identity.search_keys(cur, str(people["web_storage"])) == []
    assert admin_identity.search_keys(cur, str(people["web_storage"]), technical=True) == [people["web_storage"]]


@pytest.mark.parametrize("query_key,expected_key", [
    ("tg_id", "tg"), ("web_only", "web_storage"), ("merged_canonical", "merged_tg"), ("merged_alias", "merged_tg"),
])
def test_search_by_sylvex_id_incl_retired_alias(people, database, query_key, expected_key):
    from services import admin_identity
    people = {**people, "merged_tg": 7000000002}
    assert admin_identity.search_keys(_cur(database), str(people[query_key]))[0] == people[expected_key]


@pytest.mark.parametrize("query,expected", [
    ("7000000001", "tg"), ("webby@test.com", "web_storage"), ("@tguser", "tg"), ("Merged Person", "merged_tg"),
    ("stars_charge_abc123", "tg"), ("pp_capture_xyz789", "web_storage"),
])
def test_search_by_telegram_id_email_username_name_payment(people, database, query, expected):
    from services import admin_identity
    people = {**people, "merged_tg": 7000000002}
    assert admin_identity.search_keys(_cur(database), query)[:1] == [people[expected]]


def test_search_returns_one_row_per_person(people, database):
    from services import admin_identity
    keys = admin_identity.search_keys(_cur(database), "merged")
    assert keys.count(7000000002) == 1 and people["merged_storage"] not in keys


def test_resolve_target_explicit_and_legacy(people, database):
    from services import admin_identity
    cur = _cur(database)
    assert admin_identity.resolve_target(cur, sylvex_user_id=str(people["web_only"])) == people["web_storage"]
    assert admin_identity.resolve_target(cur, sylvex_user_id=str(people["merged_alias"])) == 7000000002
    assert admin_identity.resolve_target(cur, user_id=7000000001) == 7000000001
    assert admin_identity.resolve_target(cur, user_id=str(people["web_only"])) == people["web_storage"]
    # legacy callers that still hold a storage key keep reaching the same row
    assert admin_identity.resolve_target(cur, user_id=people["web_storage"]) == people["web_storage"]
    assert admin_identity.resolve_target(cur, sylvex_user_id="999") is None
    assert admin_identity.resolve_target(cur, user_id="abc") is None


def test_decorate_replaces_storage_keys(people, database):
    from services import admin_identity
    rows = [{"telegram_id": people["web_storage"]}, {"actor_id": 7000000001, "target_id": people["web_storage"]}]
    admin_identity.decorate(_cur(database), rows[:1])
    admin_identity.decorate(_cur(database), rows[1:], fields=("actor_id", "target_id"))
    assert rows[0]["telegram_id"] is None and rows[0]["sylvex_user_id"] == str(people["web_only"])
    assert rows[1]["target_id"] is None and rows[1]["target_identity"]["sylvex_user_id"] == str(people["web_only"])
    assert rows[1]["actor_id"] == 7000000001 and rows[1]["actor_identity"]["sylvex_user_id"] == "110626990001"


# --- admin HTTP endpoints -------------------------------------------------

@pytest.fixture
def api(people, database, monkeypatch):
    monkeypatch.setenv("BOT_TOKEN", TOKEN)
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.setenv("ADMIN_SERVICE_TOKEN", SERVICE_TOKEN)
    import main
    monkeypatch.setattr(main, "TELEGRAM_AUTH_TOKENS", (TOKEN,))
    monkeypatch.setattr(main, "BOT_TOKEN", TOKEN)
    monkeypatch.setattr(main, "ADMIN_SERVICE_TOKEN", SERVICE_TOKEN)
    monkeypatch.setattr(main, "SUPERADMIN_TELEGRAM_ID", OWNER_ID)
    monkeypatch.setattr(main, "DATABASE_URL", "pglite://test")
    monkeypatch.setattr(main, "db_connect", lambda *a, **k: database.connect())
    monkeypatch.setattr(main, "ADMIN_SCHEMA_READY", False)
    monkeypatch.setattr(main, "_PAYMENT_SCHEMA_READY", False)
    monkeypatch.setattr(main, "_PROSTUDIO_SCHEMA_READY", False)
    main.ensure_admin_tables()
    from admin_fixtures import make_admin
    conn = database.connect()
    make_admin(conn.cursor(), SUPPORT_ID, legacy=["view_users", "message_users", "view_finance"])
    conn.commit()
    main.app.middleware_stack = None
    for mw in main.app.user_middleware:
        if mw.cls is SecurityMiddleware:
            mw.kwargs["quota_check"] = AsyncMock()
    return main


async def _post(main, path, body):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app), base_url="http://test") as client:
        return await client.post(path, headers=HEADERS, json=body)


@pytest.mark.asyncio
async def test_search_api_never_shows_storage_ids_to_normal_admins(api, people):
    r = await _post(api, "/api/admin/users/search", {"telegram_id": SUPPORT_ID, "query": ""})
    assert r.status_code == 200, r.text
    body = r.text
    assert str(people["web_storage"]) not in body and str(people["merged_storage"]) not in body
    by_id = {item["sylvex_user_id"]: item for item in r.json()["items"]}
    assert by_id[str(people["web_only"])]["telegram_id"] is None
    assert by_id["110626990001"]["telegram_id"] == 7000000001
    assert "technical" not in by_id["110626990001"]["identity"]
    assert len(by_id) == 3  # Telegram-only, website-only, merged - no ghost


@pytest.mark.asyncio
async def test_owner_sees_technical_ids(api, people):
    r = await _post(api, "/api/admin/users/search", {"telegram_id": OWNER_ID, "query": str(people["web_only"])})
    item = r.json()["items"][0]
    assert item["identity"]["technical"]["internal_storage_id"] == people["web_storage"]


@pytest.mark.asyncio
async def test_detail_by_sylvex_id_and_spend_per_currency(api, people):
    r = await _post(api, "/api/admin/users/detail", {"telegram_id": SUPPORT_ID, "sylvex_user_id": str(people["web_only"])})
    assert r.status_code == 200, r.text
    account = r.json()["account"]
    assert account["sylvex_user_id"] == str(people["web_only"]) and account["telegram_id"] is None
    assert account["spent_by_currency"] == {"USD": 500}
    assert "total_spent" not in account
    assert str(people["web_storage"]) not in r.text


@pytest.mark.asyncio
async def test_detail_with_legacy_user_id_holding_a_sylvex_id(api, people):
    r = await _post(api, "/api/admin/users/detail", {"telegram_id": SUPPORT_ID, "user_id": "110626990001"})
    assert r.status_code == 200 and r.json()["account"]["telegram_id"] == 7000000001


@pytest.mark.asyncio
async def test_message_to_website_only_account_is_refused(api, people, monkeypatch):
    post = MagicMock()
    monkeypatch.setattr(api.requests, "post", post)
    r = await _post(api, "/api/admin/users/message", {"telegram_id": SUPPORT_ID, "sylvex_user_id": str(people["web_only"]), "message": "hi"})
    assert r.status_code == 409 and r.json()["detail"] == "user_has_no_telegram"
    post.assert_not_called()


@pytest.mark.asyncio
async def test_broadcast_all_skips_storage_keys(api, people, monkeypatch):
    sent = []

    def fake_post(url, json=None, timeout=None):
        sent.append(json["chat_id"])
        response = MagicMock(status_code=200, content=b"{}")
        response.json.return_value = {"ok": True}
        return response

    monkeypatch.setattr(api.requests, "post", fake_post)
    # Broadcast is Critical: on the bot channel only the owner may send it.
    r = await _post(api, "/api/admin/messages/broadcast", {"telegram_id": OWNER_ID, "message": "hello", "all": True})
    assert r.status_code == 200, r.text
    assert sorted(sent) == [7000000001, 7000000002]
    assert all(chat < FLOOR for chat in sent)


@pytest.mark.asyncio
async def test_broadcast_to_selected_resolves_sylvex_ids(api, people, monkeypatch):
    sent = []

    def fake_post(url, json=None, timeout=None):
        sent.append(json["chat_id"])
        response = MagicMock(status_code=200, content=b"{}")
        response.json.return_value = {"ok": True}
        return response

    monkeypatch.setattr(api.requests, "post", fake_post)
    r = await _post(api, "/api/admin/messages/broadcast", {
        "telegram_id": OWNER_ID, "message": "hello",
        "user_ids": ["110626990001", str(people["web_only"])], "sylvex_user_ids": [str(people["merged_alias"])]})
    assert r.status_code == 200, r.text
    assert sorted(sent) == [7000000001, 7000000002]
    assert r.json()["skipped_no_telegram"] == 1


@pytest.mark.asyncio
async def test_non_owner_cannot_broadcast_through_the_bot_channel(api, people, monkeypatch):
    post = MagicMock()
    monkeypatch.setattr(api.requests, "post", post)
    r = await _post(api, "/api/admin/messages/broadcast", {"telegram_id": SUPPORT_ID, "message": "hello", "all": True})
    assert r.status_code == 403 and r.json()["detail"] == "console_required_for_critical_action"
    post.assert_not_called()


@pytest.mark.asyncio
async def test_top_spenders_ranks_by_credits_and_reports_currency_separately(api, people):
    r = await _post(api, "/api/admin/top-spenders", {"telegram_id": SUPPORT_ID})
    assert r.status_code == 200, r.text
    items = r.json()["items"]
    assert [i["sylvex_user_id"] for i in items] == [str(people["web_only"]), "110626990001"]
    assert items[0]["spent_by_currency"] == {"USD": 500} and items[1]["spent_by_currency"] == {"XTR": 50}
    assert all("total_spent" not in i for i in items)
    assert str(people["web_storage"]) not in r.text


# --- end to end: the website merge endpoint and the browser session -------

WEB_SECRET = "test-only-web-session-secret"


def _signed_widget(telegram_id, username="tguser", first_name="Tele"):
    """A Telegram Login Widget payload signed the way Telegram signs it:
    HMAC-SHA256 keyed with SHA256(bot_token)."""
    import hashlib
    import hmac
    import time
    fields = {"id": str(telegram_id), "first_name": first_name, "username": username,
              "auth_date": str(int(time.time()))}
    check = "\n".join(f"{k}={fields[k]}" for k in sorted(fields))
    fields["hash"] = hmac.new(hashlib.sha256(TOKEN.encode()).digest(), check.encode(), hashlib.sha256).hexdigest()
    return fields


@pytest.fixture
def web(ai, database, monkeypatch):
    monkeypatch.setenv("BOT_TOKEN", TOKEN)
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.setenv("WEB_SESSION_SECRET", WEB_SECRET)
    import main
    monkeypatch.setattr(main, "TELEGRAM_AUTH_TOKENS", (TOKEN,))
    monkeypatch.setattr(main, "BOT_TOKEN", TOKEN)
    monkeypatch.setattr(main, "DATABASE_URL", "pglite://test")
    monkeypatch.setattr(main, "db_connect", lambda *a, **k: database.connect())
    # The real session-generation counter, read from the same database the
    # merge writes to (production reads it through its own pool).
    monkeypatch.setattr(main, "current_web_session_generation", lambda account_id: int(
        (q(database, "SELECT session_generation FROM sylvex_accounts WHERE account_id = %s", (account_id,)) or [[0]])[0][0]))
    # Business state (balance, plan...) is not what these tests are about.
    monkeypatch.setattr(main, "get_user_state", lambda telegram_id: {"first_name": "Person", "balance": 0})
    main.app.middleware_stack = None
    for mw in main.app.user_middleware:
        if mw.cls is SecurityMiddleware:
            mw.kwargs["quota_check"] = AsyncMock()
    return main


async def _web_call(main, method, path, cookie, body=None):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app), base_url="http://test") as client:
        return await client.request(method, path, json=body, headers={"Cookie": f"sylvex_web_session={cookie}"})


@pytest.mark.asyncio
async def test_merge_reissues_the_website_session_for_the_surviving_older_account(web, ai, database):
    from services.security import create_web_session_token, verify_web_session_token
    add_user(database, 7000000001)
    tg_id = account_of(database, 7000000001)[0]
    set_created(database, tg_id, "2024-01-01 00:00:00")
    web_id, _ = new_website_account(database, ai, "zed@test.com")
    old_cookie = create_web_session_token(web_id, 0)

    r = await _web_call(web, "POST", "/api/web/account/telegram/confirm", old_cookie, _signed_widget(7000000001))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["merge_result"]["sylvex_user_id"] == str(tg_id)
    assert body["merge_result"]["retired_sylvex_user_id"] == str(web_id)
    assert body["authenticated"] is True and body["sylvex_user_id"] == tg_id
    assert body["email"] == "zed@test.com" and body["telegram_connected"] is True

    # The browser now holds a session for the surviving canonical account...
    new_cookie = r.cookies.get("sylvex_web_session")
    assert new_cookie and new_cookie != old_cookie
    assert verify_web_session_token(new_cookie) == (tg_id, 0)
    me = await _web_call(web, "GET", "/api/web/session/me", new_cookie)
    assert me.json()["authenticated"] is True and me.json()["sylvex_user_id"] == tg_id

    # ...and the retired account's old session no longer works anywhere.
    stale = await _web_call(web, "GET", "/api/web/session/me", old_cookie)
    assert stale.json() == {"authenticated": False}


@pytest.mark.asyncio
async def test_merge_keeps_the_website_session_when_the_website_account_survives(web, ai, database):
    from services.security import create_web_session_token
    web_id, _ = new_website_account(database, ai, "zed@test.com")
    set_created(database, web_id, "2024-01-01 00:00:00")
    add_user(database, 7000000001)
    cookie = create_web_session_token(web_id, 0)

    r = await _web_call(web, "POST", "/api/web/account/telegram/confirm", cookie, _signed_widget(7000000001))
    assert r.status_code == 200, r.text
    assert r.json()["merge_result"]["sylvex_user_id"] == str(web_id)
    assert r.json()["sylvex_user_id"] == web_id
    assert r.cookies.get("sylvex_web_session") is None  # nothing to re-issue
    me = await _web_call(web, "GET", "/api/web/session/me", cookie)
    assert me.json()["authenticated"] is True and me.json()["sylvex_user_id"] == web_id


@pytest.mark.asyncio
async def test_merge_with_a_forged_widget_signature_changes_nothing(web, ai, database):
    from services.security import create_web_session_token
    add_user(database, 7000000001)
    web_id, _ = new_website_account(database, ai, "zed@test.com")
    payload = _signed_widget(7000000001)
    payload["hash"] = "0" * 64
    r = await _web_call(web, "POST", "/api/web/account/telegram/confirm", create_web_session_token(web_id, 0), payload)
    assert r.status_code in (401, 403)
    assert r.cookies.get("sylvex_web_session") is None
    assert account_of(database, 7000000001)[1] == "telegram"
    assert alias_row(database, web_id)[1] is None
