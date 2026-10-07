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
 '/api/web/assistant/message','/api/web/assistant/realtime/session','/api/web/assistant/files',
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

# Object Creation abuse protection: a dedicated bucket, deliberately
# separate from COSTLY's shared 'provider'/'upload' buckets above, checked
# only at the exact point main.py's public_prostudio_create_object creates
# a new Object Creation job (never on polling/status-read/jobs-list
# endpoints, which never call this). Kept distinct so a burst of Object
# Creation attempts can never exhaust quota shared with unrelated costly
# endpoints (image/video generation, voice tools, grid planning, ...) and
# vice versa - Object Creation's own GPT Image reference render + vision
# analysis pipeline is expensive enough to deserve its own, tighter cap.
# Uses the same sylvex_request_limits table as check_quota() above - a
# real Postgres row shared across every worker/replica, not an in-process
# counter - keyed by the caller's canonical SYLVEX identity (never IP
# alone), resolved by _resolve_canonical_identity() below.
OBJECT_CREATION_BUCKET='object_creation'


def _resolve_canonical_identity(cur, telegram_id):
 """Maps the business-data id the caller presents (a real Telegram id, or
 - for a website-embedded session, see services.security's
 resolve_web_session_uid()/the SecurityMiddleware telegram_id rewrite - the
 account's current sylvex_accounts.active_telegram_id storage key) to the
 actual sylvex_accounts.account_id ("SYLVEX ID") that is the one stable
 identity shared by every login method (Telegram, email/password, Google,
 Apple) ever linked to that account. Using account_id rather than the
 telegram_id/active_telegram_id proxy matters across a Telegram merge
 (services.account_identity._do_merge): active_telegram_id is repointed
 from the website's hidden storage id to the real Telegram id at that
 moment, so a quota keyed on it directly would silently start a fresh
 bucket post-merge; resolving to account_id first keeps one continuous
 bucket across the merge instead.

 A plain Telegram-only user who never registered/linked a website account
 has no sylvex_accounts row at all - there is no separate "account" to
 resolve to, so telegram_id itself already is the canonical identity and
 is returned unchanged. Same fallback if the sylvex_accounts table simply
 doesn't exist yet in this environment."""
 cur.execute("SELECT to_regclass('sylvex_accounts')")
 if cur.fetchone()[0] is None:
  return telegram_id
 cur.execute('SELECT account_id FROM sylvex_accounts WHERE active_telegram_id = %s', (telegram_id,))
 row = cur.fetchone()
 return int(row[0]) if row else telegram_id


def check_object_creation_quota(user_id):
 dsn=os.getenv('DATABASE_PUBLIC_URL') or os.getenv('DATABASE_URL')
 if not dsn:raise SecurityError('generation_queue_unavailable',503)
 try:
  ensure_limit_table(dsn)
  with db_connect(dsn) as conn:
   with conn.cursor() as cur:
    user_id=_resolve_canonical_identity(cur,user_id)
    for period,default in ((60,3),(86400,20)):
     limit=int(os.getenv(f'OBJECT_CREATION_REQUESTS_PER_{"MINUTE" if period==60 else "DAY"}',str(default)))
     window=int(time.time())//period
     cur.execute('''INSERT INTO sylvex_request_limits(user_id,bucket,window_start,hits) VALUES(%s,%s,%s,1)
      ON CONFLICT(user_id,bucket) DO UPDATE SET window_start=EXCLUDED.window_start,
      hits=CASE WHEN sylvex_request_limits.window_start=EXCLUDED.window_start THEN sylvex_request_limits.hits+1 ELSE 1 END
      RETURNING hits''',(user_id,f'{OBJECT_CREATION_BUCKET}:{period}',window))
     if cur.fetchone()[0]>limit:raise SecurityError('object_creation_rate_limited',429)
   conn.commit()
 except SecurityError:raise
 except Exception:raise SecurityError('usage_limit_unavailable',503)

async def check_object_creation_request_quota(user_id):
 await asyncio.to_thread(check_object_creation_quota,user_id)
