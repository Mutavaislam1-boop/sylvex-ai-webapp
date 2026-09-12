"""Text generation must stay on its direct, non-queued path, and a failed
non-critical side effect (saving conversation history) must never turn an
already-successful, already-billed generation into an error response."""
import pytest


class FakeRequest:
    def __init__(self, payload):
        self._payload = payload

    async def json(self):
        return dict(self._payload)


@pytest.fixture
def app(monkeypatch):
    import main
    monkeypatch.setattr(main, "get_user_state", lambda telegram_id, **k: {"subscription_status": "active", "balance": 1000})
    monkeypatch.setattr(main, "calculate_generation_price", lambda payload: {
        "credits": 1, "pricing_available": True, "price_snapshot": {"final_credits": 1}, "generation_cost": "1 ⚡",
    })
    monkeypatch.setattr(main, "get_active_prostudio_job", lambda telegram_id: {})
    monkeypatch.setattr(main, "reserve_direct_text_generation", lambda telegram_id, credits: "gen-1")
    monkeypatch.setattr(main, "release_direct_text_generation", lambda generation_id: None)
    monkeypatch.setattr(main, "charge_generation_balance", lambda telegram_id, generation_id, result, payload: {
        "charged": True, "balance_after": 999,
    })
    return main


def _payload():
    return {
        "telegram_id": 42,
        "mode": "text",
        "prompt": "hello",
        "model": "gpt-5.5",
        "provider": "sylvex-router",
    }


@pytest.mark.asyncio
async def test_history_save_failure_does_not_fail_a_successful_generation(app, monkeypatch):
    monkeypatch.setattr(app, "text_generation", lambda payload: {"ok": True, "text": "hi there"})

    def broken_save(payload, result):
        raise RuntimeError("history db is down")

    monkeypatch.setattr(app, "save_prostudio_message", broken_save)

    response = await app.public_prostudio_generate(FakeRequest(_payload()))

    assert isinstance(response, dict), f"expected the successful result dict, got {response!r}"
    assert response.get("ok") is True
    assert response.get("text") == "hi there"
    assert response.get("conversation_id") == ""


@pytest.mark.asyncio
async def test_text_generation_does_not_create_a_queued_job(app, monkeypatch):
    monkeypatch.setattr(app, "text_generation", lambda payload: {"ok": True, "text": "hi there"})
    monkeypatch.setattr(app, "save_prostudio_message", lambda payload, result: "conv-1")
    create_job_calls = []
    monkeypatch.setattr(app, "create_prostudio_generation_job", lambda payload: create_job_calls.append(payload) or "job-x")

    response = await app.public_prostudio_generate(FakeRequest(_payload()))

    assert response.get("ok") is True
    assert response.get("status") != "queued"
    assert not create_job_calls, "text must never go through the async job queue"


@pytest.mark.asyncio
async def test_provider_failure_still_returns_an_error_response(app, monkeypatch):
    monkeypatch.setattr(app, "text_generation", lambda payload: {"ok": False, "error": "provider exploded"})

    response = await app.public_prostudio_generate(FakeRequest(_payload()))

    assert getattr(response, "status_code", None) == 502
