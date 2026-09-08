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
 from urllib.parse import urlsplit
 for name in ('WEBAPP_URL','R2_ENDPOINT'):
  parsed=urlsplit(os.getenv(name,''))
  if parsed.scheme!='https' or not parsed.hostname:raise RuntimeError(name+' must be an HTTPS URL in production')
 for name in ('PROVIDER_REQUESTS_PER_MINUTE','PROVIDER_REQUESTS_PER_DAY','UPLOAD_REQUESTS_PER_MINUTE','UPLOAD_REQUESTS_PER_DAY'):
  if name in os.environ and int(os.environ[name])<=0:raise RuntimeError(name+' must be positive')

 if not os.getenv('TELEGRAM_PAYMENT_WEBHOOK_SECRET', '').strip():
  logging.getLogger(__name__).warning('Telegram payment webhook is disabled: TELEGRAM_PAYMENT_WEBHOOK_SECRET is not configured. Other application features remain available.')
