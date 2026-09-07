import asyncio
import hashlib
import hmac
import io
import json
import time
from urllib.parse import urlencode
from unittest.mock import Mock, AsyncMock
import httpx
import pytest
from fastapi import FastAPI, Request
from services.security import SecurityMiddleware, SecurityError, validated_user
from services.safe_io import safe_local_path, public_addresses, read_upload, validated_upload_type
TOKEN='test-only-bot-token'

def signed(uid=101,age=0):
 fields={'user':json.dumps({'id':uid,'first_name':'Test'}),'auth_date':str(int(time.time())-age)}
 check='\n'.join(f'{k}={fields[k]}' for k in sorted(fields))
 fields['hash']=hmac.new(hmac.new(b'WebAppData',TOKEN.encode(),hashlib.sha256).digest(),check.encode(),hashlib.sha256).hexdigest()
 return urlencode(fields)

@pytest.fixture
def app(monkeypatch):
 monkeypatch.setenv('BOT_TOKEN',TOKEN);monkeypatch.delenv('TELEGRAM_BOT_TOKEN',raising=False)
 import main
 monkeypatch.setattr(main,'TELEGRAM_AUTH_TOKENS',(TOKEN,));monkeypatch.setattr(main,'BOT_TOKEN',TOKEN)
 monkeypatch.setattr(main,'sync_user_to_db',lambda user:user)
 # Skip spending quota DB only; all original authentication/handler logic is live.
 main.app.middleware_stack=None
 for mw in main.app.user_middleware:
  if mw.cls is SecurityMiddleware:mw.kwargs['quota_check']=AsyncMock()
 return main.app

@pytest.fixture
def client(app):
 return httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test')

@pytest.mark.asyncio
async def test_unsigned_private_route_inventory(client,app):
 from services.security import PUBLIC_GETS,PUBLIC_PATTERNS,WEBHOOKS
 checked=0
 for route in app.routes:
  path=getattr(route,'path','')
  if not path.startswith('/api/') and path!='/save-settings':continue
  if path in WEBHOOKS:continue
  import re
  concrete=re.sub(r'\{[^}]+\}','123',path)
  for method in getattr(route,'methods',set()):
   if method in {'GET','HEAD'} and (path in PUBLIC_GETS or any(p.fullmatch(concrete) for p in PUBLIC_PATTERNS)):continue
   r=await client.request(method,concrete,json={})
   assert r.status_code in {401,403,404},(method,path,r.status_code,r.text)
   checked+=1
 assert checked>75

@pytest.mark.asyncio
async def test_signed_sync_ignores_unsafe_user(client):
 r=await client.post('/api/public/telegram/sync',headers={'X-Telegram-Init-Data':signed()},json={'initDataUnsafe':{'user':{'id':999}}})
 assert r.status_code==200 and r.json()['user']['telegram_id']==101

@pytest.mark.asyncio
@pytest.mark.parametrize('payload',[{'telegram_id':999},{'telegram_id':'not-an-id'},{'telegram_id':[]}])
async def test_body_identity_mismatch(client,payload):
 r=await client.post('/api/public/telegram/profile',json=payload,headers={'X-Telegram-Init-Data':signed()})
 assert r.status_code==403

@pytest.mark.asyncio
async def test_query_identity_mismatch(client):
 r=await client.delete('/api/public/prostudio/conversations?telegram_id=999&conversation_id=test',headers={'X-Telegram-Init-Data':signed()})
 assert r.status_code==403

@pytest.mark.asyncio
async def test_path_identity_mismatch(client):
 r=await client.get('/api/cabinet/999',headers={'X-Telegram-Init-Data':signed()})
 assert r.status_code==403

@pytest.mark.parametrize('age',[3601,86400,-60])
def test_stale_and_future_data_rejected(age):
 with pytest.raises(SecurityError):validated_user(signed(age=age),[TOKEN])

def test_signature_tamper_and_duplicate_rejected():
 with pytest.raises(SecurityError):validated_user(signed()+'&user=%7B%22id%22%3A999%7D',[TOKEN])
 with pytest.raises(SecurityError):validated_user(signed().replace('Test','Evil'),[TOKEN])

@pytest.mark.asyncio
async def test_stars_missing_or_wrong_secret(client,monkeypatch):
 import main
 finalizer=Mock();monkeypatch.setattr(main,'finalize_shop_payment',finalizer)
 monkeypatch.setattr(main,'TELEGRAM_PAYMENT_WEBHOOK_SECRET','')
 r=await client.post('/api/public/payments/stars/webhook',json={'message':{'successful_payment':{}}})
 assert r.status_code==503
 monkeypatch.setattr(main,'TELEGRAM_PAYMENT_WEBHOOK_SECRET','test-secret')
 r=await client.post('/api/public/payments/stars/webhook',json={})
 assert r.status_code==401
 r=await client.post('/api/public/payments/stars/webhook',headers={'X-Telegram-Bot-Api-Secret-Token':'test-secret'},json={})
 assert r.status_code==200
 finalizer.assert_not_called()

@pytest.mark.asyncio
async def test_malformed_json_and_body_limit(client):
 r=await client.post('/api/public/telegram/sync',content='[1]',headers={'X-Telegram-Init-Data':signed()})
 assert r.status_code==400
 r=await client.post('/api/public/telegram/sync',content='{}',headers={'Content-Length':str(17*1024*1024)})
 assert r.status_code==413

@pytest.mark.asyncio
async def test_chunked_body_limit_without_content_length():
 app=FastAPI();app.add_middleware(SecurityMiddleware)
 @app.post('/api/test')
 async def target(request:Request):return {'unexpected':True}
 messages=[{'type':'http.request','body':b'x'*(8*1024*1024),'more_body':True}]*3
 sent=[]
 async def receive():return messages.pop(0)
 async def send(message):sent.append(message)
 await app({'type':'http','asgi':{'version':'3.0'},'method':'POST','path':'/api/test','query_string':b'','headers':[],'scheme':'http','server':('test',80),'client':('test',1),'root_path':''},receive,send)
 assert sent[0]['status']==413

@pytest.mark.parametrize('path',['../outside.txt','%2e%2e/outside.txt','.env','/etc/passwd','a/../../outside','a\\..\\outside'])
def test_traversal(path,tmp_path):
 with pytest.raises(SecurityError):safe_local_path(tmp_path,path)

def test_symlink_escape(tmp_path):
 inside=tmp_path/'inside';inside.mkdir();(inside/'linked').symlink_to(tmp_path)
 with pytest.raises(SecurityError):safe_local_path(inside,'linked/outside')

@pytest.mark.parametrize('url',['file:///etc/passwd','http://localhost','http://127.0.0.1','http://169.254.169.254','http://[::1]','http://example.com:5432','http://user:password@example.com'])
def test_ssrf_blocked(url,monkeypatch):
 monkeypatch.setattr('socket.getaddrinfo',lambda *a,**k:[(2,1,6,'',('127.0.0.1',80))])
 with pytest.raises(SecurityError):public_addresses(url)

@pytest.mark.asyncio
async def test_upload_stream_stops_at_limit():
 file=Mock();file.read=AsyncMock(side_effect=[b'1234',b'5678',b'must-not-read'])
 with pytest.raises(SecurityError):await read_upload(file,5)
 assert file.read.await_count==2

def test_html_disguised_as_image():
 with pytest.raises(SecurityError):validated_upload_type(b'<script>alert(1)</script>','.jpg')

def test_pdf_mime_is_server_derived():
 assert validated_upload_type(b'%PDF-1.7 fake document','.pdf')=='application/pdf'

@pytest.mark.asyncio
async def test_job_lookup_includes_owner(client,monkeypatch):
 import main
 cur=Mock();cur.fetchone.return_value=None;conn=Mock();conn.cursor.return_value=cur
 monkeypatch.setattr(main,'DATABASE_URL','test');monkeypatch.setattr(main,'db_connect',lambda _:conn);monkeypatch.setattr(main,'ensure_prostudio_table',lambda:None)
 r=await client.get('/api/public/prostudio/job/guessed-job',headers={'X-Telegram-Init-Data':signed()})
 assert r.status_code==404
 sql,params=cur.execute.call_args.args
 assert 'telegram_id = %s' in sql and params==('guessed-job',101)

@pytest.mark.asyncio
async def test_template_uses_existing_admission(client,monkeypatch):
 import main
 import routers.video_templates as templates
 monkeypatch.setattr(templates,'get_template',lambda _: {'prompt':'template','reference_video':'https://example.invalid/video.mp4'})
 captured=[]
 async def enqueue(request):captured.append(await request.json());return {'ok':True,'job_id':'queued'}
 monkeypatch.setattr(main,'public_prostudio_generate',enqueue)
 direct=AsyncMock();monkeypatch.setattr(templates,'video_generation',direct)
 r=await client.post('/api/public/video/templates/test/generate',json={'image':'https://example.invalid/image.png'},headers={'X-Telegram-Init-Data':signed()})
 assert r.status_code==200 and captured[0]['telegram_id']==101
 direct.assert_not_called()

@pytest.mark.asyncio
async def test_signed_storage_and_rejection_after_tamper(client,monkeypatch,tmp_path):
 from services.media_access import sign_media_url
 import services.storage as storage
 monkeypatch.setattr(storage,'LOCAL_GENERATED_DIR',tmp_path/'generated')
 (tmp_path/'generated').mkdir();(tmp_path/'generated'/'test.txt').write_text('test-file')
 url=sign_media_url('/webapp/generated/test.txt')
 r=await client.get(url)
 assert r.status_code==200 and r.text=='test-file'
 assert r.headers['x-content-type-options']=='nosniff'
 assert r.headers['content-disposition']=='attachment'
 r=await client.get(url.replace('test.txt','other.txt'))
 assert r.status_code==403
 r=await client.get('/webapp/generated/test.txt')
 assert r.status_code==403

def test_input_media_needs_existing_capability(monkeypatch):
 from services.media_access import sign_media_url,validate_input_media
 monkeypatch.setenv('BOT_TOKEN',TOKEN)
 with pytest.raises(SecurityError):validate_input_media({'url':'/webapp/generated/private.png'})
 validate_input_media({'url':sign_media_url('/webapp/generated/private.png'),'path':'generated/private.png'})

def test_paypal_binding_rejects_another_owner_or_plan(monkeypatch):
 from services.paypal_binding import make_binding,read_binding
 monkeypatch.setenv('BOT_TOKEN',TOKEN)
 value=make_binding(101,'P-TEST')
 assert len(value)<=127 and read_binding(value,'P-TEST')==101
 with pytest.raises(SecurityError):read_binding(value.replace('101','999'),'P-TEST')
 with pytest.raises(SecurityError):read_binding(value,'P-OTHER')

@pytest.mark.asyncio
async def test_activation_is_not_a_paid_subscription(client,monkeypatch):
 import main
 finalizer=Mock();monkeypatch.setattr(main,'finalize_shop_payment',finalizer)
 assert main.activate_paypal_subscription_from_event({'event_type':'BILLING.SUBSCRIPTION.ACTIVATED'}) is False
 finalizer.assert_not_called()

def test_remote_redirect_revalidates_ip_and_pins_connection(monkeypatch):
 from services.safe_io import safe_get
 resolved=[];pools=[]
 def dns(host,port,**kw):
  resolved.append(host)
  return [(2,1,6,'',('93.184.216.34' if host=='example.com' else '127.0.0.1',port))]
 monkeypatch.setattr('socket.getaddrinfo',dns)
 response=Mock(status=302,headers={'location':'http://internal.test/secret'})
 pool=Mock();pool.urlopen.return_value=response
 def factory(**kw):pools.append(kw);return pool
 monkeypatch.setattr('urllib3.HTTPSConnectionPool',factory)
 with pytest.raises(SecurityError):safe_get('https://example.com/file')
 assert resolved==['example.com','internal.test']
 assert pools[0]['host']=='93.184.216.34' and pools[0]['server_hostname']=='example.com'
 response.close.assert_called_once()

def test_safe_download_has_streaming_byte_limit(monkeypatch):
 from services.safe_io import safe_get
 monkeypatch.setattr('socket.getaddrinfo',lambda *a,**k:[(2,1,6,'',('93.184.216.34',443))])
 response=Mock(status=200,headers={});response.stream.return_value=iter([b'1234',b'5678'])
 pool=Mock();pool.urlopen.return_value=response
 monkeypatch.setattr('urllib3.HTTPSConnectionPool',lambda **kw:pool)
 with pytest.raises(SecurityError):safe_get('https://example.com/file',max_bytes=5)
 response.close.assert_called_once()

@pytest.mark.asyncio
async def test_startup_and_shutdown_in_isolation(app,monkeypatch):
 import main
 from fastapi.testclient import TestClient
 monkeypatch.setattr(main,'DATABASE_URL','')
 monkeypatch.setattr(main,'PROSTUDIO_WORKER_ENABLED',False)
 monkeypatch.setattr(main,'SUBSCRIPTION_REMINDER_WORKER_ENABLED',False)
 with TestClient(app) as test:
  assert test.get('/health/live').status_code==200
  assert test.get('/health/ready').status_code==503
  assert test.get('/').status_code==200
  assert test.get('/js/api-auth.js').status_code==200

def test_model_text_cannot_mint_media_capabilities(monkeypatch):
 from services.media_access import sign_response_media
 monkeypatch.setenv('BOT_TOKEN',TOKEN)
 value='/webapp/generated/private.png'
 result=sign_response_media({'text':value,'prompt':value,'image_url':value})
 assert result['text']==value and result['prompt']==value
 assert 'media_sig=' in result['image_url']

@pytest.mark.asyncio
async def test_json_upload_download_is_byte_for_byte(client,monkeypatch,tmp_path):
 from services.media_access import sign_media_url
 import services.storage as storage
 monkeypatch.setattr(storage,'LOCAL_GENERATED_DIR',tmp_path/'generated')
 (tmp_path/'generated').mkdir()
 original=b'{ "text": "/webapp/generated/another.txt", "number":  42 }\n'
 (tmp_path/'generated'/'file.json').write_bytes(original)
 r=await client.get(sign_media_url('/webapp/generated/file.json'))
 assert r.status_code==200 and r.content==original

def test_old_public_r2_url_is_reissued_through_private_proxy(monkeypatch):
 from services.media_access import sign_response_media
 import services.storage as storage
 monkeypatch.setenv('BOT_TOKEN',TOKEN)
 monkeypatch.setenv('LEGACY_R2_PUBLIC_BASE_URL','https://old-bucket.example')
 old='https://old-bucket.example/generated/images/old.png'
 assert storage.key_from_url(old)=='generated/images/old.png'
 new=sign_response_media({'image_url':old})['image_url']
 assert '/api/public/storage/generated/images/old.png?' in new and 'old-bucket.example' not in new

@pytest.mark.asyncio
async def test_multipart_header_cannot_bypass_json_identity(client,monkeypatch):
 import main
 db=Mock();monkeypatch.setattr(main,'db_connect',db)
 r=await client.post('/api/public/telegram/profile',content=json.dumps({'telegram_id':999}),headers={'X-Telegram-Init-Data':signed(),'Content-Type':'multipart/form-data; boundary=fake'})
 assert r.status_code==415
 db.assert_not_called()

@pytest.mark.asyncio
async def test_raw_sdp_is_preserved(client,monkeypatch):
 import main
 monkeypatch.setattr(main,'OPENAI_API_KEY','test-only')
 response=Mock(status_code=201,text='answer-sdp',content=b'answer-sdp',headers={'content-type':'application/sdp'})
 post=Mock(return_value=response);monkeypatch.setattr(main.requests,'post',post)
 r=await client.post('/api/public/home-idea/realtime',content='v=0\r\ns=synthetic\r\n',headers={'X-Telegram-Init-Data':signed(),'Content-Type':'application/sdp'})
 assert r.status_code==201 and r.content==b'answer-sdp'
 assert post.call_args.kwargs['files']['sdp'][1]=='v=0\r\ns=synthetic'

@pytest.mark.asyncio
async def test_voice_clone_form_cannot_claim_other_user(client,monkeypatch):
 import main
 clone=AsyncMock();monkeypatch.setattr(main,'elevenlabs_clone_voice_from_audio',clone)
 r=await client.post('/api/public/prostudio/elevenlabs/voice-clone',files={'file':('test.wav',b'RIFFtest','audio/wav')},data={'telegram_id':'999'},headers={'X-Telegram-Init-Data':signed()})
 assert r.status_code==403
 clone.assert_not_called()

def test_update_failure_rolls_back_and_closes(monkeypatch):
 import main
 cur=Mock();cur.fetchone.return_value=['processing'];cur.execute.side_effect=[None,RuntimeError('synthetic failure')]
 conn=Mock();conn.cursor.return_value=cur
 monkeypatch.setattr(main,'DATABASE_URL','test');monkeypatch.setattr(main,'db_connect',lambda _:conn)
 monkeypatch.setattr(main,'ensure_prostudio_table',lambda:None);monkeypatch.setattr(main,'ensure_reservations',lambda _:None)
 monkeypatch.setattr(main,'release_generation',lambda c,j:None)
 assert main.update_prostudio_generation_job('test','failed') is False
 assert 'FOR UPDATE' in cur.execute.call_args_list[0].args[0]
 conn.rollback.assert_called_once();conn.close.assert_called_once();cur.close.assert_called_once()

def test_subscription_preserves_referral_events(monkeypatch):
 import main
 monkeypatch.setattr(main,'DATABASE_URL','test')
 for name in ('ensure_user_exists','ensure_payment_tables','send_subscription_congratulations'):monkeypatch.setattr(main,name,Mock())
 monkeypatch.setattr(main,'apply_payment',Mock(return_value=True))
 event=Mock();monkeypatch.setattr(main,'log_user_event',event)
 assert main.finalize_shop_payment(101,'stars',{'kind':'subscription','plan_key':'month','bonus_credits':40,'days':30},5,'XTR','test','charge')
 types=[c.kwargs.get('event_type') for c in event.call_args_list]
 assert types==['payment_success','subscription_activated','credits_added']
