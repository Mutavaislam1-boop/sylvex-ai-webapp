import os
from pathlib import Path
import sys
import pytest
from services.billing_safety import apply_payment,ensure_reservations,reserve_generation,release_generation,settle_generation

@pytest.fixture(scope='module')
def connect():
 if os.getenv('SYLVEX_TEST_DATABASE_URL'):
  import psycopg2
  # Only a disposable test database may be passed here.
  factory=lambda:psycopg2.connect(os.environ['SYLVEX_TEST_DATABASE_URL'])
  yield factory
 elif os.getenv('SYLVEX_PGLITE_MODULE'):
  sys.path.insert(0,str(Path(__file__).parent/'support'))
  from pglite_adapter import Database
  db=Database()
  yield db.connect
  db.close()
 else:pytest.skip('Set SYLVEX_TEST_DATABASE_URL to a disposable PostgreSQL database or configure PGlite')

@pytest.fixture(autouse=True)
def tables(connect):
 statements=[
 'DROP TABLE IF EXISTS generation_reservations,generation_charges,purchases,subscriptions,users CASCADE',
 'CREATE TABLE users(telegram_id BIGINT PRIMARY KEY,balance INTEGER,subscription TEXT)',
 'CREATE TABLE purchases(id SERIAL PRIMARY KEY,telegram_id BIGINT,provider TEXT,credits INTEGER,amount INTEGER,currency TEXT,payload TEXT,charge_id TEXT UNIQUE,status TEXT)',
 'CREATE TABLE subscriptions(id SERIAL PRIMARY KEY,telegram_id BIGINT,subscription_type TEXT,payment_method TEXT,amount INTEGER,currency TEXT,expires_at TIMESTAMP,status TEXT,charge_id TEXT UNIQUE)',
 'CREATE TABLE generation_charges(id SERIAL PRIMARY KEY,generation_id TEXT UNIQUE,telegram_id BIGINT,mode TEXT,model TEXT,provider TEXT,credits INTEGER,balance_after INTEGER)',
 'INSERT INTO users(telegram_id,balance) VALUES(101,100)',
 ]
 with connect() as conn:
  with conn.cursor() as cur:
   for sql in statements:cur.execute(sql)
 ensure_reservations(connect)

def scalar(connect,sql):
 with connect() as conn:
  with conn.cursor() as cur:cur.execute(sql);return cur.fetchone()[0]

def test_payment_retry_does_not_double_credit(connect):
 item={'kind':'credits','credits':50}
 assert apply_payment(connect,101,'stars',item,5,'XTR','payload','charge')
 assert not apply_payment(connect,101,'stars',item,5,'XTR','payload','charge')
 assert scalar(connect,'SELECT balance FROM users')==150
 assert scalar(connect,'SELECT COUNT(*) FROM purchases')==1

def test_payment_failure_rolls_back_purchase_and_can_retry(connect):
 # Bad subscription duration fails after INSERT purchase, exercising real PostgreSQL rollback.
 bad={'kind':'subscription','plan_key':'month','days':'bad duration','bonus_credits':40}
 with pytest.raises(Exception):apply_payment(connect,101,'stars',bad,5,'XTR','payload','charge')
 assert scalar(connect,'SELECT COUNT(*) FROM purchases')==0
 assert scalar(connect,'SELECT balance FROM users')==100
 assert apply_payment(connect,101,'stars',{**bad,'days':30},5,'XTR','payload','charge')
 assert scalar(connect,'SELECT balance FROM users')==140

def test_subscription_preserves_remaining_days_and_one_bonus(connect):
 item={'kind':'subscription','plan_key':'month','days':30,'bonus_credits':40}
 assert apply_payment(connect,101,'stars',item,5,'XTR','payload','one')
 assert apply_payment(connect,101,'stars',item,5,'XTR','payload','two')
 assert not apply_payment(connect,101,'stars',item,5,'XTR','payload','two')
 assert scalar(connect,'SELECT balance FROM users')==180
 assert scalar(connect,"SELECT COUNT(*) FROM subscriptions WHERE status='active'")==1
 assert float(scalar(connect,"SELECT EXTRACT(EPOCH FROM (MAX(expires_at)-CURRENT_TIMESTAMP))/86400 FROM subscriptions"))>59

def test_reserve_settle_and_duplicate(connect):
 with connect() as conn:
  with conn.cursor() as cur:reserve_generation(cur,101,'job',60)
 assert scalar(connect,'SELECT balance FROM users')==40
 result=settle_generation(connect,101,'job',50,{'mode':'image'}, {})
 assert result['charged'] and result['balance_after']==50
 duplicate=settle_generation(connect,101,'job',50,{}, {})
 assert duplicate['already_charged'] and scalar(connect,'SELECT balance FROM users')==50

def test_reserve_rejects_insufficient_balance_without_debit(connect):
 with pytest.raises(Exception):
  with connect() as conn:
   with conn.cursor() as cur:reserve_generation(cur,101,'job',101)
 assert scalar(connect,'SELECT balance FROM users')==100
 assert scalar(connect,'SELECT COUNT(*) FROM generation_reservations')==0

def test_failure_refunds_once(connect):
 with connect() as conn:
  with conn.cursor() as cur:reserve_generation(cur,101,'job',60)
 for _ in range(2):
  with connect() as conn:
   with conn.cursor() as cur:release_generation(cur,'job')
 assert scalar(connect,'SELECT balance FROM users')==100

def test_failure_after_charge_does_not_refund(connect):
 with connect() as conn:
  with conn.cursor() as cur:reserve_generation(cur,101,'job',60)
 settle_generation(connect,101,'job',60,{}, {})
 with connect() as conn:
  with conn.cursor() as cur:release_generation(cur,'job')
 assert scalar(connect,'SELECT balance FROM users')==40

def test_legacy_unreserved_job_charged_once(connect):
 assert settle_generation(connect,101,'legacy',20,{}, {})['charged']
 assert settle_generation(connect,101,'legacy',20,{}, {})['already_charged']
 assert scalar(connect,'SELECT balance FROM users')==80
