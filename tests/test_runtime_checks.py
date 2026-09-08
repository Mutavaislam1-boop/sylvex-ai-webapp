import importlib.util
import logging
from pathlib import Path
import pytest

@pytest.fixture
def runtime(monkeypatch):
    path = Path(__file__).resolve().parents[1] / 'services/runtime_checks.py'
    spec = importlib.util.spec_from_file_location('startup_runtime_under_test', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    values = {'APP_ENV':'production','R2_BUCKET':'test','R2_ENDPOINT':'https://storage.example.com','R2_ACCESS_KEY_ID':'test','R2_SECRET_ACCESS_KEY':'test','DATABASE_URL':'postgresql://test','BOT_TOKEN':'test','WEBAPP_URL':'https://app.example.com','ENABLE_DEV_PAYMENTS':'0','PROSTUDIO_MOCK_GENERATION':'0'}
    for key,value in values.items(): monkeypatch.setenv(key,value)
    monkeypatch.delenv('TELEGRAM_PAYMENT_WEBHOOK_SECRET',raising=False)
    return module

def test_missing_webhook_secret_warns_without_blocking_startup(runtime,caplog):
    with caplog.at_level(logging.WARNING): runtime.validate_runtime()
    assert 'Telegram payment webhook is disabled' in caplog.text

def test_configured_webhook_has_no_disabled_warning(runtime,monkeypatch,caplog):
    monkeypatch.setenv('TELEGRAM_PAYMENT_WEBHOOK_SECRET','test-secret')
    runtime.validate_runtime()
    assert 'webhook is disabled' not in caplog.text

def test_required_storage_still_blocks_startup(runtime,monkeypatch):
    monkeypatch.delenv('R2_BUCKET')
    with pytest.raises(RuntimeError,match='R2_BUCKET'): runtime.validate_runtime()

def test_developer_payments_still_blocked(runtime,monkeypatch):
    monkeypatch.setenv('ENABLE_DEV_PAYMENTS','1')
    with pytest.raises(RuntimeError,match='Developer payments'): runtime.validate_runtime()
