import importlib
import json
import os
import pytest
from test_payment_reviews import db,connect,sql,purchase,observe
m=importlib.import_module('services.payment_review_admin'if os.environ['LB006_ROLE']=='api'else'app.payment_review_admin')


@pytest.mark.parametrize('command',[
 ['resolve','--case-id','x','--revision','1','--decision','no_credit_adjustment','--mode','stripe-test','--operator','owner','--evidence','ticket'],
 ['map-original','--case-id','x','--purchase-id','1','--revision','1','--mode','stripe-test','--operator','owner','--evidence','ticket'],
 ['refund-stars','--purchase-id','1','--operator','owner','--evidence','ticket'],
 ['reconcile-stars-request','--request-id','x','--result','not-refunded','--operator','owner','--evidence','ticket']])
def test_owner_commands_refuse_without_explicit_confirm(monkeypatch,command):
    monkeypatch.setattr(m,'connect',lambda:pytest.fail('must not access database before authorization gate'))
    with pytest.raises(SystemExit)as error:m.main(command)
    assert error.value.code==2


def test_stars_refund_also_requires_real_payment_confirmation(monkeypatch):
    monkeypatch.setattr(m,'stars_provider_call',lambda *a:pytest.fail('must not call provider'))
    with pytest.raises(SystemExit):m.main(['refund-stars','--purchase-id','1','--operator','owner','--evidence','ticket','--confirm'])


def test_list_exposes_pending_events_and_preview_never_materializes_wallet(db,monkeypatch,capsys):
    purchase();case=observe();monkeypatch.setattr(m,'connect',connect)
    m.reviews.receive(connect,'stripe',False,'evt_wait','refund.created',{'object_id':'re_wait','requires_review_hint':True})
    assert m.main(['list'])==0
    listing=json.loads(capsys.readouterr().out)
    assert listing['summary']['pending_events']==1 and listing['pending_events'][0]['event_id']=='evt_wait'
    assert m.main(['preview-wallet','--case-id',case['case_id']])==0
    assert json.loads(capsys.readouterr().out)['read_only_snapshot']is True
    assert not sql('SELECT * FROM user_credit_wallets')


def test_wrong_mode_cannot_resolve_case(db,monkeypatch,capsys):
    purchase();case=observe();monkeypatch.setattr(m,'connect',connect)
    rc=m.main(['resolve','--case-id',case['case_id'],'--revision','1','--decision','no_credit_adjustment',
        '--mode','stripe-live','--operator','owner','--evidence','ticket','--confirm'])
    assert rc==1 and json.loads(capsys.readouterr().out)['reason']=='payment_mode_mismatch'
    assert not sql('SELECT * FROM financial_review_resolutions')


def test_unexpected_provider_or_db_error_is_sanitized(monkeypatch,capsys):
    monkeypatch.setattr(m,'connect',lambda:(_ for _ in ()).throw(RuntimeError('secret-value-must-not-be-printed')))
    assert m.main(['list'])==1
    output=capsys.readouterr().out
    assert 'secret-value'not in output and json.loads(output)['reason']=='provider_or_database_error'
