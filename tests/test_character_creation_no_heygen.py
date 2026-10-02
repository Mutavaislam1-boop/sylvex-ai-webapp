"""Regression tests for removing HeyGen from the Character creation
pipeline, now exercised through the async job worker.

Final architecture: GPT Image -> SYLVEX Storage -> SYLVEX Character.
Nothing else. _run_character_creation_job() (the background worker
behind public_prostudio_create_character's 202 job) must:
  - never call _create_heygen_character() (no HeyGen Character/Avatar
    creation request, no post-generation upload of the 4 references to
    HeyGen);
  - never fail because of HeyGen (missing HEYGEN_API_KEY, a HeyGen-side
    error, or anything else HeyGen-related) - there is nothing in this
    function that could even reach HeyGen;
  - mark the job completed via update_prostudio_generation_job with a
    SYLVEX-owned character_id and the full resource payload, with no
    "heygen" key anywhere in the result.

Does not touch unrelated HeyGen functionality (built-in preset
Characters' own heygen.json metadata, or Video mode's HeyGen avatar
lookalike feature) - those still read whatever heygenPhotoAvatarId/
heygenAvatarGroupId a Character happens to have (empty for one created
through this job, which is the expected, non-breaking effect of no
longer registering new Characters with HeyGen).
"""
import asyncio

import pytest

import main


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
    monkeypatch.setattr(main, "heartbeat_prostudio_generation_job", lambda job_id: None)


def _run_job(monkeypatch, job_id="job-1", telegram_id=42, name="Islam", gender="male", description="", photos=None):
    updates = []
    monkeypatch.setattr(
        main, "update_prostudio_generation_job",
        lambda job_id, status, result=None, error=None, conversation_id="": updates.append((status, result, error)),
    )
    asyncio.run(main._run_character_creation_job(job_id, telegram_id, name, gender, description, photos or ["https://cdn.sylvex.ai/a.jpg"]))
    assert updates
    return updates[-1]


def test_run_character_creation_job_never_calls_create_heygen_character(stub_image_generation, monkeypatch):
    called = {"value": False}

    def spy_create_heygen_character(name, avatar_url, references):
        called["value"] = True
        return {"response": {}, "photo_avatar_id": "x", "avatar_group_id": "y"}

    monkeypatch.setattr(main, "_create_heygen_character", spy_create_heygen_character)
    status, result, error = _run_job(monkeypatch)
    assert status == "completed"
    assert error is None
    assert called["value"] is False, "_create_heygen_character must never be invoked by Character creation"


def test_run_character_creation_job_is_structurally_unreachable_from_heygen(stub_image_generation, monkeypatch):
    # There is nothing left in this function that could call out to
    # HeyGen at all - a HeyGen-side 500, a missing API key, a bad
    # response shape, whatever - so monkeypatching it to always explode
    # must have zero effect on job completion.
    def exploding_create_heygen_character(name, avatar_url, references):
        raise RuntimeError("HEYGEN_API_KEY is not configured")

    monkeypatch.setattr(main, "_create_heygen_character", exploding_create_heygen_character)
    status, result, error = _run_job(monkeypatch)
    assert status == "completed"
    assert error is None
    resource = result["resource"]
    assert resource["heygenPhotoAvatarId"] == ""
    assert resource["heygenAvatarGroupId"] == ""
    assert resource["avatar_id"] == ""


def test_run_character_creation_job_result_has_no_heygen_key(stub_image_generation, monkeypatch):
    def exploding_create_heygen_character(name, avatar_url, references):
        raise AssertionError("must not be called")

    monkeypatch.setattr(main, "_create_heygen_character", exploding_create_heygen_character)
    status, result, error = _run_job(monkeypatch)
    # The old synchronous response shape carried a top-level "heygen" key
    # (the raw HeyGen API response) - there is no provider-registration
    # step left to report on.
    assert "heygen" not in result


def test_run_character_creation_job_resource_shape_matches_success_condition(stub_image_generation, monkeypatch):
    def exploding_create_heygen_character(name, avatar_url, references):
        raise AssertionError("must not be called")

    monkeypatch.setattr(main, "_create_heygen_character", exploding_create_heygen_character)
    status, result, error = _run_job(monkeypatch)
    assert status == "completed"
    resource = result["resource"]
    # 1. GPT Image generated the required references (4 total, chained);
    #    2. saved via save_prostudio_resource (stubbed as identity here);
    #    3. a SYLVEX character_id was created;
    #    4. the resource and its reference library are present.
    assert resource["id"].startswith("custom_character_")
    assert result["character_id"] == resource["id"]
    assert len(resource["referenceLibrary"]) == 4
    assert resource["provider"] == "openai"
    assert resource["ai_provider"] == "openai"
