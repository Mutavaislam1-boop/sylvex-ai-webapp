"""Regression tests for Character Creation V2 (Manual + Create with AI).

Covers:
  - _generate_openai_character_images(): both Scenario A (photo provided)
    and Scenario B (text-only, no photo); the standard 4-reference set
    (Primary, Front, Side, Back) is generated in order, with Front/Side/
    Back each referencing the Primary (and the previous body shot) to keep
    identity/clothing locked across the set - never four independently
    reinterpreted generations.
  - processing_mode ("preserve" vs "ai_polish", default "ai_polish") is
    threaded into the Primary prompt by _generate_openai_character_images
    (the AI-create chained set); _character_body_prompt also supports
    both modes (used by the Manual-mode per-slot processor below).
  - public_prostudio_create_character(): a photo is now optional (either a
    photo OR a non-empty description is required), capped at 1 instead of
    3; HeyGen registration is best-effort and never blocks Character
    creation; reference-library role labels match the new Front/Side/Back
    naming.
  - public_prostudio_process_character_reference() (Manual mode's own AI
    processing step, /api/public/prostudio/character/process-reference):
    Manual Character Creation lets the user decide which of the 4 slots
    exist (never auto-completing a missing one), but every slot that *is*
    filled still gets run through the chosen processing mode to meet that
    slot's own standard - this is not "save the raw upload as-is".

Does not touch the already-fixed Character generation/reference-selection
payload logic - these tests are entirely about Character *creation*.
"""
import asyncio

import pytest

import main


class FakeRequest:
    def __init__(self, data):
        self._data = data

    async def json(self):
        return self._data


def test_generate_character_images_scenario_a_chains_primary_through_body_shots(monkeypatch):
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

    # Primary is generated from the uploaded source photo only.
    assert primary_refs == ["https://cdn.sylvex.ai/uploads/source.jpg"]
    # Front is generated against the just-created Primary plus the original
    # source photo, to lock identity and visible clothing.
    assert front_refs == ["https://cdn.sylvex.ai/shot_1.png", "https://cdn.sylvex.ai/uploads/source.jpg"]
    # Side and Back each reference Primary plus the growing chain of body
    # shots already produced - never independently regenerated.
    assert side_refs == ["https://cdn.sylvex.ai/shot_1.png", "https://cdn.sylvex.ai/shot_2.png"]
    assert back_refs == ["https://cdn.sylvex.ai/shot_1.png", "https://cdn.sylvex.ai/shot_2.png", "https://cdn.sylvex.ai/shot_3.png"]

    assert "Islam" in primary_prompt
    assert "front-facing" in front_prompt
    assert "side" in side_prompt.lower()
    assert "back view" in back_prompt


def test_generate_character_images_scenario_b_text_only_establishes_identity_first(monkeypatch):
    calls = []

    async def fake_shot(prompt, reference_urls, quality="high"):
        calls.append((prompt, list(reference_urls)))
        return f"https://cdn.sylvex.ai/shot_{len(calls)}.png"

    monkeypatch.setattr(main, "_openai_character_shot", fake_shot)

    result = asyncio.run(main._generate_openai_character_images("Nova", "female", "cyberpunk hacker, neon jacket", []))
    assert len(result) == 4
    primary_prompt, primary_refs = calls[0]
    front_prompt, front_refs = calls[1]

    # No source photo at all - Primary is generated from text only and
    # becomes the fixed identity for every later shot.
    assert primary_refs == []
    assert front_refs == ["https://cdn.sylvex.ai/shot_1.png"]
    assert "brand-new, consistent character" in primary_prompt
    assert "Nova" in primary_prompt
    assert "cyberpunk hacker, neon jacket" in primary_prompt


def test_processing_mode_preserve_vs_ai_polish_only_changes_the_primary_prompt(monkeypatch):
    prompts_by_mode = {}

    async def fake_shot(prompt, reference_urls, quality="high"):
        prompts_by_mode.setdefault("prompts", []).append(prompt)
        return "https://cdn.sylvex.ai/shot.png"

    monkeypatch.setattr(main, "_openai_character_shot", fake_shot)

    asyncio.run(main._generate_openai_character_images("Islam", "male", "", ["https://cdn.sylvex.ai/a.jpg"], "preserve"))
    preserve_primary = prompts_by_mode["prompts"][0]
    prompts_by_mode["prompts"] = []

    asyncio.run(main._generate_openai_character_images("Islam", "male", "", ["https://cdn.sylvex.ai/a.jpg"], "ai_polish"))
    polish_primary = prompts_by_mode["prompts"][0]

    assert "minimal intervention" in preserve_primary
    assert "Do not change the pose" in preserve_primary
    assert "reconstruct" in polish_primary.lower()
    assert preserve_primary != polish_primary


def test_unknown_processing_mode_falls_back_to_ai_polish(monkeypatch):
    seen = []

    async def fake_shot(prompt, reference_urls, quality="high"):
        seen.append(prompt)
        return "https://cdn.sylvex.ai/shot.png"

    monkeypatch.setattr(main, "_openai_character_shot", fake_shot)
    asyncio.run(main._generate_openai_character_images("Islam", "male", "", ["https://cdn.sylvex.ai/a.jpg"], "maximum"))
    assert "reconstruct" in seen[0].lower()


@pytest.fixture
def stub_character_pipeline(monkeypatch):
    async def fake_generate_images(name, gender, description, photos, processing_mode="ai_polish"):
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


def test_create_character_requires_photo_or_description(stub_character_pipeline):
    request = FakeRequest({"telegram_id": 42, "name": "Islam", "gender": "male"})
    result = asyncio.run(main.public_prostudio_create_character(request))
    assert result.status_code == 400
    import json
    assert json.loads(result.body)["error"] == "photo_or_description_required"


def test_create_character_scenario_b_text_only_succeeds_without_a_photo(stub_character_pipeline):
    request = FakeRequest({
        "telegram_id": 42,
        "name": "Nova",
        "gender": "female",
        "description": "cyberpunk hacker, neon jacket",
    })
    result = asyncio.run(main.public_prostudio_create_character(request))
    assert result["ok"] is True
    resource = result["resource"]
    assert resource["primaryReferenceUrl"] == "https://cdn.sylvex.ai/generated/primary.png"
    assert len(resource["referenceLibrary"]) == 4


def test_create_character_reference_library_uses_front_side_back_roles(stub_character_pipeline):
    request = FakeRequest({"telegram_id": 42, "name": "Islam", "gender": "male", "photos": ["https://cdn.sylvex.ai/a.jpg"]})
    result = asyncio.run(main.public_prostudio_create_character(request))
    roles = [entry["role"] for entry in result["resource"]["referenceLibrary"]]
    assert roles == ["Primary Face", "Full Body Front", "Full Body Side", "Full Body Back"]


def test_create_character_caps_photos_at_one(stub_character_pipeline, monkeypatch):
    received = {}

    async def fake_generate_images(name, gender, description, photos, processing_mode="ai_polish"):
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


def test_create_character_threads_processing_mode_through(stub_character_pipeline, monkeypatch):
    received = {}

    async def fake_generate_images(name, gender, description, photos, processing_mode="ai_polish"):
        received["processing_mode"] = processing_mode
        return [
            "https://cdn.sylvex.ai/generated/primary.png",
            "https://cdn.sylvex.ai/generated/front.png",
            "https://cdn.sylvex.ai/generated/side.png",
            "https://cdn.sylvex.ai/generated/back.png",
        ]

    monkeypatch.setattr(main, "_generate_openai_character_images", fake_generate_images)
    request = FakeRequest({
        "telegram_id": 42, "name": "Islam", "gender": "male",
        "photos": ["https://cdn.sylvex.ai/a.jpg"], "processing_mode": "preserve",
    })
    asyncio.run(main.public_prostudio_create_character(request))
    assert received["processing_mode"] == "preserve"


def test_create_character_survives_heygen_registration_failure(stub_character_pipeline, monkeypatch):
    # HeyGen's video-avatar registration is optional and must never block
    # Character creation itself (the standard reference set is the point
    # of this task; HeyGen is a separate, unrelated capability).
    def failing_heygen(name, avatar_url, references):
        raise RuntimeError("HEYGEN_API_KEY is not configured")

    monkeypatch.setattr(main, "_create_heygen_character", failing_heygen)
    request = FakeRequest({"telegram_id": 42, "name": "Islam", "gender": "male", "photos": ["https://cdn.sylvex.ai/a.jpg"]})
    result = asyncio.run(main.public_prostudio_create_character(request))
    assert result["ok"] is True
    resource = result["resource"]
    assert resource["heygenPhotoAvatarId"] == ""
    assert resource["heygenAvatarGroupId"] == ""
    # The standard reference set itself is unaffected by the HeyGen failure.
    assert resource["primaryReferenceUrl"] == "https://cdn.sylvex.ai/generated/primary.png"
    assert len(resource["referenceLibrary"]) == 4


# ---- _character_body_prompt: processing_mode support (Manual mode fix) ----

def test_character_body_prompt_preserve_is_minimal_intervention_and_differs_from_ai_polish():
    preserve_prompt = main._character_body_prompt("front", "Islam", "male", "", True, "preserve")
    polish_prompt = main._character_body_prompt("front", "Islam", "male", "", True, "ai_polish")
    assert "minimal intervention" in preserve_prompt
    assert "Do not change the pose" in preserve_prompt
    assert preserve_prompt != polish_prompt
    # Preserve must not pull in the standardized-studio wording that AI
    # Polish uses to restage the shot.
    assert "gray studio background" not in preserve_prompt
    assert "gray studio background" in polish_prompt


def test_character_body_prompt_defaults_to_ai_polish_when_processing_mode_omitted():
    default_prompt = main._character_body_prompt("side", "Islam", "male", "", True)
    polish_prompt = main._character_body_prompt("side", "Islam", "male", "", True, "ai_polish")
    assert default_prompt == polish_prompt


def test_character_body_prompt_preserve_has_no_effect_without_a_photo():
    # Scenario B's own body shots (no photo at all) always establish the
    # standardized look from scratch - there is nothing to "preserve".
    no_photo_prompt = main._character_body_prompt("back", "Islam", "male", "", False, "preserve")
    assert "gray studio background" in no_photo_prompt


# ---- public_prostudio_process_character_reference(): Manual mode's own
# per-slot AI processing endpoint ----

@pytest.fixture
def stub_manual_reference_processor(monkeypatch):
    calls = []

    async def fake_shot(prompt, reference_urls, quality="high"):
        calls.append({"prompt": prompt, "reference_urls": list(reference_urls)})
        return "https://cdn.sylvex.ai/processed/shot.png"

    monkeypatch.setattr(main, "_openai_character_shot", fake_shot)
    return calls


def test_process_character_reference_requires_telegram_id(stub_manual_reference_processor):
    request = FakeRequest({"role": "primary", "photo_url": "https://cdn.sylvex.ai/a.jpg"})
    result = asyncio.run(main.public_prostudio_process_character_reference(request))
    assert result.status_code == 400
    import json
    assert json.loads(result.body)["error"] == "telegram_id_required"


def test_process_character_reference_rejects_invalid_role(stub_manual_reference_processor):
    request = FakeRequest({"telegram_id": 42, "role": "profile", "photo_url": "https://cdn.sylvex.ai/a.jpg"})
    result = asyncio.run(main.public_prostudio_process_character_reference(request))
    assert result.status_code == 400
    import json
    assert json.loads(result.body)["error"] == "invalid_role"


def test_process_character_reference_requires_a_photo_url(stub_manual_reference_processor):
    request = FakeRequest({"telegram_id": 42, "role": "primary", "photo_url": ""})
    result = asyncio.run(main.public_prostudio_process_character_reference(request))
    assert result.status_code == 400
    import json
    assert json.loads(result.body)["error"] == "photo_url_required"


def test_process_character_reference_processes_primary_against_only_its_own_photo(stub_manual_reference_processor):
    request = FakeRequest({
        "telegram_id": 42, "role": "primary", "photo_url": "https://cdn.sylvex.ai/uploads/me.jpg",
        "name": "Islam", "gender": "male", "processing_mode": "ai_polish",
    })
    result = asyncio.run(main.public_prostudio_process_character_reference(request))
    assert result["ok"] is True
    assert result["url"] == "https://cdn.sylvex.ai/processed/shot.png"
    assert len(stub_manual_reference_processor) == 1
    call = stub_manual_reference_processor[0]
    # Each slot is processed against its own photo only - no chaining
    # against other slots, and no other slot is ever generated.
    assert call["reference_urls"] == ["https://cdn.sylvex.ai/uploads/me.jpg"]
    assert "Islam" in call["prompt"]


def test_process_character_reference_front_role_uses_the_standardized_body_prompt(stub_manual_reference_processor):
    request = FakeRequest({
        "telegram_id": 42, "role": "front", "photo_url": "https://cdn.sylvex.ai/uploads/front.jpg",
        "name": "Islam", "gender": "male", "processing_mode": "ai_polish",
    })
    asyncio.run(main.public_prostudio_process_character_reference(request))
    call = stub_manual_reference_processor[0]
    assert "front-facing view" in call["prompt"]
    assert call["reference_urls"] == ["https://cdn.sylvex.ai/uploads/front.jpg"]


def test_process_character_reference_threads_preserve_mode_through(stub_manual_reference_processor):
    request = FakeRequest({
        "telegram_id": 42, "role": "back", "photo_url": "https://cdn.sylvex.ai/uploads/back.jpg",
        "name": "Islam", "gender": "male", "processing_mode": "preserve",
    })
    asyncio.run(main.public_prostudio_process_character_reference(request))
    call = stub_manual_reference_processor[0]
    assert "minimal intervention" in call["prompt"]


def test_process_character_reference_unknown_processing_mode_falls_back_to_ai_polish(stub_manual_reference_processor):
    request = FakeRequest({
        "telegram_id": 42, "role": "side", "photo_url": "https://cdn.sylvex.ai/uploads/side.jpg",
        "name": "Islam", "gender": "male", "processing_mode": "maximum",
    })
    asyncio.run(main.public_prostudio_process_character_reference(request))
    call = stub_manual_reference_processor[0]
    assert "gray studio background" in call["prompt"]


def test_process_character_reference_surfaces_provider_failure(monkeypatch):
    async def failing_shot(prompt, reference_urls, quality="high"):
        raise RuntimeError("OpenAI character image generation failed (status=500): boom")

    monkeypatch.setattr(main, "_openai_character_shot", failing_shot)
    request = FakeRequest({
        "telegram_id": 42, "role": "primary", "photo_url": "https://cdn.sylvex.ai/uploads/me.jpg",
        "name": "Islam", "gender": "male",
    })
    result = asyncio.run(main.public_prostudio_process_character_reference(request))
    assert result.status_code == 502
