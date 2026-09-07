"""Time-limited media capabilities for browser, Telegram and provider downloads."""
from __future__ import annotations
import hashlib
import hmac
import os
import time
from urllib.parse import urlsplit,parse_qs,urlencode,unquote,quote
from services.security import SecurityError,signing_key

PREFIXES=('/api/public/storage/','/webapp/','/static/','/')
def media_key(value):
 if not isinstance(value,str) or not value.startswith(('/', 'generated/', 'http://', 'https://')):return ''
 parsed=urlsplit(value)
 if parsed.netloc:
  allowed={urlsplit(os.getenv(k,'')).netloc for k in ('WEBAPP_URL','R2_PUBLIC_BASE_URL','LEGACY_R2_PUBLIC_BASE_URL') if os.getenv(k)}
  if parsed.netloc not in allowed:return ''
 path=unquote(parsed.path)
 for base in (os.getenv('R2_PUBLIC_BASE_URL',''),os.getenv('LEGACY_R2_PUBLIC_BASE_URL','')):
  if base and value.startswith(base.rstrip('/')+'/'):
   path=unquote(urlsplit(value[len(base.rstrip('/')):]).path)
   break
 for prefix in PREFIXES:
  if path.startswith(prefix) and path[len(prefix):].startswith('generated/'):
   key=path[len(prefix):];break
 else:
  if path.startswith('generated/'):key=path
  else:return ''
 if any(p.startswith('.') for p in key.replace('\\','/').split('/') if p):raise SecurityError('invalid_media_path',400)
 return key

def valid_media_url(value):
 try:
  key=media_key(value);query=parse_qs(urlsplit(value).query)
  exp=query.get('media_exp',[''])[0];sig=query.get('media_sig',[''])[0]
  if not key or int(exp)<time.time():return False
  expected=hmac.new(signing_key(),f'{key}:{exp}'.encode(),hashlib.sha256).hexdigest()
  return hmac.compare_digest(sig,expected)
 except (ValueError,SecurityError):return False

def sign_media_url(value):
 key=media_key(value)
 if not key:return value
 try:
  exp=str(int(time.time())+int(os.getenv('MEDIA_URL_TTL_SECONDS','604800')))
  sig=hmac.new(signing_key(),f'{key}:{exp}'.encode(),hashlib.sha256).hexdigest()
 except SecurityError:
  # No authentication credentials: local storage unit tests may still use plain filesystem URLs.
  if os.getenv('APP_ENV')=='production':raise
  return value
 base=os.getenv('WEBAPP_URL','').rstrip('/')
 return f'{base}/api/public/storage/{quote(key,safe="/")}?' + urlencode({'media_exp':exp,'media_sig':sig})

MEDIA_FIELDS = frozenset({'url','image_url','video_url','audio_url','music_url','file_url','document_url','media_url','thumbnail_url','thumb_url','full_url','result_url','song_url','avatar_url','custom_avatar_url','photo_url','preview_url','preview_video','reference_video','images','videos','audios','audio_urls','thumbnails','files','src','avatar_path'})

def sign_response_media(value, field=''):
 if isinstance(value,str):
  return sign_media_url(value) if field in MEDIA_FIELDS and value.startswith(('/','http://','https://')) else value
 if isinstance(value,list):return [sign_response_media(v,field) for v in value]
 if isinstance(value,dict):return {k:sign_response_media(v,k) for k,v in value.items()}
 return value


def validate_input_media(value):
 strings=[]
 def visit(v):
  if isinstance(v,str):strings.append(v)
  elif isinstance(v,list):
   for item in v:visit(item)
  elif isinstance(v,dict):
   for item in v.values():visit(item)
 visit(value)
 permitted={media_key(v) for v in strings if valid_media_url(v)}
 for v in strings:
  # Only actual path/URL fields, not text containing a URL, are treated as references.
  key=media_key(v)
  if key and key not in permitted:raise SecurityError('media_authorization_required',403)
  if v.startswith(('/webapp/','/generated/','/preset_catalog/')) and any(p.startswith('.') for p in unquote(urlsplit(v).path).replace('\\','/').split('/') if p):
   raise SecurityError('invalid_media_path',400)
