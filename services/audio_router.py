# =====================================================
# АВТОДОКУМЕНТАЦИЯ SYLVEX: services/audio_router.py
# Этот файл подписан русскими пояснениями для быстрой навигации по проекту.
# Комментарии описывают назначение блоков и не меняют работу приложения.
# =====================================================
import asyncio
import base64
import json
import os
import pathlib
import wave
from typing import Any
from uuid import uuid4

import httpx

from services.error_translator import raw_error_text, translate_provider_error
from services.prompt_optimizer import optimize_prompt_for_model


AUDIO_API_BASE_URL = os.getenv("AUDIO_API_BASE_URL", "https://udioapi.pro/api").rstrip("/")
AUDIO_GENERATE_ENDPOINT = os.getenv("AUDIO_API_GENERATE_ENDPOINT", f"{AUDIO_API_BASE_URL}/v2/generate")
AUDIO_FEED_ENDPOINT = os.getenv("AUDIO_API_FEED_ENDPOINT", f"{AUDIO_API_BASE_URL}/v2/feed")
BASE_DIR = pathlib.Path(__file__).resolve().parent.parent
WEBAPP_DIR = BASE_DIR / "webapp"
GENERATED_AUDIO_DIR = WEBAPP_DIR / "generated" / "audio"
GEMINI_TTS_ENDPOINT = os.getenv("GEMINI_TTS_ENDPOINT", "https://generativelanguage.googleapis.com/v1beta/interactions")

SUNO_MUSIC_MODEL_MAP = {
    "suno_chirp_3_5": "chirp-v3-5",
    "suno_chirp_4_0": "chirp-v4-0",
    "suno_chirp_4_5": "chirp-v4-5",
    "suno_chirp_5": "chirp-v5",
    "suno_chirp_5_5": "chirp-v5-5",
}

GEMINI_TTS_MODEL_MAP = {
    "gemini_3_1_flash_tts_preview": "gemini-3.1-flash-tts-preview",
    "gemini_2_5_flash_preview_tts": "gemini-2.5-flash-preview-tts",
    "gemini_2_5_pro_preview_tts": "gemini-2.5-pro-preview-tts",
    "gemini-3.1-flash-tts-preview": "gemini-3.1-flash-tts-preview",
    "gemini-2.5-flash-preview-tts": "gemini-2.5-flash-preview-tts",
    "gemini-2.5-pro-preview-tts": "gemini-2.5-pro-preview-tts",
}


# =====================================================
# PYTHON-БЛОК: safe_audio_json_response
# Выполняет отдельный шаг backend-логики SYLVEX.
# Связан с API, базой данных, провайдерами или подготовкой данных для Mini App.
# =====================================================
async def safe_audio_json_response(response, provider: str, endpoint: str):
    status = getattr(response, "status_code", None) or getattr(response, "status", None)
    try:
        text = response.text
        if callable(text):
            text = text()
    except Exception:
        try:
            text = await response.text()
        except Exception:
            text = ""

    if not text:
        return {
            "ok": False,
            "provider": provider,
            "status_code": status,
            "error": "Provider returned empty response",
            "endpoint": endpoint,
            "body_preview": "",
        }

    try:
        return json.loads(text)
    except Exception as exc:
        return {
            "ok": False,
            "provider": provider,
            "status_code": status,
            "error": "Provider returned non-JSON response",
            "details": str(exc),
            "endpoint": endpoint,
            "body_preview": text[:1000],
        }


# =====================================================
# PYTHON-БЛОК: _get_env
# Выполняет отдельный шаг backend-логики SYLVEX.
# Связан с API, базой данных, провайдерами или подготовкой данных для Mini App.
# =====================================================
def _get_env(*names: str) -> str:
    for name in names:
        value = os.getenv(name)
        if value:
            return value
    return ""


# =====================================================
# ОБРАБОТКА ОШИБОК: _audio_error
# Преобразует техническую ошибку провайдера в понятное сообщение для пользователя и сохраняет диагностические данные для логов.
# =====================================================
def _audio_error(provider: str, frontend_model: str, provider_model: str = "", error: Any = "", **extra) -> dict:
    user_message = translate_provider_error(error, provider=provider, model=frontend_model)
    result = {
        "ok": False,
        "type": "music",
        "provider": provider,
        "model": frontend_model,
        "provider_model": provider_model,
        "error": user_message,
        "message": user_message,
        "raw_error": raw_error_text(error, ""),
    }
    result.update(extra)
    return result


# =====================================================
# PYTHON-БЛОК: _audio_headers
# Выполняет отдельный шаг backend-логики SYLVEX.
# Связан с API, базой данных, провайдерами или подготовкой данных для Mini App.
# =====================================================
def _audio_headers(api_key: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


# =====================================================
# PYTHON-БЛОК: _first_value
# Выполняет отдельный шаг backend-логики SYLVEX.
# Связан с API, базой данных, провайдерами или подготовкой данных для Mini App.
# =====================================================
def _first_value(data: Any, keys: tuple[str, ...]):
    queue = [data]
    while queue:
        item = queue.pop(0)
        if isinstance(item, dict):
            for key in keys:
                value = item.get(key)
                if value not in (None, ""):
                    return value
            queue.extend(item.values())
        elif isinstance(item, list):
            queue.extend(item)
    return None


# =====================================================
# PYTHON-БЛОК: _work_id_from_response
# Выполняет отдельный шаг backend-логики SYLVEX.
# Связан с API, базой данных, провайдерами или подготовкой данных для Mini App.
# =====================================================
def _work_id_from_response(data: Any) -> str:
    value = _first_value(data, ("task_id", "workId", "work_id", "taskId", "id"))
    return str(value) if value else ""


# =====================================================
# PYTHON-БЛОК: _status_from_response
# Выполняет отдельный шаг backend-логики SYLVEX.
# Связан с API, базой данных, провайдерами или подготовкой данных для Mini App.
# =====================================================
def _status_from_response(data: Any) -> str:
    value = _first_value(data, ("type", "status", "state", "task_status", "work_status"))
    return str(value or "").lower()


# =====================================================
# PYTHON-БЛОК: _response_items
# Выполняет отдельный шаг backend-логики SYLVEX.
# Связан с API, базой данных, провайдерами или подготовкой данных для Mini App.
# =====================================================
def _response_items(data: Any) -> list[dict]:
    if not isinstance(data, dict):
        return []
    nested_data = data.get("data")
    if isinstance(nested_data, dict):
        nested_items = _response_items(nested_data)
        if nested_items:
            return nested_items
    response_data = data.get("response_data")
    if isinstance(response_data, list):
        return [item for item in response_data if isinstance(item, dict)]
    if isinstance(response_data, dict):
        nested = response_data.get("response_data") or response_data.get("data") or response_data.get("items")
        if isinstance(nested, list):
            return [item for item in nested if isinstance(item, dict)]
        return [response_data]
    for key in ("data", "items", "results", "result"):
        value = data.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
        if isinstance(value, dict):
            return [value]
    return []


# =====================================================
# PYTHON-БЛОК: _extract_audio_result
# Выполняет отдельный шаг backend-логики SYLVEX.
# Связан с API, базой данных, провайдерами или подготовкой данных для Mini App.
# =====================================================
def _extract_audio_result(data: Any) -> dict[str, Any]:
    items = _response_items(data)
    first = items[0] if items else {}
    audio_url = (
        first.get("audio_url")
        or first.get("audioUrl")
        or first.get("source_audio_url")
        or first.get("url")
        or _first_value(data, ("audio_url", "audioUrl", "music_url", "result_url"))
        or ""
    )
    image_url = (
        first.get("image_url")
        or first.get("imageUrl")
        or first.get("cover_url")
        or first.get("coverUrl")
        or _first_value(data, ("image_url", "imageUrl", "cover_url", "coverUrl"))
        or ""
    )
    title = first.get("title") or _first_value(data, ("title", "name")) or ""
    duration = first.get("duration") or _first_value(data, ("duration", "duration_sec", "duration_seconds")) or ""
    model_name = first.get("model_name") or first.get("modelName") or _first_value(data, ("model_name", "modelName")) or ""
    return {
        "audio_url": str(audio_url or ""),
        "image_url": str(image_url or ""),
        "title": str(title or ""),
        "duration": duration,
        "model_name": str(model_name or ""),
        "items": items,
    }


# =====================================================
# PYTHON-БЛОК: _music_model_mapping
# Выполняет отдельный шаг backend-логики SYLVEX.
# Связан с API, базой данных, провайдерами или подготовкой данных для Mini App.
# =====================================================
def _music_model_mapping(frontend_model: str) -> str:
    value = (frontend_model or "").strip()
    return SUNO_MUSIC_MODEL_MAP.get(value) or SUNO_MUSIC_MODEL_MAP.get(value.lower()) or ""


# =====================================================
# ЗАПРОС К AI-ПРОВАЙДЕРУ: _gemini_tts_model_mapping
# Сопоставляет название модели из Mini App с официальным ID Gemini TTS.
# =====================================================
def _gemini_tts_model_mapping(frontend_model: str) -> str:
    value = (frontend_model or "").strip()
    return GEMINI_TTS_MODEL_MAP.get(value) or GEMINI_TTS_MODEL_MAP.get(value.lower()) or ""


# =====================================================
# ЗАГРУЗКА ФАЙЛОВ: _save_gemini_tts_wav
# Сохраняет PCM-аудио Gemini TTS в WAV-файл, который Mini App и Telegram могут открыть по URL.
# =====================================================
def _save_gemini_tts_wav(pcm: bytes) -> str:
    if not pcm:
        return ""
    GENERATED_AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"{uuid4().hex}.wav"
    path = GENERATED_AUDIO_DIR / filename
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(24000)
        wf.writeframes(pcm)
    return f"/webapp/generated/audio/{filename}"


# =====================================================
# ЗАПРОС К AI-ПРОВАЙДЕРУ: _extract_gemini_output_audio
# Достаёт base64-аудио из ответа Interactions API независимо от вложенности полей.
# =====================================================
def _extract_gemini_output_audio(data: Any) -> str:
    if not isinstance(data, dict):
        return ""
    mime_type = str(data.get("mime_type") or data.get("mimeType") or data.get("type") or "").lower()
    inline_data = data.get("data")
    if inline_data and "audio" in mime_type:
        return str(inline_data or "")
    output_audio = data.get("output_audio")
    if isinstance(output_audio, dict) and output_audio.get("data"):
        return str(output_audio.get("data") or "")
    for key in ("audio", "outputAudio"):
        value = data.get(key)
        if isinstance(value, dict) and value.get("data"):
            return str(value.get("data") or "")
    for value in data.values():
        if isinstance(value, dict):
            nested = _extract_gemini_output_audio(value)
            if nested:
                return nested
        elif isinstance(value, list):
            for item in value:
                nested = _extract_gemini_output_audio(item)
                if nested:
                    return nested
    return ""


# =====================================================
# ЗАПРОС К AI-ПРОВАЙДЕРУ: _gemini_tts_payload
# Собирает официальный payload Gemini Interactions API для single-speaker или multi-speaker TTS.
# =====================================================
def _gemini_tts_payload(payload: dict, provider_model: str) -> dict:
    voice_options = payload.get("voice_options") or {}
    prompt = (payload.get("prompt") or voice_options.get("prompt") or "").strip()
    voice = voice_options.get("voice") or voice_options.get("voice_name") or "Kore"
    speaker_mode = str(voice_options.get("speaker_mode") or voice_options.get("speakerMode") or "single").lower()
    effective_mode = "single"
    if speaker_mode in {"multi", "multispeaker", "multi_speaker"}:
        speaker1 = voice_options.get("speaker1") or "Speaker1"
        speaker2 = voice_options.get("speaker2") or "Speaker2"
        has_speaker1 = f"{speaker1}:" in prompt
        has_speaker2 = f"{speaker2}:" in prompt
        if has_speaker1 and has_speaker2:
            effective_mode = "multi"
            speech_config = [
                {"speaker": speaker1, "voice": voice},
                {"speaker": speaker2, "voice": voice_options.get("second_voice") or voice_options.get("secondVoice") or "Puck"},
            ]
        else:
            speech_config = [{"voice": voice}]
    else:
        speech_config = [{"voice": voice}]
    return {
        "model": provider_model,
        "input": prompt,
        "response_format": {"type": "audio"},
        "generation_config": {"speech_config": speech_config},
        "_debug_effective_speaker_mode": effective_mode,
    }


# =====================================================
# PYTHON-БЛОК: _music_option_value
# Выполняет отдельный шаг backend-логики SYLVEX.
# Связан с API, базой данных, провайдерами или подготовкой данных для Mini App.
# =====================================================
def _music_option_value(music_options: dict, key: str) -> str:
    value = music_options.get(key)
    if value is None:
        settings = music_options.get("settings") or {}
        value = settings.get(key)
    return str(value or "").strip()


# =====================================================
# PYTHON-БЛОК: _style_from_music_options
# Выполняет отдельный шаг backend-логики SYLVEX.
# Связан с API, базой данных, провайдерами или подготовкой данных для Mini App.
# =====================================================
def _style_from_music_options(music_options: dict) -> str:
    values = []
    for key in ("genre", "mood", "tempo", "theme"):
        value = _music_option_value(music_options, key)
        if value and value.lower() != "auto":
            values.append(value.replace("_", " "))
    return ", ".join(values)


# =====================================================
# PYTHON-БЛОК: _audio_payload
# Выполняет отдельный шаг backend-логики SYLVEX.
# Связан с API, базой данных, провайдерами или подготовкой данных для Mini App.
# =====================================================
def _audio_payload(payload: dict, provider_model: str) -> dict[str, Any]:
    music_options = payload.get("music_options") or {}
    prompt = (payload.get("prompt") or music_options.get("prompt") or "").strip()
    mode = str(music_options.get("mode") or music_options.get("generation_mode") or "inspiration").strip().lower()
    title = str(music_options.get("title") or payload.get("title") or "").strip()
    vocal = _music_option_value(music_options, "vocal").lower()
    make_instrumental = vocal == "instrumental"

    custom_payload = os.getenv("AUDIO_API_GENERATE_PAYLOAD_JSON")
    if custom_payload:
        try:
            override = json.loads(custom_payload)
            if isinstance(override, dict):
                override.setdefault("prompt", prompt)
                override.setdefault("model", provider_model)
                return override
        except Exception:
            pass

    if mode == "custom":
        body = {
            "model": provider_model,
            "prompt": prompt,
            "style": _style_from_music_options(music_options),
            "make_instrumental": make_instrumental,
        }
        if title:
            body["title"] = title
        if vocal == "female":
            body["gender"] = "female"
        elif vocal == "male":
            body["gender"] = "male"
        return body

    body = {
        "model": provider_model,
        "gpt_description_prompt": prompt,
        "make_instrumental": make_instrumental,
    }
    if title:
        body["title"] = title
    return body


# =====================================================
# СИНХРОНИЗАЦИЯ С TELEGRAM: _send_generated_audio_to_telegram
# Отправляет готовый результат или статус в Telegram Bot и сохраняет признак отправки в metadata карточки.
# =====================================================
async def _send_generated_audio_to_telegram(
    telegram_id: int,
    audio_url: str,
    caption: str = "",
    image_url: str = "",
) -> bool:
    bot_token = _get_env("BOT_TOKEN", "TELEGRAM_BOT_TOKEN")
    if not bot_token or not telegram_id or not audio_url:
        print("TELEGRAM AUDIO SEND:", {
            "telegram_id": telegram_id,
            "has_audio_url": bool(audio_url),
            "error": "bot token, telegram_id or audio_url missing",
        })
        return False

    async with httpx.AsyncClient(timeout=180.0) as client:
        try:
            if str(audio_url).startswith("/webapp/"):
                local_path = WEBAPP_DIR / str(audio_url).replace("/webapp/", "", 1)
                audio_content = local_path.read_bytes() if local_path.exists() else b""
                content_type = "audio/wav" if local_path.suffix.lower() == ".wav" else "audio/mpeg"
            else:
                audio_response = await client.get(audio_url)
                if audio_response.status_code >= 400 or not audio_response.content:
                    print("TELEGRAM AUDIO SEND:", {
                        "telegram_id": telegram_id,
                        "has_audio_url": True,
                        "error": f"download failed: {audio_response.status_code}",
                    })
                    return False
                audio_content = audio_response.content
                content_type = audio_response.headers.get("content-type") or "audio/mpeg"
            if not audio_content:
                return False
            filename = "sylvex-audio.mp3"
            if "wav" in content_type:
                filename = "sylvex-audio.wav"
            elif "ogg" in content_type:
                filename = "sylvex-audio.ogg"

            data = {
                "chat_id": str(telegram_id),
                "caption": caption,
                "title": "SYLVEX Pro Studio",
            }
            files = {"audio": (filename, audio_content, content_type)}
            tg_response = await client.post(
                f"https://api.telegram.org/bot{bot_token}/sendAudio",
                data=data,
                files=files,
            )
            if tg_response.status_code < 400:
                print("TELEGRAM AUDIO SEND:", {
                    "telegram_id": telegram_id,
                    "has_audio_url": True,
                    "ok": True,
                })
                return True

            print("TELEGRAM AUDIO SEND:", {
                "telegram_id": telegram_id,
                "has_audio_url": True,
                "error": tg_response.text[:500],
            })
            return False
        except Exception as exc:
            print("TELEGRAM AUDIO SEND:", {
                "telegram_id": telegram_id,
                "has_audio_url": True,
                "error": repr(exc),
            })
            return False


# =====================================================
# PYTHON-БЛОК: audio_generation
# Выполняет отдельный шаг backend-логики SYLVEX.
# Связан с API, базой данных, провайдерами или подготовкой данных для Mini App.
# =====================================================
async def audio_generation(payload: dict) -> dict:
    mode = str(payload.get("mode") or payload.get("category") or "").lower()
    if mode == "voice":
        return await voice_generation(payload)

    api_key = _get_env("AUDIO_API_KEY")
    provider = "suno"
    frontend_model = (
        payload.get("model")
        or (payload.get("music_options") or {}).get("model")
        or "suno_chirp_5"
    )
    provider_model = _music_model_mapping(frontend_model)
    prompt_report = optimize_prompt_for_model(
        payload.get("prompt") or (payload.get("music_options") or {}).get("prompt") or "",
        model=frontend_model,
        provider=provider,
        mode="music",
    )
    print("AUDIO PROMPT OPTIMIZER:", {
        "model": frontend_model,
        "provider": provider,
        "prompt_length": prompt_report.get("original_length"),
        "model_limit": prompt_report.get("limit"),
        "optimized": prompt_report.get("optimized"),
        "new_length": prompt_report.get("optimized_length"),
        "failed_reason": prompt_report.get("failed_reason") or "",
    })
    if (payload.get("prompt") or (payload.get("music_options") or {}).get("prompt")) and not prompt_report.get("ok"):
        return _audio_error(
            provider,
            frontend_model,
            provider_model,
            "Prompt optimization failed to reach limit",
            prompt_limit=prompt_report.get("limit"),
            prompt_length=prompt_report.get("original_length"),
            optimized_length=prompt_report.get("optimized_length"),
        )
    if prompt_report.get("optimized"):
        payload["prompt"] = prompt_report.get("prompt") or payload.get("prompt") or ""
        payload["prompt_optimization"] = prompt_report
    if not provider_model:
        return _audio_error(provider, frontend_model, "", "Unknown provider model mapping", frontend_model=frontend_model)

    if not api_key:
        return _audio_error(provider, frontend_model, provider_model, "AUDIO_API_KEY is not configured")

    submit_body = _audio_payload(payload, provider_model)
    print("AUDIO API GENERATE REQUEST:", {
        "endpoint": AUDIO_GENERATE_ENDPOINT,
        "frontend_model": frontend_model,
        "provider_model": provider_model,
        "model": submit_body.get("model"),
        "has_prompt": bool(submit_body.get("prompt")),
        "has_gpt_description_prompt": bool(submit_body.get("gpt_description_prompt")),
        "make_instrumental": submit_body.get("make_instrumental"),
    })

    async with httpx.AsyncClient(timeout=180.0) as client:
        try:
            submit_response = await client.post(
                AUDIO_GENERATE_ENDPOINT,
                headers=_audio_headers(api_key),
                json=submit_body,
            )
        except Exception as exc:
            return _audio_error(provider, frontend_model, provider_model, exc, endpoint=AUDIO_GENERATE_ENDPOINT, details=repr(exc))

        submit_data = await safe_audio_json_response(submit_response, provider, AUDIO_GENERATE_ENDPOINT)
        work_id = _work_id_from_response(submit_data)
        submit_status = _status_from_response(submit_data)
        print("AUDIO API SUBMIT RESPONSE:", {
            "status_code": submit_response.status_code,
            "workId": work_id,
            "status": submit_status,
        })

        if submit_response.status_code >= 400:
            return _audio_error(provider, frontend_model, provider_model, submit_data, endpoint=AUDIO_GENERATE_ENDPOINT, status_code=submit_response.status_code, body_preview=json.dumps(submit_data, ensure_ascii=False)[:1000], response=submit_data)

        result = _extract_audio_result(submit_data)
        if result["audio_url"]:
            return await _completed_audio_response(payload, provider, frontend_model, provider_model, work_id, submit_status, result, submit_data)

        if not work_id:
            return _audio_error(provider, frontend_model, provider_model, "Audio API did not return workId", endpoint=AUDIO_GENERATE_ENDPOINT, status_code=submit_response.status_code, response=submit_data)

        attempts = int(os.getenv("AUDIO_API_POLL_ATTEMPTS", "60"))
        interval = float(os.getenv("AUDIO_API_POLL_INTERVAL", "5"))
        last_data = submit_data
        feed_url = AUDIO_FEED_ENDPOINT

        for attempt in range(1, attempts + 1):
            try:
                poll_response = await client.get(
                    feed_url,
                    headers=_audio_headers(api_key),
                    params={"workId": work_id},
                )
                poll_data = await safe_audio_json_response(poll_response, provider, feed_url)
            except Exception as exc:
                poll_data = {
                    "ok": False,
                    "error": "Audio API polling request failed",
                    "details": repr(exc),
                }
                poll_response = None

            last_data = poll_data
            poll_status_code = getattr(poll_response, "status_code", None)
            if poll_status_code and poll_status_code >= 400:
                return _audio_error(provider, frontend_model, provider_model, poll_data, workId=work_id, task_id=work_id, endpoint=feed_url, status_code=poll_status_code, body_preview=json.dumps(poll_data, ensure_ascii=False)[:1000], response=poll_data)

            status = _status_from_response(poll_data)
            result = _extract_audio_result(poll_data)
            print("AUDIO API POLL:", {
                "attempt": attempt,
                "workId": work_id,
                "status": status,
                "has_audio_url": bool(result["audio_url"]),
                "audio_url": result["audio_url"],
                "has_image_url": bool(result["image_url"]),
            })

            if status in {"complete", "completed", "succeeded", "success", "done"} and result["audio_url"]:
                return await _completed_audio_response(payload, provider, frontend_model, provider_model, work_id, status, result, poll_data)

            if status in {"failed", "error", "cancelled", "canceled"}:
                return _audio_error(provider, frontend_model, provider_model, poll_data, workId=work_id, status=status, endpoint=feed_url, status_code=getattr(poll_response, "status_code", None), response=poll_data)

            if attempt < attempts:
                await asyncio.sleep(interval)

        return {
            "ok": True,
            "type": "music",
            "provider": provider,
            "model": frontend_model,
            "provider_model": provider_model,
            "status": "processing",
            "workId": work_id,
            "task_id": work_id,
            "poll_url": f"{AUDIO_FEED_ENDPOINT}?workId={work_id}",
            "response": last_data,
        }


# =====================================================
# ЗАПРОС К AI-ПРОВАЙДЕРУ: voice_generation
# Подключает раздел «Озвучка» Mini App к Gemini TTS Interactions API.
# Получает текст пользователя, выбранную модель и голос, возвращает готовый audio_url.
# =====================================================
async def voice_generation(payload: dict) -> dict:
    provider = "gemini"
    voice_options = payload.get("voice_options") or {}
    frontend_model = (
        payload.get("model")
        or voice_options.get("model")
        or "gemini_3_1_flash_tts_preview"
    )
    provider_model = _gemini_tts_model_mapping(frontend_model)
    api_key = _get_env("GEMINI_API_KEY", "GOOGLE_API_KEY", "GOOGLE-GEMINI-API-KEY")
    prompt_report = optimize_prompt_for_model(
        payload.get("prompt") or voice_options.get("prompt") or "",
        model=frontend_model,
        provider=provider,
        mode="voice",
    )
    print("GEMINI TTS PROMPT OPTIMIZER:", {
        "model": frontend_model,
        "provider_model": provider_model,
        "prompt_length": prompt_report.get("original_length"),
        "model_limit": prompt_report.get("limit"),
        "optimized": prompt_report.get("optimized"),
        "new_length": prompt_report.get("optimized_length"),
    })
    if (payload.get("prompt") or voice_options.get("prompt")) and not prompt_report.get("ok"):
        return _audio_error(provider, frontend_model, provider_model, "Prompt optimization failed to reach limit")
    if prompt_report.get("optimized"):
        payload["prompt"] = prompt_report.get("prompt") or payload.get("prompt") or ""
        payload["prompt_optimization"] = prompt_report

    if not provider_model:
        return _audio_error(provider, frontend_model, "", "Unknown Gemini TTS model mapping", frontend_model=frontend_model)
    if not api_key:
        return _audio_error(provider, frontend_model, provider_model, "GEMINI_API_KEY is not configured")
    if not (payload.get("prompt") or "").strip():
        return _audio_error(provider, frontend_model, provider_model, "Voice prompt is empty")

    request_body = _gemini_tts_payload(payload, provider_model)
    effective_speaker_mode = request_body.pop("_debug_effective_speaker_mode", "single")
    headers = {
        "x-goog-api-key": api_key,
        "Content-Type": "application/json",
    }
    print("GEMINI TTS REQUEST:", {
        "endpoint": GEMINI_TTS_ENDPOINT,
        "frontend_model": frontend_model,
        "provider_model": provider_model,
        "voice": (voice_options.get("voice") or voice_options.get("voice_name") or "Kore"),
        "speaker_mode": voice_options.get("speaker_mode") or voice_options.get("speakerMode") or "single",
        "effective_speaker_mode": effective_speaker_mode,
        "has_prompt": bool(request_body.get("input")),
    })
    async with httpx.AsyncClient(timeout=180.0) as client:
        try:
            response = await client.post(GEMINI_TTS_ENDPOINT, headers=headers, json=request_body)
        except Exception as exc:
            return _audio_error(provider, frontend_model, provider_model, exc, endpoint=GEMINI_TTS_ENDPOINT, details=repr(exc))
    data = await safe_audio_json_response(response, provider, GEMINI_TTS_ENDPOINT)
    print("GEMINI TTS RESPONSE:", {
        "status_code": response.status_code,
        "has_output_audio": bool(_extract_gemini_output_audio(data)),
        "body_preview": json.dumps(data, ensure_ascii=False)[:1200] if isinstance(data, (dict, list)) else str(data)[:1200],
    })
    if response.status_code >= 400:
        return _audio_error(provider, frontend_model, provider_model, data, endpoint=GEMINI_TTS_ENDPOINT, status_code=response.status_code, response=data)

    audio_data = _extract_gemini_output_audio(data)
    if not audio_data:
        return _audio_error(provider, frontend_model, provider_model, "Gemini TTS returned no output_audio", endpoint=GEMINI_TTS_ENDPOINT, response=data)
    try:
        audio_bytes = base64.b64decode(audio_data)
    except Exception as exc:
        return _audio_error(provider, frontend_model, provider_model, f"Gemini TTS audio decode failed: {exc}", response=data)
    audio_url = _save_gemini_tts_wav(audio_bytes)
    if not audio_url:
        return _audio_error(provider, frontend_model, provider_model, "Gemini TTS audio save failed", response=data)

    telegram_id = int(payload.get("telegram_id") or 0)
    sent_to_telegram = await _send_generated_audio_to_telegram(
        telegram_id=telegram_id,
        audio_url=audio_url,
        caption="SYLVEX Pro Studio\nОзвучка готова ✅",
    )
    return {
        "ok": True,
        "type": "voice",
        "provider": provider,
        "model": frontend_model,
        "provider_model": provider_model,
        "status": "completed",
        "audio_url": audio_url,
        "audios": [audio_url],
        "voice": voice_options.get("voice") or voice_options.get("voice_name") or "Kore",
        "voice_options": voice_options,
        "response": data,
        "sent_to_telegram": sent_to_telegram,
        "text": "Озвучка готова ✅\n" + audio_url,
    }


# =====================================================
# PYTHON-БЛОК: _completed_audio_response
# Выполняет отдельный шаг backend-логики SYLVEX.
# Связан с API, базой данных, провайдерами или подготовкой данных для Mini App.
# =====================================================
async def _completed_audio_response(
    payload: dict,
    provider: str,
    frontend_model: str,
    provider_model: str,
    work_id: str,
    status: str,
    result: dict,
    full_response: Any,
) -> dict:
    audio_url = result.get("audio_url") or ""
    image_url = result.get("image_url") or ""
    title = result.get("title") or ""
    duration = result.get("duration") or ""
    model_name = result.get("model_name") or ""
    telegram_id = int(payload.get("telegram_id") or 0)
    caption = (
        "SYLVEX Pro Studio\n"
        "Музыка готова ✅"
    )
    sent_to_telegram = await _send_generated_audio_to_telegram(
        telegram_id=telegram_id,
        audio_url=audio_url,
        image_url=image_url,
        caption=caption,
    )
    return {
        "ok": True,
        "type": "music",
        "provider": provider,
        "model": frontend_model,
        "provider_model": provider_model,
        "status": status or "complete",
        "workId": work_id,
        "task_id": work_id,
        "audio_url": audio_url,
        "audios": [audio_url] if audio_url else [],
        "image_url": image_url,
        "images": [image_url] if image_url else [],
        "title": title,
        "duration": duration,
        "model_name": model_name,
        "response_data": result.get("items") or [],
        "response": full_response,
        "sent_to_telegram": sent_to_telegram,
        "text": "Музыка готова ✅\n" + audio_url if audio_url else "Музыка готова ✅",
    }
