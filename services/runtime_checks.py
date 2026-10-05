"""Fail closed on incomplete production configuration, without logging secrets."""
import os
import logging
import sys

def is_production():
 return os.getenv('APP_ENV','').lower()=='production' or bool(os.getenv('RAILWAY_ENVIRONMENT_ID'))

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
 from urllib.parse import urlsplit
 for name in ('WEBAPP_URL','R2_ENDPOINT'):
  parsed=urlsplit(os.getenv(name,''))
  if parsed.scheme!='https' or not parsed.hostname:raise RuntimeError(name+' must be an HTTPS URL in production')
 for name in ('PROVIDER_REQUESTS_PER_MINUTE','PROVIDER_REQUESTS_PER_DAY','UPLOAD_REQUESTS_PER_MINUTE','UPLOAD_REQUESTS_PER_DAY'):
  if name in os.environ and int(os.environ[name])<=0:raise RuntimeError(name+' must be positive')

 if not os.getenv('TELEGRAM_PAYMENT_WEBHOOK_SECRET', '').strip():
  logging.getLogger(__name__).warning('Telegram payment webhook is disabled: TELEGRAM_PAYMENT_WEBHOOK_SECRET is not configured. Other application features remain available.')
