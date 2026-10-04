"""Regression tests for the final simplified Character creation flow,
now running as an async SYLVEX job instead of a synchronous long-running
POST.

Covers:
  - public_prostudio_create_character(): validates the request, creates a
    persistent character_creation job row, and returns 202 with a job_id
    immediately - it never awaits the actual generation. The user still
    supplies exactly one source photo (mandatory, capped at 1 even if
    more are submitted) plus an optional text field - no Manual/Create-
    with-AI modes, no processing modes, no multiple upload slots (all of
    that was Character Creation V2 and has been reverted).
  - create_character_creation_job(): inserts a prostudio_generation_jobs
    row with mode='character_creation', status already 'processing' (so
    the generic image/video/music/voice worker pool - which only claims
    'queued' rows - can never race it into "Unknown generation mode").
  - _run_character_creation_job(): the actual background worker. Generates
    the standard 4-reference set (Main identity, Full Body Front/Side/
    Back, chaining Front/Side/Back off the Main identity shot and the
    previously generated body shot so identity/clothing stay locked
    across the set - never four independently reinterpreted generations),
    stores the Character resource exactly as the old synchronous endpoint
    did, and marks the job completed with character_id + the full
    resource payload (or failed, with the backend's error, on exception).
  - _generate_openai_character_images() itself (prompts, chaining) is
    byte-for-byte unchanged by this conversion.
  - reference_library role labels: Primary Face / Full Body Front / Full
    Body Side / Full Body Back.

Does not touch the already-fixed Character generation/reference-selection
payload logic, and does not test Object creation (unaffected by this
change).
"""
import asyncio
import json

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


def test_primary_prompt_asks_for_a_confident_professional_model_pose(monkeypatch):
    # Fix 3: the Primary/main identity shot must look like the person
    # posing for a professional photographer - direct camera engagement,
    # confident expressive eyes, a strong gaze - not a dead-eyed or
    # accidental-selfie look, and the identity must stay explicitly locked.
    calls = []

    async def fake_shot(prompt, reference_urls, quality="high"):
        calls.append(prompt)
        return "https://cdn.sylvex.ai/shot.png"

    monkeypatch.setattr(main, "_openai_character_shot", fake_shot)
    asyncio.run(main._generate_openai_character_images("Islam", "male", "", ["https://cdn.sylvex.ai/a.jpg"]))
    primary_prompt = calls[0]

    for phrase in (
        "direct engagement",
        "professional model-like facial posing",
        "expressive and confident eyes",
        "strong, intentional gaze",
        "natural but photogenic",
        "chest-up or waist-up",
    ):
        assert phrase in primary_prompt, f"missing expected pose guidance: {phrase!r}"

    for phrase in ("blank or dead expression", "accidental-selfie look", "looking away"):
        assert phrase in primary_prompt, f"missing expected negative guidance: {phrase!r}"

    # Identity must still be explicitly protected - this is a pose change,
    # never an identity change.
    assert "preserve the person's real identity exactly" in primary_prompt
    assert "do not" in primary_prompt.lower() and "facial identity" in primary_prompt


def test_identity_prompt_includes_description_only_when_provided():
    with_text = main._character_identity_prompt("Islam", "male", "tall, athletic build")
    without_text = main._character_identity_prompt("Islam", "male", "")
    assert "tall, athletic build" in with_text
    assert "tall, athletic build" not in without_text
    assert "Islam" in with_text and "Islam" in without_text


# ---- create_character_creation_job(): the DB insert ----

class FakeCursor:
    def __init__(self):
        self.executed = []

    def execute(self, sql, params=None):
        self.executed.append((sql, params))

    def close(self):
        pass


class FakeConnection:
    def __init__(self, cursor):
        self._cursor = cursor
        self.committed = False

    def cursor(self):
        return self._cursor

    def commit(self):
        self.committed = True

    def close(self):
        pass


def test_create_character_creation_job_requires_a_database(monkeypatch):
    monkeypatch.setattr(main, "DATABASE_URL", "")
    with pytest.raises(main.SecurityError):
        main.create_character_creation_job(42, "Islam", "male", "tall", ["https://cdn.sylvex.ai/a.jpg"])


def test_create_character_creation_job_inserts_an_already_processing_row(monkeypatch):
    cursor = FakeCursor()
    connection = FakeConnection(cursor)
    monkeypatch.setattr(main, "DATABASE_URL", "postgres://test")
    monkeypatch.setattr(main, "db_connect", lambda url: connection)
    monkeypatch.setattr(main, "ensure_prostudio_table", lambda: None)

    job_id = main.create_character_creation_job(42, "Islam", "male", "tall", ["https://cdn.sylvex.ai/a.jpg"])

    assert job_id
    assert connection.committed is True
    assert len(cursor.executed) == 1
    sql, params = cursor.executed[0]
    # Never 'queued' - a queued row would race the generic worker pool's
    # claim_next_prostudio_generation_job() (which only looks at 'queued'
    # rows for ANY mode) into failing it with "Unknown generation mode"
    # before this job's own background task gets a chance to run.
    assert "'processing'" in sql
    assert "'queued'" not in sql
    assert "character_creation" in sql
    assert params[0] == job_id
    assert params[1] == 42
    request_json = json.loads(params[3])
    assert request_json == {
        "name": "Islam", "gender": "male", "description": "tall",
        "photos": ["https://cdn.sylvex.ai/a.jpg"],
    }


# ---- _run_character_creation_job(): the background worker ----

@pytest.fixture
def stub_character_pipeline(monkeypatch):
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
    return fake_generate_images


def _capture_job_updates(monkeypatch):
    updates = []
    monkeypatch.setattr(
        main, "update_prostudio_generation_job",
        lambda job_id, status, result=None, error=None, conversation_id="": updates.append((job_id, status, result, error)),
    )
    return updates


def test_run_character_creation_job_marks_completed_with_character_id_and_resource(stub_character_pipeline, monkeypatch):
    updates = _capture_job_updates(monkeypatch)

    asyncio.run(main._run_character_creation_job("job-1", 42, "Islam", "male", "", ["https://cdn.sylvex.ai/a.jpg"]))

    assert len(updates) == 1
    job_id, status, result, error = updates[0]
    assert job_id == "job-1"
    assert status == "completed"
    assert error is None
    assert result["ok"] is True
    resource = result["resource"]
    assert result["character_id"] == resource["id"]
    assert resource["id"].startswith("custom_character_")
    assert resource["primaryReferenceUrl"] == "https://cdn.sylvex.ai/generated/primary.png"
    assert resource["primaryReferenceUrl"] == resource["avatarUrl"]
    assert len(resource["referenceLibrary"]) == 4
    # generation_result_urls() falls back to this key for any mode it does
    # not specifically recognise, which is what lets the poll endpoint
    # treat this job as genuinely completed.
    assert result["result_url"] == resource["previewUrl"]


def test_run_character_creation_job_reference_library_uses_main_front_side_back_roles(stub_character_pipeline, monkeypatch):
    updates = _capture_job_updates(monkeypatch)
    asyncio.run(main._run_character_creation_job("job-1", 42, "Islam", "male", "", ["https://cdn.sylvex.ai/a.jpg"]))
    roles = [entry["role"] for entry in updates[0][2]["resource"]["referenceLibrary"]]
    assert roles == ["Primary Face", "Full Body Front", "Full Body Side", "Full Body Back"]


def test_run_character_creation_job_keeps_source_photo_only_as_metadata(stub_character_pipeline, monkeypatch):
    # The raw uploaded source photo must not become a 5th Character
    # reference - it is kept only as originalSourceImages metadata.
    updates = _capture_job_updates(monkeypatch)
    asyncio.run(main._run_character_creation_job("job-1", 42, "Islam", "male", "", ["https://cdn.sylvex.ai/source.jpg"]))
    resource = updates[0][2]["resource"]
    assert resource["originalSourceImages"] == ["https://cdn.sylvex.ai/source.jpg"]
    assert "https://cdn.sylvex.ai/source.jpg" not in resource["referenceImages"]
    assert all(entry["url"] != "https://cdn.sylvex.ai/source.jpg" for entry in resource["referenceLibrary"])


def test_run_character_creation_job_marks_failed_on_generation_error(monkeypatch):
    async def failing_generate(name, gender, description, photos):
        raise RuntimeError("OpenAI character image generation failed (status=500): boom")

    monkeypatch.setattr(main, "_generate_openai_character_images", failing_generate)
    updates = _capture_job_updates(monkeypatch)

    asyncio.run(main._run_character_creation_job("job-2", 42, "Islam", "male", "", ["https://cdn.sylvex.ai/a.jpg"]))

    assert len(updates) == 1
    job_id, status, result, error = updates[0]
    assert status == "failed"
    assert result is None
    assert error["ok"] is False
    assert "boom" in error["error"]


def test_run_character_creation_job_translates_billing_limit_errors(monkeypatch):
    async def failing_generate(name, gender, description, photos):
        raise RuntimeError("OpenAI billing hard limit has been reached")

    monkeypatch.setattr(main, "_generate_openai_character_images", failing_generate)
    updates = _capture_job_updates(monkeypatch)

    asyncio.run(main._run_character_creation_job("job-3", 42, "Islam", "male", "", ["https://cdn.sylvex.ai/a.jpg"]))

    _, status, _, error = updates[0]
    assert status == "failed"
    assert "Лимит расходов OpenAI" in error["error"]


# ---- public_prostudio_create_character(): validation + 202 response ----

def test_create_character_requires_a_photo():
    request = FakeRequest({"telegram_id": 42, "name": "Islam", "gender": "male", "description": "tall"})
    result = asyncio.run(main.public_prostudio_create_character(request))
    assert result.status_code == 400
    assert json.loads(result.body)["error"] == "reference_image_required"


def test_create_character_requires_a_name():
    request = FakeRequest({"telegram_id": 42, "name": "A", "gender": "male", "photos": ["https://cdn.sylvex.ai/a.jpg"]})
    result = asyncio.run(main.public_prostudio_create_character(request))
    assert result.status_code == 400
    assert json.loads(result.body)["error"] == "name_required"


def test_create_character_requires_telegram_id():
    request = FakeRequest({"name": "Islam", "gender": "male", "photos": ["https://cdn.sylvex.ai/a.jpg"]})
    result = asyncio.run(main.public_prostudio_create_character(request))
    assert result.status_code == 400
    assert json.loads(result.body)["error"] == "telegram_id_required"


def test_create_character_caps_photos_at_exactly_one_before_queuing(monkeypatch):
    received = {}
    monkeypatch.setattr(main, "create_character_creation_job", lambda telegram_id, name, gender, description, photos: received.setdefault("photos", list(photos)) or "job-xyz")

    async def noop_worker(*a, **k):
        pass

    monkeypatch.setattr(main, "_run_character_creation_job", noop_worker)
    request = FakeRequest({
        "telegram_id": 42, "name": "Islam", "gender": "male",
        "photos": ["https://cdn.sylvex.ai/a.jpg", "https://cdn.sylvex.ai/b.jpg", "https://cdn.sylvex.ai/c.jpg"],
    })
    asyncio.run(main.public_prostudio_create_character(request))
    assert received["photos"] == ["https://cdn.sylvex.ai/a.jpg"]


def test_create_character_returns_202_with_job_id_without_waiting_for_generation(monkeypatch):
    finished = {"value": False}

    monkeypatch.setattr(main, "create_character_creation_job", lambda *a, **k: "job-xyz")

    async def slow_worker(job_id, telegram_id, name, gender, description, photos):
        await asyncio.sleep(0.05)
        finished["value"] = True

    monkeypatch.setattr(main, "_run_character_creation_job", slow_worker)
    # Give the endpoint a real list to keep a strong reference to its
    # fire-and-forget task, exactly like the startup event does in
    # production - otherwise nothing in this test holds the task alive.
    main.app.state.background_tasks = []

    async def scenario():
        request = FakeRequest({"telegram_id": 42, "name": "Islam", "gender": "male", "photos": ["https://cdn.sylvex.ai/a.jpg"]})
        result = await main.public_prostudio_create_character(request)
        assert result.status_code == 202
        body = json.loads(result.body)
        assert body == {"ok": True, "job_id": "job-xyz", "status": "processing"}
        # The response came back before the background worker's sleep
        # resolved - Character creation runs after the response is sent,
        # not before it (so a disconnected client never blocks it).
        assert finished["value"] is False
        await asyncio.sleep(0.2)
        assert finished["value"] is True

    asyncio.run(scenario())


def test_create_character_job_creation_failure_surfaces_as_502(monkeypatch):
    def failing_create_job(*a, **k):
        raise RuntimeError("db exploded")

    monkeypatch.setattr(main, "create_character_creation_job", failing_create_job)
    request = FakeRequest({"telegram_id": 42, "name": "Islam", "gender": "male", "photos": ["https://cdn.sylvex.ai/a.jpg"]})
    result = asyncio.run(main.public_prostudio_create_character(request))
    assert result.status_code == 502
    assert "db exploded" in json.loads(result.body)["error"]
