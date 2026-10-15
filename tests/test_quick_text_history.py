"""Text chat history: pin / rename (conversation meta), pinned-first Text
list, and image attachments kept on reopened conversations.

Runs against a real Postgres when SYLVEX_TEST_DATABASE_URL is set."""
import asyncio
import json
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
def db(monkeypatch):
    monkeypatch.setattr(main, "DATABASE_URL", DB_URL)
    monkeypatch.setattr(main, "_PROSTUDIO_SCHEMA_READY", False)
    return int(str(uuid.uuid4().int)[:9])


def _save(tg, conv, prompt, attachment=None, mode="text"):
    payload = {"conversation_id": conv, "telegram_id": tg, "mode": mode, "prompt": prompt, "model": "gpt-5.6", "provider": "openai"}
    if attachment:
        payload["attachment"] = attachment
    return main.save_prostudio_message(payload, {"text": "answer to " + prompt, "metadata": {"usage": {"input_tokens": 1}}})


def _list(tg):
    return _run(main.public_prostudio_conversations(telegram_id=tg, mode="text", limit=30))["conversations"]


@needs_db
def test_pin_rename_order_and_image_persistence(db):
    tg = db
    image = {"kind": "image", "mime": "image/png", "name": "cat.png", "url": "https://cdn.example/cat.png"}
    _save(tg, "conv-a", "first", attachment=image)
    _save(tg, "conv-b", "second")
    _save(tg, "conv-img", "a picture", mode="image")
    assert [c["id"] for c in _list(tg)] == ["conv-b", "conv-a"]

    assert _run(main.update_public_prostudio_conversation_meta(FakeRequest({"conversation_id": "conv-a", "pinned": True}, tg))) == {"ok": True}
    assert _run(main.update_public_prostudio_conversation_meta(FakeRequest({"conversation_id": "conv-b", "title": "  My   plan "}, tg))) == {"ok": True}
    listed = _list(tg)
    assert [(c["id"], c["title"], c["pinned"]) for c in listed] == [("conv-a", "first", True), ("conv-b", "My plan", False)]

    # Renaming keeps the pin, unpinning keeps the title.
    _run(main.update_public_prostudio_conversation_meta(FakeRequest({"conversation_id": "conv-a", "title": "Pinned one"}, tg)))
    assert _list(tg)[0]["pinned"] is True and _list(tg)[0]["title"] == "Pinned one"
    _run(main.update_public_prostudio_conversation_meta(FakeRequest({"conversation_id": "conv-a", "pinned": False}, tg)))
    assert [(c["id"], c["title"], c["pinned"]) for c in _list(tg)] == [("conv-b", "My plan", False), ("conv-a", "Pinned one", False)]

    messages = _run(main.public_prostudio_conversations(telegram_id=tg, conversation_id="conv-a"))["messages"]
    assert messages[0]["role"] == "user" and messages[0]["images"] == ["https://cdn.example/cat.png"]
    assert messages[1]["role"] == "assistant"

    _run(main.delete_public_prostudio_conversation(telegram_id=tg, conversation_id="conv-a"))
    assert [c["id"] for c in _list(tg)] == ["conv-b"]


@needs_db
def test_meta_only_for_own_conversations(db):
    tg = db
    _save(tg, "conv-own", "mine")
    other = _run(main.update_public_prostudio_conversation_meta(FakeRequest({"conversation_id": "conv-own", "pinned": True}, tg + 1)))
    assert other.status_code == 404
    assert _run(main.update_public_prostudio_conversation_meta(FakeRequest({"conversation_id": "conv-own"}, tg))).status_code == 400
    assert _run(main.update_public_prostudio_conversation_meta(FakeRequest({"conversation_id": "conv-own", "pinned": True}, 0))).status_code == 401


def test_inline_base64_images_are_not_stored_as_input_images():
    assert main.text_message_input_image({"mode": "text", "attachment": {"mime": "image/png", "dataBase64": "AAAA"}}) == ""
    assert main.text_message_input_image({"mode": "image", "attachment": {"mime": "image/png", "url": "https://x/y.png"}}) == ""
    assert main.text_message_input_image({"mode": "text", "attachment": {"mime": "image/png", "url": "javascript:alert(1)"}}) == ""
