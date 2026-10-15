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
