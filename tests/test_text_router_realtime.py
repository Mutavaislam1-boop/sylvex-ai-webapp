"""Home router, Text-chat SYLVEX links and live voice (Realtime) for the
shared Text conversation."""
import asyncio
import json
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).parent.parent))

import main
import services.assistant_openai as assistant_openai
from services.billing_safety import current_billing_scope


MODELS = {"image": ["seedream_5_0_pro"], "video": ["kling_3_0"], "music": [], "voice": [], "text": ["gpt-5.6"]}
TOOLS = ["remove_bg", "edit_workspace"]


class FakeRequest:
    def __init__(self, payload=None, telegram_id=0):
        self._payload = payload
        self.state = SimpleNamespace(telegram_id=telegram_id)
        self.query_params = {}

    async def json(self):
        if self._payload is None:
            raise ValueError("no json")
        return dict(self._payload)


def _run(coro):
    return asyncio.run(coro)


def test_router_passes_the_original_prompt_and_validates_choices():
    route = main.clean_home_route({"mode": "video", "model": "kling_3_0", "prompt": "rewritten"}, "a fox in snow", MODELS, TOOLS)
    assert route == {"ok": True, "ready": True, "mode": "video", "model": "kling_3_0", "tool": "", "prompt": "a fox in snow", "reply": ""}
    # A model the client did not offer for that mode is dropped.
    assert main.clean_home_route({"mode": "image", "model": "kling_3_0"}, "x", MODELS, TOOLS)["model"] == ""
    # Unknown tool falls back to the Image studio, a known one is kept.
    assert main.clean_home_route({"mode": "tool", "tool": "hack"}, "x", MODELS, TOOLS)["mode"] == "image"
    assert main.clean_home_route({"mode": "tool", "tool": "remove_bg"}, "x", MODELS, TOOLS)["tool"] == "remove_bg"


def test_router_defaults_to_text_when_unclear():
    for route in (None, {}, {"mode": "launch_rockets"}, "garbage"):
        assert main.clean_home_route(route, "what is a codec?", MODELS, TOOLS)["mode"] == "text"


def test_router_uses_a_cheap_capped_classifier(monkeypatch):
    captured = {}

    async def fake_billed(telegram_id, credits, label, call, **kwargs):
        captured.update(telegram_id=telegram_id, credits=credits, label=label, model=kwargs.get("model"))
        return {"ok": True, "text": json.dumps({"mode": "music", "model": "", "tool": ""})}

    monkeypatch.setattr(main, "run_billed_helper", fake_billed)
    body = {"message": "сочини песню про море", "telegram_id": 7, "models": MODELS, "tools": TOOLS}
    result = _run(main.public_home_idea_route(FakeRequest(body)))
    assert result["mode"] == "music" and result["prompt"] == "сочини песню про море"
    assert captured["label"] == "home_idea_route" and captured["model"] == main.HOME_ROUTE_MODEL
    assert captured["credits"] > 0


def test_text_link_guidance_is_opt_in_and_priced():
    plain = {"prompt": "hi", "text_options": {"tool": "text"}}
    linked = {"prompt": "hi", "text_options": {"tool": "text", "sylvex_links": True}}
    assert main.SYLVEX_TEXT_LINK_GUIDANCE not in main.text_generation_price_input(plain)[0]
    assert main.SYLVEX_TEXT_LINK_GUIDANCE in main.text_generation_price_input(linked)[0]
    assert main.text_generation_reservation(linked)[1] > main.text_generation_reservation(plain)[1]
    assert "sylvex://open/video" in main.SYLVEX_TEXT_LINK_GUIDANCE


def test_realtime_instructions_continue_the_conversation():
    text = main.prostudio_realtime_instructions([
        {"role": "user", "text": "Plan a trip to Rome"},
        {"role": "assistant", "text": "Day 1: Colosseum"},
        "junk",
    ])
    assert "User: Plan a trip to Rome" in text and "Assistant: Day 1: Colosseum" in text


def test_realtime_session_requires_account_and_subscription(monkeypatch):
    assert _run(main.public_prostudio_realtime_session(FakeRequest({"sdp": "v=0"}))).status_code == 401
    monkeypatch.setattr(main, "get_user_state", lambda telegram_id: {"subscription_status": "inactive"})
    response = _run(main.public_prostudio_realtime_session(FakeRequest({"sdp": "v=0"}, telegram_id=5)))
    assert response.status_code == 403
    assert json.loads(response.body)["error"] == "subscription_required"


def test_realtime_session_uses_current_model_with_barge_in(monkeypatch):
    captured = {}

    async def no_quota(*args):
        captured["quota"] = args

    def fake_post(url, headers, files, timeout):
        captured["url"] = url
        captured["scope"] = current_billing_scope()
        captured["session"] = json.loads(files["session"][1])
        captured["sdp"] = files["sdp"][1]
        return SimpleNamespace(content=b"v=0\r\nanswer", status_code=201, headers={"content-type": "application/sdp"})

    monkeypatch.setattr(main, "get_user_state", lambda telegram_id: {"subscription_status": "active"})
    monkeypatch.setattr(main, "check_request_quota", no_quota)
    monkeypatch.setattr(main, "OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(assistant_openai.requests, "post", fake_post)
    monkeypatch.setattr(main, "mint_realtime_session", assistant_openai.mint_realtime_session)

    body = {"sdp": "v=0\r\noffer", "context": [{"role": "user", "text": "hello"}]}
    response = _run(main.public_prostudio_realtime_session(FakeRequest(body, telegram_id=77)))
    assert response.status_code == 201 and response.body == b"v=0\r\nanswer"
    assert b"test-key" not in response.body
    assert captured["quota"] == (77, "/api/public/prostudio/realtime/session")
    assert captured["url"] == "https://api.openai.com/v1/realtime/calls"
    assert captured["sdp"] == "v=0\r\noffer"
    assert captured["scope"]["free"] is True and captured["scope"]["credits"] == 0
    session = captured["session"]
    assert session["model"] == main.OPENAI_ASSISTANT_REALTIME_MODEL
    assert "preview" not in session["model"]
    assert session["audio"]["input"]["turn_detection"] == {"type": "semantic_vad", "create_response": True, "interrupt_response": True}
    assert session["audio"]["input"]["transcription"]["model"] == main.PROSTUDIO_REALTIME_TRANSCRIBE_MODEL
    assert "User: hello" in session["instructions"]


def test_voice_turn_saves_into_the_shared_text_history(monkeypatch):
    saved = {}

    def fake_save(payload, result):
        saved.update(payload=payload, result=result)
        return payload.get("conversation_id") or "new-conv"

    monkeypatch.setattr(main, "save_prostudio_message", fake_save)
    assert _run(main.public_prostudio_voice_turn(FakeRequest({"user_text": "hi"}))).status_code == 401
    result = _run(main.public_prostudio_voice_turn(FakeRequest({"conversation_id": "conv-1", "user_text": "hi", "assistant_text": "hello"}, telegram_id=9)))
    assert result == {"ok": True, "conversation_id": "conv-1"}
    assert saved["payload"]["mode"] == "text" and saved["payload"]["telegram_id"] == 9
    assert saved["result"]["metadata"]["source"] == "realtime_voice"
    result = _run(main.public_prostudio_voice_turn(FakeRequest({"user_text": "hi"}, telegram_id=9)))
    assert result["conversation_id"] == "new-conv"


def test_realtime_route_is_quota_checked_once():
    from services import request_limits, security
    assert "/api/public/prostudio/realtime/session" in request_limits.COSTLY
    assert "/api/public/prostudio/realtime/session" in security.ASSISTANT_SELF_QUOTA_ROUTES
