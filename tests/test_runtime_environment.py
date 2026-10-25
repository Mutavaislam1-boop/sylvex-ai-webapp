"""SX-001 subprocess imports: no dotenv fallback, no real network/credentials."""
import os
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]


def run(code, *, with_file=False, extra=None):
    env = {"PATH": os.defpath, "PYTHONPATH": str(ROOT), "PYTHONDONTWRITEBYTECODE": "1",
           "APP_ENV": "test", "PROSTUDIO_WORKER_ENABLED": "0",
           "SUBSCRIPTION_REMINDER_WORKER_ENABLED": "0"}
    env.update(extra or {})
    trap = ROOT / ".env"
    assert not trap.exists(), "Run this test only in a checkout without a real env file"
    try:
        if with_file:
            trap.write_text("BOT_TOKEN=dummy-file-token\nDATABASE_URL=dummy-file-db\n"
                            "R2_BUCKET=dummy-file-bucket\nSX001_TRAP=dummy-marker\n")
        result = subprocess.run([sys.executable, "-c", """
import socket, dotenv, dotenv.main
def forbidden_dotenv(*args, **kwargs):
    raise AssertionError('implicit dotenv load attempted')
dotenv.load_dotenv = dotenv.main.load_dotenv = forbidden_dotenv
def forbidden_network(*args, **kwargs):
    raise AssertionError('network forbidden in bootstrap test')
socket.socket.connect = socket.socket.connect_ex = forbidden_network
""" + code], cwd=ROOT, env=env, capture_output=True, text=True, timeout=60)
        assert result.returncode == 0, result.stdout + result.stderr
        assert "dummy-marker" not in result.stdout + result.stderr
    finally:
        if with_file:
            trap.unlink(missing_ok=True)


@pytest.mark.parametrize("module", ["main", "worker", "services.storage"])
@pytest.mark.parametrize("with_file", [False, True])
def test_runtime_imports_do_not_load_dotenv(module, with_file):
    run(f"import importlib, os; importlib.import_module({module!r}); "
        "assert 'SX001_TRAP' not in os.environ; assert not os.getenv('BOT_TOKEN'); "
        "assert not os.getenv('DATABASE_URL')", with_file=with_file)


def test_storage_keeps_process_environment_and_database_priority():
    run("""
from services import storage
assert storage.DATABASE_URL == 'dummy-private-url'
assert storage.R2_BUCKET == 'dummy-runtime-bucket'
assert storage.R2_ACCESS_KEY_ID == 'dummy-access-key'
""", with_file=True, extra={"DATABASE_URL": "dummy-private-url",
                           "DATABASE_PUBLIC_URL": "dummy-public-url",
                           "R2_BUCKET": "dummy-runtime-bucket",
                           "R2_ACCESS_KEY_ID": "dummy-access-key"})


@pytest.mark.parametrize("values,missing", [({}, "DATABASE_URL"),
                                          ({"DATABASE_URL": "dummy-db"}, "BOT_TOKEN")])
def test_standalone_worker_missing_config_fails_before_connection(values, missing):
    run(f"""
import asyncio, worker
try:
    asyncio.run(worker.run_worker())
except RuntimeError as exc:
    assert {missing!r} in str(exc)
else:
    raise AssertionError('missing worker config must fail')
""", with_file=True, extra=values)
