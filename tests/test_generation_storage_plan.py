from services import generation_storage


def _complete_plan(plan):
    for entry in plan.values():
        entry["url"] = "https://storage.example.test/" + entry["key"]
    return plan


def test_media_plan_covers_every_image_audio_and_cover_output():
    result = {
        "type": "music",
        "audio_url": "https://provider.example/song.mp3",
        "audio_urls": [
            "https://provider.example/song.mp3",
            "https://provider.example/alternate.wav",
        ],
        "cover_url": "https://provider.example/cover.png",
        "metadata": {"artwork_url": "https://provider.example/artwork.webp"},
    }

    plan = generation_storage.media_plan("music-job", result, "music")

    assert {entry["source"] for entry in plan.values()} == {
        "https://provider.example/song.mp3",
        "https://provider.example/alternate.wav",
        "https://provider.example/cover.png",
        "https://provider.example/artwork.webp",
    }
    assert {entry["category"] for entry in plan.values()} == {"audio", "images"}


def test_character_resource_references_are_replaced_by_their_r2_objects():
    primary = "https://provider.example/face.png"
    side = "https://provider.example/side.png"
    result = {
        "type": "character",
        "image_url": primary,
        "images": [primary, side],
        "result_url": primary,
        "resource": {
            "id": "character-1",
            "previewUrl": primary,
            "avatarUrl": primary,
            "primaryReferenceUrl": primary,
            "referenceImages": [side],
            "sourceImages": [side],
            "referenceLibrary": [
                {"id": "front", "url": primary},
                {"id": "side", "url": side},
            ],
        },
    }

    plan = _complete_plan(
        generation_storage.media_plan("character-job", result, "character_creation")
    )
    stored = generation_storage.replace_planned_media(result, plan)

    assert len(plan) == 2
    assert all(entry["category"] == "images" for entry in plan.values())
    assert all(url.startswith("https://storage.example.test/generated/images/") for url in stored["images"])
    assert stored["resource"]["previewUrl"] == stored["images"][0]
    assert stored["resource"]["primaryReferenceUrl"] == stored["images"][0]
    assert stored["resource"]["referenceImages"] == [stored["images"][1]]
    assert [item["url"] for item in stored["resource"]["referenceLibrary"]] == stored["images"]


def test_same_job_and_source_always_choose_the_same_object_key():
    result = {"type": "video", "video_url": "https://provider.example/result.mp4?token=one"}

    first = generation_storage.media_plan("stable-job", result, "video")
    second = generation_storage.media_plan("stable-job", result, "video")

    assert [entry["key"] for entry in first.values()] == [entry["key"] for entry in second.values()]
    assert [entry["fingerprint"] for entry in first.values()] == [entry["fingerprint"] for entry in second.values()]
