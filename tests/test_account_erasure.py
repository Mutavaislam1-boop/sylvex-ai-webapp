"""Synthetic erasure regression. No real account, provider or object access."""
import sys
from types import SimpleNamespace
import json
import os
from pathlib import Path
import stat
from uuid import uuid4

import psycopg2
import pytest

from services import account_erasure as erasure
from services import account_erasure_guards as guards
from services import account_erasure_runner as runner
from services import account_erasure_policy as policy

A, B = 110626010001, 110626020002
REFERENCE_INDEX = os.environ.get("SYLVEX_TEST_REFERENCE_INDEX") == "1"
U, V = 900000001234, 900000005678


@pytest.fixture
def case(monkeypatch, tmp_path):
    dsn = os.environ.get("SYLVEX_TEST_DATABASE_URL", "")
    if not dsn:
        pytest.skip("Dedicated isolated PostgreSQL required for erasure SQL tests")
    assert "@sx001c3-postgres:" in dsn and "/policy_erasure_test_" in dsn
    schema = "erasure_case_" + uuid4().hex
    with psycopg2.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute('CREATE SCHEMA "' + schema + '"')

    def connect(*args, **kwargs):
        return psycopg2.connect(dsn, options="-c search_path=" + schema)

    monkeypatch.setattr(erasure, "db_connect", connect)
    journal = erasure.Journal(tmp_path / "ledger")
    monkeypatch.setenv("SYLVEX_ERASURE_JOURNAL_DIR", str(journal.path))
    monkeypatch.setenv("SYLVEX_ERASURE_ACCEPTING","1")
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE users(telegram_id BIGINT PRIMARY KEY,username TEXT,first_name TEXT,balance INTEGER,subscription TEXT);
                CREATE TABLE sylvex_accounts(account_id BIGINT PRIMARY KEY,active_telegram_id BIGINT,
                    storage_telegram_id BIGINT,origin TEXT,merged_telegram_id BIGINT,merged_into_account_id BIGINT,
                    merged_at TIMESTAMP,session_generation INTEGER NOT NULL DEFAULT 0,created_at TIMESTAMPTZ NOT NULL DEFAULT NOW());
                CREATE TABLE account_emails(account_id BIGINT PRIMARY KEY,email TEXT,password_hash TEXT);
                CREATE TABLE prostudio_messages(id BIGSERIAL PRIMARY KEY,telegram_id BIGINT,prompt TEXT,image_url TEXT,metadata_json JSONB);
                CREATE TABLE prostudio_resources(id BIGSERIAL PRIMARY KEY,telegram_id BIGINT,photos_json TEXT);
                CREATE TABLE prostudio_generation_jobs(id TEXT PRIMARY KEY,telegram_id BIGINT,status TEXT,cost INTEGER,
                    prompt TEXT,request_json JSONB,result_json JSONB,created_at TIMESTAMPTZ NOT NULL DEFAULT NOW());
                CREATE TABLE prostudio_media_outbox(job_id TEXT PRIMARY KEY REFERENCES prostudio_generation_jobs(id),status TEXT);
                CREATE TABLE generation_reservations(generation_id TEXT PRIMARY KEY,telegram_id BIGINT,status TEXT,credits INTEGER);
                CREATE TABLE purchases(id BIGSERIAL PRIMARY KEY,telegram_id BIGINT,credits INTEGER,amount INTEGER);
                CREATE TABLE payment_inbox(charge_id TEXT PRIMARY KEY,telegram_id BIGINT,status TEXT);
                CREATE TABLE sylvex_storage_objects(object_key TEXT PRIMARY KEY,file_url TEXT);
            """)
            cur.execute("INSERT INTO users VALUES(%s,'fixture-a','Fixture A',1234,'starter'),(%s,'fixture-b','Fixture B',5678,'pro')", (U,V))
            cur.execute("INSERT INTO sylvex_accounts(account_id,active_telegram_id,storage_telegram_id,origin) "
                        "VALUES(%s,%s,%s,'website'),(%s,%s,%s,'website')", (A,U,U,B,V,V))
            cur.execute("INSERT INTO account_emails VALUES(%s,'a@example.invalid','fake-hash'),(%s,'b@example.invalid','fake-hash')", (A,B))
            cur.execute("INSERT INTO purchases(telegram_id,credits,amount) VALUES(%s,100,1),(%s,200,2)", (U,V))
            erasure.ensure_schema(cur)
            guards.install(cur)
            if REFERENCE_INDEX:
                guards.install_reference_index(cur)
    if REFERENCE_INDEX:
        # The whole suite also runs with the reference index in use.
        done = guards.backfill_reference_index("synthetic-only", wait_for_older=False)
        assert not done["pending"], done

    class Case:
        def execute(self, sql, args=()):
            with connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(sql, args)
                    if cur.description:
                        return cur.fetchall()

        def accept(self, account=A):
            with connect() as conn:
                with conn.cursor() as cur:
                    return erasure.accept_confirmed_request(cur, account, journal=journal)

    item = Case()
    item.connect, item.journal = connect, journal
    yield item
    with psycopg2.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute('DROP SCHEMA "' + schema + '" CASCADE')


class FakeStorage:
    def __init__(self, objects=()):
        self.objects = set(objects)
        self.calls = []
        self.fail_delete = set()
        self.fail_head = set()

    def key_from_url(self, value):
        marker = "https://media.example.invalid/api/public/storage/"
        return value[len(marker):].split("?",1)[0] if value.startswith(marker) else ""

    def delete(self, key):
        self.calls.append(key)
        if key in self.fail_delete:
            raise TimeoutError("synthetic object timeout")
        self.objects.discard(key)

    def absent(self, key):
        if key in self.fail_head:
            raise PermissionError("synthetic access denied")
        return key not in self.objects


def test_confirmed_receipt_is_accepted_not_completed_and_keeps_finances(case):
    before = case.execute("SELECT telegram_id,balance,subscription FROM users ORDER BY telegram_id")
    reply = case.accept()
    assert reply["accepted"] and not reply["complete"] and reply["state"] == "queued"
    assert case.execute("SELECT telegram_id,balance,subscription FROM users ORDER BY telegram_id") == before
    assert case.execute("SELECT COUNT(*) FROM purchases")[0][0] == 2
    assert case.execute("SELECT COUNT(*) FROM account_emails")[0][0] == 2
    assert case.execute("SELECT session_generation FROM sylvex_accounts WHERE account_id=%s",(A,))[0][0] == 1
    assert case.execute("SELECT session_generation FROM sylvex_accounts WHERE account_id=%s",(B,))[0][0] == 0
    assert erasure.pending_account("synthetic-only",A)
    assert not erasure.pending_account("synthetic-only",B)


def test_repeated_request_has_one_receipt_and_one_revocation(case):
    first, second = case.accept(), case.accept()
    assert first == second
    assert case.execute("SELECT COUNT(*) FROM sylvex_erasure_requests")[0][0] == 1
    assert case.execute("SELECT session_generation FROM sylvex_accounts WHERE account_id=%s",(A,))[0][0] == 1


def test_journal_is_private_and_has_no_creative_or_login_data(case):
    reply = case.accept()
    path = case.journal.path / (reply["request_id"] + ".json")
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert stat.S_IMODE(case.journal.path.stat().st_mode) == 0o700
    text = path.read_text()
    assert "example.invalid" not in text and "fake-hash" not in text and "Fixture" not in text
    record = case.journal.read(reply["request_id"])
    assert record["account_id"] == A and record["subject_key"] == U
    assert len(list(case.journal.records())) == 1


def test_tampered_journal_is_not_accepted(case):
    reply = case.accept()
    path = case.journal.path / (reply["request_id"] + ".json")
    body = json.loads(path.read_text());body["record"]["subject_key"] = V
    path.write_text(json.dumps(body))
    with pytest.raises(erasure.ErasureError,match="erasure_journal_invalid"):
        case.journal.read(reply["request_id"])


def test_unsafe_journal_permissions_refuse_before_closing_access(case,tmp_path):
    path = tmp_path/"unsafe";path.mkdir(mode=0o755)
    with pytest.raises(erasure.ErasureError,match="erasure_journal_unsafe"):
        erasure.Journal(path)
    assert case.execute("SELECT COUNT(*) FROM sylvex_erasure_requests")[0][0] == 0


def test_mixed_legacy_scope_does_not_erase_telegram(case):
    case.execute("UPDATE sylvex_accounts SET active_telegram_id=12345,merged_at=NOW() WHERE account_id=%s",(A,))
    reply = case.accept()
    assert reply["state"] == "scope_review" and not reply["complete"]
    assert case.journal.read(reply["request_id"])["subject_key"] is None
    assert case.execute("SELECT COUNT(*) FROM users")[0][0] == 2
    assert not case.execute("SELECT to_regclass('sylvex_tg_session_revocations')")[0][0]


def test_unknown_owned_table_is_held_not_purged(case):
    case.execute("CREATE TABLE new_unclassified_content(id BIGINT,telegram_id BIGINT,prompt TEXT)")
    case.execute("INSERT INTO new_unclassified_content VALUES(1,%s,'synthetic private text')",(U,))
    reply = case.accept()
    plan = erasure.plan_request("synthetic-only",reply["request_id"],storage=FakeStorage(),journal=case.journal)
    assert plan["hold_code"] == "unclassified_owned_table" and not plan["complete"]
    assert case.execute("SELECT COUNT(*) FROM new_unclassified_content")[0][0] == 1


@pytest.mark.parametrize("kind",["generation","outbox","reservation","payment"])
def test_critical_work_holds_erasure(case,kind):
    if kind in ("generation","outbox"):
        case.execute("INSERT INTO prostudio_generation_jobs(id,telegram_id,status) VALUES('job-a',%s,%s)",(U,"processing" if kind=="generation" else "completed"))
    if kind == "outbox":
        case.execute("INSERT INTO prostudio_media_outbox VALUES('job-a','pending')")
    if kind == "reservation":
        case.execute("INSERT INTO generation_reservations VALUES('job-a',%s,'reserved',20)",(U,))
    if kind == "payment":
        case.execute("INSERT INTO payment_inbox VALUES('synthetic-charge',%s,'pending')",(U,))
    reply = case.accept()
    plan = erasure.plan_request("synthetic-only",reply["request_id"],storage=FakeStorage(),journal=case.journal)
    assert plan["state"] == "waiting_work" and not plan["complete"]
    assert case.execute("SELECT balance FROM users WHERE telegram_id=%s",(U,))[0][0] == 1234


def test_new_job_after_request_is_refused_but_old_job_can_settle(case):
    case.execute("INSERT INTO prostudio_generation_jobs(id,telegram_id,status) VALUES('existing',%s,'processing')",(U,))
    case.accept()
    with pytest.raises(psycopg2.Error,match="account_erasure_in_progress"):
        case.execute("INSERT INTO prostudio_generation_jobs(id,telegram_id,status) VALUES('new',%s,'queued')",(U,))
    case.execute("UPDATE prostudio_generation_jobs SET status='completed' WHERE id='existing'")
    assert case.execute("SELECT status FROM prostudio_generation_jobs WHERE id='existing'")[0][0] == "completed"


def test_late_private_write_is_refused_and_other_account_is_unaffected(case):
    reply = case.accept()
    case.execute("UPDATE sylvex_erasure_requests SET state='purging' WHERE request_id=%s",(reply["request_id"],))
    with pytest.raises(psycopg2.Error,match="account_erasure_in_progress"):
        case.execute("INSERT INTO prostudio_messages(telegram_id,prompt) VALUES(%s,'late private output')",(U,))
    case.execute("INSERT INTO prostudio_messages(telegram_id,prompt) VALUES(%s,'other account output')",(V,))
    assert case.execute("SELECT telegram_id FROM prostudio_messages") == [(V,)]


def test_payment_evidence_and_balance_settlement_remain_available(case):
    reply = case.accept()
    case.execute("UPDATE sylvex_erasure_requests SET state='purging' WHERE request_id=%s",(reply["request_id"],))
    case.execute("UPDATE users SET balance=balance+10 WHERE telegram_id=%s",(U,))
    case.execute("INSERT INTO purchases(telegram_id,credits,amount) VALUES(%s,10,1)",(U,))
    assert case.execute("SELECT balance FROM users WHERE telegram_id=%s",(U,))[0][0] == 1244


@pytest.mark.parametrize("value",[
    "https://media.example.invalid/api/public/storage/generated/images/a.png?sig=synthetic",
    "https://media.example.invalid/api/public/storage/generated%2Fimages%2Fa.png",
    "https://media.example.invalid/api/public/storage/generated%252Fimages%252Fa.png",
    '{"images":["https://media.example.invalid/generated/images/a.png"]}',
    "generated/images/a.png",
])
def test_reference_fence_recognizes_encoded_and_serialized_keys(case,value):
    rows = case.execute("SELECT sylvex_erasure_reference_keys(%s::jsonb)",(json.dumps({"source":value}),))
    assert "generated/images/a.png" in rows[0][0]


def test_deleted_object_cannot_gain_a_late_reference(case):
    reply = case.accept()
    case.execute("INSERT INTO sylvex_erasure_media(request_id,object_key,state,proof_kind) VALUES(%s,'generated/images/a.png','deleted','synthetic')",(reply["request_id"],))
    with pytest.raises(psycopg2.Error,match="erased_media_reference"):
        case.execute("INSERT INTO prostudio_messages(telegram_id,image_url) VALUES(%s,%s)",(V,"https://media.example.invalid/generated/images/a.png"))


def test_unproven_url_is_reviewed_not_assumed_owned(case):
    key = "generated/images/a.png"
    case.execute("INSERT INTO sylvex_storage_objects VALUES(%s,%s)",(key,"https://media.example.invalid/api/public/storage/"+key))
    case.execute("INSERT INTO prostudio_messages(telegram_id,image_url) VALUES(%s,%s)",(U,"https://media.example.invalid/api/public/storage/"+key))
    reply = case.accept()
    plan = erasure.plan_request("synthetic-only",reply["request_id"],storage=FakeStorage(),journal=case.journal)
    assert plan["state"] == "media_review" and plan["hold_code"] == "object_ownership_requires_review"
    assert case.execute("SELECT state FROM sylvex_erasure_media")[0][0] == "review"


def add_media(case, key, *, owner=U, user=U):
    url = "https://media.example.invalid/api/public/storage/" + key
    case.execute("INSERT INTO sylvex_storage_objects VALUES(%s,%s) ON CONFLICT DO NOTHING", (key,url))
    if owner:
        case.execute("INSERT INTO sylvex_storage_ownership(object_key,owner_key,source_kind) VALUES(%s,%s,'synthetic') ON CONFLICT DO NOTHING", (key,owner))
    case.execute("INSERT INTO prostudio_messages(telegram_id,prompt,image_url) VALUES(%s,'private fixture',%s)", (user,url))
    return url


def test_complete_erasure_removes_owned_work_balance_and_subscription_but_not_other_user(case):
    own, other = "generated/images/own.png", "generated/images/other.png"
    add_media(case,own);add_media(case,other,owner=V,user=V)
    store = FakeStorage([own,other])
    other_before = case.execute("SELECT telegram_id,balance,subscription FROM users WHERE telegram_id=%s",(V,))
    receipt = case.accept()
    result = runner.process_request("synthetic-only",receipt["request_id"],storage=store,journal=case.journal,apply=True)
    assert result["complete"] and result["state"] == "complete"
    assert store.objects == {other} and store.calls == [own]
    assert case.execute("SELECT telegram_id FROM prostudio_messages") == [(V,)]
    assert case.execute("SELECT account_id FROM account_emails") == [(B,)]
    # Owner decision 08.11: credits and subscription end with the account.
    assert case.execute("SELECT balance,subscription FROM users WHERE telegram_id=%s",(U,)) == [(0,'free')]
    assert case.execute("SELECT telegram_id,balance,subscription FROM users WHERE telegram_id=%s",(V,)) == other_before
    assert case.execute("SELECT COUNT(*) FROM purchases")[0][0] == 2
    assert case.execute("SELECT username,first_name FROM users WHERE telegram_id=%s",(U,)) == [(None,None)]
    assert case.journal.read(receipt["request_id"])["completed_at"]


def test_default_plan_never_deletes_data_or_objects(case):
    key = "generated/images/own.png";add_media(case,key)
    store = FakeStorage([key]);receipt = case.accept()
    result = runner.process_request("synthetic-only",receipt["request_id"],storage=store,journal=case.journal)
    assert not result["complete"] and store.calls == [] and store.objects == {key}
    assert case.execute("SELECT COUNT(*) FROM prostudio_messages")[0][0] == 1


def test_shared_reference_preserves_file_and_other_users_work(case):
    key = "generated/images/shared.png"
    url = add_media(case,key)
    case.execute("INSERT INTO prostudio_resources(telegram_id,photos_json) VALUES(%s,%s)",(V,json.dumps([url])))
    store = FakeStorage([key]);receipt = case.accept()
    result = runner.process_request("synthetic-only",receipt["request_id"],storage=store,journal=case.journal,apply=True)
    assert result["complete"] and store.calls == [] and store.objects == {key}
    assert case.execute("SELECT telegram_id,photos_json FROM prostudio_resources") == [(V,json.dumps([url]))]
    assert case.execute("SELECT state FROM sylvex_erasure_media") == [("shared",)]


def test_other_recorded_owner_is_never_overridden(case):
    key = "generated/images/other.png";add_media(case,key,owner=V)
    store = FakeStorage([key]);receipt = case.accept()
    result = runner.process_request("synthetic-only",receipt["request_id"],storage=store,journal=case.journal,apply=True)
    assert result["complete"] and store.calls == []
    assert case.execute("SELECT owner_key FROM sylvex_storage_ownership") == [(V,)]


def test_unproven_ownership_stops_apply_until_an_explicit_review(case):
    key = "generated/images/legacy.png";add_media(case,key,owner=None)
    store = FakeStorage([key]);receipt = case.accept()
    result = runner.process_request("synthetic-only",receipt["request_id"],storage=store,journal=case.journal,apply=True)
    assert result["state"] == "media_review" and not result["complete"] and not store.calls
    runner.approve_media_ownership("synthetic-only",receipt["request_id"],key,proof_kind="verified_upload_record",reviewed_by="synthetic-operator")
    result = runner.process_request("synthetic-only",receipt["request_id"],storage=store,journal=case.journal,apply=True)
    assert result["complete"] and store.calls == [key]


def test_media_timeout_keeps_manifest_and_private_rows_for_retry(case):
    key = "generated/images/own.png";add_media(case,key)
    store = FakeStorage([key]);store.fail_delete.add(key);receipt = case.accept()
    result = runner.process_request("synthetic-only",receipt["request_id"],storage=store,journal=case.journal,apply=True)
    assert not result["complete"] and result["hold_code"] == "media_retry_required"
    assert case.execute("SELECT state,attempts FROM sylvex_erasure_media") == [("owned",1)]
    assert case.execute("SELECT COUNT(*) FROM prostudio_messages")[0][0] == 1
    assert not case.journal.read(receipt["request_id"])["completed_at"]
    store.fail_delete.clear()
    result = runner.process_request("synthetic-only",receipt["request_id"],storage=store,journal=case.journal,apply=True)
    assert result["complete"] and store.objects == set()


def test_head_access_denied_is_not_false_absence(case):
    key = "generated/images/own.png";add_media(case,key)
    store = FakeStorage([key]);store.fail_head.add(key);receipt = case.accept()
    result = runner.process_request("synthetic-only",receipt["request_id"],storage=store,journal=case.journal,apply=True)
    assert not result["complete"] and result["hold_code"] == "media_retry_required"
    assert case.execute("SELECT state FROM sylvex_erasure_requests") == [("purging",)]
    assert case.execute("SELECT COUNT(*) FROM account_emails")[0][0] == 2
    store.fail_head.clear()
    assert runner.process_request("synthetic-only",receipt["request_id"],storage=store,journal=case.journal,apply=True)["complete"]


def test_repeat_completed_request_never_deletes_twice(case):
    key = "generated/images/own.png";add_media(case,key)
    store = FakeStorage([key]);receipt = case.accept()
    first = runner.process_request("synthetic-only",receipt["request_id"],storage=store,journal=case.journal,apply=True)
    second = runner.process_request("synthetic-only",receipt["request_id"],storage=store,journal=case.journal,apply=True)
    assert first == second and store.calls == [key]


def test_billed_job_retains_only_minimal_accounting_evidence(case):
    case.execute("INSERT INTO prostudio_generation_jobs(id,telegram_id,status,cost,prompt,request_json,result_json) "
                 "VALUES('paid-job',%s,'completed',7,'private prompt','{\"input\":\"private\"}','{\"text\":\"private result\"}')",(U,))
    receipt = case.accept()
    result = runner.process_request("synthetic-only",receipt["request_id"],storage=FakeStorage(),journal=case.journal,apply=True)
    assert result["complete"]
    assert case.execute("SELECT id,cost,prompt,request_json,result_json FROM prostudio_generation_jobs") == [("paid-job",7,"",{}, {})]


def test_db_failure_after_object_delete_does_not_lose_manifest_or_claim_complete(case,monkeypatch):
    key = "generated/images/own.png";add_media(case,key)
    store = FakeStorage([key]);receipt = case.accept()
    real = runner._purge_personal
    def interrupted(cur,schema,request):
        real(cur,schema,request)
        raise RuntimeError("synthetic transaction failure")
    monkeypatch.setattr(runner,"_purge_personal",interrupted)
    with pytest.raises(RuntimeError,match="synthetic transaction failure"):
        runner.process_request("synthetic-only",receipt["request_id"],storage=store,journal=case.journal,apply=True)
    assert case.execute("SELECT state FROM sylvex_erasure_requests") == [("purging",)]
    assert case.execute("SELECT COUNT(*) FROM account_emails")[0][0] == 2
    assert case.execute("SELECT state FROM sylvex_erasure_media") == [("deleted",)]
    monkeypatch.setattr(runner,"_purge_personal",real)
    assert runner.process_request("synthetic-only",receipt["request_id"],storage=store,journal=case.journal,apply=True)["complete"]
    assert store.calls == [key]


def _restore_content(case,key):
    # Model an old SQL backup, with no erasure queue/ownership ledger in it.
    case.execute("TRUNCATE sylvex_erasure_retained_rows,sylvex_erasure_media,sylvex_erasure_requests,sylvex_storage_ownership,sylvex_active_operations")
    case.execute("INSERT INTO prostudio_messages(telegram_id,prompt,image_url) VALUES(%s,'restored old private output',%s)",
                 (U,'https://media.example.invalid/api/public/storage/'+key))


def test_restore_replays_completed_erasure_without_revealing_old_content(case):
    from services import account_erasure_restore as restore
    key='generated/restore-private.png'; store=FakeStorage([key])
    case.execute("INSERT INTO prostudio_messages(telegram_id,image_url) VALUES(%s,%s)",(U,'https://media.example.invalid/api/public/storage/'+key))
    case.execute("INSERT INTO sylvex_storage_ownership(object_key,owner_key,source_kind) VALUES(%s,%s,'fixture')",(key,U))
    request=case.accept()
    assert runner.process_request('synthetic-only',request['request_id'],storage=store,journal=case.journal,apply=True)['complete']
    _restore_content(case,key)
    assert not restore.readiness('synthetic-only',journal=case.journal)['ready']
    result=restore.replay('synthetic-only',storage=store,journal=case.journal,apply=True)
    assert result['ready'] and result['results'][0]['complete']
    assert not case.execute("SELECT 1 FROM prostudio_messages WHERE telegram_id=%s",(U,))
    assert case.execute("SELECT COUNT(*) FROM purchases")[0][0]==2
    assert erasure.pending_account('synthetic-only',A)


def test_restore_preserves_shared_decision_even_if_older_backup_lacks_reference(case):
    from services import account_erasure_restore as restore
    key='generated/shared-in-newer-snapshot.png';store=FakeStorage([key])
    for uid in (U,V):
        case.execute("INSERT INTO prostudio_messages(telegram_id,image_url) VALUES(%s,%s)",(uid,'https://media.example.invalid/api/public/storage/'+key))
    case.execute("INSERT INTO sylvex_storage_ownership VALUES(%s,%s,NOW(),'fixture')",(key,U))
    request=case.accept()
    assert runner.process_request('synthetic-only',request['request_id'],storage=store,journal=case.journal,apply=True)['complete']
    case.execute("DELETE FROM prostudio_messages WHERE telegram_id=%s",(V,))
    _restore_content(case,key)
    result=restore.replay('synthetic-only',storage=store,journal=case.journal,apply=True)
    assert result['ready'] and key in store.objects and not store.calls


def test_restore_reserves_account_missing_in_older_backup_and_advances_ids(case):
    from services import account_erasure_restore as restore
    case.execute("CREATE SEQUENCE sylvex_website_id_seq START 1;CREATE SEQUENCE sylvex_web_storage_seq START 900000000000")
    request=case.accept()
    assert runner.process_request('synthetic-only',request['request_id'],storage=FakeStorage(),journal=case.journal,apply=True)['complete']
    case.execute("TRUNCATE sylvex_erasure_retained_rows,sylvex_erasure_media,sylvex_erasure_requests")
    case.execute("DELETE FROM sylvex_accounts WHERE account_id=%s",(A,))
    result=restore.replay('synthetic-only',storage=FakeStorage(),journal=case.journal,apply=True)
    assert result['ready']
    assert case.execute("SELECT active_telegram_id FROM sylvex_accounts WHERE account_id=%s",(A,))==[(U,)]
    assert case.execute("SELECT nextval('sylvex_website_id_seq')")[0][0]>int(str(A)[8:])
    assert case.execute("SELECT nextval('sylvex_web_storage_seq')")[0][0]>U


def test_restore_unknown_new_owned_content_requires_review_before_reopening(case):
    from services import account_erasure_restore as restore
    request=case.accept()
    assert runner.process_request('synthetic-only',request['request_id'],storage=FakeStorage(),journal=case.journal,apply=True)['complete']
    _restore_content(case,'uploads/not-reviewed-in-journal.png')
    result=restore.replay('synthetic-only',storage=FakeStorage(),journal=case.journal,apply=True)
    assert not result['ready'] and result['results'][0]['hold_code']=='object_ownership_requires_review'
    assert case.execute("SELECT COUNT(*) FROM prostudio_messages WHERE telegram_id=%s",(U,))[0][0]==1


def test_journal_recovers_complete_append_after_checkpoint_crash(case,monkeypatch):
    request=case.accept();original=case.journal._write_record
    def fail_root(record):
        raise OSError('synthetic checkpoint crash')
    monkeypatch.setattr(case.journal,'_write_record',fail_root)
    with pytest.raises(OSError):
        case.journal.append_decision(request['request_id'],'generated/crash.png','delete')
    monkeypatch.setattr(case.journal,'_write_record',original)
    record=case.journal.recover(request['request_id'])
    assert record['decisions_count']==1
    assert len(case.journal.decisions(request['request_id']))==1


def test_journal_refuses_incomplete_append_instead_of_discarding_evidence(case):
    request=case.accept()
    target=case.journal.path/(request['request_id']+'.decisions')
    target.write_bytes(b'{"key_hash":"incomplete');target.chmod(0o600)
    with pytest.raises(erasure.ErasureError,match='erasure_journal_invalid'):
        case.journal.recover(request['request_id'])


def test_local_deletion_rejects_escape_and_symlink(case,tmp_path,monkeypatch):
    from types import SimpleNamespace
    root=tmp_path/'media';root.mkdir();(root/'generated').mkdir()
    outside=tmp_path/'keep.txt';outside.write_text('other file')
    (root/'generated'/'alias').symlink_to(outside)
    obj=runner.ObjectStore()
    monkeypatch.setattr(obj,'storage',SimpleNamespace(LOCAL_GENERATED_DIR=root/'generated',r2_enabled=lambda:False))
    for key in ('../keep.txt','/outside/file','generated/alias'):
        with pytest.raises((erasure.ErasureError,ValueError)):
            obj.absent(key)
    assert outside.read_text()=='other file'


def test_storage_intent_survives_upload_failure_and_holds_erasure(case,monkeypatch):
    from services.security import actor_id
    monkeypatch.setitem(globals(),'normalize_key',lambda key:key)
    monkeypatch.setitem(globals(),'DATABASE_URL','synthetic-only')
    def put_bytes(key,data):
        assert erasure.storage_registry_cursor() is not None
        raise TimeoutError('synthetic upload interruption')
    guarded=erasure.storage_write(put_bytes)
    token=actor_id.set(U)
    try:
        with pytest.raises(TimeoutError):guarded('generated/orphan-intent.png',b'fake')
    finally:actor_id.reset(token)
    assert case.execute("SELECT owner_key FROM sylvex_storage_ownership WHERE object_key='generated/orphan-intent.png'")==[(U,)]
    request=case.accept()
    result=erasure.plan_request('synthetic-only',request['request_id'],storage=FakeStorage(),journal=case.journal)
    assert result['hold_code']=='operation_in_flight'


def test_storage_operation_records_owner_and_finishes_without_nested_connection(case,monkeypatch):
    from services.security import actor_id
    monkeypatch.setitem(globals(),'normalize_key',lambda key:key)
    monkeypatch.setitem(globals(),'DATABASE_URL','synthetic-only')
    def put_bytes(key,data):
        cur=erasure.storage_registry_cursor()
        cur.execute("INSERT INTO sylvex_storage_objects VALUES(%s,%s)",(key,'https://media.example.invalid/api/public/storage/'+key))
        return 'stored'
    token=actor_id.set(U)
    try:
        assert erasure.storage_write(put_bytes)('generated/new-owned.png',b'fake')=='stored'
    finally:actor_id.reset(token)
    assert case.execute("SELECT owner_key FROM sylvex_storage_ownership WHERE object_key='generated/new-owned.png'")==[(U,)]
    assert case.execute("SELECT state FROM sylvex_active_operations")==[('finished',)]


def test_storage_adoption_does_not_claim_unproven_old_object(case,monkeypatch):
    from services.security import actor_id
    monkeypatch.setitem(globals(),'normalize_key',lambda key:key)
    monkeypatch.setitem(globals(),'DATABASE_URL','synthetic-only')
    def register_existing_object(key):return key
    token=actor_id.set(U)
    try:erasure.storage_write(register_existing_object)('uploads/unknown-old.png')
    finally:actor_id.reset(token)
    assert not case.execute("SELECT 1 FROM sylvex_storage_ownership")


def test_storage_new_write_refused_after_request_without_touching_object(case,monkeypatch):
    from services.security import actor_id
    monkeypatch.setitem(globals(),'normalize_key',lambda key:key)
    monkeypatch.setitem(globals(),'DATABASE_URL','synthetic-only')
    case.accept();calls=[]
    def put_bytes(key,data):calls.append(key)
    token=actor_id.set(U)
    try:
        with pytest.raises(erasure.ErasureError,match='account_erasure_in_progress'):
            erasure.storage_write(put_bytes)('generated/refused.png',b'fake')
    finally:actor_id.reset(token)
    assert calls==[]


def test_identity_delete_checks_confirmation_then_returns_pending_receipt(case,monkeypatch):
    from services import account_identity as ai
    monkeypatch.setattr(ai,'ensure_account_tables',lambda *a,**k:None)
    monkeypatch.setattr(ai,'db_connect',case.connect)
    case.execute("CREATE TABLE account_deletion_codes(account_id BIGINT PRIMARY KEY,confirm_hash TEXT,confirm_expires_at TIMESTAMPTZ)")
    with case.connect() as conn:
        with conn.cursor() as cur:guards.install(cur)
    token='synthetic-confirmation-token'
    case.execute("INSERT INTO account_deletion_codes VALUES(%s,%s,NOW()+INTERVAL '1 minute')",(A,ai._code_hash(token)))
    for supplied in (None,'wrong'):
        with pytest.raises(ai.AccountError,match='deletion_not_confirmed'):
            ai.delete_account('synthetic-only',A,supplied)
    assert not case.execute("SELECT 1 FROM sylvex_erasure_requests")
    result=ai.delete_account('synthetic-only',A,token)
    assert result['accepted'] and not result['complete']
    assert case.execute("SELECT COUNT(*) FROM account_emails")[0][0]==2
    assert ai.get_account_summary('synthetic-only',A) is None


def test_changed_owner_cannot_resurrect_erased_content(case):
    case.execute("INSERT INTO prostudio_messages(telegram_id,prompt) VALUES(%s,'private')",(U,))
    request=case.accept()
    case.execute("UPDATE sylvex_erasure_requests SET state='purging' WHERE request_id=%s",(request['request_id'],))
    with pytest.raises(psycopg2.Error,match='account_erasure_in_progress'):
        case.execute("UPDATE prostudio_messages SET telegram_id=%s WHERE telegram_id=%s",(V,U))


def test_account_identity_cannot_be_reissued_after_erasure(case):
    request=case.accept()
    assert runner.process_request('synthetic-only',request['request_id'],storage=FakeStorage(),journal=case.journal,apply=True)['complete']
    case.execute("DELETE FROM sylvex_accounts WHERE account_id=%s",(A,))
    with pytest.raises(psycopg2.Error,match='account_erasure_in_progress'):
        case.execute("INSERT INTO sylvex_accounts(account_id,active_telegram_id,origin) VALUES(%s,%s,'website')",(A,U))


def test_billing_scope_tracks_operation_without_changing_price_or_balance(case,monkeypatch):
    from services.billing_safety import billing_scope
    from services.security import actor_id
    monkeypatch.setenv('DATABASE_URL','synthetic-only')
    token=actor_id.set(U)
    try:
        with billing_scope('synthetic-priced-helper',17) as scope:
            assert scope['credits']==17
            assert case.execute("SELECT state FROM sylvex_active_operations WHERE generation_id='synthetic-priced-helper'")==[('active',)]
            request=case.accept()
            plan=erasure.plan_request('synthetic-only',request['request_id'],storage=FakeStorage(),journal=case.journal)
            assert plan['hold_code']=='operation_in_flight'
        assert case.execute("SELECT state FROM sylvex_active_operations WHERE generation_id='synthetic-priced-helper'")==[('finished',)]
        with pytest.raises(erasure.ErasureError,match='account_erasure_in_progress'):
            with billing_scope('new-after-erasure',17):pass
    finally:actor_id.reset(token)
    assert case.execute("SELECT balance FROM users WHERE telegram_id=%s",(U,))==[(1234,)]


def test_concurrent_foreign_reference_commits_before_object_deletion(case):
    from concurrent.futures import ThreadPoolExecutor
    import time
    key='generated/concurrent-shared.png';store=FakeStorage([key])
    case.execute("INSERT INTO sylvex_storage_ownership VALUES(%s,%s,NOW(),'fixture')",(key,U))
    request=case.accept()
    writer=case.connect();cur=writer.cursor()
    cur.execute("INSERT INTO prostudio_messages(telegram_id,image_url) VALUES(%s,%s)",(V,'https://media.example.invalid/api/public/storage/'+key))
    try:
        pool=ThreadPoolExecutor(max_workers=1)
        try:
            task=pool.submit(runner.process_request,'synthetic-only',request['request_id'],storage=store,journal=case.journal,apply=True)
            deadline=time.monotonic()+5
            while time.monotonic()<deadline:
                if case.execute("SELECT 1 FROM pg_locks WHERE locktype='advisory' AND classid=61184 AND NOT granted"):break
                if task.done():raise AssertionError('erasure passed an uncommitted shared reference')
                time.sleep(0.01)
            else:raise AssertionError('erasure did not reach the fenced object')
            assert not store.calls
            writer.commit()
            assert task.result(timeout=10)['complete']
        finally:
            writer.rollback()
            pool.shutdown(wait=True)
    finally:
        writer.rollback();cur.close();writer.close()
    assert key in store.objects and not store.calls


def test_late_foreign_reference_waits_then_refuses_deleted_key(case):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    key='generated/concurrent-deleted.png';entered,finish=Event(),Event()
    class PausedStore(FakeStorage):
        def delete(self,key):
            entered.set()
            assert finish.wait(10)
            super().delete(key)
    store=PausedStore([key])
    case.execute("INSERT INTO sylvex_storage_ownership VALUES(%s,%s,NOW(),'fixture')",(key,U))
    request=case.accept()
    with ThreadPoolExecutor(max_workers=2) as pool:
        task=pool.submit(runner.process_request,'synthetic-only',request['request_id'],storage=store,journal=case.journal,apply=True)
        assert entered.wait(10)
        writer=pool.submit(case.execute,"INSERT INTO prostudio_messages(telegram_id,image_url) VALUES(%s,%s)",(V,'https://media.example.invalid/api/public/storage/'+key))
        finish.set()
        assert task.result(timeout=10)['complete']
        with pytest.raises(psycopg2.Error,match='erased_media_reference'):writer.result(timeout=10)
    assert key not in store.objects


def test_delete_route_returns_202_receipt_and_clears_cookie_without_claiming_complete(monkeypatch):
    import ast,asyncio
    from fastapi import Request
    from starlette.responses import JSONResponse
    from types import SimpleNamespace
    tree=ast.parse((Path(__file__).parents[1]/'main.py').read_text())
    node=next(n for n in tree.body if isinstance(n,ast.AsyncFunctionDef) and n.name=='web_account_delete')
    node.decorator_list=[]
    async def account(request):return A
    class AccountError(Exception):pass
    reply={'accepted':True,'complete':False,'request_id':str(uuid4()),'state':'queued'}
    env={'Request':Request,'JSONResponse':JSONResponse,'asyncio':asyncio,'AccountError':AccountError,
         '_web_session_account_id':account,'DATABASE_URL':'synthetic-only',
         'account_identity_service':SimpleNamespace(delete_account=lambda *a:reply),
         'WEB_SESSION_COOKIE':'sylvex_web_session','WEB_SESSION_COOKIE_DOMAIN':None,
         '_ERASURE_WAKE':asyncio.Event()}
    exec(compile(ast.Module(body=[node],type_ignores=[]),'erasure-route-fixture','exec'),env)
    class FakeRequest:
        async def json(self):return {'confirm_token':'synthetic-only','erasure_scope':'web_account_content_v1'}
    response=asyncio.run(env['web_account_delete'](FakeRequest()))
    assert response.status_code==202
    assert json.loads(response.body)=={'ok':True,**reply}
    assert 'Max-Age=0' in response.headers['set-cookie']
    assert env['_ERASURE_WAKE'].is_set()  # the deletion starts right away


def test_reusable_direct_upload_holds_until_expiry_and_explicit_reconciliation(case):
    import time
    key='generated/direct-issued.png'
    erasure.register_direct_upload('synthetic-only',U,key,int(time.time())+900)
    erasure.finish_direct_upload('synthetic-only',U,key)
    request=case.accept()
    plan=erasure.plan_request('synthetic-only',request['request_id'],storage=FakeStorage(),journal=case.journal)
    assert plan['hold_code']=='direct_upload_capability_active'
    with pytest.raises(erasure.ErasureError,match='direct_upload_capability_active'):
        erasure.reconcile_direct_upload('synthetic-only',key,reviewed_by='test-operator',evidence_ref='fixture-quiescence')
    case.execute("UPDATE sylvex_direct_uploads SET expires_at=NOW()-INTERVAL '1 second'")
    plan=erasure.plan_request('synthetic-only',request['request_id'],storage=FakeStorage(),journal=case.journal)
    assert plan['hold_code']=='direct_upload_reconciliation_required'
    erasure.reconcile_direct_upload('synthetic-only',key,reviewed_by='test-operator',evidence_ref='fixture-quiescence')
    store=FakeStorage([key])
    assert runner.process_request('synthetic-only',request['request_id'],storage=store,journal=case.journal,apply=True)['complete']
    assert key not in store.objects


def test_legacy_unattributed_upload_inventory_is_not_assumed_complete(case):
    case.execute("UPDATE sylvex_accounts SET created_at='2020-01-01' WHERE account_id=%s",(A,))
    request=case.accept()
    result=runner.process_request('synthetic-only',request['request_id'],storage=FakeStorage(),journal=case.journal,apply=True)
    assert result['hold_code']=='legacy_media_inventory_requires_review' and not result['complete']
    erasure.approve_legacy_inventory('synthetic-only',request['request_id'],reviewed_by='test-operator',evidence_ref='fixture-inventory',journal=case.journal)
    result=runner.process_request('synthetic-only',request['request_id'],storage=FakeStorage(),journal=case.journal,apply=True)
    assert result['complete']


def test_missing_write_guard_is_refused_before_erasures_are_accepted(case):
    case.execute('DROP TRIGGER sylvex_erasure_guard ON prostudio_messages')
    with pytest.raises(erasure.ErasureError,match='erasure_guards_incomplete'):
        case.accept()
    assert not case.execute('SELECT 1 FROM sylvex_erasure_requests')


def _telegram_subject(case,monkeypatch):
    monkeypatch.setenv('SYLVEX_ERASURE_TELEGRAM_READY','1')
    uid=123456789
    case.execute("INSERT INTO users VALUES(%s,'fixture-tg','Telegram fixture',77,'starter')",(uid,))
    case.execute("UPDATE sylvex_accounts SET active_telegram_id=%s,storage_telegram_id=NULL,origin='telegram' WHERE account_id=%s",(uid,A))
    return uid


def _bot_root():
    root=os.environ.get('SYLVEX_BOT_REVIEW_ROOT')
    if not root:
        pytest.skip('Peer bot source is required for cross-service erasure regression')
    return Path(root)


def _bot_erasure(case,monkeypatch):
    import sys
    root=_bot_root()
    sys.path.insert(0,str(root))
    from app import account_erasure as bot_erasure
    monkeypatch.setattr(bot_erasure,'connect_db',case.connect)
    monkeypatch.setenv('SYLVEX_ERASURE_ENABLED','1')
    return bot_erasure


def test_telegram_request_refuses_unprepared_bot_client(case,monkeypatch):
    _telegram_subject(case,monkeypatch)
    monkeypatch.delenv('SYLVEX_ERASURE_TELEGRAM_READY',raising=False)
    with case.connect() as conn:
        with conn.cursor() as cur:
            with pytest.raises(erasure.ErasureError,match='erasure_telegram_client_not_ready'):
                erasure.accept_confirmed_request(cur,A,ecosystem='telegram',journal=case.journal)
    assert not case.execute('SELECT 1 FROM sylvex_erasure_requests')


def test_telegram_inflight_update_holds_erasure_until_cache_is_forgotten(case,monkeypatch):
    uid=_telegram_subject(case,monkeypatch);bot=_bot_erasure(case,monkeypatch)
    operation=bot.begin_update(uid,'synthetic-update-1')
    with case.connect() as conn:
        with conn.cursor() as cur:
            request=erasure.accept_confirmed_request(cur,A,ecosystem='telegram',journal=case.journal)
    assert case.execute('SELECT generation FROM sylvex_tg_session_revocations WHERE telegram_id=%s',(uid,))==[(1,)]
    cleared=[]
    bot.forget_pending(cleared.append)
    assert not cleared
    with pytest.raises(bot.ErasurePending):bot.begin_update(uid,'new-blocked')
    assert runner.process_request('synthetic-only',request['request_id'],storage=FakeStorage(),journal=case.journal,apply=True)['hold_code']=='telegram_cache_clear_pending'
    bot.finish_update(operation)
    bot.forget_pending(cleared.append)
    assert cleared==[uid]
    result=runner.process_request('synthetic-only',request['request_id'],storage=FakeStorage(),journal=case.journal,apply=True)
    assert result['complete']
    assert case.execute('SELECT balance FROM users WHERE telegram_id=%s',(uid,))==[(0,)]
    assert case.execute('SELECT balance FROM users WHERE telegram_id=%s',(U,))==[(1234,)]


def test_telegram_financial_delivery_and_data_rights_do_not_need_generation_access(case,monkeypatch):
    import asyncio
    from types import SimpleNamespace
    uid=_telegram_subject(case,monkeypatch);bot=_bot_erasure(case,monkeypatch)
    with case.connect() as conn:
        with conn.cursor() as cur:erasure.accept_confirmed_request(cur,A,ecosystem='telegram',journal=case.journal)
    calls=[];answers=[]
    async def handler(event,data):calls.append(event);return 'delivered'
    async def answer(*args,**kwargs):answers.append((args,kwargs))
    middleware=bot.ErasureMiddleware()
    message=SimpleNamespace(successful_payment=SimpleNamespace(currency='XTR'),from_user=SimpleNamespace(id=uid),text=None,answer=answer)
    event=SimpleNamespace(message=message,callback_query=None,pre_checkout_query=None,update_id=1)
    assert asyncio.run(middleware(handler,event,{}))=='delivered'
    message.successful_payment=None;message.text='/paysupport'
    assert asyncio.run(middleware(handler,event,{}))=='delivered'
    message.text='generate';asyncio.run(middleware(handler,event,{}))
    assert len(calls)==2 and 'support@sylvex.ai' in answers[-1][0][0]
    checkout=SimpleNamespace(from_user=SimpleNamespace(id=uid),answer=answer)
    event.message=None;event.pre_checkout_query=checkout
    asyncio.run(middleware(handler,event,{}))
    assert answers[-1][1]['ok'] is False and len(calls)==2


def test_telegram_upload_carries_only_verified_context_owner(case,monkeypatch):
    import sys
    from types import SimpleNamespace
    sys.path.insert(0,str(_bot_root()))
    from app import telegram_media
    from app.account_erasure import media_owner
    monkeypatch.setenv('WEBAPP_URL','https://telegram-media.example.invalid')
    monkeypatch.setenv('TELEGRAM_MEDIA_SERVICE_TOKEN','synthetic-media-token')
    calls=[]
    def post(url,**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(status_code=200,json=lambda:{'url':'https://telegram-media.example.invalid/api/public/storage/generated/telegram-inputs/test.png?media_exp=9999999999&media_sig='+'a'*64})
    monkeypatch.setattr(telegram_media.requests,'post',post)
    token=media_owner.set(123456789)
    try:telegram_media.upload_to_sylvex(b'fake','fixture.png','image/png')
    finally:media_owner.reset(token)
    assert calls[0]['headers']['X-Sylvex-Media-Owner']=='123456789'
    assert calls[0]['headers']['X-Sylvex-Media-Token']=='synthetic-media-token'


def test_telegram_cache_forgetting_is_scoped_including_group_message_cache():
    import ast
    tree=ast.parse((_bot_root()/'app/bot/main.py').read_text())
    node=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='forget_erased_user_cache')
    names={n.id for n in ast.walk(node) if isinstance(n,ast.Name)}-{'user_id','int','list','tuple','isinstance','mapping','key'}
    env={name:{123:'own',456:'other'} for name in names if name not in {'forget_erased_user_cache'}}
    env['message_edit_cache']={(-999,1):'own group message',(-999,2):'other group message',(123,3):'private'}
    env['message_edit_cache_owners']={(-999,1):123,(-999,2):456,(123,3):123}
    exec(compile(ast.Module(body=[node],type_ignores=[]),'forget-cache-fixture','exec'),env)
    env['forget_erased_user_cache'](123)
    assert env['message_edit_cache']=={(-999,2):'other group message'}
    assert env['users']=={456:'other'}


def test_pausing_intake_does_not_drop_guards_or_revoke_unconfirmed_accounts(case,monkeypatch):
    monkeypatch.setenv('SYLVEX_ERASURE_ACCEPTING','0')
    with pytest.raises(erasure.ErasureError,match='erasure_intake_not_ready'):case.accept()
    assert not case.execute('SELECT 1 FROM sylvex_erasure_requests')
    assert case.execute('SELECT session_generation FROM sylvex_accounts WHERE account_id=%s',(A,))==[(0,)]
    with case.connect() as conn:
        with conn.cursor() as cur:guards.require_installed(cur,verify_coverage=True)


def test_normal_bracketed_prompt_is_not_malformed_attachment_metadata(case):
    case.execute("INSERT INTO prostudio_messages(telegram_id,prompt) VALUES(%s,'[Portrait] natural lighting')",(U,))
    request=case.accept()
    assert runner.process_request('synthetic-only',request['request_id'],storage=FakeStorage(),journal=case.journal,apply=True)['complete']


@pytest.mark.parametrize('code,absent',[('NoSuchKey',True),('404',True),('AccessDenied',False),('503',False)])
def test_real_store_head_classifies_only_not_found_as_absence(case,monkeypatch,code,absent):
    from types import SimpleNamespace
    class HeadError(Exception):
        response={'Error':{'Code':code}}
    def head(**kwargs):raise HeadError()
    store=runner.ObjectStore()
    monkeypatch.setattr(store,'storage',SimpleNamespace(r2_enabled=lambda:True,R2_BUCKET='fake-bucket',r2_client=lambda:SimpleNamespace(head_object=head)))
    if absent:assert store.absent('generated/fixture.png')
    else:
        with pytest.raises(HeadError):store.absent('generated/fixture.png')


def test_legacy_pending_website_account_cannot_use_a_fresh_cookie_with_cached_uid(case,monkeypatch):
    import asyncio,httpx
    from fastapi import FastAPI
    from services import security
    case.execute("UPDATE sylvex_accounts SET active_telegram_id=123456789,merged_at=NOW() WHERE account_id=%s",(A,))
    request=case.accept()
    assert request['state']=='scope_review'
    monkeypatch.setenv('DATABASE_URL','synthetic-only')
    monkeypatch.setenv('WEB_SESSION_SECRET','synthetic-web-session-secret')
    monkeypatch.setenv('WEBSITE_ORIGINS','https://website.example.invalid')
    monkeypatch.setattr(security,'current_web_session_generation',lambda account:1)
    monkeypatch.setattr(security,'resolve_web_session_uid',lambda account:123456789)
    app=FastAPI();app.add_middleware(security.SecurityMiddleware)
    @app.get('/api/erasure-auth-probe')
    async def probe():return {'private':True}
    async def scenario():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='https://api.example.invalid') as client:
            return await client.get('/api/erasure-auth-probe',headers={'Cookie':'sylvex_web_session='+security.create_web_session_token(A,1)})
    result=asyncio.run(scenario())
    assert result.status_code==403 and result.json()['error']=='account_erasure_in_progress'
    # The unresolved website scope does not authorize erasing its Telegram id.
    erasure.check_subject_access('synthetic-only',123456789)


def test_other_account_history_reference_holds_owned_job_erasure(case):
    case.execute('CREATE TABLE prostudio_character_history(id BIGSERIAL PRIMARY KEY,telegram_id BIGINT,job_id TEXT)')
    with case.connect() as conn:
        with conn.cursor() as cur:guards.install(cur)
    case.execute("INSERT INTO prostudio_generation_jobs(id,telegram_id,status,cost) VALUES('shared-job',%s,'completed',0)",(U,))
    case.execute("INSERT INTO prostudio_character_history(telegram_id,job_id) VALUES(%s,'shared-job')",(V,))
    request=case.accept()
    result=runner.process_request('synthetic-only',request['request_id'],storage=FakeStorage(),journal=case.journal,apply=True)
    assert not result['complete'] and result['hold_code']=='job_in_use_by_other_account'
    assert case.execute("SELECT job_id FROM prostudio_character_history")==[('shared-job',)]


def test_already_reserved_assistant_worker_can_finish_after_request_but_new_one_is_refused(case,monkeypatch):
    from services.billing_safety import billing_scope
    from services.security import actor_id
    monkeypatch.setenv('DATABASE_URL','synthetic-only')
    case.execute('ALTER TABLE generation_reservations ADD COLUMN created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()')
    case.execute("INSERT INTO generation_reservations(generation_id,telegram_id,status,credits) VALUES('accepted-assistant',%s,'reserved',10)",(U,))
    request=case.accept()
    token=actor_id.set(0)
    try:
        with billing_scope('accepted-assistant',10):
            with erasure.subject_operation(U,'accepted-assistant'):
                assert actor_id.get()==U
                assert case.execute("SELECT state FROM sylvex_active_operations WHERE generation_id='accepted-assistant'")==[('active',)]
                assert erasure.plan_request('synthetic-only',request['request_id'],storage=FakeStorage(),journal=case.journal)['hold_code']=='operation_in_flight'
        assert actor_id.get()==0
        with pytest.raises(erasure.ErasureError,match='account_erasure_in_progress'):
            with erasure.subject_operation(U,'unaccepted-assistant'):pass
    finally:actor_id.reset(token)


def test_real_assistant_worker_binds_its_verified_owner_for_its_full_lifetime(case,monkeypatch):
    import ast,queue,threading
    from services.billing_safety import billing_scope
    from services.security import actor_id
    monkeypatch.setenv('DATABASE_URL','synthetic-only')
    tree=ast.parse((Path(__file__).parents[1]/'main.py').read_text())
    handler=next(n for n in tree.body if isinstance(n,ast.AsyncFunctionDef) and n.name=='web_assistant_message')
    node=next(n for n in ast.walk(handler) if isinstance(n,ast.FunctionDef) and n.name=='worker')
    def stream(*args,**kwargs):
        assert actor_id.get()==U
        assert case.execute("SELECT state FROM sylvex_active_operations WHERE generation_id='assistant-thread'")==[('active',)]
        yield 'synthetic result'
    output=queue.Queue()
    env={'telegram_id':U,'assistant_generation_id':'assistant-thread','stream_assistant_reply':stream,
         'OPENAI_API_KEY':'fake','OPENAI_API_BASE':'https://example.invalid','OPENAI_ASSISTANT_MODEL':'fake',
         'messages':[],'ASSISTANT_MAX_OUTPUT_TOKENS':10,'stream_usage':{},'stream_id':'fake',
         'q':output,'_ASSISTANT_STOP_LOCK':threading.Lock(),'_ASSISTANT_STOP_FLAGS':{}}
    exec(compile(ast.Module(body=[node],type_ignores=[]),'assistant-worker-fixture','exec'),env)
    token=actor_id.set(0)
    try:
        with billing_scope('assistant-thread',10):env['worker']()
        assert actor_id.get()==0
    finally:actor_id.reset(token)
    assert output.get_nowait()==('delta','synthetic result')
    assert output.get_nowait()==('done',None)
    assert case.execute("SELECT state FROM sylvex_active_operations WHERE generation_id='assistant-thread'")==[('finished',)]


@pytest.mark.parametrize('endpoint',['web_account_delete_start','web_account_delete'])
def test_old_login_only_delete_client_cannot_request_full_content_erasure(endpoint):
    import ast,asyncio
    from fastapi import Request
    from starlette.responses import JSONResponse
    from types import SimpleNamespace
    tree=ast.parse((Path(__file__).parents[1]/'main.py').read_text())
    node=next(n for n in tree.body if isinstance(n,ast.AsyncFunctionDef) and n.name==endpoint)
    node.decorator_list=[]
    async def account(request):return A
    def forbidden(*args,**kwargs):raise AssertionError('Old scope must not email a code or queue full erasure')
    class AccountError(Exception):pass
    env={'Request':Request,'JSONResponse':JSONResponse,'asyncio':asyncio,'AccountError':AccountError,
         '_web_session_account_id':account,'DATABASE_URL':'synthetic-only',
         'account_identity_service':SimpleNamespace(delete_account=forbidden,start_account_deletion=forbidden)}
    exec(compile(ast.Module(body=[node],type_ignores=[]),'old-delete-client-fixture','exec'),env)
    class OldRequest:
        async def json(self):return {'confirm_token':'previous-login-only-confirmation'}
    response=asyncio.run(env[endpoint](OldRequest()))
    assert response.status_code==409
    assert json.loads(response.body)['error']=='erasure_scope_confirmation_required'


@pytest.mark.parametrize('proven',[True,False])
def test_metadata_committed_between_plan_and_freeze_is_not_lost(case,monkeypatch,proven):
    key='generated/late-before-freeze.png';store=FakeStorage([key]);request=case.accept()
    original=erasure.plan_request;calls=[]
    def interleaved(*args,**kwargs):
        reply=original(*args,**kwargs)
        if not calls:
            case.execute("INSERT INTO prostudio_messages(telegram_id,image_url) VALUES(%s,%s)",(U,'https://media.example.invalid/api/public/storage/'+key))
            if proven:
                case.execute("INSERT INTO sylvex_storage_ownership VALUES(%s,%s,NOW(),'fixture')",(key,U))
        calls.append(True)
        return reply
    monkeypatch.setattr(erasure,'plan_request',interleaved)
    result=runner.process_request('synthetic-only',request['request_id'],storage=store,journal=case.journal,apply=True)
    if proven:
        assert result['complete'] and store.calls==[key] and key not in store.objects
    else:
        assert not result['complete'] and result['hold_code']=='object_ownership_requires_review'
        assert key in store.objects and not store.calls
        assert case.execute('SELECT COUNT(*) FROM prostudio_messages WHERE telegram_id=%s',(U,))==[(1,)]


def test_manifest_streams_more_than_one_batch_and_preserves_other_user(case):
    keys=['generated/batch/'+str(n)+'.png'for n in range(207)]
    for key in keys:
        case.execute("INSERT INTO sylvex_storage_ownership VALUES(%s,%s,NOW(),'fixture')",(key,U))
    case.execute("INSERT INTO prostudio_messages(telegram_id,prompt) SELECT %s,'synthetic '||n FROM generate_series(1,207) n",(U,))
    case.execute("INSERT INTO prostudio_messages(telegram_id,prompt) VALUES(%s,'keep')",(V,))
    request=case.accept();plan=erasure.plan_request('synthetic-only',request['request_id'],storage=FakeStorage(keys),journal=case.journal)
    assert not plan['hold_code']
    assert case.execute('SELECT COUNT(*) FROM sylvex_erasure_media WHERE request_id=%s',(request['request_id'],))==[(207,)]
    assert case.execute('SELECT COUNT(*) FROM prostudio_messages WHERE telegram_id=%s',(V,))==[(1,)]


def test_nullable_alternative_owner_column_does_not_hide_another_users_reference(case):
    key='generated/nullable-shared.png';store=FakeStorage([key])
    case.execute('CREATE TABLE project_reviews(id BIGSERIAL PRIMARY KEY,account_id BIGINT,user_key BIGINT,image_url TEXT)')
    with case.connect() as conn:
        with conn.cursor() as cur:guards.install(cur)
    case.execute("INSERT INTO project_reviews(account_id,user_key,image_url) VALUES(NULL,%s,%s)",(V,'https://media.example.invalid/api/public/storage/'+key))
    case.execute("INSERT INTO sylvex_storage_ownership VALUES(%s,%s,NOW(),'fixture')",(key,U))
    request=case.accept()
    assert runner.process_request('synthetic-only',request['request_id'],storage=store,journal=case.journal,apply=True)['complete']
    assert key in store.objects and not store.calls
    assert case.execute('SELECT user_key FROM project_reviews')==[(V,)]


def test_lost_external_journal_refuses_readiness_even_when_sql_tombstone_exists(case):
    from services import account_erasure_restore as restore
    request=case.accept()
    assert runner.process_request('synthetic-only',request['request_id'],storage=FakeStorage(),journal=case.journal,apply=True)['complete']
    (case.journal.path/(request['request_id']+'.json')).unlink()
    state=restore.readiness('synthetic-only',journal=case.journal)
    assert not state['ready'] and state['holds'][0]['hold_code']=='erasure_journal_missing_or_mismatched'


@pytest.mark.parametrize('status,secret',[('active',None),('disabled','synthetic-opaque-value')])
def test_staff_privileges_or_second_factor_prevent_false_erasure_completion(case,status,secret):
    case.execute('CREATE TABLE admin_accounts(id BIGSERIAL PRIMARY KEY,account_id BIGINT,status TEXT,totp_secret_enc TEXT)')
    case.execute('INSERT INTO admin_accounts(account_id,status,totp_secret_enc) VALUES(%s,%s,%s)',(A,status,secret))
    with case.connect() as conn:
        with conn.cursor() as cur:guards.install(cur)
    request=case.accept()
    result=runner.process_request('synthetic-only',request['request_id'],storage=FakeStorage(),journal=case.journal,apply=True)
    assert not result['complete'] and result['hold_code']=='privileged_access_requires_review'
    assert case.execute('SELECT COUNT(*) FROM account_emails WHERE account_id=%s',(A,))==[(1,)]



# ---------------------------------------------------------------------------
# B09 self-service (owner decision 08.11): the user's confirmation alone runs
# the erasure; renewal stops, wallet and subscription end, and only the
# confirming account is touched.
# ---------------------------------------------------------------------------

class FakeStripe:
    def __init__(self, missing=(), fail=()):
        self.calls, self.missing, self.fail = [], set(missing), set(fail)

    def request(self, method, path, params=None, idempotency_key=None):
        self.calls.append((method, path))
        sid = path.rsplit("/", 1)[-1]
        if sid in self.fail:
            raise RuntimeError("synthetic stripe outage")
        if sid in self.missing:
            error = RuntimeError("No such subscription"); error.status = 404; raise error
        return {"id": sid, "status": "canceled"}


def _wallets_and_stripe(case):
    case.execute("""CREATE TABLE user_credit_wallets(telegram_id BIGINT PRIMARY KEY,purchased_credits INTEGER,
                    subscription_credits INTEGER,subscription_expires_at TIMESTAMPTZ)""")
    case.execute("INSERT INTO user_credit_wallets VALUES(%s,500,300,NOW()+INTERVAL '20 days'),(%s,40,0,NULL)",(U,V))
    case.execute("""CREATE TABLE stripe_subscriptions(subscription_id TEXT PRIMARY KEY,telegram_id BIGINT NOT NULL,
                    status TEXT NOT NULL,cancel_at_period_end BOOLEAN NOT NULL DEFAULT FALSE)""")
    case.execute("INSERT INTO stripe_subscriptions VALUES('sub_own','%s'::bigint,'active',FALSE),"
                 "('sub_old','%s'::bigint,'canceled',FALSE),('sub_other','%s'::bigint,'active',FALSE)" % (U,U,V))
    case.execute("CREATE TABLE subscriptions(id BIGSERIAL PRIMARY KEY,telegram_id BIGINT NOT NULL,status TEXT)")
    case.execute("INSERT INTO subscriptions(telegram_id,status) VALUES(%s,'active'),(%s,'active')",(U,V))


def test_self_service_pass_cancels_renewal_and_ends_wallet_only_for_the_confirming_account(case):
    _wallets_and_stripe(case)
    key = "generated/images/own.png"; add_media(case, key)
    store, stripe = FakeStorage([key]), FakeStripe()
    receipt = case.accept()
    results = runner.process_pending("synthetic-only", storage=store, journal=case.journal, stripe=stripe)
    assert results == [{"request_id": receipt["request_id"], "complete": True, "state": "complete", "hold_code": "",
                        "media": {"deleted:recorded_owner": 1}}]
    assert stripe.calls == [("DELETE", "/subscriptions/sub_own")]
    assert case.execute("SELECT subscription_id,status FROM stripe_subscriptions ORDER BY 1") == [
        ("sub_old","canceled"), ("sub_other","active"), ("sub_own","canceled")]
    assert case.execute("SELECT telegram_id FROM user_credit_wallets") == [(V,)]
    assert case.execute("SELECT telegram_id,status FROM subscriptions ORDER BY telegram_id") == [(U,"canceled"),(V,"active")]
    assert case.execute("SELECT balance,subscription FROM users WHERE telegram_id=%s",(U,)) == [(0,"free")]
    assert case.execute("SELECT balance,subscription FROM users WHERE telegram_id=%s",(V,)) == [(5678,"pro")]
    assert store.objects == set() and case.execute("SELECT COUNT(*) FROM purchases")[0][0] == 2
    # A second pass has nothing left to do and contacts nobody.
    assert runner.process_pending("synthetic-only", storage=store, journal=case.journal, stripe=stripe) == []
    assert len(stripe.calls) == 1


def test_stripe_outage_holds_erasure_and_retries_without_losing_data(case):
    _wallets_and_stripe(case)
    receipt = case.accept()
    down = FakeStripe(fail={"sub_own"})
    [result] = runner.process_pending("synthetic-only", storage=FakeStorage(), journal=case.journal, stripe=down)
    assert result["hold_code"] == "renewal_cancel_retry" and not result["complete"]
    assert case.execute("SELECT COUNT(*) FROM user_credit_wallets WHERE telegram_id=%s",(U,))[0][0] == 1
    [result] = runner.process_pending("synthetic-only", storage=FakeStorage(), journal=case.journal, stripe=FakeStripe(missing={"sub_own"}))
    assert result["complete"] and result["request_id"] == receipt["request_id"]


def test_new_registration_after_erasure_starts_empty(case):
    _wallets_and_stripe(case)
    case.accept()
    runner.process_pending("synthetic-only", storage=FakeStorage(), journal=case.journal, stripe=FakeStripe())
    # The old e-mail is free again; a new account gets a new id and storage key.
    assert case.execute("SELECT COUNT(*) FROM account_emails WHERE email='a@example.invalid'")[0][0] == 0
    new_account, new_uid = 110626990001, 900000009999
    case.execute("INSERT INTO sylvex_accounts(account_id,active_telegram_id,storage_telegram_id,origin) VALUES(%s,%s,%s,'website')",
                 (new_account,new_uid,new_uid))
    case.execute("INSERT INTO account_emails VALUES(%s,'a@example.invalid','new-hash')",(new_account,))
    case.execute("INSERT INTO users(telegram_id,balance,subscription) VALUES(%s,0,'free')",(new_uid,))
    assert case.execute("SELECT COUNT(*) FROM user_credit_wallets WHERE telegram_id=%s",(new_uid,))[0][0] == 0
    assert case.execute("SELECT COUNT(*) FROM prostudio_messages WHERE telegram_id=%s",(new_uid,))[0][0] == 0


def test_unusable_runtime_disables_erasure_instead_of_stopping_the_service(case, monkeypatch):
    monkeypatch.setenv("SYLVEX_ERASURE_ENABLED","1")
    monkeypatch.setattr(erasure, "validate_runtime", lambda url: (_ for _ in ()).throw(erasure.ErasureError("erasure_restore_replay_required",503)))
    status = erasure.activate_runtime("synthetic-only")
    try:
        assert status == {"enabled": False, "configured": True, "error": "erasure_restore_replay_required"}
        assert not erasure.enabled()
        with case.connect() as conn:
            with conn.cursor() as cur:
                with pytest.raises(erasure.ErasureError, match="erasure_intake_not_ready"):
                    erasure.accept_confirmed_request(cur, A, journal=case.journal)
    finally:
        erasure._RUNTIME_BLOCK = ""


def test_new_tables_are_classified_so_erasure_is_not_held(case):
    for table in ("user_credit_wallets","bot_generation_operations","financial_review_cases","payment_refund_requests"):
        assert table in (policy.FINANCIAL | policy.SPECIAL), table
    case.execute("CREATE TABLE bot_generation_operations(operation_id TEXT PRIMARY KEY,telegram_id BIGINT,status TEXT)")
    case.execute("INSERT INTO bot_generation_operations VALUES('op1',%s,'settled')",(U,))
    _wallets_and_stripe(case)
    case.accept()
    [result] = runner.process_pending("synthetic-only", storage=FakeStorage(), journal=case.journal, stripe=FakeStripe())
    assert result["complete"], result
    assert case.execute("SELECT COUNT(*) FROM bot_generation_operations")[0][0] == 1


def test_fences_alone_never_process_earlier_requests(case, monkeypatch):
    receipt = case.accept()
    monkeypatch.delenv("SYLVEX_ERASURE_ACCEPTING")
    assert runner.process_pending("synthetic-only", storage=FakeStorage(), journal=case.journal, stripe=FakeStripe()) == []
    assert case.execute("SELECT state FROM sylvex_erasure_requests WHERE request_id=%s",(receipt["request_id"],)) == [("queued",)]
    assert case.execute("SELECT COUNT(*) FROM account_emails WHERE account_id=%s",(A,))[0][0] == 1


def test_activation_reports_request_counts_without_ids(case, monkeypatch):
    case.accept()
    monkeypatch.setattr(erasure, "validate_runtime", lambda url: None)
    status = erasure.activate_runtime("synthetic-only")
    assert status["enabled"] and status["requests_by_state"] == {"queued": 1}
    assert "request_id" not in json.dumps(status)


def _legacy_account_with_unrecorded_media(case):
    # An account created before ownership recording; its generation and its
    # uploaded reference were written without an ownership record (B09 test
    # account: workers on older code, account older than the runtime).
    case.execute("UPDATE sylvex_accounts SET created_at='2020-01-01' WHERE account_id=%s",(A,))
    own_result, own_upload = "generated/images/legacy-result.png", "generated/references/legacy-ref.png"
    add_media(case,own_result,owner=None);add_media(case,own_upload,owner=None)
    return own_result, own_upload


def test_self_service_completes_a_legacy_account_held_for_inventory_review(case):
    own_result, own_upload = _legacy_account_with_unrecorded_media(case)
    other = "generated/images/other-user.png"; add_media(case,other,owner=None,user=V)
    store = FakeStorage([own_result,own_upload,other])
    receipt = case.accept()
    # The request as Production holds it: planned once by the earlier
    # processor and left in scope_review with the legacy inventory hold.
    held = runner.process_request("synthetic-only",receipt["request_id"],storage=store,journal=case.journal,apply=True)
    assert held["state"] == "scope_review" and held["hold_code"] == "legacy_media_inventory_requires_review"
    assert not store.calls
    [result] = runner.process_pending("synthetic-only", storage=store, journal=case.journal, stripe=FakeStripe())
    assert result["complete"] and result["hold_code"] == "", result
    assert result["media"] == {"deleted:account_reference": 2}
    assert sorted(store.calls) == sorted([own_result,own_upload]) and store.objects == {other}
    assert case.execute("SELECT COUNT(*) FROM prostudio_messages WHERE telegram_id=%s",(U,))[0][0] == 0
    assert case.execute("SELECT COUNT(*) FROM prostudio_messages WHERE telegram_id=%s",(V,))[0][0] == 1
    assert case.execute("SELECT balance,subscription FROM users WHERE telegram_id=%s",(U,)) == [(0,"free")]
    assert case.execute("SELECT balance,subscription FROM users WHERE telegram_id=%s",(V,)) == [(5678,"pro")]
    record = case.journal.read(receipt["request_id"])
    assert record["completed_at"] and record["inventory_evidence_sha256"]


def test_self_service_keeps_a_key_another_account_also_references(case):
    _legacy_account_with_unrecorded_media(case)
    shared = "generated/images/shared.png"
    add_media(case,shared,owner=None); add_media(case,shared,owner=None,user=V)
    store = FakeStorage([shared,"generated/images/legacy-result.png","generated/references/legacy-ref.png"])
    case.accept()
    [result] = runner.process_pending("synthetic-only", storage=store, journal=case.journal, stripe=FakeStripe())
    assert result["complete"] and result["media"] == {"deleted:account_reference": 2, "shared:other_reference": 1}
    assert shared in store.objects and shared not in store.calls
    assert case.execute("SELECT COUNT(*) FROM prostudio_messages WHERE telegram_id=%s",(V,))[0][0] == 1


def test_self_service_never_deletes_keys_outside_application_media(case):
    case.execute("UPDATE sylvex_accounts SET created_at='2020-01-01' WHERE account_id=%s",(A,))
    foreign = "assets/site/brand.png"; add_media(case,foreign,owner=None)
    store = FakeStorage([foreign])
    case.accept()
    [result] = runner.process_pending("synthetic-only", storage=store, journal=case.journal, stripe=FakeStripe())
    assert result["complete"] and result["media"] == {"shared:unattributed_retained": 1}
    assert store.objects == {foreign} and not store.calls


def test_self_service_recorded_other_owner_is_kept(case):
    _legacy_account_with_unrecorded_media(case)
    theirs = "generated/images/theirs.png"; add_media(case,theirs,owner=V)
    store = FakeStorage([theirs,"generated/images/legacy-result.png","generated/references/legacy-ref.png"])
    case.accept()
    [result] = runner.process_pending("synthetic-only", storage=store, journal=case.journal, stripe=FakeStripe())
    assert result["complete"] and theirs in store.objects and theirs not in store.calls
    assert case.execute("SELECT owner_key FROM sylvex_storage_ownership WHERE object_key=%s",(theirs,)) == [(V,)]


def test_operator_path_still_requires_explicit_reviews(case):
    _legacy_account_with_unrecorded_media(case)
    receipt = case.accept()
    store = FakeStorage(["generated/images/legacy-result.png","generated/references/legacy-ref.png"])
    result = runner.process_request("synthetic-only",receipt["request_id"],storage=store,journal=case.journal,apply=True)
    assert result["hold_code"] == "legacy_media_inventory_requires_review" and not store.calls
    erasure.approve_legacy_inventory("synthetic-only",receipt["request_id"],reviewed_by="op",evidence_ref="ref",journal=case.journal)
    result = runner.process_request("synthetic-only",receipt["request_id"],storage=store,journal=case.journal,apply=True)
    assert result["hold_code"] == "object_ownership_requires_review" and not store.calls


def test_a_persisting_hold_is_logged_once(case, monkeypatch):
    import ast, asyncio as aio
    tree = ast.parse((Path(__file__).parents[1]/'main.py').read_text())
    keep = [n for n in tree.body if (isinstance(n,ast.AsyncFunctionDef) and n.name=='_run_account_erasure_once')
            or (isinstance(n,ast.Assign) and any(getattr(t,'id','')=='_ERASURE_LAST_LOGGED' for t in n.targets))]
    printed = []
    held = [{"request_id":"r1","complete":False,"state":"waiting_work","hold_code":"generation_in_flight","media":{}}]
    fake = SimpleNamespace(enabled=lambda: True)
    fake_runner = SimpleNamespace(process_pending=lambda url: held)
    import services
    monkeypatch.setattr(services, "account_erasure", fake, raising=False)
    monkeypatch.setattr(services, "account_erasure_runner", fake_runner, raising=False)
    monkeypatch.setitem(sys.modules, "services.account_erasure", fake)
    monkeypatch.setitem(sys.modules, "services.account_erasure_runner", fake_runner)
    env = {"asyncio": aio, "json": json, "DATABASE_URL": "synthetic-only", "print": lambda *a, **k: printed.append(a)}
    exec(compile(ast.Module(body=keep,type_ignores=[]),'erasure-log-fixture','exec'),env)
    for _ in range(3):
        aio.run(env["_run_account_erasure_once"]())
    assert len(printed) == 1
    held[0] = {**held[0], "state": "complete", "complete": True, "hold_code": ""}
    aio.run(env["_run_account_erasure_once"]())
    assert len(printed) == 2


def _inline_image(size):
    import base64
    return "data:image/png;base64," + base64.b64encode(bytes(range(256)) * (size // 256)).decode()


def test_inline_base64_in_another_accounts_job_does_not_stop_erasure(case):
    # B09 Production: another account's job row holds a large data URL; the
    # suffix expansion of its '/'-rich base64 exceeded PostgreSQL's 1 GB array
    # limit (ProgramLimitExceeded) on every pass.
    own_result, own_upload = _legacy_account_with_unrecorded_media(case)
    blob = _inline_image(3_000_000)
    case.execute("INSERT INTO prostudio_generation_jobs(id,telegram_id,status,request_json) VALUES('other-inline',%s,'completed',%s)",
                 (V, json.dumps({"image": blob, "note": "see https://media.example.invalid/api/public/storage/generated/images/kept.png"})))
    store = FakeStorage([own_result, own_upload])
    case.accept()
    [result] = runner.process_pending("synthetic-only", storage=store, journal=case.journal, stripe=FakeStripe())
    assert result["complete"], result
    assert case.execute("SELECT COUNT(*) FROM prostudio_generation_jobs WHERE id='other-inline'")[0][0] == 1


def test_reference_fence_is_bounded_but_still_finds_keys_next_to_inline_data(case):
    blob = _inline_image(3_000_000)
    text = "result " + blob + " and https://media.example.invalid/api/public/storage/generated/images/a.png done"
    keys = case.execute("SELECT sylvex_erasure_reference_keys(%s::jsonb)", (json.dumps({"source": text}),))[0][0]
    assert "generated/images/a.png" in keys and all(len(key) <= 2048 for key in keys)
    # The write fence on an ordinary row with inline data still accepts it.
    case.execute("INSERT INTO prostudio_messages(telegram_id,prompt,image_url) VALUES(%s,%s,%s)", (V, blob, blob))


def test_activation_brings_installed_guard_functions_to_this_release(case, monkeypatch):
    # Guards installed by an earlier release keep their triggers; startup
    # replaces the function bodies so the bounded version is what runs.
    case.execute("CREATE OR REPLACE FUNCTION sylvex_erasure_reference_keys(document JSONB, nesting INTEGER DEFAULT 0) "
                 "RETURNS TEXT[] LANGUAGE sql IMMUTABLE AS $$ SELECT ARRAY['stale-release']::TEXT[] $$")
    monkeypatch.setattr(erasure, "validate_runtime", lambda url: None)
    status = erasure.activate_runtime("synthetic-only")
    assert status["enabled"] and not status["guards_installed_now"]
    keys = case.execute("SELECT sylvex_erasure_reference_keys(%s::jsonb)", (json.dumps({"s": "generated/images/a.png"}),))[0][0]
    assert keys != ["stale-release"] and "generated/images/a.png" in keys


@pytest.mark.parametrize("reference", [
    "https://media.example.invalid/api/public/storage/generated/images/shared-file.png?sig=x",
    "https://media.example.invalid/api/public/storage/generated%2Fimages%2Fshared-file.png",
    "https://media.example.invalid/api/public/storage/generated%252Fimages%252Fshared-file.png",
    '{"nested":"[\\"https://media.example.invalid/generated/images/shared-file.png\\"]"}',
])
def test_prefiltered_reference_scan_still_sees_other_accounts_encoded_references(case, reference):
    _legacy_account_with_unrecorded_media(case)
    key = "generated/images/shared-file.png"; add_media(case, key, owner=None)
    case.execute("INSERT INTO prostudio_generation_jobs(id,telegram_id,status,request_json) VALUES('other-ref',%s,'completed',%s)",
                 (V, json.dumps({"source": reference, "inline": _inline_image(300_000)})))
    store = FakeStorage([key, "generated/images/legacy-result.png", "generated/references/legacy-ref.png"])
    case.accept()
    [result] = runner.process_pending("synthetic-only", storage=store, journal=case.journal, stripe=FakeStripe())
    assert result["complete"] and result["media"]["shared:other_reference"] == 1, result
    assert key in store.objects and key not in store.calls


def test_reference_marker_is_a_literal_part_of_the_file_name():
    assert runner._reference_marker("generated/assistant-attachments/c5601207ae38474db8fd4978279e0cca.jpeg") == \
        "c5601207ae38474db8fd4978279e0cca.jpeg"
    assert runner._reference_marker("generated/images/a+b~c.png") == ""
    assert runner._reference_marker("generated/x/long_name~v2.png") == "long_name"


def test_failed_activation_is_retried_then_processing_starts(monkeypatch):
    import ast, asyncio as aio
    tree = ast.parse((Path(__file__).parents[1]/'main.py').read_text())
    node = next(n for n in tree.body if isinstance(n,ast.AsyncFunctionDef) and n.name=='account_erasure_supervisor')
    attempts = [{"enabled": False, "configured": True, "error": "LockNotAvailable"},
                {"enabled": True, "configured": True, "accepting": True}]
    calls, printed, started = [], [], []
    fake = SimpleNamespace(activate_runtime=lambda url: calls.append(url) or attempts[len(calls)-1])
    import services
    monkeypatch.setattr(services, "account_erasure", fake, raising=False)
    monkeypatch.setitem(sys.modules, "services.account_erasure", fake)
    async def no_wait(seconds): return None
    async def worker(): started.append(True)
    env = {"asyncio": SimpleNamespace(sleep=no_wait, to_thread=aio.to_thread), "json": json,
           "DATABASE_URL": "synthetic-only", "print": lambda *a, **k: printed.append(a),
           "account_erasure_worker_loop": worker}
    exec(compile(ast.Module(body=[node],type_ignores=[]),'erasure-supervisor-fixture','exec'),env)
    aio.run(env["account_erasure_supervisor"]({"enabled": False, "configured": True, "error": "LockNotAvailable"}))
    assert len(calls) == 2 and started == [True] and len(printed) == 1


def test_processor_does_not_wait_forever_for_a_held_subject_lock(case, monkeypatch):
    import time
    receipt = case.accept()
    monkeypatch.setattr(runner, "PROCESSOR_LOCK_TIMEOUT", "300ms")
    holder = psycopg2.connect(os.environ["SYLVEX_TEST_DATABASE_URL"])  # advisory locks are database-wide
    try:
        with holder.cursor() as cur:
            # Another session's open write to this subject (write-guard lock).
            cur.execute("SELECT pg_advisory_xact_lock_shared(61181,hashtext(%s))", (str(U),))
        started = time.monotonic()
        [result] = runner.process_pending("synthetic-only", storage=FakeStorage(), journal=case.journal, stripe=FakeStripe())
        assert time.monotonic() - started < 10
        assert not result["complete"] and result["hold_code"] == "LockNotAvailable", result
    finally:
        holder.rollback(); holder.close()
    [result] = runner.process_pending("synthetic-only", storage=FakeStorage(), journal=case.journal, stripe=FakeStripe())
    assert result["complete"] and result["request_id"] == receipt["request_id"]


# --- B09 performance: reference index, typed owner lookups, single processor ---

def _install_index(case):
    with case.connect() as conn, conn.cursor() as cur:
        guards.install_reference_index(cur)
    done = guards.backfill_reference_index("synthetic-only", wait_for_older=False)
    assert not done["pending"], done
    return done


def _many_rows(case, n=3000):
    # Enough rows that the planner prefers an index over a scan.
    case.execute("INSERT INTO prostudio_messages(telegram_id,prompt,image_url) SELECT 910000000000+g,'bulk',"
                 "'https://media.example.invalid/api/public/storage/generated/images/bulk-'||g||'.png' FROM generate_series(1,%s) g", (n,))
    case.execute("ANALYZE prostudio_messages")


def test_reference_index_records_writes_and_backfills_existing_rows(case):
    before = add_media(case, "generated/images/before-index.png", owner=None, user=V)
    _install_index(case)
    after = add_media(case, "generated/images/after-index.png", owner=None, user=V)
    rows = case.execute("SELECT object_key,source_table FROM sylvex_storage_references WHERE object_key LIKE 'generated/images/%%-index.png' ORDER BY 1")
    assert rows == [("generated/images/after-index.png", "prostudio_messages"), ("generated/images/before-index.png", "prostudio_messages")]
    with case.connect() as conn, conn.cursor() as cur:
        trusted = guards.trusted_reference_tables(cur)
    assert trusted["prostudio_messages"] == ["id"] and trusted["prostudio_generation_jobs"] == ["id"]
    assert before and after


def test_indexed_reference_check_reads_rows_by_key_not_by_scan(case):
    _many_rows(case)
    _install_index(case)
    shared = "generated/images/shared-indexed.png"
    add_media(case, shared, owner=None); add_media(case, shared, owner=None, user=V)
    request = case.accept()
    with case.connect() as conn, conn.cursor() as cur:
        row = erasure.request_row(cur, request["request_id"])
        schema = erasure.columns(cur)
        assert runner._shared_reference(cur, shared, schema, row)
        assert not runner._shared_reference(cur, "generated/images/bulk-none.png", schema, row)
        cur.execute("SELECT seq_scan,idx_scan FROM pg_stat_xact_user_tables WHERE relname='prostudio_messages' AND schemaname=current_schema()")
        seq, idx = cur.fetchone()
    assert seq == 0 and idx >= 1


def test_typed_owner_predicate_uses_the_owner_index(case):
    _many_rows(case)
    case.execute("CREATE INDEX ON prostudio_messages(telegram_id)"); case.execute("ANALYZE prostudio_messages")
    add_media(case, "generated/images/own-typed.png")
    request = case.accept()
    with case.connect() as conn, conn.cursor() as cur:
        row = erasure.request_row(cur, request["request_id"])
        schema = erasure.columns(cur)
        where, params = erasure.owner_clause("prostudio_messages", schema, row)
        assert "::text" not in where
        cur.execute("EXPLAIN SELECT 1 FROM prostudio_messages WHERE " + where, params)
        plan = " ".join(r[0] for r in cur.fetchall())
    assert "Index" in plan and "Seq Scan" not in plan, plan


def test_stale_index_entry_does_not_keep_a_file_another_user_dropped(case):
    _install_index(case)
    key = "generated/images/once-shared.png"
    add_media(case, key, owner=None)
    other = add_media(case, key, owner=None, user=V)
    case.execute("UPDATE prostudio_messages SET image_url='https://media.example.invalid/api/public/storage/generated/images/v-own.png' "
                 "WHERE telegram_id=%s AND image_url=%s", (V, other))
    assert case.execute("SELECT COUNT(*) FROM sylvex_storage_references WHERE object_key=%s", (key,))[0][0] == 2
    store = FakeStorage([key]); case.accept()
    [result] = runner.process_pending("synthetic-only", storage=store, journal=case.journal, stripe=FakeStripe())
    assert result["complete"] and store.calls == [key]
    assert case.execute("SELECT COUNT(*) FROM sylvex_storage_references WHERE object_key=%s", (key,))[0][0] == 0


def test_reference_added_after_backfill_is_found_through_the_index(case):
    _install_index(case)
    key = "generated/images/late-share.png"
    add_media(case, key, owner=None)
    case.execute("UPDATE prostudio_resources SET photos_json=photos_json")  # unrelated write
    case.execute("INSERT INTO prostudio_resources(telegram_id,photos_json) VALUES(%s,%s)",
                 (V, json.dumps(["https://media.example.invalid/generated/images/late-share.png"])))
    store = FakeStorage([key]); case.accept()
    [result] = runner.process_pending("synthetic-only", storage=store, journal=case.journal, stripe=FakeStripe())
    assert result["complete"] and key in store.objects and not store.calls


def test_older_guard_without_recording_makes_the_index_untrusted_until_backfilled(case, monkeypatch):
    _install_index(case)
    old_body = guards.SQL.split("-- Reference index (installed only by install_reference_index)")[0] + "    RETURN NEW;\nEND $$;\n"
    with case.connect() as conn, conn.cursor() as cur:
        cur.execute(old_body)  # what a rollback to an older release installs
    key = "generated/images/rollback-window.png"
    add_media(case, key, owner=None); add_media(case, key, owner=None, user=V)
    assert case.execute("SELECT COUNT(*) FROM sylvex_storage_references WHERE object_key=%s", (key,))[0][0] == 0
    with case.connect() as conn, conn.cursor() as cur:
        assert guards.trusted_reference_tables(cur) == {}
    monkeypatch.setattr(erasure, "validate_runtime", lambda url: None)
    status = erasure.activate_runtime("synthetic-only")
    assert status["reference_index"]["reset"] and status["reference_index"]["backfilled"] == 0
    store = FakeStorage([key]); case.accept()
    [result] = runner.process_pending("synthetic-only", storage=store, journal=case.journal, stripe=FakeStripe())
    assert result["complete"] and key in store.objects  # found by the scan fallback
    assert not guards.backfill_reference_index("synthetic-only", wait_for_older=False)["pending"]


def test_table_without_primary_key_is_always_scanned(case):
    case.execute("CREATE TABLE prostudio_drafts(telegram_id BIGINT,body TEXT)")
    with case.connect() as conn, conn.cursor() as cur:
        guards.install(cur)  # a new guarded table gets its guard first, as in a release
    _install_index(case)
    key = "generated/images/draft-ref.png"; add_media(case, key, owner=None)
    case.execute("INSERT INTO prostudio_drafts VALUES(%s,%s)", (V, "https://media.example.invalid/generated/images/draft-ref.png"))
    with case.connect() as conn, conn.cursor() as cur:
        assert "prostudio_drafts" not in guards.trusted_reference_tables(cur)
    store = FakeStorage([key]); case.accept()
    [result] = runner.process_pending("synthetic-only", storage=store, journal=case.journal, stripe=FakeStripe())
    assert result["complete"] and key in store.objects


def test_backfill_resumes_and_waits_for_older_writers(case):
    case.execute("DROP TABLE IF EXISTS sylvex_storage_reference_tables,sylvex_storage_references")  # fresh migration
    for i in range(5):
        add_media(case, "generated/images/resume-%d.png" % i, owner=None, user=V)
    writer = psycopg2.connect(os.environ["SYLVEX_TEST_DATABASE_URL"], options="-c search_path=" + case.execute("SELECT current_schema()")[0][0])
    try:
        with writer.cursor() as cur:  # a writer that started before recording
            cur.execute("INSERT INTO prostudio_messages(telegram_id,image_url) VALUES(%s,%s)",
                        (V, "https://media.example.invalid/api/public/storage/generated/images/straggler.png"))
        with case.connect() as conn, conn.cursor() as cur:
            guards.install_reference_index(cur)
        blocked = guards.backfill_reference_index("synthetic-only", wait_seconds=1)
        assert blocked.get("blocked_by_older_transactions")
        writer.commit()
    finally:
        writer.close()
    partial = guards.backfill_reference_index("synthetic-only", batch=1, max_seconds=0)
    assert partial["pending"]
    assert not guards.backfill_reference_index("synthetic-only", batch=2)["pending"]
    keys = {row[0] for row in case.execute("SELECT object_key FROM sylvex_storage_references")}
    assert {"generated/images/straggler.png"} | {"generated/images/resume-%d.png" % i for i in range(5)} <= keys


def test_one_processor_across_instances(case):
    receipt = case.accept()
    holder = psycopg2.connect(os.environ["SYLVEX_TEST_DATABASE_URL"])  # advisory locks are database-wide
    try:
        with holder.cursor() as cur:
            cur.execute("SELECT pg_advisory_lock(%s,%s)", runner.PROCESSOR_LEASE)
        holder.commit()
        assert runner.process_pending("synthetic-only", storage=FakeStorage(), journal=case.journal, stripe=FakeStripe()) == []
        assert case.execute("SELECT state FROM sylvex_erasure_requests") == [("queued",)]
    finally:
        holder.close()  # the server drops a session lock with its connection, as on a crash
    [result] = runner.process_pending("synthetic-only", storage=FakeStorage(), journal=case.journal, stripe=FakeStripe())
    assert result["complete"] and result["request_id"] == receipt["request_id"]


def test_parallel_instances_run_one_pass_and_cancel_renewal_once(case):
    import threading
    _wallets_and_stripe(case)
    case.accept()
    stripe, inflight, peak, gate = FakeStripe(), [0], [0], threading.Lock()
    original = runner.process_request
    def counted(*a, **k):
        with gate:
            inflight[0] += 1; peak[0] = max(peak[0], inflight[0])
        try:
            import time; time.sleep(0.2); return original(*a, **k)
        finally:
            with gate:
                inflight[0] -= 1
    runner.process_request = counted
    try:
        threads = [threading.Thread(target=runner.process_pending, args=("synthetic-only",),
                                    kwargs={"storage": FakeStorage(), "journal": case.journal, "stripe": stripe}) for _ in range(4)]
        for t in threads: t.start()
        for t in threads: t.join()
    finally:
        runner.process_request = original
    assert peak[0] == 1 and stripe.calls == [("DELETE", "/subscriptions/sub_own")]
    assert case.execute("SELECT state FROM sylvex_erasure_requests") == [("complete",)]


def test_large_account_finishes_in_one_pass_in_resumable_batches(case, monkeypatch):
    keys = ["generated/images/batch-%d.png" % i for i in range(7)]
    for key in keys: add_media(case, key)
    monkeypatch.setattr(runner, "MEDIA_BATCH", 2)
    store = FakeStorage(keys); case.accept()
    [result] = runner.process_pending("synthetic-only", storage=store, journal=case.journal, stripe=FakeStripe())
    assert result["complete"] and store.objects == set() and sorted(store.calls) == sorted(keys)


def test_pass_budget_defers_requests_without_losing_them(case, monkeypatch):
    receipt = case.accept()
    monkeypatch.setattr(runner, "PASS_BUDGET_SECONDS", -1)
    [result] = runner.process_pending("synthetic-only", storage=FakeStorage(), journal=case.journal, stripe=FakeStripe())
    assert result["hold_code"] == "pass_budget" and case.execute("SELECT state FROM sylvex_erasure_requests") == [("queued",)]
    monkeypatch.setattr(runner, "PASS_BUDGET_SECONDS", 120)
    [result] = runner.process_pending("synthetic-only", storage=FakeStorage(), journal=case.journal, stripe=FakeStripe())
    assert result["complete"] and result["request_id"] == receipt["request_id"]


def test_crash_between_object_delete_and_commit_resumes_safely(case, monkeypatch):
    keys = ["generated/images/crash-%d.png" % i for i in range(3)]
    for key in keys: add_media(case, key)
    store = FakeStorage(keys); case.accept()
    real_delete = store.delete
    def crash_after_first(key):
        real_delete(key)
        raise SystemExit("synthetic process crash after the object delete")
    store.delete = crash_after_first
    with pytest.raises(SystemExit):
        runner.process_pending("synthetic-only", storage=store, journal=case.journal, stripe=FakeStripe())
    assert case.execute("SELECT COUNT(*) FROM prostudio_messages WHERE telegram_id=%s", (U,))[0][0] == 3
    store.delete = real_delete
    [result] = runner.process_pending("synthetic-only", storage=store, journal=case.journal, stripe=FakeStripe())
    assert result["complete"] and store.objects == set()


def test_bulk_write_of_many_referencing_rows_does_not_exhaust_locks(case):
    # One account's 3000 rows x several key suffixes in one statement (as an
    # account merge moves them): one lock per key failed with "out of shared
    # memory"; buckets bound it to 64 (+ the owner's subject lock).
    case.execute("INSERT INTO prostudio_messages(telegram_id,prompt,image_url) SELECT %s,'bulk',"
                 "'https://media.example.invalid/api/public/storage/generated/images/bulk-'||g||'.png' FROM generate_series(1,3000) g", (V,))
    with case.connect() as conn, conn.cursor() as cur:
        cur.execute("UPDATE prostudio_messages SET prompt='bulk2' WHERE prompt='bulk'")
        cur.execute("SELECT COUNT(*) FROM pg_locks WHERE locktype='advisory' AND pid=pg_backend_pid()")
        assert cur.fetchone()[0] <= 64 + 4


def test_operator_cli_installs_and_backfills_the_reference_index_only_with_apply(case, monkeypatch, capsys):
    from services import account_erasure_cli as cli
    monkeypatch.setenv("DATABASE_URL", "synthetic-only")
    case.execute("DROP TABLE IF EXISTS sylvex_storage_reference_tables,sylvex_storage_references")
    add_media(case, "generated/images/cli-ref.png", owner=None, user=V)
    assert cli.main(["reference-index"]) == 0
    assert json.loads(capsys.readouterr().out) == {"applied": False, "installed": False}
    assert not case.execute("SELECT to_regclass('sylvex_storage_references')")[0][0]
    assert cli.main(["reference-index", "--apply", "--pause", "0"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["pending"] == [] and out["tables"] == out["backfilled"] + out["without_primary_key"] and out["trusted"] >= 3
    assert case.execute("SELECT COUNT(*) FROM sylvex_storage_references WHERE object_key='generated/images/cli-ref.png'")[0][0] == 1
