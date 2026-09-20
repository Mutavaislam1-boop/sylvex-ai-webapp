"""SYLVEX Assistant (Website AI Guide + AI Mode) tests.

Guide Mode intent routing is pure/local (services/assistant_intents.py) -
tested directly, no DB or mocks needed. Everything else exercises the real
/api/web/assistant/* route handlers against a real embedded Postgres
(pglite), same pattern as tests/test_paypal_website_payments.py. get_user_state
is monkeypatched per-test to control subscription state precisely (it's
pre-existing, unmodified code with its own extensive DB dependencies -
mocking it here keeps these tests focused on Assistant's own logic, exactly
like paypal_access_token is mocked in the PayPal tests). Outbound OpenAI
calls (services.assistant_openai.stream_assistant_reply/mint_realtime_session)
are always mocked - there is no real OpenAI to talk to in a test run, and a
Guide Mode test asserting "no OpenAI call occurs" needs the mock itself as
proof, not a live network boundary.
"""
import asyncio
import io
import json
import os
import time
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).parent / "support"))
sys.path.insert(0, str(Path(__file__).parent.parent))


def _pglite_available():
    return bool(os.getenv("SYLVEX_TEST_NODE") and os.getenv("SYLVEX_PGLITE_MODULE"))


pytestmark = pytest.mark.skipif(
    not _pglite_available(),
    reason="Set SYLVEX_TEST_NODE and SYLVEX_PGLITE_MODULE to run real-SQL tests",
)


class FakeRequest:
    def __init__(self, payload=None, cookies=None, state=None, raw_body=b""):
        self._payload = payload
        self.cookies = cookies or {}
        self.state = state if state is not None else SimpleNamespace()
        self._raw_body = raw_body or (json.dumps(payload).encode() if payload is not None else b"")
        self.query_params = {}

    async def json(self):
        return dict(self._payload or {})

    async def body(self):
        return self._raw_body


def _run(coro):
    return asyncio.run(coro)


def _unwrap(response):
    if isinstance(response, dict):
        return 200, response
    return response.status_code, json.loads(response.body)


async def _drain_stream(response):
    """Collects every SSE `data: {...}` event from a StreamingResponse
    returned by web_assistant_message's AI-mode branch, driving the real
    async generator (including its background-thread bridge) exactly as
    Starlette would."""
    events = []
    async for chunk in response.body_iterator:
        text = chunk.decode() if isinstance(chunk, (bytes, bytearray)) else chunk
        for line in text.split("\n\n"):
            line = line.strip()
            if line.startswith("data:"):
                events.append(json.loads(line[len("data:"):].strip()))
    return events


@pytest.fixture
def env(monkeypatch):
    import main
    from pglite_adapter import Database

    database = Database()
    monkeypatch.setattr(main, "db_connect", lambda *a, **k: database.connect())
    monkeypatch.setattr(main, "DATABASE_URL", "pglite://test")
    monkeypatch.setattr(main, "OPENAI_API_KEY", "test-openai-key")
    monkeypatch.setattr(main, "OPENAI_ASSISTANT_MODEL", "gpt-5.6")

    def _explode(*a, **k):
        raise AssertionError("stream_assistant_reply must never be called for a free/guest user")
    monkeypatch.setattr(main, "stream_assistant_reply", _explode)

    # services.request_limits.check_quota talks to a real DSN via its own
    # db_pool.db_connect import (independent of main.db_connect above) - out
    # of scope for these tests, which are about Assistant's own logic, not
    # re-verifying the pre-existing quota mechanism.
    async def _noop_quota(*a, **k):
        return None
    monkeypatch.setattr(main, "check_request_quota", _noop_quota)

    with database.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "CREATE TABLE users(telegram_id BIGINT PRIMARY KEY, first_name TEXT, "
                "username TEXT, balance INTEGER DEFAULT 0, subscription TEXT, created_at TEXT)"
            )
    yield main, database
    database.close()


def _authed_request(payload=None, telegram_id=900001, cookies=None):
    return FakeRequest(payload=payload, state=SimpleNamespace(telegram_id=telegram_id), cookies=cookies or {})


def _set_subscriber(main, monkeypatch, active):
    monkeypatch.setattr(
        main, "get_user_state",
        lambda telegram_id: {
            "subscription_status": "active" if active else "free",
            "subscription_plan": "sub_month" if active else None,
            "balance": 250,
        },
    )


# ---------------------------------------------------------------------------
# Guide Mode intent routing - pure, local, no DB/network
# ---------------------------------------------------------------------------

def test_welcome_response_has_no_openai_dependency():
    from services.assistant_intents import WELCOME
    assert "SYLVEX" in WELCOME["text"]
    assert len(WELCOME["actions"]) >= 3


@pytest.mark.parametrize("message,expected", [
    ("Hello", "GREETING"),
    ("hi there", "GREETING"),
    ("create a video of a sunset", "VIDEO"),
    ("generate an image of a cat", "IMAGE"),
    ("add a voiceover to my video", "VOICE"),
    ("how much does video cost?", "PRICING"),
    ("I want to upgrade to sylvex pro", "SUBSCRIPTION"),
    ("asdkjhaslkdj nonsense gibberish", "FALLBACK"),
])
def test_intent_routing_matches_expected_primary(message, expected):
    from services.assistant_intents import route_intent
    result = route_intent(message)
    assert result["primary"]["id"] == expected


def test_multi_topic_routing_surfaces_secondary_action():
    from services.assistant_intents import route_intent
    result = route_intent("How can I animate a photo and then add a voice?")
    assert result["primary"]["id"] == "IMAGE_TO_VIDEO"
    secondary_ids = [i["id"] for i in result["secondary"]]
    assert "VOICE" in secondary_ids


def test_pricing_beats_generic_video_collision():
    from services.assistant_intents import route_intent
    assert route_intent("How much does video cost?")["primary"]["id"] == "PRICING"


def test_credits_beats_generic_account_collision():
    from services.assistant_intents import route_intent
    assert route_intent("How do I buy credits?")["primary"]["id"] == "CREDITS"


# ---------------------------------------------------------------------------
# GET /api/web/assistant/state
# ---------------------------------------------------------------------------

def test_state_guest_reports_guide_mode(env):
    main, _ = env
    request = FakeRequest(cookies={})
    result = _run(main.web_assistant_state(request))
    assert result["authenticated"] is False
    assert result["mode"] == "guide"


def test_state_free_user_reports_guide_mode(env, monkeypatch):
    main, _ = env
    monkeypatch.setattr(main, "_web_session_account_id", lambda request: 42)
    monkeypatch.setattr(main, "resolve_web_session_uid", lambda account_id: 900002)
    _set_subscriber(main, monkeypatch, active=False)
    result = _run(main.web_assistant_state(FakeRequest()))
    assert result["authenticated"] is True
    assert result["mode"] == "guide"
    assert result["subscription_status"] == "free"


def test_state_subscriber_reports_ai_mode(env, monkeypatch):
    main, _ = env
    monkeypatch.setattr(main, "_web_session_account_id", lambda request: 42)
    monkeypatch.setattr(main, "resolve_web_session_uid", lambda account_id: 900003)
    _set_subscriber(main, monkeypatch, active=True)
    result = _run(main.web_assistant_state(FakeRequest()))
    assert result["mode"] == "ai"
    assert result["subscription_status"] == "active"


# ---------------------------------------------------------------------------
# Conversation CRUD + ownership
# ---------------------------------------------------------------------------

def test_create_list_get_conversation(env):
    main, _ = env
    telegram_id = 900010
    _, created = _unwrap(_run(main.web_assistant_create_conversation(_authed_request({"title": "My idea"}, telegram_id))))
    conversation_id = created["conversation"]["id"]
    assert created["conversation"]["title"] == "My idea"

    _, listed = _unwrap(_run(main.web_assistant_list_conversations(_authed_request(telegram_id=telegram_id))))
    assert any(c["id"] == conversation_id for c in listed["conversations"])

    _, fetched = _unwrap(_run(main.web_assistant_get_conversation(conversation_id, _authed_request(telegram_id=telegram_id))))
    assert fetched["conversation"]["id"] == conversation_id
    assert fetched["conversation"]["messages"] == []


def test_rename_and_pin_conversation(env):
    main, _ = env
    telegram_id = 900011
    _, created = _unwrap(_run(main.web_assistant_create_conversation(_authed_request({}, telegram_id))))
    conversation_id = created["conversation"]["id"]

    status, _ = _unwrap(_run(main.web_assistant_update_conversation(
        conversation_id, _authed_request({"title": "Renamed", "pinned": True}, telegram_id),
    )))
    assert status == 200

    _, fetched = _unwrap(_run(main.web_assistant_get_conversation(conversation_id, _authed_request(telegram_id=telegram_id))))
    assert fetched["conversation"]["title"] == "Renamed"
    assert fetched["conversation"]["pinned"] is True


def test_delete_conversation(env):
    main, _ = env
    telegram_id = 900012
    _, created = _unwrap(_run(main.web_assistant_create_conversation(_authed_request({}, telegram_id))))
    conversation_id = created["conversation"]["id"]

    status, _ = _unwrap(_run(main.web_assistant_delete_conversation(conversation_id, _authed_request(telegram_id=telegram_id))))
    assert status == 200

    import fastapi
    with pytest.raises(fastapi.HTTPException) as exc_info:
        _run(main.web_assistant_get_conversation(conversation_id, _authed_request(telegram_id=telegram_id)))
    assert exc_info.value.status_code == 404


def test_unauthorized_conversation_access_rejected(env):
    main, _ = env
    owner_id, attacker_id = 900013, 900014
    _, created = _unwrap(_run(main.web_assistant_create_conversation(_authed_request({}, owner_id))))
    conversation_id = created["conversation"]["id"]

    import fastapi
    with pytest.raises(fastapi.HTTPException) as exc_info:
        _run(main.web_assistant_get_conversation(conversation_id, _authed_request(telegram_id=attacker_id)))
    assert exc_info.value.status_code == 404

    with pytest.raises(fastapi.HTTPException) as exc_info:
        _run(main.web_assistant_delete_conversation(conversation_id, _authed_request(telegram_id=attacker_id)))
    assert exc_info.value.status_code == 404


# ---------------------------------------------------------------------------
# POST /api/web/assistant/message - Guide Mode (free/guest, never OpenAI)
# ---------------------------------------------------------------------------

def test_guide_message_for_guest_never_persists_and_never_calls_openai(env, monkeypatch):
    main, _ = env
    monkeypatch.setattr(main, "_web_session_account_id", lambda request: None)
    result = _run(main.web_assistant_message(FakeRequest(payload={"content": "create a video"})))
    assert result["ok"] is True
    assert result["mode"] == "guide"
    assert result["message"]["intent"] == "VIDEO"
    # stream_assistant_reply is monkeypatched to raise if ever called (env fixture) - reaching
    # this assertion at all is itself proof no OpenAI call was attempted.


def test_guide_message_for_authenticated_free_user_persists(env, monkeypatch):
    main, _ = env
    monkeypatch.setattr(main, "_web_session_account_id", lambda request: 42)
    monkeypatch.setattr(main, "resolve_web_session_uid", lambda account_id: 900020)
    _set_subscriber(main, monkeypatch, active=False)

    result = _run(main.web_assistant_message(FakeRequest(payload={"content": "how much does it cost?"})))
    assert result["mode"] == "guide"
    conversation_id = result["conversation_id"]
    assert result["message"]["intent"] == "PRICING"

    _, fetched = _unwrap(_run(main.web_assistant_get_conversation(conversation_id, _authed_request(telegram_id=900020))))
    roles = [m["role"] for m in fetched["conversation"]["messages"]]
    assert roles == ["user", "assistant"]


def test_guide_message_idempotent_retry_does_not_duplicate(env, monkeypatch):
    main, _ = env
    monkeypatch.setattr(main, "_web_session_account_id", lambda request: 42)
    monkeypatch.setattr(main, "resolve_web_session_uid", lambda account_id: 900021)
    _set_subscriber(main, monkeypatch, active=False)

    payload = {"content": "hello", "client_request_id": "req-abc-1"}
    first = _run(main.web_assistant_message(FakeRequest(payload=payload)))
    conversation_id = first["conversation_id"]
    payload["conversation_id"] = conversation_id
    second = _run(main.web_assistant_message(FakeRequest(payload=payload)))
    assert second.get("replay") is True
    assert second["message"]["id"] == first["message"]["id"]

    _, fetched = _unwrap(_run(main.web_assistant_get_conversation(conversation_id, _authed_request(telegram_id=900021))))
    assert len(fetched["conversation"]["messages"]) == 2  # one user + one assistant, not four


def test_free_user_attachment_never_reaches_openai(env, monkeypatch):
    main, _ = env
    monkeypatch.setattr(main, "_web_session_account_id", lambda request: 42)
    monkeypatch.setattr(main, "resolve_web_session_uid", lambda account_id: 900022)
    _set_subscriber(main, monkeypatch, active=False)

    result = _run(main.web_assistant_message(FakeRequest(payload={
        "content": "what do you think of this?",
        "attachment": {"url": "https://example.com/a.png", "mime": "image/png", "name": "a.png"},
    })))
    assert result["message"]["intent"] == "FILES"
    assert any(a["type"] == "open_subscription_modal" for a in result["message"]["actions"])


# ---------------------------------------------------------------------------
# POST /api/web/assistant/message - AI Mode (subscriber, streaming)
# ---------------------------------------------------------------------------

def test_ai_message_streams_and_persists(env, monkeypatch):
    main, _ = env
    monkeypatch.setattr(main, "_web_session_account_id", lambda request: 42)
    monkeypatch.setattr(main, "resolve_web_session_uid", lambda account_id: 900030)
    _set_subscriber(main, monkeypatch, active=True)

    def fake_stream(api_key, api_base, model, messages):
        assert api_key == "test-openai-key"
        yield "Here is an idea: "
        yield "[PROMPT]a cozy coffee shop, warm light[/PROMPT]"
    monkeypatch.setattr(main, "stream_assistant_reply", fake_stream)

    response = _run(main.web_assistant_message(FakeRequest(payload={"content": "pitch me an ad idea"})))
    events = _run(_drain_stream(response))

    assert events[0]["type"] == "start"
    conversation_id = events[0]["conversation_id"]
    deltas = "".join(e["text"] for e in events if e["type"] == "delta")
    assert deltas == "Here is an idea: [PROMPT]a cozy coffee shop, warm light[/PROMPT]"
    done = next(e for e in events if e["type"] == "done")
    assert done["prompt"] == "a cozy coffee shop, warm light"

    _, fetched = _unwrap(_run(main.web_assistant_get_conversation(conversation_id, _authed_request(telegram_id=900030))))
    assistant_msg = fetched["conversation"]["messages"][-1]
    assert assistant_msg["role"] == "assistant"
    assert assistant_msg["mode"] == "ai"
    assert assistant_msg["status"] == "completed"
    assert any(a["type"] == "use_prompt" for a in assistant_msg["actions"])


def test_ai_message_cancellation_via_stop(env, monkeypatch):
    main, _ = env
    monkeypatch.setattr(main, "_web_session_account_id", lambda request: 42)
    monkeypatch.setattr(main, "resolve_web_session_uid", lambda account_id: 900031)
    _set_subscriber(main, monkeypatch, active=True)

    def fake_stream(api_key, api_base, model, messages):
        yield "first chunk"
        # A brief pause models real network latency between provider chunks
        # and gives the test's own coroutine below a window to call the
        # real /stop endpoint mid-stream, exactly as a client would.
        time.sleep(0.2)
        yield "second chunk"
        yield "third chunk"
    monkeypatch.setattr(main, "stream_assistant_reply", fake_stream)

    async def run_and_capture():
        response = await main.web_assistant_message(FakeRequest(payload={"content": "long task"}))
        events = []
        stop_requested = False
        async for chunk in response.body_iterator:
            text = chunk.decode() if isinstance(chunk, (bytes, bytearray)) else chunk
            for line in text.split("\n\n"):
                line = line.strip()
                if not line.startswith("data:"):
                    continue
                event = json.loads(line[len("data:"):].strip())
                events.append(event)
                if event["type"] == "start" and not stop_requested:
                    stop_requested = True
                    stop_status, stop_body = _unwrap(await main.web_assistant_stop(
                        FakeRequest(payload={"stream_id": event["stream_id"]})
                    ))
                    assert stop_status == 200 and stop_body["stopped"] is True
        return events

    events = _run(run_and_capture())
    assert any(e["type"] == "cancelled" for e in events)
    assert not any(e["type"] == "done" for e in events)


def test_stop_unknown_stream_id_reports_not_found(env):
    main, _ = env
    status, body = _unwrap(_run(main.web_assistant_stop(FakeRequest(payload={"stream_id": "does-not-exist"}))))
    assert status == 200
    assert body["stopped"] is False


# ---------------------------------------------------------------------------
# POST /api/web/assistant/files - subscription enforcement
# ---------------------------------------------------------------------------

def test_free_user_file_upload_rejected_without_reaching_storage(env, monkeypatch):
    main, _ = env
    _set_subscriber(main, monkeypatch, active=False)

    def _explode(*a, **k):
        raise AssertionError("storage_put_bytes must never be called for a non-subscriber")
    monkeypatch.setattr(main, "storage_put_bytes", _explode)

    class FakeUploadFile:
        filename = "photo.png"
        content_type = "image/png"
        async def read(self, n):
            return b""

    status, body = _unwrap(_run(main.web_assistant_upload_file(_authed_request(telegram_id=900040), FakeUploadFile())))
    assert status == 403
    assert body["error"] == "subscription_required"


def test_subscriber_file_upload_succeeds(env, monkeypatch):
    main, _ = env
    _set_subscriber(main, monkeypatch, active=True)
    monkeypatch.setattr(main, "storage_put_bytes", lambda content, key, content_type: "https://cdn.example.com/" + key)

    from PIL import Image
    buffer = io.BytesIO()
    Image.new("RGB", (4, 4), color=(10, 20, 30)).save(buffer, format="PNG")
    png_bytes = buffer.getvalue()
    chunks = [png_bytes, b""]

    class FakeUploadFile:
        filename = "photo.png"
        content_type = "image/png"
        async def read(self, n):
            return chunks.pop(0)

    status, body = _unwrap(_run(main.web_assistant_upload_file(_authed_request(telegram_id=900041), FakeUploadFile())))
    assert status == 200
    assert body["file"]["kind"] == "image"
    assert body["file"]["url"].startswith("https://cdn.example.com/")


def test_unsupported_file_type_rejected(env, monkeypatch):
    main, _ = env
    _set_subscriber(main, monkeypatch, active=True)

    class FakeUploadFile:
        filename = "malware.exe"
        content_type = "application/octet-stream"
        async def read(self, n):
            return b""

    status, body = _unwrap(_run(main.web_assistant_upload_file(_authed_request(telegram_id=900042), FakeUploadFile())))
    assert status == 400
    assert body["error"] == "unsupported_file_type"


def test_oversized_file_rejected(env, monkeypatch):
    main, _ = env
    _set_subscriber(main, monkeypatch, active=True)

    big_chunk = b"a" * (21 * 1024 * 1024)
    chunks = [big_chunk, b""]

    class FakeUploadFile:
        filename = "notes.txt"
        content_type = "text/plain"
        async def read(self, n):
            return chunks.pop(0) if chunks else b""

    # read_upload() enforces the size cap itself, mid-stream, by raising
    # SecurityError directly (security_error_handler converts that to a
    # JSON 413 response in real request handling; calling the route
    # function directly here bypasses that ASGI-level conversion).
    with pytest.raises(main.SecurityError) as exc_info:
        _run(main.web_assistant_upload_file(_authed_request(telegram_id=900043), FakeUploadFile()))
    assert exc_info.value.status == 413
    assert exc_info.value.code == "file_too_large"


# ---------------------------------------------------------------------------
# POST /api/web/assistant/realtime/session - subscription enforcement, no key leak
# ---------------------------------------------------------------------------

def test_realtime_session_requires_login(env):
    main, _ = env
    request = FakeRequest(payload=None, state=SimpleNamespace(telegram_id=0), raw_body=b"v=0\r\n")
    status, body = _unwrap(_run(main.web_assistant_realtime_session(request)))
    assert status == 401
    assert body["error"] == "login_required"


def test_realtime_session_requires_subscription(env, monkeypatch):
    main, _ = env
    _set_subscriber(main, monkeypatch, active=False)
    request = FakeRequest(payload=None, state=SimpleNamespace(telegram_id=900050), raw_body=b"v=0\r\n")
    status, body = _unwrap(_run(main.web_assistant_realtime_session(request)))
    assert status == 403
    assert body["error"] == "subscription_required"


def test_realtime_session_mints_session_and_never_exposes_key(env, monkeypatch):
    main, _ = env
    _set_subscriber(main, monkeypatch, active=True)

    captured = {}
    def fake_mint(api_key, sdp, instructions, uid, model):
        captured["api_key"] = api_key
        captured["sdp"] = sdp
        return b"v=0\r\n(answer sdp)", 200, "application/sdp"
    monkeypatch.setattr(main, "mint_realtime_session", fake_mint)

    request = FakeRequest(payload=None, state=SimpleNamespace(telegram_id=900051), raw_body=b"v=0\r\n(offer sdp)")
    response = _run(main.web_assistant_realtime_session(request))
    assert response.status_code == 200
    assert captured["api_key"] == "test-openai-key"
    assert b"test-openai-key" not in response.body
