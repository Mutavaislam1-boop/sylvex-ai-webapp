"""Image thumbnails (Pillow decode + R2 upload, multiplied by quantity)
used to run synchronously inside finalize_image_result/the BytePlus
provider path before the image result was returned to the job pipeline -
delaying an already-successful provider result exactly like the R2
persistence bug this session already fixed. Thumbnails are now computed
in the background after the original image is already the job's visible
result; a thumbnail failure only ever sets thumbnail_status, never the
generation result itself."""
import asyncio

import pytest


@pytest.mark.asyncio
async def test_finalize_image_result_does_not_wait_for_thumbnails_when_job_id_present(monkeypatch):
    import main

    background_tasks = []
    monkeypatch.setattr(main.asyncio, "create_task", lambda coro: background_tasks.append(coro) or coro)

    thumbnail_started = {"value": False}

    def slow_create_thumbnails(image_urls, size=256):
        thumbnail_started["value"] = True
        return ["https://r2.example/thumb.jpg" for _ in image_urls]

    monkeypatch.setattr(main, "create_image_thumbnails", slow_create_thumbnails)
    monkeypatch.setattr(main, "materialize_image_urls", lambda urls: list(urls))

    async def fake_telegram_send(*a, **k):
        return True
    monkeypatch.setattr(main, "send_generated_images_to_telegram", lambda *a, **k: True)

    result = await main.finalize_image_result(
        {"telegram_id": 1, "job_id": "job-thumb-1", "skip_telegram": True},
        ["https://ideogram.ai/api/images/ephemeral/abc.png"],
    )

    assert thumbnail_started["value"] is False, "thumbnails must not be computed before the image result returns"
    assert result["image_url"] == "https://ideogram.ai/api/images/ephemeral/abc.png"
    assert result["thumbnail_status"] == "pending"
    assert result["thumbnails"] == []
    assert len(background_tasks) == 1

    merge_calls = []
    monkeypatch.setattr(main, "_merge_prostudio_result_fields", lambda job_id, fields: merge_calls.append((job_id, fields)))
    await background_tasks[0]

    assert thumbnail_started["value"] is True, "the background task must still actually compute thumbnails"
    assert len(merge_calls) == 1
    job_id, fields = merge_calls[0]
    assert job_id == "job-thumb-1"
    assert fields["thumbnail_status"] == "completed"
    assert fields["thumbnail_url"] == "https://r2.example/thumb.jpg"


@pytest.mark.asyncio
async def test_thumbnail_failure_only_sets_thumbnail_status(monkeypatch):
    import main

    def failing_create_thumbnails(image_urls, size=256):
        raise RuntimeError("Pillow decode failed")

    monkeypatch.setattr(main, "create_image_thumbnails", failing_create_thumbnails)

    merge_calls = []
    monkeypatch.setattr(main, "_merge_prostudio_result_fields", lambda job_id, fields: merge_calls.append((job_id, fields)))

    await main._finalize_image_thumbnails_background("job-thumb-2", ["https://example.com/a.png"])

    assert merge_calls == [("job-thumb-2", {"thumbnail_status": "failed"})]


@pytest.mark.asyncio
async def test_finalize_image_result_without_job_id_keeps_synchronous_behavior(monkeypatch):
    """Callers outside the job pipeline (e.g. character/resource image
    generation) must be completely unaffected by this change."""
    import main

    background_tasks = []
    monkeypatch.setattr(main.asyncio, "create_task", lambda coro: background_tasks.append(coro) or coro)
    monkeypatch.setattr(main, "create_image_thumbnails", lambda urls, size=256: ["https://r2.example/thumb.jpg" for _ in urls])
    monkeypatch.setattr(main, "materialize_image_urls", lambda urls: list(urls))

    result = await main.finalize_image_result(
        {"telegram_id": 1, "skip_telegram": True},
        ["https://example.com/a.png"],
    )

    assert background_tasks == [], "no job_id means no job pipeline, so no background deferral"
    assert result["thumbnail_url"] == "https://r2.example/thumb.jpg"
    assert result["thumbnails"] == ["https://r2.example/thumb.jpg"]
