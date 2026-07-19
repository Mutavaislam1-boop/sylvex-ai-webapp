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
import mimetypes
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
RUNWAY_API_BASE_URL = os.getenv("RUNWAY_API_BASE_URL", "https://api.dev.runwayml.com").rstrip("/")
RUNWAY_API_VERSION = os.getenv("RUNWAY_API_VERSION", "2024-11-06")
ELEVENLABS_BASE_URL = os.getenv("ELEVENLABS_BASE_URL", "https://api.elevenlabs.io").rstrip("/")
ELEVENLABS_DEFAULT_VOICE_ID = os.getenv("ELEVENLABS_DEFAULT_VOICE_ID", "21m00Tcm4TlvDq8ikWAM")
ELEVENLABS_DEFAULT_VOICE_NAME = os.getenv("ELEVENLABS_DEFAULT_VOICE_NAME", "Rachel")
ELEVENLABS_DEFAULT_OUTPUT_FORMAT = os.getenv("ELEVENLABS_DEFAULT_OUTPUT_FORMAT", "mp3_44100_128")

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

ELEVENLABS_VOICE_MODEL_MAP = {
    "elevenlabs_eleven_v3": "eleven_v3",
    "elevenlabs_multilingual_v2": "eleven_multilingual_v2",
    "elevenlabs_flash_v2_5": "eleven_flash_v2_5",
    "elevenlabs_flash_v2": "eleven_flash_v2",
    "eleven_v3": "eleven_v3",
    "eleven_multilingual_v2": "eleven_multilingual_v2",
    "eleven_flash_v2_5": "eleven_flash_v2_5",
    "eleven_flash_v2": "eleven_flash_v2",
}

ELEVENLABS_AUDIO_TOOLS = {
    "text_to_speech": "text_to_speech",
    "speech_to_speech": "speech_to_speech",
    "dialogue": "dialogue",
}

ELEVENLABS_VOICE_FALLBACKS = [
    {
        "voice_id": ELEVENLABS_DEFAULT_VOICE_ID,
        "name": ELEVENLABS_DEFAULT_VOICE_NAME,
        "provider": "elevenlabs",
        "type": "premade",
        "preview_url": "",
    }
]

RUNWAY_VOICE_MODEL_MAP = {
    "runway_eleven_multilingual_v2": "eleven_multilingual_v2",
    "eleven_multilingual_v2": "eleven_multilingual_v2",
}

RUNWAY_AUDIO_TOOLS = {
    "text_to_speech": {
        "model": "eleven_multilingual_v2",
        "endpoint": "/v1/text_to_speech",
    },
    "sound_effect": {
        "model": "eleven_text_to_sound_v2",
        "endpoint": "/v1/sound_effect",
    },
    "speech_to_speech": {
        "model": "eleven_multilingual_sts_v2",
        "endpoint": "/v1/speech_to_speech",
    },
    "voice_dubbing": {
        "model": "eleven_voice_dubbing",
        "endpoint": "/v1/voice_dubbing",
    },
    "voice_isolation": {
        "model": "eleven_voice_isolation",
        "endpoint": "/v1/voice_isolation",
    },
}

RUNWAY_VOICE_FALLBACKS = [
    {"voice_id": "Maya", "name": "Maya", "provider": "runway", "type": "runway-preset"},
    {"voice_id": "Noah", "name": "Noah", "provider": "runway", "type": "runway-preset"},
    {"voice_id": "Bernard", "name": "Bernard", "provider": "runway", "type": "runway-preset"},
    {"voice_id": "Arjun", "name": "Arjun", "provider": "runway", "type": "runway-preset"},
]

GEMINI_TTS_VOICE_NAMES = {
    "Zephyr", "Puck", "Charon", "Kore", "Fenrir", "Leda",
    "Orus", "Aoede", "Callirrhoe", "Autonoe", "Enceladus", "Iapetus",
    "Umbriel", "Algieba", "Despina", "Erinome", "Algenib", "Rasalgethi",
    "Laomedeia", "Achernar", "Alnilam", "Schedar", "Gacrux", "Pulcherrima",
    "Achird", "Zubenelgenubi", "Vindemiatrix", "Sadachbia", "Sadaltager", "Sulafat",
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
# ЗАПРОС К AI-ПРОВАЙДЕРУ: _runway_headers
# Готовит заголовки официального Runway API для генерации озвучки и списка голосов.
# =====================================================
def _runway_headers(api_key: str) -> dict[str, str]:
    headers = _audio_headers(api_key)
    headers["X-Runway-Version"] = RUNWAY_API_VERSION
    return headers


# =====================================================
# ЗАПРОС К AI-ПРОВАЙДЕРУ: _elevenlabs_headers
# Готовит заголовки официального ElevenLabs API для TTS, STS, Dialogue и списка голосов.
# =====================================================
def _elevenlabs_headers(content_type: str = "application/json") -> dict[str, str]:
    headers = {
        "xi-api-key": _get_env("ELEVENLABS_API_KEY", "ELEVENLABS-API-KEY"),
        "Accept": "application/json",
    }
    if content_type:
        headers["Content-Type"] = content_type
    return headers


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
# ЗАПРОС К AI-ПРОВАЙДЕРУ: _elevenlabs_voice_model_mapping
# Сопоставляет модель озвучки ElevenLabs из Mini App с официальным model_id ElevenLabs.
# =====================================================
def _elevenlabs_voice_model_mapping(frontend_model: str) -> str:
    value = (frontend_model or "").strip()
    return ELEVENLABS_VOICE_MODEL_MAP.get(value) or ELEVENLABS_VOICE_MODEL_MAP.get(value.lower()) or ""


# =====================================================
# ЗАПРОС К AI-ПРОВАЙДЕРУ: _is_elevenlabs_voice_model
# Проверяет, должна ли выбранная модель озвучки идти через ElevenLabs.
# =====================================================
def _is_elevenlabs_voice_model(frontend_model: str) -> bool:
    return bool(_elevenlabs_voice_model_mapping(frontend_model))


# =====================================================
# ЗАПРОС К AI-ПРОВАЙДЕРУ: _elevenlabs_audio_tool
# Определяет выбранный инструмент ElevenLabs и возвращает безопасное значение по умолчанию.
# =====================================================
def _elevenlabs_audio_tool(payload: dict) -> str:
    voice_options = payload.get("voice_options") or {}
    tool = str(voice_options.get("elevenlabs_tool") or voice_options.get("elevenlabsTool") or "text_to_speech").strip().lower()
    return tool if tool in ELEVENLABS_AUDIO_TOOLS else "text_to_speech"


# =====================================================
# ЗАПРОС К AI-ПРОВАЙДЕРУ: _runway_voice_model_mapping
# Сопоставляет модель озвучки Runway из Mini App с официальным ID Runway API.
# =====================================================
def _runway_voice_model_mapping(frontend_model: str) -> str:
    value = (frontend_model or "").strip()
    return RUNWAY_VOICE_MODEL_MAP.get(value) or RUNWAY_VOICE_MODEL_MAP.get(value.lower()) or ""


# =====================================================
# ЗАПРОС К AI-ПРОВАЙДЕРУ: _runway_audio_tool
# Определяет выбранный инструмент Runway Audio и возвращает безопасное значение по умолчанию.
# =====================================================
def _runway_audio_tool(payload: dict) -> str:
    voice_options = payload.get("voice_options") or {}
    tool = _runway_audio_tool(payload)
    tool = str(voice_options.get("runway_tool") or voice_options.get("runwayTool") or "text_to_speech").strip().lower()
    return tool if tool in RUNWAY_AUDIO_TOOLS else "text_to_speech"


# =====================================================
# ЗАПРОС К AI-ПРОВАЙДЕРУ: _is_runway_voice_model
# Проверяет, должна ли выбранная модель озвучки идти через Runway, а не через Gemini.
# =====================================================
def _is_runway_voice_model(frontend_model: str) -> bool:
    return bool(_runway_voice_model_mapping(frontend_model))


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
# ЗАГРУЗКА ФАЙЛОВ: _save_audio_file
# Сохраняет готовое аудио от Runway в локальную папку Mini App, чтобы карточка озвучки открывалась внутри приложения.
# =====================================================
def _save_audio_file(content: bytes, ext: str = ".mp3") -> str:
    if not content:
        return ""
    GENERATED_AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    safe_ext = ext if ext.startswith(".") and len(ext) <= 8 else ".mp3"
    filename = f"{uuid4().hex}{safe_ext}"
    path = GENERATED_AUDIO_DIR / filename
    path.write_bytes(content)
    return f"/webapp/generated/audio/{filename}"


# =====================================================
# ЗАГРУЗКА ФАЙЛОВ: _audio_extension_from_response
# Определяет расширение аудиофайла по URL или Content-Type ответа провайдера.
# =====================================================
def _audio_extension_from_response(url: str = "", content_type: str = "") -> str:
    guessed = mimetypes.guess_extension((content_type or "").split(";", 1)[0].strip()) if content_type else ""
    if guessed:
        return ".mp3" if guessed == ".mpga" else guessed
    suffix = pathlib.PurePosixPath(str(url or "").split("?", 1)[0]).suffix.lower()
    if suffix in {".mp3", ".wav", ".ogg", ".m4a", ".aac", ".flac"}:
        return suffix
    return ".mp3"


# =====================================================
# ЗАПРОС К AI-ПРОВАЙДЕРУ: _runway_task_id
# Извлекает task_id из ответа Runway после создания задачи.
# =====================================================
def _runway_task_id(data: Any) -> str:
    value = _first_value(data, ("id", "task_id", "taskId"))
    return str(value or "")


# =====================================================
# ЗАПРОС К AI-ПРОВАЙДЕРУ: _runway_status
# Приводит статус задачи Runway к единому виду для polling-процесса SYLVEX.
# =====================================================
def _runway_status(data: Any) -> str:
    return str(_first_value(data, ("status", "state")) or "").lower()


# =====================================================
# ЗАПРОС К AI-ПРОВАЙДЕРУ: _runway_audio_urls
# Находит ссылки на готовое аудио в ответе Runway независимо от вложенности результата.
# =====================================================
def _runway_audio_urls(data: Any) -> list[str]:
    urls: list[str] = []

    def walk(value: Any):
        if isinstance(value, dict):
            for key in ("audio_url", "audioUrl", "url", "uri", "output_url", "outputUrl", "result_url", "resultUrl"):
                item = value.get(key)
                if isinstance(item, str) and item.startswith(("http://", "https://", "/webapp/")):
                    urls.append(item)
            for key in ("output", "outputs", "result", "results", "artifacts", "data"):
                if key in value:
                    walk(value.get(key))
        elif isinstance(value, list):
            for item in value:
                walk(item)
        elif isinstance(value, str) and value.startswith(("http://", "https://", "/webapp/")):
            urls.append(value)

    walk(data)
    deduped = []
    for url in urls:
        if url not in deduped:
            deduped.append(url)
    return deduped


# =====================================================
# ЗАПРОС К AI-ПРОВАЙДЕРУ: _download_runway_audio
# Скачивает финальный audio URL от Runway и возвращает локальный URL для Mini App и Telegram.
# =====================================================
async def _download_runway_audio(client: httpx.AsyncClient, audio_url: str) -> str:
    if not audio_url:
        return ""
    if str(audio_url).startswith("/webapp/"):
        return str(audio_url)
    response = await client.get(audio_url)
    if response.status_code >= 400 or not response.content:
        return ""
    ext = _audio_extension_from_response(audio_url, response.headers.get("content-type") or "")
    return _save_audio_file(response.content, ext)


# =====================================================
# ЗАГРУЗКА ФАЙЛОВ: _load_provider_media
# Загружает локальный или удалённый audio/video файл для multipart-запросов ElevenLabs Speech-to-Speech.
# =====================================================
async def _load_provider_media(client: httpx.AsyncClient, media_url: str) -> tuple[bytes, str, str]:
    value = str(media_url or "").strip()
    if not value:
        return b"", "input-audio.mp3", "audio/mpeg"
    if value.startswith("/webapp/"):
        local_path = WEBAPP_DIR / value.replace("/webapp/", "", 1)
        if not local_path.exists():
            return b"", "input-audio.mp3", "audio/mpeg"
        content = local_path.read_bytes()
        content_type = mimetypes.guess_type(str(local_path))[0] or "audio/mpeg"
        return content, local_path.name or "input-audio.mp3", content_type
    response = await client.get(value)
    if response.status_code >= 400 or not response.content:
        return b"", "input-audio.mp3", "audio/mpeg"
    content_type = response.headers.get("content-type") or mimetypes.guess_type(value)[0] or "audio/mpeg"
    suffix = _audio_extension_from_response(value, content_type)
    return response.content, f"input-audio{suffix}", content_type


# =====================================================
# ЗАГРУЗКА ФАЙЛОВ: _absolute_public_url
# Превращает локальную ссылку Mini App в абсолютную ссылку, если задан публичный домен приложения.
# =====================================================
def _absolute_public_url(url: str) -> str:
    value = str(url or "").strip()
    if not value:
        return ""
    if value.startswith(("http://", "https://")):
        return value
    public_base = _get_env("PUBLIC_BASE_URL", "APP_BASE_URL", "WEBAPP_PUBLIC_URL", "MINIAPP_PUBLIC_URL").rstrip("/")
    if public_base and value.startswith("/"):
        return f"{public_base}{value}"
    return value


# =====================================================
# ЗАГРУЗКА ФАЙЛОВ: _runway_input_media_url
# Достаёт первый audio/video файл из voice upload state для Runway STS, dubbing и isolation.
# =====================================================
def _runway_input_media_url(payload: dict) -> str:
    voice_options = payload.get("voice_options") or {}
    candidates: list[Any] = []
    for key in ("uploads", "uploadedAudioUrls", "audio_urls", "audioUrls", "media_urls", "mediaUrls"):
        value = voice_options.get(key)
        if isinstance(value, list):
            candidates.extend(value)
        elif value:
            candidates.append(value)
    for key in ("attachment",):
        value = voice_options.get(key) or payload.get(key)
        if value:
            candidates.append(value)
    for item in candidates:
        if isinstance(item, str) and item.strip():
            return _absolute_public_url(item)
        if isinstance(item, dict):
            for key in ("url", "audio_url", "audioUrl", "video_url", "videoUrl", "file_url", "fileUrl", "result_url"):
                value = item.get(key)
                if value:
                    return _absolute_public_url(str(value))
    return ""


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
        voice_options = payload.get("voice_options") or {}
        frontend_model = payload.get("model") or voice_options.get("model") or ""
        if _is_elevenlabs_voice_model(frontend_model):
            return await elevenlabs_voice_generation(payload)
        if _is_runway_voice_model(frontend_model):
            return await runway_voice_generation(payload)
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
# ЗАПРОС К AI-ПРОВАЙДЕРУ: _elevenlabs_voice_settings
# Собирает voice_settings ElevenLabs: стабильность, похожесть, стиль, скорость и speaker boost.
# =====================================================
def _elevenlabs_voice_settings(voice_options: dict) -> dict[str, Any]:
    audio_settings = voice_options.get("audioSettings") or voice_options.get("audio_settings") or {}

    def number_value(*keys: str, fallback: float) -> float:
        for key in keys:
            value = voice_options.get(key)
            if value is None:
                value = audio_settings.get(key)
            if value in (None, "", "auto"):
                continue
            try:
                return float(value)
            except Exception:
                continue
        return fallback

    return {
        "stability": max(0, min(1, number_value("stability", fallback=0.5))),
        "similarity_boost": max(0, min(1, number_value("similarity_boost", "similarityBoost", fallback=0.75))),
        "style": max(0, min(1, number_value("style", fallback=0.0))),
        "speed": max(0.7, min(1.2, number_value("speed", fallback=1.0))),
        "use_speaker_boost": bool(voice_options.get("speaker_boost", voice_options.get("speakerBoost", True))),
    }


# =====================================================
# ЗАПРОС К AI-ПРОВАЙДЕРУ: _elevenlabs_dialogue_inputs
# Превращает текст пользователя в inputs для официального ElevenLabs Text to Dialogue API.
# =====================================================
def _elevenlabs_dialogue_inputs(prompt: str, voice_options: dict) -> list[dict[str, str]]:
    primary = str(voice_options.get("elevenlabs_voice") or voice_options.get("voice") or ELEVENLABS_DEFAULT_VOICE_ID)
    secondary = str(voice_options.get("elevenlabs_second_voice") or voice_options.get("secondVoice") or primary)
    inputs = []
    for raw_line in str(prompt or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        lower = line.lower()
        voice_id = primary
        text = line
        for prefix in ("speaker2:", "speaker 2:", "b:", "персонаж 2:", "герой 2:"):
            if lower.startswith(prefix):
                voice_id = secondary
                text = line[len(prefix):].strip()
                break
        for prefix in ("speaker1:", "speaker 1:", "a:", "персонаж 1:", "герой 1:"):
            if lower.startswith(prefix):
                voice_id = primary
                text = line[len(prefix):].strip()
                break
        if text:
            inputs.append({"text": text, "voice_id": voice_id})
    if not inputs and prompt:
        inputs.append({"text": str(prompt).strip(), "voice_id": primary})
    return inputs[:20]


# =====================================================
# ЗАПРОС К AI-ПРОВАЙДЕРУ: _completed_elevenlabs_voice_response
# Формирует единый успешный ответ ElevenLabs для Job, Mini App, истории и Telegram.
# =====================================================
async def _completed_elevenlabs_voice_response(
    payload: dict,
    frontend_model: str,
    provider_model: str,
    tool: str,
    audio_bytes: bytes,
    content_type: str,
    provider_response: Any = None,
) -> dict:
    voice_options = payload.get("voice_options") or {}
    audio_url = _save_audio_file(audio_bytes, _audio_extension_from_response("", content_type or "audio/mpeg"))
    if not audio_url:
        return _audio_error("elevenlabs", frontend_model, provider_model, "ElevenLabs audio save failed", type="voice")
    telegram_id = int(payload.get("telegram_id") or 0)
    sent_to_telegram = False
    if not payload.get("skip_telegram"):
        sent_to_telegram = await _send_generated_audio_to_telegram(
            telegram_id=telegram_id,
            audio_url=audio_url,
            caption="SYLVEX Pro Studio\nОзвучка ElevenLabs готова ✅",
        )
    return {
        "ok": True,
        "type": "voice",
        "provider": "elevenlabs",
        "model": frontend_model,
        "provider_model": provider_model,
        "status": "completed",
        "elevenlabs_tool": tool,
        "audio_url": audio_url,
        "audios": [audio_url],
        "voice": voice_options.get("elevenlabs_voice") or voice_options.get("voice") or ELEVENLABS_DEFAULT_VOICE_ID,
        "voice_options": voice_options,
        "response": provider_response or {"content_type": content_type, "bytes": len(audio_bytes or b"")},
        "sent_to_telegram": sent_to_telegram,
        "text": "Озвучка готова ✅\n" + audio_url,
    }


# =====================================================
# ЗАПРОС К AI-ПРОВАЙДЕРУ: fetch_elevenlabs_prostudio_voices
# Загружает список голосов ElevenLabs для шторки Pro Studio; при ошибке возвращает Rachel fallback.
# =====================================================
async def fetch_elevenlabs_prostudio_voices(limit: int = 80) -> dict:
    api_key = _get_env("ELEVENLABS_API_KEY", "ELEVENLABS-API-KEY")
    if not api_key:
        return {"ok": True, "success": True, "provider": "elevenlabs", "voices": ELEVENLABS_VOICE_FALLBACKS, "fallback": True}
    voices = []
    next_page_token = ""
    async with httpx.AsyncClient(timeout=60.0) as client:
        while len(voices) < limit:
            params = {"page_size": min(100, limit - len(voices))}
            if next_page_token:
                params["next_page_token"] = next_page_token
            try:
                response = await client.get(f"{ELEVENLABS_BASE_URL}/v2/voices", headers=_elevenlabs_headers(None), params=params)
                data = await safe_audio_json_response(response, "elevenlabs", f"{ELEVENLABS_BASE_URL}/v2/voices")
            except Exception as exc:
                print("ELEVENLABS VOICES FAILED:", repr(exc))
                return {"ok": True, "success": True, "provider": "elevenlabs", "voices": ELEVENLABS_VOICE_FALLBACKS, "fallback": True}
            if response.status_code >= 400:
                print("ELEVENLABS VOICES ERROR:", json.dumps(data, ensure_ascii=False)[:900] if isinstance(data, (dict, list)) else str(data)[:900])
                return {"ok": True, "success": True, "provider": "elevenlabs", "voices": ELEVENLABS_VOICE_FALLBACKS, "fallback": True}
            page_voices = data.get("voices") if isinstance(data, dict) else []
            if isinstance(page_voices, list):
                voices.extend(page_voices)
            next_page_token = data.get("next_page_token") or data.get("next_cursor") if isinstance(data, dict) else ""
            if not next_page_token:
                break
    normalized = []
    seen = set()
    for item in voices[:limit]:
        if not isinstance(item, dict):
            continue
        voice_id = item.get("voice_id") or item.get("voiceId") or item.get("id")
        if not voice_id or voice_id in seen:
            continue
        seen.add(voice_id)
        labels = item.get("labels") or {}
        normalized.append({
            "voice_id": str(voice_id),
            "name": str(item.get("name") or "Voice"),
            "provider": "elevenlabs",
            "type": str(item.get("category") or labels.get("category") or "voice"),
            "language": str(labels.get("language") or labels.get("accent") or item.get("language") or "multilingual"),
            "preview_url": str(item.get("preview_url") or item.get("sample_url") or ""),
            "raw": item,
        })
    if not normalized:
        normalized = ELEVENLABS_VOICE_FALLBACKS
    return {"ok": True, "success": True, "provider": "elevenlabs", "voices": normalized}


# =====================================================
# ЗАПРОС К AI-ПРОВАЙДЕРУ: elevenlabs_voice_generation
# Подключает Pro Studio «Озвучка» к официальным ElevenLabs TTS, STS и Dialogue API.
# =====================================================
async def elevenlabs_voice_generation(payload: dict) -> dict:
    provider = "elevenlabs"
    voice_options = payload.get("voice_options") or {}
    tool = _elevenlabs_audio_tool(payload)
    frontend_model = payload.get("model") or voice_options.get("model") or "elevenlabs_multilingual_v2"
    provider_model = _elevenlabs_voice_model_mapping(frontend_model)
    api_key = _get_env("ELEVENLABS_API_KEY", "ELEVENLABS-API-KEY")
    prompt_report = optimize_prompt_for_model(
        payload.get("prompt") or voice_options.get("prompt") or "",
        model=frontend_model,
        provider=provider,
        mode="voice",
    )
    print("ELEVENLABS VOICE PROMPT OPTIMIZER:", {
        "model": frontend_model,
        "provider_model": provider_model,
        "tool": tool,
        "prompt_length": prompt_report.get("original_length"),
        "model_limit": prompt_report.get("limit"),
        "optimized": prompt_report.get("optimized"),
        "new_length": prompt_report.get("optimized_length"),
    })
    if (payload.get("prompt") or voice_options.get("prompt")) and not prompt_report.get("ok"):
        return _audio_error(provider, frontend_model, provider_model, "Prompt optimization failed to reach limit", type="voice")
    if prompt_report.get("optimized"):
        payload["prompt"] = prompt_report.get("prompt") or payload.get("prompt") or ""
        payload["prompt_optimization"] = prompt_report
    if not provider_model:
        return _audio_error(provider, frontend_model, "", "Unknown ElevenLabs model mapping", type="voice", frontend_model=frontend_model)
    if not api_key:
        return _audio_error(provider, frontend_model, provider_model, "ELEVENLABS_API_KEY is not configured", type="voice")

    prompt = (payload.get("prompt") or voice_options.get("prompt") or "").strip()
    voice_id = str(voice_options.get("elevenlabs_voice") or voice_options.get("voice") or ELEVENLABS_DEFAULT_VOICE_ID)
    output_format = str(voice_options.get("output_format") or voice_options.get("outputFormat") or ELEVENLABS_DEFAULT_OUTPUT_FORMAT)
    voice_settings = _elevenlabs_voice_settings(voice_options)

    async with httpx.AsyncClient(timeout=180.0) as client:
        try:
            if tool == "speech_to_speech":
                media_url = _runway_input_media_url(payload)
                if not media_url:
                    return _audio_error(provider, frontend_model, provider_model, "ElevenLabs Speech-to-Speech requires uploaded audio file", type="voice", tool=tool)
                audio_bytes, filename, content_type = await _load_provider_media(client, media_url)
                if not audio_bytes:
                    return _audio_error(provider, frontend_model, provider_model, "Could not load audio file for ElevenLabs Speech-to-Speech", type="voice", tool=tool)
                endpoint = f"{ELEVENLABS_BASE_URL}/v1/speech-to-speech/{voice_id}"
                form_data = {
                    "model_id": provider_model,
                    "voice_settings": json.dumps(voice_settings, ensure_ascii=False),
                    "remove_background_noise": str(bool(voice_options.get("remove_background_noise", voice_options.get("removeBackgroundNoise", False)))).lower(),
                }
                print("ELEVENLABS STS REQUEST:", {"endpoint": endpoint, "model": provider_model, "voice_id": voice_id, "file": filename})
                response = await client.post(
                    endpoint,
                    headers={"xi-api-key": api_key},
                    params={"output_format": output_format},
                    data=form_data,
                    files={"audio": (filename, audio_bytes, content_type)},
                )
            elif tool == "dialogue":
                if not prompt:
                    return _audio_error(provider, frontend_model, provider_model, "Dialogue prompt is empty", type="voice", tool=tool)
                endpoint = f"{ELEVENLABS_BASE_URL}/v1/text-to-dialogue"
                request_body = {
                    "inputs": _elevenlabs_dialogue_inputs(prompt, voice_options),
                    "model_id": provider_model,
                }
                print("ELEVENLABS DIALOGUE REQUEST:", {"endpoint": endpoint, "model": provider_model, "inputs": len(request_body["inputs"])})
                response = await client.post(
                    endpoint,
                    headers=_elevenlabs_headers(),
                    params={"output_format": output_format},
                    json=request_body,
                )
            else:
                if not prompt:
                    return _audio_error(provider, frontend_model, provider_model, "Voice prompt is empty", type="voice")
                endpoint = f"{ELEVENLABS_BASE_URL}/v1/text-to-speech/{voice_id}"
                request_body = {
                    "text": prompt,
                    "model_id": provider_model,
                    "voice_settings": voice_settings,
                }
                language_code = voice_options.get("language_code") or voice_options.get("languageCode")
                if language_code:
                    request_body["language_code"] = str(language_code)
                seed = voice_options.get("seed")
                if seed not in (None, ""):
                    try:
                        request_body["seed"] = int(seed)
                    except Exception:
                        pass
                print("ELEVENLABS TTS REQUEST:", {"endpoint": endpoint, "model": provider_model, "voice_id": voice_id, "text_length": len(prompt)})
                response = await client.post(
                    endpoint,
                    headers=_elevenlabs_headers(),
                    params={"output_format": output_format},
                    json=request_body,
                )
        except Exception as exc:
            return _audio_error(provider, frontend_model, provider_model, exc, type="voice", details=repr(exc), tool=tool)

    content_type = response.headers.get("content-type") or "audio/mpeg"
    print("ELEVENLABS VOICE RESPONSE:", {
        "status_code": response.status_code,
        "content_type": content_type,
        "bytes": len(response.content or b""),
        "tool": tool,
    })
    if response.status_code >= 400:
        error_data = await safe_audio_json_response(response, provider, getattr(response, "url", ""))
        return _audio_error(provider, frontend_model, provider_model, error_data, type="voice", status_code=response.status_code, response=error_data, tool=tool)
    if not response.content or ("audio" not in content_type and "octet-stream" not in content_type):
        return _audio_error(provider, frontend_model, provider_model, "ElevenLabs returned non-audio response", type="voice", status_code=response.status_code, body_preview=(response.text or "")[:1000], tool=tool)
    return await _completed_elevenlabs_voice_response(payload, frontend_model, provider_model, tool, response.content, content_type, {"status_code": response.status_code, "content_type": content_type})


# =====================================================
# ЗАПРОС К AI-ПРОВАЙДЕРУ: elevenlabs_voice_preview
# Генерирует короткий JSON-preview ElevenLabs для общей кнопки прослушивания голосов Pro Studio.
# =====================================================
async def elevenlabs_voice_preview(payload: dict) -> dict:
    frontend_model = payload.get("model") or "elevenlabs_multilingual_v2"
    voice = str(payload.get("voice") or ELEVENLABS_DEFAULT_VOICE_ID).strip() or ELEVENLABS_DEFAULT_VOICE_ID
    sample_text = (payload.get("text") or "Привет! Это пример голоса в SYLVEX.").strip()[:220]
    request_payload = {
        "mode": "voice",
        "model": frontend_model,
        "prompt": sample_text,
        "skip_telegram": True,
        "voice_options": {
            "model": frontend_model,
            "voice": voice,
            "elevenlabs_voice": voice,
            "elevenlabs_tool": "text_to_speech",
        },
    }
    result = await elevenlabs_voice_generation(request_payload)
    if not result.get("ok"):
        return result
    result["success"] = True
    result["type"] = "voice_preview"
    return result


# =====================================================
# ЗАПРОС К AI-ПРОВАЙДЕРУ: _runway_voice_payload
# Собирает официальный payload Runway Text to Speech: текст пользователя и выбранный голос.
# =====================================================
def _runway_voice_payload(payload: dict, provider_model: str) -> dict[str, Any]:
    voice_options = payload.get("voice_options") or {}
    tool = _runway_audio_tool(payload)
    prompt = (payload.get("prompt") or voice_options.get("prompt") or "").strip()
    voice_id = (
        voice_options.get("runway_voice")
        or voice_options.get("voice")
        or voice_options.get("voice_name")
        or "Maya"
    )
    if tool == "sound_effect":
        body = {
            "model": provider_model,
            "promptText": prompt,
        }
        duration = voice_options.get("duration") or voice_options.get("runway_duration") or voice_options.get("runwayDuration")
        try:
            duration_value = float(duration)
        except Exception:
            duration_value = 5
        body["duration"] = max(1, min(30, duration_value))
        return body

    if tool == "speech_to_speech":
        media_url = _runway_input_media_url(payload)
        return {
            "model": provider_model,
            "media": {
                "type": "audio",
                "uri": media_url,
            },
            "voice": {
                "type": "runway-preset",
                "presetId": str(voice_id or "Maya"),
            },
        }

    if tool == "voice_dubbing":
        media_url = _runway_input_media_url(payload)
        return {
            "model": provider_model,
            "audioUri": media_url,
            "targetLanguage": str(voice_options.get("target_language") or voice_options.get("targetLanguage") or "en"),
        }

    if tool == "voice_isolation":
        media_url = _runway_input_media_url(payload)
        return {
            "model": provider_model,
            "audioUri": media_url,
        }

    return {
        "model": provider_model,
        "promptText": prompt,
        "voice": {
            "type": "runway-preset",
            "presetId": str(voice_id or "Maya"),
        },
    }


# =====================================================
# ЗАПРОС К AI-ПРОВАЙДЕРУ: _completed_runway_voice_response
# Формирует единый успешный ответ озвучки Runway для Job, Mini App, истории и Telegram.
# =====================================================
async def _completed_runway_voice_response(
    payload: dict,
    frontend_model: str,
    provider_model: str,
    task_id: str,
    status: str,
    audio_url: str,
    provider_response: Any,
) -> dict:
    voice_options = payload.get("voice_options") or {}
    tool = _runway_audio_tool(payload)
    voice = (
        voice_options.get("runway_voice")
        or voice_options.get("voice")
        or voice_options.get("voice_name")
        or "Maya"
    )
    telegram_id = int(payload.get("telegram_id") or 0)
    sent_to_telegram = False
    if not payload.get("skip_telegram"):
        sent_to_telegram = await _send_generated_audio_to_telegram(
            telegram_id=telegram_id,
            audio_url=audio_url,
            caption="SYLVEX Pro Studio\nОзвучка Runway готова ✅",
        )
    return {
        "ok": True,
        "type": "voice",
        "provider": "runway",
        "model": frontend_model,
        "provider_model": provider_model,
        "status": "completed",
        "task_id": task_id,
        "runway_tool": tool,
        "audio_url": audio_url,
        "audios": [audio_url],
        "voice": voice,
        "voice_options": voice_options,
        "response": provider_response,
        "sent_to_telegram": sent_to_telegram,
        "text": "Озвучка готова ✅\n" + audio_url,
    }


# =====================================================
# POLLING-ПРОЦЕСС: _poll_runway_voice_task
# Проверяет статус задачи Runway до готового аудио или ошибки и останавливается сразу после финального состояния.
# =====================================================
async def _poll_runway_voice_task(
    client: httpx.AsyncClient,
    api_key: str,
    frontend_model: str,
    provider_model: str,
    task_id: str,
    payload: dict,
    initial_response: Any,
) -> dict:
    task_url = f"{RUNWAY_API_BASE_URL}/v1/tasks/{task_id}"
    attempts = int(os.getenv("RUNWAY_AUDIO_POLL_ATTEMPTS", "90"))
    interval = float(os.getenv("RUNWAY_AUDIO_POLL_INTERVAL", "2"))
    last_data = initial_response

    for attempt in range(1, attempts + 1):
        try:
            response = await client.get(task_url, headers=_runway_headers(api_key))
            data = await safe_audio_json_response(response, "runway", task_url)
        except Exception as exc:
            return _audio_error("runway", frontend_model, provider_model, exc, type="voice", endpoint=task_url, task_id=task_id, details=repr(exc))

        last_data = data
        status = _runway_status(data)
        audio_urls = _runway_audio_urls(data)
        print("RUNWAY TTS POLL:", {
            "attempt": attempt,
            "task_id": task_id,
            "status": status,
            "has_audio_url": bool(audio_urls),
            "status_code": response.status_code,
        })

        if response.status_code >= 400:
            return _audio_error("runway", frontend_model, provider_model, data, type="voice", endpoint=task_url, status_code=response.status_code, response=data, task_id=task_id)

        if status in {"succeeded", "success", "completed", "complete", "done"} and audio_urls:
            local_audio_url = await _download_runway_audio(client, audio_urls[0])
            if not local_audio_url:
                return _audio_error("runway", frontend_model, provider_model, "Runway TTS audio download failed", type="voice", endpoint=task_url, response=data, task_id=task_id)
            return await _completed_runway_voice_response(
                payload,
                frontend_model,
                provider_model,
                task_id,
                status,
                local_audio_url,
                data,
            )

        if status in {"failed", "failure", "error", "cancelled", "canceled"}:
            return _audio_error("runway", frontend_model, provider_model, data, type="voice", endpoint=task_url, status=status, response=data, task_id=task_id)

        if attempt < attempts:
            await asyncio.sleep(interval)

    return _audio_error("runway", frontend_model, provider_model, "Runway TTS polling timed out", type="voice", endpoint=task_url, response=last_data, task_id=task_id)


# =====================================================
# ЗАПРОС К AI-ПРОВАЙДЕРУ: runway_voice_generation
# Подключает раздел «Озвучка» Mini App к официальному Runway Text to Speech API.
# Получает текст, выбранный голос Runway, создаёт задачу, ждёт результат и возвращает audio_url.
# =====================================================
async def runway_voice_generation(payload: dict) -> dict:
    provider = "runway"
    voice_options = payload.get("voice_options") or {}
    tool = _runway_audio_tool(payload)
    tool_config = RUNWAY_AUDIO_TOOLS.get(tool) or RUNWAY_AUDIO_TOOLS["text_to_speech"]
    frontend_model = (
        payload.get("model")
        or voice_options.get("model")
        or "runway_eleven_multilingual_v2"
    )
    provider_model = tool_config["model"]
    api_key = _get_env("RUNWAY_API_KEY", "RUNWAYML_API_SECRET", "RUNWAYML_API_KEY")
    prompt_report = optimize_prompt_for_model(
        payload.get("prompt") or voice_options.get("prompt") or "",
        model=frontend_model,
        provider=provider,
        mode="voice",
    )
    print("RUNWAY TTS PROMPT OPTIMIZER:", {
        "model": frontend_model,
        "provider_model": provider_model,
        "tool": tool,
        "prompt_length": prompt_report.get("original_length"),
        "model_limit": prompt_report.get("limit"),
        "optimized": prompt_report.get("optimized"),
        "new_length": prompt_report.get("optimized_length"),
    })
    needs_prompt = tool in {"text_to_speech", "sound_effect"}
    needs_media = tool in {"speech_to_speech", "voice_dubbing", "voice_isolation"}
    if (payload.get("prompt") or voice_options.get("prompt")) and not prompt_report.get("ok"):
        return _audio_error(provider, frontend_model, provider_model, "Prompt optimization failed to reach limit", type="voice")
    if prompt_report.get("optimized"):
        payload["prompt"] = prompt_report.get("prompt") or payload.get("prompt") or ""
        payload["prompt_optimization"] = prompt_report

    if not api_key:
        return _audio_error(provider, frontend_model, provider_model, "RUNWAY_API_KEY is not configured", type="voice")
    if needs_prompt and not (payload.get("prompt") or "").strip():
        return _audio_error(provider, frontend_model, provider_model, "Voice prompt is empty", type="voice")
    if needs_media and not _runway_input_media_url(payload):
        return _audio_error(provider, frontend_model, provider_model, "Runway audio tool requires uploaded audio or video file", type="voice", tool=tool)

    endpoint = f"{RUNWAY_API_BASE_URL}{tool_config['endpoint']}"
    request_body = _runway_voice_payload(payload, provider_model)
    print("RUNWAY TTS REQUEST:", {
        "endpoint": endpoint,
        "frontend_model": frontend_model,
        "provider_model": provider_model,
        "tool": tool,
        "voice": (request_body.get("voice") or {}).get("presetId"),
        "has_prompt": bool(request_body.get("promptText")),
        "has_media": bool((request_body.get("media") or {}).get("uri") or request_body.get("audioUri")),
    })

    async with httpx.AsyncClient(timeout=180.0) as client:
        try:
            response = await client.post(endpoint, headers=_runway_headers(api_key), json=request_body)
        except Exception as exc:
            return _audio_error(provider, frontend_model, provider_model, exc, type="voice", endpoint=endpoint, details=repr(exc))
        data = await safe_audio_json_response(response, provider, endpoint)
        print("RUNWAY TTS RESPONSE:", {
            "status_code": response.status_code,
            "task_id": _runway_task_id(data),
            "status": _runway_status(data),
            "has_audio_url": bool(_runway_audio_urls(data)),
            "body_preview": json.dumps(data, ensure_ascii=False)[:1200] if isinstance(data, (dict, list)) else str(data)[:1200],
        })
        if response.status_code >= 400:
            return _audio_error(provider, frontend_model, provider_model, data, type="voice", endpoint=endpoint, status_code=response.status_code, response=data)

        audio_urls = _runway_audio_urls(data)
        if audio_urls:
            local_audio_url = await _download_runway_audio(client, audio_urls[0])
            if not local_audio_url:
                return _audio_error(provider, frontend_model, provider_model, "Runway TTS audio download failed", type="voice", endpoint=endpoint, response=data)
            return await _completed_runway_voice_response(payload, frontend_model, provider_model, _runway_task_id(data), _runway_status(data), local_audio_url, data)

        task_id = _runway_task_id(data)
        if not task_id:
            return _audio_error(provider, frontend_model, provider_model, "Runway TTS did not return task id", type="voice", endpoint=endpoint, response=data)

        return await _poll_runway_voice_task(client, api_key, frontend_model, provider_model, task_id, payload, data)


# =====================================================
# ЗАПРОС К AI-ПРОВАЙДЕРУ: fetch_runway_voices
# Загружает список голосов Runway для Mini App. Если API недоступен, возвращает безопасный локальный список.
# =====================================================
async def fetch_runway_voices() -> dict:
    api_key = _get_env("RUNWAY_API_KEY", "RUNWAYML_API_SECRET", "RUNWAYML_API_KEY")
    if not api_key:
        return {"ok": True, "success": True, "provider": "runway", "voices": RUNWAY_VOICE_FALLBACKS, "fallback": True}

    endpoint = f"{RUNWAY_API_BASE_URL}/v1/voices"
    async with httpx.AsyncClient(timeout=60.0) as client:
        try:
            response = await client.get(endpoint, headers=_runway_headers(api_key))
            data = await safe_audio_json_response(response, "runway", endpoint)
        except Exception as exc:
            print("RUNWAY VOICES FAILED:", repr(exc))
            return {"ok": True, "success": True, "provider": "runway", "voices": RUNWAY_VOICE_FALLBACKS, "fallback": True}

    if response.status_code >= 400:
        print("RUNWAY VOICES ERROR:", {
            "status_code": response.status_code,
            "body_preview": json.dumps(data, ensure_ascii=False)[:900] if isinstance(data, (dict, list)) else str(data)[:900],
        })
        return {"ok": True, "success": True, "provider": "runway", "voices": RUNWAY_VOICE_FALLBACKS, "fallback": True}

    source = data
    if isinstance(data, dict):
        for key in ("voices", "data", "items", "results"):
            if isinstance(data.get(key), list):
                source = data.get(key)
                break
    voices = []
    if isinstance(source, list):
        for item in source:
            if not isinstance(item, dict):
                continue
            voice_id = (
                item.get("id")
                or item.get("voice_id")
                or item.get("voiceId")
                or item.get("presetId")
                or item.get("preset_id")
                or item.get("name")
            )
            if not voice_id:
                continue
            name = item.get("name") or item.get("displayName") or item.get("label") or voice_id
            voices.append({
                "voice_id": str(voice_id),
                "name": str(name),
                "provider": "runway",
                "type": str(item.get("type") or "runway-preset"),
                "preview_url": str(item.get("preview_url") or item.get("previewUrl") or item.get("sample_url") or ""),
                "raw": item,
            })
    if not voices:
        voices = RUNWAY_VOICE_FALLBACKS
    return {"ok": True, "success": True, "provider": "runway", "voices": voices, "response": data}


# =====================================================
# ЗАПРОС К AI-ПРОВАЙДЕРУ: runway_voice_preview
# Генерирует короткий пример выбранного голоса Runway без создания Job.
# Используется только кнопкой прослушивания голоса в Mini App.
# =====================================================
async def runway_voice_preview(payload: dict) -> dict:
    frontend_model = payload.get("model") or "runway_eleven_multilingual_v2"
    voice = str(payload.get("voice") or "Maya").strip() or "Maya"
    sample_text = (payload.get("text") or "Привет! Это пример голоса в SYLVEX.").strip()[:220]
    request_payload = {
        "mode": "voice",
        "model": frontend_model,
        "prompt": sample_text,
        "skip_telegram": True,
        "voice_options": {
            "model": frontend_model,
            "voice": voice,
            "runway_voice": voice,
        },
    }
    result = await runway_voice_generation(request_payload)
    if not result.get("ok"):
        return result
    result["success"] = True
    result["type"] = "voice_preview"
    return result


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
# ЗАПРОС К AI-ПРОВАЙДЕРУ: gemini_tts_voice_preview
# Генерирует короткий пример выбранного голоса Gemini TTS без создания Job.
# Mini App использует этот endpoint только для прослушивания голоса перед выбором.
# =====================================================
async def gemini_tts_voice_preview(payload: dict) -> dict:
    provider = "gemini"
    frontend_model = payload.get("model") or "gemini_3_1_flash_tts_preview"
    provider_model = _gemini_tts_model_mapping(frontend_model)
    api_key = _get_env("GEMINI_API_KEY", "GOOGLE_API_KEY", "GOOGLE-GEMINI-API-KEY")
    voice = str(payload.get("voice") or "Kore").strip()
    if voice not in GEMINI_TTS_VOICE_NAMES:
        return _audio_error(provider, frontend_model, provider_model, f"Unsupported Gemini TTS voice: {voice}")
    if not provider_model:
        return _audio_error(provider, frontend_model, "", "Unknown Gemini TTS model mapping", frontend_model=frontend_model)
    if not api_key:
        return _audio_error(provider, frontend_model, provider_model, "GEMINI_API_KEY is not configured")

    sample_text = (payload.get("text") or "Привет! Это пример голоса в SYLVEX.").strip()[:220]
    request_payload = {
        "prompt": sample_text,
        "voice_options": {
            "model": frontend_model,
            "voice": voice,
            "speaker_mode": "single",
        },
    }
    request_body = _gemini_tts_payload(request_payload, provider_model)
    request_body.pop("_debug_effective_speaker_mode", None)
    headers = {
        "x-goog-api-key": api_key,
        "Content-Type": "application/json",
    }
    print("GEMINI TTS VOICE PREVIEW REQUEST:", {
        "endpoint": GEMINI_TTS_ENDPOINT,
        "frontend_model": frontend_model,
        "provider_model": provider_model,
        "voice": voice,
        "text_length": len(sample_text),
    })
    async with httpx.AsyncClient(timeout=120.0) as client:
        try:
            response = await client.post(GEMINI_TTS_ENDPOINT, headers=headers, json=request_body)
        except Exception as exc:
            return _audio_error(provider, frontend_model, provider_model, exc, endpoint=GEMINI_TTS_ENDPOINT, details=repr(exc))
    data = await safe_audio_json_response(response, provider, GEMINI_TTS_ENDPOINT)
    print("GEMINI TTS VOICE PREVIEW RESPONSE:", {
        "status_code": response.status_code,
        "has_output_audio": bool(_extract_gemini_output_audio(data)),
        "body_preview": json.dumps(data, ensure_ascii=False)[:900] if isinstance(data, (dict, list)) else str(data)[:900],
    })
    if response.status_code >= 400:
        return _audio_error(provider, frontend_model, provider_model, data, endpoint=GEMINI_TTS_ENDPOINT, status_code=response.status_code, response=data)
    audio_data = _extract_gemini_output_audio(data)
    if not audio_data:
        return _audio_error(provider, frontend_model, provider_model, "Gemini TTS preview returned no output_audio", endpoint=GEMINI_TTS_ENDPOINT, response=data)
    try:
        audio_bytes = base64.b64decode(audio_data)
    except Exception as exc:
        return _audio_error(provider, frontend_model, provider_model, f"Gemini TTS preview audio decode failed: {exc}", response=data)
    audio_url = _save_gemini_tts_wav(audio_bytes)
    if not audio_url:
        return _audio_error(provider, frontend_model, provider_model, "Gemini TTS preview audio save failed", response=data)
    return {
        "ok": True,
        "success": True,
        "type": "voice_preview",
        "provider": provider,
        "model": frontend_model,
        "provider_model": provider_model,
        "voice": voice,
        "audio_url": audio_url,
        "audios": [audio_url],
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
