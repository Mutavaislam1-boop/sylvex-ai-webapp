"""SYLVEX pricing rule: user credits = ceil(provider_cost_usd * 1.5 * 100),
computed in one Decimal function, and usage-billed LLM helpers that cap
output and settle on provider-reported tokens. No network."""
import json

import pytest

import main
from services.price_engine import sylvex_credits
from services import assistant_openai


@pytest.mark.parametrize("cost,credits", [("0.10", 15), ("0.20", 30), ("0.13", 20), ("0.6", 90), ("0.004", 1), ("0", 0)])
def test_sylvex_credits_is_exact(cost, credits):
    assert sylvex_credits(cost) == credits
    assert sylvex_credits(float(cost)) == credits  # float input: no 15.000000000000002 -> 16


def test_cost_derived_tariffs_follow_the_rule():
    assert [main.character_replace_cost_info(n)["credits"] for n in range(6)] == [11, 15, 20, 24, 29, 33]  # 1 input was 16
    assert main.enhance_photo_cost_info()["credits"] == 15
    assert main.animate_photo_cost_info()["credits"] == 90
    assert main.FASHN_TRYON_CREDITS_PER_GARMENT == 30  # tryon-max $0.20, was 9


def test_text_tariff_uses_usd_token_rates():
    # gpt-5.5 $5/$30 per 1M; 1,000 in + 512 out = $0.02036 -> 4 credits.
    assert main.text_tokens_credits("gpt-5.5", 1000, 512) == 4
    assert main.text_tokens_credits("no-such-model", 1000, 512) == 0
    assert main.helper_text_reservation("gpt-5.5", "x" * 1000, 512) == 4
    assert main.helper_text_reservation("gpt-5.5", "x", 100, image_count=1) == main.text_tokens_credits("gpt-5.5", 1 + main.HELPER_IMAGE_TOKEN_BOUND, 100)


@pytest.mark.parametrize("metadata,tokens", [
    ({"usage": {"input_tokens": 10, "output_tokens": 20}}, (10, 20)),                     # Responses API
    ({"usage": {"prompt_tokens": 11, "completion_tokens": 21}}, (11, 21)),                # Chat Completions
    ({"usageMetadata": {"promptTokenCount": 12, "candidatesTokenCount": 5, "thoughtsTokenCount": 7}}, (12, 12)),  # Gemini thinking billed as output
    ({}, None), (None, None),
])
def test_provider_usage_is_read_from_every_response_shape(metadata, tokens):
    assert main.text_usage_tokens(metadata) == tokens


class _Resp:
    status_code = 200
    content = b"{}"
    text = "{}"

    def __init__(self, data):
        self._data = data

    def json(self):
        return self._data


def test_output_cap_reaches_every_provider_request(monkeypatch):
    sent = []

    def fake_post(url, headers=None, data=None, timeout=None, **kw):
        sent.append((url, json.loads(data)))
        return _Resp({"output_text": "ok", "choices": [{"message": {"content": "ok"}}], "candidates": []})
    monkeypatch.setattr(main.requests, "post", fake_post)
    monkeypatch.setattr(main, "env_value", lambda *names, default="": default or "key")
    monkeypatch.setattr(main, "OPENAI_API_KEY", "key")
    with main.billing_scope("cap-test", 1):
        main.call_text_provider("gpt-5.5", [{"role": "user", "content": "hi"}], None, 777)
        main.call_text_provider("gpt-5-mini", [{"role": "user", "content": "hi"}], None, 777)
        main.call_text_provider("gemini_2_5_flash", [{"role": "user", "content": "hi"}], None, 777)
        main.call_text_provider("gpt-5.5", [{"role": "user", "content": "hi"}])  # no cap: product text unchanged
    bodies = [body for _, body in sent]
    assert any(body.get("max_output_tokens") == 777 for body in bodies)                  # Responses
    assert any(body.get("max_completion_tokens") == 777 for body in bodies)              # Chat Completions
    assert any((body.get("generationConfig") or {}).get("maxOutputTokens") == 777 for body in bodies)  # Gemini
    assert "max_output_tokens" not in bodies[-1]


def test_assistant_stream_caps_output_and_reports_usage(monkeypatch):
    events = [
        {"type": "response.output_text.delta", "delta": "Hi"},
        {"type": "response.completed", "response": {"usage": {"input_tokens": 100, "output_tokens": 50}}},
    ]

    class Stream:
        status_code = 200

        def iter_lines(self, decode_unicode=True):
            for event in events:
                yield "data: " + json.dumps(event)

        def close(self):
            pass
    bodies = []
    monkeypatch.setattr(assistant_openai.requests, "post", lambda url, headers=None, data=None, stream=None, timeout=None: bodies.append(json.loads(data)) or Stream())
    usage = {}
    with main.billing_scope("assistant-test", 1):
        text = "".join(assistant_openai.stream_assistant_reply("key", "https://api", "gpt-5.6", [{"role": "user", "content": "x"}],
                                                             max_output_tokens=900, usage_sink=usage))
    assert text == "Hi" and bodies[0]["max_output_tokens"] == 900
    assert main.text_usage_credits("gpt-5.6", usage) == main.text_tokens_credits("gpt-5.6", 100, 50)
