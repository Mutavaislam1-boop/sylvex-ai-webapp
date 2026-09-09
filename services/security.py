"""Request authentication and limits. Business handlers remain responsible for resource ownership."""
from __future__ import annotations
import asyncio
import contextvars
import hashlib
import hmac
import json
import os
import re
import time
from collections import OrderedDict
from urllib.parse import parse_qsl, urlencode
from starlette.responses import JSONResponse

actor_id = contextvars.ContextVar('sylvex_actor_id', default=0)
actor_init_data = contextvars.ContextVar('sylvex_init_data', default='')
PUBLIC_GETS = frozenset({
 '/health/live', '/health/ready', '/api/public/config', '/api/payment-links',
 '/api/public/prostudio/preset-catalog', '/api/public/prostudio/voice-avatars',
 '/api/public/prostudio/image-capabilities', '/api/public/prostudio/video-templates',
 '/api/public/prostudio/photo-catalog', '/api/public/prostudio/photo-tool-demos',
 '/api/public/prostudio/quick-image-catalog', '/api/public/prostudio/kling/effects',
 '/api/public/prostudio/pricing-catalog',
 '/api/public/video/templates',
})
MULTIPART_ROUTES = frozenset({'/api/public/prostudio/upload-media','/api/public/prostudio/transcribe','/api/public/prostudio/elevenlabs/voice-clone'})
WEBHOOKS = frozenset({'/api/public/payments/stars/webhook','/api/public/payments/paypal/webhook'})
PUBLIC_PATTERNS = [re.compile(x) for x in (
 r'/api/public/prostudio/voice-avatar/[A-Za-z0-9_-]+',
 r'/api/public/video/templates/[^/]+',
 r'/api/public/prostudio/share/[A-Za-z0-9_-]+(?:/(?:download|media))?',
)]

class SecurityError(ValueError):
 def __init__(self, code, status=401): self.code, self.status = code, status; super().__init__(code)

def bot_tokens():
 return tuple(dict.fromkeys(x.strip() for x in (os.getenv('BOT_TOKEN',''),os.getenv('TELEGRAM_BOT_TOKEN','')) if x.strip()))

def validated_user(init_data, tokens=None, now=None):
 if not isinstance(init_data,str) or len(init_data)>16384: raise SecurityError('invalid_init_data')
 pairs=parse_qsl(init_data,keep_blank_values=True)
 data=dict(pairs)
 if len(data)!=len(pairs): raise SecurityError('duplicate_init_data_fields')
 received=data.pop('hash','')
 if not re.fullmatch(r'[a-fA-F0-9]{64}',received): raise SecurityError('invalid_init_data')
 message='\n'.join(f'{k}={data[k]}' for k in sorted(data)).encode()
 tokens=bot_tokens() if tokens is None else tokens
 if not tokens: raise SecurityError('telegram_auth_not_configured',503)
 valid=any(hmac.compare_digest(hmac.new(hmac.new(b'WebAppData',t.encode(),hashlib.sha256).digest(),message,hashlib.sha256).hexdigest(),received.lower()) for t in tokens)
 if not valid: raise SecurityError('invalid_init_data')
 try:
  age=(time.time() if now is None else now)-int(data['auth_date'])
  if age < -30 or age > int(os.getenv('TELEGRAM_AUTH_MAX_AGE_SECONDS','3600')): raise ValueError()
  user=json.loads(data['user'])
  if not isinstance(user,dict) or isinstance(user.get('id'),bool) or not isinstance(user.get('id'),int) or user['id']<=0: raise ValueError()
 except (KeyError,ValueError,TypeError): raise SecurityError('expired_or_invalid_telegram_user')
 return user

def signing_key():
 # Domain separation keeps media/session tokens independent from Telegram HMAC.
 key=os.getenv('MEDIA_SIGNING_SECRET','').strip() or next(iter(bot_tokens()),'')
 if not key: raise SecurityError('media_signing_not_configured',503)
 return hmac.new(key.encode(),b'SYLVEX media v1',hashlib.sha256).digest()

class LocalLimiter:
 def __init__(self): self.items=OrderedDict()
 def allow(self,key,limit,seconds):
  now=time.monotonic();count,start=self.items.pop(key,(0,now))
  if now-start>=seconds:count,start=0,now
  self.items[key]=(count+1,start)
  while len(self.items)>10000:self.items.popitem(last=False)
  return count<limit

class SecurityMiddleware:
 def __init__(self,app,quota_check=None): self.app=app;self.limiter=LocalLimiter();self.quota_check=quota_check
 async def __call__(self,scope,receive,send):
  if scope['type']!='http':return await self.app(scope,receive,send)
  path=scope['path'];method=scope['method'];headers=dict(scope.get('headers',[]))
  from services.media_access import media_key, valid_media_url, validate_input_media, sign_response_media
  media_path=path.startswith(('/webapp/generated/','/static/generated/','/generated/','/api/public/storage/'))
  media_url=path+'?'+scope.get('query_string',b'').decode()
  media_allowed=False
  if media_path:
   media_allowed=method in {'GET','HEAD'} and valid_media_url(media_url)
   if not media_allowed:
    return await JSONResponse({'ok':False,'error':'media_authorization_required'},status_code=403)(scope,receive,send)
  protected=path.startswith('/api/') or path=='/save-settings' or media_path
  if not protected:return await self.app(scope,receive,send)
  is_public=media_allowed or (method in {'GET','HEAD'} and (path in PUBLIC_GETS or any(p.fullmatch(path) for p in PUBLIC_PATTERNS)))
  is_webhook=path in WEBHOOKS
  if path.startswith('/api/public/payments/dev/') and (os.getenv('APP_ENV','development')=='production' or os.getenv('ENABLE_DEV_PAYMENTS','0')!='1'):
   return await JSONResponse({'ok':False,'error':'not_found'},status_code=404)(scope,receive,send)
  ip=(scope.get('client') or ('unknown',))[0]
  # Do not trust forwarded headers supplied by clients. Per-user durable quotas supplement this process-local burst guard.
  if not is_webhook and not self.limiter.allow(('ip',ip),int(os.getenv('API_IP_REQUESTS_PER_MINUTE','1200')),60):
   return await JSONResponse({'ok':False,'error':'rate_limited'},status_code=429,headers={'Retry-After':'60'})(scope,receive,send)
  content_type=headers.get(b'content-type',b'').lower()
  multipart=content_type.startswith(b'multipart/form-data')
  if multipart and path not in MULTIPART_ROUTES:
   return await JSONResponse({'ok':False,'error':'unsupported_content_type'},status_code=415)(scope,receive,send)
  sdp=path=='/api/public/home-idea/realtime' and content_type.split(b';',1)[0].strip()==b'application/sdp'
  max_size=(201 if multipart else 16)*1024*1024
  if is_webhook or sdp:max_size=1024*1024
  try:
   if int(headers.get(b'content-length',b'0'))>max_size:raise SecurityError('request_too_large',413)
  except ValueError as exc:
   code=exc.code if isinstance(exc,SecurityError) else 'invalid_content_length';status=exc.status if isinstance(exc,SecurityError) else 400
   return await JSONResponse({'ok':False,'error':code},status_code=status)(scope,receive,send)
  query=parse_qsl(scope.get('query_string',b'').decode(),keep_blank_values=True)
  json_body=None;body=None
  try:
   # Authentication can be sent in the header for streamed multipart requests.
   if not multipart and not is_public and not is_webhook and method in {'POST','PUT','PATCH','DELETE'}:
    chunks=[];size=0
    while True:
     message=await receive()
     if message['type']=='http.disconnect':return
     chunk=message.get('body',b'');size+=len(chunk)
     if size>max_size:raise SecurityError('request_too_large',413)
     chunks.append(chunk)
     if not message.get('more_body'):break
    body=b''.join(chunks)
    if body and not sdp:
     try:json_body=json.loads(body)
     except (ValueError,UnicodeError):raise SecurityError('invalid_json',400)
     if not isinstance(json_body,dict):raise SecurityError('json_object_required',400)
   init_data=headers.get(b'x-telegram-init-data',b'').decode()
   if not init_data and json_body:init_data=str(json_body.get('initData') or json_body.get('init_data') or '')
   if not init_data:init_data=next((v for k,v in query if k in {'init_data','initData'}),'')
   uid=0
   if not is_public and not is_webhook:
    user=validated_user(init_data);uid=user['id']
    admin=path.startswith('/api/admin/')
    if not admin:
     ids=[v for k,v in query if k=='telegram_id']
     if json_body is not None and 'telegram_id' in json_body:ids.append(json_body['telegram_id'])
     if path.startswith('/api/cabinet/'):ids.append(path.rsplit('/',1)[-1])
     for claimed in ids:
      try:
       if isinstance(claimed, (bool, list, dict)) or int(claimed or 0) not in (0,uid):raise ValueError()
      except (ValueError,TypeError):raise SecurityError('user_mismatch',403)
     query=[(k,v) for k,v in query if k!='telegram_id']+[('telegram_id',str(uid))]
     scope['query_string']=urlencode(query).encode()
     if json_body is not None:json_body['telegram_id']=uid
    if json_body is not None:
     if not admin:
      for key in ('mode','category','model','provider','prompt'):
       if key in json_body and not isinstance(json_body[key],str):raise SecurityError('invalid_'+key,422)
      for key in ('image_options','video_options','voice_options','text_options'):
       if key in json_body and json_body[key] is not None and not isinstance(json_body[key],dict):raise SecurityError('invalid_'+key,422)
      if len(json_body.get('prompt',''))>100000:raise SecurityError('prompt_too_large',413)
      if 'history' in json_body and (not isinstance(json_body['history'],list) or len(json_body['history'])>100):raise SecurityError('invalid_history',422)
      validate_input_media(json_body)
     # Legacy handlers now see the same verified credentials as middleware.
     json_body['initData']=init_data;json_body['init_data']=init_data
     body=json.dumps(json_body,separators=(',',':')).encode()
    scope.setdefault('state',{}).update(telegram_id=uid,telegram_user=user,telegram_init_data=init_data)
    if self.quota_check and method=='POST' and not admin and path not in WEBHOOKS:
     await self.quota_check(uid,path)
  except SecurityError as exc:
   return await JSONResponse({'ok':False,'error':exc.code},status_code=exc.status)(scope,receive,send)
  size=0;replayed=False
  async def bounded_receive():
   nonlocal size,replayed
   if body is not None and not replayed:
    replayed=True;return {'type':'http.request','body':body,'more_body':False}
   message=await receive();size+=len(message.get('body',b''))
   if size>max_size:raise SecurityError('request_too_large',413)
   return message
  started=False; pending_start=None; response_parts=[]
  async def secured_send(message):
   nonlocal started, pending_start
   if message['type']=='http.response.start':
    started=True;message=dict(message);hs=list(message.get('headers',[]))
    hs.extend([(b'x-content-type-options',b'nosniff'),(b'referrer-policy',b'same-origin')])
    if uid:
     hs=[(k,v) for k,v in hs if k.lower()!=b'cache-control'];hs.append((b'cache-control',b'no-store'))
    # Content-derived safe MIME prevents legacy uploads from serving active HTML.
    if media_path:
     import mimetypes
     mime=mimetypes.guess_type(path)[0] or 'application/octet-stream'
     hs=[(k,v) for k,v in hs if k.lower()!=b'content-type']+[(b'content-type',mime.encode())]
     if not mime.startswith(('image/','audio/','video/')):
      hs.append((b'content-disposition',b'attachment'))
     hs=[(k,v) for k,v in hs if k.lower()!=b'cache-control']+[(b'cache-control',b'private, max-age=300')]
    message['headers']=hs
    if not media_path and not any(k.lower()==b'content-disposition' for k,v in hs) and any(k.lower()==b'content-type' and b'application/json' in v for k,v in hs):
     pending_start=message; return
   if message['type']=='http.response.body' and pending_start is not None:
    response_parts.append(message.get('body',b''))
    if message.get('more_body'):return
    raw=b''.join(response_parts)
    try:raw=json.dumps(sign_response_media(json.loads(raw)),ensure_ascii=False,separators=(',',':')).encode()
    except (ValueError,TypeError):pass
    pending_start['headers']=[(k,v) for k,v in pending_start['headers'] if k.lower()!=b'content-length']+[(b'content-length',str(len(raw)).encode())]
    await send(pending_start);pending_start=None
    return await send({'type':'http.response.body','body':raw,'more_body':False})
   await send(message)
  token=actor_id.set(uid);itoken=actor_init_data.set(init_data)
  try:await self.app(scope,bounded_receive,secured_send)
  except SecurityError as exc:
   if started:raise
   await JSONResponse({'ok':False,'error':exc.code},status_code=exc.status)(scope,receive,send)
  finally:actor_id.reset(token);actor_init_data.reset(itoken)
