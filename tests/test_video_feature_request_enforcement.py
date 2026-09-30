"""Phase 1 Batch 5 of the Pro Studio master remediation plan (see
/root/.claude/plans/splendid-moseying-starlight.md, roadmap step 5): backend
enforcement for video start_image/end_image/character/object visual
references.

Prior to this batch, _build_video_payload passed start_image, end_image,
characterReferences, and objectReferences straight through from the raw
request regardless of whether the target model actually supports them -
unlike the boolean flags (native_audio, motion_control, avatar, lip_sync,
etc.) which were already gated via _gated_flag(key). A direct API call
(bypassing the frontend's own best-effort, fail-open slicing) could reach a
provider with a reference image it doesn't support.

This batch:
1. Gates start_image/end_image and characterReferences/objectReferences in
   _build_video_payload the same gating philosophy the existing boolean
   flags already use via _gated_flag(key) - never touching
   characterId/characterName/objectId/objectName, the text-only
   conditioning axis, which must always flow (every video model's
   text_conditioning is True today).
2. Adds main.validate_video_feature_request(), mirroring
   validate_image_feature_request()'s exact contract (Optional[dict], None
   on success, {"ok": False, "type": "video", "error": ..., "model": ...}
   on failure), wired into public_prostudio_generate's video block as the
   first statement - before calculate_generation_price - so an unsupported
   visual reference image (character/object reference, or a start/end
   frame) is rejected with HTTP 400 before the request is priced or
   dispatched.

Fix (user-requested correction to the original Batch 5 pass): the first
version only validated character/object references, silently relying on
_build_video_payload's own stripping for start_image/end_image, and that
stripping itself read VIDEO_MODEL_CONFIG directly instead of the central
ModelCapability registry. Both gaps are closed here:
- validate_video_feature_request() now also rejects an unsupported
  start_image (checked from both video_options.start_image and the
  top-level payload.start_image, matching exactly what
  _build_video_payload itself accepts) or end_image before pricing.
- Both validate_video_feature_request() and _build_video_payload's gating
  now read the single shared model_capabilities.video_frame_support()
  helper - the same registry fields (ModelCapability.start_frame/
  end_frame) the frontend's currentVideoConfig() repoint and
  _kling_capability_supports_end_frame() already read - so request-time
  validation and payload-level defense-in-depth can never drift from each
  other or from VIDEO_MODEL_CONFIG.

These tests prove: the gating strips only visual reference images (never
text-only fields) for unsupported models; the validator rejects exactly
those same cases (character/object references AND start/end frames) and no
others; the request-path wiring runs validation before pricing; and
_build_video_payload's frame gating and the request-time validator derive
from the same registry-backed source.
"""
import re

import main  # noqa: F401 - import-time side effect populates the capability registry
import services.video_router as video_router
from services import model_capabilities as mc


# Batch 2's audited REAL_MULTI_IMAGE/DEGRADED_SINGLE_IMAGE model sets,
# reused here (not re-derived) to build accept/reject expectations for
# character/object visual reference support - both axes are identical for
# every video model today (register_video_models() computes character= and
# object= from the same _video_character_capability(model_id) call).
REAL_MULTI_IMAGE_MODELS = {
    "seedance_2_fast", "seedance_2_0", "seedance_1_5_pro",
    "heygen_v3_video_agent", "heygen_cinematic_avatar", "gemini_omni_flash",
}
DEGRADED_SINGLE_IMAGE_KLING_SAMPLE = {"kling_2_6", "kling_3_0", "kling_1_6"}
UNSUPPORTED_SAMPLE = {"sora_2", "sora_2_pro", "veo_3_1", "runway_gen4_5", "kling_lip_sync", "grok_video"}


def test_video_character_object_visual_reference_supported_matches_batch2_audit():
    for model_id in REAL_MULTI_IMAGE_MODELS | DEGRADED_SINGLE_IMAGE_KLING_SAMPLE:
        support = mc.video_character_object_visual_reference_supported(model_id)
        assert support["character"] is True, f"{model_id}: character visual reference should be supported"
        assert support["object"] is True, f"{model_id}: object visual reference should be supported"
    for model_id in UNSUPPORTED_SAMPLE:
        support = mc.video_character_object_visual_reference_supported(model_id)
        assert support["character"] is False, f"{model_id}: character visual reference should be unsupported"
        assert support["object"] is False, f"{model_id}: object visual reference should be unsupported"


def test_video_character_object_visual_reference_supported_fails_closed_for_unknown_model():
    assert mc.video_character_object_visual_reference_supported("not_a_real_model") == {
        "character": False, "object": False,
    }


def test_video_character_object_visual_reference_supported_fails_closed_for_non_video_model():
    # An image model id must not accidentally read as "supported" here.
    assert mc.video_character_object_visual_reference_supported("gpt_image_2_5_sunburst") == {
        "character": False, "object": False,
    }


def _video_payload(model, **video_options):
    return {
        "prompt": "a test prompt",
        "video_options": {"model": model, **video_options},
        "_visual_prompt_built": True,
    }


def test_build_video_payload_strips_visual_references_for_unsupported_model():
    payload = _video_payload(
        "sora_2",
        characterReferences=["https://x.test/char.png"],
        objectReferences=["https://x.test/obj.png"],
    )
    body = video_router._build_video_payload("sora_2", "a test prompt", payload)
    assert body["characterReferences"] == []
    assert body["objectReferences"] == []
    assert body["reference_images"] == []


def test_build_video_payload_keeps_visual_references_for_supported_model():
    payload = _video_payload(
        "seedance_2_fast",
        characterReferences=["https://x.test/char.png"],
        objectReferences=["https://x.test/obj.png"],
    )
    body = video_router._build_video_payload("seedance_2_fast", "a test prompt", payload)
    assert body["characterReferences"] == ["https://x.test/char.png"]
    assert body["objectReferences"] == ["https://x.test/obj.png"]
    assert set(body["reference_images"]) == {"https://x.test/char.png", "https://x.test/obj.png"}


def test_build_video_payload_never_strips_text_only_character_object_fields():
    # The Sora-style regression: text conditioning (name/id) must survive
    # even though sora_2 cannot accept a reference IMAGE at all.
    payload = _video_payload(
        "sora_2",
        characterId="char_1",
        characterName="Bob",
        objectId="obj_1",
        objectName="Red hat",
    )
    body = video_router._build_video_payload("sora_2", "a test prompt", payload)
    assert body["characterId"] == "char_1"
    assert body["characterName"] == "Bob"
    assert body["objectId"] == "obj_1"
    assert body["objectName"] == "Red hat"


def test_build_video_payload_gates_start_end_image_per_model():
    # sora_2: start_image True, end_image False (per VIDEO_MODEL_CONFIG).
    payload = _video_payload("sora_2", start_image="https://x.test/s.png", end_image="https://x.test/e.png")
    body = video_router._build_video_payload("sora_2", "a test prompt", payload)
    assert body["start_image"] == "https://x.test/s.png"
    assert body["end_image"] == ""


def test_build_video_payload_strips_start_image_for_model_without_it():
    # kling_o3_edit: start_image False, end_image False.
    payload = _video_payload("kling_o3_edit", start_image="https://x.test/s.png", end_image="https://x.test/e.png")
    body = video_router._build_video_payload("kling_o3_edit", "a test prompt", payload)
    assert body["start_image"] == ""
    assert body["end_image"] == ""


def test_validate_video_feature_request_accepts_supported_visual_reference():
    payload = _video_payload("seedance_2_fast", characterReferences=["https://x.test/char.png"])
    assert main.validate_video_feature_request(payload) is None


def test_validate_video_feature_request_rejects_unsupported_character_reference():
    payload = _video_payload("sora_2", characterReferences=["https://x.test/char.png"])
    error = main.validate_video_feature_request(payload)
    assert error == {
        "ok": False, "type": "video",
        "error": "Selected model does not support character reference images",
        "model": "sora_2",
    }


def test_validate_video_feature_request_rejects_unsupported_object_reference():
    payload = _video_payload("runway_gen4_5", objectReferences=["https://x.test/obj.png"])
    error = main.validate_video_feature_request(payload)
    assert error == {
        "ok": False, "type": "video",
        "error": "Selected model does not support object reference images",
        "model": "runway_gen4_5",
    }


def test_validate_video_feature_request_never_rejects_text_only_mention():
    # The required regression per the plan text: "a text-only character/
    # object mention is never rejected" - sora_2 cannot take a reference
    # image, but naming a saved character/object by id/name must pass.
    payload = _video_payload("sora_2", characterId="char_1", characterName="Bob", objectId="obj_1", objectName="Red hat")
    assert main.validate_video_feature_request(payload) is None


def test_validate_video_feature_request_rejects_reference_for_unknown_model():
    # Mirrors validate_image_feature_request's own fail-closed behavior:
    # image_character_object_seed() (and this batch's video counterpart)
    # both return all-False support for a model id they can't resolve, so a
    # visual reference image attached to an unknown model is rejected the
    # same way it would be for a known model that genuinely lacks support.
    payload = _video_payload("not_a_real_model", characterReferences=["https://x.test/char.png"])
    error = main.validate_video_feature_request(payload)
    assert error is not None
    assert error["ok"] is False
    assert error["model"] == "not_a_real_model"


def test_validate_video_feature_request_passes_unknown_model_with_no_references():
    # An unknown model with no visual reference attached has nothing to
    # reject - text-only fields and the pricing path fail on their own,
    # elsewhere, for a genuinely unknown model.
    payload = _video_payload("not_a_real_model", characterId="char_1", characterName="Bob")
    assert main.validate_video_feature_request(payload) is None


def test_validate_video_feature_request_ignores_video_with_no_references():
    payload = _video_payload("sora_2")
    assert main.validate_video_feature_request(payload) is None


# --- Fix regression tests: start/end frame validation ----------------------

def test_video_frame_support_matches_video_model_config():
    # Parity test: the shared registry helper must agree with
    # VIDEO_MODEL_CONFIG's own start_image/end_image booleans for every
    # video model - the same guarantee test_kling_end_frame_unification.py
    # already proves for end_frame alone; this covers start_frame too and
    # every provider, not just Kling.
    for model_id, config in video_router.VIDEO_MODEL_CONFIG.items():
        expected = {
            "start_frame": bool(config.get("start_image")),
            "end_frame": bool(config.get("end_image")),
        }
        actual = mc.video_frame_support(model_id)
        assert actual == expected, f"{model_id}: VIDEO_MODEL_CONFIG says {expected}, registry says {actual}"


def test_video_frame_support_fails_closed_for_unknown_model():
    assert mc.video_frame_support("not_a_real_model") == {"start_frame": False, "end_frame": False}


def test_validate_video_feature_request_rejects_unsupported_end_image_before_pricing():
    # sora_2: start_image True, end_image False.
    payload = _video_payload("sora_2", end_image="https://x.test/e.png")
    error = main.validate_video_feature_request(payload)
    assert error == {
        "ok": False, "type": "video",
        "error": "Selected model does not support an end frame image",
        "model": "sora_2",
    }


def test_validate_video_feature_request_rejects_unsupported_start_image_before_pricing():
    # kling_o3_edit: start_image False, end_image False.
    payload = _video_payload("kling_o3_edit", start_image="https://x.test/s.png")
    error = main.validate_video_feature_request(payload)
    assert error == {
        "ok": False, "type": "video",
        "error": "Selected model does not support a start frame image",
        "model": "kling_o3_edit",
    }


def test_validate_video_feature_request_accepts_supported_start_and_end_frames():
    # kling_2_6: start_image True, end_image True.
    payload = _video_payload("kling_2_6", start_image="https://x.test/s.png", end_image="https://x.test/e.png")
    assert main.validate_video_feature_request(payload) is None


def test_validate_video_feature_request_checks_top_level_start_image_too():
    # _build_video_payload accepts start_image from either video_options or
    # the top-level payload (opts.get("start_image") or
    # payload.get("start_image")) - the validator must check the exact same
    # two sources, not just video_options.
    payload = {
        "prompt": "a test prompt",
        "video_options": {"model": "kling_o3_edit"},
        "start_image": "https://x.test/s.png",
        "_visual_prompt_built": True,
    }
    error = main.validate_video_feature_request(payload)
    assert error == {
        "ok": False, "type": "video",
        "error": "Selected model does not support a start frame image",
        "model": "kling_o3_edit",
    }


def test_validate_video_feature_request_accepts_top_level_start_image_when_supported():
    payload = {
        "prompt": "a test prompt",
        "video_options": {"model": "sora_2"},
        "start_image": "https://x.test/s.png",
        "_visual_prompt_built": True,
    }
    assert main.validate_video_feature_request(payload) is None


def test_build_video_payload_and_validator_derive_from_same_registry_capability():
    # The fix's core guarantee: _build_video_payload's frame gating
    # (_video_capability_supports_start_frame/_video_capability_supports_end_frame)
    # and validate_video_feature_request's own check both read
    # model_capabilities.video_frame_support() - assert they can never
    # disagree, across every video model, not just the spot-checked cases
    # above.
    for model_id in video_router.VIDEO_MODEL_CONFIG:
        support = mc.video_frame_support(model_id)
        assert video_router._video_capability_supports_start_frame(model_id) == support["start_frame"]
        assert video_router._video_capability_supports_end_frame(model_id) == support["end_frame"]

        payload = _video_payload(model_id, start_image="https://x.test/s.png", end_image="https://x.test/e.png")
        body = video_router._build_video_payload(model_id, "a test prompt", payload)
        error = main.validate_video_feature_request(payload)

        start_stripped = body["start_image"] == ""
        end_stripped = body["end_image"] == ""
        assert start_stripped == (not support["start_frame"]), f"{model_id}: start_image stripping disagrees with registry"
        assert end_stripped == (not support["end_frame"]), f"{model_id}: end_image stripping disagrees with registry"
        if not support["start_frame"] or not support["end_frame"]:
            assert error is not None, f"{model_id}: validator should reject when either frame is unsupported"
        else:
            assert error is None, f"{model_id}: validator should accept when both frames are supported"


def test_public_prostudio_generate_runs_video_validation_before_pricing():
    # Grep-based wiring check (same style as Batch 3's call-site tests):
    # validate_video_feature_request must run, and be checked, before
    # calculate_generation_price inside the video mode block - mirroring
    # the image block's own validate_image_feature_request -> pricing order.
    source = open(main.__file__, encoding="utf-8").read()
    match = re.search(
        r'if mode == "video":\s*\n\s*feature_error = validate_video_feature_request\(payload\)\s*\n'
        r'\s*if feature_error:\s*\n\s*return JSONResponse\(feature_error, status_code=400\)\s*\n'
        r'\s*\n\s*telegram_id = int\(payload\.get\("telegram_id"\) or 0\)\s*\n'
        r'\s*cost_estimate = calculate_generation_price\(payload\)',
        source,
    )
    assert match, "validate_video_feature_request must run and be checked before calculate_generation_price in the video mode block"
