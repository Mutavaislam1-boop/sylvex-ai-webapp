"""Regression test for the SYLVEX-only Character pipeline.

Historically public_prostudio_create_character built the Character's own
`id` directly from HeyGen's photo_avatar_id/avatar_group_id (so losing or
rotating that HeyGen mapping would have destroyed the Character's very
identity, not just a HeyGen-specific capability), and then registered the
generated reference set with HeyGen as a required step of Character
creation.

Both of those are gone: the canonical `id` is a fresh SYLVEX-owned uuid4,
and HeyGen is no longer called at all when creating a Character - GPT
Image generates the reference set, SYLVEX stores it, and that's the
entire pipeline (GPT Image -> SYLVEX Storage -> SYLVEX Character). A
Character created this way always has empty heygenPhotoAvatarId/
heygenAvatarGroupId fields; nothing about HeyGen's availability,
configuration, or response can make Character creation fail.
"""
import asyncio
import re

import pytest

import main


class FakeRequest:
    def __init__(self, data):
        self._data = data

    async def json(self):
        return self._data


@pytest.fixture(autouse=True)
def _stub_character_pipeline(monkeypatch):
    async def fake_generate_images(name, gender, description, photos):
        return [
            "https://cdn.sylvex.ai/generated/avatar.png",
            "https://cdn.sylvex.ai/generated/ref1.png",
            "https://cdn.sylvex.ai/generated/ref2.png",
            "https://cdn.sylvex.ai/generated/ref3.png",
        ]

    def fail_if_called_create_heygen_character(name, avatar_url, references):
        raise AssertionError("_create_heygen_character must never be called by Character creation")

    monkeypatch.setattr(main, "_generate_openai_character_images", fake_generate_images)
    monkeypatch.setattr(main, "_create_heygen_character", fail_if_called_create_heygen_character)
    monkeypatch.setattr(main, "save_prostudio_resource", lambda telegram_id, resource: resource)


def test_character_id_is_a_fresh_sylvex_owned_uuid():
    request = FakeRequest({
        "telegram_id": 42,
        "name": "Islam",
        "gender": "male",
        "description": "test character",
        "photos": ["https://cdn.sylvex.ai/uploads/photo1.jpg"],
    })
    result = asyncio.run(main.public_prostudio_create_character(request))
    assert result["ok"] is True
    resource = result["resource"]

    # A fresh SYLVEX-generated identifier: custom_character_ followed by a
    # uuid4 hex (32 lowercase hex chars) - never a provider-specific id.
    assert re.fullmatch(r"custom_character_[0-9a-f]{32}", resource["id"])


def test_character_creation_never_calls_heygen_and_leaves_heygen_fields_empty():
    request = FakeRequest({"telegram_id": 42, "name": "Islam", "photos": ["https://cdn.sylvex.ai/a.jpg"]})
    result = asyncio.run(main.public_prostudio_create_character(request))
    assert result["ok"] is True
    resource = result["resource"]
    # _create_heygen_character is stubbed above to raise if called - ok is
    # True here is itself proof it was never invoked. The fields it used
    # to populate must still be present (other code reads them) but empty.
    assert resource["heygenPhotoAvatarId"] == ""
    assert resource["heygenAvatarGroupId"] == ""
    assert resource["avatar_id"] == ""
    assert resource["provider"] == "openai"
    assert resource["ai_provider"] == "openai"
    assert "heygen" not in result


def test_two_characters_created_with_the_same_name_get_distinct_ids(monkeypatch):
    # Guards against a regression where the id was accidentally derived
    # from something request-shaped (e.g. the name) instead of a fresh
    # random SYLVEX id.
    request_a = FakeRequest({"telegram_id": 1, "name": "Same Name", "photos": ["https://cdn.sylvex.ai/a.jpg"]})
    request_b = FakeRequest({"telegram_id": 1, "name": "Same Name", "photos": ["https://cdn.sylvex.ai/a.jpg"]})
    result_a = asyncio.run(main.public_prostudio_create_character(request_a))
    result_b = asyncio.run(main.public_prostudio_create_character(request_b))
    assert result_a["resource"]["id"] != result_b["resource"]["id"]


def test_primary_reference_url_is_set_to_the_generated_avatar():
    request = FakeRequest({"telegram_id": 42, "name": "Islam", "photos": ["https://cdn.sylvex.ai/a.jpg"]})
    result = asyncio.run(main.public_prostudio_create_character(request))
    resource = result["resource"]
    assert resource["primaryReferenceUrl"] == "https://cdn.sylvex.ai/generated/avatar.png"
    assert resource["primaryReferenceUrl"] == resource["avatarUrl"]
