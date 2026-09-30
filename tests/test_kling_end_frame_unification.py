"""Phase 1 Batch 3 (part 2) of the Pro Studio master remediation plan (see
/root/.claude/plans/splendid-moseying-starlight.md, roadmap step 3): Kling
end-frame unification.

Dedicated research traced all 17 Kling models against the three previously
independent decision points in services/video_router.py's _call_kling
(the legacy hardcoded id set at the is_legacy_model branch, the ungated
mode-only check in the omni branch, and _kling_supports_last_frame() in the
final else branch) and found they currently agree for every model under
default provider_model values - but only by manual diligence, since none of
the three was actually derived from VIDEO_MODEL_CONFIG/the capability
registry. All four call sites (the legacy branch's one, the omni branch's
one, and the else branch's two) were repointed to
_kling_capability_supports_end_frame(model_id), a single function reading
services.model_capabilities' end_frame flag - itself a direct mirror of
VIDEO_MODEL_CONFIG["end_image"].

This test asserts _kling_capability_supports_end_frame() returns exactly
the value the research's MATCH table found for every one of the 17 Kling
models, licensing the refactor as behavior-preserving (not merely asserted -
proven against the same per-model ground truth the research established).
_kling_supports_last_frame() and the legacy hardcoded id set are still
present in the source (additive-only migration - see model_capabilities.py's
comment above the new function) but are no longer called from any of the
four sites; a grep-based test confirms that too.
"""
import re

import main  # noqa: F401 - import-time side effect populates the capability registry
import services.video_router as video_router
from services import model_capabilities as mc


# model_id -> expected _kling_capability_supports_end_frame() result, taken
# directly from the research's confirmed MATCH table (every model currently
# agrees with VIDEO_MODEL_CONFIG["end_image"] across all three old sites).
EXPECTED_END_FRAME_SUPPORT = {
    "kling_3_0_turbo": False,
    "kling_3_0": True,
    "kling_motion_3_0": False,
    "kling_lip_sync": False,
    "kling_effects": False,
    "kling_o3_omni": True,
    "kling_o3_edit": False,
    "kling_o1": True,
    "kling_2_6": True,
    "kling_motion_2_6": False,
    "kling_2_5_turbo": True,
    "kling_2_1": True,
    "kling_2_1_master": False,
    "kling_2_0_master": False,
    "kling_1_6": True,
    "kling_1_5": True,
    "kling_1_0": False,
}


def test_every_kling_model_covered_by_expectations():
    kling_ids = {mid for mid, cap in mc.MODEL_CAPABILITIES.items() if cap.provider == "kling"}
    assert kling_ids == set(EXPECTED_END_FRAME_SUPPORT), (
        "EXPECTED_END_FRAME_SUPPORT must cover exactly the Kling models "
        f"in the registry; missing={kling_ids - set(EXPECTED_END_FRAME_SUPPORT)} "
        f"extra={set(EXPECTED_END_FRAME_SUPPORT) - kling_ids}"
    )


def test_kling_capability_supports_end_frame_matches_research_table():
    for model_id, expected in EXPECTED_END_FRAME_SUPPORT.items():
        actual = video_router._kling_capability_supports_end_frame(model_id)
        assert actual is expected, f"{model_id}: expected {expected}, got {actual}"


def test_end_frame_flag_mirrors_video_model_config_end_image():
    # The registry's end_frame is a direct transcription of
    # VIDEO_MODEL_CONFIG["end_image"] (Batch 1's register_video_models) -
    # confirm the new unification function agrees with that source exactly,
    # not just with its own hardcoded expectations table above.
    for model_id, config in video_router.VIDEO_MODEL_CONFIG.items():
        if config.get("provider") != "kling":
            continue
        expected = bool(config.get("end_image"))
        actual = video_router._kling_capability_supports_end_frame(model_id)
        assert actual == expected, f"{model_id}: VIDEO_MODEL_CONFIG says {expected}, registry-backed function says {actual}"


def test_unknown_model_id_does_not_support_end_frame():
    assert video_router._kling_capability_supports_end_frame("not_a_real_model") is False


def test_old_kling_supports_last_frame_kept_but_unused_additive_only():
    # Old mechanisms stay in the source per the additive-only migration rule
    # (not deleted)...
    assert hasattr(video_router, "_kling_supports_last_frame")
    source = open(video_router.__file__, encoding="utf-8").read()
    definition_line = next(
        i for i, line in enumerate(source.splitlines())
        if re.match(r"def _kling_supports_last_frame\(", line)
    )
    # ...but no longer called anywhere else in the file (only its own def).
    calls = [
        i for i, line in enumerate(source.splitlines())
        if "_kling_supports_last_frame(" in line and i != definition_line
    ]
    assert calls == [], f"_kling_supports_last_frame() should have no remaining call sites, found at lines {calls}"


def test_legacy_hardcoded_end_frame_id_set_no_longer_gates_image_tail():
    # The old hardcoded {"kling_2_1","kling_1_6","kling_1_5"} hand-picked set
    # must no longer appear as the guard on kling_body["image_tail"] - the
    # single registry-backed function does instead.
    source = open(video_router.__file__, encoding="utf-8").read()
    assert 'model_id in {"kling_2_1", "kling_1_6", "kling_1_5"}' not in source
    assert "_kling_capability_supports_end_frame(model_id)" in source
