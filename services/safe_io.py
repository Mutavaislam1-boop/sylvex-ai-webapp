"""Bounded media IO. Remote connections are pinned to a validated public IP."""
from __future__ import annotations
import asyncio
import ipaddress
import mimetypes
import os
from pathlib import Path
import socket
import ssl
import time
from urllib.parse import unquote, urljoin, urlsplit, urlencode
import certifi
import requests
import urllib3
from services.security import SecurityError

MAX_REMOTE_BYTES=200*1024*1024

def safe_local_path(root, relative):
 root=Path(root).resolve()
 value=unquote(urlsplit(str(relative)).path).replace('\\','/')
 parts=value.split('/')
 if value.startswith('/') or any(p=='..' or p.startswith('.') for p in parts if p):
  raise SecurityError('invalid_media_path',400)
 path=(root/value).resolve()
 if not path.is_relative_to(root) or path==root:raise SecurityError('invalid_media_path',400)
 return path

def public_addresses(url):
 try:
  parsed=urlsplit(url)
  if parsed.scheme not in {'http','https'} or not parsed.hostname or parsed.username or parsed.password:raise ValueError()
  port=parsed.port or (443 if parsed.scheme=='https' else 80)
  if port not in {80,443}:raise ValueError()
  hostname=parsed.hostname.encode('idna').decode()
  if any(c in hostname for c in '\r\n\x00%'):raise ValueError()
  entries=socket.getaddrinfo(hostname,port,type=socket.SOCK_STREAM)
  ips=tuple(dict.fromkeys(item[4][0] for item in entries))
  if not ips or any(not ipaddress.ip_address(ip).is_global for ip in ips):raise ValueError()
 except (ValueError,UnicodeError,OSError):raise SecurityError('unsafe_remote_url',400)
 return parsed,hostname,port,ips

def safe_get(url, *, timeout=60, headers=None, params=None, max_bytes=MAX_REMOTE_BYTES, **kwargs):
 if kwargs:raise ValueError('unsupported_safe_get_option')
 if params:
  query=urlencode(params,doseq=True);url=str(url)+('&' if urlsplit(str(url)).query else '?')+query
 url=str(url);request_headers=dict(headers or {})
 for redirect in range(6):
  parsed,hostname,port,ips=public_addresses(url)
  request_headers['Host']=hostname if port in {80,443} else f'{hostname}:{port}'
  request_headers['Accept-Encoding']='identity'
  seconds=float(timeout if isinstance(timeout,(int,float)) else 60)
  pool_args=dict(host=ips[0],port=port,timeout=urllib3.Timeout(connect=min(seconds,15),read=seconds),retries=False)
  if parsed.scheme=='https':
   pool=urllib3.HTTPSConnectionPool(**pool_args,server_hostname=hostname,assert_hostname=hostname,cert_reqs=ssl.CERT_REQUIRED,ca_certs=certifi.where())
  else:pool=urllib3.HTTPConnectionPool(**pool_args)
  response=None
  deadline=time.monotonic()+seconds
  try:
   target=parsed.path or '/'
   if parsed.query:target+='?'+parsed.query
   response=pool.urlopen('GET',target,headers=request_headers,redirect=False,preload_content=False)
   if response.status in {301,302,303,307,308}:
    location=response.headers.get('location')
    if not location:raise SecurityError('invalid_remote_redirect',400)
    next_url=urljoin(url,location)
    if urlsplit(next_url).netloc!=parsed.netloc or urlsplit(next_url).scheme!=parsed.scheme:
     request_headers={k:v for k,v in request_headers.items() if k.lower() in {'accept','range','user-agent'}}
    url=next_url;continue
   length=response.headers.get('content-length')
   if length and int(length)>max_bytes:raise SecurityError('remote_file_too_large',413)
   chunks=[];size=0
   for chunk in response.stream(65536,decode_content=True):
    if time.monotonic()>deadline:raise SecurityError('remote_download_timeout',504)
    size+=len(chunk)
    if size>max_bytes:raise SecurityError('remote_file_too_large',413)
    chunks.append(chunk)
   result=requests.Response();result.status_code=response.status;result.headers.update(response.headers);result._content=b''.join(chunks);result.url=url
   return result
  finally:
   if response is not None:response.close()
   pool.close()
 raise SecurityError('too_many_remote_redirects',400)

async def safe_client_get(client,url,**kwargs):
 # Retain provider client headers/params while enforcing the same network boundary.
 headers=dict(client.headers);headers.update(kwargs.pop('headers',{}) or {})
 params=dict(client.params);params.update(kwargs.pop('params',{}) or {})
 full_url=urljoin(str(client.base_url),str(url))
 return await asyncio.to_thread(safe_get,full_url,headers=headers,params=params,**kwargs)

async def read_upload(file,max_bytes):
 chunks=[];size=0
 while chunk:=await file.read(65536):
  size+=len(chunk)
  if size>max_bytes:raise SecurityError('file_too_large',413)
  chunks.append(chunk)
 return b''.join(chunks)

def validated_upload_type(content,suffix):
 """Do not publish a MIME type supplied by an upload client."""
 import io
 import zipfile
 suffix=suffix.lower()
 if suffix in {'.jpg','.jpeg','.png','.webp'}:
  from PIL import Image
  try:
   with Image.open(io.BytesIO(content)) as img:
    if img.width*img.height>40_000_000:raise ValueError()
    fmt=img.format;img.verify()
   if fmt not in {'JPEG','PNG','WEBP'}:raise ValueError()
  except Exception:raise SecurityError('invalid_image',400)
  return {'JPEG':'image/jpeg','PNG':'image/png','WEBP':'image/webp'}[fmt]
 if suffix=='.pdf' and not content.startswith(b'%PDF-'):raise SecurityError('invalid_pdf',400)
 if suffix=='.docx':
  try:
   with zipfile.ZipFile(io.BytesIO(content)) as archive:
    if '[Content_Types].xml' not in archive.namelist() or sum(i.file_size for i in archive.infolist())>100*1024*1024:raise ValueError()
  except Exception:raise SecurityError('invalid_document',400)
 # Media is served with a fixed MIME and nosniff. Document routes force download.
 return mimetypes.guess_type('upload'+suffix)[0] or 'application/octet-stream'
