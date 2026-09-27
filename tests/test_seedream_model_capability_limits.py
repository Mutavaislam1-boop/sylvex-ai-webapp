"""Every BytePlus Seedream variant uses the provider's `image` input field,
but each model has a model-aware cap on references. These tests cover the
shared capability matrix, model-aware body construction, and the fair
round-robin merge of user/Character/Object references."""
import base64

import main


def test_every_seedream_variant_has_capability_entry():
    for key in main.SEEDREAM_MODEL_VARIANTS:
        caps = main.seedream_capabilities(key, main.BYTEPLUS_SEEDREAM_MODEL_MAP[key])
        assert caps is not None, f"{key} must have an image reference capability"
        assert caps["max_references"] >= 1
        assert caps["reference_param"] == "image"


def test_seedream_5_0_pro_uses_official_image_field():
    caps = main.seedream_capabilities("", main.BYTEPLUS_SEEDREAM_MODEL_MAP["seedream_5_0_pro"])
    assert caps["reference_param"] == "image"
    assert caps["allow_inline_base64"] is True


def test_non_pro_seedream_variants_use_image_field():
    for key in ("seedream_4_0", "seedream_4_5", "seedream_5_0_lite", "seedream_5_0"):
        caps = main.seedream_capabilities("", main.BYTEPLUS_SEEDREAM_MODEL_MAP[key])
        assert caps["reference_param"] == "image"
        assert caps["allow_inline_base64"] is True


def test_byteplus_seedream_body_sends_pro_references_under_image():
    model = main.BYTEPLUS_SEEDREAM_MODEL_MAP["seedream_5_0_pro"]
    body = main.byteplus_seedream_body(
        model, "a portrait", reference_images=["https://example.com/a.png"], size="1:1",
    )
    assert "image" in body
    assert "image_urls" not in body
    assert body["image"] == "https://example.com/a.png"


def test_byteplus_seedream_body_pro_passes_inline_base64_references():
    model = main.BYTEPLUS_SEEDREAM_MODEL_MAP["seedream_5_0_pro"]
    png_b64 = base64.b64encode(b"fake-png-bytes").decode("ascii")
    body = main.byteplus_seedream_body(
        model, "a portrait",
        reference_images=[f"data:image/png;base64,{png_b64}", "https://example.com/a.png"],
        size="1:1",
    )
    assert len(body["image"]) == 2
    assert body["image"][0] == f"data:image/png;base64,{png_b64}"
    assert "https://example.com/a.png" in body["image"]


def test_byteplus_seedream_body_pro_passes_through_sylvex_hosted_urls_unchanged():
    # SYLVEX's own signed media URLs (WEBAPP_URL/R2) are already publicly
    # fetchable as-is (see services/media_access.py), so they should remain
    # URLs in the provider's input list.
    model = main.BYTEPLUS_SEEDREAM_MODEL_MAP["seedream_5_0_pro"]
    signed_url = "https://api.sylvex.ai/api/public/storage/generated/x.png?media_exp=999&media_sig=abc"
    body = main.byteplus_seedream_body(model, "a portrait", reference_images=[signed_url], size="1:1")
    assert body["image"] == signed_url


def test_byteplus_seedream_body_pro_never_drops_assembled_references():
    # None of these assembled references (a mix of hosted URLs and raw
    # Base64) may be silently discarded.
    model = main.BYTEPLUS_SEEDREAM_MODEL_MAP["seedream_5_0_pro"]
    refs = [
        "https://example.com/user1.png",
        "https://example.com/user2.png",
        f"data:image/png;base64,{base64.b64encode(b'ref-bytes-1').decode('ascii')}",
        f"data:image/png;base64,{base64.b64encode(b'ref-bytes-2').decode('ascii')}",
        "https://example.com/character1.png",
        "https://example.com/object1.png",
    ]
    body = main.byteplus_seedream_body(model, "a scene", reference_images=refs, size="1:1")
    assert len(body["image"]) == 6


def test_byteplus_seedream_body_non_pro_still_sends_single_ref_as_string():
    model = main.BYTEPLUS_SEEDREAM_MODEL_MAP["seedream_4_5"]
    body = main.byteplus_seedream_body(
        model, "a portrait", reference_images=["https://example.com/a.png"], size="1:1",
    )
    # Preserves 4.5's existing, already-working request shape exactly -
    # single reference goes in as a bare string, not a one-item list.
    assert body["image"] == "https://example.com/a.png"


def test_byteplus_seedream_body_non_pro_multiple_refs_as_list():
    model = main.BYTEPLUS_SEEDREAM_MODEL_MAP["seedream_4_5"]
    refs = [f"https://example.com/{i}.png" for i in range(3)]
    body = main.byteplus_seedream_body(model, "a portrait", reference_images=refs, size="1:1")
    assert body["image"] == refs


def test_byteplus_seedream_body_rejects_over_limit_instead_of_clipping():
    import pytest

    model = main.BYTEPLUS_SEEDREAM_MODEL_MAP["seedream_4_5"]
    max_refs = main.seedream_capabilities("", model)["max_references"]
    refs = [f"https://example.com/{i}.png" for i in range(max_refs + 5)]
    with pytest.raises(ValueError, match="at most"):
        main.byteplus_seedream_body(model, "a portrait", reference_images=refs, size="1:1")


def test_seedream_merge_references_interleaves_all_three_sources():
    opts = {
        "referenceImageUrls": ["u1", "u2", "u3"],
        "characterReferences": ["c1"],
        "objectReferences": ["o1", "o2"],
    }
    merged, counts = main.seedream_merge_references(opts)
    assert counts == {"user": 3, "character": 1, "object": 2, "combined_before_clip": 6}
    # Round-robin order: one from each source per pass (user, character,
    # object), so a downstream clip to a small N still keeps a
    # representative from every selected source instead of draining
    # whichever source happens to be read first.
    assert merged[:3] == ["u1", "c1", "o1"]
    assert set(merged) == {"u1", "u2", "u3", "c1", "o1", "o2"}


def test_seedream_merge_references_dedupes_across_sources():
    opts = {
        "referenceImageUrls": ["shared.png"],
        "characterReferences": ["shared.png", "c1"],
        "objectReferences": [],
    }
    merged, counts = main.seedream_merge_references(opts)
    assert merged.count("shared.png") == 1
    assert counts["user"] == 1
    assert counts["character"] == 2


def test_seedream_merge_references_ignores_style_text_field():
    # Style is a text-only prompt preset in SYLVEX's image pipeline - it has
    # no image field at all, so it must never appear among references even
    # if a caller passes it through image_options.
    opts = {"style": "calm", "referenceImageUrls": ["u1"]}
    merged, counts = main.seedream_merge_references(opts)
    assert merged == ["u1"]
    assert counts["character"] == 0 and counts["object"] == 0


def test_all_selected_sources_survive_when_model_supports_them():
    model = main.BYTEPLUS_SEEDREAM_MODEL_MAP["seedream_4_5"]
    opts = {
        "referenceImageUrls": ["https://example.com/u1.png"],
        "characterReferences": ["https://example.com/c1.png"],
        "objectReferences": ["https://example.com/o1.png"],
    }
    merged, _ = main.seedream_merge_references(opts)
    body = main.byteplus_seedream_body(model, "a scene", reference_images=merged, size="1:1")
    assert set(body["image"]) == {
        "https://example.com/u1.png", "https://example.com/c1.png", "https://example.com/o1.png",
    }


def test_image_reference_urls_preserves_all_selected_visual_references():
    payload = {
        "image_options": {
            "characterReferences": [f"c{i}.png" for i in range(6)],
            "objectReferences": [f"o{i}.png" for i in range(6)],
        }
    }
    refs = main.image_reference_urls(payload)
    character_refs = [r for r in refs if r.startswith("c")]
    object_refs = [r for r in refs if r.startswith("o")]
    assert len(character_refs) == 6
    assert len(object_refs) == 6
