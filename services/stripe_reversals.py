"""Verified Stripe reversal intake; successful purchase/grant logic is unchanged."""
import re
from services import payment_reviews as reviews, stripe_billing as stripe

EVENT_TYPES={'refund.created','refund.updated','refund.failed','charge.refund.updated','charge.refunded',
             'charge.dispute.created','charge.dispute.updated','charge.dispute.closed',
             'charge.dispute.funds_withdrawn','charge.dispute.funds_reinstated'}


def _id(value,prefix):
    value=value.get('id')if isinstance(value,dict)else value
    if not isinstance(value,str)or not re.fullmatch(re.escape(prefix)+r'_[A-Za-z0-9_]+',value):raise reviews.ReviewError('invalid_stripe_resource_id')
    return value


def _checked(client,path,expected):
    value=client.request('GET',path)
    if value.get('id')!=expected:raise reviews.ReviewError('provider_resource_mismatch')
    if 'livemode'in value and(type(value['livemode'])is not bool or value['livemode']!=client.livemode):raise reviews.ReviewError('provider_mode_mismatch')
    return value


def _observation(connect,client,event_type,payload):
    object_id=payload['object_id']
    if event_type=='charge.refunded':
        charge_id=_id(object_id,'ch');obj=charge=_checked(client,'/charges/'+charge_id,charge_id);kind='charge_refunded'
    else:
        prefix='dp'if event_type.startswith('charge.dispute.')else're'
        object_id=_id(object_id,prefix)
        obj=_checked(client,('/disputes/'if prefix=='dp'else'/refunds/')+object_id,object_id)
        charge_id=_id(obj.get('charge'),'ch');charge=_checked(client,'/charges/'+charge_id,charge_id)
        kind='dispute'if prefix=='dp'else'refund'
    refs={charge_id};order_id=(charge.get('metadata')or{}).get('sylvex_order_id')
    if charge.get('payment_intent'):refs.add(_id(charge['payment_intent'],'pi'))
    if obj.get('payment_intent'):refs.add(_id(obj['payment_intent'],'pi'))
    if charge.get('invoice'):
        invoice_id=_id(charge['invoice'],'in');refs.add(invoice_id)
        invoice=_checked(client,'/invoices/'+invoice_id,invoice_id)
        if invoice.get('payment_intent'):refs.add(_id(invoice['payment_intent'],'pi'))
        subscription_id=stripe._invoice_subscription_id(invoice)
        if subscription_id:
            link=stripe.get_subscription(connect,subscription_id)
            if link and link.get('livemode')in(None,client.livemode):order_id=link.get('order_id')or order_id
            else:
                subscription=_checked(client,'/subscriptions/'+_id(subscription_id,'sub'),subscription_id)
                order_id=(subscription.get('metadata')or{}).get('sylvex_order_id')or order_id
    if order_id is not None and not re.fullmatch('[0-9a-f]{32}',str(order_id)):raise reviews.ReviewError('invalid_provider_order_reference')
    currency=str(charge.get('currency')or'').upper()
    if currency!='USD' or(obj.get('currency')and str(obj['currency']).upper()!=currency):raise reviews.ReviewError('unsupported_or_mismatched_refund_currency')
    value=reviews.amount(charge.get('amount_refunded',0)if kind=='charge_refunded'else obj.get('amount',0))
    original=reviews.amount(charge.get('amount',0))
    cumulative=reviews.amount(charge.get('amount_refunded',0))
    if max(value,cumulative)>original:raise reviews.ReviewError('reversal_exceeds_original_payment')
    return {'charge_id':charge_id,'refs':sorted(refs),'order_id':order_id,'kind':kind,'entity_id':object_id,
            'amount':value,'currency':currency,'original_amount':original,'cumulative_refunded':cumulative,'status':str(obj.get('status')or''),
            'funds_withdrawn':event_type=='charge.dispute.funds_withdrawn',
            'funds_reinstated':event_type=='charge.dispute.funds_reinstated'}


def process_record(connect,client,record):
    try:
        observation=_observation(connect,client,record['event_type'],record['payload'])
        return reviews.apply(connect,'stripe',client.livemode,record['event_id'],observation)
    except Exception as error:
        reviews.failed(connect,'stripe',client.livemode,record['event_id'],error)
        raise


def receive_verified(connect,client,event):
    """Caller already verified Stripe HMAC. Never accepts a browser refund request."""
    event_type=event.get('type')
    if event_type not in EVENT_TYPES:return {'outcome':'ignored','reason':'not_a_reversal'}
    if type(event.get('livemode'))is not bool or event['livemode']!=client.livemode:return {'outcome':'ignored','reason':'mode_mismatch'}
    obj=(event.get('data')or{}).get('object')or{}
    if 'livemode'in obj and(type(obj['livemode'])is not bool or obj['livemode']!=client.livemode):return {'outcome':'ignored','reason':'mode_mismatch'}
    prefix='ch'if event_type=='charge.refunded'else'dp'if event_type.startswith('charge.dispute.')else're'
    object_id=_id(obj.get('id'),prefix)
    refs=[]
    if prefix=='ch':refs.append(object_id)
    for field,ref_prefix in [('charge','ch'),('payment_intent','pi'),('invoice','in')]:
        if obj.get(field):refs.append(_id(obj[field],ref_prefix))
    order_id=(obj.get('metadata')or{}).get('sylvex_order_id')
    if order_id is not None and not re.fullmatch('[0-9a-f]{32}',str(order_id)):order_id=None
    payload={'object_id':object_id,'payment_refs':sorted(set(refs)),
             'order_id':order_id,
             'requires_review_hint':event_type.startswith('charge.dispute.')or event_type=='charge.refunded'or obj.get('status')=='succeeded'}
    status=reviews.receive(connect,'stripe',client.livemode,event['id'],event_type,payload)
    if status=='processed':return {'outcome':'duplicate_event'}
    return process_record(connect,client,dict(event_id=event['id'],event_type=event_type,payload=payload))


def replay(connect,client,limit=50):
    counts={'processed':0,'retry':0}
    for record in reviews.pending_events(connect,'stripe',client.livemode,limit):
        try:process_record(connect,client,record);counts['processed']+=1
        except Exception:counts['retry']+=1
    return counts
