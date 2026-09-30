"""Required parity test for Phase 1 Batch 1 (see
/root/.claude/plans/splendid-moseying-starlight.md, "Tests for Batch 1" -
this test is explicitly called out as required, not optional).

main.image_model_features() was repointed to read from
services.model_capabilities instead of IMAGE_MODEL_FEATURES directly. This
test independently reimplements the exact pre-repoint algorithm (a frozen
copy, not a call into the repointed function) and asserts it produces
identical output to the live, repointed function for every model in
IMAGE_MODEL_FEATURES - this is what licenses calling the repoint
behavior-preserving rather than merely asserting it.
"""
import re

import main


def _old_image_model_features(frontend_model: str) -> dict:
    """Frozen copy of image_model_features()'s body exactly as it existed
    before the Phase 1 Batch 1 repoint (reading IMAGE_MODEL_FEATURES
    directly)."""
    normalized = (frontend_model or "").strip().lower().replace("-", "_")
    features = main.IMAGE_MODEL_FEATURES.get(normalized) or re.sub(r"_0$", "", normalized)
    if isinstance(features, str):
        features = main.IMAGE_MODEL_FEATURES.get(features)
    if not features:
        features = {"character": False, "object": False, "seed": False}
    return {
        "character": bool(features.get("character")),
        "object": bool(features.get("object")),
        "seed": bool(features.get("seed")),
    }


def test_every_image_model_matches_pre_repoint_behavior():
    for model_id in main.IMAGE_MODEL_FEATURES:
        old = _old_image_model_features(model_id)
        new = main.image_model_features(model_id)
        assert new == old, f"{model_id}: old={old} new={new}"


def test_hyphenated_and_uppercase_variants_still_match():
    samples = ["Nano-Banana-Pro", "SEEDREAM-5-0-PRO", "Grok", "gpt-image-1"]
    for raw in samples:
        old = _old_image_model_features(raw)
        new = main.image_model_features(raw)
        assert new == old, f"{raw}: old={old} new={new}"


def test_unknown_model_still_defaults_to_all_false():
    old = _old_image_model_features("totally_unknown_model_xyz")
    new = main.image_model_features("totally_unknown_model_xyz")
    assert old == new == {"character": False, "object": False, "seed": False}


def test_empty_and_none_input_still_match():
    for raw in ("", None):
        old = _old_image_model_features(raw)
        new = main.image_model_features(raw)
        assert new == old == {"character": False, "object": False, "seed": False}
