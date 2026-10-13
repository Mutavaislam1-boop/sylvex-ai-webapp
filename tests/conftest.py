"""Tests never load the project's real .env or start its background consumers."""
import os
os.environ['PYTHON_DOTENV_DISABLED']='1'
os.environ['PROSTUDIO_WORKER_ENABLED']='0'
os.environ['SUBSCRIPTION_REMINDER_WORKER_ENABLED']='0'
os.environ['APP_ENV']='test'
# Explicit test DB has its own variable and is never the application database.
for name in ('DATABASE_URL','DATABASE_PUBLIC_URL','BOT_TOKEN','TELEGRAM_BOT_TOKEN','R2_BUCKET','R2_ENDPOINT','R2_ACCESS_KEY_ID','R2_SECRET_ACCESS_KEY','R2_PUBLIC_BASE_URL','RAILWAY_ENVIRONMENT_ID'):
 os.environ.pop(name,None)


import pytest


def pytest_configure(config):
    config.addinivalue_line("markers", "unbilled: run without the default billing scope (billing-guard tests)")


@pytest.fixture(autouse=True)
def _billed_job_scope(request):
    """Adapter/unit tests run as if inside a billed job; provider dispatch
    outside any billing scope is refused by design (services.billing_safety).
    Tests of that guard itself opt out with @pytest.mark.unbilled."""
    if request.node.get_closest_marker("unbilled"):
        yield
        return
    from services.billing_safety import billing_scope
    with billing_scope("test-billed-job", 1):
        yield


@pytest.fixture(autouse=True)
def _fresh_account_schema_cache():
    """Each real-SQL test gets its own empty database; the account schema's
    process-wide "already ensured" flag must not leak between them (admin
    setup now ensures the account tables first)."""
    from services import account_identity
    account_identity._ACCOUNT_TABLES_READY = False
    yield
    account_identity._ACCOUNT_TABLES_READY = False
