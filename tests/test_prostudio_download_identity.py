import json
import io
import zipfile

import pytest
from fastapi import HTTPException, Request

import main


class _Cursor:
    def __init__(self, row):
        self.row = row

    def execute(self, _query, _params):
        return None

    def fetchone(self):
        return self.row

    def close(self):
        return None


class _Connection:
    def __init__(self, row):
        self.row = row

    def cursor(self):
        return _Cursor(self.row)

    def close(self):
        return None


def _request(owner_id, auth_kind="web"):
    return Request({
        "type": "http",
        "method": "GET",
        "path": "/api/public/prostudio/download/job-1",
        "query_string": b"",
        "headers": [],
        "state": {"telegram_id": owner_id, "auth_kind": auth_kind},
    })


def _download_mocks(monkeypatch, owner_id):
    result = json.dumps({
        "ok": True,
        "type": "image",
        "image_url": "/api/public/storage/generated/images/result.png",
    })
    row = (owner_id, "completed", "image", result)
    monkeypatch.setattr(main, "DATABASE_URL", "postgresql://test")
    monkeypatch.setattr(main, "db_connect", lambda _url: _Connection(row))
    monkeypatch.setattr(main, "storage_exists", lambda key: key == "generated/images/result.png")
    monkeypatch.setattr(
        main,
        "storage_get_object",
        lambda key: (b"png-result", "image/png", len(b"png-result")),
    )
    monkeypatch.setattr(main, "storage_iter_object", lambda body, max_bytes=None: iter((body,)))


async def _response_bytes(response):
    chunks = []
    async for chunk in response.body_iterator:
        chunks.append(chunk)
    return b"".join(chunks)


@pytest.mark.asyncio
async def test_web_session_owner_downloads_completed_generation_without_telegram_initdata(monkeypatch):
    owner_id = 9_000_000_000_777
    _download_mocks(monkeypatch, owner_id)

    response = await main.public_prostudio_download(
        _request(owner_id, "web"),
        "job-1",
        telegram_id=0,
        init_data="",
    )

    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    assert response.headers["content-disposition"].startswith('attachment; filename="sylvex-image-job-1.png"')
    assert await _response_bytes(response) == b"png-result"


@pytest.mark.asyncio
async def test_download_uses_authenticated_owner_and_denies_another_users_job(monkeypatch):
    _download_mocks(monkeypatch, owner_id=777)

    with pytest.raises(HTTPException) as error:
        await main.public_prostudio_download(
            _request(888, "web"),
            "job-1",
            telegram_id=777,
            init_data="forged",
        )

    assert error.value.status_code == 403
    assert error.value.detail == "job_access_denied"


@pytest.mark.asyncio
async def test_download_can_select_the_opened_image_from_a_multi_result_job(monkeypatch):
    owner_id = 9_000_000_000_778
    result = json.dumps({
        "ok": True,
        "type": "image",
        "images": [
            "/api/public/storage/generated/images/first.png",
            "/api/public/storage/generated/images/second.png",
        ],
    })
    row = (owner_id, "completed", "image", result)
    monkeypatch.setattr(main, "DATABASE_URL", "postgresql://test")
    monkeypatch.setattr(main, "db_connect", lambda _url: _Connection(row))
    monkeypatch.setattr(main, "storage_exists", lambda key: key in {
        "generated/images/first.png", "generated/images/second.png",
    })
    monkeypatch.setattr(
        main,
        "storage_get_object",
        lambda key: (key.encode(), "image/png", len(key.encode())),
    )
    monkeypatch.setattr(main, "storage_iter_object", lambda body, max_bytes=None: iter((body,)))

    response = await main.public_prostudio_download(
        _request(owner_id, "web"),
        "job-1",
        result_index=1,
    )

    assert response.status_code == 200
    assert await _response_bytes(response) == b"generated/images/second.png"


@pytest.mark.asyncio
async def test_grid_download_falls_back_to_private_project_media_after_reopen(monkeypatch):
    owner_id = 9_000_000_000_779
    result = json.dumps({"ok": True, "type": "video", "video_url": "https://provider.example/expired.mp4"})
    row = (owner_id, "completed", "video", result)
    monkeypatch.setattr(main, "DATABASE_URL", "postgresql://test")
    monkeypatch.setattr(main, "db_connect", lambda _url: _Connection(row))
    monkeypatch.setattr(main.grid_projects_service, "get", lambda _connect, owner, project: {
        "projectId": project,
        "nodes": [{"id": "grid_video_1", "output": {
            "type": "video", "url": "/api/public/storage/generated/videos/restored.mp4",
        }}],
    })
    monkeypatch.setattr(main, "storage_exists", lambda key: key == "generated/videos/restored.mp4")
    monkeypatch.setattr(main, "storage_get_object", lambda key: (b"video-result", "video/mp4", len(b"video-result")))
    monkeypatch.setattr(main, "storage_iter_object", lambda body, max_bytes=None: iter((body,)))

    response = await main.public_prostudio_download(
        _request(owner_id, "web"), "job-1",
        grid_project_id="grid_project_saved", grid_node_id="grid_video_1",
    )

    assert response.status_code == 200
    assert response.headers["content-type"] == "video/mp4"
    assert await _response_bytes(response) == b"video-result"


@pytest.mark.asyncio
async def test_grid_download_all_returns_one_zip_with_every_image(monkeypatch):
    owner_id = 9_000_000_000_780
    result = json.dumps({
        "ok": True, "type": "image", "images": [
            "/api/public/storage/generated/images/first.png",
            "/api/public/storage/generated/images/second.webp",
        ],
    })
    row = (owner_id, "completed", "image", result)
    monkeypatch.setattr(main, "DATABASE_URL", "postgresql://test")
    monkeypatch.setattr(main, "db_connect", lambda _url: _Connection(row))
    monkeypatch.setattr(main, "storage_exists", lambda key: key in {
        "generated/images/first.png", "generated/images/second.webp",
    })
    monkeypatch.setattr(main, "storage_read_bytes", lambda key: key.encode())

    response = await main.public_prostudio_download(
        _request(owner_id, "web"), "job-1", download_all=True,
    )

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    with zipfile.ZipFile(io.BytesIO(response.body)) as archive:
        assert archive.namelist() == ["sylvex-image-1.png", "sylvex-image-2.webp"]
        assert archive.read("sylvex-image-1.png") == b"generated/images/first.png"
