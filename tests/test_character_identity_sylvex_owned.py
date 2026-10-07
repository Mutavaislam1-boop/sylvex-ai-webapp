"""Regression test for the SYLVEX-only Character pipeline's identity
invariant, now exercised through the async job worker.

Historically public_prostudio_create_character built the Character's own
`id` directly from HeyGen's photo_avatar_id/avatar_group_id, and HeyGen
was a required step of Character creation. Both are gone: the canonical
`id` is a fresh SYLVEX-owned uuid4, HeyGen is never called, and the whole
pipeline now runs as a background job (_run_character_creation_job)
rather than inline in the request handler - see
test_character_creation_simple.py for the job-creation/202-response
contract. This file is scoped to the one invariant that must survive
every rewrite: the Character's id is always a fresh SYLVEX-owned uuid,
never derived from anything provider- or request-shaped.
"""
import asyncio
import re

import pytest

import main


@pytest.fixture(autouse=True)
def _stub_character_pipeline(monkeypatch):
    async def fake_generate_images(job_id, name, gender, description, photos):
        return [
            "https://cdn.sylvex.ai/generated/avatar.png",
            "https://cdn.sylvex.ai/generated/ref1.png",
            "https://cdn.sylvex.ai/generated/ref2.png",
            "https://cdn.sylvex.ai/generated/ref3.png",
        ]

    monkeypatch.setattr(main, "_generate_openai_character_images", fake_generate_images)
    monkeypatch.setattr(main, "save_prostudio_resource", lambda telegram_id, resource: resource)
    monkeypatch.setattr(main, "heartbeat_prostudio_generation_job", lambda job_id: None)


def _run_job_and_capture_result(monkeypatch, job_id, telegram_id=42, name="Islam", gender="male", description="", photos=None):
    updates = []
    monkeypatch.setattr(
        main, "update_prostudio_generation_job",
        lambda job_id, status, result=None, error=None, conversation_id="": updates.append((status, result, error)),
    )
    asyncio.run(main._run_character_creation_job(job_id, telegram_id, name, gender, description, photos or ["https://cdn.sylvex.ai/a.jpg"]))
    assert updates, "update_prostudio_generation_job was never called"
    return updates[-1]


def test_character_id_is_a_fresh_sylvex_owned_uuid(monkeypatch):
    status, result, error = _run_job_and_capture_result(monkeypatch, "job-1", description="test character")
    assert status == "completed"
    assert error is None
    resource = result["resource"]

    # A fresh SYLVEX-generated identifier: custom_character_ followed by a
    # uuid4 hex (32 lowercase hex chars) - never a provider-specific id.
    assert re.fullmatch(r"custom_character_[0-9a-f]{32}", resource["id"])


def test_two_characters_created_with_the_same_name_get_distinct_ids(monkeypatch):
    status_a, result_a, _ = _run_job_and_capture_result(monkeypatch, "job-a", name="Same Name")
    status_b, result_b, _ = _run_job_and_capture_result(monkeypatch, "job-b", name="Same Name")
    assert status_a == status_b == "completed"
    assert result_a["resource"]["id"] != result_b["resource"]["id"]


def test_primary_reference_url_is_set_to_the_generated_avatar(monkeypatch):
    status, result, _ = _run_job_and_capture_result(monkeypatch, "job-1")
    resource = result["resource"]
    assert resource["primaryReferenceUrl"] == "https://cdn.sylvex.ai/generated/avatar.png"
    assert resource["primaryReferenceUrl"] == resource["avatarUrl"]
