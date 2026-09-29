"""Regression tests for the Pro Studio A-Z audit's Phase 1 billing fixes.

Prior to this fix, _build_video_payload forwarded 8 of 9 Kling capability
booleans (everything but `sound`) to both the real provider request and the
pricing-tier selector without checking the model's own VIDEO_MODEL_CONFIG -
so a caller could request e.g. `multi_element_editing: True` on kling_1_6
(whose config explicitly declares that capability False) and get billed at
the higher tier for a capability the model never actually receives.

Separately, estimate_video_generation_cost priced non-Kling video duration
and resolution from raw, unclamped values while the real request
(_build_video_payload) clamps them to the model's declared durations/
resolutions - so an out-of-range value inflated the price relative to what
was actually generated.
"""
import services.video_router as video_router


def test_kling_capability_flags_are_gated_against_model_config():
    # kling_1_6's own VIDEO_MODEL_CONFIG entry declares multi_element_editing
    # and video_extension as unsupported (False).
    payload = {
        "model": "kling_1_6",
        "video_options": {
            "model": "kling_1_6",
            "duration": 10,
            "resolution": "1080p",
            "multi_element_editing": True,
            "video_extension": True,
        },
        "prompt": "test",
    }
    body = video_router._build_video_payload("kling_1_6", "test", payload)
    assert body["multi_element_editing"] is False
    assert body["video_extension"] is False
    # The pricing-tier selector must therefore never see the premium variant.
    assert video_router._kling_cost_variant("kling_1_6", body) == "standard"


def test_kling_capability_flags_pass_through_when_model_supports_them():
    payload = {
        "model": "kling_o3_omni",
        "video_options": {"model": "kling_o3_omni", "native_audio": True},
        "prompt": "test",
    }
    body = video_router._build_video_payload("kling_o3_omni", "test", payload)
    assert body["native_audio"] is True


def test_video_pricing_clamps_out_of_range_duration_and_resolution():
    # seedance_2_fast's real durations are [4..15] and resolutions are
    # ["720p", "480p"]; an out-of-range request must be clamped the same
    # way _build_video_payload clamps it, not priced at the raw value.
    unclamped = video_router.estimate_video_generation_cost({
        "model": "seedance_2_fast",
        "video_options": {"model": "seedance_2_fast", "duration": 999, "resolution": "9999p"},
    })
    clamped_equivalent = video_router.estimate_video_generation_cost({
        "model": "seedance_2_fast",
        "video_options": {"model": "seedance_2_fast", "duration": 4, "resolution": "720p"},
    })
    assert unclamped["credits"] == clamped_equivalent["credits"]
    # Sanity: this must NOT equal what the raw (unclamped) duration*rate
    # would have produced (15 * 18 = 270), proving the fix actually clamps.
    assert unclamped["credits"] != 270
