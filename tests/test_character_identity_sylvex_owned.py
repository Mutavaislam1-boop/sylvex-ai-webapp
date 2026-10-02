"""Regression test for the Character System V2 product contract (Master
A-Z Remediation Phase 4): "Do not make a provider-specific persistent
character ID the canonical identity."

Before this fix, public_prostudio_create_character built the Character's
own `id` directly from HeyGen's photo_avatar_id/avatar_group_id
(`f"custom_character_{stable_id}"` where stable_id came from the HeyGen
API response) - so losing or rotating that HeyGen mapping would have
destroyed the Character's very identity, not just its HeyGen-specific
capability. The fix generates a SYLVEX-owned id (uuid4) and keeps the
HeyGen ids only as a separate mapping (heygenPhotoAvatarId/
heygenAvatarGroupId), exactly as the contract requires: "If a provider
supports persistent characters, provider mappings may exist... but
removing/changing that provider must not destroy the SYLVEX Character."
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
    async def fake_generate_images(name, gender, description, photos, processing_mode="ai_polish"):
        return [
            "https://cdn.sylvex.ai/generated/avatar.png",
            "https://cdn.sylvex.ai/generated/ref1.png",
            "https://cdn.sylvex.ai/generated/ref2.png",
            "https://cdn.sylvex.ai/generated/ref3.png",
        ]

    def fake_create_heygen_character(name, avatar_url, references):
        return {
            "response": {"ok": True},
            "photo_avatar_id": "heygen_photo_avatar_12345",
            "avatar_group_id": "heygen_group_67890",
        }

    monkeypatch.setattr(main, "_generate_openai_character_images", fake_generate_images)
    monkeypatch.setattr(main, "_create_heygen_character", fake_create_heygen_character)
    monkeypatch.setattr(main, "save_prostudio_resource", lambda telegram_id, resource: resource)


def test_character_id_is_sylvex_owned_not_derived_from_heygen():
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

    # The canonical id must never equal (or embed, beyond the generic
    # "custom_character_" prefix) either HeyGen id.
    assert resource["id"] != "custom_character_heygen_photo_avatar_12345"
    assert resource["id"] != "custom_character_heygen_group_67890"
    assert "heygen_photo_avatar_12345" not in resource["id"]
    assert "heygen_group_67890" not in resource["id"]

    # It must be a fresh SYLVEX-generated identifier: custom_character_
    # followed by a uuid4 hex (32 lowercase hex chars).
    assert re.fullmatch(r"custom_character_[0-9a-f]{32}", resource["id"])

    # HeyGen's ids survive as an explicit provider mapping, not as identity.
    assert resource["heygenPhotoAvatarId"] == "heygen_photo_avatar_12345"
    assert resource["heygenAvatarGroupId"] == "heygen_group_67890"


def test_two_characters_created_with_identical_heygen_response_get_distinct_ids(monkeypatch):
    # Guards against a regression where the id was accidentally derived
    # from something heygen-response-shaped (e.g. name) instead of a
    # fresh random SYLVEX id - two different Characters must never
    # collide just because their HeyGen avatar creation calls look alike.
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
