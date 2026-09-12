"""Backend error strings surfaced toward the user must never read like a
developer/backend message. "Генерация не прошла. Проверь выбранную модель
или backend-провайдер." was returned by 3 BytePlus/Seedream image code
paths and could reach the user verbatim through translateGenerationError's
fallback - this pins the fix so it can't silently come back."""
from pathlib import Path

MAIN_PY = Path(__file__).parent.parent / "main.py"


def test_backend_provider_jargon_is_not_returned_to_users():
    source = MAIN_PY.read_text(encoding="utf-8")
    assert "backend-провайдер" not in source, (
        "a technical/developer-sounding error string leaked back into main.py - "
        "user-facing error text must be calm and free of backend terminology"
    )
