import asyncio
import json
import pytest
import main
from services import payment_reviews as r,stripe_billing as sb
from services.security import SecurityError
from test_payment_reviews import db,connect,sql,purchase,observe,held,balance
from test_subscription_admission import admission
from test_billing_coverage import ledger


@pytest.mark.parametrize('kind',['helper','text','character','object','queued'])
def test_review_blocks_every_existing_paid_entry_before_reserve_or_dispatch(admission,monkeypatch,kind):
    ledger,calls,start=admission
    monkeypatch.setattr(main,'STRIPE_SECRET_KEY','sk_test_synthetic')
    purchase();observe()
    with pytest.raises(SecurityError,match='payment_review_required'):start(kind)
    assert ledger.balance(101)==100 and not calls and not ledger.charges()
    assert sql('SELECT COUNT(*)FROM generation_reservations')[0][0]==0


@pytest.mark.parametrize('ok',[True,False])
def test_already_accepted_api_work_can_finish_after_review(admission,monkeypatch,ok):
    ledger,calls,start=admission;purchase()
    monkeypatch.setattr(main,'STRIPE_SECRET_KEY','sk_test_synthetic')
    async def accepted_provider():
        observe();assert held();return {'ok':ok}
    assert asyncio.run(main.run_billed_helper(101,3,'grid_plan',accepted_provider))['ok']==ok
    assert ledger.balance(101)==(97 if ok else 100)
    with pytest.raises(SecurityError,match='payment_review_required'):start('helper')


class Request:
    def __init__(self,body,secret='hook'):self.body=body;self.headers={'X-Telegram-Bot-Api-Secret-Token':secret}
    async def json(self):return self.body


def receipt():return {'message':{'refunded_payment':dict(currency='XTR',total_amount=10,invoice_payload='legacy',telegram_payment_charge_id='star_one')}}


@pytest.mark.parametrize('secret,status',[('bad',401),('hook',200)])
def test_authenticated_stars_refund_webhook_is_durable_without_grant(db,monkeypatch,secret,status):
    purchase('telegram_stars','star_one',amount='10')
    monkeypatch.setattr(main,'TELEGRAM_PAYMENT_WEBHOOK_SECRET','hook');monkeypatch.setattr(main,'shop_db',connect)
    response=asyncio.run(main.public_stars_webhook(Request(receipt(),secret)))
    assert (200 if isinstance(response,dict)else response.status_code)==status
    assert held()==(status==200) and balance()[0][1]==100


def test_webhook_db_failure_returns_retryable_503(db,monkeypatch):
    monkeypatch.setattr(main,'TELEGRAM_PAYMENT_WEBHOOK_SECRET','hook')
    monkeypatch.setattr(main.payment_reviews,'ensure_tables',lambda *a:(_ for _ in ()).throw(RuntimeError('synthetic database down')))
    response=asyncio.run(main.public_stars_webhook(Request(receipt())))
    assert response.status_code==503 and not sql('SELECT * FROM financial_review_events')


def test_old_unhandled_stripe_event_does_not_suppress_new_reversal_branch(db,monkeypatch):
    calls=[];monkeypatch.setattr(main,'ensure_stripe_tables',lambda:None)
    monkeypatch.setattr(main,'shop_db',connect);monkeypatch.setattr(main,'stripe_client',lambda:'fake-client')
    monkeypatch.setattr(sb,'event_processed',lambda *a:True)
    monkeypatch.setattr(main.stripe_reversals,'receive_verified',lambda *a:calls.append(a)or{'outcome':'pending_review'})
    assert main.process_stripe_event({'id':'evt_old','type':'charge.refunded'})['outcome']=='pending_review' and len(calls)==1


def test_review_response_provides_support_without_sensitive_data():
    response=asyncio.run(main.security_error_handler(None,SecurityError('payment_review_required',403)))
    data=json.loads(response.body)
    assert response.status_code==403 and data['support_email']=='support@sylvex.ai'
    assert set(data)=={'ok','error','support_email','message'}
