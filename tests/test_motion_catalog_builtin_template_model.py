"""Regression test for the Phase 1 Batch 7 correction (see
/root/.claude/plans/splendid-moseying-starlight.md): the Motion Catalog is
a dedicated fixed-model workflow that must always route to
kling_motion_3_0, never fall back to kling_o3_omni.

prostudio_builtin_video_template_slots() (main.py) is the backend source
for the built-in video templates catalog - the reference-video-driven
templates users actually see in Pro Studio (as opposed to
prostudio_video_templates_from_env(), which already hardcoded
kling_motion_3_0 correctly and was never the buggy source). Before this
fix it served preferred_model="kling_o3_omni" for every non-effect
template, which is exactly what made the frontend's now-also-fixed
templatePreferredModel() always resolve to kling_o3_omni - a drift from
its own env-sourced sibling function, not a deliberate product choice.
"""
import main


def test_builtin_video_templates_use_kling_motion_3_0_as_preferred_model():
    templates = main.prostudio_builtin_video_template_slots()
    assert templates, "expected at least one built-in video template slot to be discovered"
    non_effect = [t for t in templates if not t.get("is_kling_effect")]
    assert non_effect, "expected at least one non-effect (Motion Catalog) template"
    for template in non_effect:
        assert template["preferred_model"] == "kling_motion_3_0", template["id"]
        assert template["models"] == ["kling_motion_3_0"], template["id"]


def test_builtin_kling_effects_templates_still_use_kling_effects_model():
    # The separate Kling Effects catalog (task #94) is unaffected by this
    # correction - it was never the buggy branch and must keep its own
    # fixed model.
    templates = main.prostudio_builtin_video_template_slots()
    effects = [t for t in templates if t.get("is_kling_effect")]
    for template in effects:
        assert template["preferred_model"] == "kling_effects", template["id"]
        assert template["models"] == ["kling_effects"], template["id"]


def test_builtin_and_env_video_templates_agree_on_the_motion_catalog_model():
    # prostudio_video_templates_from_env() always hardcoded kling_motion_3_0
    # (see main.py) - the two sources of the same catalog must never
    # disagree on its fixed model again.
    import json
    import os

    os.environ["VIDEO_TEMPLATES_JSON"] = json.dumps({
        "templates": [
            {"id": "env_test_template", "title": "Env Test", "reference_video": "https://example.com/ref.mp4"},
        ]
    })
    try:
        env_templates = main.prostudio_video_templates_from_env()
    finally:
        del os.environ["VIDEO_TEMPLATES_JSON"]
    assert env_templates, "expected the env-sourced template to parse"
    assert env_templates[0]["preferred_model"] == "kling_motion_3_0"

    builtin_templates = main.prostudio_builtin_video_template_slots()
    builtin_non_effect = [t for t in builtin_templates if not t.get("is_kling_effect")]
    assert builtin_non_effect
    assert {t["preferred_model"] for t in builtin_non_effect} == {"kling_motion_3_0"}
