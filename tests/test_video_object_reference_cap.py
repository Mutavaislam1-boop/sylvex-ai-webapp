"""Regression test for the Pro Studio A-Z audit's Phase 7 fix: video
objectReferences must be capped [:4] the same way characterReferences
already is when building the merged reference_images list, so an
unusually large object catalog item can't silently crowd out the
character reference (or vice versa) in the fixed-size list a provider
actually receives.
"""
import services.video_router as video_router


def test_video_reference_images_caps_both_character_and_object_refs():
    payload = {
        "model": "kling_3_0",
        "video_options": {
            "model": "kling_3_0",
            "characterReferences": [f"https://x.test/char{i}.png" for i in range(6)],
            "objectReferences": [f"https://x.test/obj{i}.png" for i in range(6)],
        },
        "prompt": "test",
    }
    body = video_router._build_video_payload("kling_3_0", "test", payload)
    assert len(body["reference_images"]) == 8
    character_count = sum(1 for url in body["reference_images"] if "char" in url)
    object_count = sum(1 for url in body["reference_images"] if "obj" in url)
    assert character_count == 4
    assert object_count == 4
