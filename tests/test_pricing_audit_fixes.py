from decimal import Decimal

import main
from services.price_engine import finalise_price, settle_media_price_snapshot
from services.video_router import estimate_video_generation_cost


def test_sylvex_asset_fee_is_one_credit_per_unique_asset_and_separate():
    url = "https://cdn.example/ref.png"
    payload = {
        "mode": "image",
        "image_options": {
            "style": "cinematic",
            "selected_object": "watch",
            "character_id": "person-1",
            "referenceImageUrls": [url, "https://cdn.example/ref-2.png"],
            "referenceImages": [{"url": url}],
        },
        "references": [url],
    }
    snapshot = finalise_price(10, payload)
    assert snapshot["provider_and_model_credits"] == 10
    assert snapshot["sylvex_project_fee_credits"] == 5
    assert snapshot["additions"] == {
        "sylvex_styles": 1.0,
        "sylvex_characters": 1.0,
        "sylvex_objects": 1.0,
        "sylvex_references": 2.0,
    }
    assert snapshot["final_credits"] == 15


def test_text_image_attachment_keeps_provider_tokens_and_one_project_reference_fee():
    plain = main.calculate_generation_price({"mode": "text", "model": "gpt-5.5", "prompt": "describe"})
    with_image = main.calculate_generation_price({
        "mode": "text",
        "model": "gpt-5.5",
        "prompt": "describe",
        "attachment": {"url": "https://cdn.example/photo.png", "mime": "image/png"},
    })
    assert with_image["price_snapshot"]["sylvex_project_fee_credits"] == 1
    assert with_image["price_snapshot"]["additions"] == {"sylvex_references": 1.0}
    assert with_image["credits"] > plain["credits"]


def test_seedream_5_pro_provider_reference_fee_starts_with_second_reference():
    no_ref = main.seedream_cost_info("seedream_5_0_pro", "", 1, "1024x1024", 0)
    one_ref = main.seedream_cost_info("seedream_5_0_pro", "", 1, "1024x1024", 1)
    three_refs = main.seedream_cost_info("seedream_5_0_pro", "", 1, "1024x1024", 3)
    assert no_ref["provider_cost_usd"] == one_ref["provider_cost_usd"] == 0.045
    assert three_refs["provider_reference_cost_usd"] == 0.006
    assert three_refs["cost_credits"] == 8
    assert main.seedream_cost_info("seedream_4_5", "", 1, "2048x2048", 4)["provider_reference_cost_usd"] == 0


def test_flux_two_prices_output_and_each_reference_by_rounded_megapixel():
    info = main.flux_cost_info("flux_2", "flux-2-pro", 1, "2048x2048", ["1200x1200"])
    assert info["output_megapixels"] == 5
    assert info["reference_megapixels"] == [2]
    assert info["provider_cost_usd"] == 0.12
    assert info["cost_credits"] == 18


def test_retired_and_unconfirmed_video_routes_fail_closed():
    for model in ("sora_2", "sora_2_pro", "runway_gen3a_turbo", "runway_aleph", "luma_dream_machine", "minimax_hailuo_2_3"):
        estimate = estimate_video_generation_cost({"mode": "video", "model": model, "video_options": {"model": model}})
        assert estimate["pricing_available"] is False
        assert estimate["credits"] == 0


def test_direct_veo_price_does_not_change_when_sound_toggle_is_off():
    def price(sound):
        return estimate_video_generation_cost({
            "mode": "video", "model": "veo_3_1",
            "video_options": {"model": "veo_3_1", "duration": 5, "resolution": "720p", "sound": sound},
        })["credits"]
    assert price(False) == price(True) == 300


def test_gemini_tts_reserves_input_and_audio_output_tokens():
    short = main.estimate_generation_cost({"mode": "voice", "model": "gemini_3_1_flash_tts_preview", "prompt": "hello", "voice_options": {"model": "gemini_3_1_flash_tts_preview", "duration": 5}})
    long = main.estimate_generation_cost({"mode": "voice", "model": "gemini_3_1_flash_tts_preview", "prompt": "hello", "voice_options": {"model": "gemini_3_1_flash_tts_preview", "duration": 120}})
    assert long["credits"] > short["credits"] >= 1


def test_voice_provider_reported_usage_is_used_for_final_cost():
    eleven = main.voice_provider_usage_cost_usd(
        {"mode": "voice", "model": "elevenlabs_eleven_v3"},
        {"ok": True, "provider": "elevenlabs", "response": {"character_cost": "250"}},
    )
    assert eleven == 0.025

    gemini = main.voice_provider_usage_cost_usd(
        {"mode": "voice", "model": "gemini_3_1_flash_tts_preview"},
        {
            "ok": True,
            "provider": "gemini",
            "response": {"usageMetadata": {"promptTokenCount": 100, "candidatesTokenCount": 250}},
        },
    )
    assert gemini == 0.0051


def test_text_cached_usage_long_context_and_xai_exact_cost():
    uncached = main.text_tokens_credits("gpt-5.5", 100_000, 1000)
    cached = main.text_tokens_credits("gpt-5.5", 100_000, 1000, 90_000)
    assert cached < uncached
    assert main.text_token_rates("byteplus_seed_2_lite", 128_001) == (Decimal("0.50"), Decimal("4.00"))
    # $0.04 exact provider cost -> 6 credits with the 50% markup.
    usage = {"usage": {"input_tokens": 1, "output_tokens": 1, "cost_in_usd_ticks": 400_000_000}}
    assert main.text_usage_credits("grok_4_1", usage) == 6


def test_media_exact_cost_settlement_keeps_project_fee_and_never_exceeds_reservation():
    payload = {"price_snapshot": {"final_credits": 20, "additions_credits": 2, "sylvex_project_fee_credits": 2}}
    result = {"provider": "grok", "provider_response": {"usage": {"cost_in_usd_ticks": 400_000_000}}}
    settled = settle_media_price_snapshot(payload, result)
    assert settled["provider_and_model_credits"] == 6
    assert settled["sylvex_project_fee_credits"] == 2
    assert settled["final_credits"] == 8
    expensive = {"provider": "grok", "provider_response": {"usage": {"cost_in_usd_ticks": 99_000_000_000}}}
    assert settle_media_price_snapshot(payload, expensive)["final_credits"] == 20
