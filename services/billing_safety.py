"""Transactional additions around existing tariffs and accounting tables."""
from __future__ import annotations
import contextlib
import contextvars
from services.security import SecurityError

# Invariant: no billable provider dispatch without a SYLVEX price and a
# billing transaction. Every billed entry point (queued job, direct text,
# priced helper) opens billing_scope() after its credits are reserved; the
# low-level provider dispatchers call require_billing_scope() and refuse to
# run outside one. Internal calls of the same job (retries, polling,
# downloads, storage) run inside the job's single scope and are never
# charged again. contextvars follow asyncio tasks and asyncio.to_thread.
_BILLING_SCOPE = contextvars.ContextVar('sylvex_billing_scope', default=None)


@contextlib.contextmanager
def billing_scope(generation_id, credits, *, free=False):
 """Mark provider dispatch as billed under generation_id.
 credits must be a known positive SYLVEX price unless the operation is
 explicitly free (local work such as pixel resize)."""
 generation_id=str(generation_id or '').strip()
 if not generation_id:raise SecurityError('billing_id_required',500)
 credits=int(credits or 0)
 if credits<=0 and not free:raise SecurityError('pricing_not_configured',402)
 token=_BILLING_SCOPE.set({'generation_id':generation_id,'credits':max(0,credits),'free':bool(free)})
 try:yield _BILLING_SCOPE.get()
 finally:_BILLING_SCOPE.reset(token)


def current_billing_scope():
 return _BILLING_SCOPE.get()


def require_billing_scope(operation):
 scope=_BILLING_SCOPE.get()
 if scope is None:
  print('UNBILLED_PROVIDER_DISPATCH_BLOCKED:',{'operation':str(operation)})
  raise SecurityError('unbilled_provider_dispatch',402)
 return scope


def assert_reserved(cur,job_id,credits):
 """A queued job may dispatch only while its own reservation is held:
 never after release (failed/cancelled) or settlement (already charged)."""
 credits=max(0,int(credits or 0))
 cur.execute('SELECT credits,status FROM generation_reservations WHERE generation_id=%s',(job_id,))
 row=cur.fetchone()
 if not row or row[1]!='reserved' or int(row[0])<credits:
  raise SecurityError('billing_reservation_missing',402)

def ensure_reservations(connect):
 with connect() as conn:
  with conn.cursor() as cur:
   cur.execute('''CREATE TABLE IF NOT EXISTS generation_reservations (
    generation_id TEXT PRIMARY KEY, telegram_id BIGINT NOT NULL,
    credits INTEGER NOT NULL CHECK (credits>=0), status TEXT NOT NULL DEFAULT 'reserved',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW())''')
   cur.execute("ALTER TABLE generation_reservations ADD COLUMN IF NOT EXISTS subscription_credits INTEGER NOT NULL DEFAULT 0")
   cur.execute("ALTER TABLE generation_reservations ADD COLUMN IF NOT EXISTS purchased_credits INTEGER NOT NULL DEFAULT 0")
   cur.execute("ALTER TABLE generation_reservations ADD COLUMN IF NOT EXISTS subscription_expires_at TIMESTAMPTZ")
   cur.execute('''CREATE TABLE IF NOT EXISTS user_credit_wallets (
    telegram_id BIGINT PRIMARY KEY REFERENCES users(telegram_id) ON DELETE CASCADE,
    purchased_credits INTEGER NOT NULL DEFAULT 0 CHECK (purchased_credits>=0),
    subscription_credits INTEGER NOT NULL DEFAULT 0 CHECK (subscription_credits>=0),
    subscription_expires_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW())''')


def _ensure_wallet(cur,uid,*,include_expiry_state=False):
 """Create/synchronise the split wallet without losing legacy balances."""
 cur.execute('SELECT COALESCE(balance,0) FROM users WHERE telegram_id=%s FOR UPDATE',(uid,))
 user=cur.fetchone()
 if not user:raise SecurityError('user_not_found',404)
 balance=max(0,int(user[0] or 0))
 cur.execute('''INSERT INTO user_credit_wallets(telegram_id,purchased_credits)
  VALUES(%s,%s) ON CONFLICT(telegram_id) DO NOTHING''',(uid,balance))
 cur.execute('''SELECT purchased_credits,subscription_credits,subscription_expires_at
  FROM user_credit_wallets WHERE telegram_id=%s FOR UPDATE''',(uid,))
 purchased,subscription,expires_at=cur.fetchone()
 purchased=max(0,int(purchased or 0));subscription=max(0,int(subscription or 0))
 # Legacy writers (including the bot) still change users.balance. Reconcile
 # their delta before expiry, using the same subscription-first priority as
 # an API debit. Otherwise an expired stale bucket can consume purchased funds.
 total=purchased+subscription
 if balance>total:
  purchased+=balance-total
 elif balance<total:
  missing=total-balance
  take=min(subscription,missing);subscription-=take;missing-=take
  if missing:purchased=max(0,purchased-missing)
 expired=False
 if expires_at is not None:
  cur.execute('SELECT %s::timestamptz <= NOW()',(expires_at,))
  expired=bool(cur.fetchone()[0])
  if expired:subscription=0;expires_at=None
 cur.execute('''UPDATE user_credit_wallets SET purchased_credits=%s,
  subscription_credits=%s,subscription_expires_at=%s,updated_at=NOW()
  WHERE telegram_id=%s''',(purchased,subscription,expires_at,uid))
 cur.execute('UPDATE users SET balance=%s WHERE telegram_id=%s',(purchased+subscription,uid))
 result=(purchased,subscription,expires_at)
 return (*result,expired) if include_expiry_state else result


def _set_wallet(cur,uid,purchased,subscription,expires_at):
 purchased=max(0,int(purchased or 0));subscription=max(0,int(subscription or 0))
 cur.execute('''UPDATE user_credit_wallets SET purchased_credits=%s,
  subscription_credits=%s,subscription_expires_at=%s,updated_at=NOW()
  WHERE telegram_id=%s''',(purchased,subscription,expires_at,uid))
 cur.execute('UPDATE users SET balance=%s WHERE telegram_id=%s',(purchased+subscription,uid))


def _debit_wallet(cur,uid,credits):
 purchased,subscription,expires_at=_ensure_wallet(cur,uid)
 credits=max(0,int(credits or 0))
 if credits>purchased+subscription:raise SecurityError('insufficient_balance',402)
 from_subscription=min(subscription,credits)
 from_purchased=credits-from_subscription
 _set_wallet(cur,uid,purchased-from_purchased,subscription-from_subscription,expires_at)
 return from_subscription,from_purchased,purchased+subscription-credits


def grant_credits(cur,uid,credits,source='purchased',expires_at=None):
 """Grant credits into the correct bucket inside the caller transaction."""
 credits=max(0,int(credits or 0))
 purchased,subscription,current_expiry=_ensure_wallet(cur,uid)
 if source=='subscription':
  subscription+=credits
  if expires_at is not None:
   cur.execute('SELECT GREATEST(%s::timestamptz,%s::timestamptz)',(current_expiry,expires_at))
   current_expiry=cur.fetchone()[0]
 else:purchased+=credits
 _set_wallet(cur,uid,purchased,subscription,current_expiry)
 return {'purchased_credits':purchased,'subscription_credits':subscription,
         'subscription_expires_at':current_expiry,'balance':purchased+subscription}


def wallet_snapshot(connect,uid):
 with connect() as conn:
  with conn.cursor() as cur:
   purchased,subscription,expires_at=_ensure_wallet(cur,uid)
   return {'purchased_credits':purchased,'subscription_credits':subscription,
           'subscription_expires_at':expires_at,'balance':purchased+subscription}

def reserve_generation(cur,uid,job_id,credits):
 credits=max(0,int(credits))
 if not credits:return
 subscription,purchased,_balance=_debit_wallet(cur,uid,credits)
 cur.execute('SELECT subscription_expires_at FROM user_credit_wallets WHERE telegram_id=%s',(uid,))
 expires_at=cur.fetchone()[0]
 cur.execute('''INSERT INTO generation_reservations
  (generation_id,telegram_id,credits,subscription_credits,purchased_credits,subscription_expires_at)
  VALUES(%s,%s,%s,%s,%s,%s)''',(job_id,uid,credits,subscription,purchased,expires_at))

def _reservation_sources(credits,subscription,purchased):
 """Preserve unallocated pre-wallet holds as purchased, without minting funds."""
 credits=max(0,int(credits or 0))
 subscription=min(credits,max(0,int(subscription or 0)))
 purchased=credits-subscription
 return subscription,purchased

def _unexpired_subscription_return(cur,credits,reservation_expiry,wallet_expired):
 if not credits or wallet_expired:return 0
 if reservation_expiry is not None:
  cur.execute('SELECT %s::timestamptz > NOW()',(reservation_expiry,))
  if not cur.fetchone()[0]:return 0
 return credits

def release_generation(cur,job_id):
 # Lock user before reservation, consistently with settlement/admission.
 cur.execute('SELECT u.telegram_id FROM users u JOIN generation_reservations r ON r.telegram_id=u.telegram_id WHERE r.generation_id=%s FOR UPDATE OF u',(job_id,))
 cur.execute("""UPDATE generation_reservations SET status='released'
  WHERE generation_id=%s AND status='reserved'
  RETURNING telegram_id,credits,subscription_credits,purchased_credits,subscription_expires_at""",(job_id,))
 row=cur.fetchone()
 if row:
  purchased,subscription,expires_at,wallet_expired=_ensure_wallet(cur,row[0],include_expiry_state=True)
  reserved_subscription,reserved_purchased=_reservation_sources(row[1],row[2],row[3])
  reserved_subscription=_unexpired_subscription_return(cur,reserved_subscription,row[4],wallet_expired)
  _set_wallet(cur,row[0],purchased+reserved_purchased,subscription+reserved_subscription,expires_at)

def settle_generation(connect,uid,job_id,credits,payload,result):
 credits=max(0,int(credits))
 with connect() as conn:
  with conn.cursor() as cur:
   purchased,subscription,expires_at,wallet_expired=_ensure_wallet(cur,uid,include_expiry_state=True)
   cur.execute('SELECT credits,balance_after FROM generation_charges WHERE generation_id=%s',(job_id,));existing=cur.fetchone()
   if existing:return {'charged':False,'already_charged':True,'credits':existing[0],'balance_after':existing[1]}
   cur.execute("""SELECT credits,subscription_credits,purchased_credits,subscription_expires_at FROM generation_reservations
    WHERE generation_id=%s AND telegram_id=%s AND status='reserved' FOR UPDATE""",(job_id,uid))
   hold=cur.fetchone();reserved=int(hold[0]) if hold else 0
   if not credits and not reserved:return {'charged':False,'credits':0,'balance_after':purchased+subscription}
   if hold:
    held_subscription,held_purchased=_reservation_sources(reserved,hold[1],hold[2])
    # Settle from the hold itself, even when its period has ended. Only the
    # unused part is returned; it must not borrow a newer period's allocation.
    used_subscription=min(credits,held_subscription)
    used_purchased=min(max(0,credits-used_subscription),held_purchased)
    purchased+=held_purchased-used_purchased
    subscription+=_unexpired_subscription_return(cur,held_subscription-used_subscription,hold[3],wallet_expired)
    _set_wallet(cur,uid,purchased,subscription,expires_at)
    additional=max(0,credits-used_subscription-used_purchased)
    if additional:
     _sub_used,_purchased_used,balance=_debit_wallet(cur,uid,additional)
    else:balance=purchased+subscription
   else:
    _sub_used,_purchased_used,balance=_debit_wallet(cur,uid,credits)
   cur.execute('''INSERT INTO generation_charges(generation_id,telegram_id,mode,model,provider,credits,balance_after)
    VALUES(%s,%s,%s,%s,%s,%s,%s)''',(job_id,uid,payload.get('mode') or payload.get('category') or result.get('type') or '',payload.get('model') or result.get('model') or '',payload.get('provider') or result.get('provider') or '',credits,balance))
   if hold:cur.execute("UPDATE generation_reservations SET status='charged' WHERE generation_id=%s",(job_id,))
   return {'charged':True,'credits':credits,'balance_after':balance}

def apply_payment(connect,uid,provider,item,amount,currency,payload,charge_id):
 if not charge_id:raise SecurityError('payment_charge_id_required',400)
 credits=int(item.get('credits') or 0);bonus=int(item.get('bonus_credits') or 0)
 with connect() as conn:
  with conn.cursor() as cur:
   cur.execute('SELECT telegram_id FROM users WHERE telegram_id=%s FOR UPDATE',(uid,))
   if not cur.fetchone():raise SecurityError('user_not_found',404)
   cur.execute('''INSERT INTO purchases(telegram_id,provider,credits,amount,currency,payload,charge_id,status)
    VALUES(%s,%s,%s,%s,%s,%s,%s,'completed') ON CONFLICT(charge_id) DO NOTHING RETURNING id''',(uid,provider,credits or bonus,amount,currency,payload,charge_id))
   if not cur.fetchone():return False
   if item['kind']=='subscription':
    cur.execute('''INSERT INTO subscriptions(telegram_id,subscription_type,payment_method,amount,currency,expires_at,status,charge_id)
     VALUES(%s,%s,%s,%s,%s,(SELECT GREATEST(CURRENT_TIMESTAMP,COALESCE(MAX(expires_at::timestamp),CURRENT_TIMESTAMP))+(%s || ' days')::interval FROM subscriptions WHERE telegram_id=%s AND status='active' AND expires_at::timestamp>CURRENT_TIMESTAMP),'active',%s)
     RETURNING id''',(uid,item['plan_key'],provider,amount,currency,item['days'],uid,charge_id))
    subscription_id=cur.fetchone()[0]
    cur.execute("UPDATE subscriptions SET status='cancelled' WHERE telegram_id=%s AND status='active' AND id<>%s",(uid,subscription_id))
    cur.execute('UPDATE users SET subscription=%s WHERE telegram_id=%s',(item['plan_key'],uid))
    cur.execute('SELECT expires_at FROM subscriptions WHERE id=%s',(subscription_id,))
    grant_credits(cur,uid,bonus,'subscription',cur.fetchone()[0])
   else:grant_credits(cur,uid,credits,'purchased')
   return True
