"""Invariant: no billable provider dispatch without a SYLVEX price and a
billing transaction.

- Every low-level provider dispatcher refuses to run outside a billing scope.
- Queued jobs dispatch only with a known price and their own held
  reservation; internal retries/polling share that one scope and charge once.
- Priced helpers (Grid plan, idea routing, voice text tool, voice preview,
  Character/Object creation) reserve -> dispatch -> settle or refund, and are
  idempotent by client_request_id.
- Helpers with no SYLVEX tariff are blocked before any provider is called.

No network and no paid calls: providers are fakes. Ledger tests run against a
disposable PostgreSQL given by SYLVEX_TEST_DATABASE_URL (skipped otherwise).
"""
import asyncio
import inspect
import json
import os
from types import SimpleNamespace

import pytest

import main
import services.audio_router as audio_router
import services.assistant_openai as assistant_openai
import services.video_router as video_router
from services import billing_safety
from services.billing_safety import billing_scope, current_billing_scope
from services.security import SecurityError

DATABASE = os.getenv("SYLVEX_TEST_DATABASE_URL")


def _no_network(*args, **kwargs):
    raise AssertionError("a provider HTTP call was attempted")


@pytest.fixture(autouse=True)
def _block_network(monkeypatch):
    import httpx
    import requests
    monkeypatch.setattr(requests, "post", _no_network)
    monkeypatch.setattr(requests, "get", _no_network)
    monkeypatch.setattr(httpx, "post", _no_network)
    monkeypatch.setattr(httpx.AsyncClient, "post", _no_network)


# ------------------------------------------------------------ guard primitives

UNBILLED_DISPATCHES = {
    "text_generation": lambda: main.text_generation({"mode": "text", "model": "gpt-5.5", "prompt": "hi"}),
    "call_text_provider": lambda: main.call_text_provider("gpt-5.5", [{"role": "user", "content": "hi"}]),
    "openai_compatible_text_request": lambda: main.openai_compatible_text_request("openai", "https://x", "k", "m", []),
    "openai_responses_text_request": lambda: main.openai_responses_text_request("m", []),
    "gemini_text_request": lambda: main.gemini_text_request("m", []),
    "image_generation": lambda: asyncio.run(main.image_generation({"mode": "image", "model": "gpt_image_2", "prompt": "x"})),
    "video_generation": lambda: asyncio.run(video_router.video_generation({"model": "kling_3_0", "prompt": "x"})),
    "audio_generation": lambda: asyncio.run(audio_router.audio_generation({"mode": "music", "prompt": "x"})),
    "openai_transcribe_bytes": lambda: main.openai_transcribe_bytes(b"x", "a.wav", "audio/wav"),
    "gemini_transcribe_bytes": lambda: main.gemini_transcribe_bytes(b"x", "audio/wav"),
    "elevenlabs_clone_voice_from_audio": lambda: asyncio.run(audio_router.elevenlabs_clone_voice_from_audio(b"x")),
    "elevenlabs_voice_preview": lambda: asyncio.run(audio_router.elevenlabs_voice_preview({})),
    "runway_voice_preview": lambda: asyncio.run(audio_router.runway_voice_preview({})),
    "gemini_tts_voice_preview": lambda: asyncio.run(audio_router.gemini_tts_voice_preview({})),
    "stream_assistant_reply": lambda: next(assistant_openai.stream_assistant_reply("k", "https://x", "m", [])),
    "mint_realtime_session": lambda: assistant_openai.mint_realtime_session("k", "sdp", "i", "u", "m"),
    "dispatch_prostudio_provider_request": lambda: asyncio.run(main.dispatch_prostudio_provider_request("job", {}, "text", "m", "p", {"text"})),
    "_generate_openai_character_images": lambda: asyncio.run(main._generate_openai_character_images("job", "n", "g", "d", [])),
    "_generate_voice_avatar_once": lambda: main._generate_voice_avatar_once("elevenlabs", "voice"),
}


@pytest.mark.unbilled
@pytest.mark.parametrize("name", sorted(UNBILLED_DISPATCHES))
def test_provider_dispatch_outside_billing_scope_is_refused(name):
    assert current_billing_scope() is None
    with pytest.raises(SecurityError) as exc:
        UNBILLED_DISPATCHES[name]()
    assert exc.value.code == "unbilled_provider_dispatch"


@pytest.mark.unbilled
def test_billing_scope_requires_a_known_price_and_an_id():
    with pytest.raises(SecurityError) as exc:
        with billing_scope("job-1", 0):
            pass
    assert exc.value.code == "pricing_not_configured"
    with pytest.raises(SecurityError):
        with billing_scope("", 5):
            pass
    with billing_scope("resize-1", 0, free=True) as scope:
        assert scope["free"] is True
    assert current_billing_scope() is None


@pytest.mark.unbilled
def test_billing_scope_follows_threads_and_off_loop_provider_calls():
    async def scenario():
        with billing_scope("job-ctx", 7):
            in_thread = await asyncio.to_thread(current_billing_scope)

            async def provider():
                return current_billing_scope()
            off_loop = await main.run_provider_coroutine_off_loop(provider)
        return in_thread, off_loop
    in_thread, off_loop = asyncio.run(scenario())
    assert in_thread["generation_id"] == "job-ctx"
    assert off_loop["generation_id"] == "job-ctx"


# ------------------------------------------------------------- ledger fixture

@pytest.fixture
def ledger(monkeypatch):
    if not DATABASE:
        pytest.skip("Set SYLVEX_TEST_DATABASE_URL to a disposable PostgreSQL database")
    import psycopg2

    def connect(*args, **kwargs):
        return psycopg2.connect(DATABASE)

    def run(sql, params=None, fetch=False):
        conn = connect()
        try:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                rows = cur.fetchall() if fetch else None
            conn.commit()
            return rows
        finally:
            conn.close()

    for statement in (
        "DROP TABLE IF EXISTS generation_reservations, generation_charges, users, prostudio_generation_jobs CASCADE",
        "CREATE TABLE users(telegram_id BIGINT PRIMARY KEY, balance INTEGER)",
        "CREATE TABLE generation_charges(id SERIAL PRIMARY KEY, generation_id TEXT UNIQUE, telegram_id BIGINT, mode TEXT, model TEXT, provider TEXT, credits INTEGER, balance_after INTEGER)",
        "CREATE TABLE prostudio_generation_jobs(id TEXT PRIMARY KEY, telegram_id BIGINT, mode TEXT, model TEXT, provider TEXT, prompt TEXT, status TEXT, request_json JSONB, heartbeat_at TIMESTAMPTZ)",
        "INSERT INTO users VALUES (101, 100), (202, 1), (303, 500)",
    ):
        run(statement)
    billing_safety.ensure_reservations(connect)
    monkeypatch.setattr(main, "DATABASE_URL", DATABASE)
    monkeypatch.setattr(main, "db_connect", connect)
    monkeypatch.setattr(main, "ensure_user_exists", lambda telegram_id: None)
    monkeypatch.setattr(main, "ensure_prostudio_table", lambda: None)

    def reserve(uid, job_id, credits):
        conn = connect()
        try:
            with conn.cursor() as cur:
                billing_safety.reserve_generation(cur, uid, job_id, credits)
            conn.commit()
        finally:
            conn.close()

    def release(job_id):
        conn = connect()
        try:
            with conn.cursor() as cur:
                billing_safety.release_generation(cur, job_id)
            conn.commit()
        finally:
            conn.close()

    return SimpleNamespace(
        balance=lambda uid: run("SELECT balance FROM users WHERE telegram_id=%s", (uid,), fetch=True)[0][0],
        charges=lambda: run("SELECT generation_id, telegram_id, mode, model, credits FROM generation_charges ORDER BY id", fetch=True),
        reservation=lambda gid: (run("SELECT status, credits FROM generation_reservations WHERE generation_id=%s", (gid,), fetch=True) or [None])[0],
        reserve=reserve,
        release=release,
    )


# ------------------------------------------------- queued jobs: every mode

JOB_PAYLOADS = {
    "text": {"mode": "text", "model": "gpt-5.5", "prompt": "hi"},
    "image": {"mode": "image", "model": "gpt_image_2", "prompt": "cat"},
    "video": {"mode": "video", "model": "kling_3_0", "prompt": "cat"},
    "voice": {"mode": "voice", "model": "elevenlabs_eleven_v3", "prompt": "hello"},
    "music": {"mode": "music", "model": "suno_chirp_5", "prompt": "song"},
    "pro_studio_tool": {"mode": "image", "model": "gpt_image_2", "prompt": "", "image_options": {"tool": "remove_object"}},
    "grid_node": {"mode": "video", "model": "seedance_2_0", "prompt": "grid node", "grid_node_id": "n1"},
}


def _gate(monkeypatch, outcome=None):
    seen = []

    async def fake_billed(job_id, payload, mode, *args):
        seen.append(current_billing_scope())
        return (outcome or {"ok": True, "type": mode}), ("completed" if (outcome or {"ok": True}).get("ok") else "failed")
    monkeypatch.setattr(main, "_run_prostudio_provider_request_billed", fake_billed)
    return seen


def _run_gate(job_id, payload):
    return asyncio.run(main.run_prostudio_provider_request(
        job_id, payload, payload["mode"], payload["model"], "p", {"text"}, "p",
    ))


@pytest.mark.parametrize("kind", sorted(JOB_PAYLOADS))
def test_job_success_charges_once_and_retry_never_double_charges(kind, ledger, monkeypatch):
    seen = _gate(monkeypatch)
    payload = dict(JOB_PAYLOADS[kind], price_snapshot={"final_credits": 7})
    job_id = f"job-{kind}"
    ledger.reserve(101, job_id, 7)
    assert ledger.balance(101) == 93

    result, status = _run_gate(job_id, payload)
    assert status == "completed"
    assert seen and seen[0]["generation_id"] == job_id and seen[0]["credits"] == 7

    first = main.charge_generation_balance(101, job_id, result, payload)
    again = main.charge_generation_balance(101, job_id, result, payload)
    assert first["charged"] is True and again.get("already_charged") is True
    assert ledger.balance(101) == 93
    assert [row[0] for row in ledger.charges()] == [job_id]
    # A settled job can never be dispatched again.
    seen.clear()
    _, status = _run_gate(job_id, payload)
    assert status == "failed" and seen == []


@pytest.mark.parametrize("kind", sorted(JOB_PAYLOADS))
def test_job_provider_failure_refunds_the_reservation(kind, ledger, monkeypatch):
    _gate(monkeypatch, outcome={"ok": False, "error": "provider exploded"})
    payload = dict(JOB_PAYLOADS[kind], price_snapshot={"final_credits": 9})
    ledger.reserve(101, "job-fail", 9)
    _, status = _run_gate("job-fail", payload)
    assert status == "failed"
    ledger.release("job-fail")  # what update_prostudio_generation_job(..., "failed") does
    assert ledger.balance(101) == 100
    assert ledger.charges() == []
    assert "release_generation(cursor, job_id)" in inspect.getsource(main.update_prostudio_generation_job)


def test_job_insufficient_balance_never_reserves_or_dispatches(ledger, monkeypatch):
    seen = _gate(monkeypatch)
    with pytest.raises(SecurityError) as exc:
        ledger.reserve(202, "job-poor", 5)
    assert exc.value.status == 402
    _, status = _run_gate("job-poor", dict(JOB_PAYLOADS["image"], price_snapshot={"final_credits": 5}))
    assert status == "failed" and seen == []
    assert ledger.balance(202) == 1


def test_job_with_unknown_price_is_never_dispatched(ledger, monkeypatch):
    seen = _gate(monkeypatch)
    result, status = _run_gate("job-unpriced", dict(JOB_PAYLOADS["video"]))
    assert status == "failed" and result["raw_error"] == "pricing_not_configured"
    assert seen == []


def test_job_whose_reservation_was_released_is_never_dispatched(ledger, monkeypatch):
    seen = _gate(monkeypatch)
    ledger.reserve(101, "job-cancelled", 4)
    ledger.release("job-cancelled")
    _, status = _run_gate("job-cancelled", dict(JOB_PAYLOADS["text"], price_snapshot={"final_credits": 4}))
    assert status == "failed" and seen == []


def test_free_local_resize_runs_without_reservation(ledger, monkeypatch):
    seen = _gate(monkeypatch)
    payload = {"mode": "image", "model": "resize", "image_options": {"tool": "edit_workspace", "editWorkspaceMode": "resize"},
               "price_snapshot": {"final_credits": 0}}
    _, status = _run_gate("job-resize", payload)
    assert status == "completed" and seen[0]["free"] is True


# ------------------------------------------------------------ priced helpers

def _ok_call(calls, text="done"):
    async def call():
        calls.append(current_billing_scope())
        return {"ok": True, "text": text}
    return call


def test_helper_success_reserves_dispatches_in_scope_and_settles(ledger):
    calls = []
    result = asyncio.run(main.run_billed_helper(101, 3, "grid_plan", _ok_call(calls), model="gpt-5.5"))
    assert result["ok"] and result["cost_credits"] == 3
    assert calls[0]["credits"] == 3 and calls[0]["generation_id"].startswith("helper-grid_plan-")
    assert ledger.balance(101) == 97
    assert [(row[2], row[3], row[4]) for row in ledger.charges()] == [("helper", "gpt-5.5", 3)]


def test_helper_insufficient_balance_never_dispatches(ledger):
    calls = []
    with pytest.raises(SecurityError) as exc:
        asyncio.run(main.run_billed_helper(202, 5, "voice_text_tool", _ok_call(calls)))
    assert exc.value.status == 402 and calls == []
    assert ledger.balance(202) == 1


def test_helper_provider_failure_is_refunded(ledger):
    async def failing():
        return {"ok": False, "error": "provider down"}
    result = asyncio.run(main.run_billed_helper(101, 4, "home_idea_route", failing))
    assert result["ok"] is False
    assert ledger.balance(101) == 100 and ledger.charges() == []


def test_helper_provider_exception_is_refunded(ledger):
    async def exploding():
        raise RuntimeError("timeout")
    with pytest.raises(RuntimeError):
        asyncio.run(main.run_billed_helper(101, 4, "voice_preview", exploding))
    assert ledger.balance(101) == 100 and ledger.charges() == []


def test_helper_retry_with_same_request_id_is_never_charged_twice(ledger):
    calls = []
    asyncio.run(main.run_billed_helper(101, 2, "grid_plan", _ok_call(calls), client_request_id="req-1"))
    with pytest.raises(SecurityError) as exc:
        asyncio.run(main.run_billed_helper(101, 2, "grid_plan", _ok_call(calls), client_request_id="req-1"))
    assert exc.value.status == 409
    assert len(calls) == 1 and len(ledger.charges()) == 1 and ledger.balance(101) == 98


def test_helper_with_unknown_price_never_dispatches(ledger):
    calls = []
    with pytest.raises(SecurityError) as exc:
        asyncio.run(main.run_billed_helper(101, 0, "grid_plan", _ok_call(calls)))
    assert exc.value.code == "pricing_not_configured" and calls == []
    assert ledger.balance(101) == 100


class FakeRequest:
    def __init__(self, payload=None, query=None):
        self._payload = payload or {}
        self.query_params = query or {}
        self.state = SimpleNamespace()

    async def json(self):
        return dict(self._payload)

    async def body(self):
        return b"v=0"


def _body(response):
    if isinstance(response, dict):
        return 200, response
    return response.status_code, json.loads(response.body)


def test_grid_plan_is_charged_at_the_planner_models_text_tariff(ledger, monkeypatch):
    seen = []

    def fake_text_generation(payload):
        seen.append(current_billing_scope())
        return {"ok": True, "text": json.dumps({"action": "clarify", "question": "Which format?"})}
    monkeypatch.setattr(main, "text_generation", fake_text_generation)
    status, body = _body(asyncio.run(main.public_prostudio_grid_plan(FakeRequest({"telegram_id": 101, "task": "promo video", "model": "gpt-5.5"}))))
    assert status == 200 and body["action"] == "clarify"
    (generation_id, uid, mode, model, credits), = ledger.charges()
    assert (uid, mode, model) == (101, "helper", "gpt-5.5") and credits > 0
    assert seen[0]["generation_id"] == generation_id
    assert ledger.balance(101) == 100 - credits


def test_grid_plan_with_unpriced_model_fails_closed(ledger, monkeypatch):
    monkeypatch.setattr(main, "text_generation", _no_network)
    with pytest.raises(SecurityError) as exc:
        asyncio.run(main.public_prostudio_grid_plan(FakeRequest({"telegram_id": 101, "task": "x", "model": "no-such-model"})))
    assert exc.value.code == "pricing_not_configured"
    assert ledger.balance(101) == 100


def test_home_idea_route_is_charged(ledger, monkeypatch):
    monkeypatch.setattr(main, "text_generation", lambda payload: {"ok": True, "text": json.dumps({"reply": "ok", "ready": False})})
    status, body = _body(asyncio.run(main.public_home_idea_route(FakeRequest({"telegram_id": 101, "message": "an ad"}))))
    assert status == 200 and body["ok"]
    assert ledger.charges()[0][3] == "gpt-5.6"
    assert ledger.balance(101) < 100


def test_voice_text_tool_is_charged_and_refunded_when_every_provider_fails(ledger, monkeypatch):
    monkeypatch.setattr(main, "OPENAI_API_KEY", "test")
    monkeypatch.setattr(main, "openai_compatible_text_request", lambda *a, **k: (True, "Improved text", {}))
    status, body = _body(asyncio.run(main.public_prostudio_voice_text_tool(FakeRequest({"telegram_id": 101, "action": "improve", "text": "helo"}))))
    assert status == 200 and body["text"] == "Improved text"
    assert len(ledger.charges()) == 1
    charged_balance = ledger.balance(101)
    monkeypatch.setattr(main, "openai_compatible_text_request", lambda *a, **k: (False, "down", {}))
    monkeypatch.setattr(main, "gemini_text_request", lambda *a, **k: (False, "down", {}))
    status, _ = _body(asyncio.run(main.public_prostudio_voice_text_tool(FakeRequest({"telegram_id": 101, "action": "improve", "text": "helo"}))))
    assert status == 503
    assert ledger.balance(101) == charged_balance and len(ledger.charges()) == 1


def test_voice_preview_is_charged_on_the_fixed_sample_text(ledger, monkeypatch):
    received = []

    async def fake_preview(data):
        received.append(dict(data))
        return {"ok": True, "audio_url": "https://cdn/a.mp3"}
    monkeypatch.setattr(main, "gemini_tts_voice_preview", fake_preview)
    status, _ = _body(asyncio.run(main.public_prostudio_voice_preview(FakeRequest({
        "telegram_id": 101, "model": "gemini_3_1_flash_tts_preview", "voice": "Kore", "text": "free text-to-speech abuse " * 50,
    }))))
    assert status == 200
    assert received[0]["text"] == main.VOICE_PREVIEW_SAMPLE_TEXT
    assert ledger.balance(101) == 99


@pytest.mark.parametrize("endpoint", [
    "elevenlabs_preview", "public_prostudio_runway_avatar", "public_prostudio_transcribe",
    "public_prostudio_elevenlabs_voice_clone", "public_home_idea_realtime",
])
def test_helpers_without_a_tariff_are_blocked_before_any_provider(endpoint):
    response = asyncio.run(getattr(main, endpoint)(FakeRequest({"telegram_id": 101})))
    status, body = _body(response)
    assert status == 402 and body["error"] == "pricing_not_configured"


def test_voice_avatar_auto_generation_stays_blocked_even_when_enabled(monkeypatch):
    monkeypatch.setattr(main, "VOICE_AVATAR_AUTO_GENERATION", True)
    monkeypatch.setattr(main, "DATABASE_URL", "postgres://unused")
    monkeypatch.setattr(main, "db_connect", _no_network)
    assert main.schedule_voice_avatars_batch([{"provider": "elevenlabs", "voice_id": "v1"}]) == {}


# --------------------------------------------- Character / Object creation

def test_character_and_object_prices_compose_existing_tariffs():
    shot = main._gpt_image_2_shot_price()
    assert shot > 0
    assert main.character_creation_price() == 4 * shot
    vision = main.helper_text_price("gpt-5.5", main._object_prompt_instruction_text("Bag", "leather"))
    assert vision > 0
    assert main.object_creation_price("Bag", "leather") == shot + vision


def _creation_stubs(monkeypatch, ledger, fail=False):
    seen = []

    async def fake_images(job_id, name, gender, description, photos):
        seen.append(current_billing_scope())
        if fail:
            raise RuntimeError("OpenAI character image generation failed (status=500): boom")
        return [f"https://cdn/{i}.png" for i in range(4)]

    def fake_update(job_id, status, result=None, error=None, conversation_id=""):
        if status == "failed":
            ledger.release(job_id)
        return True

    async def no_progress(*args, **kwargs):
        return None
    monkeypatch.setattr(main, "_generate_openai_character_images", fake_images)
    monkeypatch.setattr(main, "save_prostudio_resource", lambda telegram_id, resource: resource)
    monkeypatch.setattr(main, "update_prostudio_generation_job", fake_update)
    monkeypatch.setattr(main, "get_prostudio_generation_job_status", lambda job_id: "processing")
    monkeypatch.setattr(main, "heartbeat_prostudio_generation_job", lambda job_id: None)
    monkeypatch.setattr(main, "_record_character_job_progress", no_progress)
    return seen


def test_character_creation_reserves_dispatches_in_scope_and_settles(ledger, monkeypatch):
    seen = _creation_stubs(monkeypatch, ledger)
    credits = main.character_creation_price()
    job_id = main.create_character_creation_job(303, "Ann", "female", "", ["https://cdn/src.png"], credits)
    assert ledger.balance(303) == 500 - credits and ledger.reservation(job_id) == ("reserved", credits)
    asyncio.run(main._run_character_creation_job(job_id, 303, "Ann", "female", "", ["https://cdn/src.png"], credits))
    assert seen[0]["generation_id"] == job_id
    assert ledger.balance(303) == 500 - credits
    assert ledger.reservation(job_id)[0] == "charged"
    assert [row[0] for row in ledger.charges()] == [job_id]


def test_character_creation_failure_refunds(ledger, monkeypatch):
    _creation_stubs(monkeypatch, ledger, fail=True)
    credits = main.character_creation_price()
    job_id = main.create_character_creation_job(303, "Ann", "female", "", ["https://cdn/src.png"], credits)
    asyncio.run(main._run_character_creation_job(job_id, 303, "Ann", "female", "", ["https://cdn/src.png"], credits))
    assert ledger.balance(303) == 500 and ledger.charges() == []


def test_character_creation_with_insufficient_balance_creates_nothing(ledger):
    with pytest.raises(SecurityError) as exc:
        main.create_character_creation_job(101, "Ann", "female", "", ["https://cdn/src.png"], main.character_creation_price())
    assert exc.value.status == 402 and ledger.balance(101) == 100


def test_object_creation_reserves_and_settles(ledger, monkeypatch):
    seen = []

    async def fake_reference(job_id, name, description, photo):
        seen.append(current_billing_scope())
        return "https://cdn/object.png"

    async def fake_analysis(job_id, name, description, photo):
        seen.append(current_billing_scope())
        return "a brown leather bag"

    async def no_progress(*args, **kwargs):
        return None
    monkeypatch.setattr(main, "_generate_object_reference_image", fake_reference)
    monkeypatch.setattr(main, "_analyze_object_prompt", fake_analysis)
    monkeypatch.setattr(main, "_record_object_job_progress", no_progress)
    monkeypatch.setattr(main, "save_prostudio_resource", lambda telegram_id, resource: resource)
    monkeypatch.setattr(main, "update_prostudio_generation_job", lambda *a, **k: True)
    monkeypatch.setattr(main, "get_prostudio_generation_job_status", lambda job_id: "processing")
    monkeypatch.setattr(main, "heartbeat_prostudio_generation_job", lambda job_id: None)
    credits = main.object_creation_price("Bag", "")
    job_id = main.create_object_creation_job(303, "Bag", "", ["https://cdn/src.png"], credits)
    asyncio.run(main._run_object_creation_job(job_id, 303, "Bag", "", ["https://cdn/src.png"], credits))
    assert {scope["generation_id"] for scope in seen} == {job_id}
    assert ledger.balance(303) == 500 - credits and ledger.reservation(job_id)[0] == "charged"


def test_unpriced_creation_job_is_failed_without_dispatch(monkeypatch):
    updates = []
    monkeypatch.setattr(main, "update_prostudio_generation_job", lambda *a, **k: updates.append(a[:2]))
    monkeypatch.setattr(main, "_generate_openai_character_images", _no_network)
    asyncio.run(main._run_character_creation_job("job-x", 1, "Ann", "female", "", [], 0))
    assert updates == [("job-x", "failed")]
