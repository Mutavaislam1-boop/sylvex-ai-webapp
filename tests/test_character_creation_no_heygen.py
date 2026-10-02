"""Regression tests for removing HeyGen from the Character creation
pipeline.

Final architecture: GPT Image -> SYLVEX Storage -> SYLVEX Character.
Nothing else. public_prostudio_create_character() must:
  - never call _create_heygen_character() (no HeyGen Character/Avatar
    creation request, no post-generation upload of the 4 references to
    HeyGen);
  - never fail because of HeyGen (missing HEYGEN_API_KEY, a HeyGen-side
    error, or anything else HeyGen-related);
  - succeed as soon as GPT Image generated the 4 references and they were
    saved via save_prostudio_resource(), using a SYLVEX-owned
    character_id - there is no additional provider-registration step.

Does not touch unrelated HeyGen functionality (built-in preset
Characters' own heygen.json metadata, or Video mode's HeyGen avatar
lookalike feature) - those still read whatever heygenPhotoAvatarId/
heygenAvatarGroupId a Character happens to have (empty for one created
through this endpoint, which is the expected, non-breaking effect of no
longer registering new Characters with HeyGen).
"""
import asyncio

import pytest

import main


class FakeRequest:
    def __init__(self, data):
        self._data = data

    async def json(self):
        return self._data


@pytest.fixture
def stub_image_generation(monkeypatch):
    async def fake_generate_images(name, gender, description, photos):
        return [
            "https://cdn.sylvex.ai/generated/primary.png",
            "https://cdn.sylvex.ai/generated/front.png",
            "https://cdn.sylvex.ai/generated/side.png",
            "https://cdn.sylvex.ai/generated/back.png",
        ]

    monkeypatch.setattr(main, "_generate_openai_character_images", fake_generate_images)
    monkeypatch.setattr(main, "save_prostudio_resource", lambda telegram_id, resource: resource)


def test_create_character_never_calls_create_heygen_character(stub_image_generation, monkeypatch):
    called = {"value": False}

    def spy_create_heygen_character(name, avatar_url, references):
        called["value"] = True
        return {"response": {}, "photo_avatar_id": "x", "avatar_group_id": "y"}

    monkeypatch.setattr(main, "_create_heygen_character", spy_create_heygen_character)
    request = FakeRequest({"telegram_id": 42, "name": "Islam", "gender": "male", "photos": ["https://cdn.sylvex.ai/a.jpg"]})
    result = asyncio.run(main.public_prostudio_create_character(request))
    assert result["ok"] is True
    assert called["value"] is False, "_create_heygen_character must never be invoked by Character creation"


def test_create_character_succeeds_even_when_heygen_is_completely_unconfigured(stub_image_generation, monkeypatch):
    # HEYGEN_API_KEY missing used to make _create_heygen_character raise
    # RuntimeError("HEYGEN_API_KEY is not configured"), which the old
    # best-effort wrapper caught - now there is no call at all, so there
    # is nothing to configure and nothing that can fail.
    def exploding_create_heygen_character(name, avatar_url, references):
        raise RuntimeError("HEYGEN_API_KEY is not configured")

    monkeypatch.setattr(main, "_create_heygen_character", exploding_create_heygen_character)
    request = FakeRequest({"telegram_id": 42, "name": "Islam", "gender": "male", "photos": ["https://cdn.sylvex.ai/a.jpg"]})
    result = asyncio.run(main.public_prostudio_create_character(request))
    assert result["ok"] is True


def test_create_character_succeeds_even_when_heygen_would_fail_hard(stub_image_generation, monkeypatch):
    # A HeyGen-side 500, a bad response shape, a network timeout -
    # whatever it is, it must be structurally unreachable from this
    # endpoint, not merely caught.
    def exploding_create_heygen_character(name, avatar_url, references):
        raise RuntimeError("HeyGen character creation failed: 500 Internal Server Error")

    monkeypatch.setattr(main, "_create_heygen_character", exploding_create_heygen_character)
    request = FakeRequest({"telegram_id": 7, "name": "Nova", "gender": "female", "photos": ["https://cdn.sylvex.ai/b.jpg"]})
    result = asyncio.run(main.public_prostudio_create_character(request))
    assert result["ok"] is True
    resource = result["resource"]
    assert resource["heygenPhotoAvatarId"] == ""
    assert resource["heygenAvatarGroupId"] == ""


def test_create_character_response_has_no_heygen_key(stub_image_generation, monkeypatch):
    def exploding_create_heygen_character(name, avatar_url, references):
        raise AssertionError("must not be called")

    monkeypatch.setattr(main, "_create_heygen_character", exploding_create_heygen_character)
    request = FakeRequest({"telegram_id": 42, "name": "Islam", "gender": "male", "photos": ["https://cdn.sylvex.ai/a.jpg"]})
    result = asyncio.run(main.public_prostudio_create_character(request))
    # The old response shape carried a top-level "heygen" key (the raw
    # HeyGen API response) - there is no provider-registration step left
    # to report on.
    assert "heygen" not in result


def test_create_character_resource_shape_matches_success_condition(stub_image_generation, monkeypatch):
    def exploding_create_heygen_character(name, avatar_url, references):
        raise AssertionError("must not be called")

    monkeypatch.setattr(main, "_create_heygen_character", exploding_create_heygen_character)
    request = FakeRequest({"telegram_id": 42, "name": "Islam", "gender": "male", "photos": ["https://cdn.sylvex.ai/a.jpg"]})
    result = asyncio.run(main.public_prostudio_create_character(request))
    assert result["ok"] is True
    resource = result["resource"]
    # 1. GPT Image generated the required references (4 total, chained);
    #    2. saved via save_prostudio_resource (stubbed as identity here);
    #    3. a SYLVEX character_id was created;
    #    4. the resource and its reference library are present.
    assert resource["id"].startswith("custom_character_")
    assert len(resource["referenceLibrary"]) == 4
    assert resource["provider"] == "openai"
    assert resource["ai_provider"] == "openai"
