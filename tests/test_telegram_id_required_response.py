"""Regression tests for remediation item #22 (DUP-3): the identical
400 JSONResponse({"ok": False, "error": "telegram_id_required"})
construction, repeated at 32 separate endpoint call sites in main.py, was
extracted into one shared telegram_id_required_response() helper. Only
the response *construction* changed - how each endpoint obtains, parses,
or validates telegram_id before deciding to call the helper is untouched.

This file proves:
  - the helper itself returns exactly the required status/body;
  - all 32 former duplicate call sites now use the shared helper, and the
    exact literal construction appears exactly once in the whole file
    (inside the helper's own definition);
  - the 3 genuinely different occurrences (the differently-formatted
    inline one-liner, and the two raise HTTPException(...) call sites)
    were correctly left untouched;
  - a representative GET endpoint and a representative POST endpoint
    both still return the exact same 400 JSON response for a missing
    telegram_id;
  - the valid-telegram_id path on both of those endpoints is unaffected."""
import json
import pathlib

import pytest

import main

MAIN_PY_SOURCE = pathlib.Path(__file__).resolve().parent.parent.joinpath("main.py").read_text(encoding="utf-8")

EXPECTED_BODY = {"ok": False, "error": "telegram_id_required"}


class FakeRequest:
    def __init__(self, payload):
        self._payload = payload

    async def json(self):
        return dict(self._payload)


# ---------------------------------------------------------------------------
# The helper itself
# ---------------------------------------------------------------------------

def test_helper_returns_exactly_the_required_status_and_body():
    response = main.telegram_id_required_response()
    assert response.status_code == 400
    assert json.loads(response.body) == EXPECTED_BODY


def test_helper_returns_a_fresh_response_object_each_call():
    # Never a shared/cached instance accidentally reused across requests.
    assert main.telegram_id_required_response() is not main.telegram_id_required_response()


# ---------------------------------------------------------------------------
# Static source checks: exactly 31 call sites use the helper (32 before the
# dead legacy /prostudio/runway-avatar endpoint that used it was deleted), the raw
# literal construction appears nowhere else, and the 3 genuinely
# different occurrences were left alone.
# ---------------------------------------------------------------------------

def test_exactly_31_call_sites_now_use_the_shared_helper():
    count = MAIN_PY_SOURCE.count("return telegram_id_required_response()")
    assert count == 31, f"expected exactly 31 call sites using the helper, found {count}"


def test_the_raw_duplicate_literal_appears_only_inside_the_helpers_own_definition():
    literal = 'return JSONResponse({"ok": False, "error": "telegram_id_required"}, status_code=400)'
    count = MAIN_PY_SOURCE.count(literal)
    assert count == 1, (
        f"the exact duplicate construction must exist only inside telegram_id_required_response() "
        f"itself, found {count} occurrences"
    )


def test_the_three_genuinely_different_occurrences_were_left_untouched():
    # The differently-formatted one-liner (no spaces around the keys).
    assert MAIN_PY_SOURCE.count(
        '{"ok":False,"error":"telegram_id_required"}'
    ) == 1
    # The two raise HTTPException(...) call sites - a different mechanism
    # entirely (FastAPI exception handling, not a direct JSONResponse),
    # explicitly out of scope for this item.
    assert MAIN_PY_SOURCE.count(
        'raise HTTPException(status_code=400, detail="telegram_id_required")'
    ) == 2


# ---------------------------------------------------------------------------
# Representative GET endpoint: public_prostudio_active_job
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_endpoint_missing_telegram_id_returns_the_exact_400_response():
    response = await main.public_prostudio_active_job(telegram_id=0)
    assert response.status_code == 400
    assert json.loads(response.body) == EXPECTED_BODY


@pytest.mark.asyncio
async def test_get_endpoint_valid_telegram_id_path_is_unchanged(monkeypatch):
    monkeypatch.setattr(main, "get_active_prostudio_job", lambda telegram_id: {"id": "job-1", "status": "processing"})
    response = await main.public_prostudio_active_job(telegram_id=42)
    assert response == {
        "ok": True,
        "active": True,
        "active_job_id": "job-1",
        "status": "processing",
        "job": {"id": "job-1", "status": "processing"},
    }


# ---------------------------------------------------------------------------
# Representative POST endpoint: public_community_like
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_post_endpoint_missing_telegram_id_returns_the_exact_400_response():
    response = await main.public_community_like(post_id=1, request=FakeRequest({}))
    assert response.status_code == 400
    assert json.loads(response.body) == EXPECTED_BODY


@pytest.mark.asyncio
async def test_post_endpoint_valid_telegram_id_path_is_unchanged(monkeypatch):
    calls = []

    class FakeCursor:
        def execute(self, query, params=None):
            calls.append((query.strip().split()[0], params))

        def fetchone(self):
            return None  # not previously liked

        def close(self):
            pass

    class FakeConnection:
        def cursor(self):
            return FakeCursor()

        def commit(self):
            calls.append(("COMMIT", None))

        def close(self):
            pass

    monkeypatch.setattr(main, "ensure_community_tables", lambda: None)
    monkeypatch.setattr(main, "db_connect", lambda url: FakeConnection())

    response = await main.public_community_like(post_id=7, request=FakeRequest({"telegram_id": 42}))

    assert response == {"ok": True, "liked": True}
    # Proves the request proceeded past the telegram_id check into the
    # real DB-write path, not short-circuited by the 400 helper.
    assert any(query == "INSERT" for query, _ in calls)
