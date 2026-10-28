"""Actual result writers must retain complete URLs and generated text.

The database is a capturing fake: no production or provider connection.
"""
import json
import pytest
import main


class Cursor:
    rowcount=1
    def __init__(self,initial,status='completed'):self.initial=initial;self.status=status;self.saved=None;self.saved_response=None;self.saved_request=None;self.sql=[]
    def execute(self,sql,params=None):
        self.sql.append(sql)
        if 'SET status = %s' in sql:
            self.saved=json.loads(params[3]);self.saved_response=json.loads(params[2])
        elif 'SET result_json = %s::jsonb' in sql:self.saved=json.loads(params[0])
        elif 'INSERT INTO prostudio_messages' in sql:
            self.saved_request=json.loads(params[18]);self.saved=json.loads(params[19])
        elif 'UPDATE prostudio_messages' in sql:self.saved=json.loads(params[6])
    def fetchone(self):
        if 'result_json FROM' in self.sql[-1]:return (self.status,self.initial)
        if 'prostudio_messages' in self.sql[-1]:return (501,)
        return ('processing',)
    def close(self):pass


class Connection:
    def __init__(self,cursor):self.c=cursor;self.committed=False
    def cursor(self):return self.c
    def commit(self):self.committed=True
    def rollback(self):pass
    def close(self):pass
    def __enter__(self):return self
    def __exit__(self,*args):self.commit()


@pytest.mark.parametrize('writer',['job','background_merge','history_insert','history_replace'])
@pytest.mark.parametrize('kind',['signed_url','generated_text'])
def test_result_roundtrip_is_lossless(writer,kind,monkeypatch):
    value=('https://provider.example.test/result.png?test_signature='+('x'*1800)) if kind=='signed_url' else ('Строка результата.\n'*180)
    result={'ok':True,'image_url':value,'images':[value],'metadata':{'image_url':value}} if kind=='signed_url' else {'ok':True,'type':'text','text':value}
    cursor=Cursor(result,status='processing' if writer=='job' else 'completed');conn=Connection(cursor)
    monkeypatch.setattr(main,'DATABASE_URL','fake://captured-result-only')
    monkeypatch.setattr(main,'db_connect',lambda *a:conn)
    monkeypatch.setattr(main,'db_connection',lambda *a:conn)
    monkeypatch.setattr(main,'ensure_prostudio_table',lambda:None)
    monkeypatch.setattr(main,'ensure_reservations',lambda *a:None)
    if writer=='job':assert main.update_prostudio_generation_job('roundtrip-job','completed',result)
    elif writer=='background_merge':main._merge_prostudio_result_fields('roundtrip-job',{'thumbnail_status':'completed'})
    else:
        payload={'telegram_id':101,'conversation_id':'roundtrip-conversation','mode':'text' if writer=='history_replace' or kind=='generated_text' else 'image'}
        if writer=='history_replace':payload['replace_message_id']=501
        result['metadata']={**result.get('metadata',{}),'type':payload['mode']}
        main.save_prostudio_message(payload,result)
    assert conn.committed
    field='image_url' if kind=='signed_url' else 'text'
    assert len(cursor.saved[field])==len(value),'Durable result writer truncated the actual output'
    assert cursor.saved[field]==value
    if writer=='job':assert cursor.saved_response==cursor.saved
    if kind=='signed_url':
        assert cursor.saved['images']==[value]
        assert cursor.saved['metadata']['image_url']==value
    assert not any('generation_reservations' in sql or 'generation_charges' in sql for sql in cursor.sql)


def test_history_request_keeps_complete_reference_urls(monkeypatch):
    value='https://storage.example.test/reference.png?test_signature='+('x'*1800)
    payload={'telegram_id':101,'conversation_id':'request-roundtrip','mode':'image',
        'image_options':{'referenceImageUrls':[value], 'region':{'reference':{'url':value}}}}
    result={'ok':True,'metadata':{'type':'image'}};cursor=Cursor(result);conn=Connection(cursor)
    monkeypatch.setattr(main,'DATABASE_URL','fake://captured-result-only')
    monkeypatch.setattr(main,'db_connection',lambda *a:conn)
    monkeypatch.setattr(main,'ensure_prostudio_table',lambda:None)
    main.save_prostudio_message(payload,result)
    assert cursor.saved_request['image_options']==payload['image_options']


def test_diagnostic_event_clipping_remains_enabled():
    clipped=main._sanitize_event_payload({'debug':'x'*2400},max_text=1200)
    assert len(clipped['debug'])==1201
    assert clipped['debug'].endswith('…')
