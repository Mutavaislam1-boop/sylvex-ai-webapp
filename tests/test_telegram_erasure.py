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
