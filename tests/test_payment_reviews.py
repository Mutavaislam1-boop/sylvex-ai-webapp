"""LB-006 synthetic DB and fake providers only. Never a payment or provider call."""
import contextlib
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
import psycopg2
import pytest
if os.environ['LB006_ROLE']=='api':
    from services import payment_reviews as r, billing_safety as wallet
else:
    from app.database import payment_reviews as r, credit_wallet as wallet


def connect():
    conn=psycopg2.connect(os.environ['SYLVEX_TEST_DATABASE_URL'])
    assert 'test_lb006_' in conn.get_dsn_parameters()['dbname']
    return conn


def sql(query,params=()):
    with contextlib.closing(connect())as conn:
        with conn:
            with conn.cursor()as cur:
                cur.execute(query,params)
                return cur.fetchall()if cur.description else None


def install_payment_tables(connector):
    with r.transaction(connector)as conn:
        with conn.cursor()as cur:
            cur.execute('DROP TABLE IF EXISTS financial_review_resolutions,financial_review_events,financial_review_cases,payment_refund_requests,purchases,shop_orders CASCADE')
            cur.execute('CREATE TABLE purchases(id BIGSERIAL PRIMARY KEY,telegram_id BIGINT,provider TEXT,credits INTEGER,amount TEXT,currency TEXT,payload TEXT,charge_id TEXT UNIQUE,status TEXT)')
            cur.execute('CREATE TABLE shop_orders(order_id TEXT PRIMARY KEY,telegram_id BIGINT,provider TEXT,kind TEXT,credits INTEGER,status TEXT)')
    r.ensure_tables(connector)


@pytest.fixture
def db():
    sql('DROP SCHEMA public CASCADE; CREATE SCHEMA public')
    sql('CREATE TABLE users(telegram_id BIGINT PRIMARY KEY,balance INTEGER); INSERT INTO users VALUES(101,100),(202,100)')
    sql('CREATE TABLE subscriptions(id SERIAL PRIMARY KEY,telegram_id BIGINT,charge_id TEXT,subscription_type TEXT,starts_at TIMESTAMP,expires_at TIMESTAMP,status TEXT)')
    sql("INSERT INTO subscriptions(telegram_id,subscription_type,starts_at,expires_at,status)VALUES(101,'starter_month',NOW()-INTERVAL'1 day',NOW()+INTERVAL'30 days','active')")
    wallet.ensure_reservations(connect);install_payment_tables(connect)
    return connect


def purchase(provider='stripe',charge='pi_one',uid=101,kind='credits',order='a'*32,credits=100,amount='1000'):
    sql("INSERT INTO shop_orders VALUES(%s,%s,%s,%s,%s,'paid')ON CONFLICT DO NOTHING",(order,uid,provider,kind,credits))
    return sql("INSERT INTO purchases(telegram_id,provider,credits,amount,currency,payload,charge_id,status)VALUES(%s,%s,%s,%s,%s,%s,%s,'completed')RETURNING id",
               (uid,provider,credits,amount,'XTR'if provider=='telegram_stars'else'USD','sylvex_order:'+order,charge))[0][0]


def observe(event='evt_1',mode=False,provider='stripe',**kw):
    obs=dict(kind='refund',charge_id='ch_one',refs=['pi_one'],entity_id='re_one',amount=200,status='succeeded')
    obs.update(kw);r.receive(connect,provider,mode,event,'synthetic',obs)
    return r.apply(connect,provider,mode,event,obs)


def held(uid=101,mode=False):
    with r.transaction(connect)as conn:
        with conn.cursor()as cur:
            cur.execute('SELECT telegram_id FROM users WHERE telegram_id=%s FOR UPDATE',(uid,))
            return r.blocked_for(cur,uid,mode)


def balance():return sql('SELECT telegram_id,balance FROM users ORDER BY telegram_id')

def resolve(case,decision='no_credit_adjustment',**kw):
    return r.resolve(connect,case['case_id'],case['review_revision'],operator='synthetic-owner',evidence='synthetic-provider-proof',decision=decision,**kw)


def test_additive_migration_and_ingestion_do_not_change_history_or_balances(db):
    purchase();before=balance();original=sql('SELECT * FROM purchases')
    for _ in range(2):r.ensure_tables(connect)
    case=observe();assert held() and not held(202) and not held(mode=True)
    assert balance()==before and sql('SELECT * FROM purchases')==original
    assert sql('SELECT COUNT(*)FROM subscriptions')[0][0]==1
    assert resolve(case)['outcome']=='resolved' and not held() and balance()==before


def test_event_duplicate_and_conflicting_identity(db):
    purchase();case=observe();assert observe()['outcome']=='duplicate_event'
    with pytest.raises(r.ReviewError,match='identity_conflict'):observe(amount=201)
    assert sql('SELECT review_revision FROM financial_review_cases')[0][0]==case['review_revision']==1


def test_partial_refund_aggregate_does_not_count_summary_twice(db):
    purchase();observe(amount=200);observe('evt_2',kind='charge_refunded',entity_id='ch_one',amount=200)
    observe('evt_3',entity_id='re_two',amount=300)
    observe('evt_4',kind='charge_refunded',entity_id='ch_one',amount=500)
    facts=sql('SELECT facts FROM financial_review_cases')[0][0]
    assert max(facts['cumulative_refunded'],sum(facts['refunds'].values()))==500
    assert balance()==[(101,100),(202,100)]


@pytest.mark.parametrize('kind,status',[('refund','pending'),('refund','failed'),('refund','canceled'),('charge_refunded','')])
def test_non_confirmed_refund_alone_does_not_hold(db,kind,status):
    purchase();observe(kind=kind,status=status,amount=0 if kind=='charge_refunded' else 200)
    assert not held()


def test_dispute_out_of_order_and_won_requires_explicit_resolution(db):
    purchase();observe(kind='dispute',entity_id='dp_one',status='won')
    case=observe('evt_late',kind='dispute',entity_id='dp_one',status='under_review')
    assert sql('SELECT facts FROM financial_review_cases')[0][0]['disputes']['dp_one']['status']=='won'
    assert held();resolve(case,'dispute_won');assert not held()
    observe('evt_duplicate_business',kind='dispute',entity_id='dp_one',status='won');assert not held()


def test_new_material_event_reopens_resolved_review_and_stale_resolution_refused(db):
    purchase();first=observe();resolve(first);second=observe('evt_2',entity_id='re_two',amount=10)
    assert held() and second['review_revision']>first['review_revision']
    with pytest.raises(r.ReviewError,match='review_changed'):resolve(first)
    with pytest.raises(r.ReviewError,match='all_disputes_won'):resolve(second,'dispute_won')


def test_exact_original_mapping_no_claimed_user_binding(db):
    purchase(charge='pi_unrelated');case=observe(telegram_id=101)
    assert not case['mapped'] and not held() and r.summary(connect)['pending_mapping']==1
    with pytest.raises(r.ReviewError,match='original_payment_not_mapped'):resolve(case)
    resolve(case,'not_platform_payment')
    purchase(charge='pi_one',order='b'*32);assert held()
    assert r.refresh_mappings(connect)==1 and held()


def test_refund_before_grant_known_order_and_late_purchase_reopens(db):
    sql("INSERT INTO shop_orders VALUES(%s,101,'stripe','credits',100,'pending')",('a'*32,))
    case=observe(order_id='a'*32);assert held()
    resolve(case,'ungranted_payment_refunded');assert not held()
    purchase();assert held();r.refresh_mappings(connect);assert held()


def test_mapping_conflict_requires_explicit_exact_alias_proof(db):
    pid=purchase();purchase(charge='pi_two',uid=202,order='b'*32)
    case=observe(refs=['pi_one','pi_two']);assert not case['mapped']
    with pytest.raises(r.ReviewError,match='mapping_conflict'):resolve(case)
    with pytest.raises(r.ReviewError,match='source_conflicts'):
        r.map_original(connect,case['case_id'],pid,1,operator='owner',evidence='proof',source='bad')
    unrelated=purchase(charge='pi_unrelated',order='c'*32)
    with pytest.raises(r.ReviewError,match='exact_original'):
        r.map_original(connect,case['case_id'],unrelated,1,operator='owner',evidence='proof')
    mapped=r.map_original(connect,case['case_id'],pid,1,operator='owner',evidence='verified-exact-alias')
    assert mapped['review_revision']==2 and held() and not held(202)
    resolve(mapped);assert not held()


def test_pending_event_blocks_exact_account_before_failed_provider_fetch(db):
    purchase();r.receive(connect,'stripe',False,'evt_pending','refund.created',{'payment_refs':['pi_one'],'requires_review_hint':True})
    r.failed(connect,'stripe',False,'evt_pending',TimeoutError('never-log-this-secret'))
    assert held() and not held(202) and not held(mode=True)
    assert sql('SELECT last_error_class FROM financial_review_events')[0][0]=='TimeoutError'


def test_concurrent_events_and_same_event_duplicates(db):
    purchase()
    with ThreadPoolExecutor(max_workers=4)as pool:
        result=list(pool.map(lambda i:observe('evt_'+str(i),entity_id='re_'+str(i),amount=1),range(8)))
    assert len({x['case_id']for x in result})==1
    assert len(sql('SELECT facts FROM financial_review_cases')[0][0]['refunds'])==8
    with ThreadPoolExecutor(max_workers=4)as pool:
        assert all(x['outcome']=='duplicate_event'for x in pool.map(lambda _:observe('evt_0',entity_id='re_0',amount=1),range(4)))


def test_resolution_idempotence_and_different_decision_refused(db):
    purchase();case=observe();resolve(case)
    assert resolve(case)['outcome']=='duplicate_resolution'
    with pytest.raises(r.ReviewError,match='resolved_differently'):resolve(case,'loss_accepted')
    assert sql('SELECT COUNT(*)FROM financial_review_resolutions')[0][0]==1


def correction(case,**overrides):
    params=dict(decision='confirmed_credit_correction',credits=20,source='purchased',confirmed_unspent_credits=20,
                expected_balance=100,expected_purchased=100,expected_subscription=0,wallet=wallet)
    params.update(overrides);return resolve(case,**params)


def test_confirmed_correction_uses_existing_wallet_exactly_once(db):
    purchase();case=observe();assert correction(case)['balance_after']==80
    assert correction(case)['outcome']=='duplicate_resolution' and balance()[0][1]==80
    assert sql('SELECT * FROM purchases')[0][-1]=='completed'


@pytest.mark.parametrize('overrides,reason',[
    ({'source':'subscription'},'original_source'),({'confirmed_unspent_credits':None},'unused_credits'),
    ({'confirmed_unspent_credits':101},'exceeds_original'),({'credits':101,'confirmed_unspent_credits':101},'exceeds_original'),
    ({'expected_balance':99},'wallet_changed'),({'expected_purchased':99},'wallet_changed')])
def test_correction_refuses_unsafe_or_stale_attestation(db,overrides,reason):
    purchase();case=observe()
    with pytest.raises(r.ReviewError,match=reason):correction(case,**overrides)
    assert balance()[0][1]==100 and held() and not sql('SELECT * FROM financial_review_resolutions')


def test_correction_never_takes_unrelated_bucket_or_open_reservation(db):
    purchase();case=observe()
    sql("INSERT INTO user_credit_wallets(telegram_id,purchased_credits,subscription_credits,subscription_expires_at)VALUES(101,10,90,NOW()+INTERVAL'30 days')")
    with pytest.raises(r.ReviewError,match='insufficient_original_source'):
        correction(case,expected_purchased=10,expected_subscription=90)
    sql("INSERT INTO generation_reservations(generation_id,telegram_id,credits,status)VALUES('accepted',101,5,'reserved')")
    with pytest.raises(r.ReviewError,match='existing_holds'):correction(case)
    assert balance()[0][1]==100


def test_subscription_correction_cannot_debit_new_period(db):
    purchase(kind='subscription');case=observe()
    sql("UPDATE subscriptions SET charge_id='pi_one',expires_at=NOW()+INTERVAL'10 days'")
    sql("INSERT INTO user_credit_wallets(telegram_id,purchased_credits,subscription_credits,subscription_expires_at)VALUES(101,0,100,NOW()+INTERVAL'30 days')")
    with pytest.raises(r.ReviewError,match='different_subscription_period'):
        correction(case,source='subscription',expected_purchased=0,expected_subscription=100)
    sql('UPDATE user_credit_wallets SET subscription_expires_at=(SELECT expires_at FROM subscriptions LIMIT 1)')
    assert correction(case,source='subscription',expected_purchased=0,expected_subscription=100)['balance_after']==80


def test_resolution_and_wallet_roll_back_together_on_audit_failure(db):
    purchase();case=observe()
    sql("""CREATE FUNCTION fail_review()RETURNS trigger LANGUAGE plpgsql AS $$BEGIN RAISE EXCEPTION 'synthetic';END$$;
        CREATE TRIGGER fail_review BEFORE INSERT ON financial_review_resolutions FOR EACH ROW EXECUTE FUNCTION fail_review()""")
    with pytest.raises(psycopg2.Error):correction(case)
    assert held() and balance()[0][1]==100 and not sql('SELECT * FROM user_credit_wallets')


def star_receipt(charge='star_one',order=None):
    return dict(currency='XTR',total_amount=10,telegram_payment_charge_id=charge,invoice_payload='sylvex_order:'+order if order else'legacy')


def test_stars_refund_channels_deduplicate_economic_effect_without_wallet_changes(db):
    purchase('telegram_stars','star_one',amount='10')
    r.record_stars_refund(connect,star_receipt(order='a'*32))
    assert r.record_star_transaction_refund(connect,dict(id='star_one',amount=10,receiver={'type':'user','transaction_type':'invoice_payment'}))
    assert held(mode=True) and held(mode=False) and balance()[0][1]==100
    assert sum(sql('SELECT facts FROM financial_review_cases')[0][0]['refunds'].values())==10


@pytest.mark.parametrize('tx',[
    dict(id='one',amount=1,source={'type':'user','transaction_type':'invoice_payment'}),
    dict(id='one',amount=1,receiver={'type':'user','transaction_type':'gift_purchase'}),
    dict(id='one',amount=1,receiver={'type':'fragment'})])
def test_unrelated_stars_transactions_are_not_refunds(db,tx):
    assert r.record_star_transaction_refund(connect,tx)is False
    assert not sql('SELECT * FROM financial_review_cases')


def test_stars_receipt_survives_apply_failure_and_restarts(db,monkeypatch):
    purchase('telegram_stars','star_one',amount='10');real=r.apply
    monkeypatch.setattr(r,'apply',lambda *a,**k:(_ for _ in ()).throw(RuntimeError('synthetic crash')))
    with pytest.raises(RuntimeError):r.record_stars_refund(connect,star_receipt())
    assert held() and r.summary(connect)['pending_events']==1
    monkeypatch.setattr(r,'apply',real)
    assert r.replay_stars_refunds(connect)=={'processed':1,'retry':0}
    assert r.replay_stars_refunds(connect)=={'processed':0,'retry':0} and held()


def test_stars_refund_request_is_durable_before_provider_and_called_once(db):
    pid=purchase('telegram_stars','star_one',amount='10');calls=[]
    def provider(uid,charge):
        calls.append((uid,charge));assert held() and sql('SELECT status FROM payment_refund_requests')[0][0]=='dispatching';return True
    result=r.request_stars_refund(connect,pid,provider,operator='owner',evidence='explicit-refund-approval')
    assert result['status']=='confirmed' and r.request_stars_refund(connect,pid,provider,operator='owner',evidence='proof')['provider_called']is False
    assert calls==[(101,'star_one')] and held() and balance()[0][1]==100


def test_timeout_never_reissues_refund_manual_proof_required(db):
    pid=purchase('telegram_stars','star_one',amount='10');calls=[]
    def provider(*a):calls.append(1);raise TimeoutError('sensitive-provider-url')
    with pytest.raises(TimeoutError):r.request_stars_refund(connect,pid,provider,operator='owner',evidence='approval')
    request=sql('SELECT request_id,status FROM payment_refund_requests')[0]
    assert request[1]=='pending_reconciliation' and held()
    assert r.request_stars_refund(connect,pid,provider,operator='owner',evidence='approval')['provider_called']is False and calls==[1]
    r.resolve_stars_request(connect,request[0],refunded=False,operator='owner',evidence='confirmed-not-refunded')
    assert not held() and sql('SELECT COUNT(*)FROM financial_review_events')[0][0]==1


def test_hard_process_exit_after_external_dispatch_stays_reconcilable(db):
    pid=purchase('telegram_stars','star_one',amount='10')
    module='services.payment_reviews'if os.environ['LB006_ROLE']=='api'else'app.database.payment_reviews'
    code=f'''import os,psycopg2\nfrom {module} import request_stars_refund\nrequest_stars_refund(lambda:psycopg2.connect(os.environ['SYLVEX_TEST_DATABASE_URL']),{pid},lambda *a:os._exit(77),operator='synthetic-owner',evidence='fake-provider')'''
    result=subprocess.run([sys.executable,'-c',code],capture_output=True,timeout=15)
    assert result.returncode==77 and held()
    sql("UPDATE payment_refund_requests SET created_at=NOW()-INTERVAL'3 minutes'")
    assert r.reconcile_uncertain_requests(connect)==1
    assert sql('SELECT status FROM payment_refund_requests')[0][0]=='pending_reconciliation'


def test_refund_request_db_failure_never_calls_provider(db):
    pid=purchase('telegram_stars','star_one',amount='10');sql('DROP TABLE payment_refund_requests');calls=[]
    with pytest.raises(psycopg2.Error):r.request_stars_refund(connect,pid,lambda *a:calls.append(1),operator='owner',evidence='proof')
    assert not calls


def test_case_lock_serializes_resolution_with_new_event(db):
    purchase();case=observe()
    def submit():return observe('evt_next',entity_id='re_next',amount=10)
    with r.transaction(connect)as conn:
        with conn.cursor()as cur:
            cur.execute('SELECT telegram_id FROM users WHERE telegram_id=101 FOR UPDATE')
            with ThreadPoolExecutor(max_workers=1)as pool:
                future=pool.submit(submit)
                # Owner decision under the already held user lock is represented by
                # the same production transaction on a second connection only after release.
                assert not future.done()
                conn.commit()
                assert future.result(timeout=10)['review_revision']==2
    with pytest.raises(r.ReviewError,match='review_changed'):resolve(case)
