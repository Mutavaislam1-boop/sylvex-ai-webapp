"""B09 message-review regression: synthetic PostgreSQL, fake media only."""
from datetime import datetime, timedelta, timezone
import ast
import asyncio
import copy
from pathlib import Path

import pytest

from services import account_erasure as erasure
from services import account_erasure_guards as guards
from services import account_erasure_runner as runner
from services import account_erasure_restore as restore
from test_account_erasure import (
    A, B, U, V, REFERENCE_INDEX, FakeStorage, case, add_media,
    _telegram_subject,
)
from test_telegram_erasure import _allocator


@pytest.fixture
def messages(case, monkeypatch):
    uid = _telegram_subject(case, monkeypatch)
    case.uid = uid
    case.execute("""
        CREATE TABLE community_messages (
            id BIGSERIAL PRIMARY KEY, sender_id BIGINT NOT NULL,
            recipient_id BIGINT NOT NULL DEFAULT 0, body TEXT NOT NULL,
            read_at TIMESTAMP, created_at TIMESTAMP DEFAULT NOW());
        CREATE TABLE admin_messages (
            id BIGSERIAL PRIMARY KEY, admin_telegram_id BIGINT NOT NULL,
            user_telegram_id BIGINT NOT NULL, message TEXT NOT NULL,
            telegram_sent BOOLEAN NOT NULL DEFAULT FALSE, created_at TIMESTAMP DEFAULT NOW());
    """)
    for id in (7, 8, 9, 10):
        case.execute("INSERT INTO community_messages VALUES(%s,%s,%s,%s,'2026-01-02','2026-01-01')",
                     (id, uid, V, 'synthetic departing author '+str(id)))
    for id in (2, 8):
        case.execute("INSERT INTO admin_messages VALUES(%s,%s,%s,%s,TRUE,'2026-01-01')",
                     (id, V, uid, 'synthetic administrator '+str(id)))
    case.execute("INSERT INTO community_messages VALUES(90,%s,%s,'unrelated conversation',NULL,'2026-01-01')",(V,U))
    case.execute("INSERT INTO admin_messages VALUES(90,%s,%s,'unrelated admin record',TRUE,'2026-01-01')",(V,U))
    with case.connect() as conn:
        with conn.cursor() as cur:
            guards.install(cur)
            if REFERENCE_INDEX:
                guards.install_reference_index(cur)
    if REFERENCE_INDEX:
        assert not guards.backfill_reference_index('synthetic-only',wait_for_older=False)['pending']
    case.keys = ['generated/images/message-erasure-%02d.png' % n for n in range(10)]
    for key in case.keys:
        add_media(case,key,owner=None,user=uid)
    case.store = FakeStorage(case.keys)
    case.original_messages = case.execute('SELECT * FROM community_messages ORDER BY id')
    case.original_admin = case.execute('SELECT * FROM admin_messages ORDER BY id')
    case.financial = case.execute('SELECT * FROM purchases ORDER BY id')
    case.other_users = case.execute('SELECT * FROM users WHERE telegram_id<>%s ORDER BY telegram_id',(uid,))
    return case


def accept(env):
    with env.connect() as conn:
        with conn.cursor() as cur:
            reply=erasure.accept_confirmed_request(cur,A,ecosystem='telegram',journal=env.journal)
            cur.execute('UPDATE sylvex_erasure_requests SET telegram_caches_cleared_at=NOW(),'
                        "state='scope_review',hold_code='third_party_or_legal_scope_requires_review' WHERE request_id=%s",
                        (reply['request_id'],))
    return reply


def process(env, receipt, **kw):
    return runner.process_request('synthetic-only',receipt['request_id'],storage=env.store,
                                  journal=env.journal,apply=True,self_service=True,**kw)


def assert_others_unchanged(env):
    assert env.execute('SELECT * FROM purchases ORDER BY id')==env.financial
    assert env.execute('SELECT * FROM users WHERE telegram_id<>%s ORDER BY telegram_id',(env.uid,))==env.other_users
    assert env.execute('SELECT * FROM community_messages WHERE id=90')==[env.original_messages[-1]]
    assert env.execute('SELECT * FROM admin_messages WHERE id=90')==[env.original_admin[-1]]


def test_six_message_hold_completes_without_retention_approvals(messages):
    env=messages;receipt=accept(env)
    result=process(env,receipt)
    assert result['complete'],(result.get('state'),result.get('hold_code'))
    assert env.execute('SELECT COUNT(*) FROM sylvex_erasure_retained_rows')==[(0,)]
    assert env.execute('SELECT sender_id,recipient_id,body,read_at,created_at FROM community_messages WHERE id<90 ORDER BY id')==[
        (-A,V,'',row[4],row[5]) for row in env.original_messages[:-1]]
    assert env.execute('SELECT admin_telegram_id,user_telegram_id,message,telegram_sent,created_at FROM admin_messages WHERE id<90 ORDER BY id')==[
        (row[1],-A,row[3],row[4],row[5]) for row in env.original_admin[:-1]]
    assert sorted(env.store.calls)==sorted(env.keys) and not env.store.objects
    assert_others_unchanged(env)


def test_plan_never_changes_message_content_or_deletes_files(messages):
    env=messages;receipt=accept(env)
    plan=runner.process_request('synthetic-only',receipt['request_id'],storage=env.store,
                                journal=env.journal,apply=False,self_service=True)
    assert plan['state']=='queued' and not plan.get('hold_code'),plan
    assert env.execute('SELECT * FROM community_messages ORDER BY id')==env.original_messages
    assert env.execute('SELECT * FROM admin_messages ORDER BY id')==env.original_admin
    assert not env.store.calls


def test_incoming_authors_content_and_public_chat_are_preserved(messages):
    env=messages
    env.execute("INSERT INTO community_messages(id,sender_id,recipient_id,body) VALUES"
                "(11,%s,%s,'other author private'),(12,%s,0,'departing public'),"
                "(13,%s,0,'other public'),(14,%s,%s,'self message')",
                (V,env.uid,env.uid,V,env.uid,env.uid))
    assert process(env,accept(env))['complete']
    assert env.execute('SELECT id,sender_id,recipient_id,body FROM community_messages WHERE id BETWEEN 11 AND 14 ORDER BY id')==[
        (11,V,-A,'other author private'),(12,-A,0,''),(13,V,0,'other public'),(14,-A,-A,'')]
    assert_others_unchanged(env)


def test_retry_is_idempotent_and_never_redeletes_a_finished_object(messages):
    env=messages;receipt=accept(env)
    assert process(env,receipt)['complete']
    after=env.execute('SELECT * FROM community_messages ORDER BY id')
    calls=list(env.store.calls)
    journal=erasure.Journal(env.journal.path)
    assert runner.process_request('synthetic-only',receipt['request_id'],storage=env.store,
                                   journal=journal,apply=True,self_service=True)['complete']
    assert env.execute('SELECT * FROM community_messages ORDER BY id')==after
    assert env.store.calls==calls
    assert_others_unchanged(env)


def test_media_failure_leaves_messages_until_retry_can_finish(messages):
    env=messages;receipt=accept(env)
    env.store.fail_delete.add(env.keys[0])
    result=process(env,receipt)
    assert not result['complete'] and result['hold_code']=='media_retry_required'
    assert env.execute('SELECT * FROM community_messages ORDER BY id')==env.original_messages
    assert env.execute('SELECT * FROM admin_messages ORDER BY id')==env.original_admin
    env.store.fail_delete.clear()
    assert process(env,receipt)['complete']
    assert_others_unchanged(env)


def test_final_transaction_failure_rolls_message_changes_back(messages,monkeypatch):
    env=messages;receipt=accept(env)
    original=runner._purge_personal
    def fail(cur,schema,request):
        original(cur,schema,request)
        raise RuntimeError('synthetic transaction failure')
    monkeypatch.setattr(runner,'_purge_personal',fail)
    with pytest.raises(RuntimeError,match='synthetic transaction failure'):
        process(env,receipt)
    assert env.execute('SELECT * FROM community_messages ORDER BY id')==env.original_messages
    assert env.execute('SELECT * FROM admin_messages ORDER BY id')==env.original_admin
    assert env.journal.read(receipt['request_id'])['completed_at'] is None
    calls=list(env.store.calls)
    monkeypatch.setattr(runner,'_purge_personal',original)
    assert process(env,receipt)['complete']
    assert env.store.calls==calls
    assert_others_unchanged(env)


def test_new_registration_does_not_inherit_old_message_or_admin_history(messages):
    env=messages;_allocator(env);receipt=accept(env)
    assert process(env,receipt)['complete']
    new_account=env.execute('SELECT account_id FROM sylvex_accounts WHERE active_telegram_id=%s',(env.uid,))[0][0]
    assert new_account!=A
    assert env.execute('SELECT balance,subscription FROM users WHERE telegram_id=%s',(env.uid,))==[(0,'free')]
    assert env.execute('SELECT id FROM community_messages WHERE sender_id=%s OR recipient_id=%s',(env.uid,env.uid))==[]
    assert env.execute('SELECT id FROM admin_messages WHERE user_telegram_id=%s',(env.uid,))==[]
    erasure.check_subject_access('synthetic-only',env.uid)
    env.execute("INSERT INTO community_messages(sender_id,recipient_id,body) VALUES(%s,%s,'new account')",(env.uid,V))
    before=env.execute('SELECT * FROM community_messages ORDER BY id')
    assert process(env,receipt)['complete']
    assert env.execute('SELECT * FROM community_messages ORDER BY id')==before


@pytest.mark.parametrize('table,column',[('community_messages','extra_private'),('admin_messages','extra_private')])
def test_unknown_message_fields_keep_the_existing_review_hold(messages,table,column):
    env=messages
    env.execute('ALTER TABLE '+table+' ADD COLUMN '+column+' TEXT')
    result=process(env,accept(env))
    assert not result['complete'] and result['hold_code']=='third_party_or_legal_scope_requires_review'
    assert not env.store.calls


@pytest.mark.parametrize('table,id,column',[('community_messages',7,'body'),('admin_messages',2,'message')])
def test_media_bearing_messages_keep_reference_review(messages,table,id,column):
    env=messages
    env.execute('UPDATE '+table+' SET '+column+'=%s WHERE id=%s',
                ('https://media.example.invalid/api/public/storage/'+env.keys[0],id))
    result=process(env,accept(env))
    assert not result['complete'] and result['hold_code']=='third_party_or_legal_scope_requires_review'
    assert not env.store.calls


def test_other_review_categories_and_staff_privileges_are_not_bypassed(messages):
    env=messages
    env.execute('CREATE TABLE admin_accounts(id BIGSERIAL PRIMARY KEY,account_id BIGINT,status TEXT,totp_secret_enc TEXT)')
    env.execute("INSERT INTO admin_accounts(account_id,status) VALUES(%s,'active')",(A,))
    with env.connect() as conn:
        with conn.cursor() as cur:
            guards.install(cur)
    result=process(env,accept(env))
    assert not result['complete'] and result['hold_code']=='privileged_access_requires_review'
    assert not env.store.calls
    assert env.execute('SELECT * FROM community_messages ORDER BY id')==env.original_messages


def test_explicit_retention_exception_is_not_overwritten(messages):
    env=messages;receipt=accept(env)
    with env.connect() as conn:
        with conn.cursor() as cur:
            cur.execute('SELECT to_jsonb(t) FROM community_messages t WHERE id=7')
            identity=erasure.row_identity(cur.fetchone()[0])
    runner.approve_row_retention('synthetic-only',receipt['request_id'],'community_messages',identity,
                                basis='other_participant_rights',reviewed_by='synthetic-reviewer',
                                expires_at=(datetime.now(timezone.utc)+timedelta(days=1)).isoformat())
    assert process(env,receipt)['complete']
    assert env.execute('SELECT * FROM community_messages WHERE id=7')==[env.original_messages[0]]


def test_website_review_behavior_is_unchanged(messages):
    env=messages
    receipt=env.accept(account=B)  # Existing website account with its valid storage key.
    result=process(env,receipt)
    assert not result['complete'] and result['hold_code']=='third_party_or_legal_scope_requires_review'
    assert not env.store.calls


def test_shared_media_still_survives_with_other_participants_data(messages):
    env=messages
    shared=env.keys[0]
    add_media(env,shared,owner=None,user=V)
    assert process(env,accept(env))['complete']
    assert shared in env.store.objects and shared not in env.store.calls
    assert env.execute('SELECT COUNT(*) FROM prostudio_messages WHERE telegram_id=%s',(V,))==[(1,)]
    assert_others_unchanged(env)


def test_restore_replays_message_anonymization_from_old_backup(messages):
    env=messages;receipt=accept(env)
    assert process(env,receipt)['complete']
    env.execute('TRUNCATE sylvex_erasure_media,sylvex_erasure_retained_rows,sylvex_erasure_requests,sylvex_active_operations')
    env.execute('TRUNCATE community_messages,admin_messages')
    for row in env.original_messages:
        env.execute('INSERT INTO community_messages VALUES(%s,%s,%s,%s,%s,%s)',row)
    for row in env.original_admin:
        env.execute('INSERT INTO admin_messages VALUES(%s,%s,%s,%s,%s,%s)',row)
    for key in env.keys:add_media(env,key,owner=None,user=env.uid)
    env.store.objects.update(env.keys)
    assert not restore.readiness('synthetic-only',journal=env.journal)['ready']
    result=restore.replay('synthetic-only',storage=env.store,journal=env.journal,apply=True)
    assert result['ready'] and result['results'][0]['complete'],result
    assert env.execute('SELECT sender_id,recipient_id,body FROM community_messages WHERE id<90 ORDER BY id')==[(-A,V,'')]*4
    assert env.execute('SELECT user_telegram_id FROM admin_messages WHERE id<90 ORDER BY id')==[(-A,),(-A,)]
    assert_others_unchanged(env)


def test_current_message_api_keeps_the_other_participants_conversation(messages):
    env=messages
    env.execute('CREATE TABLE user_profiles(telegram_id BIGINT PRIMARY KEY,display_name TEXT,custom_avatar_url TEXT)')
    env.execute("INSERT INTO community_messages(id,sender_id,recipient_id,body) VALUES(11,%s,%s,'reply from other author')",(V,env.uid))
    with env.connect() as conn:
        with conn.cursor() as cur:guards.install(cur)
    assert process(env,accept(env))['complete']
    # Execute the unchanged production endpoint against this isolated database.
    source=ast.parse((Path(__file__).parents[1]/'main.py').read_text())
    node=copy.deepcopy(next(n for n in source.body if isinstance(n,ast.AsyncFunctionDef) and n.name=='public_community_messages'))
    node.decorator_list=[]
    ns={'asyncio':asyncio,'ensure_community_tables':lambda:None,
        'db_connect':lambda _:env.connect(),'DATABASE_URL':'synthetic-only',
        '_to_iso':lambda value:value.isoformat() if value else None}
    exec(compile(ast.Module(body=[node],type_ignores=[]),'production-message-endpoint','exec'),ns)
    reply=asyncio.run(ns['public_community_messages'](other_id=-A,telegram_id=V))
    assert len(reply['items'])==5
    own=[r for r in reply['items'] if r['is_own']]
    assert len(own)==1 and own[0]['body']=='reply from other author'
    assert all(r['body']=='' and r['author_name']=='SYLVEX User' for r in reply['items'] if not r['is_own'])
    assert env.execute('SELECT telegram_id FROM users WHERE telegram_id<0')==[]
