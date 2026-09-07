"""Transactional additions around existing tariffs and accounting tables."""
from __future__ import annotations
from services.security import SecurityError

def ensure_reservations(connect):
 with connect() as conn:
  with conn.cursor() as cur:
   cur.execute('''CREATE TABLE IF NOT EXISTS generation_reservations (
    generation_id TEXT PRIMARY KEY, telegram_id BIGINT NOT NULL,
    credits INTEGER NOT NULL CHECK (credits>=0), status TEXT NOT NULL DEFAULT 'reserved',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW())''')

def reserve_generation(cur,uid,job_id,credits):
 credits=max(0,int(credits))
 if not credits:return
 cur.execute('UPDATE users SET balance=COALESCE(balance,0)-%s WHERE telegram_id=%s AND COALESCE(balance,0)>=%s RETURNING balance',(credits,uid,credits))
 if cur.fetchone() is None:raise SecurityError('insufficient_balance',402)
 cur.execute('INSERT INTO generation_reservations(generation_id,telegram_id,credits) VALUES(%s,%s,%s)',(job_id,uid,credits))

def release_generation(cur,job_id):
 # Lock user before reservation, consistently with settlement/admission.
 cur.execute('SELECT u.telegram_id FROM users u JOIN generation_reservations r ON r.telegram_id=u.telegram_id WHERE r.generation_id=%s FOR UPDATE OF u',(job_id,))
 cur.execute("UPDATE generation_reservations SET status='released' WHERE generation_id=%s AND status='reserved' RETURNING telegram_id,credits",(job_id,))
 row=cur.fetchone()
 if row:cur.execute('UPDATE users SET balance=COALESCE(balance,0)+%s WHERE telegram_id=%s',(row[1],row[0]))

def settle_generation(connect,uid,job_id,credits,payload,result):
 credits=max(0,int(credits))
 with connect() as conn:
  with conn.cursor() as cur:
   cur.execute('SELECT COALESCE(balance,0) FROM users WHERE telegram_id=%s FOR UPDATE',(uid,));user=cur.fetchone()
   if not user:raise SecurityError('user_not_found',404)
   cur.execute('SELECT credits,balance_after FROM generation_charges WHERE generation_id=%s',(job_id,));existing=cur.fetchone()
   if existing:return {'charged':False,'already_charged':True,'credits':existing[0],'balance_after':existing[1]}
   cur.execute("SELECT credits FROM generation_reservations WHERE generation_id=%s AND telegram_id=%s AND status='reserved' FOR UPDATE",(job_id,uid));hold=cur.fetchone();reserved=int(hold[0]) if hold else 0
   if credits>int(user[0])+reserved:raise SecurityError('insufficient_balance',402)
   if not credits and not reserved:return {'charged':False,'credits':0,'balance_after':int(user[0])}
   balance=int(user[0])+reserved-credits
   cur.execute('UPDATE users SET balance=%s WHERE telegram_id=%s',(balance,uid))
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
    cur.execute('UPDATE users SET subscription=%s,balance=COALESCE(balance,0)+%s WHERE telegram_id=%s',(item['plan_key'],bonus,uid))
   else:cur.execute('UPDATE users SET balance=COALESCE(balance,0)+%s WHERE telegram_id=%s',(credits,uid))
   return True
