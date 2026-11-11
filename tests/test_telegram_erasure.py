"""B09 / S7-04: support-assisted erasure of a Telegram account.

Synthetic data in an isolated PostgreSQL schema (same harness rules as
test_account_erasure.py); no Telegram message is sent, no real account.
The confirmed request goes through the real B09-WEB intake and processor.
"""
import os
import re
from pathlib import Path
from uuid import uuid4

import psycopg2
import pytest

from services import account_erasure as erasure
from services import account_erasure_guards as guards
from services import account_erasure_runner as runner
from services import telegram_erasure as tge

TG = 123456789          # Telegram-origin subject
OTHER = 987654321       # another Telegram user, never touched
WEB = 900000001234      # a website account's storage key
ACC, ACC_OTHER, ACC_WEB = 110626990001, 110626990002, 110626010001
OWNER = {"admin_id": 1, "account_id": 110626010099, "role": "owner", "channel": "web"}


@pytest.fixture
def db(monkeypatch, tmp_path):
    dsn = os.environ.get("SYLVEX_TEST_DATABASE_URL", "")
    if not dsn:
        pytest.skip("Dedicated isolated PostgreSQL required for erasure SQL tests")
    assert "@sx001c3-postgres:" in dsn and "/policy_erasure_test_" in dsn
    schema = "tg_erasure_case_" + uuid4().hex
    with psycopg2.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute('CREATE SCHEMA "' + schema + '"')

    def connect(*args, **kwargs):
        return psycopg2.connect(dsn, options="-c search_path=" + schema)

    monkeypatch.setattr(erasure, "db_connect", connect)
    journal = erasure.Journal(tmp_path / "ledger")
    monkeypatch.setenv("SYLVEX_ERASURE_JOURNAL_DIR", str(journal.path))
    monkeypatch.setenv("SYLVEX_ERASURE_ACCEPTING", "1")
    monkeypatch.setenv("SYLVEX_ERASURE_TELEGRAM_READY", "1")
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE users(telegram_id BIGINT PRIMARY KEY,username TEXT,first_name TEXT,balance INTEGER,subscription TEXT);
                CREATE TABLE sylvex_accounts(account_id BIGINT PRIMARY KEY,active_telegram_id BIGINT,
                    storage_telegram_id BIGINT,origin TEXT,merged_telegram_id BIGINT,merged_into_account_id BIGINT,
                    merged_at TIMESTAMP,session_generation INTEGER NOT NULL DEFAULT 0,created_at TIMESTAMPTZ NOT NULL DEFAULT NOW());
                CREATE TABLE prostudio_messages(id BIGSERIAL PRIMARY KEY,telegram_id BIGINT,prompt TEXT,image_url TEXT,metadata_json JSONB);
                CREATE TABLE purchases(id BIGSERIAL PRIMARY KEY,telegram_id BIGINT,credits INTEGER,amount INTEGER);
                CREATE TABLE subscription_agreements(id SERIAL PRIMARY KEY,telegram_id BIGINT NOT NULL,renewal_status TEXT NOT NULL);
                CREATE TABLE admin_accounts(id BIGSERIAL PRIMARY KEY,account_id BIGINT,status TEXT);
                CREATE TABLE sylvex_storage_objects(object_key TEXT PRIMARY KEY,file_url TEXT);
            """)
            cur.execute("INSERT INTO users VALUES(%s,'tg-fixture','Telegram fixture',77,'starter'),"
                        "(%s,'tg-other','Other',55,'pro'),(%s,'web-fixture','Web',12,'free')", (TG, OTHER, WEB))
            cur.execute("INSERT INTO sylvex_accounts(account_id,active_telegram_id,storage_telegram_id,origin) VALUES"
                        "(%s,%s,NULL,'telegram'),(%s,%s,NULL,'telegram'),(%s,%s,%s,'website')",
                        (ACC, TG, ACC_OTHER, OTHER, ACC_WEB, WEB, WEB))
            cur.execute("INSERT INTO prostudio_messages(telegram_id,prompt) VALUES(%s,'synthetic prompt'),(%s,'other prompt')",
                        (TG, OTHER))
            cur.execute("INSERT INTO purchases(telegram_id,credits,amount) VALUES(%s,100,1),(%s,200,2)", (TG, OTHER))
            erasure.ensure_schema(cur)
            guards.install(cur)

    class Env:
        sent = []
        audits = []
        send_ok = (True, None)

        def execute(self, sql, args=()):
            with connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(sql, args)
                    return cur.fetchall() if cur.description else None

        def send(self, telegram_id, text):
            self.sent.append((telegram_id, text))
            return self.send_ok

        def audit(self, cur, actor, action, **kw):
            self.audits.append(dict(kw, action=action, actor=actor.get("admin_id")))

        def accept(self, cur, account_id, *, ecosystem):
            return erasure.accept_confirmed_request(cur, account_id, ecosystem=ecosystem, journal=journal)

        def last_code(self):
            return re.search(r"Код подтверждения: (\d{6})", self.sent[-1][1]).group(1)

        def start(self, telegram_id=TG, **kw):
            kw.setdefault("support_ref", "support#42")
            kw.setdefault("reason", "user request by e-mail")
            with connect() as conn:
                with conn.cursor() as cur:
                    return tge.start(cur, OWNER, telegram_id, send=self.send, audit=self.audit, **kw)

        def confirm(self, confirmation_id, code, typed=TG, reason="confirmed by the account holder"):
            with connect() as conn:
                with conn.cursor() as cur:
                    return tge.confirm(cur, OWNER, confirmation_id, code=code, confirm_telegram_id=typed,
                                       reason=reason, accept=self.accept, audit=self.audit)

    env = Env()
    env.sent, env.audits, env.connect, env.journal = [], [], connect, journal
    yield env
    with psycopg2.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute('DROP SCHEMA "' + schema + '" CASCADE')


def test_code_goes_only_to_the_accounts_own_chat_and_is_never_stored_or_audited(db):
    reply = db.start()
    assert reply["ok"] and reply["telegram_hint"] == "…6789"
    assert len(db.sent) == 1 and db.sent[0][0] == TG
    code = db.last_code()
    assert "без кода аккаунт не будет удалён" in db.sent[0][1]
    stored = db.execute(f"SELECT code_hash,state,support_ref FROM {tge.TABLE}")
    assert stored[0][1] == "sent" and stored[0][2] == "support#42" and code not in stored[0][0]
    assert db.audits[-1]["action"] == "telegram_erasure_code_sent" and code not in repr(db.audits)
    assert code not in repr(reply)
    # Nothing is requested or deleted yet.
    assert not db.execute("SELECT 1 FROM sylvex_erasure_requests")
    assert db.execute("SELECT COUNT(*) FROM prostudio_messages") == [(2,)]


def test_confirmed_code_accepts_the_telegram_request_through_the_b09_intake(db):
    reply = db.start()
    done = db.confirm(reply["confirmation_id"], db.last_code())
    assert done["ok"] and done["accepted"] and done["state"] == "queued"
    request = db.execute("SELECT account_id,subject_key,ecosystem,state FROM sylvex_erasure_requests")
    assert request == [(ACC, TG, "telegram", "queued")]
    assert db.execute("SELECT generation FROM sylvex_tg_session_revocations WHERE telegram_id=%s", (TG,)) == [(1,)]
    assert db.execute("SELECT session_generation FROM sylvex_accounts WHERE account_id=%s", (ACC,)) == [(1,)]
    assert db.journal.read(done["request_id"])["ecosystem"] == "telegram"
    row = db.execute(f"SELECT state,code_hash,request_id::text FROM {tge.TABLE}")[0]
    assert row == ("confirmed", "", done["request_id"])
    assert db.audits[-1]["action"] == "telegram_erasure_accepted"
    assert db.audits[-1]["after"]["request_id"] == done["request_id"]
    # The intake itself deletes nothing; the other user is untouched.
    assert db.execute("SELECT COUNT(*) FROM prostudio_messages") == [(2,)]
    assert db.execute("SELECT balance FROM users WHERE telegram_id=%s", (OTHER,)) == [(55,)]
    with pytest.raises(tge.TelegramErasureError, match="confirmation_closed"):
        db.confirm(reply["confirmation_id"], "000000")


def test_wrong_codes_are_counted_and_lock_the_confirmation(db):
    reply = db.start()
    good = db.last_code()
    wrong = "000000" if good != "000000" else "111111"
    for left in (4, 3, 2, 1):
        result = db.confirm(reply["confirmation_id"], wrong)
        assert result == {"ok": False, "error": "invalid_code", "status": 400, "attempts_left": left}
    assert db.confirm(reply["confirmation_id"], wrong)["error"] == "too_many_attempts"
    assert db.execute(f"SELECT state,attempts,code_hash FROM {tge.TABLE}") == [("cancelled", 5, "")]
    with pytest.raises(tge.TelegramErasureError, match="confirmation_closed"):
        db.confirm(reply["confirmation_id"], good)
    assert not db.execute("SELECT 1 FROM sylvex_erasure_requests")


def test_retyped_telegram_id_must_match_and_does_not_spend_an_attempt(db):
    reply = db.start()
    with pytest.raises(tge.TelegramErasureError, match="telegram_id_mismatch"):
        db.confirm(reply["confirmation_id"], db.last_code(), typed=OTHER)
    assert db.execute(f"SELECT attempts,state FROM {tge.TABLE}") == [(0, "sent")]
    assert not db.execute("SELECT 1 FROM sylvex_erasure_requests")


def test_an_expired_code_is_closed_not_accepted(db):
    reply = db.start()
    db.execute(f"UPDATE {tge.TABLE} SET expires_at=NOW()-INTERVAL '1 second'")
    assert db.confirm(reply["confirmation_id"], db.last_code())["error"] == "code_expired"
    assert db.execute(f"SELECT state,code_hash FROM {tge.TABLE}") == [("expired", "")]
    assert not db.execute("SELECT 1 FROM sylvex_erasure_requests")
    assert db.start()["ok"]  # a new code can then be sent


@pytest.mark.parametrize("prepare,code", [
    ("UPDATE sylvex_accounts SET origin='website' WHERE account_id=110626990001", "not_a_telegram_account"),
    ("UPDATE sylvex_accounts SET merged_at=NOW() WHERE account_id=110626990001", "telegram_scope_requires_review"),
    ("INSERT INTO admin_accounts(account_id,status) VALUES(110626990001,'active')", "staff_account_requires_handover"),
    ("INSERT INTO subscription_agreements(telegram_id,renewal_status) VALUES(123456789,'auto')", "stars_renewal_active"),
    ("INSERT INTO subscription_agreements(telegram_id,renewal_status) VALUES(123456789,'stop_pending')", "stars_renewal_active"),
    ("DELETE FROM sylvex_accounts WHERE account_id=110626990001", "telegram_account_not_found"),
])
def test_out_of_scope_accounts_get_no_code(db, prepare, code):
    db.execute(prepare)
    with pytest.raises(tge.TelegramErasureError, match=code):
        db.start()
    assert not db.sent  # the refusal rolls back before any confirmation row exists
    assert db.execute("SELECT to_regclass(%s)", (tge.TABLE,)) == [(None,)]


def test_ended_stars_subscription_does_not_block(db):
    db.execute("INSERT INTO subscription_agreements(telegram_id,renewal_status) VALUES(%s,'canceled'),(%s,'ended')", (TG, TG))
    assert db.start()["ok"]


@pytest.mark.parametrize("value", [WEB, 0, -5, "abc", None])
def test_website_storage_keys_and_junk_are_not_telegram_ids(db, value):
    with pytest.raises(tge.TelegramErasureError, match="invalid_telegram_id"):
        db.start(telegram_id=value)
    assert not db.sent


def test_scope_is_checked_again_at_confirmation(db):
    reply = db.start()
    code = db.last_code()
    db.execute("INSERT INTO subscription_agreements(telegram_id,renewal_status) VALUES(%s,'auto')", (TG,))
    with pytest.raises(tge.TelegramErasureError, match="stars_renewal_active"):
        db.confirm(reply["confirmation_id"], code)
    assert not db.execute("SELECT 1 FROM sylvex_erasure_requests")
    assert db.execute(f"SELECT state FROM {tge.TABLE}") == [("sent",)]


def test_one_open_code_three_codes_a_day_and_support_reference_required(db):
    first = db.start()
    with pytest.raises(tge.TelegramErasureError, match="code_already_sent"):
        db.start()
    with db.connect() as conn:
        with conn.cursor() as cur:
            tge.cancel(cur, OWNER, first["confirmation_id"], reason="wrong person", audit=db.audit)
    assert db.audits[-1]["action"] == "telegram_erasure_cancelled"
    second = db.start()
    db.execute(f"UPDATE {tge.TABLE} SET state='cancelled' WHERE confirmation_id=%s", (second["confirmation_id"],))
    db.start()
    db.execute(f"UPDATE {tge.TABLE} SET state='cancelled' WHERE state='sent'")
    with pytest.raises(tge.TelegramErasureError, match="too_many_codes"):
        db.start()
    with pytest.raises(tge.TelegramErasureError, match="support_reference_required"):
        db.start(telegram_id=OTHER, support_ref=" ")


def test_failed_delivery_is_kept_and_audited_without_a_live_code(db):
    db.send_ok = (False, "Forbidden: bot was blocked by the user")
    reply = db.start()
    assert reply["ok"] is False and reply["error"] == "code_delivery_failed"
    assert db.execute(f"SELECT state,code_hash FROM {tge.TABLE}") == [("failed", "")]
    assert db.audits[-1]["action"] == "telegram_erasure_code_failed"


def test_admin_cannot_erase_own_account(db):
    actor = dict(OWNER, account_id=ACC)
    with db.connect() as conn:
        with conn.cursor() as cur:
            with pytest.raises(tge.TelegramErasureError, match="cannot_erase_self"):
                tge.start(cur, actor, TG, support_ref="x", reason="y", send=db.send, audit=db.audit)


def test_bot_client_gate_still_applies(db, monkeypatch):
    reply = db.start()
    monkeypatch.delenv("SYLVEX_ERASURE_TELEGRAM_READY")
    with pytest.raises(erasure.ErasureError, match="erasure_telegram_client_not_ready"):
        db.confirm(reply["confirmation_id"], db.last_code())
    assert not db.execute("SELECT 1 FROM sylvex_erasure_requests")


def test_the_confirmation_table_is_classified_so_erasures_are_not_held(db):
    db.start()
    assert tge.TABLE not in erasure.unknown_owned_tables(erasure.columns(db.connect().cursor()))


def _bot(db, monkeypatch):
    root = os.environ.get("SYLVEX_BOT_REVIEW_ROOT")
    if not root:
        pytest.skip("Peer bot source is required for cross-service erasure regression")
    import sys
    sys.path.insert(0, str(Path(root)))
    from app import account_erasure as bot_erasure
    monkeypatch.setattr(bot_erasure, "connect_db", db.connect)
    monkeypatch.setenv("SYLVEX_ERASURE_ENABLED", "1")
    return bot_erasure


class _Storage:
    def key_from_url(self, value):
        return ""

    def delete(self, key):
        raise AssertionError("no object in this case")

    def absent(self, key):
        return True


def test_end_to_end_bot_cache_then_processor_erases_only_the_subject_and_keeps_payments(db, monkeypatch):
    bot = _bot(db, monkeypatch)
    reply = db.start()
    done = db.confirm(reply["confirmation_id"], db.last_code())
    result = runner.process_request("synthetic-only", done["request_id"], storage=_Storage(), journal=db.journal, apply=True,
                                    self_service=True)
    assert result["hold_code"] == "telegram_cache_clear_pending"
    cleared = []
    bot.forget_pending(cleared.append)
    assert cleared == [TG]
    result = runner.process_request("synthetic-only", done["request_id"], storage=_Storage(), journal=db.journal, apply=True,
                                    self_service=True)
    assert result["complete"], result
    assert db.execute("SELECT telegram_id FROM prostudio_messages") == [(OTHER,)]
    assert db.execute("SELECT balance FROM users WHERE telegram_id=%s", (TG,)) == [(0,)]
    assert db.execute("SELECT balance FROM users WHERE telegram_id=%s", (OTHER,)) == [(55,)]
    assert db.execute("SELECT telegram_id,credits FROM purchases ORDER BY id") == [(TG, 100), (OTHER, 200)]


# --- S7-04 self-service: the person deletes their own Telegram account --------

SECRET = "test-only-self-erasure-secret"


def _preview(db, telegram_id=TG, now=1_000_000):
    with db.connect() as conn:
        with conn.cursor() as cur:
            return tge.self_preview(cur, telegram_id, secret=SECRET, now=now)


def _self_confirm(db, token, telegram_id=TG, now=1_000_100, scope=tge.SELF_SCOPE):
    with db.connect() as conn:
        with conn.cursor() as cur:
            return tge.self_confirm(cur, telegram_id, token=token, scope=scope, secret=SECRET, now=now, accept=db.accept)


def test_self_preview_shows_the_balance_and_gives_a_token_without_changing_anything(db):
    reply = _preview(db)
    assert reply["ok"] and reply["blocker"] is None and reply["balance"] == 77 and reply["expires_in"] == 600
    assert reply["confirm_token"].startswith(f"{TG}.{ACC}.")
    assert not db.execute("SELECT 1 FROM sylvex_erasure_requests")
    assert db.execute("SELECT COUNT(*) FROM prostudio_messages") == [(2,)]


def test_self_confirm_accepts_through_the_b09_intake_and_revokes_sessions(db):
    token = _preview(db)["confirm_token"]
    done = _self_confirm(db, token)
    assert done["ok"] and done["accepted"] and done["state"] == "queued"
    assert db.execute("SELECT account_id,subject_key,ecosystem FROM sylvex_erasure_requests") == [(ACC, TG, "telegram")]
    assert db.execute("SELECT generation FROM sylvex_tg_session_revocations WHERE telegram_id=%s", (TG,)) == [(1,)]
    assert db.execute("SELECT balance FROM users WHERE telegram_id=%s", (OTHER,)) == [(55,)]
    with pytest.raises(tge.TelegramErasureError, match="erasure_already_requested"):
        _self_confirm(db, token)


def test_a_renewing_stars_subscription_blocks_until_it_is_turned_off(db):
    db.execute("INSERT INTO subscription_agreements(telegram_id,renewal_status) VALUES(%s,'auto')", (TG,))
    reply = _preview(db)
    assert reply == {"ok": True, "blocker": "stars_renewal_active", "balance": 77}
    db.execute("UPDATE subscription_agreements SET renewal_status='canceled'")
    token = _preview(db)["confirm_token"]
    db.execute("UPDATE subscription_agreements SET renewal_status='auto'")  # turned back on before confirming
    with pytest.raises(tge.TelegramErasureError, match="stars_renewal_active"):
        _self_confirm(db, token)
    assert not db.execute("SELECT 1 FROM sylvex_erasure_requests")


@pytest.mark.parametrize("prepare,code", [
    ("INSERT INTO admin_accounts(account_id,status) VALUES(110626990001,'active')", "staff_account_requires_handover"),
    ("UPDATE sylvex_accounts SET merged_at=NOW() WHERE account_id=110626990001", "telegram_scope_requires_review"),
])
def test_self_preview_refuses_team_members_and_linked_accounts(db, prepare, code):
    db.execute(prepare)
    reply = _preview(db)
    assert reply["ok"] is False and reply["error"] == code and "confirm_token" not in reply


def test_the_token_is_bound_to_the_person_and_expires(db):
    token = _preview(db)["confirm_token"]
    other = _preview(db, telegram_id=OTHER)["confirm_token"]
    with pytest.raises(tge.TelegramErasureError, match="confirmation_invalid"):
        _self_confirm(db, other)                      # someone else's token
    with pytest.raises(tge.TelegramErasureError, match="confirmation_invalid"):
        _self_confirm(db, token[:-1] + ("0" if token[-1] != "0" else "1"))  # tampered
    with pytest.raises(tge.TelegramErasureError, match="confirmation_expired"):
        _self_confirm(db, token, now=1_000_000 + 601)
    with pytest.raises(tge.TelegramErasureError, match="erasure_scope_confirmation_required"):
        _self_confirm(db, token, scope="web_account_content_v1")
    assert not db.execute("SELECT 1 FROM sylvex_erasure_requests")


# --- S7-04: re-registration with the same Telegram id after a completed erasure --

def _allocator(db):
    db.execute("CREATE SEQUENCE sylvex_telegram_id_seq START 500")
    db.execute("CREATE FUNCTION sylvex_allocate_telegram_account_id() RETURNS BIGINT LANGUAGE sql AS "
               "$$ SELECT 110626990000 + nextval('sylvex_telegram_id_seq') $$")


def _erase_completely(db, monkeypatch):
    bot = _bot(db, monkeypatch)
    token = _preview(db)["confirm_token"]
    done = _self_confirm(db, token)
    runner.process_request("synthetic-only", done["request_id"], storage=_Storage(), journal=db.journal, apply=True,
                           self_service=True)
    bot.forget_pending(lambda uid: None)
    result = runner.process_request("synthetic-only", done["request_id"], storage=_Storage(), journal=db.journal,
                                    apply=True, self_service=True)
    assert result["complete"], result
    return bot, done["request_id"]


def test_completed_erasure_releases_the_telegram_id_as_a_new_empty_account(db, monkeypatch):
    _allocator(db)
    bot, request_id = _erase_completely(db, monkeypatch)
    # The erased identity is detached and kept as the request's record; a new SYLVEX ID exists.
    assert db.execute("SELECT active_telegram_id FROM sylvex_accounts WHERE account_id=%s", (ACC,)) == [(None,)]
    new = db.execute("SELECT account_id,origin FROM sylvex_accounts WHERE active_telegram_id=%s", (TG,))
    assert len(new) == 1 and new[0][0] != ACC and new[0][1] == "telegram"
    # Old data stays erased; payment records stay as they are.
    assert db.execute("SELECT telegram_id FROM prostudio_messages") == [(OTHER,)]
    assert db.execute("SELECT balance FROM users WHERE telegram_id=%s", (TG,)) == [(0,)]
    assert db.execute("SELECT telegram_id,credits FROM purchases ORDER BY id") == [(TG, 100), (OTHER, 200)]
    # No fence any more: API access check, bot admission, database write guard.
    erasure.check_subject_access("synthetic-only", TG)
    assert bot.pending(TG) is False
    operation = bot.begin_update(TG, "after-re-registration")
    bot.finish_update(operation)
    db.execute("INSERT INTO prostudio_messages(telegram_id,prompt) VALUES(%s,'new account')", (TG,))
    db.execute("UPDATE users SET username='back', balance=5 WHERE telegram_id=%s", (TG,))
    # The old request cannot touch the new account: processing it again is a no-op,
    # and the restore replay of its journal record finds it complete.
    again = runner.process_request("synthetic-only", request_id, storage=_Storage(), journal=db.journal, apply=True,
                                   self_service=True)
    assert again["complete"]
    from services import account_erasure_restore as restore
    assert restore.readiness("synthetic-only", journal=db.journal)["ready"]
    replayed = restore.replay("synthetic-only", storage=_Storage(), journal=db.journal, apply=True)
    assert replayed["ready"]
    assert db.execute("SELECT prompt FROM prostudio_messages WHERE telegram_id=%s", (TG,)) == [("new account",)]
    assert db.execute("SELECT username,balance FROM users WHERE telegram_id=%s", (TG,)) == [("back", 5)]
    # Payment records of the erased account are dated before the release cutoff.
    with db.connect() as conn:
        with conn.cursor() as cur:
            assert erasure.erased_before(cur, TG) is not None
            assert erasure.erased_before(cur, OTHER) is None
    # A second deletion of the re-registered account goes through support.
    reply = _preview(db)
    assert reply["ok"] is False and reply["error"] == "erasure_repeat_requires_support"


def test_until_completion_the_telegram_id_stays_blocked(db, monkeypatch):
    _allocator(db)
    bot = _bot(db, monkeypatch)
    token = _preview(db)["confirm_token"]
    _self_confirm(db, token)
    with pytest.raises(erasure.ErasureError, match="account_erasure_in_progress"):
        erasure.check_subject_access("synthetic-only", TG)
    assert bot.pending(TG) is True
    with pytest.raises(bot.ErasurePending):
        bot.begin_update(TG, "while-pending")
    assert db.execute("SELECT COUNT(*) FROM sylvex_accounts WHERE active_telegram_id=%s", (TG,)) == [(1,)]


def test_restore_of_an_older_backup_erases_the_old_account_again_and_releases(db, monkeypatch):
    """A backup taken before the erasure: the journal replays it, then releases."""
    _allocator(db)
    _, request_id = _erase_completely(db, monkeypatch)
    # Simulate the restored database: the request row and the release are gone, old data is back.
    # (the fence of a completed request whose identity is not released blocks these writes,
    # so the request rows go first, as in a backup taken before the request existed)
    db.execute("DELETE FROM sylvex_erasure_media; DELETE FROM sylvex_erasure_requests")
    db.execute("DELETE FROM sylvex_accounts WHERE active_telegram_id=%s", (TG,))
    db.execute("UPDATE sylvex_accounts SET active_telegram_id=%s WHERE account_id=%s", (TG, ACC))
    db.execute("INSERT INTO prostudio_messages(telegram_id,prompt) VALUES(%s,'restored old data')", (TG,))
    from services import account_erasure_restore as restore
    assert not restore.readiness("synthetic-only", journal=db.journal)["ready"]
    replayed = restore.replay("synthetic-only", storage=_Storage(), journal=db.journal, apply=True)
    assert replayed["ready"], replayed
    assert not db.execute("SELECT 1 FROM prostudio_messages WHERE telegram_id=%s", (TG,))
    new = db.execute("SELECT account_id FROM sylvex_accounts WHERE active_telegram_id=%s", (TG,))
    assert len(new) == 1 and new[0][0] != ACC


def test_new_account_does_not_see_the_erased_plans_with_production_text_columns(db, monkeypatch):
    """subscriptions as the main bot creates it: dates are TEXT, created_at unset."""
    from services import shop_orders
    _allocator(db)
    db.execute("CREATE TABLE subscriptions(id SERIAL PRIMARY KEY,telegram_id BIGINT,subscription_type TEXT,"
               "payment_method TEXT,amount INTEGER,currency TEXT,starts_at TEXT,expires_at TEXT,"
               "status TEXT DEFAULT 'active',charge_id TEXT UNIQUE,created_at TEXT)")
    db.execute("INSERT INTO subscriptions(telegram_id,subscription_type,starts_at,expires_at,status) VALUES"
               "(%s,'pro_month',NOW()-INTERVAL '3 days',NOW()+INTERVAL '27 days','active'),"
               "(%s,'starter_month',NOW()-INTERVAL '90 days',NOW()-INTERVAL '60 days','active')", (TG, TG))
    _erase_completely(db, monkeypatch)
    db.execute("DROP TABLE subscription_agreements")
    shop_orders.ensure_order_tables(db.connect)
    assert db.execute("SELECT status FROM subscriptions ORDER BY id") == [("canceled",), ("canceled",)]
    assert shop_orders.subscription_summary(db.connect, TG) is None
    # A plan bought by the new account (created_at stays unset, as in Production) is shown.
    db.execute("INSERT INTO subscriptions(telegram_id,subscription_type,payment_method,amount,currency,expires_at,status)"
               " VALUES(%s,'starter_month','telegram_stars',100,'XTR',NOW()+INTERVAL '30 days','active')", (TG,))
    summary = shop_orders.subscription_summary(db.connect, TG)
    assert summary and summary["state"] != "expired", summary
