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
import datetime as dt
import json
from contextlib import contextmanager

import pytest

import main


@pytest.fixture(autouse=True)
def _creation_job_settlement(monkeypatch):
    """Character/Object creation now reserves a composed SYLVEX price at job
    creation and settles it on success (see test_billing_coverage.py); the
    settlement is recorded here instead of touching a database."""
    charges = []
    monkeypatch.setattr(
        main, "charge_generation_balance",
        lambda telegram_id, job_id, result, payload: charges.append((job_id, payload["price_snapshot"]["final_credits"])) or {"charged": True},
    )
    return charges


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
    result = asyncio.run(main._generate_openai_character_images("job-chain", "Islam", "male", "tall, athletic", photos))

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
    # Fix: once Primary succeeds, the raw uploaded source photo must never
    # be resent - Front/Side/Back are generated only from the already
    # normalized, already-generated Character references, chained forward:
    # Front <- Primary; Side <- Primary+Front; Back <- Primary+Front+Side.
    assert front_refs == ["https://cdn.sylvex.ai/shot_1.png"]
    assert "https://cdn.sylvex.ai/uploads/source.jpg" not in front_refs
    assert side_refs == ["https://cdn.sylvex.ai/shot_1.png", "https://cdn.sylvex.ai/shot_2.png"]
    assert back_refs == ["https://cdn.sylvex.ai/shot_1.png", "https://cdn.sylvex.ai/shot_2.png", "https://cdn.sylvex.ai/shot_3.png"]

    assert "Islam" in primary_prompt
    assert "chest-up or waist-up" in primary_prompt

    # Each body prompt explicitly requests a fully clothed, neutral,
    # non-sexual technical reference - the production fix for gpt-image-2
    # rejecting "Full Body Front" with safety_violations=[sexual].
    for body_prompt in (front_prompt, side_prompt, back_prompt):
        assert "non-sexual" in body_prompt
        assert "non-suggestive" in body_prompt
        assert "fully clothed" in body_prompt
        assert "ordinary" in body_prompt and "non-revealing clothing" in body_prompt
        assert "no lingerie" in body_prompt.lower()
        assert "no underwear" in body_prompt.lower()
        assert "no swimwear" in body_prompt.lower()
        assert "transparent clothing" in body_prompt
        assert "no exposed intimate areas" in body_prompt.lower()
        assert "erotic or suggestive presentation" in body_prompt
        assert "do not sexualize or exaggerate body proportions" in body_prompt.lower()
        assert "no provocative posing" in body_prompt.lower()
        assert "body-emphasizing pose" in body_prompt
        assert "glamour" in body_prompt.lower() and "body-focused composition" in body_prompt
        assert "gray studio background" in body_prompt
        assert "never invent different trousers, shoes, jackets" in body_prompt
        assert "never infer lingerie, underwear, swimwear, transparent" in body_prompt

    # Per-view framing instructions.
    assert "Front: Full-body front view, standing straight and facing directly toward the camera." in front_prompt
    assert "Side: Strict full-body side/profile view." in side_prompt
    assert "Back: Strict full-body back view, facing directly away from the camera." in back_prompt


def test_generate_character_images_records_progress_after_each_stage(monkeypatch):
    # Use the new existing stage logs to expose a simple job stage
    # (primary/front/side/back/saving/completed) with completed_references
    # and, once known, the Primary Face URL - so the pending Character
    # card can show "1/4", "2/4", "3/4" and a progressive preview instead
    # of a flat "Creating..." for the whole run.
    urls = iter([
        "https://cdn.sylvex.ai/primary.png",
        "https://cdn.sylvex.ai/front.png",
        "https://cdn.sylvex.ai/side.png",
        "https://cdn.sylvex.ai/back.png",
    ])

    async def fake_shot(prompt, reference_urls, quality="high"):
        return next(urls)

    monkeypatch.setattr(main, "_openai_character_shot", fake_shot)
    progress_updates = _capture_job_updates(monkeypatch)

    asyncio.run(main._generate_openai_character_images("job-progress", "Islam", "male", "", ["https://cdn.sylvex.ai/a.jpg"]))

    stages = [(entry[0], entry[1], entry[2]) for entry in progress_updates]
    assert stages == [
        ("job-progress", "processing", {"stage": "front", "completed_references": 1, "total_references": 4, "primary_url": "https://cdn.sylvex.ai/primary.png"}),
        ("job-progress", "processing", {"stage": "side", "completed_references": 2, "total_references": 4, "primary_url": "https://cdn.sylvex.ai/primary.png"}),
        ("job-progress", "processing", {"stage": "back", "completed_references": 3, "total_references": 4, "primary_url": "https://cdn.sylvex.ai/primary.png"}),
    ]


def test_generate_character_images_works_with_no_optional_text(monkeypatch):
    calls = []

    async def fake_shot(prompt, reference_urls, quality="high"):
        calls.append(prompt)
        return "https://cdn.sylvex.ai/shot.png"

    monkeypatch.setattr(main, "_openai_character_shot", fake_shot)
    result = asyncio.run(main._generate_openai_character_images("job-nova", "Nova", "female", "", ["https://cdn.sylvex.ai/a.jpg"]))
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
    asyncio.run(main._generate_openai_character_images("job-pose", "Islam", "male", "", ["https://cdn.sylvex.ai/a.jpg"]))
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
        main.create_character_creation_job(42, "Islam", "male", "tall", ["https://cdn.sylvex.ai/a.jpg"], 132)


def test_create_character_creation_job_inserts_an_already_processing_row(monkeypatch):
    cursor = FakeCursor()
    connection = FakeConnection(cursor)
    monkeypatch.setattr(main, "DATABASE_URL", "postgres://test")
    monkeypatch.setattr(main, "db_connect", lambda url: connection)
    monkeypatch.setattr(main, "ensure_prostudio_table", lambda: None)
    monkeypatch.setattr(main, "ensure_reservations", lambda connect: None)
    reserved = []
    monkeypatch.setattr(main, "reserve_generation", lambda cur, uid, job_id, credits: reserved.append((uid, job_id, credits)))

    job_id = main.create_character_creation_job(42, "Islam", "male", "tall", ["https://cdn.sylvex.ai/a.jpg"], 132)

    assert job_id
    assert connection.committed is True
    # The composed price is reserved in the same transaction as the insert.
    assert reserved == [(42, job_id, 132)]
    inserts = [entry for entry in cursor.executed if "INSERT INTO prostudio_generation_jobs" in entry[0]]
    assert len(inserts) == 1
    sql, params = inserts[0]
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
    assert request_json.pop("price_snapshot")["final_credits"] == 132
    assert request_json == {
        "name": "Islam", "gender": "male", "description": "tall",
        "photos": ["https://cdn.sylvex.ai/a.jpg"],
    }


# ---- _run_character_creation_job(): the background worker ----

@pytest.fixture
def stub_character_pipeline(monkeypatch):
    async def fake_generate_images(job_id, name, gender, description, photos):
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
    # Captures every update_prostudio_generation_job call, including the
    # new mid-job progress writes (status stays 'processing' for those -
    # see _record_character_job_progress) - not just the single terminal
    # completed/failed call older tests assumed was the only one.
    updates = []
    monkeypatch.setattr(
        main, "update_prostudio_generation_job",
        lambda job_id, status, result=None, error=None, conversation_id="": updates.append((job_id, status, result, error)),
    )
    return updates


def _terminal_update(updates):
    terminal = [entry for entry in updates if entry[1] in ("completed", "failed")]
    assert len(terminal) == 1, f"expected exactly one terminal (completed/failed) update, got {terminal}"
    return terminal[0]


def test_run_character_creation_job_marks_completed_with_character_id_and_resource(stub_character_pipeline, monkeypatch):
    updates = _capture_job_updates(monkeypatch)

    asyncio.run(main._run_character_creation_job("job-1", 42, "Islam", "male", "", ["https://cdn.sylvex.ai/a.jpg"], credits=132))

    job_id, status, result, error = _terminal_update(updates)
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
    asyncio.run(main._run_character_creation_job("job-1", 42, "Islam", "male", "", ["https://cdn.sylvex.ai/a.jpg"], credits=132))
    _, _, result, _ = _terminal_update(updates)
    roles = [entry["role"] for entry in result["resource"]["referenceLibrary"]]
    assert roles == ["Primary Face", "Full Body Front", "Full Body Side", "Full Body Back"]


def test_run_character_creation_job_keeps_source_photo_only_as_metadata(stub_character_pipeline, monkeypatch):
    # The raw uploaded source photo must not become a 5th Character
    # reference - it is kept only as originalSourceImages metadata.
    updates = _capture_job_updates(monkeypatch)
    asyncio.run(main._run_character_creation_job("job-1", 42, "Islam", "male", "", ["https://cdn.sylvex.ai/source.jpg"], credits=132))
    _, _, terminal_result, _ = _terminal_update(updates)
    resource = terminal_result["resource"]
    assert resource["originalSourceImages"] == ["https://cdn.sylvex.ai/source.jpg"]
    assert "https://cdn.sylvex.ai/source.jpg" not in resource["referenceImages"]
    assert all(entry["url"] != "https://cdn.sylvex.ai/source.jpg" for entry in resource["referenceLibrary"])


def test_run_character_creation_job_marks_failed_on_generation_error(monkeypatch):
    async def failing_generate(job_id, name, gender, description, photos):
        raise RuntimeError("OpenAI character image generation failed (status=500): boom")

    monkeypatch.setattr(main, "_generate_openai_character_images", failing_generate)
    updates = _capture_job_updates(monkeypatch)

    asyncio.run(main._run_character_creation_job("job-2", 42, "Islam", "male", "", ["https://cdn.sylvex.ai/a.jpg"], credits=132))

    assert len(updates) == 1
    job_id, status, result, error = updates[0]
    assert status == "failed"
    assert result is None
    assert error["ok"] is False
    assert "boom" in error["error"]


def test_run_character_creation_job_translates_billing_limit_errors(monkeypatch):
    async def failing_generate(job_id, name, gender, description, photos):
        raise RuntimeError("OpenAI billing hard limit has been reached")

    monkeypatch.setattr(main, "_generate_openai_character_images", failing_generate)
    updates = _capture_job_updates(monkeypatch)

    asyncio.run(main._run_character_creation_job("job-3", 42, "Islam", "male", "", ["https://cdn.sylvex.ai/a.jpg"], credits=132))

    _, status, _, error = updates[0]
    assert status == "failed"
    assert "Лимит расходов OpenAI" in error["error"]


def test_run_character_creation_job_translates_safety_violation_errors_into_a_clean_message(monkeypatch):
    # Production evidence: gpt-image-2 rejected "Full Body Front" with
    # status=400 safety_violations=[sexual]. The job must still terminate
    # normally as failed (never bypass/retry around provider safety), and
    # the user-facing error must be a clean, generic message - never the
    # raw provider diagnostic/status/payload fragment that
    # _openai_character_shot folds into the exception.
    async def failing_generate(job_id, name, gender, description, photos):
        raise RuntimeError(
            "OpenAI character image generation failed (status=400, model=gpt-image-2): "
            "safety_violations=[sexual]"
        )

    monkeypatch.setattr(main, "_generate_openai_character_images", failing_generate)
    updates = _capture_job_updates(monkeypatch)

    asyncio.run(main._run_character_creation_job("job-4", 42, "Islam", "male", "", ["https://cdn.sylvex.ai/a.jpg"], credits=132))

    assert len(updates) == 1
    job_id, status, result, error = updates[0]
    assert status == "failed"
    assert result is None
    assert error["ok"] is False
    # Clean, generic - no raw provider diagnostic, status code, or payload.
    assert "safety_violations" not in error["error"]
    assert "status=400" not in error["error"]
    assert "sexual" not in error["error"].lower()
    assert len(error["error"]) > 0


# ---- Continuous heartbeat + terminal-job guard (stale status / delayed
# "ghost Character" appearance fix) ----

def test_run_character_creation_job_heartbeats_continuously_during_generation(monkeypatch):
    # Production bug: the only heartbeat write happened once, *after*
    # _generate_openai_character_images() had already finished - so a
    # Character creation taking longer than the stale-recovery threshold
    # could be wrongly marked 'failed' by requeue_stale_prostudio_jobs()
    # while all four GPT Image calls were still genuinely running. The fix
    # is a background heartbeat loop that ticks for the job's whole
    # lifetime. Shrink the tick interval so this test proves multiple
    # ticks happen during a still-running generation, without a real
    # 20-30s sleep.
    monkeypatch.setattr(main, "CHARACTER_CREATION_HEARTBEAT_SECONDS", 0.01)
    heartbeats = []
    monkeypatch.setattr(main, "heartbeat_prostudio_generation_job", lambda job_id: heartbeats.append(job_id))
    monkeypatch.setattr(main, "save_prostudio_resource", lambda telegram_id, resource: resource)
    monkeypatch.setattr(main, "get_prostudio_generation_job_status", lambda job_id: "processing")
    updates = _capture_job_updates(monkeypatch)

    async def slow_generate(job_id, name, gender, description, photos):
        await asyncio.sleep(0.08)
        return [
            "https://cdn.sylvex.ai/generated/primary.png",
            "https://cdn.sylvex.ai/generated/front.png",
            "https://cdn.sylvex.ai/generated/side.png",
            "https://cdn.sylvex.ai/generated/back.png",
        ]

    monkeypatch.setattr(main, "_generate_openai_character_images", slow_generate)

    asyncio.run(main._run_character_creation_job("job-heartbeat", 42, "Islam", "male", "", ["https://cdn.sylvex.ai/a.jpg"], credits=132))

    # Several ticks happened *while generation was still running* - not
    # just one heartbeat fired after it already finished.
    assert len(heartbeats) >= 2
    assert all(job_id == "job-heartbeat" for job_id in heartbeats)
    _, status, _, _ = _terminal_update(updates)
    assert status == "completed"


def test_run_character_creation_job_skips_resource_save_when_job_already_terminal(monkeypatch):
    # If the job has already gone genuinely terminal (failed/cancelled) by
    # the time all four GPT Image calls finish, the Character resource
    # must never be created. This is what prevents a "ghost Character"
    # from materializing later - via the ordinary catalog refresh - after
    # the UI already received a real terminal failure for this job.
    save_calls = []
    monkeypatch.setattr(main, "save_prostudio_resource", lambda telegram_id, resource: save_calls.append(resource) or resource)
    monkeypatch.setattr(main, "get_prostudio_generation_job_status", lambda job_id: "failed")
    monkeypatch.setattr(main, "heartbeat_prostudio_generation_job", lambda job_id: None)

    async def fake_generate(job_id, name, gender, description, photos):
        return [
            "https://cdn.sylvex.ai/generated/primary.png",
            "https://cdn.sylvex.ai/generated/front.png",
            "https://cdn.sylvex.ai/generated/side.png",
            "https://cdn.sylvex.ai/generated/back.png",
        ]

    monkeypatch.setattr(main, "_generate_openai_character_images", fake_generate)
    updates = _capture_job_updates(monkeypatch)

    asyncio.run(main._run_character_creation_job("job-terminal", 42, "Islam", "male", "", ["https://cdn.sylvex.ai/a.jpg"], credits=132))

    assert save_calls == []
    # The already-terminal job row is left exactly as it was - this
    # function never re-affirms or overwrites it.
    assert updates == []


def test_run_character_creation_job_cancelled_status_also_blocks_resource_save(monkeypatch):
    save_calls = []
    monkeypatch.setattr(main, "save_prostudio_resource", lambda telegram_id, resource: save_calls.append(resource) or resource)
    monkeypatch.setattr(main, "get_prostudio_generation_job_status", lambda job_id: "cancelled")
    monkeypatch.setattr(main, "heartbeat_prostudio_generation_job", lambda job_id: None)

    async def fake_generate(job_id, name, gender, description, photos):
        return [
            "https://cdn.sylvex.ai/generated/primary.png",
            "https://cdn.sylvex.ai/generated/front.png",
            "https://cdn.sylvex.ai/generated/side.png",
            "https://cdn.sylvex.ai/generated/back.png",
        ]

    monkeypatch.setattr(main, "_generate_openai_character_images", fake_generate)
    updates = _capture_job_updates(monkeypatch)

    asyncio.run(main._run_character_creation_job("job-cancelled", 42, "Islam", "male", "", ["https://cdn.sylvex.ai/a.jpg"], credits=132))

    assert save_calls == []
    assert updates == []


def test_run_character_creation_job_full_regression_long_running_completes_exactly_once(monkeypatch):
    # The exact production scenario: a Character job runs longer than the
    # stale-recovery threshold; stale recovery runs during it (checked via
    # get_prostudio_generation_job_status staying 'processing' - i.e. the
    # continuous heartbeat kept it from ever being marked failed); all 4
    # references finish; the Character resource is created exactly once;
    # the job becomes 'completed'; and the result handed back is the full
    # resource the frontend needs to show the Character immediately - no
    # second, later-appearing Character and no 'failed' status anywhere.
    monkeypatch.setattr(main, "CHARACTER_CREATION_HEARTBEAT_SECONDS", 0.01)
    monkeypatch.setattr(main, "get_prostudio_generation_job_status", lambda job_id: "processing")
    save_calls = []
    monkeypatch.setattr(main, "save_prostudio_resource", lambda telegram_id, resource: save_calls.append(resource) or resource)
    monkeypatch.setattr(main, "heartbeat_prostudio_generation_job", lambda job_id: None)
    updates = _capture_job_updates(monkeypatch)

    async def slow_generate(job_id, name, gender, description, photos):
        await asyncio.sleep(0.05)
        return [
            "https://cdn.sylvex.ai/generated/primary.png",
            "https://cdn.sylvex.ai/generated/front.png",
            "https://cdn.sylvex.ai/generated/side.png",
            "https://cdn.sylvex.ai/generated/back.png",
        ]

    monkeypatch.setattr(main, "_generate_openai_character_images", slow_generate)

    asyncio.run(main._run_character_creation_job("job-long", 42, "Islam", "male", "", ["https://cdn.sylvex.ai/a.jpg"], credits=132))

    assert len(save_calls) == 1
    job_id, status, result, error = _terminal_update(updates)
    assert status == "completed"
    assert error is None
    assert result["ok"] is True
    assert result["resource"]["id"] == save_calls[0]["id"]
    # The progress writes along the way (front/side/back/saving) must
    # never themselves flip the job to a terminal status - only this one
    # final 'completed' write does.
    assert all(entry[1] in ("processing", "completed") for entry in updates)
    saving_updates = [entry for entry in updates if entry[1] == "processing" and entry[2] and entry[2].get("stage") == "saving"]
    assert len(saving_updates) == 1
    assert saving_updates[0][2]["completed_references"] == 4
    assert saving_updates[0][2]["total_references"] == 4


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
    monkeypatch.setattr(main, "create_character_creation_job", lambda telegram_id, name, gender, description, photos, credits=0: received.setdefault("photos", list(photos)) or "job-xyz")

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

    async def slow_worker(job_id, telegram_id, name, gender, description, photos, credits=0):
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


# ---- public_prostudio_character_creation_jobs(): owner-scoped list used
# by the frontend's pending-Character-card restore-on-reload flow ----

class _JobsListFakeCursor:
    def __init__(self, rows):
        self.rows = rows
        self.executed = []

    def execute(self, sql, params=None):
        self.executed.append((sql, params))

    def fetchall(self):
        return self.rows

    def close(self):
        pass


class _JobsListFakeConnection:
    def __init__(self, cursor):
        self._cursor = cursor

    def cursor(self):
        return self._cursor


def _patch_jobs_list_db(monkeypatch, rows, database_url="postgres://fake"):
    cursor = _JobsListFakeCursor(rows)

    @contextmanager
    def fake_db_connection(url):
        yield _JobsListFakeConnection(cursor)

    monkeypatch.setattr(main, "DATABASE_URL", database_url)
    monkeypatch.setattr(main, "db_connection", fake_db_connection)
    monkeypatch.setattr(main, "ensure_prostudio_table", lambda: None)
    return cursor


def test_character_creation_jobs_endpoint_requires_telegram_id():
    result = asyncio.run(main.public_prostudio_character_creation_jobs(0))
    assert result.status_code == 400
    assert json.loads(result.body)["error"] == "telegram_id_required"


def test_character_creation_jobs_endpoint_returns_empty_list_without_database(monkeypatch):
    monkeypatch.setattr(main, "DATABASE_URL", "")
    result = asyncio.run(main.public_prostudio_character_creation_jobs(42))
    assert result == {"ok": True, "jobs": []}


def test_character_creation_jobs_endpoint_scopes_query_to_the_requesting_telegram_id(monkeypatch):
    # The only thing that can ever select a row here is WHERE
    # telegram_id = %s - there is no path by which this can return
    # another user's jobs.
    cursor = _patch_jobs_list_db(monkeypatch, [])
    asyncio.run(main.public_prostudio_character_creation_jobs(777))
    sql, params = cursor.executed[0]
    assert "character_creation" in sql
    assert "telegram_id = %s" in sql
    assert params == (777,)

    cursor2 = _patch_jobs_list_db(monkeypatch, [])
    asyncio.run(main.public_prostudio_character_creation_jobs(456))
    _, params2 = cursor2.executed[0]
    assert params2 == (456,)


def test_character_creation_jobs_endpoint_shapes_a_processing_job_with_progress(monkeypatch):
    created = dt.datetime(2026, 1, 1, 12, 0, 0)
    updated = dt.datetime(2026, 1, 1, 12, 5, 0)
    rows = [(
        "job-1", "processing",
        {"name": "Islam", "gender": "male", "description": "tall", "photos": ["https://cdn.sylvex.ai/a.jpg"]},
        {"stage": "side", "completed_references": 2, "total_references": 4, "primary_url": "https://cdn.sylvex.ai/primary.png"},
        None,
        created, updated,
    )]
    _patch_jobs_list_db(monkeypatch, rows)

    result = asyncio.run(main.public_prostudio_character_creation_jobs(42))

    assert result["ok"] is True
    assert len(result["jobs"]) == 1
    job = result["jobs"][0]
    assert job["job_id"] == "job-1"
    assert job["status"] == "processing"
    assert job["name"] == "Islam"
    assert job["gender"] == "male"
    assert job["description"] == "tall"
    assert job["photos"] == ["https://cdn.sylvex.ai/a.jpg"]
    assert job["created_at"] == created.isoformat()
    assert job["updated_at"] == updated.isoformat()
    assert job["result"]["stage"] == "side"
    assert job["result"]["completed_references"] == 2
    assert job["result"]["total_references"] == 4
    assert job["result"]["primary_url"] == "https://cdn.sylvex.ai/primary.png"
    assert job["error"] is None


def test_character_creation_jobs_endpoint_includes_a_completed_job_with_its_resource(monkeypatch):
    rows = [(
        "job-done", "completed",
        {"name": "Nova", "gender": "female", "description": "", "photos": ["https://cdn.sylvex.ai/b.jpg"]},
        {"ok": True, "character_id": "custom_character_abc", "resource": {"id": "custom_character_abc"}, "result_url": "https://cdn.sylvex.ai/p.png"},
        None,
        dt.datetime(2026, 1, 1), dt.datetime(2026, 1, 1),
    )]
    _patch_jobs_list_db(monkeypatch, rows)

    result = asyncio.run(main.public_prostudio_character_creation_jobs(42))

    job = result["jobs"][0]
    assert job["status"] == "completed"
    assert job["result"]["resource"]["id"] == "custom_character_abc"
    assert job["error"] is None


def test_character_creation_jobs_endpoint_sanitizes_a_failed_jobs_error(monkeypatch):
    # The same whitelist/translation the single-job GET endpoint already
    # applies - an error record can carry raw provider/exception text
    # (raw_error, traceback, secrets), which must never reach the client.
    rows = [(
        "job-2", "failed",
        {"name": "Nova", "gender": "female", "description": "", "photos": ["https://cdn.sylvex.ai/b.jpg"]},
        None,
        {"ok": False, "error": "boom", "raw_error": "Traceback ... api_key=sk-secret"},
        dt.datetime(2026, 1, 1), dt.datetime(2026, 1, 1),
    )]
    _patch_jobs_list_db(monkeypatch, rows)

    result = asyncio.run(main.public_prostudio_character_creation_jobs(42))

    job = result["jobs"][0]
    assert job["status"] == "failed"
    assert "raw_error" not in job["error"]
    assert "sk-secret" not in str(job["error"])


def test_character_creation_jobs_endpoint_list_failure_surfaces_as_500(monkeypatch):
    monkeypatch.setattr(main, "DATABASE_URL", "postgres://fake")
    monkeypatch.setattr(main, "ensure_prostudio_table", lambda: (_ for _ in ()).throw(RuntimeError("db exploded")))
    result = asyncio.run(main.public_prostudio_character_creation_jobs(42))
    assert result.status_code == 500
    assert json.loads(result.body)["error"] == "character_jobs_list_failed"
