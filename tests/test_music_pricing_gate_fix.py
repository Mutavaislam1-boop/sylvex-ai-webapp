"""8 of 10 music models (all 6 Suno Chirp variants, MiniMax Music 2.5,
and Google Lyria RealTime) were fully wired in services/audio_router.py
- including a correctly-built, bounded WebSocket session for Lyria
RealTime - but estimate_generation_cost's music pricing table only had
entries for the two Lyria HTTP models. public_prostudio_generate rejects
any model with pricing_available=False with HTTP 422
pricing_not_configured before audio_generation() is ever called, so
these 8 models were dead on arrival regardless of API keys."""
import main


def test_unverified_aggregator_and_realtime_music_tariffs_fail_closed():
    models = (
        "suno_chirp_3_5", "suno_chirp_4_0", "suno_chirp_4_5", "suno_chirp_4_5_plus",
        "suno_chirp_5", "minimax_music_2_5", "google_lyria_realtime",
    )
    for model in models:
        result = main.estimate_generation_cost({"mode": "music", "model": model})
        assert result["pricing_available"] is False, f"{model} must stay blocked until its account tariff is confirmed"
        assert result["credits"] == 0


def test_existing_lyria_http_models_still_priced_correctly():
    pro = main.estimate_generation_cost({"mode": "music", "model": "google_lyria_3_pro"})
    clip = main.estimate_generation_cost({"mode": "music", "model": "google_lyria_3_clip"})
    assert pro == {"credits": 12, "cost_usd": 0.08, "generation_cost": "12 ⚡", "pricing_available": True}
    assert clip == {"credits": 6, "cost_usd": 0.04, "generation_cost": "6 ⚡", "pricing_available": True}


def test_still_rejects_a_genuinely_unknown_music_model():
    result = main.estimate_generation_cost({"mode": "music", "model": "not_a_real_model"})
    assert result["pricing_available"] is False


def test_suno_prices_set_by_sylvex_for_udioapi_models():
    # Suno runs through the UdioAPI aggregator; SYLVEX sets these prices.
    expected = {"suno_chirp_5_5": 18, "suno_chirp_6": 18, "suno_chirp_6_mini": 15}
    for model, credits in expected.items():
        for payload in ({"mode": "music", "model": model},
                        {"mode": "music", "music_options": {"model": model, "duration_minutes": 4}}):
            result = main.calculate_generation_price(payload)
            assert result["pricing_available"] is True, model
            assert result["credits"] == credits, model
            assert result["generation_cost"] == f"{credits} ⚡", model


def test_new_suno_models_route_to_udioapi_and_grid():
    from services import audio_router
    assert audio_router.AUDIO_API_BASE_URL.startswith("https://udioapi.pro")
    assert audio_router._music_model_mapping("suno_chirp_6") == "chirp-v6"
    assert audio_router._music_model_mapping("suno_chirp_6_mini") == "chirp-v6-mini"
    assert audio_router._music_model_mapping("suno_chirp_5_5") == "chirp-v5-5"
    catalog = main.grid_planner_catalog()["music"]
    for model, credits in {"suno_chirp_5_5": 18, "suno_chirp_6": 18, "suno_chirp_6_mini": 15}.items():
        assert model in catalog["models"]
        assert catalog["cost_hints"][model]["sample_credits"] == credits


def test_published_price_list_and_music_docs_show_suno_prices():
    import asyncio
    import json
    from pathlib import Path
    response = asyncio.run(main.public_prostudio_pricing_catalog())
    assert response.headers["cache-control"] == "no-cache"
    rows = json.loads(response.body)["rows"]
    suno = {row["model"]: row["price"] for row in rows if row["provider"] == "Suno"}
    assert suno == {"Chirp v6": "18 ⚡", "Chirp v5.5": "18 ⚡", "Chirp v6 Mini": "15 ⚡"}
    webapp = Path(__file__).resolve().parent.parent / "webapp"
    docs = (webapp / "docs-music.html").read_text(encoding="utf-8")
    for row in ('<td>Suno Chirp v6</td><td>$0.18</td><td>18 <i class="sx-token" aria-hidden="true"></i></td>',
                '<td>Suno Chirp v5.5</td><td>$0.18</td><td>18 <i class="sx-token" aria-hidden="true"></i></td>',
                '<td>Suno Chirp v6 Mini</td><td>$0.15</td><td>15 <i class="sx-token" aria-hidden="true"></i></td>'):
        assert row in docs
    assert "model=suno_chirp_6" in docs and "model=suno_chirp_6_mini" in docs
    pricing_page = (webapp / "docs-pricing.html").read_text(encoding="utf-8")
    assert "force-cache" not in pricing_page
