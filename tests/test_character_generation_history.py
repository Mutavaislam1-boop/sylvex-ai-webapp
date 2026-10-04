"""Regression tests for "Generated with this Character" history writes.

Covers the Character System fix: every successfully completed generation
job that had a Character actively selected/committed at submission time
(metadata.characterId, populated straight from that request's own
image/video/music/voice options - never a separately tracked "currently
selected" state) must produce exactly one prostudio_character_history row,
regardless of which surface the client observes the completion through
(Pro Studio result, Telegram delivery, a plain Image-mode result, or a job
discovered later via polling after a disconnect) - they all funnel through
the single process_prostudio_generation completion path.

Uses the same FakeCursor/FakeConnection technique as
test_character_reference_library.py and the same process_prostudio_generation
fixture pattern as test_generation_completion_storage_decoupling.py.
"""
import asyncio
from contextlib import contextmanager

import pytest

import main


class FakeCursor:
    def __init__(self):
        self.executed = []

    def execute(self, sql, params=None):
        self.executed.append((sql, params))

    def fetchone(self):
        return None

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


def test_record_character_generation_history_inserts_with_conflict_guard(monkeypatch):
    cursor = FakeCursor()
    _patch_db(monkeypatch, cursor)

    main.record_character_generation_history(
        "custom_character_abc123", 42, "job-1",
        "https://cdn.sylvex.ai/result.png", "a cat", "gpt-image-2",
    )

    assert len(cursor.executed) == 1
    sql, params = cursor.executed[0]
    assert "prostudio_character_history" in sql
    assert "ON CONFLICT (character_id, job_id) DO NOTHING" in sql
    # id, character_id, telegram_id, job_id, media_url, prompt, model
    assert params[1] == "custom_character_abc123"
    assert params[2] == 42
    assert params[3] == "job-1"
    assert params[4] == "https://cdn.sylvex.ai/result.png"
    assert params[5] == "a cat"
    assert params[6] == "gpt-image-2"


@pytest.mark.parametrize("missing", ["character_id", "telegram_id", "job_id", "media_url"])
def test_record_character_generation_history_skips_without_required_fields(monkeypatch, missing):
    cursor = FakeCursor()
    _patch_db(monkeypatch, cursor)

    args = {
        "character_id": "custom_character_abc123",
        "telegram_id": 42,
        "job_id": "job-1",
        "media_url": "https://cdn.sylvex.ai/result.png",
    }
    args[missing] = "" if missing != "telegram_id" else 0

    main.record_character_generation_history(
        args["character_id"], args["telegram_id"], args["job_id"], args["media_url"],
    )

    assert cursor.executed == []


def test_record_character_generation_history_noop_without_database(monkeypatch):
    monkeypatch.setattr(main, "DATABASE_URL", "")
    # Must not raise and must not touch the DB layer at all.
    main.record_character_generation_history(
        "custom_character_abc123", 42, "job-1", "https://cdn.sylvex.ai/result.png",
    )


# ===== Integration: the single job-completion pipeline writes history
# exactly when a Character was selected on that request. =====

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

    async def fake_provider_request(*a, **k):
        return (
            {
                "ok": True,
                "type": "image",
                "status": "completed",
                "image_url": "https://cdn.sylvex.ai/generated.png",
                "images": ["https://cdn.sylvex.ai/generated.png"],
                "provider": "openai",
                "model": "gpt-image-2",
            },
            "completed",
        )
    monkeypatch.setattr(main, "run_prostudio_provider_request", fake_provider_request)
    return main


def _track_history_calls(monkeypatch, app):
    calls = []
    monkeypatch.setattr(
        app, "record_character_generation_history",
        lambda *a, **k: calls.append(a),
    )
    return calls


@pytest.mark.asyncio
async def test_completed_job_with_selected_character_writes_history(app, monkeypatch):
    calls = _track_history_calls(monkeypatch, app)
    payload = {
        "telegram_id": 42,
        "mode": "image",
        "prompt": "A hero portrait",
        "model": "gpt-image-2",
        "provider": "openai",
        "price_snapshot": {"final_credits": 5},
        "image_options": {"characterId": "custom_character_abc123", "characterName": "Islam"},
    }
    await app.process_prostudio_generation("job-char-1", payload)

    assert len(calls) == 1
    character_id, telegram_id, job_id, media_url, prompt, model = calls[0]
    assert character_id == "custom_character_abc123"
    assert telegram_id == 42
    assert job_id == "job-char-1"
    assert media_url == "https://cdn.sylvex.ai/generated.png"
    assert prompt == "A hero portrait"
    assert model == "gpt-image-2"


@pytest.mark.asyncio
async def test_completed_job_without_selected_character_writes_no_history(app, monkeypatch):
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
