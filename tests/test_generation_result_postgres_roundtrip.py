"""Optional real PostgreSQL contract test, using only an explicit local test DB.

Each test creates and removes only its own uniquely named schema. No user,
billing, subscription, or generation rows outside that schema are touched.
"""
from contextlib import contextmanager
import json
import os
from types import SimpleNamespace
from urllib.parse import urlparse
from uuid import uuid4

import pytest
import main


@pytest.fixture
def result_database(monkeypatch):
    dsn=os.getenv('SYLVEX_RESULT_TEST_DB','')
    if not dsn:pytest.skip('Set SYLVEX_RESULT_TEST_DB to an isolated local PostgreSQL test database')
    parsed=urlparse(dsn)
    assert parsed.hostname in {'127.0.0.1','localhost','::1'}
    assert parsed.path.endswith(('_test','_tests'))
    import psycopg2
    from psycopg2 import sql
    schema='sx_result_roundtrip_'+uuid4().hex
    admin=psycopg2.connect(dsn);admin.autocommit=True
    with admin.cursor() as cur:
        cur.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(schema)))

    def connect(*args):
        conn=psycopg2.connect(dsn)
        with conn.cursor() as cur:cur.execute(sql.SQL('SET search_path TO {}').format(sql.Identifier(schema)))
        return conn

    @contextmanager
    def transaction(*args):
        conn=connect()
        try:
            yield conn;conn.commit()
        except Exception:
            conn.rollback();raise
        finally:conn.close()

    def query(statement,params=None):
        with transaction() as conn:
            with conn.cursor() as cur:
                cur.execute(statement,params)
                return cur.fetchall() if cur.description else None

    try:
        query('''CREATE TABLE prostudio_generation_jobs (
            id TEXT PRIMARY KEY, status TEXT, conversation_id TEXT,
            response_json JSONB, result_json JSONB, error_json JSONB, cost INTEGER,
            updated_at TIMESTAMPTZ, completed_at TIMESTAMPTZ)''')
        query('''CREATE TABLE prostudio_messages (
            id SERIAL PRIMARY KEY, conversation_id TEXT, telegram_id BIGINT, mode TEXT,
            prompt TEXT, response_text TEXT, image_url TEXT, images_json JSONB, thumbnails_json JSONB,
            thumb_url TEXT, video_url TEXT, videos_json JSONB, audio_url TEXT, audios_json JSONB,
            metadata_json JSONB, status TEXT, model TEXT, provider TEXT, cost INTEGER,
            request_json JSONB, response_json JSONB, updated_at TIMESTAMPTZ, completed_at TIMESTAMPTZ)''')
        with transaction() as conn:
            with conn.cursor() as cursor:
                main.generation_storage.ensure_table(cursor)
        monkeypatch.setattr(main,'DATABASE_URL',dsn)
        monkeypatch.setattr(main,'db_connect',connect)
        monkeypatch.setattr(main,'db_connection',transaction)
        monkeypatch.setattr(main,'ensure_prostudio_table',lambda:None)
        monkeypatch.setattr(main,'ensure_reservations',lambda *a:None)
        yield SimpleNamespace(query=query, connect=connect, transaction=transaction)
    finally:
        with admin.cursor() as cur:
            cur.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(schema)))
        admin.close()


def test_real_postgres_job_and_background_merge_preserve_all_outputs(result_database):
    db=result_database
    db.query("INSERT INTO prostudio_generation_jobs(id,status,cost) VALUES ('long-job','processing',19)")
    images=['https://provider.example.test/result-'+str(i)+'.png?test_signature='+('x'*1800) for i in range(4)]
    result={'ok':True,'type':'image','images':images,'image_url':images[0],
        'text':'Полный результат.\n'*200,'cost_credits':19,'metadata':{'image_url':images[0]}}
    assert main.update_prostudio_generation_job('long-job','completed',result)
    status,response,saved,cost=db.query('SELECT status,response_json,result_json,cost FROM prostudio_generation_jobs')[0]
    assert status=='completed' and cost==19
    assert response==saved==result
    main._merge_prostudio_result_fields('long-job',{'thumbnail_status':'completed'})
    status,saved,cost=db.query('SELECT status,result_json,cost FROM prostudio_generation_jobs')[0]
    assert status=='completed' and cost==19
    assert saved['thumbnail_status']=='completed'
    for key,value in result.items():
        if key=='metadata':
            assert all(saved['metadata'][name]==item for name,item in value.items())
        else:assert saved[key]==value
    assert saved['metadata']['result_images']==images


def test_real_postgres_history_insert_and_regenerate_preserve_full_text_and_refs(result_database):
    db=result_database
    url='https://storage.example.test/ref.png?test_signature='+('x'*1800)
    payload={'telegram_id':101,'conversation_id':'long-history','mode':'text','prompt':'Запрос.\n'*250,
        'model':'test-text-model','provider':'test-provider','image_options':{'referenceImageUrls':[url]}}
    result={'ok':True,'type':'text','text':'Развёрнутый ответ.\n'*250,'metadata':{'type':'text','input_images':[url]}}
    expected=json.loads(json.dumps(result))
    assert main.save_prostudio_message(payload,result)=='long-history'
    saved_request,saved_response,answer=db.query('SELECT request_json,response_json,response_text FROM prostudio_messages')[0]
    assert saved_request==payload and saved_response==expected and answer==expected['text']
    replacement={'ok':True,'type':'text','text':'Новый развёрнутый ответ.\n'*250,'metadata':{'type':'text','input_images':[url]}}
    updated={**payload,'replace_message_id':result['message_id']}
    expected=json.loads(json.dumps(replacement))
    main.save_prostudio_message(updated,replacement)
    assert db.query('SELECT count(*) FROM prostudio_messages')[0][0]==1
    response,answer=db.query('SELECT response_json,response_text FROM prostudio_messages')[0]
    assert response==expected and answer==expected['text']
