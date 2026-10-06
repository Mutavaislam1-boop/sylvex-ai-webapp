"""Regression tests for Object Creation V2: single reference + auto
objectPrompt, background job.

Covers:
  - _object_reference_prompt()/_object_prompt_instruction_text(): the two
    prompts sent to the image model and the vision/text analysis model -
    the latter must explicitly exclude background/scene/camera/person
    information and only ask about stable physical properties of the
    object itself.
  - _object_prompt_fallback(): used only when prompt analysis fails -
    Description if present, else the Object's name - never blocks Object
    creation.
  - create_object_creation_job(): inserts an already-'processing'
    object_creation row (never 'queued', so the generic worker pool can
    never race it).
  - _run_object_creation_job(): generates exactly one normalized
    reference image and the objectPrompt in parallel; a prompt-analysis
    failure uses the safe fallback and does not fail the job; a
    reference-generation failure does fail the job; the raw uploaded
    photo is kept only as originalSourceImages metadata, never as a
    second usable reference; the continuous heartbeat and terminal-status
    guard already proven for Character creation are reused unmodified.
  - public_prostudio_create_object(): validates the request (name,
    telegram_id, exactly one photo - more than one is capped, never
    rejected outright) and returns 202 with a job_id immediately.
  - public_prostudio_object_creation_jobs(): owner-scoped list used by the
    frontend's pending-Object-card restore-on-reload flow.
  - load_prostudio_resources(): an Object's objectPrompt/
    primaryReferenceUrl/originalSourceImages survive a reload, additively
    and backward-compatibly (an Object saved before this existed just
    gets harmless defaults).

Does not touch Character creation at all - none of its tests, fixtures,
or production code paths are modified by this file.
"""
import asyncio
import datetime as dt
import json
from contextlib import contextmanager

import pytest

import main


class FakeRequest:
    def __init__(self, data):
        self._data = data

    async def json(self):
        return self._data


# ---- _object_reference_prompt / _object_prompt_instruction_text /
# _object_prompt_fallback: pure prompt-building functions ----

def test_object_reference_prompt_asks_to_preserve_identity_and_normalize_scene():
    prompt = main._object_reference_prompt("Bag", "dark brown leather, brass hardware")
    assert "Bag" in prompt
    assert "dark brown leather, brass hardware" in prompt
    assert "same physical object" in prompt
    assert "background" in prompt.lower()


def test_object_reference_prompt_works_with_no_description():
    prompt = main._object_reference_prompt("Bag", "")
    assert "Bag" in prompt
    assert "Additional details" not in prompt


def test_object_prompt_instruction_excludes_background_and_scene_information():
    instruction = main._object_prompt_instruction_text("Bag", "")
    lowered = instruction.lower()
    assert "do not mention the background" in lowered
    assert "describe the object only" in lowered
    assert "camera angle" in lowered
    assert "hands" in lowered


def test_object_prompt_instruction_includes_name_and_non_conflicting_description():
    instruction = main._object_prompt_instruction_text("Bag", "The metal parts are brass.")
    assert '"Bag"' in instruction
    assert "The metal parts are brass." in instruction
    assert "does not conflict" in instruction


def test_object_prompt_instruction_omits_description_clause_when_empty():
    instruction = main._object_prompt_instruction_text("Bag", "")
    assert "owner also provided" not in instruction


def test_object_prompt_fallback_prefers_description_over_name():
    assert main._object_prompt_fallback("Bag", "Dark brown leather bag") == "Dark brown leather bag"


def test_object_prompt_fallback_uses_name_when_description_empty():
    assert main._object_prompt_fallback("Bag", "") == "Bag"
    assert main._object_prompt_fallback("Bag", "   ") == "Bag"


# ---- _analyze_object_prompt(): the vision/text analysis call ----

def test_analyze_object_prompt_sends_image_and_instruction_to_call_text_provider(monkeypatch):
    captured = {}

    def fake_call_text_provider(model, messages):
        captured["model"] = model
        captured["messages"] = messages
        return {"ok": True, "text": "Black structured leather shoulder bag."}

    monkeypatch.setattr(main, "call_text_provider", fake_call_text_provider)

    text = asyncio.run(main._analyze_object_prompt("job-1", "Bag", "", "https://cdn.sylvex.ai/source.jpg"))

    assert text == "Black structured leather shoulder bag."
    assert captured["model"] == "gpt-5.5"
    user_message = captured["messages"][-1]
    assert user_message["role"] == "user"
    image_parts = [part for part in user_message["content"] if part.get("type") == "image_url"]
    assert image_parts and image_parts[0]["image_url"]["url"] == "https://cdn.sylvex.ai/source.jpg"


def test_analyze_object_prompt_raises_without_an_image():
    with pytest.raises(RuntimeError):
        asyncio.run(main._analyze_object_prompt("job-1", "Bag", "", ""))


def test_analyze_object_prompt_raises_when_provider_call_fails(monkeypatch):
    monkeypatch.setattr(main, "call_text_provider", lambda model, messages: {"ok": False, "error": "quota exceeded"})
    with pytest.raises(RuntimeError):
        asyncio.run(main._analyze_object_prompt("job-1", "Bag", "", "https://cdn.sylvex.ai/source.jpg"))


def test_analyze_object_prompt_raises_on_empty_text(monkeypatch):
    monkeypatch.setattr(main, "call_text_provider", lambda model, messages: {"ok": True, "text": "   "})
    with pytest.raises(RuntimeError):
        asyncio.run(main._analyze_object_prompt("job-1", "Bag", "", "https://cdn.sylvex.ai/source.jpg"))


# ---- create_object_creation_job(): the DB insert ----

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


def test_create_object_creation_job_requires_a_database(monkeypatch):
    monkeypatch.setattr(main, "DATABASE_URL", "")
    with pytest.raises(main.SecurityError):
        main.create_object_creation_job(42, "Bag", "leather", ["https://cdn.sylvex.ai/a.jpg"])


def test_create_object_creation_job_inserts_an_already_processing_row(monkeypatch):
    cursor = FakeCursor()
    connection = FakeConnection(cursor)
    monkeypatch.setattr(main, "DATABASE_URL", "postgres://test")
    monkeypatch.setattr(main, "db_connect", lambda url: connection)
    monkeypatch.setattr(main, "ensure_prostudio_table", lambda: None)

    job_id = main.create_object_creation_job(42, "Bag", "leather", ["https://cdn.sylvex.ai/a.jpg"])

    assert job_id
    assert connection.committed is True
    assert len(cursor.executed) == 1
    sql, params = cursor.executed[0]
    assert "'processing'" in sql
    assert "'queued'" not in sql
    assert "object_creation" in sql
    assert params[0] == job_id
    assert params[1] == 42
    request_json = json.loads(params[3])
    assert request_json == {
        "name": "Bag", "description": "leather",
        "photos": ["https://cdn.sylvex.ai/a.jpg"],
    }


# ---- _run_object_creation_job(): the background worker ----

@pytest.fixture
def stub_object_pipeline(monkeypatch):
    async def fake_reference(job_id, name, description, source_photo):
        return "https://cdn.sylvex.ai/generated/reference.png"

    async def fake_prompt(job_id, name, description, image_url):
        return "Black structured leather shoulder bag."

    monkeypatch.setattr(main, "_generate_object_reference_image", fake_reference)
    monkeypatch.setattr(main, "_analyze_object_prompt", fake_prompt)
    monkeypatch.setattr(main, "save_prostudio_resource", lambda telegram_id, resource: resource)
    monkeypatch.setattr(main, "heartbeat_prostudio_generation_job", lambda job_id: None)
    monkeypatch.setattr(main, "get_prostudio_generation_job_status", lambda job_id: "processing")


def _capture_job_updates(monkeypatch):
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


def test_run_object_creation_job_marks_completed_with_a_single_reference(stub_object_pipeline, monkeypatch):
    updates = _capture_job_updates(monkeypatch)

    asyncio.run(main._run_object_creation_job("job-1", 42, "Bag", "leather", ["https://cdn.sylvex.ai/source.jpg"]))

    job_id, status, result, error = _terminal_update(updates)
    assert job_id == "job-1"
    assert status == "completed"
    assert error is None
    assert result["ok"] is True
    resource = result["resource"]
    assert result["object_id"] == resource["id"]
    assert resource["id"].startswith("custom_object_")
    assert resource["referenceImages"] == ["https://cdn.sylvex.ai/generated/reference.png"]
    assert len(resource["referenceImages"]) == 1
    assert resource["primaryReferenceUrl"] == "https://cdn.sylvex.ai/generated/reference.png"
    assert resource["previewUrl"] == "https://cdn.sylvex.ai/generated/reference.png"
    assert resource["objectPrompt"] == "Black structured leather shoulder bag."
    assert resource["description"] == "leather"
    assert result["result_url"] == resource["previewUrl"]


def test_run_object_creation_job_keeps_original_source_as_metadata_only(stub_object_pipeline, monkeypatch):
    updates = _capture_job_updates(monkeypatch)
    asyncio.run(main._run_object_creation_job("job-1", 42, "Bag", "", ["https://cdn.sylvex.ai/source.jpg"]))
    _, _, result, _ = _terminal_update(updates)
    resource = result["resource"]
    assert resource["originalSourceImages"] == ["https://cdn.sylvex.ai/source.jpg"]
    assert "https://cdn.sylvex.ai/source.jpg" not in resource["referenceImages"]
    assert resource["referenceImages"] != resource["originalSourceImages"]


def test_run_object_creation_job_objectprompt_separate_from_user_description(stub_object_pipeline, monkeypatch):
    updates = _capture_job_updates(monkeypatch)
    asyncio.run(main._run_object_creation_job("job-1", 42, "Bag", "User-entered description", ["https://cdn.sylvex.ai/source.jpg"]))
    _, _, result, _ = _terminal_update(updates)
    resource = result["resource"]
    assert resource["description"] == "User-entered description"
    assert resource["objectPrompt"] == "Black structured leather shoulder bag."
    assert resource["description"] != resource["objectPrompt"]


def test_run_object_creation_job_prompt_analysis_failure_does_not_fail_the_job(monkeypatch):
    async def fake_reference(job_id, name, description, source_photo):
        return "https://cdn.sylvex.ai/generated/reference.png"

    async def failing_prompt(job_id, name, description, image_url):
        raise RuntimeError("vision analysis failed")

    monkeypatch.setattr(main, "_generate_object_reference_image", fake_reference)
    monkeypatch.setattr(main, "_analyze_object_prompt", failing_prompt)
    monkeypatch.setattr(main, "save_prostudio_resource", lambda telegram_id, resource: resource)
    monkeypatch.setattr(main, "heartbeat_prostudio_generation_job", lambda job_id: None)
    monkeypatch.setattr(main, "get_prostudio_generation_job_status", lambda job_id: "processing")
    updates = _capture_job_updates(monkeypatch)

    asyncio.run(main._run_object_creation_job("job-1", 42, "Bag", "Dark brown leather", ["https://cdn.sylvex.ai/source.jpg"]))

    job_id, status, result, error = _terminal_update(updates)
    assert status == "completed"
    assert error is None
    resource = result["resource"]
    # Safe fallback: Description, since it was provided.
    assert resource["objectPrompt"] == "Dark brown leather"
    assert resource["referenceImages"] == ["https://cdn.sylvex.ai/generated/reference.png"]


def test_run_object_creation_job_prompt_analysis_failure_falls_back_to_name_without_description(monkeypatch):
    async def fake_reference(job_id, name, description, source_photo):
        return "https://cdn.sylvex.ai/generated/reference.png"

    async def failing_prompt(job_id, name, description, image_url):
        raise RuntimeError("vision analysis failed")

    monkeypatch.setattr(main, "_generate_object_reference_image", fake_reference)
    monkeypatch.setattr(main, "_analyze_object_prompt", failing_prompt)
    monkeypatch.setattr(main, "save_prostudio_resource", lambda telegram_id, resource: resource)
    monkeypatch.setattr(main, "heartbeat_prostudio_generation_job", lambda job_id: None)
    monkeypatch.setattr(main, "get_prostudio_generation_job_status", lambda job_id: "processing")
    updates = _capture_job_updates(monkeypatch)

    asyncio.run(main._run_object_creation_job("job-1", 42, "Bag", "", ["https://cdn.sylvex.ai/source.jpg"]))

    _, status, result, error = _terminal_update(updates)
    assert status == "completed"
    assert error is None
    assert result["resource"]["objectPrompt"] == "Bag"


def test_run_object_creation_job_reference_generation_failure_fails_the_job(monkeypatch):
    async def failing_reference(job_id, name, description, source_photo):
        raise RuntimeError("OpenAI object image generation failed (status=500): boom")

    async def fake_prompt(job_id, name, description, image_url):
        return "Black bag."

    monkeypatch.setattr(main, "_generate_object_reference_image", failing_reference)
    monkeypatch.setattr(main, "_analyze_object_prompt", fake_prompt)
    monkeypatch.setattr(main, "heartbeat_prostudio_generation_job", lambda job_id: None)
    save_calls = []
    monkeypatch.setattr(main, "save_prostudio_resource", lambda telegram_id, resource: save_calls.append(resource) or resource)
    updates = _capture_job_updates(monkeypatch)

    asyncio.run(main._run_object_creation_job("job-2", 42, "Bag", "", ["https://cdn.sylvex.ai/source.jpg"]))

    job_id, status, result, error = _terminal_update(updates)
    assert status == "failed"
    assert result is None
    assert error is not None
    assert save_calls == []


def test_run_object_creation_job_translates_billing_limit_errors(monkeypatch):
    async def failing_reference(job_id, name, description, source_photo):
        raise RuntimeError("billing hard limit has been reached")

    monkeypatch.setattr(main, "_generate_object_reference_image", failing_reference)
    monkeypatch.setattr(main, "_analyze_object_prompt", lambda *a, **k: asyncio.sleep(0, result="x"))
    monkeypatch.setattr(main, "heartbeat_prostudio_generation_job", lambda job_id: None)
    updates = _capture_job_updates(monkeypatch)

    asyncio.run(main._run_object_creation_job("job-3", 42, "Bag", "", ["https://cdn.sylvex.ai/source.jpg"]))

    _, status, _, error = _terminal_update(updates)
    assert status == "failed"
    assert "Лимит расходов" in error["error"]


def test_run_object_creation_job_translates_safety_violation_errors(monkeypatch):
    async def failing_reference(job_id, name, description, source_photo):
        raise RuntimeError("Rejected by safety_violations=[sexual]")

    monkeypatch.setattr(main, "_generate_object_reference_image", failing_reference)
    monkeypatch.setattr(main, "_analyze_object_prompt", lambda *a, **k: asyncio.sleep(0, result="x"))
    monkeypatch.setattr(main, "heartbeat_prostudio_generation_job", lambda job_id: None)
    updates = _capture_job_updates(monkeypatch)

    asyncio.run(main._run_object_creation_job("job-4", 42, "Bag", "", ["https://cdn.sylvex.ai/source.jpg"]))

    _, status, _, error = _terminal_update(updates)
    assert status == "failed"
    assert "безопасности" in error["error"]
    assert "safety_violations" not in error["error"]


def test_run_object_creation_job_skips_resource_save_when_job_already_terminal(stub_object_pipeline, monkeypatch):
    monkeypatch.setattr(main, "get_prostudio_generation_job_status", lambda job_id: "failed")
    save_calls = []
    monkeypatch.setattr(main, "save_prostudio_resource", lambda telegram_id, resource: save_calls.append(resource) or resource)
    updates = _capture_job_updates(monkeypatch)

    asyncio.run(main._run_object_creation_job("job-terminal", 42, "Bag", "", ["https://cdn.sylvex.ai/a.jpg"]))

    assert save_calls == []
    # No terminal (completed/failed) update - the already-terminal job row
    # is left exactly as it was by this function. The initial "reference"
    # progress write (status stays 'processing') is harmless and already
    # guarded against overwriting a terminal row by
    # update_prostudio_generation_job() itself.
    assert all(entry[1] == "processing" for entry in updates)


def test_run_object_creation_job_heartbeats_continuously_during_generation(monkeypatch):
    monkeypatch.setattr(main, "CHARACTER_CREATION_HEARTBEAT_SECONDS", 0.01)
    heartbeats = []
    monkeypatch.setattr(main, "heartbeat_prostudio_generation_job", lambda job_id: heartbeats.append(job_id))
    monkeypatch.setattr(main, "save_prostudio_resource", lambda telegram_id, resource: resource)
    monkeypatch.setattr(main, "get_prostudio_generation_job_status", lambda job_id: "processing")
    updates = _capture_job_updates(monkeypatch)

    async def slow_reference(job_id, name, description, source_photo):
        await asyncio.sleep(0.08)
        return "https://cdn.sylvex.ai/generated/reference.png"

    async def fake_prompt(job_id, name, description, image_url):
        return "Black bag."

    monkeypatch.setattr(main, "_generate_object_reference_image", slow_reference)
    monkeypatch.setattr(main, "_analyze_object_prompt", fake_prompt)

    asyncio.run(main._run_object_creation_job("job-heartbeat", 42, "Bag", "", ["https://cdn.sylvex.ai/a.jpg"]))

    assert len(heartbeats) >= 2
    assert all(job_id == "job-heartbeat" for job_id in heartbeats)
    _, status, _, _ = _terminal_update(updates)
    assert status == "completed"


def test_run_object_creation_job_records_reference_then_saving_stage_progress(stub_object_pipeline, monkeypatch):
    updates = _capture_job_updates(monkeypatch)
    asyncio.run(main._run_object_creation_job("job-1", 42, "Bag", "", ["https://cdn.sylvex.ai/a.jpg"]))
    processing_updates = [entry for entry in updates if entry[1] == "processing"]
    stages = [entry[2]["stage"] for entry in processing_updates]
    assert stages == ["reference", "saving"]
    saving_entry = processing_updates[-1]
    assert saving_entry[2]["reference_url"] == "https://cdn.sylvex.ai/generated/reference.png"


# ---- public_prostudio_create_object(): validation + 202 response ----

def test_create_object_requires_a_photo():
    request = FakeRequest({"telegram_id": 42, "name": "Bag", "description": "leather"})
    result = asyncio.run(main.public_prostudio_create_object(request))
    assert result.status_code == 400
    assert json.loads(result.body)["error"] == "reference_image_required"


def test_create_object_requires_a_name():
    request = FakeRequest({"telegram_id": 42, "name": "", "photos": ["https://cdn.sylvex.ai/a.jpg"]})
    result = asyncio.run(main.public_prostudio_create_object(request))
    assert result.status_code == 400
    assert json.loads(result.body)["error"] == "name_required"


def test_create_object_requires_telegram_id():
    request = FakeRequest({"name": "Bag", "photos": ["https://cdn.sylvex.ai/a.jpg"]})
    result = asyncio.run(main.public_prostudio_create_object(request))
    assert result.status_code == 400
    assert json.loads(result.body)["error"] == "telegram_id_required"


async def _noop_quota_check(telegram_id):
    pass


def test_create_object_caps_photos_at_exactly_one_before_queuing(monkeypatch):
    received = {}
    monkeypatch.setattr(main, "check_object_creation_request_quota", _noop_quota_check)
    monkeypatch.setattr(main, "create_object_creation_job", lambda telegram_id, name, description, photos: received.setdefault("photos", list(photos)) or "job-xyz")

    async def noop_worker(*a, **k):
        pass

    monkeypatch.setattr(main, "_run_object_creation_job", noop_worker)
    request = FakeRequest({
        "telegram_id": 42, "name": "Bag",
        "photos": ["https://cdn.sylvex.ai/a.jpg", "https://cdn.sylvex.ai/b.jpg", "https://cdn.sylvex.ai/c.jpg"],
    })
    asyncio.run(main.public_prostudio_create_object(request))
    assert received["photos"] == ["https://cdn.sylvex.ai/a.jpg"]


def test_create_object_returns_202_with_job_id_without_waiting_for_generation(monkeypatch):
    finished = {"value": False}
    monkeypatch.setattr(main, "check_object_creation_request_quota", _noop_quota_check)
    monkeypatch.setattr(main, "create_object_creation_job", lambda *a, **k: "job-xyz")

    async def slow_worker(job_id, telegram_id, name, description, photos):
        await asyncio.sleep(0.05)
        finished["value"] = True

    monkeypatch.setattr(main, "_run_object_creation_job", slow_worker)
    main.app.state.background_tasks = []

    async def scenario():
        request = FakeRequest({"telegram_id": 42, "name": "Bag", "photos": ["https://cdn.sylvex.ai/a.jpg"]})
        result = await main.public_prostudio_create_object(request)
        assert result.status_code == 202
        body = json.loads(result.body)
        assert body == {"ok": True, "job_id": "job-xyz", "status": "processing"}
        assert finished["value"] is False
        await asyncio.sleep(0.2)
        assert finished["value"] is True

    asyncio.run(scenario())


def test_create_object_job_creation_failure_surfaces_as_502(monkeypatch):
    def failing_create_job(*a, **k):
        raise RuntimeError("db exploded")

    monkeypatch.setattr(main, "check_object_creation_request_quota", _noop_quota_check)
    monkeypatch.setattr(main, "create_object_creation_job", failing_create_job)
    request = FakeRequest({"telegram_id": 42, "name": "Bag", "photos": ["https://cdn.sylvex.ai/a.jpg"]})
    result = asyncio.run(main.public_prostudio_create_object(request))
    assert result.status_code == 502
    assert "db exploded" in json.loads(result.body)["error"]


# ---- public_prostudio_object_creation_jobs(): owner-scoped list used by
# the frontend's pending-Object-card restore-on-reload flow ----

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


def test_object_creation_jobs_endpoint_requires_telegram_id():
    result = asyncio.run(main.public_prostudio_object_creation_jobs(0))
    assert result.status_code == 400
    assert json.loads(result.body)["error"] == "telegram_id_required"


def test_object_creation_jobs_endpoint_returns_empty_list_without_database(monkeypatch):
    monkeypatch.setattr(main, "DATABASE_URL", "")
    result = asyncio.run(main.public_prostudio_object_creation_jobs(42))
    assert result == {"ok": True, "jobs": []}


def test_object_creation_jobs_endpoint_scopes_query_to_the_requesting_telegram_id(monkeypatch):
    cursor = _patch_jobs_list_db(monkeypatch, [])
    asyncio.run(main.public_prostudio_object_creation_jobs(777))
    sql, params = cursor.executed[0]
    assert "object_creation" in sql
    assert "telegram_id = %s" in sql
    assert params == (777,)

    cursor2 = _patch_jobs_list_db(monkeypatch, [])
    asyncio.run(main.public_prostudio_object_creation_jobs(456))
    _, params2 = cursor2.executed[0]
    assert params2 == (456,)


def test_object_creation_jobs_endpoint_shapes_a_processing_job_with_progress(monkeypatch):
    created = dt.datetime(2026, 1, 1, 12, 0, 0)
    updated = dt.datetime(2026, 1, 1, 12, 1, 0)
    rows = [(
        "job-1", "processing",
        {"name": "Bag", "description": "leather", "photos": ["https://cdn.sylvex.ai/a.jpg"]},
        {"stage": "saving", "reference_url": "https://cdn.sylvex.ai/reference.png"},
        None,
        created, updated,
    )]
    _patch_jobs_list_db(monkeypatch, rows)

    result = asyncio.run(main.public_prostudio_object_creation_jobs(42))

    assert result["ok"] is True
    job = result["jobs"][0]
    assert job["job_id"] == "job-1"
    assert job["status"] == "processing"
    assert job["name"] == "Bag"
    assert job["description"] == "leather"
    assert job["photos"] == ["https://cdn.sylvex.ai/a.jpg"]
    assert job["created_at"] == created.isoformat()
    assert job["updated_at"] == updated.isoformat()
    assert job["result"]["stage"] == "saving"
    assert job["result"]["reference_url"] == "https://cdn.sylvex.ai/reference.png"
    assert job["error"] is None


def test_object_creation_jobs_endpoint_includes_a_completed_job_with_its_resource(monkeypatch):
    rows = [(
        "job-done", "completed",
        {"name": "Bag", "description": "", "photos": ["https://cdn.sylvex.ai/b.jpg"]},
        {"ok": True, "object_id": "custom_object_abc", "resource": {"id": "custom_object_abc"}, "result_url": "https://cdn.sylvex.ai/p.png"},
        None,
        dt.datetime(2026, 1, 1), dt.datetime(2026, 1, 1),
    )]
    _patch_jobs_list_db(monkeypatch, rows)

    result = asyncio.run(main.public_prostudio_object_creation_jobs(42))

    job = result["jobs"][0]
    assert job["status"] == "completed"
    assert job["result"]["resource"]["id"] == "custom_object_abc"
    assert job["error"] is None


def test_object_creation_jobs_endpoint_sanitizes_a_failed_jobs_error(monkeypatch):
    rows = [(
        "job-2", "failed",
        {"name": "Bag", "description": "", "photos": ["https://cdn.sylvex.ai/b.jpg"]},
        None,
        {"ok": False, "error": "boom", "raw_error": "Traceback ... api_key=sk-secret"},
        dt.datetime(2026, 1, 1), dt.datetime(2026, 1, 1),
    )]
    _patch_jobs_list_db(monkeypatch, rows)

    result = asyncio.run(main.public_prostudio_object_creation_jobs(42))

    job = result["jobs"][0]
    assert job["status"] == "failed"
    assert "raw_error" not in job["error"]
    assert "sk-secret" not in str(job["error"])


def test_object_creation_jobs_endpoint_list_failure_surfaces_as_500(monkeypatch):
    monkeypatch.setattr(main, "DATABASE_URL", "postgres://fake")
    monkeypatch.setattr(main, "ensure_prostudio_table", lambda: (_ for _ in ()).throw(RuntimeError("db exploded")))
    result = asyncio.run(main.public_prostudio_object_creation_jobs(42))
    assert result.status_code == 500
    assert json.loads(result.body)["error"] == "object_jobs_list_failed"


# ---- load_prostudio_resources(): objectPrompt/primaryReferenceUrl/
# originalSourceImages survive a reload ----

class _LoadFakeCursor:
    def __init__(self, rows):
        self.rows = rows

    def execute(self, sql, params=None):
        pass

    def fetchall(self):
        return self.rows

    def close(self):
        pass


class _LoadFakeConnection:
    def __init__(self, cursor):
        self._cursor = cursor

    def cursor(self):
        return self._cursor


def _patch_load_db(monkeypatch, rows):
    cursor = _LoadFakeCursor(rows)

    @contextmanager
    def fake_db_connection(url):
        yield _LoadFakeConnection(cursor)

    monkeypatch.setattr(main, "DATABASE_URL", "postgres://fake")
    monkeypatch.setattr(main, "db_connection", fake_db_connection)
    monkeypatch.setattr(main, "ensure_prostudio_table", lambda: None)


def test_load_prostudio_resources_exposes_object_prompt_and_metadata(monkeypatch):
    rows = [(
        "custom_object_abc", "object", "Bag", "leather", "",
        "https://cdn.sylvex.ai/reference.png", ["https://cdn.sylvex.ai/reference.png"],
        {
            "objectPrompt": "Black structured leather shoulder bag.",
            "primaryReferenceUrl": "https://cdn.sylvex.ai/reference.png",
            "originalSourceImages": ["https://cdn.sylvex.ai/source.jpg"],
            "provider": "openai", "model": "gpt-image-2",
        },
        "ready", dt.datetime(2026, 1, 1), dt.datetime(2026, 1, 1),
    )]
    _patch_load_db(monkeypatch, rows)

    resources = main.load_prostudio_resources(42)

    assert len(resources["objects"]) == 1
    item = resources["objects"][0]
    assert item["objectPrompt"] == "Black structured leather shoulder bag."
    assert item["prompt"] == item["objectPrompt"]
    assert item["primaryReferenceUrl"] == "https://cdn.sylvex.ai/reference.png"
    assert item["originalSourceImages"] == ["https://cdn.sylvex.ai/source.jpg"]
    assert item["referenceImages"] == ["https://cdn.sylvex.ai/reference.png"]
    assert len(item["referenceImages"]) == 1


def test_load_prostudio_resources_backward_compatible_with_objects_saved_before_v2(monkeypatch):
    # An Object saved by the old synchronous flow has no objectPrompt/
    # primaryReferenceUrl/originalSourceImages in its metadata_json at
    # all - this must not break, and must fall back to harmless defaults.
    rows = [(
        "custom_object_old", "object", "Lamp", "", "",
        "https://cdn.sylvex.ai/lamp.png", ["https://cdn.sylvex.ai/lamp.png"],
        {},
        "ready", dt.datetime(2025, 1, 1), dt.datetime(2025, 1, 1),
    )]
    _patch_load_db(monkeypatch, rows)

    resources = main.load_prostudio_resources(42)

    item = resources["objects"][0]
    assert item["objectPrompt"] == ""
    assert item["primaryReferenceUrl"] == "https://cdn.sylvex.ai/lamp.png"
    assert item["originalSourceImages"] == []
    assert item["name"] == "Lamp"
    assert item["status"] == "ready"
