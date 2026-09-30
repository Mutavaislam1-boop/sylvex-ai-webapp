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
1. Gates start_image/end_image in _build_video_payload the same way the
   existing boolean flags are (config.get("start_image")/["end_image"]).
2. Gates the characterReferences/objectReferences that actually feed
   reference_images (what every _call_<provider> function consumes) on the
   new model_capabilities.video_character_object_visual_reference_supported()
   helper - never touching characterId/characterName/objectId/objectName,
   the text-only conditioning axis, which must always flow (every video
   model's text_conditioning is True today).
3. Adds main.validate_video_feature_request(), mirroring
   validate_image_feature_request()'s exact contract (Optional[dict], None
   on success, {"ok": False, "type": "video", "error": ..., "model": ...}
   on failure), wired into public_prostudio_generate's video block as the
   first statement - before calculate_generation_price - so an unsupported
   visual reference image is rejected with HTTP 400 before the request is
   priced or dispatched.

These tests prove: the gating strips only visual reference images for
unsupported models (never text-only fields); the validator rejects exactly
those same cases and no others; and the request-path wiring runs validation
before pricing.
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
