"""Tests never load the project's real .env or start its background consumers."""
import os
os.environ['PYTHON_DOTENV_DISABLED']='1'
os.environ['PROSTUDIO_WORKER_ENABLED']='0'
os.environ['SUBSCRIPTION_REMINDER_WORKER_ENABLED']='0'
os.environ['APP_ENV']='test'
# Explicit test DB has its own variable and is never the application database.
for name in ('DATABASE_URL','DATABASE_PUBLIC_URL','BOT_TOKEN','TELEGRAM_BOT_TOKEN','R2_BUCKET','R2_ENDPOINT','R2_ACCESS_KEY_ID','R2_SECRET_ACCESS_KEY','R2_PUBLIC_BASE_URL','RAILWAY_ENVIRONMENT_ID'):
 os.environ.pop(name,None)
