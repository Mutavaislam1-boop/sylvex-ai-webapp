"""Synthetic balances only. Expected behavior from the accepted launch checklist."""
import os
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import psycopg2
import pytest
from services import billing_safety as billing

pytestmark = pytest.mark.skipif(not os.getenv("SYLVEX_TEST_DATABASE_URL"), reason="Set SYLVEX_TEST_DATABASE_URL to a disposable wallet_fix_test_ database")

@pytest.fixture
def connect():
    url = os.environ['SYLVEX_TEST_DATABASE_URL']
    def factory():
        c = psycopg2.connect(url)
        assert c.get_dsn_parameters()['dbname'].startswith('wallet_fix_test_')
        return c
    with factory() as c:
        with c.cursor() as q:
            q.execute('DROP TABLE IF EXISTS user_credit_wallets,generation_reservations,generation_charges,users CASCADE')
            q.execute('CREATE TABLE users(telegram_id BIGINT PRIMARY KEY,balance INTEGER,subscription TEXT)')
            q.execute('CREATE TABLE generation_charges(generation_id TEXT UNIQUE,telegram_id BIGINT,mode TEXT,model TEXT,provider TEXT,credits INTEGER,balance_after INTEGER)')
            q.execute("INSERT INTO users VALUES(101,120,'pro_month')")
    billing.ensure_reservations(factory)
    with factory() as c:
        with c.cursor() as q:
            q.execute("INSERT INTO user_credit_wallets(telegram_id,purchased_credits,subscription_credits,subscription_expires_at) VALUES(101,20,100,NOW()+INTERVAL '1 day')")
    return factory

def reserve(connect, key='test-job', credits=80):
    with connect() as c:
        with c.cursor() as q: billing.reserve_generation(q, 101, key, credits)

def expire(connect):
    with connect() as c:
        with c.cursor() as q:
            q.execute("UPDATE user_credit_wallets SET subscription_expires_at=NOW()-INTERVAL '1 second' WHERE telegram_id=101")

def test_api_debits_subscription_before_purchased(connect):
    reserve(connect)
    wallet = billing.wallet_snapshot(connect, 101)
    assert (wallet['purchased_credits'],wallet['subscription_credits']) == (20,20)

def test_legacy_bot_debit_must_not_spend_purchased_first(connect):
    # Exact legacy BotCharge balance update, without a provider or bot request.
    with connect() as c:
        with c.cursor() as q: q.execute('UPDATE users SET balance=balance-80 WHERE telegram_id=101 AND balance>=80')
    wallet = billing.wallet_snapshot(connect, 101)
    assert (wallet['purchased_credits'],wallet['subscription_credits']) == (20,20)

def test_expired_refund_must_not_reactivate_subscription_credits(connect):
    reserve(connect); expire(connect)
    with connect() as c:
        with c.cursor() as q: billing.release_generation(q, 'test-job')
    wallet = billing.wallet_snapshot(connect, 101)
    assert wallet['purchased_credits'] == 20
    assert wallet['subscription_credits'] == 0
    assert wallet['balance'] == 20

def test_expired_settlement_remainder_must_not_become_permanent(connect):
    reserve(connect); expire(connect)
    billing.settle_generation(connect,101,'test-job',60,{'mode':'image'}, {})
    wallet = billing.wallet_snapshot(connect,101)
    assert wallet['purchased_credits'] == 20
    assert wallet['subscription_credits'] == 0
    assert wallet['balance'] == 20

def test_duplicate_refund_is_applied_once(connect):
    reserve(connect)
    for _ in range(2):
        with connect() as c:
            with c.cursor() as q: billing.release_generation(q,'test-job')
    assert billing.wallet_snapshot(connect,101)['balance'] == 120

def test_two_concurrent_reservations_cannot_double_spend(connect):
    def run(key):
        try: reserve(connect,key,80); return True
        except Exception: return False
    with ThreadPoolExecutor(max_workers=2) as pool: success=list(pool.map(run,['one','two']))
    assert sum(success) == 1
    assert billing.wallet_snapshot(connect,101)['balance'] == 40

def test_topup_after_legacy_bot_debit_must_not_restore_spent_credits(connect):
    from services.shop_orders import _add_credits
    with connect() as c:
        with c.cursor() as q:
            q.execute('UPDATE users SET balance=balance-80 WHERE telegram_id=101')
            _add_credits(q,101,10,'purchased')
            q.execute('SELECT balance FROM users WHERE telegram_id=101')
            assert q.fetchone()[0] == 50

def test_renewal_must_not_revive_expired_subscription_allocation(connect):
    from services.shop_orders import _add_credits
    expire(connect)
    with connect() as c:
        with c.cursor() as q:
            q.execute("SELECT NOW()+INTERVAL '30 days'");new_expiry=q.fetchone()[0]
            _add_credits(q,101,100,'subscription',new_expiry)
            q.execute('SELECT balance FROM users WHERE telegram_id=101')
            assert q.fetchone()[0] == 120

def wallet_amounts(connect):
    w = billing.wallet_snapshot(connect,101)
    return w['purchased_credits'],w['subscription_credits'],w['balance']

def expire_hold(connect,key='test-job'):
    with connect() as c:
        with c.cursor() as q:
            q.execute("UPDATE generation_reservations SET subscription_expires_at=NOW()-INTERVAL '1 second' WHERE generation_id=%s",(key,))
    expire(connect)

def release(connect,key='test-job'):
    with connect() as c:
        with c.cursor() as q: billing.release_generation(q,key)

def renew(connect):
    from services.shop_orders import _add_credits
    with connect() as c:
        with c.cursor() as q:
            q.execute("SELECT NOW()+INTERVAL '30 days'")
            _add_credits(q,101,100,'subscription',q.fetchone()[0])

def test_reservation_records_original_subscription_deadline(connect):
    reserve(connect)
    with connect() as c:
        with c.cursor() as q:
            q.execute('SELECT r.subscription_expires_at=w.subscription_expires_at FROM generation_reservations r JOIN user_credit_wallets w USING(telegram_id)')
            assert q.fetchone()[0] is True

@pytest.mark.parametrize('action',['release','settle'])
def test_old_period_hold_never_enters_a_new_period(connect,action):
    reserve(connect);expire_hold(connect);renew(connect)
    if action=='release':release(connect)
    else:billing.settle_generation(connect,101,'test-job',60,{}, {})
    assert wallet_amounts(connect)==(20,100,120)

@pytest.mark.parametrize('expired',[False,True])
@pytest.mark.parametrize('actual,expected',[(0,(20,100,120)),(90,(20,10,30)),(105,(15,0,15)),(110,(10,0,10)),(115,(5,0,5))])
def test_mixed_hold_settles_from_original_sources(connect,expired,actual,expected):
    reserve(connect,credits=110)
    if expired:expire_hold(connect)
    billing.settle_generation(connect,101,'test-job',actual,{}, {})
    if expired:
        # The unused portion of the original subscription allocation expires.
        expected=(expected[0],0,expected[0])
    assert wallet_amounts(connect)==expected
    again=billing.settle_generation(connect,101,'test-job',actual,{}, {})
    assert again['already_charged'] is True
    release(connect)
    assert wallet_amounts(connect)==expected

def test_expired_mixed_refund_preserves_purchased_credits(connect):
    reserve(connect,credits=110);expire_hold(connect);release(connect)
    assert wallet_amounts(connect)==(20,0,20)

def test_expired_purchase_only_refund_is_preserved(connect):
    expire(connect);billing.wallet_snapshot(connect,101)
    reserve(connect,credits=15);release(connect)
    assert wallet_amounts(connect)==(20,0,20)

def test_failed_additional_charge_rolls_back_hold_and_wallet(connect):
    reserve(connect)
    with pytest.raises(Exception) as error:
        billing.settle_generation(connect,101,'test-job',121,{}, {})
    assert str(error.value)=='insufficient_balance'
    assert wallet_amounts(connect)==(20,20,40)
    with connect() as c:
        with c.cursor() as q:
            q.execute("SELECT status FROM generation_reservations WHERE generation_id='test-job'")
            assert q.fetchone()[0]=='reserved'
            q.execute('SELECT COUNT(*) FROM generation_charges')
            assert q.fetchone()[0]==0

def test_legacy_debit_before_expiry_preserves_purchased_bucket(connect):
    with connect() as c:
        with c.cursor() as q:q.execute('UPDATE users SET balance=balance-80 WHERE telegram_id=101')
    expire(connect)
    assert wallet_amounts(connect)==(20,0,20)

def test_grant_and_reservation_are_serialized(connect):
    from services.shop_orders import _add_credits
    def topup():
        with connect() as c:
            with c.cursor() as q:_add_credits(q,101,10,'purchased')
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures=[pool.submit(topup),pool.submit(reserve,connect)]
        for future in futures:future.result()
    assert wallet_amounts(connect)==(30,20,50)

def test_legacy_unallocated_hold_remains_refundable(connect):
    with connect() as c:
        with c.cursor() as q:
            q.execute('UPDATE users SET balance=40 WHERE telegram_id=101')
            q.execute('UPDATE user_credit_wallets SET purchased_credits=20,subscription_credits=20 WHERE telegram_id=101')
            q.execute("INSERT INTO generation_reservations(generation_id,telegram_id,credits) VALUES('legacy',101,80)")
    release(connect,'legacy')
    assert wallet_amounts(connect)==(100,20,120)

@pytest.mark.parametrize('action',['release','settle'])
def test_old_writer_gets_expiry_during_rolling_deployment(connect,action):
    migration=Path(__file__).resolve().parents[1]/'migrations/20261107_wallet_reservation_expiry.sql'
    with connect() as c:
        with c.cursor() as q:
            q.execute(migration.read_text())
            # Old writer omits the new field; trigger captures the original period.
            q.execute('UPDATE users SET balance=40 WHERE telegram_id=101')
            q.execute('UPDATE user_credit_wallets SET subscription_credits=20 WHERE telegram_id=101')
            q.execute("INSERT INTO generation_reservations(generation_id,telegram_id,credits,subscription_credits,purchased_credits) VALUES('test-job',101,80,80,0)")
            q.execute('SELECT subscription_expires_at IS NOT NULL FROM generation_reservations')
            assert q.fetchone()[0] is True
    expire_hold(connect);renew(connect)
    if action=='release':release(connect)
    else:billing.settle_generation(connect,101,'test-job',60,{}, {})
    assert wallet_amounts(connect)==(20,100,120)
