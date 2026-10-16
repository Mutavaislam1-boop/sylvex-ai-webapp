"""Music history track actions: favorite / rename keep the item in place.
Runs against a real Postgres when SYLVEX_TEST_DATABASE_URL is set."""
import asyncio
import os
import sys
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

import main

DB_URL = os.getenv("SYLVEX_TEST_DATABASE_URL", "")
needs_db = pytest.mark.skipif(not DB_URL, reason="Set SYLVEX_TEST_DATABASE_URL to run real-SQL tests")


class FakeRequest:
    def __init__(self, payload, telegram_id):
        self._payload = payload
        self.state = SimpleNamespace(telegram_id=telegram_id)

    async def json(self):
        return dict(self._payload)


def _run(coro):
    return asyncio.run(coro)


@pytest.fixture()
def tg(monkeypatch):
    monkeypatch.setattr(main, "DATABASE_URL", DB_URL)
    monkeypatch.setattr(main, "_PROSTUDIO_SCHEMA_READY", False)
    return int(str(uuid.uuid4().int)[:9])


def _track(tg, prompt, audio):
    result = {"text": "Музыка готова", "audio_url": audio, "audios": [audio], "image_url": "/c.png", "images": ["/c.png"], "title": prompt, "type": "music"}
    main.save_prostudio_message({"telegram_id": tg, "mode": "music", "prompt": prompt, "model": "suno_chirp_5_5", "provider": "suno"}, result)
    return result["message_id"]


def _music(tg):
    items = _run(main.public_prostudio_gallery(telegram_id=tg, limit=20))["items"]
    return [(i["id"], i["title"], i["favorite"]) for i in items if i["type"] == "music"]


@needs_db
def test_favorite_and_rename_keep_order(tg):
    first = _track(tg, "First", "/a.mp3")
    second = _track(tg, "Second", "/b.mp3")
    assert _music(tg) == [(second, "Second", False), (first, "First", False)]
    assert _run(main.update_public_prostudio_gallery_item(first, FakeRequest({"favorite": True}, tg))) == {"ok": True}
    assert _run(main.update_public_prostudio_gallery_item(first, FakeRequest({"title": "  My   track "}, tg))) == {"ok": True}
    assert _music(tg) == [(second, "Second", False), (first, "My track", True)]
    _run(main.update_public_prostudio_gallery_item(first, FakeRequest({"favorite": False}, tg)))
    assert _music(tg)[1] == (first, "My track", False)


@needs_db
def test_only_owner_can_change_and_input_is_validated(tg):
    track = _track(tg, "Mine", "/m.mp3")
    assert _run(main.update_public_prostudio_gallery_item(track, FakeRequest({"favorite": True}, tg + 1))).status_code == 404
    assert _run(main.update_public_prostudio_gallery_item(track, FakeRequest({"favorite": True}, 0))).status_code == 401
    assert _run(main.update_public_prostudio_gallery_item(track, FakeRequest({}, tg))).status_code == 400
    assert _run(main.update_public_prostudio_gallery_item(track, FakeRequest({"title": "   "}, tg))).status_code == 400
    assert _music(tg) == [(track, "Mine", False)]
