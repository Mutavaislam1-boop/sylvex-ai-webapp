"""services/model_capabilities.py - Phase 1 (Batches 1 and 2) of the Pro
Studio master remediation plan (see
/root/.claude/plans/splendid-moseying-starlight.md).

Migration is additive-only: IMAGE_MODEL_FEATURES, SEEDREAM_MODEL_CAPABILITIES,
VIDEO_MODEL_CONFIG and KLING_COST_MATRIX are left untouched and stay
authoritative; this module's registry is populated from them at import time.
These tests confirm every model from those sources gets a MODEL_CAPABILITIES
entry, and spot-check the specific facts the plan calls out: the dead Kling
voice_control tier stays present-but-unreachable, every video model's
character/object text-conditioning axis (folding a selected character/object
into the prompt text - see services/character_prompts.py and
_build_video_visual_prompt's has_character branch) stays True independent of
whether that model supports an actual reference IMAGE, and (Batch 2) the real
per-provider visual-reference classification established by reading every
_call_<provider> function in services/video_router.py.
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
    # sora_2 never reads reference_images at all (_call_sora only ever sends
    # start_image, confirmed by Batch 2's provider research), but must still
    # support naming a character/object in the prompt text - this is the
    # axis correction 1 of the approved plan protects.
    cap = mc.get_capability("sora_2")
    assert cap.character.visual_reference.visual_mode == mc.VisualReferenceMode.UNSUPPORTED
    assert cap.character.text_conditioning is True
    assert cap.object.text_conditioning is True


def test_video_text_conditioning_true_for_every_model_without_exception():
    for model_id in main._VIDEO_MODEL_CONFIG:
        cap = mc.get_capability(model_id)
        assert cap.character.text_conditioning is True, model_id
        assert cap.object.text_conditioning is True, model_id


def test_heygen_avatar_iv_v_iii_are_unsupported_for_this_axis():
    # Batch 2's provider research found _call_heygen_direct_video's
    # avatar_iv/v/iii branch builds its request from a separate, user-
    # supplied avatar_id option - reference_images/characterReferences/
    # objectReferences are never read there at all. These models do have
    # their own unrelated "avatar" concept, but an attached Character/Object
    # reference IMAGE (the thing this axis gates) is silently dropped, so
    # UNSUPPORTED is the honest classification here - not
    # PROVIDER_NATIVE_ASSET, which would wrongly imply the picker's
    # reference image feeds that avatar concept.
    for model_id in ("heygen_avatar_iv", "heygen_avatar_v", "heygen_avatar_iii", "heygen_image_video"):
        cap = mc.get_capability(model_id)
        assert cap.character.visual_reference.visual_mode == mc.VisualReferenceMode.UNSUPPORTED, model_id


def test_heygen_v3_and_cinematic_avatar_are_real_multi_image():
    # Unlike their avatar_iv/v/iii sibling above, these two HeyGen models'
    # provider functions (_call_heygen and _call_heygen_direct_video's
    # cinematic_avatar branch) both call _heygen_files_from_payload, which
    # reads reference_images and forwards every URL as a separate asset.
    for model_id in ("heygen_v3_video_agent", "heygen_cinematic_avatar"):
        cap = mc.get_capability(model_id)
        assert cap.character.visual_reference.visual_mode == mc.VisualReferenceMode.REAL_MULTI_IMAGE, model_id


def test_kling_family_is_degraded_single_image_except_lip_sync():
    # _call_kling resolves reference_images down to a single URL via
    # _first_url() before placing it into one of several differently-named
    # single-image fields depending on model tier/mode - every additional
    # attached reference beyond the first is silently dropped. kling_lip_sync
    # is the one exception: its is_lip_sync branch never places the resolved
    # image anywhere, so it falls through to UNSUPPORTED instead.
    degraded = (
        "kling_3_0_turbo", "kling_3_0", "kling_motion_3_0", "kling_effects",
        "kling_o3_omni", "kling_o3_edit", "kling_o1", "kling_2_6",
        "kling_motion_2_6", "kling_2_5_turbo", "kling_2_1", "kling_2_1_master",
        "kling_2_0_master", "kling_1_6", "kling_1_5", "kling_1_0",
    )
    for model_id in degraded:
        cap = mc.get_capability(model_id)
        assert cap.character.visual_reference.visual_mode == mc.VisualReferenceMode.DEGRADED_SINGLE_IMAGE, model_id
        assert cap.character.visual_reference.max_count == 1, model_id
    lip_sync_cap = mc.get_capability("kling_lip_sync")
    assert lip_sync_cap.character.visual_reference.visual_mode == mc.VisualReferenceMode.UNSUPPORTED


def test_runway_models_unsupported_despite_confusable_names():
    # runway_seedance2*/runway_gemini_omni_flash go through Runway's own
    # _call_runway endpoint (which never reads reference_images), NOT the
    # native seedance_*/gemini_omni_flash paths that really are
    # REAL_MULTI_IMAGE - their names must not be mistaken for the same
    # capability as their differently-provider-routed namesakes.
    confusable = ("runway_seedance2", "runway_seedance2_fast", "runway_seedance2_mini", "runway_gemini_omni_flash")
    for model_id in confusable:
        cap = mc.get_capability(model_id)
        assert cap.character.visual_reference.visual_mode == mc.VisualReferenceMode.UNSUPPORTED, model_id
    # Confirm their real namesakes are the opposite classification, so a
    # future refactor can't silently make this distinction disappear.
    for model_id in ("seedance_2_fast", "seedance_2_0", "seedance_1_5_pro", "gemini_omni_flash"):
        cap = mc.get_capability(model_id)
        assert cap.character.visual_reference.visual_mode == mc.VisualReferenceMode.REAL_MULTI_IMAGE, model_id


def test_wan_2_6_classified_unsupported_for_realistic_character_only_flow():
    # _call_wan's reference_images[0] fallback for wan_2_6 only executes
    # when has_media is already True (start_image/end_image/input_video
    # present) - has_media itself never considers reference_images. In the
    # realistic "attach only a Character/Object reference" flow this model
    # drops the image exactly like a fully unsupported one, so it is
    # classified UNSUPPORTED rather than claiming support that doesn't hold
    # for the actual gated user flow.
    cap = mc.get_capability("wan_2_6")
    assert cap.character.visual_reference.visual_mode == mc.VisualReferenceMode.UNSUPPORTED


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
    assert entry["character"]["visual_reference"]["visual_mode"] == "degraded_single_image"
    assert isinstance(entry["durations"], list)
    assert isinstance(entry["pricing"]["voice_control"]["unreachable"], bool)
