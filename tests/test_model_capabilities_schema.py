"""services/model_capabilities.py - Phase 1, Batch 1 of the Pro Studio master
remediation plan (see /root/.claude/plans/splendid-moseying-starlight.md).

Migration is additive-only: IMAGE_MODEL_FEATURES, SEEDREAM_MODEL_CAPABILITIES,
VIDEO_MODEL_CONFIG and KLING_COST_MATRIX are left untouched and stay
authoritative; this module's registry is populated from them at import time.
These tests confirm every model from those sources gets a MODEL_CAPABILITIES
entry, and spot-check the specific facts the plan calls out: the dead Kling
voice_control tier stays present-but-unreachable, and every video model's
character/object text-conditioning axis (folding a selected character/object
into the prompt text - see services/character_prompts.py and
_build_video_visual_prompt's has_character branch) stays True, independent
of whether that model supports an actual reference IMAGE.
"""
import main
from services import model_capabilities as mc


def test_every_image_model_has_a_capability_entry():
    for model_id in main.IMAGE_MODEL_FEATURES:
        cap = mc.get_capability(model_id)
        assert cap is not None, f"{model_id} missing from MODEL_CAPABILITIES"
        assert cap.category == mc.MediaCategory.IMAGE


def test_every_video_model_has_a_capability_entry():
    for model_id in main._VIDEO_MODEL_CONFIG:
        cap = mc.get_capability(model_id)
        assert cap is not None, f"{model_id} missing from MODEL_CAPABILITIES"
        assert cap.category == mc.MediaCategory.VIDEO


def test_kling_voice_control_tier_kept_but_marked_unreachable():
    cap = mc.get_capability("kling_2_6")
    tier = cap.pricing.get("voice_control")
    assert tier is not None, "voice_control pricing data must not be deleted"
    assert tier.unreachable is True


def test_kling_2_6_other_tiers_remain_reachable():
    cap = mc.get_capability("kling_2_6")
    assert cap.pricing["standard"].unreachable is False
    assert cap.pricing["native_audio"].unreachable is False


def test_video_text_conditioning_true_even_without_visual_reference_support():
    # kling_2_6 has no visual reference-image support declared (no evidence
    # for it in VIDEO_MODEL_CONFIG), but must still support naming a
    # character/object in the prompt text - this is the axis correction 1 of
    # the approved plan protects.
    cap = mc.get_capability("kling_2_6")
    assert cap.character.visual_reference.visual_mode == mc.VisualReferenceMode.UNSUPPORTED
    assert cap.character.text_conditioning is True
    assert cap.object.text_conditioning is True


def test_video_text_conditioning_true_for_every_model_without_exception():
    for model_id in main._VIDEO_MODEL_CONFIG:
        cap = mc.get_capability(model_id)
        assert cap.character.text_conditioning is True, model_id
        assert cap.object.text_conditioning is True, model_id


def test_heygen_avatar_models_use_provider_native_asset_mode():
    for model_id in ("heygen_avatar_iv", "heygen_avatar_v", "heygen_avatar_iii"):
        cap = mc.get_capability(model_id)
        assert cap.character.visual_reference.visual_mode == mc.VisualReferenceMode.PROVIDER_NATIVE_ASSET, model_id


def test_seedream_reference_limits_carried_into_registry():
    cap = mc.get_capability("seedream_5_0_pro")
    limits = cap.character.visual_reference
    assert limits.max_count == 10
    assert limits.param_name == "image_urls"
    assert limits.accepts_inline_base64 is False
    assert limits.visual_mode == mc.VisualReferenceMode.REAL_MULTI_IMAGE


def test_seedream_bare_aliases_resolve_to_canonical_reference_limits():
    # seedream_5/seedream_5_pro/seedream_4 exist in IMAGE_MODEL_FEATURES but
    # SEEDREAM_MODEL_CAPABILITIES only has their canonical "_0" keys - a code
    # review caught register_image_models() missing this alias resolution,
    # which silently capped these three ids to max_count=1 instead of 10.
    aliases = {
        "seedream_5": ("image", True),
        "seedream_5_pro": ("image_urls", False),
        "seedream_4": ("image", True),
    }
    for model_id, (param_name, accepts_inline_base64) in aliases.items():
        cap = mc.get_capability(model_id)
        assert cap is not None, model_id
        limits = cap.character.visual_reference
        assert limits.max_count == 10, model_id
        assert limits.param_name == param_name, model_id
        assert limits.accepts_inline_base64 is accepts_inline_base64, model_id
        assert limits.visual_mode == mc.VisualReferenceMode.REAL_MULTI_IMAGE, model_id


def test_model_without_character_support_is_unsupported_not_missing():
    cap = mc.get_capability("grok")
    assert cap.character.visual_reference.visual_mode == mc.VisualReferenceMode.UNSUPPORTED
    # Text-conditioning is a trivial true for image generation (it's a
    # text-to-image system) - see register_image_models()'s comment.
    assert cap.character.text_conditioning is True


def test_serialize_capabilities_is_json_shaped():
    data = mc.serialize_capabilities()
    assert "kling_2_6" in data
    entry = data["kling_2_6"]
    assert entry["category"] == "video"
    assert entry["character"]["visual_reference"]["visual_mode"] == "unsupported"
    assert isinstance(entry["durations"], list)
    assert isinstance(entry["pricing"]["voice_control"]["unreachable"], bool)
