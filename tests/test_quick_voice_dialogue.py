"""Quick Access → Voice: block-based dialogue.

Every block keeps its own voice and position, the billed prompt is rebuilt
from the blocks, AI-written scripts are split into blocks without voices and
only supported Eleven v3 tags survive."""
import asyncio
import json
import re
from pathlib import Path

import httpx
import pytest

import main
import services.audio_router as audio_router

BLOCKS = [
    {"voice_id": "voiceA", "voice_name": "Elena", "text": "[excited] I finally found it!"},
    {"voice_id": "voiceB", "voice_name": "Marcus", "text": "Really? [curious] Where?"},
    {"voice_id": "voiceA", "voice_name": "Elena", "text": "Right here."},
    {"voice_id": "voiceA", "voice_name": "Elena", "text": "Look."},
]


def _payload(blocks=None, model="elevenlabs_eleven_v3", prompt="x"):
    return {
        "mode": "voice",
        "model": model,
        "prompt": prompt,
        "voice_options": {"model": model, "elevenlabs_tool": "dialogue", "dialogue_blocks": [dict(b) for b in (BLOCKS if blocks is None else blocks)]},
    }


def test_blocks_become_ordered_dialogue_inputs_without_merging():
    inputs = audio_router._elevenlabs_dialogue_inputs("ignored", {"dialogue_blocks": BLOCKS})
    assert inputs == [{"text": b["text"], "voice_id": b["voice_id"]} for b in BLOCKS]


@pytest.mark.parametrize("blocks,code", [
    ([], "dialogue_empty"),
    ([{"voice_id": "", "text": "hi"}], "dialogue_voice_missing"),
    ([{"voice_id": "a", "text": "  "}], "dialogue_text_missing"),
    ([{"voice_id": "bad id!", "text": "hi"}], "dialogue_invalid_block"),
    ([{"voice_id": "v%d" % i, "text": "hi"} for i in range(11)], "dialogue_too_many_voices"),
    ([{"voice_id": "a", "text": "x" * 1500}, {"voice_id": "b", "text": "y" * 501}], "dialogue_too_long"),
])
def test_invalid_blocks_are_rejected(blocks, code):
    error = main.normalize_voice_dialogue_request(_payload(blocks))
    assert error and error["error"] == code and error["message"]


def test_unsupported_model_is_rejected():
    error = main.normalize_voice_dialogue_request(_payload(model="elevenlabs_multilingual_v2"))
    assert error["error"] == "dialogue_model_not_supported"


def test_prompt_and_price_come_from_the_blocks():
    payload = _payload(prompt="hi")  # a short prompt must not under-price long blocks
    assert main.normalize_voice_dialogue_request(payload) is None
    joined = "\n".join(b["text"] for b in BLOCKS)
    assert payload["prompt"] == joined
    options = payload["voice_options"]
    assert options["elevenlabs_tool"] == "dialogue" and options["speaker_voices"] == ["voiceA", "voiceB"] and options["num_speakers"] == 2
    estimate = main.calculate_generation_price(payload)
    assert estimate["pricing_available"] is True
    assert estimate["credits"] == (len(joined) + 49) // 50 * 2


def test_requests_without_blocks_are_untouched():
    payload = {"mode": "voice", "model": "elevenlabs_eleven_v3", "prompt": "Hello", "voice_options": {"model": "elevenlabs_eleven_v3"}}
    assert main.normalize_voice_dialogue_request(payload) is None
    assert payload["prompt"] == "Hello" and "elevenlabs_tool" not in payload["voice_options"]


class _FakeClient:
    def __init__(self, calls):
        self.calls = calls

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return httpx.Response(200, content=b"mp3", headers={"content-type": "audio/mpeg"}, request=httpx.Request("POST", url))


@pytest.mark.parametrize("model", ["elevenlabs_eleven_v3", "elevenlabs_multilingual_v2"])
def test_dialogue_goes_to_text_to_dialogue_with_eleven_v3(monkeypatch, model):
    calls = []
    monkeypatch.setattr(audio_router, "httpx", type("_M", (), {"AsyncClient": lambda self=None, **kw: _FakeClient(calls)})())
    monkeypatch.setattr(audio_router, "_get_env", lambda *names: "test-key")
    monkeypatch.setattr(audio_router, "_elevenlabs_headers", lambda: {"xi-api-key": "test-key"})
    monkeypatch.setattr(audio_router, "optimize_prompt_for_model", lambda prompt, **k: {"ok": True, "optimized": False})

    async def fake_completed(payload, frontend_model, provider_model, tool, content, content_type, meta):
        return {"ok": True, "provider_model": provider_model, "tool": tool}

    monkeypatch.setattr(audio_router, "_completed_elevenlabs_voice_response", fake_completed)
    payload = _payload(model=model)
    payload["prompt"] = "\n".join(b["text"] for b in BLOCKS)
    result = asyncio.run(audio_router.elevenlabs_voice_generation(payload))
    assert result == {"ok": True, "provider_model": "eleven_v3", "tool": "dialogue"}
    url, kwargs = calls[0]
    assert url.endswith("/v1/text-to-dialogue")
    assert kwargs["json"]["model_id"] == "eleven_v3"
    assert kwargs["json"]["inputs"] == [{"text": b["text"], "voice_id": b["voice_id"]} for b in BLOCKS]


def test_ai_script_is_split_into_blocks_with_supported_tags_only():
    script = "**Anna**: [excited] We found it! [shouting] Look!\nBoris: [curious] Really?\nand then?\n- Anna: [Laughs] Yes."
    assert main.parse_voice_dialogue_script(script) == [
        {"speaker": "Anna", "text": "[excited] We found it! Look!"},
        {"speaker": "Boris", "text": "[curious] Really? and then?"},
        {"speaker": "Anna", "text": "[laughs] Yes."},
    ]


def test_ai_script_respects_the_dialogue_length_limit():
    script = "\n".join("A: " + "x" * 300 for _ in range(10))
    blocks = main.parse_voice_dialogue_script(script)
    assert sum(len(b["text"]) for b in blocks) <= 2000 and len(blocks) == 6


def test_dialogue_text_tool_returns_blocks(monkeypatch):
    sent = []
    monkeypatch.setattr(main, "OPENAI_API_KEY", "test")

    def fake_openai(provider, base, key, model, messages, extra):
        sent.append(messages[-1]["content"])
        return True, "Anna: [excited] Hi!\nBoris: Hello.", {}

    async def fake_billed(telegram_id, credits, operation, call, **kwargs):
        return await call()

    monkeypatch.setattr(main, "openai_compatible_text_request", fake_openai)
    monkeypatch.setattr(main, "run_billed_helper", fake_billed)

    class Request:
        async def json(self):
            return {"telegram_id": 101, "action": "dialogue", "brief": "Two friends meet"}

    body = asyncio.run(main.public_prostudio_voice_text_tool(Request()))
    assert body["blocks"] == [{"speaker": "Anna", "text": "[excited] Hi!"}, {"speaker": "Boris", "text": "Hello."}]
    assert "Two friends meet" in sent[0] and "[whispers]" in sent[0]


def test_dialogue_text_tool_needs_a_brief():
    class Request:
        async def json(self):
            return {"telegram_id": 101, "action": "dialogue", "brief": " "}

    response = asyncio.run(main.public_prostudio_voice_text_tool(Request()))
    assert response.status_code == 400


def test_gallery_returns_saved_blocks():
    metadata = {"settings": {"dialogue_blocks": BLOCKS + ["junk"]}}
    assert main.gallery_dialogue_blocks(metadata) == BLOCKS
    assert main.gallery_dialogue_blocks({"settings": {}}) == []


def test_mini_app_tags_match_the_server_list():
    source = (Path(__file__).parent.parent / "webapp/js/cabinet.js").read_text(encoding="utf-8")
    match = re.search(r"audioTags:\[(.*?)\] \}", source, re.S)
    tags = re.findall(r"\['([a-z ]+)','", match.group(1))
    assert tuple(tags) == audio_router.ELEVENLABS_V3_AUDIO_TAGS
