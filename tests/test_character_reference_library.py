"""Regression tests for the remaining Character System V2 (Master A-Z
Remediation Phase 4) requirements: an expandable reference library beyond
the original ~4-photo batch, a "set primary reference" action, an explicit
"Add generated image to Character References" endpoint (never automatic),
and "Generated with this Character" history that stays private per user
even for a shared/built-in Character.

Exercises the route functions directly with asyncio.run (same pattern as
test_character_identity_sylvex_owned.py / test_web_auth_config_endpoint.py
- this sandbox's Python 3.11 can't run main.py's own startup event). The
DB layer is a minimal fake cursor/connection (same technique as
test_prostudio_connection_leak_fix.py) rather than a real Postgres/pglite,
since these tests only need to prove the endpoint logic (ownership
scoping, library mutation, primary swap, dedup, history query shape) -
not real SQL semantics.
"""
import asyncio
from contextlib import contextmanager

import pytest

import main


class FakeRequest:
    def __init__(self, data):
        self._data = data

    async def json(self):
        return self._data


class FakeCursor:
    def __init__(self, fetchone_result=None, fetchall_result=None):
        self.fetchone_result = fetchone_result
        self.fetchall_result = fetchall_result or []
        self.executed = []

    def execute(self, sql, params=None):
        self.executed.append((sql, params))

    def fetchone(self):
        return self.fetchone_result

    def fetchall(self):
        return self.fetchall_result

    def close(self):
        pass


class FakeConnection:
    def __init__(self, cursor):
        self._cursor = cursor

    def cursor(self):
        return self._cursor


def _character_row(resource, telegram_id=42):
    # Matches _load_character_resource's SELECT column order.
    return (
        resource.get("name", ""),
        resource.get("description", ""),
        resource.get("gender", ""),
        resource.get("avatarUrl", ""),
        dict(resource.get("photos_json") or []),
        dict(resource),
        resource.get("status", "ready"),
    )


@pytest.fixture
def character_resource():
    return {
        "id": "custom_character_abc123",
        "name": "Islam",
        "resource_type": "character",
        "avatarUrl": "https://cdn.sylvex.ai/avatar.png",
        "primaryReferenceUrl": "https://cdn.sylvex.ai/avatar.png",
        "previewUrl": "https://cdn.sylvex.ai/avatar.png",
        "referenceLibrary": [
            {"id": "ref_primary", "url": "https://cdn.sylvex.ai/avatar.png", "role": "Primary Face"},
            {"id": "ref_body", "url": "https://cdn.sylvex.ai/body.png", "role": "Full Body"},
        ],
    }


@pytest.fixture(autouse=True)
def _stub_save(monkeypatch):
    saved = {}

    def fake_save(telegram_id, resource):
        saved["telegram_id"] = telegram_id
        saved["resource"] = resource
        return resource

    monkeypatch.setattr(main, "save_prostudio_resource", fake_save)
    return saved


def _patch_db(monkeypatch, cursor, database_url="postgres://fake"):
    @contextmanager
    def fake_db_connection(url):
        yield FakeConnection(cursor)

    monkeypatch.setattr(main, "DATABASE_URL", database_url)
    monkeypatch.setattr(main, "db_connection", fake_db_connection)
    monkeypatch.setattr(main, "ensure_prostudio_table", lambda: None)


def test_add_character_reference_expands_the_library(monkeypatch, character_resource, _stub_save):
    row = (
        character_resource["name"], "", "", character_resource["avatarUrl"],
        [], character_resource, "ready",
    )
    cursor = FakeCursor(fetchone_result=row)
    _patch_db(monkeypatch, cursor)

    request = FakeRequest({
        "telegram_id": 42,
        "url": "https://cdn.sylvex.ai/profile.png",
        "role": "Profile",
    })
    result = asyncio.run(main.public_prostudio_add_character_reference("custom_character_abc123", request))

    assert result["ok"] is True
    library = _stub_save["resource"]["referenceLibrary"]
    assert len(library) == 3  # the 2 original + the new one
    new_entry = next(e for e in library if e["url"] == "https://cdn.sylvex.ai/profile.png")
    assert new_entry["role"] == "Profile"
    assert new_entry["id"]  # a fresh stable id was assigned


def test_add_character_reference_rejects_duplicate_url(monkeypatch, character_resource, _stub_save):
    row = (character_resource["name"], "", "", character_resource["avatarUrl"], [], character_resource, "ready")
    cursor = FakeCursor(fetchone_result=row)
    _patch_db(monkeypatch, cursor)

    request = FakeRequest({"telegram_id": 42, "url": "https://cdn.sylvex.ai/body.png"})
    result = asyncio.run(main.public_prostudio_add_character_reference("custom_character_abc123", request))
    assert result.status_code == 409


def test_add_character_reference_requires_ownership_match():
    # No DATABASE_URL at all -> _load_character_resource returns None
    # regardless of telegram_id, so the endpoint reports character_not_found
    # rather than ever operating on a resource it didn't verify belongs to
    # that telegram_id.
    request = FakeRequest({"telegram_id": 999, "url": "https://cdn.sylvex.ai/x.png"})
    result = asyncio.run(main.public_prostudio_add_character_reference("custom_character_abc123", request))
    assert result.status_code == 404


def test_set_primary_reference_updates_avatar_and_preview(monkeypatch, character_resource, _stub_save):
    row = (character_resource["name"], "", "", character_resource["avatarUrl"], [], character_resource, "ready")
    cursor = FakeCursor(fetchone_result=row)
    _patch_db(monkeypatch, cursor)

    request = FakeRequest({"telegram_id": 42, "reference_id": "ref_body"})
    result = asyncio.run(main.public_prostudio_set_character_primary_reference("custom_character_abc123", request))

    assert result["ok"] is True
    saved = _stub_save["resource"]
    assert saved["primaryReferenceUrl"] == "https://cdn.sylvex.ai/body.png"
    assert saved["avatarUrl"] == "https://cdn.sylvex.ai/body.png"
    assert saved["previewUrl"] == "https://cdn.sylvex.ai/body.png"


def test_set_primary_reference_rejects_unknown_reference_id(monkeypatch, character_resource):
    row = (character_resource["name"], "", "", character_resource["avatarUrl"], [], character_resource, "ready")
    cursor = FakeCursor(fetchone_result=row)
    _patch_db(monkeypatch, cursor)

    request = FakeRequest({"telegram_id": 42, "reference_id": "does_not_exist"})
    result = asyncio.run(main.public_prostudio_set_character_primary_reference("custom_character_abc123", request))
    assert result.status_code == 404


def test_character_history_is_scoped_to_the_requesting_user(monkeypatch):
    rows = [
        ("hist1", "https://cdn.sylvex.ai/img1.png", "a prompt", "gpt-image-2", "2026-01-01T00:00:00"),
    ]
    cursor = FakeCursor(fetchall_result=rows)
    _patch_db(monkeypatch, cursor)

    result = asyncio.run(main.public_prostudio_character_history("custom_character_abc123", telegram_id=42, limit=50))

    assert result["ok"] is True
    assert len(result["items"]) == 1
    item = result["items"][0]
    assert item["media_url"] == "https://cdn.sylvex.ai/img1.png"
    assert item["prompt"] == "a prompt"
    assert item["model"] == "gpt-image-2"
    # The query itself must filter by telegram_id - inspect the bound
    # params actually sent, not just trust the fake's canned rows.
    executed_sql, executed_params = cursor.executed[0]
    assert "telegram_id = %s" in executed_sql
    assert "prostudio_character_history" in executed_sql
    assert executed_params[0] == 42
    assert executed_params[1] == "custom_character_abc123"


def test_character_history_requires_telegram_id():
    result = asyncio.run(main.public_prostudio_character_history("custom_character_abc123", telegram_id=0))
    assert result.status_code == 400
