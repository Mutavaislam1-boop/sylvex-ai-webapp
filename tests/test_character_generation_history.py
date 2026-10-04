"""Regression tests for "Generated with this Character" history writes.

Covers the Character System fix: every successfully completed generation
job that had a Character actively selected/committed at submission time
(metadata.characterId, populated straight from that request's own
image/video/music/voice options - never a separately tracked "currently
selected" state) must produce one prostudio_character_history row PER
generated media URL, regardless of which surface the client observes the
completion through (Pro Studio result, Telegram delivery, a plain
Image-mode result, or a job discovered later via polling after a
disconnect) - they all funnel through the single
process_prostudio_generation completion path.

Also covers the three corrective fixes on top of that:
  - a job returning several images must produce several History rows, not
    one, and replaying the same completed job must not duplicate them
    (UNIQUE(character_id, job_id, media_url), not UNIQUE(character_id,
    job_id));
  - deleting a custom Character deletes its own History rows, scoped to
    the same owner, never another user's;
  - only a user-created/custom Character (one the user actually owns, per
    the existing _load_character_resource ownership lookup) ever
    accumulates History - a built-in/preset SYLVEX Character never does.

Uses the same FakeCursor/FakeConnection technique as
test_character_reference_library.py and the same process_prostudio_generation
fixture pattern as test_generation_completion_storage_decoupling.py.
"""
import asyncio
from contextlib import contextmanager

import pytest

import main


class FakeCursor:
    def __init__(self, fetchone_result=None):
        self.executed = []
        self.fetchone_result = fetchone_result
        self.rowcount = 0

    def execute(self, sql, params=None):
        self.executed.append((sql, params))
        if "DELETE FROM prostudio_resources" in sql or "DELETE FROM prostudio_character_history WHERE id" in sql:
            self.rowcount = 1

    def fetchone(self):
        return self.fetchone_result

    def fetchall(self):
        return []

    def close(self):
        pass


class FakeConnection:
    def __init__(self, cursor):
        self._cursor = cursor

    def cursor(self):
        return self._cursor


def _patch_db(monkeypatch, cursor, database_url="postgres://fake"):
    @contextmanager
    def fake_db_connection(url):
        yield FakeConnection(cursor)

    monkeypatch.setattr(main, "DATABASE_URL", database_url)
    monkeypatch.setattr(main, "db_connection", fake_db_connection)
    monkeypatch.setattr(main, "ensure_prostudio_table", lambda: None)


def _own_this_character(monkeypatch, owned=True):
    # record_character_generation_history's ownership/custom-vs-built-in
    # gate is _load_character_resource returning something truthy - stub
    # it directly rather than wiring a second fake DB layer for it.
    monkeypatch.setattr(
        main, "_load_character_resource",
        lambda telegram_id, character_id: ({"id": character_id} if owned else None),
    )


# ===== Fix 1: one row per generated image, deduped per (character_id,
# job_id, media_url) =====

def test_record_character_generation_history_inserts_one_row_per_image(monkeypatch):
    cursor = FakeCursor()
    _patch_db(monkeypatch, cursor)
    _own_this_character(monkeypatch)

    main.record_character_generation_history(
        "custom_character_abc123", 42, "job-1",
        [
            "https://cdn.sylvex.ai/result_1.png",
            "https://cdn.sylvex.ai/result_2.png",
            "https://cdn.sylvex.ai/result_3.png",
            "https://cdn.sylvex.ai/result_4.png",
        ],
        "a cat", "gpt-image-2",
    )

    assert len(cursor.executed) == 4
    inserted_urls = []
    for sql, params in cursor.executed:
        assert "prostudio_character_history" in sql
        assert "ON CONFLICT (character_id, job_id, media_url) DO NOTHING" in sql
        # id, character_id, telegram_id, job_id, media_url, prompt, model
        assert params[1] == "custom_character_abc123"
        assert params[2] == 42
        assert params[3] == "job-1"
        assert params[5] == "a cat"
        assert params[6] == "gpt-image-2"
        inserted_urls.append(params[4])
    assert inserted_urls == [
        "https://cdn.sylvex.ai/result_1.png",
        "https://cdn.sylvex.ai/result_2.png",
        "https://cdn.sylvex.ai/result_3.png",
        "https://cdn.sylvex.ai/result_4.png",
    ]


def test_record_character_generation_history_accepts_a_single_url_too(monkeypatch):
    cursor = FakeCursor()
    _patch_db(monkeypatch, cursor)
    _own_this_character(monkeypatch)

    main.record_character_generation_history(
        "custom_character_abc123", 42, "job-1", "https://cdn.sylvex.ai/result.png",
    )

    assert len(cursor.executed) == 1
    assert cursor.executed[0][1][4] == "https://cdn.sylvex.ai/result.png"


def test_record_character_generation_history_dedups_a_repeated_url_within_one_call(monkeypatch):
    cursor = FakeCursor()
    _patch_db(monkeypatch, cursor)
    _own_this_character(monkeypatch)

    main.record_character_generation_history(
        "custom_character_abc123", 42, "job-1",
        ["https://cdn.sylvex.ai/a.png", "https://cdn.sylvex.ai/a.png"],
    )

    assert len(cursor.executed) == 1


@pytest.mark.parametrize("missing", ["character_id", "telegram_id", "job_id", "media_urls"])
def test_record_character_generation_history_skips_without_required_fields(monkeypatch, missing):
    cursor = FakeCursor()
    _patch_db(monkeypatch, cursor)
    _own_this_character(monkeypatch)

    args = {
        "character_id": "custom_character_abc123",
        "telegram_id": 42,
        "job_id": "job-1",
        "media_urls": ["https://cdn.sylvex.ai/result.png"],
    }
    args[missing] = "" if missing not in ("telegram_id", "media_urls") else (0 if missing == "telegram_id" else [])

    main.record_character_generation_history(
        args["character_id"], args["telegram_id"], args["job_id"], args["media_urls"],
    )

    assert cursor.executed == []


def test_record_character_generation_history_noop_without_database(monkeypatch):
    monkeypatch.setattr(main, "DATABASE_URL", "")
    _own_this_character(monkeypatch)
    # Must not raise and must not touch the DB layer at all.
    main.record_character_generation_history(
        "custom_character_abc123", 42, "job-1", ["https://cdn.sylvex.ai/result.png"],
    )


# ===== Fix 3: only a custom Character actually owned by this user ever
# accumulates History rows - never a built-in/preset one, never one not
# owned by this telegram_id. No single Character id is hardcoded: the
# gate is purely isCustomVisualItem-equivalent (id prefix) plus the
# existing ownership lookup. =====

def test_record_character_generation_history_skips_a_built_in_preset_character(monkeypatch):
    cursor = FakeCursor()
    _patch_db(monkeypatch, cursor)
    _own_this_character(monkeypatch, owned=True)  # even if the lookup somehow returned something

    main.record_character_generation_history(
        "character_sylvex", 42, "job-1", ["https://cdn.sylvex.ai/result.png"],
    )

    assert cursor.executed == [], "a non-custom_ character id must never reach the DB layer"


def test_record_character_generation_history_skips_when_the_character_is_not_owned_by_this_user(monkeypatch):
    cursor = FakeCursor()
    _patch_db(monkeypatch, cursor)
    _own_this_character(monkeypatch, owned=False)

    main.record_character_generation_history(
        "custom_character_abc123", 999, "job-1", ["https://cdn.sylvex.ai/result.png"],
    )

    assert cursor.executed == []


def test_record_character_generation_history_writes_once_ownership_confirmed(monkeypatch):
    cursor = FakeCursor()
    _patch_db(monkeypatch, cursor)
    _own_this_character(monkeypatch, owned=True)

    main.record_character_generation_history(
        "custom_character_abc123", 42, "job-1", ["https://cdn.sylvex.ai/result.png"],
    )

    assert len(cursor.executed) == 1


# ===== Fix 2: deleting a custom Character deletes its own History rows,
# scoped to the same owner, never another user's data. =====

def test_deleting_a_custom_character_also_deletes_its_character_history_rows(monkeypatch):
    cursor = FakeCursor()
    _patch_db(monkeypatch, cursor)
    monkeypatch.setattr(main, "log_user_event", lambda *a, **k: None)

    result = asyncio.run(main.public_prostudio_delete_resource("custom_character_abc123", telegram_id=42))

    assert result["deleted"] is True
    sqls = [sql for sql, _ in cursor.executed]
    assert any("DELETE FROM prostudio_resources" in sql for sql in sqls)
    history_calls = [(sql, params) for sql, params in cursor.executed if "DELETE FROM prostudio_character_history" in sql]
    assert len(history_calls) == 1
    history_sql, history_params = history_calls[0]
    assert "telegram_id = %s" in history_sql
    assert history_params == ("custom_character_abc123", 42)


def test_deleting_a_custom_character_never_touches_another_users_history_rows(monkeypatch):
    # The cleanup DELETE is scoped by telegram_id in its own WHERE clause -
    # assert that scoping directly rather than trusting a fake's behavior.
    cursor = FakeCursor()
    _patch_db(monkeypatch, cursor)
    monkeypatch.setattr(main, "log_user_event", lambda *a, **k: None)

    asyncio.run(main.public_prostudio_delete_resource("custom_character_abc123", telegram_id=42))

    history_calls = [params for sql, params in cursor.executed if "DELETE FROM prostudio_character_history" in sql]
    assert history_calls == [("custom_character_abc123", 42)]
    assert all(params[1] == 42 for params in history_calls), "cleanup must always carry the deleting user's own telegram_id"


def test_deleting_an_object_never_touches_character_history(monkeypatch):
    cursor = FakeCursor()
    _patch_db(monkeypatch, cursor)
    monkeypatch.setattr(main, "log_user_event", lambda *a, **k: None)

    asyncio.run(main.public_prostudio_delete_resource("custom_object_xyz", telegram_id=42))

    assert not any("prostudio_character_history" in sql for sql, _ in cursor.executed)


def test_character_history_cleanup_is_skipped_when_the_resource_was_not_actually_deleted(monkeypatch):
    class NoRowsCursor(FakeCursor):
        def execute(self, sql, params=None):
            self.executed.append((sql, params))
            # Simulate "nothing matched" - rowcount stays 0.

    cursor = NoRowsCursor()
    _patch_db(monkeypatch, cursor)
    monkeypatch.setattr(main, "log_user_event", lambda *a, **k: None)

    result = asyncio.run(main.public_prostudio_delete_resource("custom_character_abc123", telegram_id=42))

    assert result["deleted"] is False
    assert not any("prostudio_character_history" in sql for sql, _ in cursor.executed)


# ===== Integration: the single job-completion pipeline passes every
# generated image URL, and only ever fires for a request that actually
# had a Character selected. =====

@pytest.fixture
def app(monkeypatch):
    monkeypatch.setattr(main, "DATABASE_URL", "postgres://test")
    monkeypatch.setattr(main, "PROSTUDIO_MOCK_GENERATION", False)
    monkeypatch.setattr(main, "optimize_prompt_for_model", lambda *a, **k: {"ok": True, "optimized": False})
    monkeypatch.setattr(main, "resolve_prostudio_provider_for_slot", lambda *a, **k: "OPENAI")
    monkeypatch.setattr(main, "circuit_before_request", lambda *a, **k: {"allowed": True})
    monkeypatch.setattr(main, "circuit_release_probe", lambda *a, **k: None)
    monkeypatch.setattr(main, "heartbeat_prostudio_generation_job", lambda *a, **k: None)
    monkeypatch.setattr(main, "log_user_event", lambda *a, **k: None)
    monkeypatch.setattr(main, "save_generation", lambda *a, **k: None)
    monkeypatch.setattr(main, "save_prostudio_message", lambda *a, **k: "conv-1")
    monkeypatch.setattr(main, "charge_generation_balance", lambda *a, **k: {"charged": True, "balance_after": 100})
    monkeypatch.setattr(main, "update_prostudio_generation_job", lambda *a, **k: True)
    monkeypatch.setattr(main, "verify_persisted_generation_media", lambda result, mode: result)
    monkeypatch.setattr(main, "persist_generation_media", lambda result, mode: result)
    monkeypatch.setattr(main.asyncio, "create_task", lambda coro: coro.close())

    async def fake_telegram(*a, **k):
        return True
    monkeypatch.setattr(main, "sync_completed_generation_to_telegram", fake_telegram)
    return main


def _stub_provider_result(monkeypatch, app, images):
    async def fake_provider_request(*a, **k):
        return (
            {
                "ok": True,
                "type": "image",
                "status": "completed",
                "image_url": images[0],
                "images": images,
                "provider": "openai",
                "model": "gpt-image-2",
            },
            "completed",
        )
    monkeypatch.setattr(app, "run_prostudio_provider_request", fake_provider_request)


def _track_history_calls(monkeypatch, app):
    calls = []
    monkeypatch.setattr(
        app, "record_character_generation_history",
        lambda *a, **k: calls.append(a),
    )
    return calls


@pytest.mark.asyncio
async def test_completed_job_with_multiple_images_passes_every_image_url(app, monkeypatch):
    images = [
        "https://cdn.sylvex.ai/result_1.png",
        "https://cdn.sylvex.ai/result_2.png",
        "https://cdn.sylvex.ai/result_3.png",
        "https://cdn.sylvex.ai/result_4.png",
    ]
    _stub_provider_result(monkeypatch, app, images)
    calls = _track_history_calls(monkeypatch, app)
    payload = {
        "telegram_id": 42,
        "mode": "image",
        "prompt": "A hero portrait",
        "model": "gpt-image-2",
        "provider": "openai",
        "price_snapshot": {"final_credits": 5},
        "image_options": {"characterId": "custom_character_abc123", "characterName": "Islam", "count": 4},
    }
    await app.process_prostudio_generation("job-char-1", payload)

    assert len(calls) == 1
    character_id, telegram_id, job_id, media_urls, prompt, model = calls[0]
    assert character_id == "custom_character_abc123"
    assert telegram_id == 42
    assert job_id == "job-char-1"
    assert list(media_urls) == images
    assert prompt == "A hero portrait"
    assert model == "gpt-image-2"


@pytest.mark.asyncio
async def test_completed_job_without_selected_character_writes_no_history(app, monkeypatch):
    _stub_provider_result(monkeypatch, app, ["https://cdn.sylvex.ai/generated.png"])
    calls = _track_history_calls(monkeypatch, app)
    payload = {
        "telegram_id": 42,
        "mode": "image",
        "prompt": "A random landscape",
        "model": "gpt-image-2",
        "provider": "openai",
        "price_snapshot": {"final_credits": 5},
        "image_options": {},
    }
    await app.process_prostudio_generation("job-no-char-1", payload)

    assert calls == []


@pytest.mark.asyncio
async def test_replaying_the_same_completed_job_does_not_duplicate_history_rows(app, monkeypatch):
    # End-to-end version of the idempotency requirement: run the real
    # record_character_generation_history (not mocked) against a fake DB
    # cursor twice for "the same job", and confirm the second pass's
    # inserts are still issued with the per-image ON CONFLICT guard that
    # makes them no-ops - never a second distinct insert statement set
    # that could land as duplicates against a real UNIQUE index.
    images = ["https://cdn.sylvex.ai/result_1.png", "https://cdn.sylvex.ai/result_2.png"]
    _stub_provider_result(monkeypatch, app, images)
    _own_this_character(monkeypatch, owned=True)
    cursor = FakeCursor()
    _patch_db(monkeypatch, cursor)
    payload = {
        "telegram_id": 42,
        "mode": "image",
        "prompt": "A hero portrait",
        "model": "gpt-image-2",
        "provider": "openai",
        "price_snapshot": {"final_credits": 5},
        "image_options": {"characterId": "custom_character_abc123", "count": 2},
    }

    await app.process_prostudio_generation("job-repeat-1", dict(payload))
    first_pass_inserts = [p for sql, p in cursor.executed if "INSERT INTO prostudio_character_history" in sql]
    assert len(first_pass_inserts) == 2

    cursor.executed = []
    await app.process_prostudio_generation("job-repeat-1", dict(payload))
    second_pass_inserts = [p for sql, p in cursor.executed if "INSERT INTO prostudio_character_history" in sql]
    # Same job, same images -> the same two (character_id, job_id, media_url)
    # conflict keys are sent again, each guarded by ON CONFLICT DO NOTHING -
    # a real UNIQUE index would keep this at exactly 2 rows total, never 4.
    assert len(second_pass_inserts) == 2
    assert {p[4] for p in first_pass_inserts} == {p[4] for p in second_pass_inserts} == set(images)


# ===== Fix 2: Character History is image-only - a video/music/voice job
# must never write a row, even if it carries a characterId. =====

@pytest.mark.asyncio
async def test_completed_video_job_with_a_character_id_writes_no_history(app, monkeypatch):
    async def fake_video_provider(*a, **k):
        return (
            {
                "ok": True,
                "type": "video",
                "status": "completed",
                "video_url": "https://cdn.sylvex.ai/clip.mp4",
                "videos": ["https://cdn.sylvex.ai/clip.mp4"],
                "provider": "kling",
                "model": "kling_2_6",
            },
            "completed",
        )
    monkeypatch.setattr(app, "run_prostudio_provider_request", fake_video_provider)
    calls = _track_history_calls(monkeypatch, app)
    payload = {
        "telegram_id": 42,
        "mode": "video",
        "prompt": "A hero walking",
        "model": "kling_2_6",
        "provider": "kling",
        "price_snapshot": {"final_credits": 20},
        "video_options": {"characterId": "custom_character_abc123", "characterName": "Islam"},
    }
    await app.process_prostudio_generation("job-video-1", payload)

    assert calls == [], "a video job must never write Character History, even with a characterId"


@pytest.mark.asyncio
async def test_completed_voice_job_with_a_character_id_writes_no_history(app, monkeypatch):
    async def fake_voice_provider(*a, **k):
        return (
            {
                "ok": True,
                "type": "voice",
                "status": "completed",
                "audio_url": "https://cdn.sylvex.ai/line.mp3",
                "audios": ["https://cdn.sylvex.ai/line.mp3"],
                "provider": "elevenlabs",
                "model": "eleven_v3",
            },
            "completed",
        )
    monkeypatch.setattr(app, "run_prostudio_provider_request", fake_voice_provider)
    calls = _track_history_calls(monkeypatch, app)
    payload = {
        "telegram_id": 42,
        "mode": "voice",
        "prompt": "Hello there",
        "model": "eleven_v3",
        "provider": "elevenlabs",
        "price_snapshot": {"final_credits": 10},
        "voice_options": {"characterId": "custom_character_abc123"},
    }
    await app.process_prostudio_generation("job-voice-1", payload)

    assert calls == []


# ===== Fix 3: deleting a single History entry, scoped to
# history_entry_id + character_id + telegram_id, and never touching the
# original media or the Pro Studio generation/job. =====

def test_delete_character_history_entry_succeeds_when_owned_by_this_user(monkeypatch):
    cursor = FakeCursor()
    _patch_db(monkeypatch, cursor)

    result = asyncio.run(main.public_prostudio_delete_character_history_entry(
        "custom_character_abc123", "hist-1", telegram_id=42,
    ))

    assert result == {"ok": True, "deleted": True, "id": "hist-1"}
    sql, params = cursor.executed[0]
    assert "DELETE FROM prostudio_character_history" in sql
    assert "id = %s" in sql and "character_id = %s" in sql and "telegram_id = %s" in sql
    assert params == ("hist-1", "custom_character_abc123", 42)


def test_delete_character_history_entry_requires_telegram_id(monkeypatch):
    result = asyncio.run(main.public_prostudio_delete_character_history_entry(
        "custom_character_abc123", "hist-1", telegram_id=0,
    ))
    assert result.status_code == 400


def test_delete_character_history_entry_never_deletes_another_users_row(monkeypatch):
    # The fake's rowcount never flips to >0 unless the DELETE actually
    # matched - simulating "this history_id belongs to a different user"
    # by having the DELETE match nothing (as the real WHERE telegram_id
    # clause would for a mismatched owner).
    class NoMatchCursor(FakeCursor):
        def execute(self, sql, params=None):
            self.executed.append((sql, params))

    cursor = NoMatchCursor()
    _patch_db(monkeypatch, cursor)

    result = asyncio.run(main.public_prostudio_delete_character_history_entry(
        "custom_character_abc123", "hist-1", telegram_id=999,
    ))

    assert result == {"ok": True, "deleted": False, "id": "hist-1"}
    # The attempted delete was still scoped by the caller's own
    # telegram_id (999), never silently widened to match anyone's row.
    sql, params = cursor.executed[0]
    assert params == ("hist-1", "custom_character_abc123", 999)


def test_delete_character_history_entry_only_deletes_the_history_row(monkeypatch):
    # No cascading: the function must never touch prostudio_resources,
    # prostudio_messages, or prostudio_generation_jobs (the R2 media and
    # the generation itself) - only prostudio_character_history.
    cursor = FakeCursor()
    _patch_db(monkeypatch, cursor)

    asyncio.run(main.public_prostudio_delete_character_history_entry(
        "custom_character_abc123", "hist-1", telegram_id=42,
    ))

    assert len(cursor.executed) == 1
    sql, _ = cursor.executed[0]
    for forbidden_table in ("prostudio_resources", "prostudio_messages", "prostudio_generation_jobs"):
        assert forbidden_table not in sql


def test_delete_character_history_entry_noop_without_database(monkeypatch):
    monkeypatch.setattr(main, "DATABASE_URL", "")
    result = asyncio.run(main.public_prostudio_delete_character_history_entry(
        "custom_character_abc123", "hist-1", telegram_id=42,
    ))
    assert result == {"ok": True, "deleted": False}
