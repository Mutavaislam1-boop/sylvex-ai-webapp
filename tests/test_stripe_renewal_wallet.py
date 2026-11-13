"""S2-08: subscription renewals must stay in the existing split wallet.
Only synthetic SQL on a new disposable LOCAL database; no Stripe calls.
"""
import os,time
import pytest
from services import billing_safety as wallet,shop_catalog,stripe_billing as stripe
from tests.support.pglite_adapter import Database

UID=100042
pytestmark=pytest.mark.skipif(not(os.getenv('SYLVEX_TEST_NODE') and os.getenv('SYLVEX_PGLITE_MODULE')),reason='Configure the existing optional isolated SQL test harness')

@pytest.fixture
def renewal_db():
 db=Database()
 try:
  with db.connect() as c:
   with c.cursor() as cur:
    cur.execute('CREATE TABLE users(telegram_id BIGINT PRIMARY KEY,first_name TEXT,balance INTEGER DEFAULT 0,subscription TEXT)')
    cur.execute('CREATE TABLE purchases(id SERIAL PRIMARY KEY,telegram_id BIGINT,provider TEXT,credits INTEGER,amount INTEGER,currency TEXT,payload TEXT,charge_id TEXT UNIQUE,status TEXT,created_at TIMESTAMP)')
    cur.execute('CREATE TABLE subscriptions(id SERIAL PRIMARY KEY,telegram_id BIGINT,subscription_type TEXT,payment_method TEXT,amount INTEGER,currency TEXT,expires_at TIMESTAMP,status TEXT,charge_id TEXT UNIQUE)')
    cur.execute("INSERT INTO users VALUES(%s,'Synthetic',50,'free')",(UID,))
  wallet.ensure_reservations(db.connect)
  assert wallet.wallet_snapshot(db.connect,UID)['purchased_credits']==50
  yield db
 finally:db.close()

def renew(db,period='month',invoice='in_synthetic',amount=None):
 product=shop_catalog.FIXED_PRODUCTS['plan_starter_'+period]
 start=int(time.time());end=start+int(product['days'])*86400
 result=stripe.grant_renewal(db.connect,{'telegram_id':UID,'plan_key':'starter_'+period},invoice,product['usd_cents'] if amount is None else amount,'USD',start,end)
 return result,product

@pytest.mark.parametrize('period',['month','year'])
def test_renewal_allocates_subscription_not_purchased(renewal_db,period):
 db=renewal_db;result,product=renew(db,period)
 state=wallet.wallet_snapshot(db.connect,UID)
 assert result['status']=='granted'
 assert state['purchased_credits']==50, state
 assert state['subscription_credits']==product['credits'],state
 assert state['subscription_expires_at'] is not None
 assert state['balance']==50+product['credits']

def test_duplicate_invoice_cannot_repeat_wallet_grant(renewal_db):
 db=renewal_db
 first,product=renew(db);before=wallet.wallet_snapshot(db.connect,UID)
 second,_=renew(db);after=wallet.wallet_snapshot(db.connect,UID)
 assert first['status']=='granted' and second['status']=='duplicate'
 assert after==before
 with db.connect() as c:
  with c.cursor() as cur:
   cur.execute('SELECT count(*) FROM purchases');assert cur.fetchone()[0]==1
   cur.execute('SELECT count(*) FROM subscriptions');assert cur.fetchone()[0]==1

def test_expiry_of_renewal_preserves_purchased_credits(renewal_db):
 db=renewal_db;renew(db)
 with db.connect() as c:
  with c.cursor() as cur:cur.execute("UPDATE user_credit_wallets SET subscription_expires_at=NOW()-INTERVAL '1 second'")
 after=wallet.wallet_snapshot(db.connect,UID)
 assert (after['purchased_credits'],after['subscription_credits'],after['balance'])==(50,0,50),after

def test_wrong_renewal_amount_changes_nothing(renewal_db):
 db=renewal_db;before=wallet.wallet_snapshot(db.connect,UID)
 result,_=renew(db,amount=1)
 assert result=={'status':'rejected','reason':'amount_mismatch'}
 assert wallet.wallet_snapshot(db.connect,UID)==before

def test_reconciliation_failure_rolls_back_renewal_and_payment(renewal_db,monkeypatch):
 db=renewal_db
 def fail(*a,**kw):raise RuntimeError('synthetic wallet update failure')
 monkeypatch.setattr(wallet,'grant_credits',fail)
 with pytest.raises(RuntimeError,match='synthetic wallet update failure'):renew(db)
 with db.connect() as c:
  with c.cursor() as cur:
   cur.execute('SELECT balance FROM users');assert cur.fetchone()[0]==50
   cur.execute('SELECT count(*) FROM purchases');assert cur.fetchone()[0]==0
   cur.execute('SELECT count(*) FROM subscriptions');assert cur.fetchone()[0]==0

def test_expired_previous_allocation_is_not_revived_on_renewal(renewal_db):
 db=renewal_db
 with db.connect() as c:
  with c.cursor() as cur:
   cur.execute("UPDATE user_credit_wallets SET subscription_credits=900,subscription_expires_at=NOW()-INTERVAL '1 second'")
   cur.execute('UPDATE users SET balance=950')
 result,product=renew(db)
 after=wallet.wallet_snapshot(db.connect,UID)
 assert result['status']=='granted'
 assert (after['purchased_credits'],after['subscription_credits'],after['balance'])==(50,product['credits'],50+product['credits']),after

def test_legacy_balance_without_wallet_row_can_renew(renewal_db):
 db=renewal_db
 with db.connect() as c:
  with c.cursor() as cur:cur.execute('DELETE FROM user_credit_wallets')
 result,product=renew(db)
 after=wallet.wallet_snapshot(db.connect,UID)
 assert result['status']=='granted'
 assert (after['purchased_credits'],after['subscription_credits'],after['balance'])==(50,product['credits'],50+product['credits']),after
