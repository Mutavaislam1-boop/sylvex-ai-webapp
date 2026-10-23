"""Home router and Text-chat SYLVEX links."""
import asyncio
import json
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).parent.parent))

import main


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


def test_realtime_voice_mode_is_removed_for_now():
    paths = {getattr(route, "path", "") for route in main.app.routes}
    assert "/api/public/prostudio/realtime/session" not in paths
    assert "/api/public/prostudio/conversations/voice-turn" not in paths


def test_text_models_keep_their_real_identity():
    prompt = main.text_system_prompt("text", "neutral", "markdown", "gpt-5.6")
    assert "You are GPT-5.6 by OpenAI" in prompt
    assert "Do not call yourself SYLVEX Assistant" in prompt
    assert "SYLVEX Pro Studio Text AI" not in prompt
    assert "You are Gemini 3.1 Pro by Google" in main.text_system_prompt("text", "neutral", "markdown", "gemini_3_1_pro")
    # Every selectable text model has a display identity.
    assert set(main.TEXT_MODEL_VARIANTS) <= set(main.TEXT_MODEL_IDENTITY)


def test_text_chat_policy_assistant_scope_and_catalog():
    assert main.sylvex_text_policy({"tool": "text"}) == ""
    assert main.sylvex_text_policy({"tool": "translate", "sylvex_links": True}) == ""
    catalog = {
        "video": [["kling_3_0", "Kling 3.0"], ["bad id!", "Evil](javascript:x)"], ["veo_3_1", "Veo [3.1]"]],
        "image": "not a list",
        "other": [["x", "y"]],
    }
    policy = main.sylvex_text_policy({"tool": "text", "sylvex_links": True, "sylvex_catalog": catalog})
    assert "(sylvex://assistant)" in policy and "SYLVEX Assistant" in policy
    assert "unrestricted general-purpose assistant" in policy
    assert "sylvex://model/<section>/<id>" in policy
    assert "video: kling_3_0=Kling 3.0; badid=Evil  javascript:x; veo_3_1=Veo  3.1" in policy
    assert "image:" not in policy and "other:" not in policy


def test_text_generation_sends_identity_and_policy(monkeypatch):
    seen = {}

    def fake_provider(model, messages, attachment=None, max_output_tokens=None):
        seen["model"] = model
        seen["system"] = messages[0]["content"]
        return {"ok": True, "text": "ok", "provider": "openai", "model": model}

    monkeypatch.setattr(main, "call_text_provider", fake_provider)
    payload = {"prompt": "Which model is best for video?", "model": "gpt-5.6",
               "text_options": {"tool": "text", "sylvex_links": True, "sylvex_catalog": {"video": [["kling_3_0", "Kling 3.0"]]}}}
    from services.billing_safety import billing_scope
    with billing_scope("test-identity", 0, free=True):
        result = main.text_generation(payload)
    assert result["ok"]
    assert "You are GPT-5.6 by OpenAI" in seen["system"]
    assert "video: kling_3_0=Kling 3.0" in seen["system"]
    # The reservation covers the same system text.
    linked = main.text_generation_reservation(payload)[1]
    plain = main.text_generation_reservation({"prompt": payload["prompt"], "model": "gpt-5.6", "text_options": {"tool": "text"}})[1]
    assert linked > plain + len(main.SYLVEX_TEXT_LINK_GUIDANCE)


def test_router_takes_the_home_section_and_attached_references(monkeypatch):
    seen = {}

    async def fake_billed(telegram_id, credits, label, call, **kwargs):
        return {"ok": True, "text": json.dumps({"mode": "video", "model": "", "tool": ""})}

    price_input = main.text_generation_price_input

    def capture_price_input(payload):
        seen["prompt"] = payload["prompt"]
        return price_input(payload)

    monkeypatch.setattr(main, "run_billed_helper", fake_billed)
    monkeypatch.setattr(main, "text_generation_price_input", capture_price_input)
    body = {"message": "a cat surfing at sunset", "telegram_id": 7, "models": MODELS, "tools": TOOLS, "section": "video",
            "attachments": [{"kind": "image", "name": "cat.png", "mime": "image/png"}, {"kind": "audio", "name": "wave\nsong.mp3", "mime": "audio/mpeg"}, "junk"]}
    result = _run(main.public_home_idea_route(FakeRequest(body)))
    assert result["mode"] == "video" and result["prompt"] == "a cat surfing at sunset"
    prompt = seen["prompt"]
    assert "Запрос отправлен из раздела «video»" in prompt and "Если сомневаешься — video." in prompt
    assert "Вложение (image): cat.png (image/png)" in prompt and "Вложение (audio): wave song.mp3 (audio/mpeg)" in prompt
    # Files alone are enough to route; an unknown section is ignored.
    seen.clear()
    result = _run(main.public_home_idea_route(FakeRequest({"telegram_id": 7, "section": "rockets", "attachments": [{"kind": "video", "name": "a.mp4"}]})))
    assert result["ok"] and "Запрос отправлен из раздела" not in seen["prompt"] and "Если сомневаешься — text." in seen["prompt"]
    assert "Вложение (video): a.mp4 ()" in seen["prompt"]
