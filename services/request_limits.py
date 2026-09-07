"""Cross-process quotas for endpoints that spend provider/storage resources."""
from __future__ import annotations
import asyncio
import os
import threading
import time
from db_pool import db_connect
from services.security import SecurityError

_lock=threading.Lock();_ready=False
COSTLY=frozenset({
 '/api/public/prostudio/generate','/api/public/prostudio/character',
 '/api/public/prostudio/runway-avatar','/api/public/prostudio/transcribe',
 '/api/public/prostudio/voice/text-tool','/api/public/prostudio/elevenlabs/voice-clone',
 '/api/public/prostudio/voice-preview','/api/elevenlabs/preview',
 '/api/public/prostudio/voice-avatars/ensure','/api/public/home-idea/route',
 '/api/public/home-idea/realtime','/api/public/prostudio/grid/plan',
 '/api/public/prostudio/upload-media',
})
def ensure_limit_table(dsn):
 global _ready
 with _lock:
  if _ready:return
  with db_connect(dsn) as conn:
   with conn.cursor() as cur:
    cur.execute('CREATE TABLE IF NOT EXISTS sylvex_request_limits (user_id BIGINT NOT NULL, bucket TEXT NOT NULL, window_start BIGINT NOT NULL, hits INTEGER NOT NULL, PRIMARY KEY(user_id,bucket))')
   conn.commit()
  _ready=True

def check_quota(user_id,path):
 if path not in COSTLY and not path.endswith('/generate'):return
 dsn=os.getenv('DATABASE_PUBLIC_URL') or os.getenv('DATABASE_URL')
 if not dsn:raise SecurityError('database_not_configured',503)
 try:
  ensure_limit_table(dsn)
  with db_connect(dsn) as conn:
   with conn.cursor() as cur:
    # Aggregate all paid helper routes, preventing bypass by switching endpoints.
    bucket='upload' if path.endswith('/upload-media') else 'provider'
    for period,default in ((60,12),(86400,200)):
     limit=int(os.getenv(f'{bucket.upper()}_REQUESTS_PER_{"MINUTE" if period==60 else "DAY"}',str(default)))
     window=int(time.time())//period
     cur.execute('''INSERT INTO sylvex_request_limits(user_id,bucket,window_start,hits) VALUES(%s,%s,%s,1)
      ON CONFLICT(user_id,bucket) DO UPDATE SET window_start=EXCLUDED.window_start,
      hits=CASE WHEN sylvex_request_limits.window_start=EXCLUDED.window_start THEN sylvex_request_limits.hits+1 ELSE 1 END
      RETURNING hits''',(user_id,f'{bucket}:{period}',window))
     if cur.fetchone()[0]>limit:raise SecurityError('usage_limit_reached',429)
   conn.commit()
 except SecurityError:raise
 except Exception:raise SecurityError('usage_limit_unavailable',503)

async def check_request_quota(user_id,path):
 await asyncio.to_thread(check_quota,user_id,path)
