"""Regression tests for Master A-Z Remediation Phase 13 (Telegram
completion/error notifications): a terminal job failure must notify the
user via Telegram regardless of whether the Mini App is open - the
successful-generation half of this (sync_completed_generation_to_telegram)
already existed and is called from inside the background worker
(process_prostudio_generation), independent of any client connection; the
failed half did not exist at all before this fix. The notice must be a
curated, calm sentence (never a raw provider error/stack trace) and must
never fire twice for the same terminal transition.
"""
import asyncio

import pytest

import main


def _fake_response(status_code=200, ok=True):
    class _Resp:
        def __init__(self):
            self.status_code = status_code
            self.content = b'{"ok": true}'

        def json(self):
            return {"ok": ok}

    return _Resp()


def test_no_telegram_id_never_calls_the_api(monkeypatch):
    calls = []
    monkeypatch.setattr(main, "BOT_TOKEN", "test-token")
    monkeypatch.setattr(main.requests, "post", lambda *a, **kw: calls.append(a) or _fake_response())

    sent = asyncio.run(main.notify_telegram_generation_failed(0, "image"))
    assert sent is False
    assert calls == []


def test_no_bot_token_never_calls_the_api(monkeypatch):
    calls = []
    monkeypatch.setattr(main, "BOT_TOKEN", "")
    monkeypatch.setattr(main.requests, "post", lambda *a, **kw: calls.append(a) or _fake_response())

    sent = asyncio.run(main.notify_telegram_generation_failed(42, "image"))
    assert sent is False
    assert calls == []


def test_text_mode_never_notifies_telegram(monkeypatch):
    # Text failures are shown inline in the chat and are never billed - a
    # push notification would be redundant noise.
    calls = []
    monkeypatch.setattr(main, "BOT_TOKEN", "test-token")
    monkeypatch.setattr(main.requests, "post", lambda *a, **kw: calls.append(a) or _fake_response())

    sent = asyncio.run(main.notify_telegram_generation_failed(42, "text"))
    assert sent is False
    assert calls == []


def test_unknown_mode_never_notifies_telegram(monkeypatch):
    calls = []
    monkeypatch.setattr(main, "BOT_TOKEN", "test-token")
    monkeypatch.setattr(main.requests, "post", lambda *a, **kw: calls.append(a) or _fake_response())

    sent = asyncio.run(main.notify_telegram_generation_failed(42, ""))
    assert sent is False
    assert calls == []


@pytest.mark.parametrize("mode", ["image", "video", "music", "voice"])
def test_each_generation_mode_sends_a_curated_sentence(monkeypatch, mode):
    requests_made = []

    def fake_post(url, json=None, timeout=None):
        requests_made.append((url, json))
        return _fake_response()

    monkeypatch.setattr(main, "BOT_TOKEN", "test-token")
    monkeypatch.setattr(main.requests, "post", fake_post)

    sent = asyncio.run(main.notify_telegram_generation_failed(777, mode))

    assert sent is True
    assert len(requests_made) == 1
    url, body = requests_made[0]
    assert url.endswith("/sendMessage")
    assert body["chat_id"] == 777
    # Never a raw provider error, stack trace or technical identifier -
    # just the curated calm sentence for this mode.
    assert body["text"] == "Генерация не удалась ❌\nSYLVEX Pro Studio\n\n" + main._GENERATION_FAILED_TELEGRAM_TEXT[mode]
    assert "Traceback" not in body["text"]
    assert "Exception" not in body["text"]


def test_failed_telegram_delivery_is_reported_as_not_sent(monkeypatch):
    monkeypatch.setattr(main, "BOT_TOKEN", "test-token")
    monkeypatch.setattr(main.requests, "post", lambda *a, **kw: _fake_response(status_code=500, ok=False))

    sent = asyncio.run(main.notify_telegram_generation_failed(777, "image"))
    assert sent is False


def test_timeout_path_notifies_telegram_only_when_the_db_transition_succeeds(monkeypatch):
    # Mirrors tests/test_prostudio_job_hard_timeout.py's own timeout
    # scenario but asserts on the new notify call specifically: it must
    # fire only when update_prostudio_generation_job actually recorded
    # this failure as the terminal transition (never on a late/duplicate
    # callback racing a job that was already terminal).
    notified = []

    async def fake_notify(telegram_id, mode):
        notified.append((telegram_id, mode))
        return True

    monkeypatch.setattr(main, "notify_telegram_generation_failed", fake_notify)
    monkeypatch.setattr(main, "log_prostudio_error", lambda *a, **kw: None)
    monkeypatch.setattr(main, "prostudio_debug", lambda *a, **kw: None)

    async def hanging_process(job_id, payload):
        await asyncio.Event().wait()

    monkeypatch.setattr(main, "process_prostudio_generation", hanging_process)
    monkeypatch.setattr(main, "PROSTUDIO_MAX_JOB_RUNTIME_SECONDS", 0.03)

    monkeypatch.setattr(main, "update_prostudio_generation_job", lambda *a, **kw: True)
    asyncio.run(main.run_prostudio_generation_with_timeout("job-1", {"telegram_id": 555, "mode": "video"}))
    assert notified == [(555, "video")]

    notified.clear()
    monkeypatch.setattr(main, "update_prostudio_generation_job", lambda *a, **kw: False)
    asyncio.run(main.run_prostudio_generation_with_timeout("job-2", {"telegram_id": 555, "mode": "video"}))
    assert notified == []
