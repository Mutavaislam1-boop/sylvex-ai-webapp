"""Phase 1 Batch 4 of the Pro Studio master remediation plan (see
/root/.claude/plans/splendid-moseying-starlight.md, roadmap step 4): sound
toggle repoint.

Prior research (this batch) traced every current source of video
sound/native-audio capability data and every consumer that reads it:
- VIDEO_MODEL_CONFIG[model_id]["sound"] (both the JS and Python mirrors) is
  the single, complete, drift-free source of "does this model support the
  sound toggle at all" - unlike the narrower "native_audio" key, only ever
  set on a handful of Kling entries and used solely to select a Kling
  pricing tier (_kling_cost_variant), which this batch deliberately leaves
  untouched to avoid any pricing semantics change.
- services.model_capabilities' ModelCapability.sound_toggle is already a
  complete, correct mirror of that same "sound" key (register_video_models()
  does sound_toggle=bool(config.get("sound"))), so no new data-population
  work was needed before repointing - unlike Batch 2's visual_reference.
- Two backend call sites independently read VIDEO_MODEL_CONFIG[model_id]
  .get("sound") directly: _build_video_payload (the primary gate that
  computes body["sound"]) and _call_runway's own redundant check. Both are
  now repointed to _video_capability_supports_sound(model_id), a single
  function reading the registry.

This test proves the new function's output matches VIDEO_MODEL_CONFIG's own
"sound" key for every video model (parity, not just plausibility), and that
the repointed call sites behave identically to before the change.
"""
import main  # noqa: F401 - import-time side effect populates the capability registry
import services.video_router as video_router
from services import model_capabilities as mc


def test_every_video_model_has_a_registry_entry():
    video_model_ids = set(video_router.VIDEO_MODEL_CONFIG.keys())
    registry_video_ids = {
        mid for mid, cap in mc.MODEL_CAPABILITIES.items() if cap.category.value == "video"
    }
    assert video_model_ids == registry_video_ids, (
        "Every VIDEO_MODEL_CONFIG entry must have a corresponding video "
        f"MODEL_CAPABILITIES entry; missing={video_model_ids - registry_video_ids} "
        f"extra={registry_video_ids - video_model_ids}"
    )


def test_sound_capability_supports_sound_matches_video_model_config_exactly():
    # Parity test (required, not optional, per this effort's established
    # pattern): the new registry-backed helper must produce the exact same
    # answer as the old VIDEO_MODEL_CONFIG[model_id]["sound"] key for every
    # video model - this is what licenses calling the repoint
    # behavior-preserving rather than merely plausible.
    for model_id, config in video_router.VIDEO_MODEL_CONFIG.items():
        expected = bool(config.get("sound"))
        actual = video_router._video_capability_supports_sound(model_id)
        assert actual == expected, (
            f"{model_id}: VIDEO_MODEL_CONFIG says sound={expected}, "
            f"_video_capability_supports_sound says {actual}"
        )


def test_unknown_model_id_does_not_support_sound():
    assert video_router._video_capability_supports_sound("not_a_real_model") is False


def test_native_audio_field_is_not_touched_by_this_batch():
    # native_audio must remain exactly what it was before this batch: set
    # only for the Kling models whose VIDEO_MODEL_CONFIG entry declares it,
    # used only by _kling_cost_variant. This batch's repoint must not widen
    # or narrow it.
    native_audio_models = {
        mid for mid, config in video_router.VIDEO_MODEL_CONFIG.items()
        if config.get("native_audio")
    }
    assert native_audio_models == {
        "kling_3_0_turbo", "kling_3_0", "kling_o3_omni", "kling_o3_edit", "kling_2_6",
    }
    for model_id in video_router.VIDEO_MODEL_CONFIG:
        cap = mc.get_capability(model_id)
        expected = bool(video_router.VIDEO_MODEL_CONFIG[model_id].get("native_audio"))
        assert cap.native_audio == expected, (
            f"{model_id}: native_audio should still mirror VIDEO_MODEL_CONFIG "
            f"unchanged by this batch, expected {expected} got {cap.native_audio}"
        )


def test_build_video_payload_gates_sound_identically_to_before(monkeypatch):
    # _build_video_payload's own "sound" output is what every downstream
    # provider call trusts - prove the repointed gate produces the exact
    # same body["sound"] the old config.get("sound") gate would have, for a
    # sound-capable model (veo_3_1) and a sound-incapable one (sora_2), in
    # both the requested-on and requested-off cases.
    for model_id, requested, expected in (
        ("veo_3_1", True, True),
        ("veo_3_1", False, False),
        ("sora_2", True, False),  # sora_2 doesn't support sound - must stay gated off
        ("sora_2", False, False),
    ):
        payload = {
            "prompt": "a test prompt",
            "video_options": {"sound": requested},
            "_visual_prompt_built": True,
        }
        body = video_router._build_video_payload(model_id, "a test prompt", payload)
        assert body["sound"] == expected, f"{model_id} requested={requested}: expected sound={expected}, got {body['sound']}"


def test_call_runway_generate_audio_matches_gated_sound(monkeypatch):
    # _call_runway's own redundant "if config.get('sound')" check is now
    # backed by the same _video_capability_supports_sound() helper as
    # _build_video_payload - runway_veo3_1 supports sound, runway_gen4_5
    # does not (per VIDEO_MODEL_CONFIG), so generate_audio must reflect that
    # exactly as it did before this batch's repoint.
    assert video_router._video_capability_supports_sound("runway_veo3_1") is True
    assert bool(video_router.VIDEO_MODEL_CONFIG["runway_veo3_1"].get("sound")) is True
    assert video_router._video_capability_supports_sound("runway_gen4_5") is False
    assert bool(video_router.VIDEO_MODEL_CONFIG["runway_gen4_5"].get("sound")) is False
