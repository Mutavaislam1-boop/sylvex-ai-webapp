"""grok_3, qwen_plus, qwen_turbo, and qwen_max were fully wired in
TEXT_MODEL_VARIANTS and selectable in the UI, but estimate_generation_cost's
per_million pricing table for text mode had no entry for any of them -
public_prostudio_generate rejects any model with pricing_available=False
with HTTP 422 pricing_not_configured before text_generation() is ever
called, so these 4 models were dead on arrival regardless of API keys."""
import main


def test_previously_unpriced_text_models_now_have_pricing_available():
    for model in ("grok_3", "qwen_plus", "qwen_turbo", "qwen_max"):
        result = main.estimate_generation_cost({"mode": "text", "model": model, "prompt": "hello"})
        assert result["pricing_available"] is True, f"{model} must not be blocked by pricing_not_configured"
        assert result["credits"] >= 1


def test_still_rejects_a_genuinely_unknown_text_model():
    result = main.estimate_generation_cost({"mode": "text", "model": "not_a_real_model", "prompt": "hello"})
    assert result["pricing_available"] is False
