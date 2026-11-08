"""Verified provider-object fakes, no Stripe network or payments."""
import copy
import pytest
from services import stripe_reversals as s, payment_reviews as r, stripe_billing as sb
from test_payment_reviews import db,connect,sql,purchase,held,balance,resolve


class Provider:
    livemode=False
    def __init__(self):
        self.calls=[];self.fail=False
        self.objects={
          '/charges/ch_one':dict(id='ch_one',livemode=False,amount=1000,amount_refunded=200,currency='usd',payment_intent='pi_one'),
          '/refunds/re_one':dict(id='re_one',livemode=False,amount=200,currency='usd',charge='ch_one',payment_intent='pi_one',status='succeeded'),
          '/disputes/dp_one':dict(id='dp_one',livemode=False,amount=1000,currency='usd',charge='ch_one',status='needs_response')}
    def request(self,method,path):
        assert method=='GET';self.calls.append(path)
        if self.fail:raise TimeoutError('sensitive-provider-response')
        return copy.deepcopy(self.objects[path])


def event(kind='refund.created',eid='evt_one',**fields):
    prefix='ch'if kind=='charge.refunded'else'dp'if kind.startswith('charge.dispute.')else're'
    obj=dict(id=prefix+'_one',charge='ch_one',payment_intent='pi_one',currency='usd',status='succeeded',livemode=False)
    obj.update(fields)
    return dict(id=eid,type=kind,livemode=False,data={'object':obj})


@pytest.mark.parametrize('kind',sorted(s.EVENT_TYPES))
def test_all_supported_reversal_events_are_linked_durably_without_clawback(db,kind):
    purchase();provider=Provider();before=balance();result=s.receive_verified(connect,provider,event(kind))
    assert result['mapped'] and held() and balance()==before
    assert sql('SELECT status FROM financial_review_events')[0][0]=='processed'
    assert all(path.startswith(('/charges/','/refunds/','/disputes/'))for path in provider.calls)


def test_duplicate_event_never_refetches_current_provider_object(db):
    purchase();provider=Provider();e=event();s.receive_verified(connect,provider,e);provider.calls=[]
    assert s.receive_verified(connect,provider,e)['outcome']=='duplicate_event' and not provider.calls


@pytest.mark.parametrize('changed',['event-mode','object-mode','missing-mode'])
def test_wrong_mode_never_records_or_blocks(db,changed):
    purchase();provider=Provider();e=event()
    if changed=='event-mode':e['livemode']=True
    elif changed=='object-mode':e['data']['object']['livemode']=True
    else:e.pop('livemode')
    assert s.receive_verified(connect,provider,e)['outcome']=='ignored'
    assert not provider.calls and not held() and not sql('SELECT * FROM financial_review_events')


def test_provider_failure_is_durable_retryable_and_blocks_only_exact_original(db):
    purchase();provider=Provider();provider.fail=True
    with pytest.raises(TimeoutError):s.receive_verified(connect,provider,event())
    assert held() and not held(202) and r.summary(connect)['pending_events']==1
    assert sql('SELECT last_error_class FROM financial_review_events')[0][0]=='TimeoutError'
    sql('UPDATE financial_review_events SET next_attempt_at=NOW()');provider.fail=False
    assert s.replay(connect,provider)=={'processed':1,'retry':0} and held()


def test_stale_event_uses_current_provider_status_not_delivery_timestamp(db):
    purchase();provider=Provider();provider.objects['/refunds/re_one']['status']='failed'
    provider.objects['/charges/ch_one']['amount_refunded']=0
    s.receive_verified(connect,provider,event(status='succeeded',created=123))
    assert not held()
    provider.objects['/refunds/re_one']['status']='succeeded'
    provider.objects['/charges/ch_one']['amount_refunded']=200
    s.receive_verified(connect,provider,event('refund.updated','evt_two',status='pending',created=123))
    assert held()


def test_invoice_subscription_receipt_maps_by_invoice_not_customer(db,monkeypatch):
    purchase(charge='in_one',kind='subscription');provider=Provider()
    provider.objects['/charges/ch_one']['invoice']='in_one'
    provider.objects['/invoices/in_one']=dict(id='in_one',subscription='sub_one',customer='cus_untrusted',livemode=False)
    monkeypatch.setattr(sb,'get_subscription',lambda *a:dict(order_id='a'*32,livemode=False))
    result=s.receive_verified(connect,provider,event());assert result['mapped'] and held()
    assert sql('SELECT source FROM financial_review_cases')[0][0]=='subscription'


@pytest.mark.parametrize('change,reason',[
 ('currency','currency'),('amount','exceeds_original'),('mode','mode_mismatch'),('id','resource_mismatch')])
def test_inconsistent_provider_resource_stays_pending_without_balance_changes(db,change,reason):
    purchase();provider=Provider();obj=provider.objects['/refunds/re_one']
    obj[{'currency':'currency','amount':'amount','mode':'livemode','id':'id'}[change]]={'currency':'eur','amount':1001,'mode':True,'id':'re_other'}[change]
    with pytest.raises(r.ReviewError,match=reason):s.receive_verified(connect,provider,event())
    assert held() and balance()[0][1]==100 and r.summary(connect)['pending_events']==1


def test_resource_id_cannot_request_arbitrary_url(db):
    provider=Provider()
    with pytest.raises(r.ReviewError,match='invalid_stripe'):s.receive_verified(connect,provider,event(id='https://invalid.example'))
    assert not provider.calls


def test_partial_receipt_includes_current_charge_total_when_prior_refund_event_missing(db):
    purchase();provider=Provider()
    provider.objects['/charges/ch_one']['amount_refunded']=600
    s.receive_verified(connect,provider,event())
    facts=sql('SELECT facts FROM financial_review_cases')[0][0]
    assert facts['cumulative_refunded']==600 and sum(facts['refunds'].values())==200 and held()
