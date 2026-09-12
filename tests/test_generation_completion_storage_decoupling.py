"""Non-negotiable rule: the AI provider's own response is on the critical
user path; R2 persistence, thumbnails, history, and Telegram delivery are
side effects. A storage failure must never turn an already-successful
provider result into generation_status=failed - it must only ever affect
a separate storage_status, resolved in the background after the job is
already visible to the user.

This directly covers the production incident where an Ideogram image
generation succeeded but R2's SignatureDoesNotMatch during the old
synchronous persist-then-verify step turned the whole job into "failed"."""
import asyncio

import pytest


@pytest.fixture
def app(monkeypatch):
    import main
    monkeypatch.setattr(main, "DATABASE_URL", "postgres://test")
    monkeypatch.setattr(main, "PROSTUDIO_MOCK_GENERATION", False)
    monkeypatch.setattr(main, "optimize_prompt_for_model", lambda *a, **k: {"ok": True, "optimized": False})
    monkeypatch.setattr(main, "resolve_prostudio_provider_for_slot", lambda *a, **k: "IDEOGRAM")
    monkeypatch.setattr(main, "circuit_before_request", lambda *a, **k: {"allowed": True})
    monkeypatch.setattr(main, "circuit_release_probe", lambda *a, **k: None)
    monkeypatch.setattr(main, "heartbeat_prostudio_generation_job", lambda *a, **k: None)
    monkeypatch.setattr(main, "log_user_event", lambda *a, **k: None)
    monkeypatch.setattr(main, "save_generation", lambda *a, **k: None)
    monkeypatch.setattr(main, "build_prostudio_metadata", lambda *a, **k: {})
    monkeypatch.setattr(main, "save_prostudio_message", lambda *a, **k: "conv-1")
    monkeypatch.setattr(main, "charge_generation_balance", lambda *a, **k: {"charged": True, "balance_after": 100})

    async def fake_telegram(*a, **k):
        return True
    monkeypatch.setattr(main, "sync_completed_generation_to_telegram", fake_telegram)
    return main


def _track_job_updates(monkeypatch, app):
    calls = []

    def fake_update(job_id, status, result=None, error=None, conversation_id=""):
        calls.append({"job_id": job_id, "status": status, "result": result, "error": error})
        return True

    monkeypatch.setattr(app, "update_prostudio_generation_job", fake_update)
    return calls


class _InlineTask:
    """Stand-in for asyncio.create_task that exposes the coroutine so the
    test can await it explicitly and deterministically, instead of racing
    the real event loop's scheduling of a fire-and-forget task."""

    def __init__(self, coro):
        self.coro = coro


def _capture_background_tasks(monkeypatch, app):
    created = []
    monkeypatch.setattr(app.asyncio, "create_task", lambda coro: created.append(coro) or _InlineTask(coro))
    return created


@pytest.mark.asyncio
async def test_r2_failure_after_provider_success_still_completes_the_job(app, monkeypatch):
    """This is the exact production scenario: Ideogram (or any provider)
    returns a successful image, but the background R2 persist+verify step
    fails with SignatureDoesNotMatch. The job must still read completed."""
    job_updates = _track_job_updates(monkeypatch, app)
    background_tasks = _capture_background_tasks(monkeypatch, app)

    async def fake_provider_request(*a, **k):
        return (
            {
                "ok": True,
                "type": "image",
                "status": "completed",
                "image_url": "https://ideogram.ai/api/images/ephemeral/abc.png?exp=1",
                "images": ["https://ideogram.ai/api/images/ephemeral/abc.png?exp=1"],
                "provider": "ideogram",
                "model": "ideogram_3_0",
            },
            "completed",
        )

    monkeypatch.setattr(app, "run_prostudio_provider_request", fake_provider_request)

    def failing_verify(result, mode):
        raise RuntimeError("R2 persistence verification failed: SignatureDoesNotMatch")

    monkeypatch.setattr(app, "verify_persisted_generation_media", failing_verify)
    monkeypatch.setattr(app, "persist_generation_media", lambda result, mode: result)

    payload = {
        "telegram_id": 555,
        "mode": "image",
        "prompt": "Радуга",
        "model": "ideogram_3_0",
        "provider": "ideogram",
        "price_snapshot": {"final_credits": 10},
    }
    await app.process_prostudio_generation("job-r2-fail", payload)

    completed_updates = [c for c in job_updates if c["status"] == "completed"]
    failed_updates = [c for c in job_updates if c["status"] == "failed"]
    assert completed_updates, "provider success must commit generation_status=completed synchronously"
    assert not failed_updates, "an R2/storage failure must never flip generation_status to failed"
    assert completed_updates[0]["result"]["storage_status"] == "pending"
    # The ephemeral provider URL is what the user/Telegram see immediately -
    # nothing waits for R2 before this commit happens.
    assert "ideogram.ai" in completed_updates[0]["result"]["image_url"]

    assert len(background_tasks) == 1, "R2 persistence must be scheduled as a background task, not awaited inline"

    # Running the background task to completion must not raise, and must
    # only ever touch storage_status via the safe merge helper - never the
    # job's terminal status.
    merge_calls = []
    monkeypatch.setattr(
        app, "_merge_prostudio_storage_result",
        lambda job_id, fields, status: merge_calls.append((job_id, fields, status)),
    )
    await background_tasks[0]
    assert merge_calls == [("job-r2-fail", {}, "failed")]


@pytest.mark.asyncio
async def test_r2_success_marks_storage_completed_via_background_merge(app, monkeypatch):
    background_tasks = _capture_background_tasks(monkeypatch, app)
    _track_job_updates(monkeypatch, app)

    async def fake_provider_request(*a, **k):
        return (
            {
                "ok": True,
                "type": "image",
                "status": "completed",
                "image_url": "https://provider.example/tmp.png",
                "images": ["https://provider.example/tmp.png"],
                "provider": "ideogram",
                "model": "ideogram_3_0",
            },
            "completed",
        )

    monkeypatch.setattr(app, "run_prostudio_provider_request", fake_provider_request)
    monkeypatch.setattr(app, "persist_generation_media", lambda result, mode: {**result, "image_url": "https://r2.example/permanent.png", "images": ["https://r2.example/permanent.png"]})
    monkeypatch.setattr(app, "verify_persisted_generation_media", lambda result, mode: result["images"])

    payload = {
        "telegram_id": 556, "mode": "image", "prompt": "cat",
        "model": "ideogram_3_0", "provider": "ideogram",
        "price_snapshot": {"final_credits": 10},
    }
    await app.process_prostudio_generation("job-r2-ok", payload)
    assert len(background_tasks) == 1

    merge_calls = []
    monkeypatch.setattr(
        app, "_merge_prostudio_storage_result",
        lambda job_id, fields, status: merge_calls.append((job_id, fields, status)),
    )
    await background_tasks[0]
    assert len(merge_calls) == 1
    job_id, fields, status = merge_calls[0]
    assert job_id == "job-r2-ok"
    assert status == "completed"
    assert fields["image_url"] == "https://r2.example/permanent.png"
