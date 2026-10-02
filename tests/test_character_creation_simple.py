"""Regression tests for the final simplified Character creation flow.

Covers:
  - public_prostudio_create_character(): the user supplies exactly one
    source photo (mandatory, capped at 1 even if more are submitted) plus
    an optional text field - no Manual/Create-with-AI modes, no processing
    modes, no multiple upload slots (all of that was Character Creation V2
    and has been reverted).
  - _generate_openai_character_images(): generates exactly 4 references
    (Main identity, Full Body Front, Full Body Side, Full Body Back) from
    the single source photo, chaining Front/Side/Back off the Main
    identity shot (and the previously generated body shot) so identity and
    clothing stay locked across the set - never four independently
    reinterpreted generations.
  - The optional text field is additional guidance only: Character
    creation works identically whether it is present or empty, and the
    source photo always remains the identity source.
  - reference_library role labels: Primary Face / Full Body Front / Full
    Body Side / Full Body Back.

Does not touch the already-fixed Character generation/reference-selection
payload logic, and does not test Object creation (unaffected by this
change).
"""
import asyncio

import pytest

import main


class FakeRequest:
    def __init__(self, data):
        self._data = data

    async def json(self):
        return self._data


def test_generate_character_images_chains_primary_through_body_shots(monkeypatch):
    calls = []

    async def fake_shot(prompt, reference_urls, quality="high"):
        calls.append((prompt, list(reference_urls)))
        return f"https://cdn.sylvex.ai/shot_{len(calls)}.png"

    monkeypatch.setattr(main, "_openai_character_shot", fake_shot)

    photos = ["https://cdn.sylvex.ai/uploads/source.jpg"]
    result = asyncio.run(main._generate_openai_character_images("Islam", "male", "tall, athletic", photos))

    assert result == [
        "https://cdn.sylvex.ai/shot_1.png",
        "https://cdn.sylvex.ai/shot_2.png",
        "https://cdn.sylvex.ai/shot_3.png",
        "https://cdn.sylvex.ai/shot_4.png",
    ]
    assert len(calls) == 4
    primary_prompt, primary_refs = calls[0]
    front_prompt, front_refs = calls[1]
    side_prompt, side_refs = calls[2]
    back_prompt, back_refs = calls[3]

    # Main identity is generated from the single uploaded source photo only.
    assert primary_refs == ["https://cdn.sylvex.ai/uploads/source.jpg"]
    # Front is generated against the just-created Main identity shot plus
    # the original source photo, to lock identity and visible clothing.
    assert front_refs == ["https://cdn.sylvex.ai/shot_1.png", "https://cdn.sylvex.ai/uploads/source.jpg"]
    # Side and Back each reference Main identity plus the growing chain of
    # body shots already produced - never independently regenerated.
    assert side_refs == ["https://cdn.sylvex.ai/shot_1.png", "https://cdn.sylvex.ai/shot_2.png"]
    assert back_refs == ["https://cdn.sylvex.ai/shot_1.png", "https://cdn.sylvex.ai/shot_2.png", "https://cdn.sylvex.ai/shot_3.png"]

    assert "Islam" in primary_prompt
    assert "chest-up or waist-up" in primary_prompt
    assert "front-facing" in front_prompt
    assert "side" in side_prompt.lower()
    assert "back view" in back_prompt
    # Front/Side/Back standardization: gray studio background, no dramatic
    # posing, same clothing/proportions - these are the technical identity
    # views, not lifestyle photographs.
    for body_prompt in (front_prompt, side_prompt, back_prompt):
        assert "gray studio background" in body_prompt
        assert "never invent different trousers, shoes, jackets" in body_prompt


def test_generate_character_images_works_with_no_optional_text(monkeypatch):
    calls = []

    async def fake_shot(prompt, reference_urls, quality="high"):
        calls.append(prompt)
        return "https://cdn.sylvex.ai/shot.png"

    monkeypatch.setattr(main, "_openai_character_shot", fake_shot)
    result = asyncio.run(main._generate_openai_character_images("Nova", "female", "", ["https://cdn.sylvex.ai/a.jpg"]))
    assert len(result) == 4
    # No description text - the identity sentence still names the
    # character, just without extra guidance appended.
    assert "Nova" in calls[0]


def test_identity_prompt_includes_description_only_when_provided():
    with_text = main._character_identity_prompt("Islam", "male", "tall, athletic build")
    without_text = main._character_identity_prompt("Islam", "male", "")
    assert "tall, athletic build" in with_text
    assert "tall, athletic build" not in without_text
    assert "Islam" in with_text and "Islam" in without_text


@pytest.fixture
def stub_character_pipeline(monkeypatch):
    async def fake_generate_images(name, gender, description, photos):
        return [
            "https://cdn.sylvex.ai/generated/primary.png",
            "https://cdn.sylvex.ai/generated/front.png",
            "https://cdn.sylvex.ai/generated/side.png",
            "https://cdn.sylvex.ai/generated/back.png",
        ]

    def fake_create_heygen_character(name, avatar_url, references):
        return {"response": {"ok": True}, "photo_avatar_id": "heygen_photo_1", "avatar_group_id": "heygen_group_1"}

    monkeypatch.setattr(main, "_generate_openai_character_images", fake_generate_images)
    monkeypatch.setattr(main, "_create_heygen_character", fake_create_heygen_character)
    monkeypatch.setattr(main, "save_prostudio_resource", lambda telegram_id, resource: resource)
    return fake_generate_images


def test_create_character_requires_a_photo(stub_character_pipeline):
    # Unlike the reverted V2's text-only Scenario B, the photo is mandatory
    # in the final simplified flow - a description alone is not enough.
    request = FakeRequest({"telegram_id": 42, "name": "Islam", "gender": "male", "description": "tall"})
    result = asyncio.run(main.public_prostudio_create_character(request))
    assert result.status_code == 400
    import json
    assert json.loads(result.body)["error"] == "reference_image_required"


def test_create_character_caps_photos_at_exactly_one(stub_character_pipeline, monkeypatch):
    received = {}

    async def fake_generate_images(name, gender, description, photos):
        received["photos"] = list(photos)
        return [
            "https://cdn.sylvex.ai/generated/primary.png",
            "https://cdn.sylvex.ai/generated/front.png",
            "https://cdn.sylvex.ai/generated/side.png",
            "https://cdn.sylvex.ai/generated/back.png",
        ]

    monkeypatch.setattr(main, "_generate_openai_character_images", fake_generate_images)
    request = FakeRequest({
        "telegram_id": 42, "name": "Islam", "gender": "male",
        "photos": ["https://cdn.sylvex.ai/a.jpg", "https://cdn.sylvex.ai/b.jpg", "https://cdn.sylvex.ai/c.jpg"],
    })
    asyncio.run(main.public_prostudio_create_character(request))
    assert received["photos"] == ["https://cdn.sylvex.ai/a.jpg"]


def test_create_character_succeeds_with_photo_and_no_optional_text(stub_character_pipeline):
    request = FakeRequest({
        "telegram_id": 42, "name": "Islam", "gender": "male",
        "photos": ["https://cdn.sylvex.ai/a.jpg"],
    })
    result = asyncio.run(main.public_prostudio_create_character(request))
    assert result["ok"] is True
    resource = result["resource"]
    assert resource["primaryReferenceUrl"] == "https://cdn.sylvex.ai/generated/primary.png"
    assert resource["primaryReferenceUrl"] == resource["avatarUrl"]
    assert len(resource["referenceLibrary"]) == 4


def test_create_character_reference_library_uses_main_front_side_back_roles(stub_character_pipeline):
    request = FakeRequest({"telegram_id": 42, "name": "Islam", "gender": "male", "photos": ["https://cdn.sylvex.ai/a.jpg"]})
    result = asyncio.run(main.public_prostudio_create_character(request))
    roles = [entry["role"] for entry in result["resource"]["referenceLibrary"]]
    assert roles == ["Primary Face", "Full Body Front", "Full Body Side", "Full Body Back"]


def test_create_character_source_photo_kept_only_as_metadata_not_a_reference(stub_character_pipeline):
    # The raw uploaded source photo must not become a 5th Character
    # reference - it is kept only as originalSourceImages metadata.
    request = FakeRequest({"telegram_id": 42, "name": "Islam", "gender": "male", "photos": ["https://cdn.sylvex.ai/source.jpg"]})
    result = asyncio.run(main.public_prostudio_create_character(request))
    resource = result["resource"]
    assert resource["originalSourceImages"] == ["https://cdn.sylvex.ai/source.jpg"]
    assert "https://cdn.sylvex.ai/source.jpg" not in resource["referenceImages"]
    assert all(entry["url"] != "https://cdn.sylvex.ai/source.jpg" for entry in resource["referenceLibrary"])
