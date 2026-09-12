"""8 of 10 music models (all 6 Suno Chirp variants, MiniMax Music 2.5,
and Google Lyria RealTime) were fully wired in services/audio_router.py
- including a correctly-built, bounded WebSocket session for Lyria
RealTime - but estimate_generation_cost's music pricing table only had
entries for the two Lyria HTTP models. public_prostudio_generate rejects
any model with pricing_available=False with HTTP 422
pricing_not_configured before audio_generation() is ever called, so
these 8 models were dead on arrival regardless of API keys."""
import main


def test_previously_unpriced_music_models_now_have_pricing_available():
    models = (
        "suno_chirp_3_5", "suno_chirp_4_0", "suno_chirp_4_5", "suno_chirp_4_5_plus",
        "suno_chirp_5", "suno_chirp_5_5", "minimax_music_2_5", "google_lyria_realtime",
    )
    for model in models:
        result = main.estimate_generation_cost({"mode": "music", "model": model})
        assert result["pricing_available"] is True, f"{model} must not be blocked by pricing_not_configured"
        assert result["credits"] >= 1


def test_existing_lyria_http_models_still_priced_correctly():
    pro = main.estimate_generation_cost({"mode": "music", "model": "google_lyria_3_pro"})
    clip = main.estimate_generation_cost({"mode": "music", "model": "google_lyria_3_clip"})
    assert pro == {"credits": 12, "cost_usd": 0.08, "generation_cost": "12 ⚡", "pricing_available": True}
    assert clip == {"credits": 6, "cost_usd": 0.04, "generation_cost": "6 ⚡", "pricing_available": True}


def test_still_rejects_a_genuinely_unknown_music_model():
    result = main.estimate_generation_cost({"mode": "music", "model": "not_a_real_model"})
    assert result["pricing_available"] is False
