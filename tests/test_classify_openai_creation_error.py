"""Regression tests for remediation item #21B (DUP-2): the billing-limit/
safety-policy/generic error-text classification that
_run_character_creation_job() and _run_object_creation_job() each ran
inline, regex for regex, was extracted into one shared
classify_openai_creation_error(error_text, safety_message) helper in
main.py. Only the safety-policy message differs between the two callers
(each already-translated, already-different user-facing Character vs
Object text) - the billing-limit regex/message, the safety regex, and the
generic truncate-to-1200 fallback were always identical and are proven
here directly, plus end-to-end through both job runners to confirm the
exact same classification each produced before the extraction still
comes out today."""
import asyncio

import pytest

import main

CHARACTER_SAFETY_MESSAGE = (
    "Не удалось сгенерировать референс персонажа: запрос был отклонён системой безопасности "
    "провайдера изображений. Попробуйте другое фото или измените описание персонажа."
)
OBJECT_SAFETY_MESSAGE = (
    "Не удалось сгенерировать референс объекта: запрос был отклонён системой безопасности "
    "провайдера изображений. Попробуйте другое фото или измените описание объекта."
)
BILLING_MESSAGE = "Лимит расходов OpenAI исчерпан. Пополните баланс или увеличьте бюджет API-проекта OpenAI."


# ---------------------------------------------------------------------------
# classify_openai_creation_error() itself
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("error_text", [
    "Error: OpenAI billing hard limit has been reached",
    "Request failed: billing limit exceeded for this project",
    "status=400 insufficient_quota: you have run out of credits",
    "insufficient quota remaining",
])
def test_billing_limit_errors_are_classified_the_same_regardless_of_caller(error_text):
    character_result = main.classify_openai_creation_error(error_text, CHARACTER_SAFETY_MESSAGE)
    object_result = main.classify_openai_creation_error(error_text, OBJECT_SAFETY_MESSAGE)
    assert character_result == {"ok": False, "error": BILLING_MESSAGE, "provider": "openai"}
    assert object_result == {"ok": False, "error": BILLING_MESSAGE, "provider": "openai"}


@pytest.mark.parametrize("error_text", [
    "status=400 safety_violations=[sexual]",
    "Rejected by the safety system",
    "blocked: content policy violation",
    "flagged by moderation",
])
def test_safety_violation_errors_use_the_callers_own_message(error_text):
    character_result = main.classify_openai_creation_error(error_text, CHARACTER_SAFETY_MESSAGE)
    object_result = main.classify_openai_creation_error(error_text, OBJECT_SAFETY_MESSAGE)
    assert character_result == {"ok": False, "error": CHARACTER_SAFETY_MESSAGE, "provider": "openai"}
    assert object_result == {"ok": False, "error": OBJECT_SAFETY_MESSAGE, "provider": "openai"}
    # The raw provider diagnostic must never leak into the user-facing text.
    assert "safety_violations" not in character_result["error"]
    assert "safety_violations" not in object_result["error"]


def test_billing_limit_takes_precedence_when_both_patterns_somehow_match():
    error_text = "billing hard limit reached, and also safety_violations=[x]"
    result = main.classify_openai_creation_error(error_text, CHARACTER_SAFETY_MESSAGE)
    assert result["error"] == BILLING_MESSAGE


def test_unrecognized_errors_fall_back_to_the_raw_text_truncated_to_1200_chars():
    error_text = "some unrelated provider failure " + ("x" * 2000)
    result = main.classify_openai_creation_error(error_text, CHARACTER_SAFETY_MESSAGE)
    assert result == {"ok": False, "error": error_text[:1200]}
    assert len(result["error"]) == 1200


def test_unrecognized_short_error_is_returned_verbatim_with_no_provider_key():
    result = main.classify_openai_creation_error("a short unrelated failure", CHARACTER_SAFETY_MESSAGE)
    assert result == {"ok": False, "error": "a short unrelated failure"}
    assert "provider" not in result


# ---------------------------------------------------------------------------
# End-to-end through both job runners: the exact classification each
# produced before the extraction must still come out today.
# ---------------------------------------------------------------------------

@pytest.fixture
def stub_character_pipeline(monkeypatch):
    monkeypatch.setattr(main, "heartbeat_prostudio_generation_job", lambda job_id: None)


def _run_character_job_with_failure(monkeypatch, exc):
    async def failing_generate_images(job_id, name, gender, description, photos):
        raise exc

    updates = []
    monkeypatch.setattr(main, "_generate_openai_character_images", failing_generate_images)
    monkeypatch.setattr(main, "heartbeat_prostudio_generation_job", lambda job_id: None)
    monkeypatch.setattr(
        main, "update_prostudio_generation_job",
        lambda job_id, status, result=None, error=None, conversation_id="": updates.append((status, result, error)),
    )
    asyncio.run(main._run_character_creation_job("job-1", 42, "Islam", "male", "", ["https://cdn.sylvex.ai/a.jpg"]))
    assert updates
    return updates[-1]


def _run_object_job_with_failure(monkeypatch, exc):
    async def failing_generate_reference(job_id, name, description, source_photo):
        raise exc

    async def fake_analyze_prompt(job_id, name, description, image_url):
        return "a fallback description"

    updates = []
    monkeypatch.setattr(main, "_generate_object_reference_image", failing_generate_reference)
    monkeypatch.setattr(main, "_analyze_object_prompt", fake_analyze_prompt)
    monkeypatch.setattr(main, "heartbeat_prostudio_generation_job", lambda job_id: None)
    monkeypatch.setattr(
        main, "update_prostudio_generation_job",
        lambda job_id, status, result=None, error=None, conversation_id="": updates.append((status, result, error)),
    )
    asyncio.run(main._run_object_creation_job("job-1", 42, "Watch", "", ["https://cdn.sylvex.ai/a.jpg"]))
    assert updates
    return updates[-1]


def test_character_job_billing_limit_failure_matches_the_shared_classification(monkeypatch):
    status, result, error = _run_character_job_with_failure(monkeypatch, RuntimeError("OpenAI billing hard limit has been reached"))
    assert status == "failed"
    assert error == {"ok": False, "error": BILLING_MESSAGE, "provider": "openai"}


def test_character_job_safety_violation_failure_uses_the_character_specific_message(monkeypatch):
    status, result, error = _run_character_job_with_failure(monkeypatch, RuntimeError("status=400 safety_violations=[sexual]"))
    assert status == "failed"
    assert error == {"ok": False, "error": CHARACTER_SAFETY_MESSAGE, "provider": "openai"}
    assert "safety_violations" not in error["error"]


def test_object_job_billing_limit_failure_matches_the_shared_classification(monkeypatch):
    status, result, error = _run_object_job_with_failure(monkeypatch, RuntimeError("billing hard limit reached"))
    assert status == "failed"
    assert error == {"ok": False, "error": BILLING_MESSAGE, "provider": "openai"}


def test_object_job_safety_violation_failure_uses_the_object_specific_message(monkeypatch):
    status, result, error = _run_object_job_with_failure(monkeypatch, RuntimeError("Rejected by safety_violations=[sexual]"))
    assert status == "failed"
    assert error == {"ok": False, "error": OBJECT_SAFETY_MESSAGE, "provider": "openai"}
    assert "safety_violations" not in error["error"]


def test_character_and_object_safety_messages_remain_distinct():
    # The one behavior DUP-2 explicitly must preserve: Character and
    # Object keep their own, different safety-policy wording even though
    # the classification logic itself is now shared.
    assert CHARACTER_SAFETY_MESSAGE != OBJECT_SAFETY_MESSAGE
    character_result = main.classify_openai_creation_error("content policy violation", CHARACTER_SAFETY_MESSAGE)
    object_result = main.classify_openai_creation_error("content policy violation", OBJECT_SAFETY_MESSAGE)
    assert character_result["error"] != object_result["error"]
