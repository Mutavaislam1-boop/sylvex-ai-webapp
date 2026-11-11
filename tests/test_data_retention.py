"""B09 / S8-08: retention of error logs and closed support conversations.

Synthetic rows in an isolated PostgreSQL schema; no real data, no storage.
"""
import json
import os
from uuid import uuid4

import psycopg2
import pytest

from services import data_retention as dr

KEY = "generated/support-uploads/t123/" + "a" * 32 + ".png"


@pytest.fixture
def db():
    dsn = os.environ.get("SYLVEX_TEST_DATABASE_URL", "")
    if not dsn:
        pytest.skip("Dedicated isolated PostgreSQL required for retention SQL tests")
    assert "@sx001c3-postgres:" in dsn and "/policy_erasure_test_" in dsn
    schema = "retention_case_" + uuid4().hex
    with psycopg2.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute('CREATE SCHEMA "' + schema + '"')

    def connect():
        return psycopg2.connect(dsn, options="-c search_path=" + schema)

    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE prostudio_errors(id SERIAL PRIMARY KEY,telegram_id BIGINT,error_text TEXT,created_at TIMESTAMP DEFAULT NOW());
                CREATE TABLE prostudio_error_reports(id SERIAL PRIMARY KEY,telegram_id BIGINT NOT NULL,prompt TEXT,
                    status TEXT DEFAULT 'open',created_at TIMESTAMP DEFAULT NOW());
                CREATE TABLE support_threads(id BIGSERIAL PRIMARY KEY,account_id BIGINT,user_key BIGINT,status TEXT NOT NULL DEFAULT 'open',
                    created_at TIMESTAMP NOT NULL DEFAULT NOW(),updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
                    last_message_at TIMESTAMP NOT NULL DEFAULT NOW());
                CREATE TABLE support_messages(id BIGSERIAL PRIMARY KEY,
                    thread_id BIGINT NOT NULL REFERENCES support_threads(id) ON DELETE CASCADE,
                    direction TEXT NOT NULL,body TEXT NOT NULL,image_key TEXT,attachments JSONB,
                    created_at TIMESTAMP NOT NULL DEFAULT NOW());
                CREATE TABLE financial_review_cases(id SERIAL PRIMARY KEY,telegram_id BIGINT,
                    review_revision INTEGER NOT NULL,resolved_revision INTEGER NOT NULL DEFAULT 0);
                CREATE TABLE purchases(id SERIAL PRIMARY KEY,telegram_id BIGINT,amount INTEGER,created_at TIMESTAMP);
                CREATE TABLE subscription_payments(id SERIAL PRIMARY KEY,telegram_id BIGINT,created_at TIMESTAMP);
                CREATE TABLE admin_audit_events(id SERIAL PRIMARY KEY,action TEXT,at TIMESTAMP);
                CREATE TABLE user_notifications(id SERIAL PRIMARY KEY,thread_id BIGINT,body TEXT,created_at TIMESTAMP);
            """)
            old = "NOW() - INTERVAL '3 years'"
            cur.execute(f"INSERT INTO purchases(telegram_id,amount,created_at) VALUES(1,10,{old})")
            cur.execute(f"INSERT INTO subscription_payments(telegram_id,created_at) VALUES(1,{old})")
            cur.execute(f"INSERT INTO admin_audit_events(action,at) VALUES('x',{old})")

    class Env:
        def q(self, sql, args=()):
            with connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(sql, args)
                    return cur.fetchall() if cur.description else None

        def thread(self, status, *, closed_months=0, last_months=None, user_key=123, attachments=None, image_key=None):
            last_months = closed_months if last_months is None else last_months
            tid = self.q("INSERT INTO support_threads(user_key,status,updated_at,last_message_at) VALUES "
                         "(%s,%s,NOW()-make_interval(months=>%s),NOW()-make_interval(months=>%s)) RETURNING id",
                         (user_key, status, closed_months, last_months))[0][0]
            self.q("INSERT INTO support_messages(thread_id,direction,body,image_key,attachments) VALUES "
                   "(%s,'in','help me',NULL,%s::jsonb),(%s,'out','answer',%s,NULL)",
                   (tid, json.dumps(attachments) if attachments else None, tid, image_key))
            self.q("INSERT INTO user_notifications(thread_id,body) VALUES(%s,'answer')", (tid,))
            return tid

        def purge(self, **kw):
            with connect() as conn:
                with conn.cursor() as cur:
                    return dr.purge_once(cur, **kw)

        def preview(self):
            with connect() as conn:
                with conn.cursor() as cur:
                    return dr.preview(cur)

    env = Env()
    env.connect = connect
    yield env
    with psycopg2.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute('DROP SCHEMA "' + schema + '" CASCADE')


def _protected(db):
    return (db.q("SELECT COUNT(*) FROM purchases"), db.q("SELECT COUNT(*) FROM subscription_payments"),
            db.q("SELECT COUNT(*) FROM admin_audit_events"), db.q("SELECT COUNT(*) FROM user_notifications"))


def test_error_logs_older_than_30_days_are_removed_newer_kept(db):
    for table in ("prostudio_errors", "prostudio_error_reports"):
        db.q(f"INSERT INTO {table}(telegram_id,created_at) VALUES(1,NOW()-INTERVAL '31 days'),(2,NOW()-INTERVAL '29 days'),"
             f"(3,NOW()-INTERVAL '400 days')")
    result = db.purge()
    assert result["error_logs"] == {"prostudio_errors": 2, "prostudio_error_reports": 2}
    for table in ("prostudio_errors", "prostudio_error_reports"):
        assert db.q(f"SELECT telegram_id FROM {table}") == [(2,)]


def test_closed_conversation_is_removed_12_months_after_closure_with_its_own_files_only(db):
    gone = db.thread("closed", closed_months=13, attachments=[{"key": KEY, "name": "a.png"},
                                                               {"key": "generated/other/x.png"}],
                     image_key="messages/admin-image.png")
    kept = db.thread("closed", closed_months=11)
    before = _protected(db)
    result = db.purge()
    assert result["support_threads"] == 1 and result["support_messages"] == 2
    assert result["attachment_keys"] == [KEY]  # never an admin image or another folder
    assert db.q("SELECT id FROM support_threads") == [(kept,)]
    assert not db.q("SELECT 1 FROM support_messages WHERE thread_id=%s", (gone,))
    assert _protected(db) == before


@pytest.mark.parametrize("status,closed,last", [
    ("open", 30, 30), ("in_progress", 30, 30), ("answered", 30, 30),  # never closed
    ("closed", 13, 6),   # a message after closure
])
def test_conversations_not_closed_for_12_months_stay(db, status, closed, last):
    db.thread(status, closed_months=closed, last_months=last)
    assert db.purge()["support_threads"] == 0
    assert db.q("SELECT COUNT(*) FROM support_messages") == [(2,)]


def test_an_unresolved_payment_review_keeps_the_conversation(db):
    db.q("INSERT INTO financial_review_cases(telegram_id,review_revision,resolved_revision) VALUES(123,2,1)")
    db.thread("closed", closed_months=24)
    assert db.purge()["support_threads"] == 0
    db.q("UPDATE financial_review_cases SET resolved_revision=2")
    assert db.purge()["support_threads"] == 1


def test_preview_counts_what_a_pass_removes_and_changes_nothing(db):
    db.q("INSERT INTO prostudio_errors(telegram_id,created_at) VALUES(1,NOW()-INTERVAL '40 days')")
    db.thread("closed", closed_months=13)
    db.thread("closed", closed_months=1)
    first = db.preview()
    assert first["error_logs"] == {"prostudio_errors": 1, "prostudio_error_reports": 0}
    assert first["support_threads"] == 1 and first["support_messages"] == 2
    assert db.preview() == first
    result = db.purge()
    assert result["error_logs"]["prostudio_errors"] == 1 and result["support_threads"] == 1
    after = db.preview()
    assert after["error_logs"]["prostudio_errors"] == 0 and after["support_threads"] == 0


def test_batches_are_bounded(db):
    db.q("INSERT INTO prostudio_errors(telegram_id,created_at) SELECT g,NOW()-INTERVAL '60 days' FROM generate_series(1,25) g")
    assert db.purge(batch=10)["error_logs"]["prostudio_errors"] == 10
    assert db.q("SELECT COUNT(*) FROM prostudio_errors") == [(15,)]


def test_one_pass_at_a_time(db):
    db.q("INSERT INTO prostudio_errors(telegram_id,created_at) VALUES(1,NOW()-INTERVAL '60 days')")
    holder = db.connect()
    cur = holder.cursor()
    cur.execute("SELECT pg_advisory_xact_lock(%s,%s)", dr.LOCK)
    try:
        assert db.purge() == {"skipped": "locked"}
        assert db.q("SELECT COUNT(*) FROM prostudio_errors") == [(1,)]
    finally:
        holder.rollback()
        holder.close()


def test_missing_tables_are_skipped(db):
    db.q("DROP TABLE support_messages; DROP TABLE support_threads; DROP TABLE prostudio_error_reports")
    db.q("INSERT INTO prostudio_errors(telegram_id,created_at) VALUES(1,NOW()-INTERVAL '60 days')")
    assert db.purge() == {"error_logs": {"prostudio_errors": 1}, "support_threads": 0, "support_messages": 0,
                          "finished_operations": 0, "attachment_keys": []}


def test_only_finished_fence_entries_older_than_a_day_are_removed(db):
    db.q("CREATE TABLE sylvex_active_operations(operation_id UUID PRIMARY KEY,subject_key BIGINT NOT NULL,"
         "generation_id TEXT NOT NULL,state TEXT NOT NULL,started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),"
         "finished_at TIMESTAMPTZ,process_id TEXT NOT NULL)")
    rows = [("finished", "NOW()-INTERVAL '2 days'"), ("finished", "NOW()-INTERVAL '2 hours'"),
            ("active", "NULL"), ("active", "NULL")]
    for i, (state, finished) in enumerate(rows):
        db.q(f"INSERT INTO sylvex_active_operations VALUES(%s,123,'telegram-update:{i}',%s,NOW()-INTERVAL '3 days',"
             f"{finished},'1')", (str(uuid4()), state))
    assert db.preview()["finished_operations"] == 1
    assert db.purge()["finished_operations"] == 1
    assert db.q("SELECT state,COUNT(*) FROM sylvex_active_operations GROUP BY state ORDER BY state") == [
        ("active", 2), ("finished", 1)]


def test_attachment_deletion_is_best_effort_and_counted():
    calls = []

    def delete(key):
        calls.append(key)
        if key.endswith("bad"):
            raise TimeoutError("synthetic")

    assert dr.delete_attachments([KEY, KEY + "bad"], delete) == (1, 1)
    assert calls == [KEY, KEY + "bad"]


def test_retention_is_off_by_default():
    import main
    assert main.DATA_RETENTION_ENABLED is (os.getenv("DATA_RETENTION_ENABLED") == "1")
    assert os.getenv("DATA_RETENTION_ENABLED") != "1" and main.DATA_RETENTION_ENABLED is False
