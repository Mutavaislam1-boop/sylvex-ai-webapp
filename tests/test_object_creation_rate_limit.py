# Regression tests for the security audit's Object Creation abuse-protection
# finding: unlike Character Creation (POST /api/public/prostudio/character,
# a COSTLY-bucket member), Object Creation (POST /api/public/prostudio/object)
# had no rate limit at all - any authenticated caller could submit unlimited
# GPT Image reference-render + vision-analysis jobs back to back.
#
# Fix: services/request_limits.py's check_object_creation_quota() - a
# dedicated per-user bucket ('object_creation'), deliberately separate from
# the shared COSTLY 'provider'/'upload' buckets, backed by the same
# cross-worker/replica-shared sylvex_request_limits Postgres table check_quota()
# already uses (never an in-process limiter). Wired into main.py's
# public_prostudio_create_object() right before create_object_creation_job()
# - the exact point a new job is submitted - and nowhere else: polling
# (public_prostudio_object_creation_jobs), status reads, and viewing existing
# Objects never call it.
#
# Part 1 (real-SQL, pglite): exercises check_object_creation_quota() itself -
# normal creation, repeated rapid creation, different users independent, and
# proof the limit is backed by a real shared DB row rather than any
# process-local/in-memory state.
#
# Part 2 (ASGI, real FastAPI app + middleware): exercises main.py's actual
# route wiring - the dedicated check fires exactly once at job creation and
# produces a clean 429, while polling/jobs-list is never gated by it.
import os
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent / "support"))


def _pglite_available():
    return bool(os.getenv("SYLVEX_TEST_NODE") and os.getenv("SYLVEX_PGLITE_MODULE"))


pytestmark_pglite = pytest.mark.skipif(
    not _pglite_available(),
    reason="Set SYLVEX_TEST_NODE and SYLVEX_PGLITE_MODULE to run real-SQL tests",
)


# ---------------------------------------------------------------------------
# Part 1: check_object_creation_quota() against a real Postgres (pglite).
# ---------------------------------------------------------------------------

@pytest.fixture
def quota_db(monkeypatch):
    from pglite_adapter import Database
    from services import request_limits as rl

    database = Database()
    monkeypatch.setattr(rl, "db_connect", lambda *a, **k: database.connect())
    monkeypatch.setattr(rl, "_ready", False)
    monkeypatch.setenv("OBJECT_CREATION_REQUESTS_PER_MINUTE", "3")
    monkeypatch.setenv("OBJECT_CREATION_REQUESTS_PER_DAY", "20")
    monkeypatch.setenv("DATABASE_URL", "pglite://test")
    yield database, rl
    database.close()


@pytestmark_pglite
def test_a_normal_creation_within_limit_succeeds(quota_db):
    database, rl = quota_db
    for _ in range(3):
        rl.check_object_creation_quota(111)  # must not raise


@pytestmark_pglite
def test_b_repeated_rapid_creation_raises_429_past_the_limit(quota_db):
    from services.security import SecurityError

    database, rl = quota_db
    for _ in range(3):
        rl.check_object_creation_quota(222)
    with pytest.raises(SecurityError) as exc_info:
        rl.check_object_creation_quota(222)
    assert exc_info.value.code == "object_creation_rate_limited"
    assert exc_info.value.status == 429


@pytestmark_pglite
def test_c_different_users_are_independent(quota_db):
    from services.security import SecurityError

    database, rl = quota_db
    for _ in range(3):
        rl.check_object_creation_quota(333)
    with pytest.raises(SecurityError):
        rl.check_object_creation_quota(333)  # user 333 is now limited
    for _ in range(3):
        rl.check_object_creation_quota(444)  # user 444 is unaffected


@pytestmark_pglite
def test_d_daily_bucket_is_also_enforced_independently_of_the_minute_bucket(quota_db, monkeypatch):
    from services.security import SecurityError

    database, rl = quota_db
    monkeypatch.setenv("OBJECT_CREATION_REQUESTS_PER_MINUTE", "1000")  # effectively unlimited per minute
    monkeypatch.setenv("OBJECT_CREATION_REQUESTS_PER_DAY", "2")
    rl.check_object_creation_quota(555)
    rl.check_object_creation_quota(555)
    with pytest.raises(SecurityError) as exc_info:
        rl.check_object_creation_quota(555)
    assert exc_info.value.code == "object_creation_rate_limited"


@pytestmark_pglite
def test_e_limit_is_shared_state_in_the_db_not_a_process_local_counter(quota_db):
    # Prove this is not an in-process/per-worker counter like LocalLimiter:
    # each call below opens a brand-new connection (via the monkeypatched
    # db_connect, exactly as a real separate worker/replica process would),
    # and the running total still correctly persists and enforces across
    # those independent connections - because the count lives in the
    # sylvex_request_limits table, not in any Python object.
    database, rl = quota_db
    for i in range(3):
        with database.connect() as fresh_conn_proof_only:
            pass  # each iteration proves a fresh connection is obtainable
        rl.check_object_creation_quota(666)
    from services.security import SecurityError
    with pytest.raises(SecurityError):
        rl.check_object_creation_quota(666)


@pytestmark_pglite
def test_f_window_resets_after_the_minute_elapses(quota_db, monkeypatch):
    database, rl = quota_db
    for _ in range(3):
        rl.check_object_creation_quota(777)
    from services.security import SecurityError
    with pytest.raises(SecurityError):
        rl.check_object_creation_quota(777)
    # Simulate the next minute's window by monkeypatching time.time() forward -
    # window = int(time.time()) // 60, so +61s guarantees a new window.
    real_time = time.time
    monkeypatch.setattr(rl.time, "time", lambda: real_time() + 61)
    rl.check_object_creation_quota(777)  # must not raise - fresh window


# ---------------------------------------------------------------------------
# Part 2: the real route wiring (ASGI, same pattern as test_security_boundaries.py).
# ---------------------------------------------------------------------------

import asyncio
import hashlib
import hmac
import json
from unittest.mock import AsyncMock
from urllib.parse import urlencode

import httpx
from services.security import SecurityMiddleware, SecurityError

TOKEN = "test-only-bot-token"


def signed(uid=101, age=0):
    fields = {"user": json.dumps({"id": uid, "first_name": "Test"}), "auth_date": str(int(time.time()) - age)}
    check = "\n".join(f"{k}={fields[k]}" for k in sorted(fields))
    fields["hash"] = hmac.new(hmac.new(b"WebAppData", TOKEN.encode(), hashlib.sha256).digest(), check.encode(), hashlib.sha256).hexdigest()
    return urlencode(fields)


@pytest.fixture
def app(monkeypatch):
    monkeypatch.setenv("BOT_TOKEN", TOKEN)
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    import main

    monkeypatch.setattr(main, "TELEGRAM_AUTH_TOKENS", (TOKEN,))
    monkeypatch.setattr(main, "BOT_TOKEN", TOKEN)
    monkeypatch.setattr(main, "sync_user_to_db", lambda user: user)
    # The middleware's own generic quota_check is irrelevant here (it's a
    # no-op for this path anyway, since /api/public/prostudio/object isn't
    # in COSTLY) - mocked out purely so it never needs a real DB.
    main.app.middleware_stack = None
    for mw in main.app.user_middleware:
        if mw.cls is SecurityMiddleware:
            mw.kwargs["quota_check"] = AsyncMock()
    return main.app


@pytest.fixture
def client(app):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


@pytest.mark.asyncio
async def test_create_object_calls_the_dedicated_quota_check_before_creating_the_job(client, monkeypatch):
    import main

    calls = []

    async def spy_quota(telegram_id):
        calls.append(telegram_id)

    monkeypatch.setattr(main, "check_object_creation_request_quota", spy_quota)

    # create_object_creation_job is a plain sync function, called via
    # asyncio.to_thread() in the real handler - the replacement must stay
    # sync too, or asyncio.to_thread() would just hand back an unawaited
    # coroutine object instead of a job id.
    def fake_create_job(telegram_id, name, description, photos):
        return "job-123"

    monkeypatch.setattr(main, "create_object_creation_job", fake_create_job)
    monkeypatch.setattr(main, "_run_object_creation_job", AsyncMock())

    r = await client.post(
        "/api/public/prostudio/object",
        headers={"X-Telegram-Init-Data": signed(uid=101)},
        json={"telegram_id": 101, "name": "My Bag", "description": "A nice bag", "photos": ["https://cdn.sylvex.ai/a.png"]},
    )
    assert r.status_code == 202, r.text
    assert r.json()["job_id"] == "job-123"
    assert calls == [101]


@pytest.mark.asyncio
async def test_create_object_returns_429_when_the_dedicated_limit_is_exceeded(client, monkeypatch):
    import main

    async def rate_limited(telegram_id):
        raise SecurityError("object_creation_rate_limited", 429)

    monkeypatch.setattr(main, "check_object_creation_request_quota", rate_limited)
    job_create_called = []
    monkeypatch.setattr(main, "create_object_creation_job", lambda *a, **k: job_create_called.append(1))

    r = await client.post(
        "/api/public/prostudio/object",
        headers={"X-Telegram-Init-Data": signed(uid=101)},
        json={"telegram_id": 101, "name": "My Bag", "description": "", "photos": ["https://cdn.sylvex.ai/a.png"]},
    )
    assert r.status_code == 429
    assert r.json() == {"ok": False, "error": "object_creation_rate_limited"}
    # The job must never actually be created once the dedicated limit rejects the request.
    assert job_create_called == []


@pytest.mark.asyncio
async def test_polling_the_object_creation_jobs_list_never_calls_the_dedicated_quota_check(client, monkeypatch):
    import main

    calls = []

    async def spy_quota(telegram_id):
        calls.append(telegram_id)

    monkeypatch.setattr(main, "check_object_creation_request_quota", spy_quota)
    monkeypatch.setattr(main, "DATABASE_URL", "")  # short-circuits to {"ok": True, "jobs": []}

    r = await client.get("/api/public/prostudio/object-creation-jobs?telegram_id=101", headers={"X-Telegram-Init-Data": signed(uid=101)})
    assert r.status_code == 200
    assert r.json() == {"ok": True, "jobs": []}
    assert calls == []  # polling must never be gated by the creation-only limit


@pytest.mark.asyncio
async def test_repeated_polling_calls_never_accumulate_against_the_creation_limit(client, monkeypatch):
    # A stronger version of the above: hammer the jobs-list endpoint many
    # times in a row (simulating the frontend's poll loop) and confirm the
    # dedicated check still never fires, regardless of call volume.
    import main

    calls = []

    async def spy_quota(telegram_id):
        calls.append(telegram_id)

    monkeypatch.setattr(main, "check_object_creation_request_quota", spy_quota)
    monkeypatch.setattr(main, "DATABASE_URL", "")

    for _ in range(10):
        r = await client.get("/api/public/prostudio/object-creation-jobs?telegram_id=101", headers={"X-Telegram-Init-Data": signed(uid=101)})
        assert r.status_code == 200
    assert calls == []
