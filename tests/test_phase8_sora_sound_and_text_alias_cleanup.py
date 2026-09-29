"""Regression tests for the Pro Studio A-Z audit's Phase 8 fixes:

- Sora 2 / Sora 2 Pro declared sound:True in VIDEO_MODEL_CONFIG despite
  _call_sora never sending any audio field (OpenAI's Sora 2 API has no
  documented audio control at all) - the Sound toggle it gated in the
  composer had zero real effect either way. Now sound:False.
- TEXT_MODEL_ALIASES was a pure identity-mapping dict (every key mapped to
  itself) feeding normalize_text_model() - functionally a no-op layer.
  Removed; normalize_text_model() now falls back directly to the raw model
  id, with identical behavior for every previously-aliased key.
"""
import services.video_router as video_router
import main


def test_sora_models_no_longer_declare_sound_support():
    assert video_router.VIDEO_MODEL_CONFIG["sora_2"]["sound"] is False
    assert video_router.VIDEO_MODEL_CONFIG["sora_2_pro"]["sound"] is False


def test_sora_sound_gating_never_reaches_the_real_request_either_way():
    # Even before this fix, _call_sora never read body.get("sound") - the
    # toggle was decorative. This just confirms the gated capability flag
    # is consistent with that reality now (sound never granted to Sora).
    payload = {"video_options": {"model": "sora_2", "sound": True, "duration": 8}}
    body = video_router._build_video_payload("sora_2", "test", payload)
    assert body["sound"] is False


def test_text_model_aliases_dict_removed():
    assert not hasattr(main, "TEXT_MODEL_ALIASES")


def test_normalize_text_model_unchanged_for_every_previously_aliased_key():
    previously_aliased = [
        "gpt-5.6", "gpt-5.5", "gpt-5", "gpt-5-mini", "gpt-4.1", "gpt-4.1-mini",
        "gpt-4o", "gpt-4o-mini", "gemini_3_1_pro", "gemini_3_1_flash",
        "gemini_2_5_pro", "gemini_2_5_flash", "grok_4_1", "grok_4_fast",
        "grok_3", "qwen_plus", "qwen_turbo", "qwen_max", "byteplus_seed_2_lite",
    ]
    for model_id in previously_aliased:
        assert main.normalize_text_model(model_id) == model_id


def test_normalize_text_model_still_defaults_empty_to_gpt55():
    assert main.normalize_text_model("") == "gpt-5.5"
    assert main.normalize_text_model(None) == "gpt-5.5"


def test_normalize_text_model_still_redirects_image_model_ids():
    assert main.normalize_text_model("gpt_image_1") == "gpt-5.5"
    assert main.normalize_text_model("gpt-image-2") == "gpt-5.5"
