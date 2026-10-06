"""Fail closed on incomplete production configuration, without logging secrets."""
import os
import logging
import sys

def is_production():
 return os.getenv('APP_ENV','').lower()=='production' or bool(os.getenv('RAILWAY_ENVIRONMENT_ID'))

def parse_website_origins(raw=None):
 """Single source of truth for the WEBSITE_ORIGINS trusted-origin
 allowlist - services.security.website_origins() (which the CSRF guard's
 origin_allowed() reads) and main.py's CORSMiddleware registration both
 call this (the latter via services.security.website_origins()), so CORS
 and the CSRF guard can never drift onto two differently-normalized
 lists. Lives here rather than in services.security itself only because
 services.security already imports is_production() from this module, and
 this function is needed by validate_runtime() below too - putting it in
 services.security would make this module import back from it (a cycle).
 Normalizes whitespace and a trailing slash (an origin a browser sends in
 an Origin header never has one, so a lingering trailing slash in config
 would otherwise make an intended-to-match origin silently never match),
 drops empty entries, and - independent of, and in addition to,
 validate_runtime()'s own hard startup check below - unconditionally
 drops any entry that is or contains a literal '*': Starlette's
 CORSMiddleware treats a literal '*' allow_origins entry as a sentinel
 that reflects ANY request's Origin back with credentials allowed
 (CORS-2), and a '*' can never be a real browser-sent Origin value
 anyway, so dropping it here can only ever narrow the allowlist, never
 widen it - this keeps every caller of the parsed list safe even outside
 validate_runtime()'s production-only startup gate (tests, local dev)."""
 if raw is None:
  raw = os.getenv('WEBSITE_ORIGINS', '')
 origins = []
 for entry in raw.split(','):
  value = entry.strip().rstrip('/')
  if not value or '*' in value or value in origins:
   continue
  origins.append(value)
 return origins

def website_origins_configuration_error(raw=None):
 """Returns a human-readable reason WEBSITE_ORIGINS is unsafe to run with
 in production, or '' if it's fine. Separate from parse_website_origins()
 above (which silently drops a bad entry so every ordinary caller stays
 safe) because a production deploy must refuse to START on a wildcard
 rather than silently continuing with a narrowed - and possibly fully
 empty, guard-disabling - allowlist: an operator who configured
 WEBSITE_ORIGINS=* almost certainly meant to allow the real website, not
 to accidentally disable the CSRF guard, and deserves a startup failure
 that says so rather than a website that silently stops working."""
 if raw is None:
  raw = os.getenv('WEBSITE_ORIGINS', '')
 wildcard = [entry.strip() for entry in raw.split(',') if entry.strip() and '*' in entry]
 if wildcard:
  return ("WEBSITE_ORIGINS must not contain a wildcard origin (" + ', '.join(wildcard) + ") - "
          "a literal '*' makes Starlette's CORSMiddleware reflect ANY request's Origin back "
          "with credentials allowed (CORS-2). List the exact trusted website origin(s) instead.")
 return ''

def validate_runtime():
 if sys.version_info<(3,12):raise RuntimeError('Python 3.12 or newer is required; use the project runtime.')
 if not is_production():return
 required=['R2_BUCKET','R2_ENDPOINT','R2_ACCESS_KEY_ID','R2_SECRET_ACCESS_KEY']
 missing=[name for name in required if not os.getenv(name,'').strip()]
 if not (os.getenv('DATABASE_PUBLIC_URL') or os.getenv('DATABASE_URL')):missing.append('DATABASE_URL')
 if not (os.getenv('BOT_TOKEN') or os.getenv('TELEGRAM_BOT_TOKEN')):missing.append('BOT_TOKEN')
 if missing:raise RuntimeError('Missing required production configuration: '+', '.join(missing))
 if os.getenv('ENABLE_DEV_PAYMENTS','0')=='1' or os.getenv('PROSTUDIO_MOCK_GENERATION','0').lower() in {'1','true','yes','on'}:
  raise RuntimeError('Developer payments and mock generation must be disabled in production')
 if not os.getenv('WEBSITE_ORIGINS','').strip():
  # The /api/web/* account/session routes and the website-session cookie
  # fallback (see services/security.py) are always reachable regardless of
  # whether CORS is configured - CORS only stops an attacker's JS from
  # reading the response, never from sending the state-changing request in
  # the first place. WEBSITE_ORIGINS is the only source of trusted origins
  # services.security.origin_allowed() has to check a request's Origin/
  # Referer against; leaving it unset would mean either silently disabling
  # that CSRF guard (never acceptable) or, as implemented, the guard
  # failing closed and rejecting every one of those routes outright. Refuse
  # to start rather than deploy either outcome unnoticed.
  raise RuntimeError('WEBSITE_ORIGINS must be set in production: it is the trusted-origin allowlist the CSRF guard on /api/web/* and the website-session cookie fallback checks against (see services/security.py origin_allowed) - without it the guard fails closed and those routes stop working.')
 origins_error=website_origins_configuration_error()
 if origins_error:raise RuntimeError(origins_error)
 from urllib.parse import urlsplit
 for name in ('WEBAPP_URL','R2_ENDPOINT'):
  parsed=urlsplit(os.getenv(name,''))
  if parsed.scheme!='https' or not parsed.hostname:raise RuntimeError(name+' must be an HTTPS URL in production')
 for name in ('PROVIDER_REQUESTS_PER_MINUTE','PROVIDER_REQUESTS_PER_DAY','UPLOAD_REQUESTS_PER_MINUTE','UPLOAD_REQUESTS_PER_DAY','OBJECT_CREATION_REQUESTS_PER_MINUTE','OBJECT_CREATION_REQUESTS_PER_DAY'):
  if name in os.environ and int(os.environ[name])<=0:raise RuntimeError(name+' must be positive')

 if not os.getenv('TELEGRAM_PAYMENT_WEBHOOK_SECRET', '').strip():
  logging.getLogger(__name__).warning('Telegram payment webhook is disabled: TELEGRAM_PAYMENT_WEBHOOK_SECRET is not configured. Other application features remain available.')
