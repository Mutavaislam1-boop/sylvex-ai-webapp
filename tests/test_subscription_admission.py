"""LB-003: synthetic SQL and fake providers only; no purchases or external calls."""
import ast
import asyncio
import contextlib
import json
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import psycopg2
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
import main
from services.security import SecurityError
from test_billing_coverage import ledger


def sql(query, params=()):
    with contextlib.closing(psycopg2.connect(os.environ['SYLVEX_TEST_DATABASE_URL'])) as conn:
        with conn:
            with conn.cursor() as cur:
                cur.execute(query, params)
                return cur.fetchall() if cur.description else None


@pytest.fixture
def admission(ledger, monkeypatch):
    sql('ALTER TABLE prostudio_generation_jobs ADD COLUMN conversation_id TEXT, ADD COLUMN created_at TIMESTAMP DEFAULT NOW()')
    calls=[]
    async def provider():
        calls.append(1)
        return {'ok': True}
    def start(kind):
        if kind=='helper':return asyncio.run(main.run_billed_helper(101, 3, 'grid_plan', provider))
        if kind=='text':return main.reserve_direct_text_generation(101, 3)
        if kind=='character':return main.create_character_creation_job(101, 'Ann', 'female', '', ['https://invalid.example/ref.png'], 3)
        if kind=='object':return main.create_object_creation_job(101, 'Bag', '', ['https://invalid.example/ref.png'], 3)
        return main.create_prostudio_generation_job({'telegram_id':101,'mode':'image','model':'gpt_image_2','price_snapshot':{'final_credits':3}})
    return ledger, calls, start


@pytest.mark.parametrize('kind',['helper','text','character','object','queued'])
@pytest.mark.parametrize('condition',['missing','expired','future','cancelled','refunded'])
def test_paid_admission_refuses_invalid_entitlement_without_debit_or_dispatch(admission,kind,condition):
    ledger,calls,start=admission
    if condition=='missing':sql('DELETE FROM subscriptions WHERE telegram_id=101')
    elif condition=='expired':sql("UPDATE subscriptions SET expires_at=NOW()-INTERVAL '1 second' WHERE telegram_id=101")
    elif condition=='future':sql("UPDATE subscriptions SET starts_at=NOW()+INTERVAL '1 day' WHERE telegram_id=101")
    else:sql('UPDATE subscriptions SET status=%s WHERE telegram_id=101',(condition,))
    with pytest.raises(SecurityError) as exc:start(kind)
    assert (exc.value.code,exc.value.status)==('subscription_required',403)
    assert ledger.balance(101)==100 and not calls and not ledger.charges()
    assert sql('SELECT COUNT(*) FROM generation_reservations')[0][0]==0
    assert sql('SELECT COUNT(*) FROM prostudio_generation_jobs')[0][0]==0


@pytest.mark.parametrize('kind',['helper','text','character','object','queued'])
@pytest.mark.parametrize('plan',['starter_month','pro_month','max_month','ultra_month','creator_month'])
def test_all_five_plans_keep_the_same_paid_admission(admission,kind,plan):
    ledger,calls,start=admission
    sql('UPDATE subscriptions SET subscription_type=%s WHERE telegram_id=101',(plan,))
    assert start(kind)
    assert ledger.balance(101)==97
    assert len(calls)==int(kind=='helper')


def test_legacy_paid_period_without_starts_and_cancelled_renewal_preserves_access(admission):
    ledger,calls,start=admission
    sql('UPDATE subscriptions SET starts_at=NULL WHERE telegram_id=101')
    # Renewal agreements do not invalidate the separately paid entitlement.
    sql('CREATE TABLE billing_agreements(telegram_id BIGINT,renewal_status TEXT)')
    sql("INSERT INTO billing_agreements VALUES(101,'cancelled')")
    assert start('helper') and ledger.balance(101)==97 and calls==[1]


@pytest.mark.parametrize('result_ok',[True,False])
def test_already_admitted_work_can_settle_or_refund_after_expiry(admission,result_ok):
    ledger,calls,start=admission
    async def provider():
        sql("UPDATE subscriptions SET expires_at=NOW()-INTERVAL '1 second' WHERE telegram_id=101")
        return {'ok':result_ok}
    result=asyncio.run(main.run_billed_helper(101,3,'voice_preview',provider))
    assert result['ok']==result_ok
    assert ledger.balance(101)==(97 if result_ok else 100)
    with pytest.raises(SecurityError,match='subscription_required'):start('helper')


def test_entitlement_lock_serializes_expiry_changes_with_reservation(admission):
    ledger,calls,start=admission
    def revoke():
        try:
            sql("SET lock_timeout='250ms'; UPDATE subscriptions SET status='cancelled' WHERE telegram_id=101")
        except psycopg2.errors.LockNotAvailable:return 'blocked'
        return 'changed'
    with contextlib.closing(psycopg2.connect(os.environ['SYLVEX_TEST_DATABASE_URL'])) as conn:
        with conn:
            with conn.cursor() as cur:
                main.require_generation_subscription(cur,101)
                with ThreadPoolExecutor(max_workers=1) as pool:assert pool.submit(revoke).result(timeout=5)=='blocked'
    assert revoke()=='changed'
    with pytest.raises(SecurityError,match='subscription_required'):start('helper')
    assert ledger.balance(101)==100 and not calls


@pytest.mark.parametrize('route',['character','object','voice-preview'])
def test_existing_http_handlers_return_403_before_job_or_provider(admission,monkeypatch,route):
    ledger,calls,start=admission
    sql('DELETE FROM subscriptions WHERE telegram_id=101')
    monkeypatch.setattr(main,'character_creation_price',lambda:3)
    monkeypatch.setattr(main,'object_creation_price',lambda *a:3)
    monkeypatch.setattr(main,'calculate_generation_price',lambda *a:{'pricing_available':True,'price_snapshot':{'final_credits':3}})
    async def quota(*a):return None
    async def provider(*a):calls.append(1);return {'ok':True}
    monkeypatch.setattr(main,'check_object_creation_request_quota',quota)
    monkeypatch.setattr(main,'gemini_tts_voice_preview',provider)
    app=FastAPI()
    app.add_exception_handler(SecurityError,main.security_error_handler)
    handlers={'character':main.public_prostudio_create_character,'object':main.public_prostudio_create_object,'voice-preview':main.public_prostudio_voice_preview}
    app.add_api_route('/entry',handlers[route],methods=['POST'])
    # Actual shared route handlers after identity validation, no alternate product routes.
    with TestClient(app) as client:
        response=client.post('/entry',json={'telegram_id':101,'name':'Example','photos':['https://invalid.example/ref.png']})
    assert response.status_code==403 and response.json()['error']=='subscription_required'
    assert ledger.balance(101)==100 and not calls
    assert sql('SELECT COUNT(*) FROM prostudio_generation_jobs')[0][0]==0


def test_every_current_api_reservation_entry_has_transactional_subscription_gate():
    tree=ast.parse(Path(main.__file__).read_text())
    functions=[]
    for fn in tree.body:
        if not isinstance(fn,(ast.FunctionDef,ast.AsyncFunctionDef)):continue
        reserves=[n for n in ast.walk(fn) if isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id=='reserve_generation']
        if not reserves:continue
        guards=[n for n in ast.walk(fn) if isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id=='require_generation_subscription']
        assert len(reserves)==len(guards)==1 and guards[0].lineno<reserves[0].lineno
        functions.append(fn.name)
    assert set(functions)=={'create_prostudio_generation_job','reserve_direct_text_generation','create_character_creation_job','create_object_creation_job'}


@pytest.mark.parametrize('route',['grid','home','voice-text'])
@pytest.mark.parametrize('entitled',[True,False])
def test_current_helper_route_uses_subscription_admission_before_fake_provider(admission,monkeypatch,route,entitled):
    ledger,calls,start=admission
    if not entitled:sql('DELETE FROM subscriptions WHERE telegram_id=101')
    monkeypatch.setattr(main,'helper_text_reservation',lambda *a,**k:3)
    monkeypatch.setattr(main,'grid_planner_catalog',lambda:{})
    monkeypatch.setattr(main,'grid_planner_prompt',lambda *a:'synthetic brief')
    monkeypatch.setattr(main,'grid_planner_usage_credits',lambda *a:lambda r:3)
    monkeypatch.setattr(main,'text_generation_usage_credits',lambda *a:lambda r:3)
    def fake_planner(*a):
        calls.append(1)
        return {'ok':True,'text':json.dumps({'action':'clarify','question':'Which format?'})}
    def fake_text(*a):
        calls.append(1)
        return {'ok':True,'text':json.dumps({'reply':'ok','ready':False})}
    def fake_editor(*a):calls.append(1);return True,'Improved text',{}
    monkeypatch.setattr(main,'grid_planner_generation_with_fallback',fake_planner)
    monkeypatch.setattr(main,'text_generation',fake_text)
    monkeypatch.setattr(main,'openai_compatible_text_request',fake_editor)
    monkeypatch.setattr(main,'OPENAI_API_KEY','synthetic-test-key')
    handlers={'grid':main.public_prostudio_grid_plan,'home':main.public_home_idea_route,'voice-text':main.public_prostudio_voice_text_tool}
    app=FastAPI()
    app.add_exception_handler(SecurityError,main.security_error_handler)
    @app.middleware('http')
    async def verified_test_identity(request,call_next):
        request.state.telegram_id=101
        return await call_next(request)
    app.add_api_route('/entry',handlers[route],methods=['POST'])
    with TestClient(app) as client:
        response=client.post('/entry',json={'telegram_id':101,'task':'A short ad','message':'An ad','action':'improve','text':'helo'})
    assert response.status_code==(200 if entitled else 403)
    if entitled:
        assert calls==[1] and len(ledger.charges())==1 and ledger.balance(101)<100
    else:
        assert response.json()['error']=='subscription_required'
        assert not calls and ledger.balance(101)==100 and not ledger.charges()
