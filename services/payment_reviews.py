"""Shared LB-006 review journal. No automatic wallet or entitlement changes.

Keep identical in API services/payment_reviews.py and bot app/database/.
Only trusted provider adapters call receive/apply. New paid work consults
blocked_for inside its existing user-locked reservation transaction.
"""
from contextlib import contextmanager
import hashlib
import json
import re

PROVIDERS={'stripe','telegram_stars'}
DDL=(
"""CREATE TABLE IF NOT EXISTS financial_review_events(
 provider TEXT NOT NULL,livemode BOOLEAN NOT NULL,event_id TEXT NOT NULL,
 event_type TEXT NOT NULL,payload JSONB NOT NULL,payload_hash TEXT NOT NULL,
 status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN('pending','processed')),
 attempts INTEGER NOT NULL DEFAULT 0,last_error_class TEXT,
 received_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
 processed_at TIMESTAMPTZ,case_id TEXT,PRIMARY KEY(provider,livemode,event_id))""",
"CREATE INDEX IF NOT EXISTS financial_review_events_pending ON financial_review_events(next_attempt_at)WHERE status='pending'",
"""CREATE TABLE IF NOT EXISTS financial_review_cases(
 case_id TEXT PRIMARY KEY,provider TEXT NOT NULL,livemode BOOLEAN NOT NULL,
 charge_id TEXT NOT NULL,currency TEXT NOT NULL,telegram_id BIGINT,purchase_id BIGINT,order_id TEXT,
 payment_refs TEXT[] NOT NULL DEFAULT '{}',source TEXT,
 facts JSONB NOT NULL DEFAULT '{}',risk_hash TEXT NOT NULL,
 review_revision INTEGER NOT NULL DEFAULT 0,resolved_revision INTEGER NOT NULL DEFAULT 0,
 mapping_conflict BOOLEAN NOT NULL DEFAULT FALSE,manual_mapping_verified BOOLEAN NOT NULL DEFAULT FALSE,
 created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
 UNIQUE(provider,livemode,charge_id))""",
"CREATE INDEX IF NOT EXISTS financial_review_cases_pending ON financial_review_cases(telegram_id,updated_at)WHERE review_revision>resolved_revision",
"CREATE INDEX IF NOT EXISTS financial_review_cases_refs ON financial_review_cases USING GIN(payment_refs)",
"""CREATE TABLE IF NOT EXISTS financial_review_resolutions(
 resolution_id TEXT PRIMARY KEY,case_id TEXT NOT NULL REFERENCES financial_review_cases(case_id),
 review_revision INTEGER NOT NULL,telegram_id BIGINT,purchase_id BIGINT,
 operator TEXT NOT NULL,evidence TEXT NOT NULL,decision TEXT NOT NULL,
 source TEXT,credits INTEGER NOT NULL DEFAULT 0 CHECK(credits>=0),
 balance_before INTEGER,balance_after INTEGER,request_hash TEXT NOT NULL,
 created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),UNIQUE(case_id,review_revision))""",
"""CREATE TABLE IF NOT EXISTS payment_refund_requests(
 request_id TEXT PRIMARY KEY,provider TEXT NOT NULL,livemode BOOLEAN NOT NULL,
 charge_id TEXT NOT NULL,telegram_id BIGINT NOT NULL,purchase_id BIGINT NOT NULL,
 amount BIGINT NOT NULL CHECK(amount>0),currency TEXT NOT NULL,
 status TEXT NOT NULL CHECK(status IN('dispatching','pending_reconciliation','confirmed','not_refunded')),
 operator TEXT NOT NULL,evidence TEXT NOT NULL,last_error_class TEXT,
 created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
 UNIQUE(provider,livemode,charge_id))""",
)


class ReviewError(RuntimeError):
    pass


def canonical(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=True)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def identifier(value,required=True):
    if not isinstance(value,str)or not value or len(value)>256 or any(ord(c)<32 for c in value):
        if not required and value in(None,''):return None
        raise ReviewError('invalid_payment_identifier')
    return value


def amount(value):
    if isinstance(value,bool)or not isinstance(value,int)or value<0 or value>10**15:
        raise ReviewError('invalid_minor_unit_amount')
    return value


@contextmanager
def transaction(connect):
    resource=connect()
    try:
        with resource as conn:yield conn
    finally:
        if hasattr(resource,'close'):resource.close()


def ensure_tables(connect):
    with transaction(connect)as conn:
        with conn.cursor()as cur:
            for statement in DDL:cur.execute(statement)


def receive(connect,provider,livemode,event_id,event_type,payload):
    """Durable BEFORE acknowledgement/provider fetch. Payload is adapter-whitelisted."""
    if provider not in PROVIDERS or type(livemode)is not bool or(provider=='telegram_stars'and not livemode):raise ReviewError('invalid_provider_mode')
    identifier(event_id);identifier(event_type)
    encoded=canonical(payload);signature=digest(payload)
    if len(encoded)>16000:raise ReviewError('review_payload_too_large')
    with transaction(connect)as conn:
        with conn.cursor()as cur:
            cur.execute('''INSERT INTO financial_review_events(provider,livemode,event_id,event_type,payload,payload_hash)
                VALUES(%s,%s,%s,%s,%s::jsonb,%s)ON CONFLICT DO NOTHING''',
                (provider,livemode,event_id,event_type,encoded,signature))
            cur.execute('SELECT payload_hash,status FROM financial_review_events WHERE provider=%s AND livemode=%s AND event_id=%s',
                        (provider,livemode,event_id))
            stored,status=cur.fetchone()
            if stored!=signature:raise ReviewError('event_identity_conflict')
            return status


def failed(connect,provider,livemode,event_id,error):
    with transaction(connect)as conn:
        with conn.cursor()as cur:
            cur.execute('''UPDATE financial_review_events SET attempts=attempts+1,last_error_class=%s,
                next_attempt_at=NOW()+LEAST(300,5*POWER(2,LEAST(attempts,6)))::int*INTERVAL'1 second'
                WHERE provider=%s AND livemode=%s AND event_id=%s AND status='pending' ''',
                (type(error).__name__[:100],provider,livemode,event_id))


def pending_events(connect,provider,livemode,limit=50):
    with transaction(connect)as conn:
        with conn.cursor()as cur:
            cur.execute('''SELECT event_id,event_type,payload FROM financial_review_events
                WHERE provider=%s AND livemode=%s AND status='pending'AND next_attempt_at<=NOW()
                ORDER BY received_at,event_id LIMIT %s''',(provider,livemode,min(100,max(1,int(limit)))))
            return [dict(event_id=a,event_type=b,payload=c)for a,b,c in cur.fetchall()]


def _original(cur,provider,refs,order_id=None):
    """Exact local payment/order binding. Never bind by a claimed UID/customer alone."""
    cur.execute('''SELECT id,telegram_id,credits,amount,currency,payload,charge_id,status
        FROM purchases WHERE provider=%s AND charge_id=ANY(%s)''',(provider,list(refs)))
    purchases=cur.fetchall();order=None
    if not order_id and len(purchases)==1:
        text=str(purchases[0][5]or'')
        if re.fullmatch(r'sylvex_order:[0-9a-f]{32}',text):order_id=text.split(':',1)[1]
    if order_id:
        cur.execute('SELECT telegram_id,kind,credits,order_id FROM shop_orders WHERE order_id=%s AND provider=%s',
                    (order_id,provider));order=cur.fetchone()
    owners={int(p[1])for p in purchases}
    if order:owners.add(int(order[0]))
    if len(owners)>1 or len(purchases)>1:return {'conflict':True,'uid':None,'purchase':None,'source':None,'order_id':order_id}
    uid=next(iter(owners),None);purchase=purchases[0]if purchases else None
    source=('purchased'if order[1]=='credits'else'subscription')if order and order[1]in('credits','subscription')else None
    if purchase and source is None:
        cur.execute('SELECT 1 FROM subscriptions WHERE telegram_id=%s AND charge_id=%s LIMIT 1',(uid,purchase[6]))
        if cur.fetchone():source='subscription'
        elif str(purchase[5]or'').startswith(('sylvex_stars:','stripe_credit:')):source='purchased'
    return {'conflict':False,'uid':uid,'purchase':purchase,'source':source,'order_id':order_id}


def _merge_facts(previous,observation):
    facts=json.loads(canonical(previous or{}));facts.setdefault('refunds',{});facts.setdefault('disputes',{})
    facts.setdefault('cumulative_refunded',0);facts.setdefault('conflicts',[])
    if observation.get('cumulative_refunded')is not None:
        facts['cumulative_refunded']=max(facts['cumulative_refunded'],amount(observation['cumulative_refunded']))
    if observation.get('original_amount')is not None:
        original=amount(observation['original_amount'])
        if facts.get('original_amount')not in(None,original):facts['conflicts']=sorted(set(facts['conflicts']+['original_amount_conflict']))
        else:facts['original_amount']=original
    kind=observation['kind'];entity=identifier(observation.get('entity_id')or observation['charge_id'])
    value=amount(observation.get('amount',0));status=str(observation.get('status')or'')
    if kind=='refund'and status=='succeeded':facts['refunds'][entity]=max(facts['refunds'].get(entity,0),value)
    elif kind=='refund'and status in('failed','canceled')and entity in facts['refunds']:
        facts['conflicts']=sorted(set(facts['conflicts']+['refund_terminal_conflict:'+entity]))
    elif kind=='charge_refunded':facts['cumulative_refunded']=max(facts['cumulative_refunded'],value)
    elif kind=='dispute':
        previous_dispute=facts['disputes'].get(entity,{})
        old_status=previous_dispute.get('status');terminal={'won','lost','warning_closed'}
        if old_status in terminal and status not in terminal:status=old_status
        elif old_status in terminal and status in terminal and old_status!=status:
            facts['conflicts']=sorted(set(facts['conflicts']+['dispute_terminal_conflict:'+entity]))
            status=old_status
        facts['disputes'][entity]={'amount':max(previous_dispute.get('amount',0),value),'status':status,
            'funds_withdrawn':bool(previous_dispute.get('funds_withdrawn')or observation.get('funds_withdrawn')),
            'funds_reinstated':bool(previous_dispute.get('funds_reinstated')or observation.get('funds_reinstated'))}
    total=max(facts['cumulative_refunded'],sum(facts['refunds'].values()))
    risk={'refunded_amount':total,'disputes':facts['disputes'],'conflicts':facts['conflicts']}
    return facts,risk,bool(total or facts['disputes']or facts['conflicts'])


def apply(connect,provider,livemode,event_id,observation):
    """Atomically link journal/case. No balance, subscription or history writes."""
    charge=identifier(observation['charge_id']);refs=sorted(set([charge]+[identifier(x)for x in observation.get('refs',[])]))
    currency=observation.get('currency')or('USD'if provider=='stripe'else'XTR')
    if currency!=('USD'if provider=='stripe'else'XTR'):raise ReviewError('unsupported_review_currency')
    order_id=observation.get('order_id')
    if order_id is not None and not re.fullmatch(r'[0-9a-f]{32}',str(order_id)):raise ReviewError('invalid_order_reference')
    if observation['kind']not in('refund','charge_refunded','dispute'):raise ReviewError('invalid_review_kind')
    case_id=digest([provider,livemode,charge])
    with transaction(connect)as conn:
        with conn.cursor()as cur:
            cur.execute('SELECT status FROM financial_review_events WHERE provider=%s AND livemode=%s AND event_id=%s FOR UPDATE',
                        (provider,livemode,event_id));event=cur.fetchone()
            if not event:raise ReviewError('event_not_durable')
            if event[0]=='processed':return {'outcome':'duplicate_event','case_id':case_id}
            # Serialize enrichment before reading aliases/owner. User locks still
            # precede case row locks, matching paid admission and owner resolution.
            cur.execute('SELECT pg_advisory_xact_lock(%s)',(int(case_id[:15],16),))
            cur.execute('SELECT telegram_id,payment_refs,order_id,manual_mapping_verified,purchase_id,source FROM financial_review_cases WHERE case_id=%s',(case_id,));old_owner=cur.fetchone()
            if old_owner:
                refs=sorted(set(refs+old_owner[1]));order_id=order_id or old_owner[2]
            original=_original(cur,provider,refs,order_id)
            if old_owner and old_owner[3]:
                original={'conflict':False,'uid':old_owner[0],'purchase':None,'source':old_owner[5],'order_id':old_owner[2]}
            order_id=order_id or original['order_id']
            uid=old_owner[0]if old_owner and old_owner[0]is not None else original['uid']
            if uid is not None:
                cur.execute('SELECT telegram_id FROM users WHERE telegram_id=%s FOR UPDATE',(uid,))
                if not cur.fetchone():uid=None
            cur.execute('''INSERT INTO financial_review_cases(case_id,provider,livemode,charge_id,currency,risk_hash)
                VALUES(%s,%s,%s,%s,%s,%s)ON CONFLICT DO NOTHING''',(case_id,provider,livemode,charge,currency,digest({})))
            cur.execute('''SELECT facts,risk_hash,review_revision,resolved_revision,payment_refs,purchase_id,order_id,source,telegram_id
                FROM financial_review_cases WHERE case_id=%s FOR UPDATE''',(case_id,));old=cur.fetchone()
            conflict=original['conflict']or bool(old[8]is not None and original['uid']is not None and old[8]!=original['uid'])
            purchase_id=original['purchase'][0]if original['purchase']and not conflict else old[5]
            source=original['source']if not conflict and original['source']else old[7]
            facts,risk,needs_review=_merge_facts(old[0],observation)
            if conflict:risk['mapping_conflict']=True;needs_review=True
            marker=digest({'risk':risk,'uid':uid,'purchase_id':purchase_id})
            revision=old[2]+int(needs_review and marker!=old[1])
            cur.execute('''UPDATE financial_review_cases SET telegram_id=%s,purchase_id=%s,order_id=%s,
                payment_refs=%s,source=%s,facts=%s::jsonb,risk_hash=%s,review_revision=%s,
                mapping_conflict=%s,updated_at=NOW()WHERE case_id=%s''',
                (uid,purchase_id,order_id or old[6],sorted(set(old[4]+refs)),source,canonical(facts),marker,revision,conflict,case_id))
            cur.execute('''UPDATE financial_review_events SET status='processed',processed_at=NOW(),case_id=%s,last_error_class=NULL
                WHERE provider=%s AND livemode=%s AND event_id=%s''',(case_id,provider,livemode,event_id))
            if provider=='telegram_stars'and observation['kind']=='refund'and observation.get('status')=='succeeded':
                cur.execute("UPDATE payment_refund_requests SET status='confirmed',updated_at=NOW(),last_error_class=NULL WHERE provider='telegram_stars'AND livemode=TRUE AND charge_id=%s",(charge,))
            return {'outcome':'pending_review'if revision>old[3]else'observed','case_id':case_id,'review_revision':revision,'mapped':uid is not None}


def blocked_for(cur,uid,stripe_livemode=True):
    """Caller already holds users row lock; Stars is always real, never Stripe-test.

    API supplies its configured Stripe mode. Native bot defaults to real
    payments only, so Stripe test events cannot freeze real Stars usage.
    Late receipts are matched at read time, preventing refund-before-grant gaps.
    """
    cur.execute("SELECT 1 FROM payment_refund_requests WHERE telegram_id=%s AND provider='telegram_stars'AND livemode=TRUE AND status IN('dispatching','pending_reconciliation')LIMIT 1",(uid,))
    if cur.fetchone():return True
    cur.execute('''SELECT 1 FROM financial_review_events e WHERE e.status='pending'
        AND((e.provider='telegram_stars'AND e.livemode=TRUE)
            OR(e.provider='stripe'AND e.livemode=%s AND e.payload->>'requires_review_hint'='true'))
        AND(EXISTS(SELECT 1 FROM purchases p WHERE p.provider=e.provider AND p.telegram_id=%s
            AND(p.charge_id=e.payload->>'charge_id'OR(e.payload->'payment_refs')?p.charge_id))
            OR EXISTS(SELECT 1 FROM shop_orders o WHERE o.provider=e.provider AND o.telegram_id=%s
                AND o.order_id=e.payload->>'order_id'))LIMIT 1''',(bool(stripe_livemode),uid,uid))
    if cur.fetchone():return True
    cur.execute('''SELECT 1 FROM financial_review_cases c WHERE
        ((c.provider='telegram_stars'AND c.livemode=TRUE)OR(c.provider='stripe'AND c.livemode=%s))
        AND (c.review_revision>c.resolved_revision OR(c.review_revision>0 AND c.purchase_id IS NULL AND EXISTS(
            SELECT 1 FROM purchases p WHERE p.provider=c.provider AND p.charge_id=ANY(c.payment_refs))))
        AND(c.telegram_id=%s OR(c.telegram_id IS NULL AND NOT c.mapping_conflict AND EXISTS(
            SELECT 1 FROM purchases p WHERE p.telegram_id=%s AND p.provider=c.provider AND p.charge_id=ANY(c.payment_refs))))
        LIMIT 1''',(bool(stripe_livemode),uid,uid))
    return bool(cur.fetchone())


def summary(connect):
    with transaction(connect)as conn:
        with conn.cursor()as cur:
            cur.execute('''SELECT count(*),count(*)FILTER(WHERE telegram_id IS NULL),
                count(*)FILTER(WHERE updated_at<NOW()-INTERVAL'30 minutes')FROM financial_review_cases
                WHERE review_revision>resolved_revision''');pending,unmapped,stale=cur.fetchone()
            cur.execute("SELECT count(*)FROM financial_review_events WHERE status='pending'");events=cur.fetchone()[0]
            cur.execute("SELECT count(*)FROM payment_refund_requests WHERE status IN('dispatching','pending_reconciliation')");requests=cur.fetchone()[0]
            return dict(pending_review=pending,pending_mapping=unmapped,stale=stale,pending_events=events,refund_requests_pending_reconciliation=requests)


def pending_cases(connect,limit=50):
    with transaction(connect)as conn:
        with conn.cursor()as cur:
            cur.execute('''SELECT case_id,provider,livemode,charge_id,currency,telegram_id,purchase_id,order_id,
                source,review_revision,resolved_revision,facts,mapping_conflict,updated_at
                FROM financial_review_cases WHERE review_revision>resolved_revision
                ORDER BY updated_at,case_id LIMIT %s''',(min(200,max(1,int(limit))),))
            keys=('case_id','provider','livemode','charge_id','currency','telegram_id','purchase_id','order_id','source',
                  'review_revision','resolved_revision','facts','mapping_conflict','updated_at')
            return [dict(zip(keys,row))for row in cur.fetchall()]


def reconcile_uncertain_requests(connect):
    """Detect a crash/lost response. NEVER reissue an external refund."""
    with transaction(connect)as conn:
        with conn.cursor()as cur:
            cur.execute("UPDATE payment_refund_requests SET status='pending_reconciliation',updated_at=NOW()WHERE status='dispatching'AND created_at<NOW()-INTERVAL'2 minutes'")
            return cur.rowcount


def stars_refund_record(payment):
    if not isinstance(payment,dict)or payment.get('currency')!='XTR':raise ReviewError('invalid_stars_refund_currency')
    charge=identifier(payment.get('telegram_payment_charge_id'));value=amount(payment.get('total_amount'))
    if not value:raise ReviewError('empty_stars_refund')
    payload=str(payment.get('invoice_payload')or'')
    order_id=payload.split(':',1)[1]if re.fullmatch(r'sylvex_order:[0-9a-f]{32}',payload)else None
    return {'charge_id':charge,'amount':value,'currency':'XTR','order_id':order_id}


def record_stars_refund(connect,payment):
    record=stars_refund_record(payment);key='stars-refund:'+record['charge_id']+':'+(record['order_id']or'legacy')
    status=receive(connect,'telegram_stars',True,key,'refunded_payment',record)
    if status=='processed':return {'outcome':'duplicate_event'}
    return apply(connect,'telegram_stars',True,key,{'kind':'refund','entity_id':record['charge_id'],
        'charge_id':record['charge_id'],'refs':[record['charge_id']],'order_id':record['order_id'],'amount':record['amount'],'status':'succeeded'})


def record_star_transaction_refund(connect,tx):
    receiver=tx.get('receiver')or{}
    if tx.get('source')or receiver.get('type')!='user'or receiver.get('transaction_type')!='invoice_payment':return False
    if int(tx.get('nanostar_amount')or 0)!=0:raise ReviewError('fractional_invoice_refund_requires_review')
    record_stars_refund(connect,{'currency':'XTR','telegram_payment_charge_id':tx.get('id'),'invoice_payload':receiver.get('invoice_payload'),
                                'total_amount':abs(int(tx.get('amount')or 0))})
    return True


def replay_stars_refunds(connect,limit=50):
    """Finish receipts persisted before an interrupted apply, no provider calls."""
    counts={'processed':0,'retry':0}
    for event in pending_events(connect,'telegram_stars',True,limit):
        if event['event_type']!='refunded_payment':continue
        record=event['payload']
        try:
            apply(connect,'telegram_stars',True,event['event_id'],{'kind':'refund',
                'entity_id':record['charge_id'],'charge_id':record['charge_id'],
                'refs':[record['charge_id']],'order_id':record.get('order_id'),
                'amount':record['amount'],'status':'succeeded'})
            counts['processed']+=1
        except Exception as error:
            failed(connect,'telegram_stars',True,event['event_id'],error);counts['retry']+=1
    return counts


def request_stars_refund(connect,purchase_id,provider_call,*,operator,evidence):
    """Separately authorized full Stars refund; durable BEFORE external call.

    Caller must require explicit owner confirmation. A retry/timeout/crash
    never reissues the request. Credits/entitlements stay on manual review.
    """
    if not operator or not evidence or len(operator)>128 or len(evidence)>512:raise ReviewError('confirmed_owner_decision_required')
    with transaction(connect)as conn:
        with conn.cursor()as cur:
            cur.execute("SELECT telegram_id,charge_id,amount,currency,status FROM purchases WHERE id=%s AND provider='telegram_stars'",(int(purchase_id),));purchase=cur.fetchone()
            if not purchase or purchase[3]!='XTR'or purchase[4]!='completed'or not str(purchase[2]).isdigit():raise ReviewError('verified_original_stars_purchase_required')
            uid,charge= purchase[0],identifier(purchase[1]);value=amount(int(purchase[2]))
            if not value:raise ReviewError('empty_stars_refund')
            cur.execute('SELECT telegram_id FROM users WHERE telegram_id=%s FOR UPDATE',(uid,))
            if not cur.fetchone():raise ReviewError('account_not_found')
            key=digest(['telegram_stars',True,charge])
            cur.execute('''INSERT INTO payment_refund_requests(request_id,provider,livemode,charge_id,telegram_id,
                purchase_id,amount,currency,status,operator,evidence)VALUES(%s,'telegram_stars',TRUE,%s,%s,%s,%s,'XTR','dispatching',%s,%s)
                ON CONFLICT DO NOTHING RETURNING request_id''',(key,charge,uid,int(purchase_id),value,operator,evidence))
            if not cur.fetchone():
                cur.execute('SELECT status FROM payment_refund_requests WHERE request_id=%s',(key,))
                return {'request_id':key,'status':cur.fetchone()[0],'provider_called':False}
    try:
        if provider_call(uid,charge)is not True:raise ReviewError('refund_result_not_confirmed')
        record_stars_refund(connect,{'currency':'XTR','telegram_payment_charge_id':charge,'total_amount':value})
        return {'request_id':key,'status':'confirmed','provider_called':True}
    except BaseException as error:
        try:
            with transaction(connect)as conn:
                with conn.cursor()as cur:cur.execute("UPDATE payment_refund_requests SET status='pending_reconciliation',last_error_class=%s,updated_at=NOW()WHERE request_id=%s AND status<>'confirmed'",(type(error).__name__[:100],key))
        except Exception:pass # Durable dispatching row is detected after restart.
        raise


def resolve_stars_request(connect,request_id,*,refunded,operator,evidence):
    """Manual confirmed provider reconciliation. Never an external refund call."""
    if not operator or not evidence or len(operator)>128 or len(evidence)>512 or type(refunded)is not bool:raise ReviewError('confirmed_owner_decision_required')
    with transaction(connect)as conn:
        with conn.cursor()as cur:
            cur.execute("SELECT telegram_id FROM payment_refund_requests WHERE request_id=%s",(request_id,));owner=cur.fetchone()
            if not owner:raise ReviewError('refund_request_not_found')
            cur.execute('SELECT telegram_id FROM users WHERE telegram_id=%s FOR UPDATE',(owner[0],))
            cur.execute('SELECT charge_id,amount,status FROM payment_refund_requests WHERE request_id=%s FOR UPDATE',(request_id,));charge,value,status=cur.fetchone()
            if status=='confirmed'and not refunded:raise ReviewError('confirmed_refund_cannot_be_unconfirmed')
            if status=='not_refunded'and refunded:raise ReviewError('contradictory_manual_refund_decision')
            audit={'request_id':request_id,'refunded':refunded,'operator':operator,'evidence':evidence}
            cur.execute('''INSERT INTO financial_review_events(provider,livemode,event_id,event_type,payload,payload_hash,status,processed_at)
                VALUES('telegram_stars',TRUE,%s,'operator.refund_reconciliation',%s::jsonb,%s,'processed',NOW())ON CONFLICT DO NOTHING''',
                ('manual-request:'+digest(audit),canonical(audit),digest(audit)))
            if not refunded:
                cur.execute("UPDATE payment_refund_requests SET status='not_refunded',updated_at=NOW()WHERE request_id=%s",(request_id,))
                return {'status':'not_refunded'}
    result=record_stars_refund(connect,{'currency':'XTR','telegram_payment_charge_id':charge,'total_amount':value})
    return {'status':'confirmed','review':result}


def refresh_mappings(connect,limit=50):
    """Retry exact local receipt binding after out-of-order grants; no provider calls."""
    with transaction(connect)as conn:
        with conn.cursor()as cur:
            cur.execute('''SELECT case_id,provider,livemode,charge_id,payment_refs,order_id FROM financial_review_cases
                WHERE purchase_id IS NULL ORDER BY updated_at,case_id LIMIT %s''',(min(100,max(1,int(limit))),));rows=cur.fetchall()
    changed=0
    for case_id,provider,mode,charge,refs,order_id in rows:
        with transaction(connect)as conn:
            with conn.cursor()as cur:
                original=_original(cur,provider,refs,order_id)
                if original['conflict']or not original['purchase']:continue
                uid=original['uid'];cur.execute('SELECT telegram_id FROM users WHERE telegram_id=%s FOR UPDATE',(uid,))
                if not cur.fetchone():continue
                cur.execute('''SELECT telegram_id,purchase_id,review_revision,resolved_revision FROM financial_review_cases
                    WHERE case_id=%s FOR UPDATE''',(case_id,));old=cur.fetchone()
                if old[1]is not None or old[0]not in(None,uid):continue
                cur.execute('SELECT facts FROM financial_review_cases WHERE case_id=%s',(case_id,));facts=cur.fetchone()[0]
                risk={'refunded_amount':max(facts.get('cumulative_refunded',0),sum(facts.get('refunds',{}).values())),
                      'disputes':facts.get('disputes',{}),'conflicts':facts.get('conflicts',[])}
                marker=digest({'risk':risk,'uid':uid,'purchase_id':original['purchase'][0]})
                cur.execute('''UPDATE financial_review_cases SET telegram_id=%s,purchase_id=%s,source=COALESCE(source,%s),risk_hash=%s,
                    review_revision=review_revision+CASE WHEN review_revision>0 THEN 1 ELSE 0 END,updated_at=NOW()
                    WHERE case_id=%s''',(uid,original['purchase'][0],original['source'],marker,case_id));changed+=1
    return changed


DECISIONS={'no_credit_adjustment','dispute_won','loss_accepted','not_platform_payment','confirmed_credit_correction','ungranted_payment_refunded'}


def map_original(connect,case_id,purchase_id,revision,*,operator,evidence,source=None):
    """Explicit owner mapping of already known exact aliases, never a claimed UID."""
    if not operator or not evidence or len(operator)>128 or len(evidence)>512:raise ReviewError('verified_mapping_evidence_required')
    with transaction(connect)as conn:
        with conn.cursor()as cur:
            cur.execute('SELECT telegram_id,provider,charge_id FROM purchases WHERE id=%s',(int(purchase_id),));purchase=cur.fetchone()
            if not purchase:raise ReviewError('purchase_not_found')
            uid,provider,charge=purchase
            cur.execute('SELECT telegram_id FROM users WHERE telegram_id=%s FOR UPDATE',(uid,))
            if not cur.fetchone():raise ReviewError('account_not_found')
            cur.execute('''SELECT review_revision,provider,livemode,payment_refs,order_id,facts FROM financial_review_cases
                WHERE case_id=%s FOR UPDATE''',(case_id,));case=cur.fetchone()
            if not case or int(revision)!=case[0]:raise ReviewError('review_changed_refresh_before_mapping')
            if provider!=case[1]or charge not in case[3]:raise ReviewError('exact_original_payment_alias_required')
            bound=_original(cur,provider,[charge],case[4])
            actual_source=bound['source']
            if source is not None and(source not in('purchased','subscription')or(actual_source is not None and source!=actual_source)):
                raise ReviewError('source_conflicts_with_original_payment')
            chosen=actual_source or source
            risk={'refunded_amount':max(case[5].get('cumulative_refunded',0),sum(case[5].get('refunds',{}).values())),
                  'disputes':case[5].get('disputes',{}),'conflicts':case[5].get('conflicts',[])}
            marker=digest({'risk':risk,'uid':uid,'purchase_id':int(purchase_id)})
            cur.execute('''UPDATE financial_review_cases SET telegram_id=%s,purchase_id=%s,source=%s,
                mapping_conflict=FALSE,manual_mapping_verified=TRUE,risk_hash=%s,
                review_revision=review_revision+1,updated_at=NOW()WHERE case_id=%s''',(uid,int(purchase_id),chosen,marker,case_id))
            record={'case_id':case_id,'purchase_id':int(purchase_id),'operator':operator,'evidence':evidence,'source':chosen}
            key='manual-map:'+digest([case_id,int(revision),record])
            cur.execute('''INSERT INTO financial_review_events(provider,livemode,event_id,event_type,payload,payload_hash,status,case_id,processed_at)
                VALUES(%s,%s,%s,'operator.mapping',%s::jsonb,%s,'processed',%s,NOW())''',
                (provider,case[2],key,canonical(record),digest(record),case_id))
            return {'case_id':case_id,'review_revision':case[0]+1,'mapped':True}


def resolve(connect,case_id,revision,*,operator,evidence,decision,credits=0,source=None,
            expected_balance=None,expected_purchased=None,expected_subscription=None,
            confirmed_unspent_credits=None,wallet=None):
    """Owner-only confirmed decision, CAS and once-only audit. No public endpoint.

    Non-zero correction requires separate per-payment authorization, explicit
    unused-original-credit attestation, exact source/period and wallet snapshot.
    Unknown provenance is NOT guessed; accept loss/no adjustment explicitly.
    """
    if decision not in DECISIONS or not isinstance(operator,str)or not operator.strip()or len(operator)>128 or not isinstance(evidence,str)or not evidence.strip()or len(evidence)>512:
        raise ReviewError('confirmed_owner_decision_required')
    credits=amount(credits);revision=int(revision)
    request_hash=digest([case_id,revision,operator,evidence,decision,credits,source])
    with transaction(connect)as conn:
        with conn.cursor()as cur:
            cur.execute('SELECT telegram_id FROM financial_review_cases WHERE case_id=%s',(case_id,));owner=cur.fetchone()
            if not owner:raise ReviewError('case_not_found')
            uid=owner[0]
            if uid is not None:cur.execute('SELECT telegram_id FROM users WHERE telegram_id=%s FOR UPDATE',(uid,))
            cur.execute('''SELECT review_revision,resolved_revision,purchase_id,source,provider,payment_refs,order_id,mapping_conflict,facts
                FROM financial_review_cases WHERE case_id=%s FOR UPDATE''',(case_id,));row=cur.fetchone()
            if revision!=row[0]:raise ReviewError('review_changed_refresh_before_resolution')
            cur.execute('SELECT request_hash,balance_after FROM financial_review_resolutions WHERE case_id=%s AND review_revision=%s',(case_id,revision));prior=cur.fetchone()
            if prior:
                if prior[0]!=request_hash:raise ReviewError('review_already_resolved_differently')
                return {'outcome':'duplicate_resolution','balance_after':prior[1]}
            if revision<=0:raise ReviewError('no_confirmed_review_to_resolve')
            if row[7]:raise ReviewError('mapping_conflict_requires_verified_remapping')
            if decision=='dispute_won':
                disputes=row[8].get('disputes',{})
                if not disputes or any(x.get('status')!='won'for x in disputes.values())or max(row[8].get('cumulative_refunded',0),sum(row[8].get('refunds',{}).values()))or row[8].get('conflicts'):
                    raise ReviewError('all_disputes_won_and_no_refund_required')
            if row[2]is None and decision not in('not_platform_payment','ungranted_payment_refunded'):raise ReviewError('original_payment_not_mapped')
            if decision=='ungranted_payment_refunded':
                if row[2]is not None or uid is None or row[6]is None:raise ReviewError('ungranted_order_binding_required')
                cur.execute("SELECT status FROM shop_orders WHERE order_id=%s AND telegram_id=%s AND provider=%s",(row[6],uid,row[4]));order=cur.fetchone()
                if not order or order[0]=='paid':raise ReviewError('grant_state_requires_manual_review')
                cur.execute('SELECT 1 FROM purchases WHERE provider=%s AND charge_id=ANY(%s)LIMIT 1',(row[4],row[5]))
                if cur.fetchone():raise ReviewError('late_payment_receipt_refresh_required')
            if decision=='not_platform_payment'and(row[2]is not None or row[6]is not None or uid is not None):raise ReviewError('known_platform_payment_cannot_be_ignored')
            before=after=None
            if credits:
                if decision!='confirmed_credit_correction'or wallet is None or source not in('purchased','subscription')or source!=row[3]or confirmed_unspent_credits is None or credits>amount(confirmed_unspent_credits):
                    raise ReviewError('verified_original_source_and_unused_credits_required')
                cur.execute('SELECT telegram_id,credits,charge_id,status FROM purchases WHERE id=%s AND provider=%s FOR SHARE',(row[2],row[4]));purchase=cur.fetchone()
                if not purchase or purchase[0]!=uid or purchase[2]not in row[5]or purchase[3]!='completed':raise ReviewError('original_payment_binding_changed')
                cur.execute('SELECT COALESCE(SUM(credits),0)FROM financial_review_resolutions WHERE purchase_id=%s',(row[2],))
                remaining=int(purchase[1]or 0)-cur.fetchone()[0]
                if credits>remaining or confirmed_unspent_credits>remaining:raise ReviewError('correction_exceeds_original_grant')
                cur.execute("SELECT 1 FROM generation_reservations WHERE telegram_id=%s AND status='reserved'LIMIT 1",(uid,))
                if cur.fetchone():raise ReviewError('wait_for_existing_holds_and_reconciliation')
                purchased,subscription,expires=wallet._ensure_wallet(cur,uid)
                before=purchased+subscription
                if(expected_balance,expected_purchased,expected_subscription)!=(before,purchased,subscription):raise ReviewError('wallet_changed_refresh_before_correction')
                if source=='purchased':
                    if credits>purchased:raise ReviewError('insufficient_original_source')
                    purchased-=credits
                else:
                    cur.execute('SELECT expires_at::timestamptz=%s::timestamptz FROM subscriptions WHERE telegram_id=%s AND charge_id=%s ORDER BY id DESC LIMIT 1',(expires,uid,purchase[2]))
                    period=cur.fetchone()
                    if not expires or not period or period[0]is not True:raise ReviewError('different_subscription_period_manual_review_required')
                    if credits>subscription:raise ReviewError('insufficient_original_source')
                    subscription-=credits
                wallet._set_wallet(cur,uid,purchased,subscription,expires);after=purchased+subscription
            elif decision=='confirmed_credit_correction':raise ReviewError('nonzero_confirmed_correction_required')
            cur.execute('''INSERT INTO financial_review_resolutions(resolution_id,case_id,review_revision,telegram_id,
                purchase_id,operator,evidence,decision,source,credits,balance_before,balance_after,request_hash)
                VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)''',
                (digest([case_id,revision]),case_id,revision,uid,row[2],operator,evidence,decision,source,credits,before,after,request_hash))
            cur.execute('UPDATE financial_review_cases SET resolved_revision=%s,updated_at=NOW()WHERE case_id=%s',(revision,case_id))
            return {'outcome':'resolved','balance_after':after}
