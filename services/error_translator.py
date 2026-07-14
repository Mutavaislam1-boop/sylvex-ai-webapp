import json
import re
from typing import Any


DEFAULT_USER_ERROR = "Во время генерации произошла временная ошибка сервиса. Попробуйте повторить попытку немного позже."


def raw_error_text(value: Any, fallback: str = "") -> str:
    if isinstance(value, str):
        return value.strip() or fallback
    if isinstance(value, BaseException):
        return str(value) or fallback
    if isinstance(value, dict):
        for key in (
            "message", "error", "detail", "details", "body_preview", "msg",
            "status", "code", "provider_response",
        ):
            nested = value.get(key)
            if nested in (None, ""):
                continue
            text = raw_error_text(nested, "")
            if text:
                return text
        try:
            return json.dumps(value, ensure_ascii=False)[:2000]
        except Exception:
            return fallback
    if isinstance(value, list):
        for item in value:
            text = raw_error_text(item, "")
            if text:
                return text
        try:
            return json.dumps(value, ensure_ascii=False)[:2000]
        except Exception:
            return fallback
    if value is not None:
        return str(value)
    return fallback


def translate_provider_error(value: Any, provider: str = "", model: str = "", fallback: str = DEFAULT_USER_ERROR) -> str:
    text = raw_error_text(value, "")
    low = text.lower()
    provider_low = (provider or "").lower()

    if re.search(r"prompt.*size.*between.*0.*3072|prompt.*3072|size must be between", low):
        if provider_low == "kling" or "kling" in low:
            return "Описание слишком длинное для выбранной модели.\nМаксимальная длина текста для Kling — 3072 символа.\nСократите описание и попробуйте снова."
        return "Описание слишком длинное для выбранной модели. Сократите текст и попробуйте снова."
    if re.search(r"unknown parameter|unsupported parameter|invalid parameter|unrecognized.*parameter|candidate_count", low):
        return "Выбранные параметры не поддерживаются этой моделью.\nИзмените настройки генерации и попробуйте снова."
    if re.search(r"duration.*not supported|unsupported.*duration|video too long|duration.*limit", low):
        return "Длительность видео превышает допустимый лимит для выбранной модели."
    if re.search(r"resolution.*not supported|unsupported.*resolution|size.*not supported", low):
        return "Выбранное разрешение временно недоступно для этой модели. Измените настройки и попробуйте снова."
    if re.search(r"image too large|file too large|payload too large|413", low):
        return "Размер изображения превышает допустимый лимит.\nУменьшите размер файла и повторите попытку."
    if re.search(r"invalid image|image.*invalid|cannot process.*image|bad image|unsupported image", low):
        return "Не удалось обработать загруженное изображение.\nПопробуйте выбрать другое изображение."
    if re.search(r"sensitive|safety|policy|moderation|blocked|content.*violat", low):
        return "Запрос не может быть обработан из-за ограничений выбранной AI-модели.\nПопробуйте изменить изображение или описание."
    if re.search(r"rate limit|too many requests|429|overloaded|busy", low):
        return "Сервис сейчас перегружен большим количеством запросов.\nПовторите попытку через несколько минут."
    if re.search(r"quota|insufficient quota|credit.*exceed|limit.*exceed", low):
        return "Временный лимит генераций исчерпан.\nПовторите попытку позже."
    if re.search(r"timeout|timed out|readtimeout|deadline", low):
        return "Генерация заняла слишком много времени.\nПопробуйте выполнить запрос ещё раз."
    if re.search(r"api key|missing key|invalid key|unauthorized|401|forbidden|403|authentication|permission", low):
        return "Сервис генерации временно недоступен.\nМы уже получили информацию об ошибке. Попробуйте немного позже."
    if re.search(r"provider returned invalid response|invalid response|non-json|json decode|html|empty response", low):
        return "Сервис временно вернул некорректный ответ.\nПопробуйте повторить генерацию через несколько секунд."
    if re.search(r"http\s*503|status_code.*503|\b503\b|service unavailable|temporarily unavailable", low):
        return "Сервис сейчас временно недоступен.\nПовторите попытку немного позже."
    if re.search(r"http\s*500|status_code.*500|\b500\b|internal server error|bad gateway|\b502\b|\b504\b", low):
        return "Во время генерации произошла временная ошибка сервиса.\nПопробуйте немного позже."
    if re.search(r"badrequest|bad request|http\s*400|\b400\b", low):
        return "Выбранные параметры не поддерживаются этой моделью.\nИзмените настройки генерации и попробуйте снова."
    if re.search(r"provider|request|response|traceback|exception|stack|json|http|badrequest|internal server|unknown parameter", low):
        return fallback
    return fallback


def translated_error_payload(value: Any, provider: str = "", model: str = "", fallback: str = DEFAULT_USER_ERROR) -> dict:
    raw = raw_error_text(value, "")
    user_message = translate_provider_error(value, provider=provider, model=model, fallback=fallback)
    return {
        "error": user_message,
        "message": user_message,
        "raw_error": raw,
    }
