import asyncio
import io
import json
from pathlib import Path
from types import SimpleNamespace

from PIL import Image

import main
from services import edit_sessions, media_access, price_engine


def _png_bytes():
    output = io.BytesIO()
    Image.new("RGBA", (8, 8), (20, 40, 60, 128)).save(output, "PNG")
    return output.getvalue()


def test_private_database_url_has_priority_in_runtime_sources():
    root = Path(main.__file__).parent
    for relative in ("main.py", "services/storage.py", "services/security.py", "services/request_limits.py"):
        source = (root / relative).read_text()
        assert source.find("DATABASE_URL") < source.find("DATABASE_PUBLIC_URL")


def test_price_snapshot_does_not_copy_large_media_or_prompt_payloads():
    payload = {
        "mode": "image", "model": "gpt_image_2_5_sunburst", "provider": "openai",
        "image_options": {
            "referenceImageUrls": ["data:image/png;base64," + letter * 2_000_000 for letter in "ABCD"],
            "style_prompt": "restore " * 100_000,
            "quality": "high",
        },
    }
    snapshot = price_engine.create_price_snapshot(payload, {"credits": 10})
    encoded = json.dumps(snapshot)
    assert len(encoded) < 2_000
    assert snapshot["parameters"]["model"] == "gpt_image_2_5_sunburst"
    assert snapshot["parameters"]["image_options"]["referenceImageUrls"] == {"count": 4}
    assert snapshot["final_credits"] == 14  # four one-credit SYLVEX references


def test_new_generation_metadata_stores_one_canonical_settings_snapshot():
    payload = {"mode": "image", "model": "model", "image_options": {"quality": "high", "count": 1}}
    metadata = main.build_prostudio_metadata(payload, {"ok": True, "images": ["/generated/images/a.png"]})
    assert metadata["settings"] == payload["image_options"]
    assert "image_options" not in metadata
    assert "video_options" not in metadata
    assert "music_options" not in metadata
    assert "voice_options" not in metadata


def test_response_signing_reuses_one_presign_per_object(monkeypatch):
    calls = []
    monkeypatch.setattr(media_access, "media_key", lambda value: value.rsplit("/", 1)[-1])
    monkeypatch.setattr(media_access, "sign_media_url", lambda value: calls.append(value) or (value + "?signed=1"))
    result = media_access.sign_response_media({
        "image_url": "/api/public/storage/generated/images/a.png",
        "images": ["/api/public/storage/generated/images/a.png"],
        "thumbnail_url": "/api/public/storage/generated/images/a.png",
    })
    assert len(calls) == 1
    assert result["image_url"] == result["images"][0] == result["thumbnail_url"]


def test_edit_history_canonicalizes_expiring_media_capabilities():
    state = {
        "sessionId": "edit-test", "activeNodeId": "edit-node-1",
        "chain": [{
            "id": "edit-node-1", "parentId": None, "status": "ready", "x": 0, "y": 0,
            "slotWidth": 200, "slotHeight": 200,
            "url": "/api/public/storage/generated/images/a.png?media_exp=1&media_sig=old",
        }],
    }
    stable = edit_sessions.canonicalize_media(state)
    assert stable["chain"][0]["url"] == "/api/public/storage/generated/images/a.png"


def test_queue_notifications_preserve_100_slot_capacity_without_thundering_herd():
    assert main._bounded_prostudio_worker_concurrency(None) == 20

    async def exercise():
        signals = [main.ProstudioQueueSignal() for _ in range(5)]
        waiters = [
            asyncio.create_task(signal.wait(0, 1.0))
            for signal in signals for _ in range(20)
        ]
        await asyncio.sleep(0)
        for signal in signals:
            await signal.notify()
        await asyncio.sleep(0.02)
        assert sum(task.done() for task in waiters) == 5
        for signal in signals:
            for _ in range(19):
                await signal.notify()
        await asyncio.wait_for(asyncio.gather(*waiters), timeout=1.0)
        assert len(waiters) == 100
    asyncio.run(exercise())


def test_remote_provider_media_is_streamed_to_r2(monkeypatch, tmp_path):
    uploaded = {}

    def download(url, destination, timeout):
        Path(destination).write_bytes(b"video-data")
        return {"url": url, "headers": {"content-type": "video/mp4"}, "size": 10, "status_code": 200}

    def put(path, key, content_type, remove_local=False):
        uploaded.update(data=Path(path).read_bytes(), key=key, content_type=content_type)
        return "/api/public/storage/" + key

    monkeypatch.setattr(main, "safe_download_to_file", download)
    monkeypatch.setattr(main, "storage_put_file", put)
    monkeypatch.setattr(main, "storage_key_from_url", lambda value: "")
    monkeypatch.setattr(main, "r2_enabled", lambda: True)
    result = main._persist_remote_media_url("https://provider.example/result.mp4", "videos", "provider")
    assert result.startswith("/api/public/storage/generated/videos/")
    assert uploaded["data"] == b"video-data"
    assert uploaded["content_type"] == "video/mp4"


class _JsonRequest:
    def __init__(self, payload):
        self._payload = payload
        self.state = SimpleNamespace(account_storage_id=7, telegram_id=0)

    async def json(self):
        return self._payload


def test_direct_r2_upload_is_authorized_validated_and_registered(monkeypatch):
    content = _png_bytes()
    descriptor = {"filename": "photo.png", "content_type": "image/png", "size": len(content), "kind": "image"}
    monkeypatch.setattr(main, "storage_direct_upload_enabled", lambda: True)
    monkeypatch.setattr(main, "storage_presigned_put_url", lambda key, content_type: "https://r2.example/upload")
    monkeypatch.setattr(main, "signing_key", lambda: b"x" * 32)
    init = asyncio.run(main.public_prostudio_upload_media_init(_JsonRequest(descriptor)))
    assert init["direct"] is True and "upload_url" in init

    monkeypatch.setattr(main, "storage_head_object", lambda key: {"size": len(content), "content_type": "image/png"})
    monkeypatch.setattr(main, "storage_get_object", lambda key: (io.BytesIO(content), "image/png", len(content)))
    monkeypatch.setattr(main, "storage_register_existing_object", lambda key, mime, size: "/api/public/storage/" + key)
    complete_payload = dict(descriptor, object_key=init["object_key"], expires=init["expires"], upload_token=init["upload_token"])
    completed = asyncio.run(main.public_prostudio_upload_media_complete(_JsonRequest(complete_payload)))
    assert completed["ok"] is True
    assert completed["content_type"] == "image/png"
    assert completed["bytes"] == len(content)
