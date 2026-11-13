"""S6-07: Test/unknown money never becomes confirmed cash revenue.
Synthetic local SQL only. Does not create purchases via any payment provider.
"""
import asyncio
import os
import pytest
from services import stripe_billing as stripe, payment_reporting as reporting
from tests.support.pglite_adapter import Database

pytestmark = pytest.mark.skipif(not(os.getenv('SYLVEX_TEST_NODE') and os.getenv('SYLVEX_PGLITE_MODULE')), reason='Configure isolated SQL harness')


def q(db, sql, params=()):
    with db.connect() as c:
        with c.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchall()


@pytest.fixture
def db():
    d = Database()
    try:
        q(d, '''CREATE TABLE users(telegram_id BIGINT PRIMARY KEY, first_name TEXT, username TEXT, balance INTEGER, subscription TEXT, created_at TIMESTAMP);
            CREATE TABLE user_credit_wallets(telegram_id BIGINT PRIMARY KEY, purchased_credits INTEGER, subscription_credits INTEGER);
            CREATE TABLE purchases(id SERIAL PRIMARY KEY, telegram_id BIGINT, provider TEXT, credits INTEGER, amount INTEGER, currency TEXT, charge_id TEXT, status TEXT DEFAULT 'completed', created_at TEXT DEFAULT NOW()::text);
            CREATE TABLE subscriptions(id SERIAL PRIMARY KEY, telegram_id BIGINT, charge_id TEXT UNIQUE, status TEXT, expires_at TIMESTAMP);
            CREATE TABLE shop_orders(charge_id TEXT, provider_invoice_id TEXT);
            CREATE TABLE admin_audit_events(action TEXT, after JSONB, at TIMESTAMP);
            CREATE TABLE prostudio_generation_jobs(telegram_id BIGINT,provider TEXT,request_json JSONB,status TEXT,created_at TIMESTAMP,mode TEXT);
            CREATE TABLE app_presence(telegram_id BIGINT,last_seen TIMESTAMP);
            CREATE TABLE admin_accounts(status TEXT);
            CREATE TABLE user_profiles(telegram_id BIGINT,display_name TEXT);
            CREATE TABLE prostudio_error_reports(id BIGINT);
            CREATE TABLE prostudio_errors(id BIGINT,telegram_id BIGINT,job_id TEXT,provider TEXT,model TEXT,status TEXT,error_text TEXT,created_at TIMESTAMP);
            INSERT INTO users VALUES(1,'Synthetic','synthetic',101,'starter',NOW());
            INSERT INTO user_credit_wallets VALUES(1,51,50);
            INSERT INTO subscriptions(telegram_id,charge_id,status,expires_at) VALUES(1,'in_live','active',NOW()+interval '1 day');''')
        stripe.ensure_tables(d.connect)
        yield d
    finally:
        d.close()


def event(eid='evt_synthetic', typ='invoice.paid', mode=False, obj=None):
    return {'id': eid, 'type': typ, 'livemode': mode, 'data': {'object': obj or {'id': 'in_synthetic'}}}


@pytest.mark.parametrize('typ,obj,expected', [
    ('invoice.paid', {'id': 'in_synthetic'}, 'in_synthetic'),
    ('checkout.session.completed', {'id': 'cs_synthetic','mode':'payment','payment_intent':'pi_synthetic'}, 'pi_synthetic'),
    ('checkout.session.async_payment_succeeded', {'id':'cs_synthetic','payment_intent':{'id':'pi_expanded'}}, 'pi_expanded'),
    ('checkout.session.completed', {'id':'cs_fallback','mode':'payment'}, 'cs_fallback'),
    ('checkout.session.completed', {'id':'cs_subscription','mode':'subscription','payment_intent':'pi_ignored'}, None),
    ('invoice.payment_failed', {'id':'in_failed'}, None),
])
def test_verified_payment_provenance_uses_actual_canonical_charge(db, typ, obj, expected):
    stripe.record_event(db.connect, event(typ=typ,obj=obj), 'granted')
    assert q(db, 'SELECT livemode,purchase_charge_id FROM stripe_events') == [[False, expected]]


@pytest.mark.parametrize('mode,expected', [(True,True),(False,False),(None,None),('false',None),(0,None)])
def test_only_explicit_boolean_mode_can_confirm_cash(db, mode, expected):
    stripe.record_event(db.connect, event(mode=mode), 'duplicate')
    assert q(db,'SELECT livemode FROM stripe_events') == [[expected]]


def test_duplicate_journal_cannot_reclassify_applied_payment(db):
    stripe.record_event(db.connect,event(mode=False),'granted')
    stripe.record_event(db.connect,event(mode=True),'duplicate')
    assert q(db,'SELECT outcome,livemode,purchase_charge_id FROM stripe_events') == [['granted',False,'in_synthetic']]
    assert stripe.event_processed(db.connect,'evt_synthetic')
    assert not stripe.event_processed(db.connect,'evt_absent')


def test_old_journal_upgrade_is_nullable_idempotent_and_preserves_history(db):
    q(db, 'DROP TABLE stripe_events; CREATE TABLE stripe_events(event_id TEXT PRIMARY KEY,event_type TEXT NOT NULL,outcome TEXT,processed_at TIMESTAMP DEFAULT NOW()); INSERT INTO stripe_events VALUES(\'evt_old\',\'invoice.paid\',\'granted\',\'2026-01-01\')')
    stripe.ensure_tables(db.connect);stripe.ensure_tables(db.connect)
    assert q(db,'SELECT event_id,outcome,processed_at::date::text,livemode,purchase_charge_id FROM stripe_events') == [['evt_old','granted','2026-01-01',None,None]]
    assert stripe.event_processed(db.connect,'evt_old')


def add(db, charge, provider='stripe', amount=1001, currency='USD', uid=1, status='completed', credits=100, at=None):
    if at is None:
        q(db,'INSERT INTO purchases(telegram_id,provider,amount,currency,charge_id,status,credits) VALUES(%s,%s,%s,%s,%s,%s,%s)',(uid,provider,amount,currency,charge,status,credits))
    else:
        q(db,'INSERT INTO purchases(telegram_id,provider,amount,currency,charge_id,status,credits,created_at) VALUES(%s,%s,%s,%s,%s,%s,%s,%s)',(uid,provider,amount,currency,charge,status,credits,at))


def classify(db):
    with db.connect() as c:
        with c.cursor() as cur:
            mode=reporting.payment_mode_sql(cur)
            cur.execute('SELECT p.charge_id,'+mode+','+reporting.payment_amount_sql()+' FROM purchases p ORDER BY p.id')
            return {r[0]:(r[1],float(r[2])) for r in cur.fetchall()}


def mark(db,charge,live,eid=None):
    stripe.record_event(db.connect,event(eid=eid or 'evt_'+charge,mode=live,obj={'id':charge}),'granted')


def test_cash_classifier_handles_real_test_unknown_conflicting_and_retired_records(db):
    for charge in ['in_live','in_test','in_null','in_conflict','in_partial','in_old_test','in_old_unknown','in_conflict_old','in_fake_live']:
        add(db,charge)
    mark(db,'in_live',True);mark(db,'in_test',False);mark(db,'in_null',None)
    mark(db,'in_conflict',True);mark(db,'in_conflict',False,'evt_second')
    mark(db,'in_partial',True);mark(db,'in_partial',None,'evt_partial')
    mark(db,'in_conflict_old',True)
    q(db,"INSERT INTO shop_orders VALUES('in_old_test','cs_test_synthetic'),('in_conflict_old','cs_test_conflict'),('in_fake_live','cs_live_not_evidence')")
    add(db,'stars','telegram_stars',150,'XTR');add(db,'stars_subscription','telegram_stars_subscription',75,'XTR')
    add(db,'dev','dev',10,'USD');add(db,'mock','stripe',10,'DEV')
    add(db,'retired','legacy_retired',42,'USD')
    got=classify(db)
    assert got['in_live']==('live',10.01) and got['in_test']==('test',10.01)
    assert got['in_old_test'][0]=='test'
    for name in ['in_null','in_conflict','in_partial','in_old_unknown','in_conflict_old','in_fake_live','retired']:
        assert got[name][0]=='unknown', (name,got[name])
    assert got['stars']==('live',150) and got['stars_subscription']==('live',75)
    assert got['dev']==('test',10)
    # An impossible Stripe DEV record has no signed mode and stays unknown.
    assert got['mock'][0]=='unknown'


@pytest.mark.parametrize('drop', ['stripe_events','shop_orders','both'])
def test_partial_upgrade_never_infers_live_or_breaks_reporting(db,drop):
    if drop in ('stripe_events','both'):q(db,'DROP TABLE stripe_events')
    if drop in ('shop_orders','both'):q(db,'DROP TABLE shop_orders')
    add(db,'pi_unverified')
    assert classify(db)['pi_unverified']==('unknown',10.01)


def snapshot(db):
    return [q(db,'SELECT row_to_json(t)::text FROM '+table+' t ORDER BY 1') for table in ['users','user_credit_wallets','purchases','subscriptions','shop_orders']]


class Request:
    def __init__(self,**payload):self.payload=payload
    async def json(self):return dict(self.payload)


def prepare_handlers(db,monkeypatch):
    import main
    def readonly(_):
        c=db.connect();c.c.set_session(readonly=True);return c
    monkeypatch.setattr(main,'db_connect',readonly)
    monkeypatch.setattr(main,'_admin_actor',lambda *a,**k: {})
    for name in ['ensure_admin_tables','ensure_payment_tables','ensure_prostudio_table']:
        monkeypatch.setattr(main,name,lambda:None)
    monkeypatch.setattr(main,'_admin_technical',lambda *a:False)
    monkeypatch.setattr(main,'_public_actor',lambda *a:{})
    monkeypatch.setattr(main.admin_identity,'decorate',lambda c,items,**kw:items)
    return main


def seed_reports(db):
    add(db,'in_live');mark(db,'in_live',True)
    add(db,'in_eur',amount=2025,currency='EUR',uid=2,credits=200);mark(db,'in_eur',True)
    add(db,'in_test',amount=5000,uid=3,credits=500);mark(db,'in_test',False)
    add(db,'pi_old',amount=6000,uid=4);q(db,"INSERT INTO shop_orders VALUES('pi_old','cs_test_old')")
    add(db,'in_unknown',amount=7000,uid=5)
    add(db,'stars','telegram_stars',150,'XTR',uid=6,credits=150)
    add(db,'dev','dev',800,'DEV',uid=7)
    add(db,'retired','legacy_retired',12345,'USD',uid=8)
    add(db,'in_bad_date',amount=9999,at='2026-02-30');mark(db,'in_bad_date',True)
    add(db,'in_refund_live',amount=250,status='refunded');mark(db,'in_refund_live',True)
    add(db,'in_refund_test',amount=350,status='refunded');mark(db,'in_refund_test',False)
    add(db,'in_refund_unknown',amount=450,status='refunded')
    q(db,"INSERT INTO admin_audit_events VALUES('balance_changed','{\"delta\":25,\"reason_code\":\"gift\"}',NOW())")


@pytest.mark.asyncio
async def test_actual_finance_endpoint_separates_modes_in_readonly_transaction(db,monkeypatch):
    seed_reports(db);main=prepare_handlers(db,monkeypatch);before=snapshot(db)
    result=await main.admin_finance(Request(days=30))
    assert result['ok']
    assert result['revenue']=={'USD':10.01,'EUR':20.25,'XTR':150}
    assert result['buyers']==3 and result['new_buyers']==3
    assert result['credits']['sold']==450 and result['credits']['granted']==25
    assert sum(r['count'] for r in result['test_payments'])==3
    assert sum(r['count'] for r in result['unknown_payments'])==2
    assert sum(d['payments'] for d in result['days'])==3
    assert sum(r['amount'] for r in result['refunds'])==2.5
    assert sum(r['amount'] for r in result['test_refunds'])==3.5
    assert sum(r['amount'] for r in result['unknown_refunds'])==4.5
    assert snapshot(db)==before


@pytest.mark.asyncio
async def test_actual_dashboard_and_recorded_spending_use_consistent_units_without_rewriting_rows(db,monkeypatch):
    seed_reports(db);main=prepare_handlers(db,monkeypatch);before=snapshot(db)
    result=await main.admin_dashboard(Request())
    # Dashboard is all-time; the period-only finance report excludes the bad date.
    assert result['stats']['revenue_by_currency']=={'USD':110.0,'EUR':20.25,'XTR':150}
    assert result['stats']['purchases_total']==9
    top=await main.admin_top_spenders(Request())
    by_id={r['telegram_id']:r for r in top['items']}
    assert by_id[3]['spent_by_currency']=={'USD':50.0}
    assert by_id[6]['spent_by_currency']=={'XTR':150.0}
    assert snapshot(db)==before


@pytest.mark.parametrize('live', [False,True])
def test_opposite_mode_event_is_ignored_before_any_grant_and_duplicate_behavior_is_preserved(db,monkeypatch,live):
    import main
    monkeypatch.setattr(main,'shop_db',db.connect)
    monkeypatch.setattr(main,'ensure_stripe_tables',lambda:None)
    monkeypatch.setattr(main,'stripe_client',lambda:stripe.StripeClient('sk_live_synthetic' if live else 'sk_test_synthetic'))
    def forbidden(*a,**kw):raise AssertionError('wrong mode must not reach billing')
    monkeypatch.setattr(stripe,'handle_event',forbidden)
    opposite=event(mode=not live)
    before=snapshot(db)
    assert main.process_stripe_event(opposite)=={'outcome':'ignored','reason':'mode_mismatch'}
    assert main.process_stripe_event(opposite)=={'outcome':'duplicate_event'}
    assert q(db,'SELECT livemode,purchase_charge_id,outcome FROM stripe_events')==[[not live,None,'ignored_mode_mismatch']]
    assert snapshot(db)==before


def test_invalid_dynamic_alias_is_rejected_without_sql(db):
    with db.connect() as c:
        with c.cursor() as cur:
            for f in [lambda:reporting.payment_mode_sql(cur,'p; DROP TABLE purchases'),lambda:reporting.payment_amount_sql('p.--')]:
                with pytest.raises(ValueError):f()
    assert q(db,'SELECT COUNT(*) FROM users')==[[1]]
