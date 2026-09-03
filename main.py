# =====================================================
# АВТОДОКУМЕНТАЦИЯ SYLVEX: main.py
# Этот файл подписан русскими пояснениями для быстрой навигации по проекту.
# Комментарии описывают назначение блоков и не меняют работу приложения.
# =====================================================
import os
import pathlib
import json
import hmac
import hashlib
import urllib.parse
import asyncio
import re
import base64
import time
import traceback
import threading
import random
import html
import concurrent.futures
import tempfile
import mimetypes
from typing import Optional
from uuid import uuid4
import requests
import psycopg2
from dotenv import load_dotenv
from fastapi.responses import JSONResponse, RedirectResponse, StreamingResponse
from routers.video_templates import router as video_templates_router

from services.audio_router import audio_generation, elevenlabs_clone_voice_from_audio, elevenlabs_voice_preview, fetch_elevenlabs_prostudio_voices, fetch_runway_voices, gemini_tts_voice_preview, runway_voice_preview, _extract_audio_from_video_for_dubbing, _mux_video_with_audio, _send_generated_audio_to_telegram
from services.error_translator import raw_error_text, translate_provider_error
from services.prompt_optimizer import optimize_prompt_for_model
from services.character_prompts import build_character_prompt, infer_character_operation
from services.video_router import estimate_video_generation_cost, poll_video_generation, video_generation, _send_generated_videos_to_telegram, _gemini_upload_file_from_url
from services.storage import delete as storage_delete, exists as storage_exists, generated_key, get_object as storage_get_object, get_object_range as storage_get_object_range, iter_object as storage_iter_object, key_from_url as storage_key_from_url, object_url as storage_object_url, put_bytes as storage_put_bytes, put_file as storage_put_file, read_bytes as storage_read_bytes, r2_enabled
from services.prostudio_share import create_or_get_share, get_public_share, increment_downloads
from provider_concurrency import WORKER_ID, ProviderSlotUnavailable, ensure_provider_slot_table, normalize_provider, provider_slot
from provider_resilience import (
    circuit_before_request,
    circuit_record_outcome,
    circuit_release_probe,
    run_with_provider_retry,
)
from db_pool import close_db_pool, db_connect, db_pool_status, start_db_pool

from fastapi import FastAPI, Request, UploadFile, File, HTTPException
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

load_dotenv()

app = FastAPI()

STATIC_IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg", ".avif", ".ico")


@app.middleware("http")
async def cache_static_images(request: Request, call_next):
    """Keep version-stable visual assets in the Telegram WebView cache."""
    response = await call_next(request)
    path = request.url.path.lower()
    if response.status_code in {200, 206} and path.endswith(STATIC_IMAGE_EXTENSIONS):
        response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    return response

BASE_DIR = pathlib.Path(__file__).resolve().parent
WEBAPP_DIR = BASE_DIR / "webapp"
PRESET_CATALOG_DIR = BASE_DIR / "backend" / "preset_catalog"
PRESET_CHARACTERS_DIR = PRESET_CATALOG_DIR / "characters"
PRESET_OBJECTS_DIR = PRESET_CATALOG_DIR / "objects"
VOICE_AVATARS_DIR = PRESET_CATALOG_DIR / "voice_avatars"
VOICE_GENERATED_AVATARS_DIR = WEBAPP_DIR / "generated" / "voice-avatars"
VOICE_AVATAR_AUTO_GENERATION = os.getenv("VOICE_AVATAR_AUTO_GENERATION", "0").lower() in {"1", "true", "yes"}
PRESET_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
PRESET_CATALOG_CACHE_TTL = 60
PRESET_CATALOG_CACHE = {"expires_at": 0.0, "value": None}
VIDEO_TEMPLATE_CATALOG_CACHE_TTL = 60
VIDEO_TEMPLATE_CATALOG_CACHE = {"expires_at": 0.0, "value": None}
PHOTO_CATALOG_CACHE_TTL = 60
PHOTO_CATALOG_CACHE = {"expires_at": 0.0, "value": None}
QUICK_IMAGE_CATALOG_CACHE = {"expires_at": 0.0, "value": None}
HEYGEN_AVATAR_LOOK_CACHE_TTL = 300
HEYGEN_AVATAR_LOOK_CACHE = {}

for catalog_dir in (PRESET_CHARACTERS_DIR, PRESET_OBJECTS_DIR, VOICE_AVATARS_DIR, VOICE_GENERATED_AVATARS_DIR):
    catalog_dir.mkdir(parents=True, exist_ok=True)

app.mount("/webapp", StaticFiles(directory=WEBAPP_DIR, html=True), name="webapp")
app.mount("/static", StaticFiles(directory=WEBAPP_DIR), name="static")
app.mount("/image", StaticFiles(directory="image"), name="image")
app.mount("/assets", StaticFiles(directory="webapp/assets"), name="assets")
app.mount("/js", StaticFiles(directory="webapp/js"), name="js")
app.mount("/css", StaticFiles(directory="webapp/css"), name="css")
app.mount("/generated", StaticFiles(directory=WEBAPP_DIR / "generated"), name="generated")
app.mount("/preset_catalog", StaticFiles(directory=PRESET_CATALOG_DIR), name="preset_catalog")
app.include_router(video_templates_router)


@app.get("/api/public/storage/{object_key:path}")
async def public_storage_object(object_key: str, request: Request):
    key = storage_key_from_url(object_key) or object_key
    try:
        range_header = str(request.headers.get("range") or "")
        body, content_type, content_length, total, start, end = await asyncio.to_thread(storage_get_object_range, key, range_header)
    except Exception:
        return Response(status_code=404)
    headers = {"Cache-Control": "public, max-age=31536000, immutable", "Accept-Ranges": "bytes"}
    headers["Content-Length"] = str(content_length)
    status_code = 206 if range_header else 200
    if range_header:
        headers["Content-Range"] = f"bytes {start}-{end}/{total}"
    return StreamingResponse(storage_iter_object(body, max_bytes=content_length), media_type=content_type, headers=headers, status_code=status_code)

_BOT_TOKEN_VALUES = [
    str(os.getenv("BOT_TOKEN") or "").strip(),
    str(os.getenv("TELEGRAM_BOT_TOKEN") or "").strip(),
]
TELEGRAM_AUTH_TOKENS = tuple(dict.fromkeys(token for token in _BOT_TOKEN_VALUES if token))
BOT_TOKEN = TELEGRAM_AUTH_TOKENS[0] if TELEGRAM_AUTH_TOKENS else ""
TELEGRAM_PAYMENT_WEBHOOK_SECRET = (os.getenv("TELEGRAM_PAYMENT_WEBHOOK_SECRET") or "").strip()
DATABASE_URL = os.getenv("DATABASE_PUBLIC_URL") or os.getenv("DATABASE_URL")
print("MINIAPP DATABASE CONFIGURED:", bool(DATABASE_URL))
PROSTUDIO_SCHEMA_LOCK = threading.Lock()
PROSTUDIO_WORKER_ENABLED = os.getenv("PROSTUDIO_WORKER_ENABLED", "1").lower() not in {"0", "false", "no"}
PROSTUDIO_WORKER_INTERVAL = float(os.getenv("PROSTUDIO_WORKER_INTERVAL", "2"))


def _bounded_prostudio_worker_concurrency(value) -> int:
    try:
        raw = str("3" if value is None else value).strip() or "3"
        parsed = int(raw)
    except (TypeError, ValueError):
        parsed = 3
    return max(1, min(20, parsed))


PROSTUDIO_WORKER_CONCURRENCY = _bounded_prostudio_worker_concurrency(
    os.getenv("PROSTUDIO_WORKER_CONCURRENCY", "3")
)
PROSTUDIO_MOCK_GENERATION = os.getenv("PROSTUDIO_MOCK_GENERATION", "0").strip().lower() in {
    "1", "true", "yes", "on",
}
SUBSCRIPTION_REMINDER_WORKER_ENABLED = os.getenv("SUBSCRIPTION_REMINDER_WORKER_ENABLED", "1").lower() not in {"0", "false", "no"}
SUBSCRIPTION_REMINDER_INTERVAL_SECONDS = int(os.getenv("SUBSCRIPTION_REMINDER_INTERVAL_SECONDS", "1800"))
PROSTUDIO_STALE_PROCESSING_MINUTES = int(os.getenv("PROSTUDIO_STALE_PROCESSING_MINUTES", "30"))
PROSTUDIO_MAX_JOB_ATTEMPTS = int(os.getenv("PROSTUDIO_MAX_JOB_ATTEMPTS", "3"))
SUPERADMIN_TELEGRAM_ID = int(os.getenv("SUPERADMIN_TELEGRAM_ID", "7932380565") or 7932380565)
PROSTUDIO_ADMIN_ID = int(os.getenv("ADMIN_ID", str(SUPERADMIN_TELEGRAM_ID)) or SUPERADMIN_TELEGRAM_ID)
PROSTUDIO_TEXT_RESPONSE_CACHE = {}
WEBAPP_URL = os.getenv("WEBAPP_URL", "https://sylvex-ai-webapp-production.up.railway.app")
PAYMENT_WEBAPP_URL = os.getenv("PAYMENT_WEBAPP_URL", WEBAPP_URL.rstrip("/") + "/payments")
SHOP_WEBAPP_URL = os.getenv("SHOP_WEBAPP_URL", WEBAPP_URL.rstrip("/") + "/webapp/index.html?view=shop")

# =====================================================
# PYTHON-БЛОК: env_value
# Выполняет отдельный шаг backend-логики SYLVEX.
# Связан с API, базой данных, провайдерами или подготовкой данных для Mini App.
# =====================================================
def env_value(*names: str, default: str = "") -> str:
    for name in names:
        value = os.getenv(name)
        if value:
            return value
    return default

def _natural_catalog_key(value: str):
    return [int(part) if part.isdigit() else part.lower() for part in re.split(r"(\d+)", str(value or ""))]

def _preset_file_url(path: pathlib.Path) -> str:
    rel = path.relative_to(PRESET_CATALOG_DIR)
    return "/preset_catalog/" + "/".join(urllib.parse.quote(part) for part in rel.parts)

def _catalog_folder_label(folder: pathlib.Path) -> str:
    return re.sub(r"[_-]+", " ", folder.name).strip().title() or folder.name

def _catalog_image_files(folder: pathlib.Path) -> list[pathlib.Path]:
    if not folder.exists() or not folder.is_dir():
        return []
    return sorted(
        [
            item for item in folder.iterdir()
            if item.is_file() and item.suffix.lower() in PRESET_IMAGE_EXTENSIONS
        ],
        key=lambda item: _natural_catalog_key(item.name),
    )

def _catalog_video_files(folder: pathlib.Path) -> list[pathlib.Path]:
    if not folder.exists() or not folder.is_dir():
        return []
    return sorted(
        [
            item for item in folder.iterdir()
            if item.is_file() and item.suffix.lower() in {".mp4", ".mov", ".m4v", ".webm"}
        ],
        key=lambda item: _natural_catalog_key(item.name),
    )

def _catalog_json_file(folder: pathlib.Path, name: str) -> dict:
    path = folder / name
    if not path.exists() or not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}

def _scan_preset_catalog_section(section_dir: pathlib.Path, kind: str) -> list[dict]:
    items = []
    if not section_dir.exists():
        return items
    def catalog_sort_key(item: pathlib.Path):
        official_rank = 0 if kind == "character" and item.name.lower() == "sylvex" else 1
        return (official_rank, _natural_catalog_key(item.name))

    for folder in sorted([item for item in section_dir.iterdir() if item.is_dir()], key=catalog_sort_key):
        images = _catalog_image_files(folder)
        videos = _catalog_video_files(folder)
        avatar = next((item for item in images if item.stem.lower() == "avatar"), None)
        references = [item for item in images if item != avatar]
        video_reference = next((item for item in videos if item.stem.lower() == "video_reference"), None) or (videos[0] if videos else None)
        heygen_meta = _catalog_json_file(folder, "heygen.json")
        prompt_path = folder / "prompt.txt"
        prompt = ""
        if prompt_path.exists() and prompt_path.is_file():
            try:
                prompt = prompt_path.read_text(encoding="utf-8").strip()
            except UnicodeDecodeError:
                prompt = prompt_path.read_text(errors="ignore").strip()
        avatar_image = avatar or (references[0] if references else None)
        item = {
            "id": f"{kind}_{folder.name}",
            "name": _catalog_folder_label(folder),
            "prompt": prompt,
            "avatarUrl": _preset_file_url(avatar_image) if avatar_image else "",
            "referenceImages": [_preset_file_url(image) for image in references],
            "videoReferenceUrl": _preset_file_url(video_reference) if video_reference else "",
            "videoReferences": [_preset_file_url(video) for video in videos],
            "heygenPhotoAvatarId": heygen_meta.get("photoAvatarId") or heygen_meta.get("photo_avatar_id") or heygen_meta.get("avatar_id") or "",
            "heygenVideoAvatarId": heygen_meta.get("videoAvatarId") or heygen_meta.get("video_avatar_id") or "",
            "heygenAvatarGroupId": heygen_meta.get("avatarGroupId") or heygen_meta.get("avatar_group_id") or "",
            "heygenDefaultVoiceId": heygen_meta.get("defaultVoiceId") or heygen_meta.get("default_voice_id") or "",
            "heygenLooks": heygen_meta.get("looks") if isinstance(heygen_meta.get("looks"), list) else [],
            "type": "file-preset",
            "status": "ready",
            "sourcePath": str(folder.relative_to(BASE_DIR)),
        }
        if kind == "character":
            item["gender"] = "neutral"
            if folder.name.lower() == "sylvex":
                item["official"] = True
                item["label"] = "Official AI SYLVEX character"
        else:
            item["description"] = ""
        items.append(item)
    return items

def load_preset_catalog() -> dict:
    now = time.time()
    cached = PRESET_CATALOG_CACHE.get("value")
    if cached is not None and now < float(PRESET_CATALOG_CACHE.get("expires_at") or 0):
        return cached
    catalog = {
        "characters": _scan_preset_catalog_section(PRESET_CHARACTERS_DIR, "character"),
        "objects": _scan_preset_catalog_section(PRESET_OBJECTS_DIR, "object"),
    }
    PRESET_CATALOG_CACHE["value"] = catalog
    PRESET_CATALOG_CACHE["expires_at"] = now + PRESET_CATALOG_CACHE_TTL
    return catalog

def load_voice_avatar_catalog() -> dict:
    avatars = []
    if VOICE_AVATARS_DIR.exists():
        folders = [VOICE_AVATARS_DIR]
        folders.extend([item for item in VOICE_AVATARS_DIR.rglob("*") if item.is_dir()])
        for folder in sorted(folders, key=lambda item: _natural_catalog_key(str(item.relative_to(VOICE_AVATARS_DIR)))):
            images = _catalog_image_files(folder)
            avatar = next((item for item in images if item.stem.lower() == "avatar"), None) or (images[0] if images else None)
            if not avatar:
                continue
            rel_parts = folder.relative_to(VOICE_AVATARS_DIR).parts
            # Изображения принимаются только из provider/voice_id/, чтобы файл в корне
            # провайдера случайно не превратился в отдельный голос.
            if len(rel_parts) < 2:
                continue
            provider = rel_parts[0]
            voice_id = rel_parts[-1]
            metadata = _catalog_json_file(folder, "voice.json")
            voice_id = str(metadata.get("voice_id") or metadata.get("id") or voice_id)
            provider = str(metadata.get("provider") or provider)
            avatars.append({
                "id": voice_id,
                "voice_id": voice_id,
                "provider": provider,
                "name": metadata.get("name") or voice_id,
                "gender": metadata.get("gender") or "neutral",
                "avatarUrl": _preset_file_url(avatar),
                "sourcePath": str(folder.relative_to(BASE_DIR)),
            })
    if DATABASE_URL and VOICE_AVATAR_AUTO_GENERATION:
        try:
            ensure_prostudio_table()
            conn = db_connect(DATABASE_URL)
            cursor = conn.cursor()
            cursor.execute("""
                SELECT provider, voice_id, seed, avatar_key, avatar_path
                FROM prostudio_voice_avatars WHERE status = 'ready'
                ORDER BY provider, voice_id
            """)
            for provider, voice_id, seed, avatar_key, avatar_path in cursor.fetchall():
                avatars.append({
                    "id": voice_id,
                    "voice_id": voice_id,
                    "provider": provider,
                    "seed": seed,
                    "avatarUrl": avatar_path or f"/api/public/prostudio/voice-avatar/{avatar_key}",
                })
            cursor.execute("SELECT COUNT(*) FROM prostudio_voice_avatars WHERE status IN ('pending', 'generating')")
            pending_count = int(cursor.fetchone()[0] or 0)
            cursor.close()
            conn.close()
            return {"avatars": avatars, "pending_count": pending_count}
        except Exception as exc:
            print("VOICE AVATAR CATALOG DB FAILED:", exc)
    return {"avatars": avatars, "pending_count": 0}


VOICE_AVATAR_EXECUTOR = concurrent.futures.ThreadPoolExecutor(
    max_workers=max(1, int(os.getenv("VOICE_AVATAR_GENERATION_WORKERS", "1")))
)
VOICE_AVATAR_IN_FLIGHT = set()
VOICE_AVATAR_IN_FLIGHT_LOCK = threading.Lock()


def _voice_avatar_identity(provider: str, voice_id: str) -> tuple[str, int]:
    # По ТЗ идентичность портрета зависит только от voice_id, а не от порядка выдачи или провайдера.
    normalized = str(voice_id or "").strip()
    digest = hashlib.sha256(normalized.encode("utf-8")).digest()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:40], int.from_bytes(digest[:8], "big") & 0x7FFFFFFFFFFFFFFF


def _voice_avatar_prompt(provider: str, voice_id: str, seed: int) -> str:
    rng = random.Random(seed)
    choices = lambda values: rng.choice(values)
    attributes = {
        "gender": choices(["woman", "man", "androgynous adult"]),
        "age": choices(["young adult", "adult in their thirties", "mature adult in their forties", "mature adult in their fifties"]),
        "heritage": choices(["East Asian", "South Asian", "Southeast Asian", "Middle Eastern", "North African", "West African", "East African", "Northern European", "Southern European", "Latin American", "Central Asian", "mixed heritage"]),
        "skin": choices(["porcelain", "fair", "olive", "golden tan", "warm brown", "deep brown", "ebony"]),
        "eyes": choices(["dark brown", "hazel", "green", "gray", "blue", "amber"]),
        "face": choices(["oval", "angular", "round", "heart-shaped", "long", "square"]),
        "nose": choices(["straight", "softly rounded", "aquiline", "wide", "delicate"]),
        "lips": choices(["full", "defined", "soft", "narrow"]),
        "hair": choices(["short textured crop", "sleek bob", "long loose waves", "natural curls", "close-cropped hair", "shoulder-length straight hair", "braided hair", "modern swept-back style"]),
        "hair_color": choices(["black", "dark brown", "chestnut", "copper", "platinum blond", "ash blond", "silver gray"]),
        "clothes": choices(["minimalist tailored jacket", "premium knit top", "modern high-collar shirt", "understated satin blouse", "clean structured overshirt", "elegant monochrome blazer"]),
        "clothes_color": choices(["charcoal", "ivory", "navy", "deep burgundy", "forest green", "sand", "muted violet", "cobalt"]),
        "light": choices(["soft teal rim light", "warm amber edge light", "cool silver rim light", "subtle violet edge light", "soft daylight rim light"]),
        "background": choices(["warm gray", "cool graphite", "muted blue-gray", "soft beige", "desaturated teal", "subtle lavender-gray"]),
        "accessory": choices(["no accessories", "small geometric earrings", "a subtle ear cuff", "thin modern eyeglasses", "a minimal necklace"]),
        "palette": choices(["teal and graphite", "amber and charcoal", "cobalt and silver", "burgundy and warm gray", "forest green and sand", "violet and slate"]),
    }
    return (
        "Create one unique fictional adult voice avatar in the premium SYLVEX visual identity. "
        "Photorealistic studio portrait, chest-up, looking directly into camera, calm expression, slight torso turn, neutral pose, centered composition, square crop. "
        f"Subject: {attributes['gender']}, {attributes['age']}, {attributes['heritage']} appearance, {attributes['skin']} skin, {attributes['eyes']} eyes, "
        f"{attributes['face']} face, {attributes['nose']} nose, {attributes['lips']} lips, {attributes['hair']} in {attributes['hair_color']}. "
        f"Wardrobe: {attributes['clothes']} in {attributes['clothes_color']}, {attributes['accessory']}. Color palette: {attributes['palette']}. Lighting: soft cinematic key light with {attributes['light']}. "
        f"Minimal neutral {attributes['background']} studio background. Premium retouching, highly detailed natural skin, contemporary AI editorial style. "
        "One person only, no text, no letters, no logo, no watermark, no border."
    )


def _generate_voice_avatar_once(provider: str, voice_id: str):
    key, seed = _voice_avatar_identity(provider, voice_id)
    try:
        if not DATABASE_URL or not OPENAI_API_KEY:
            raise RuntimeError("DATABASE_URL or OPENAI_API_KEY is not configured")
        ensure_prostudio_table()
        conn = db_connect(DATABASE_URL)
        cursor = conn.cursor()
        cursor.execute("SELECT status, updated_at FROM prostudio_voice_avatars WHERE avatar_key = %s", (key,))
        row = cursor.fetchone()
        if row and row[0] == "ready":
            cursor.close(); conn.close(); return
        cursor.execute("UPDATE prostudio_voice_avatars SET status='generating', updated_at=NOW(), error_text='' WHERE avatar_key=%s", (key,))
        conn.commit(); cursor.close(); conn.close()
        response = requests.post(
            f"{OPENAI_API_BASE}/images/generations",
            headers={"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"},
            json={"model": os.getenv("VOICE_AVATAR_IMAGE_MODEL", "gpt-image-2"), "prompt": _voice_avatar_prompt(provider, voice_id, seed), "size": "1024x1024", "quality": os.getenv("VOICE_AVATAR_IMAGE_QUALITY", "medium"), "n": 1},
            timeout=int(os.getenv("VOICE_AVATAR_IMAGE_TIMEOUT", "180")),
        )
        data = response.json()
        if not response.ok:
            raise RuntimeError(raw_error_text(data) or f"OpenAI image HTTP {response.status_code}")
        image_item = (data.get("data") or [{}])[0]
        if image_item.get("b64_json"):
            image_bytes = base64.b64decode(image_item["b64_json"])
        elif image_item.get("url"):
            download = requests.get(image_item["url"], timeout=120)
            download.raise_for_status(); image_bytes = download.content
        else:
            raise RuntimeError("OpenAI image response has no image")
        avatar_path = storage_put_bytes(image_bytes, generated_key("voice-avatars", f"{key}.png"), "image/png")
        conn = db_connect(DATABASE_URL); cursor = conn.cursor()
        cursor.execute("""
            UPDATE prostudio_voice_avatars SET image_data=%s, content_type='image/png', avatar_path=%s,
            status='ready', error_text='', updated_at=NOW() WHERE avatar_key=%s
        """, (psycopg2.Binary(image_bytes), avatar_path, key))
        conn.commit(); cursor.close(); conn.close()
    except Exception as exc:
        print("VOICE AVATAR GENERATION FAILED:", {"provider": provider, "voice_id": voice_id, "error": str(exc)})
        if DATABASE_URL:
            try:
                conn = db_connect(DATABASE_URL); cursor = conn.cursor()
                cursor.execute("UPDATE prostudio_voice_avatars SET status='failed', error_text=%s, updated_at=NOW() WHERE avatar_key=%s", (str(exc)[:1000], key))
                conn.commit(); cursor.close(); conn.close()
            except Exception:
                pass
    finally:
        with VOICE_AVATAR_IN_FLIGHT_LOCK:
            VOICE_AVATAR_IN_FLIGHT.discard(key)


def schedule_voice_avatar(provider: str, voice_id: str) -> str:
    result = schedule_voice_avatars_batch([{"provider": provider, "voice_id": voice_id}])
    return result.get(_voice_avatar_identity(provider, voice_id)[0], "")


def schedule_voice_avatars_batch(voices: list) -> dict:
    normalized_items = []
    for item in voices or []:
        if not isinstance(item, dict):
            continue
        provider = str(item.get("provider") or "unknown").strip().lower()
        voice_id = str(item.get("voice_id") or item.get("voiceId") or item.get("id") or item.get("name") or "").strip()
        if voice_id:
            key, seed = _voice_avatar_identity(provider, voice_id)
            normalized_items.append((provider, voice_id, key, seed))
    if not normalized_items or not DATABASE_URL or not VOICE_AVATAR_AUTO_GENERATION:
        return {}
    ensure_prostudio_table()
    conn = db_connect(DATABASE_URL); cursor = conn.cursor()
    for provider, voice_id, key, seed in normalized_items:
        cursor.execute("""
            INSERT INTO prostudio_voice_avatars (provider, voice_id, seed, avatar_key, avatar_path, status)
            VALUES (%s,%s,%s,%s,%s,'pending') ON CONFLICT DO NOTHING
        """, (provider, voice_id, seed, key, f"/api/public/prostudio/voice-avatar/{key}"))
    keys = list(dict.fromkeys(item[2] for item in normalized_items))
    cursor.execute("SELECT avatar_key, status, updated_at < NOW() - INTERVAL '1 hour' FROM prostudio_voice_avatars WHERE avatar_key = ANY(%s)", (keys,))
    rows = {row[0]: (row[1], row[2]) for row in cursor.fetchall()}
    conn.commit(); cursor.close(); conn.close()
    ready = {}
    for provider, voice_id, key, _seed in normalized_items:
        row = rows.get(key)
        if row and row[0] == "ready":
            ready[key] = f"/api/public/prostudio/voice-avatar/{key}"
            continue
        should_retry = bool(row and (row[0] == "pending" or (row[0] in {"failed", "generating"} and row[1])))
        if should_retry:
            with VOICE_AVATAR_IN_FLIGHT_LOCK:
                if key not in VOICE_AVATAR_IN_FLIGHT:
                    VOICE_AVATAR_IN_FLIGHT.add(key)
                    VOICE_AVATAR_EXECUTOR.submit(_generate_voice_avatar_once, provider, voice_id)
    return ready


def voice_avatar_url_for(voice_id: str, provider: str = "") -> str:
    raw_voice_id = str(voice_id or "").strip()
    raw_provider = str(provider or "").strip()
    if not raw_voice_id:
        return ""
    normalized_voice = raw_voice_id.lower()
    normalized_slug = re.sub(r"[^a-z0-9]+", "_", normalized_voice).strip("_")
    normalized_provider = raw_provider.lower()
    for item in load_voice_avatar_catalog().get("avatars", []):
        item_voice = str(item.get("voice_id") or item.get("id") or "").strip().lower()
        item_slug = re.sub(r"[^a-z0-9]+", "_", item_voice).strip("_")
        item_provider = str(item.get("provider") or "").strip().lower()
        if normalized_provider and item_provider and item_provider != normalized_provider:
            continue
        if item_voice == normalized_voice or item_slug == normalized_slug:
            return str(item.get("avatarUrl") or "")
    return ""

def attach_voice_avatars(voices: list, provider: str = "") -> list:
    catalog = load_voice_avatar_catalog().get("avatars", [])
    avatar_lookup = {}
    for avatar in catalog:
        avatar_voice = str(avatar.get("voice_id") or avatar.get("id") or "").strip().lower()
        avatar_provider = str(avatar.get("provider") or "").strip().lower()
        url = str(avatar.get("avatarUrl") or avatar.get("avatar_url") or "")
        if avatar_voice and url:
            avatar_lookup[(avatar_provider, avatar_voice)] = url
            avatar_lookup.setdefault(("", avatar_voice), url)
    result = []
    missing = []
    for item in voices or []:
        if not isinstance(item, dict):
            result.append(item)
            continue
        voice_id = item.get("voice_id") or item.get("voiceId") or item.get("id") or item.get("name")
        resolved_provider = provider or str(item.get("provider") or "")
        avatar_url = item.get("avatarUrl") or item.get("avatar_url") or avatar_lookup.get((resolved_provider.lower(), str(voice_id or "").strip().lower())) or avatar_lookup.get(("", str(voice_id or "").strip().lower()))
        if not avatar_url:
            missing.append({"provider": resolved_provider, "voice_id": voice_id})
        next_item = dict(item)
        if avatar_url:
            next_item["avatarUrl"] = avatar_url
            next_item["avatar_url"] = avatar_url
        result.append(next_item)
    if missing:
        schedule_voice_avatars_batch(missing)
    return result

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_API_BASE = os.getenv("OPENAI_API_BASE", "https://api.openai.com/v1").rstrip("/")
RUNWAY_API_BASE_URL = os.getenv("RUNWAY_API_BASE_URL", "https://api.dev.runwayml.com").rstrip("/")
RUNWAY_API_VERSION = os.getenv("RUNWAY_API_VERSION", "2024-11-06")
BYTEPLUS_ARK_API_KEY = os.getenv("BYTEPLUS_ARK_API_KEY")
BYTEPLUS_ARK_ENDPOINT = os.getenv("BYTEPLUS_ARK_ENDPOINT", "https://ark.ap-southeast.bytepluses.com/api/v3").rstrip("/")
BYTEPLUS_SEEDREAM_MODEL_MAP = {
    "seedream_5_0_lite": env_value("BYTEPLUS_SEEDREAM_5_LITE_MODEL", "BYTEPLUS-SEEDREAM-5-LITE-MODEL", default="seedream-5-0-260128"),
    "seedream_5_0": os.getenv("BYTEPLUS_SEEDREAM_5_MODEL", "seedream-5-0-260128"),
    "seedream_5_0_pro": env_value("BYTEPLUS_SEEDREAM_5_PRO_MODEL", "BYTEPLUS-SEEDREAM-5-PRO-MODEL", default="dola-seedream-5-0-pro-260628"),
    "seedream_4_5": os.getenv("BYTEPLUS_SEEDREAM_4_5_MODEL", "seedream-4-5-251128"),
    "seedream_4_0": os.getenv("BYTEPLUS_SEEDREAM_4_MODEL", "seedream-4-0-250828"),
    "seedream-5-0-lite-260128": os.getenv("BYTEPLUS_SEEDREAM_5_LITE_MODEL", "seedream-5-0-260128"),
    "seedream-5-0-260128": os.getenv("BYTEPLUS_SEEDREAM_5_MODEL", "seedream-5-0-260128"),
    "dola-seedream-5-0-pro-260628": os.getenv("BYTEPLUS_SEEDREAM_5_PRO_MODEL", "dola-seedream-5-0-pro-260628"),
    "seedream-4-5-251128": os.getenv("BYTEPLUS_SEEDREAM_4_5_MODEL", "seedream-4-5-251128"),
    "seedream-4-0-250828": os.getenv("BYTEPLUS_SEEDREAM_4_MODEL", "seedream-4-0-250828"),
}

IMAGE_PROVIDER_MODEL_MAP = {
    "ideogram_3_0": {"provider": "ideogram", "provider_model": env_value("IDEOGRAM_3_MODEL", "IDEOGRAM-3-MODEL", default="ideogram-v3"), "endpoint": "https://api.ideogram.ai/v1/ideogram-v3/generate"},
    "ideogram_4_0": {"provider": "ideogram", "provider_model": env_value("IDEOGRAM_4_MODEL", "IDEOGRAM-4-MODEL", default="ideogram-v4"), "endpoint": "https://api.ideogram.ai/v1/ideogram-v4/generate"},
    "recraft_v4_1": {"provider": "recraft", "provider_model": env_value("RECRAFT_V4_1_MODEL", "RECRAFT-V4-1-MODEL", default="recraftv4_1"), "endpoint": "https://external.api.recraft.ai/v1/images/generations"},
    "recraft_v3": {"provider": "recraft", "provider_model": env_value("RECRAFT_V3_MODEL", "RECRAFT-V3-MODEL", default="recraftv3"), "endpoint": "https://external.api.recraft.ai/v1/images/generations"},
    "recraft_v4_1_pro": {"provider": "recraft", "provider_model": env_value("RECRAFT_V4_1_PRO_MODEL", "RECRAFT-V4-1-PRO-MODEL", default="recraftv4_1_pro"), "endpoint": "https://external.api.recraft.ai/v1/images/generations"},
    "seedream_4_0": {"provider": "bytedance", "provider_model": BYTEPLUS_SEEDREAM_MODEL_MAP["seedream_4_0"], "endpoint": f"{BYTEPLUS_ARK_ENDPOINT}/images/generations"},
    "seedream_5_0": {"provider": "bytedance", "provider_model": BYTEPLUS_SEEDREAM_MODEL_MAP["seedream_5_0"], "endpoint": f"{BYTEPLUS_ARK_ENDPOINT}/images/generations"},
    "seedream_5_0_lite": {"provider": "bytedance", "provider_model": BYTEPLUS_SEEDREAM_MODEL_MAP["seedream_5_0_lite"], "endpoint": f"{BYTEPLUS_ARK_ENDPOINT}/images/generations"},
    "seedream_5_0_pro": {"provider": "bytedance", "provider_model": BYTEPLUS_SEEDREAM_MODEL_MAP["seedream_5_0_pro"], "endpoint": f"{BYTEPLUS_ARK_ENDPOINT}/images/generations"},
    "seedream_4_5": {"provider": "bytedance", "provider_model": BYTEPLUS_SEEDREAM_MODEL_MAP["seedream_4_5"], "endpoint": f"{BYTEPLUS_ARK_ENDPOINT}/images/generations"},
    "gpt_image_1": {"provider": "openai", "provider_model": "gpt-image-1", "endpoint": f"{OPENAI_API_BASE}/images/generations"},
    "gpt_image_2": {"provider": "openai", "provider_model": "gpt-image-2", "endpoint": f"{OPENAI_API_BASE}/images/generations"},
    "flux_pro_kontext": {"provider": "flux", "provider_model": env_value("FLUX_PRO_KONTEXT_MODEL", "FLUX-PRO-KONTEXT-MODEL", default="flux-kontext-pro"), "endpoint": "https://api.bfl.ai/v1"},
    "flux_2": {"provider": "flux", "provider_model": env_value("FLUX_2_MODEL", "FLUX-2-MODEL", default="flux-2-pro"), "endpoint": "https://api.bfl.ai/v1"},
    "flux_2_turbo": {"provider": "flux", "provider_model": env_value("FLUX_2_TURBO_MODEL", "FLUX-2-TURBO-MODEL", default="flux-2-flex"), "endpoint": "https://api.bfl.ai/v1"},
    "qwen_image": {"provider": "qwen", "provider_model": env_value("QWEN_IMAGE_MODEL", "QWEN-IMAGE-MODEL", default="qwen-image"), "endpoint": env_value("QWEN_IMAGE_ENDPOINT", "QWEN-IMAGE-ENDPOINT", default="https://dashscope-intl.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation")},
    "qwen_image_2_pro": {"provider": "qwen", "provider_model": env_value("QWEN_IMAGE_2_PRO_MODEL", "QWEN-IMAGE-2-PRO-MODEL", default="qwen-image-2.0-pro"), "endpoint": env_value("QWEN_IMAGE_ENDPOINT", "QWEN-IMAGE-ENDPOINT", default="https://dashscope-intl.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation")},
    "qwen_image_2": {"provider": "qwen", "provider_model": env_value("QWEN_IMAGE_2_MODEL", "QWEN-IMAGE-2-MODEL", default="qwen-image-2.0"), "endpoint": env_value("QWEN_IMAGE_ENDPOINT", "QWEN-IMAGE-ENDPOINT", default="https://dashscope-intl.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation")},
    "nano_banana_pro": {"provider": "google", "provider_model": env_value("NANO_BANANA_PRO_MODEL", "NANO-BANANA-PRO-MODEL", default="gemini-3-pro-image"), "endpoint": env_value("GOOGLE_IMAGE_ENDPOINT", "GOOGLE-IMAGE-ENDPOINT", default="https://generativelanguage.googleapis.com/v1beta/interactions")},
    "nano_banana_2": {"provider": "google", "provider_model": env_value("NANO_BANANA_2_MODEL", "NANO-BANANA-2-MODEL", default="gemini-3.1-flash-image"), "endpoint": env_value("GOOGLE_IMAGE_ENDPOINT", "GOOGLE-IMAGE-ENDPOINT", default="https://generativelanguage.googleapis.com/v1beta/interactions")},
    "nano_banana_2_lite": {"provider": "google", "provider_model": env_value("NANO_BANANA_2_LITE_MODEL", "NANO-BANANA-2-LITE-MODEL", default="gemini-3.1-flash-lite-image"), "endpoint": env_value("GOOGLE_IMAGE_ENDPOINT", "GOOGLE-IMAGE-ENDPOINT", default="https://generativelanguage.googleapis.com/v1beta/interactions")},
    "nano_banana": {"provider": "google", "provider_model": env_value("NANO_BANANA_MODEL", "NANO-BANANA-MODEL", default="gemini-2.5-flash-image"), "endpoint": env_value("GOOGLE_IMAGE_ENDPOINT", "GOOGLE-IMAGE-ENDPOINT", default="https://generativelanguage.googleapis.com/v1beta/interactions")},
    "gemini-3.1-flash-image": {"provider": "google", "provider_model": env_value("NANO_BANANA_2_MODEL", "NANO-BANANA-2-MODEL", default="gemini-3.1-flash-image"), "endpoint": env_value("GOOGLE_IMAGE_ENDPOINT", "GOOGLE-IMAGE-ENDPOINT", default="https://generativelanguage.googleapis.com/v1beta/interactions")},
    "gemini-3.1-flash-lite-image": {"provider": "google", "provider_model": env_value("NANO_BANANA_2_LITE_MODEL", "NANO-BANANA-2-LITE-MODEL", default="gemini-3.1-flash-lite-image"), "endpoint": env_value("GOOGLE_IMAGE_ENDPOINT", "GOOGLE-IMAGE-ENDPOINT", default="https://generativelanguage.googleapis.com/v1beta/interactions")},
    "gemini-3-pro-image": {"provider": "google", "provider_model": env_value("NANO_BANANA_PRO_MODEL", "NANO-BANANA-PRO-MODEL", default="gemini-3-pro-image"), "endpoint": env_value("GOOGLE_IMAGE_ENDPOINT", "GOOGLE-IMAGE-ENDPOINT", default="https://generativelanguage.googleapis.com/v1beta/interactions")},
    "gemini-2.5-flash-image": {"provider": "google", "provider_model": env_value("NANO_BANANA_MODEL", "NANO-BANANA-MODEL", default="gemini-2.5-flash-image"), "endpoint": env_value("GOOGLE_IMAGE_ENDPOINT", "GOOGLE-IMAGE-ENDPOINT", default="https://generativelanguage.googleapis.com/v1beta/interactions")},
    "imagen_4_fast": {"provider": "google", "provider_model": env_value("IMAGEN_4_FAST_MODEL", "IMAGEN-4-FAST-MODEL", default="imagen-4.0-fast-generate-001"), "endpoint": "https://generativelanguage.googleapis.com/v1beta/models/{model}:predict"},
    "imagen_4_standard": {"provider": "google", "provider_model": env_value("IMAGEN_4_STANDARD_MODEL", "IMAGEN-4-STANDARD-MODEL", default="imagen-4.0-generate-001"), "endpoint": "https://generativelanguage.googleapis.com/v1beta/models/{model}:predict"},
    "imagen_4_ultra": {"provider": "google", "provider_model": env_value("IMAGEN_4_ULTRA_MODEL", "IMAGEN-4-ULTRA-MODEL", default="imagen-4.0-ultra-generate-001"), "endpoint": "https://generativelanguage.googleapis.com/v1beta/models/{model}:predict"},
    "imagen-4.0-fast-generate-001": {"provider": "google", "provider_model": env_value("IMAGEN_4_FAST_MODEL", "IMAGEN-4-FAST-MODEL", default="imagen-4.0-fast-generate-001"), "endpoint": "https://generativelanguage.googleapis.com/v1beta/models/{model}:predict"},
    "imagen-4.0-generate-001": {"provider": "google", "provider_model": env_value("IMAGEN_4_STANDARD_MODEL", "IMAGEN-4-STANDARD-MODEL", default="imagen-4.0-generate-001"), "endpoint": "https://generativelanguage.googleapis.com/v1beta/models/{model}:predict"},
    "imagen-4.0-ultra-generate-001": {"provider": "google", "provider_model": env_value("IMAGEN_4_ULTRA_MODEL", "IMAGEN-4-ULTRA-MODEL", default="imagen-4.0-ultra-generate-001"), "endpoint": "https://generativelanguage.googleapis.com/v1beta/models/{model}:predict"},
    "grok_pro": {"provider": "grok", "provider_model": env_value("GROK_IMAGE_PRO_MODEL", "GROK-IMAGE-PRO-MODEL", default="grok-imagine-image-quality"), "endpoint": env_value("XAI_IMAGE_ENDPOINT", "XAI-IMAGE-ENDPOINT", default="https://api.x.ai/v1/images/generations")},
    "grok": {"provider": "grok", "provider_model": env_value("GROK_IMAGE_MODEL", "GROK-IMAGE-MODEL", default="grok-imagine-image"), "endpoint": env_value("XAI_IMAGE_ENDPOINT", "XAI-IMAGE-ENDPOINT", default="https://api.x.ai/v1/images/generations")},
    "grok_imagine_image_quality": {"provider": "grok", "provider_model": env_value("GROK_IMAGE_PRO_MODEL", "GROK-IMAGE-PRO-MODEL", default="grok-imagine-image-quality"), "endpoint": env_value("XAI_IMAGE_ENDPOINT", "XAI-IMAGE-ENDPOINT", default="https://api.x.ai/v1/images/generations")},
    "grok_imagine_image": {"provider": "grok", "provider_model": env_value("GROK_IMAGE_MODEL", "GROK-IMAGE-MODEL", default="grok-imagine-image"), "endpoint": env_value("XAI_IMAGE_ENDPOINT", "XAI-IMAGE-ENDPOINT", default="https://api.x.ai/v1/images/generations")},
   
}
IDEOGRAM_MODEL_VARIANTS = {
    "ideogram_3_0": {
        "rendering_speed": env_value("IDEOGRAM_3_RENDERING_SPEED", "IDEOGRAM-3-RENDERING-SPEED", default="TURBO").upper(),
        "provider_model": env_value("IDEOGRAM_3_MODEL", "IDEOGRAM-3-MODEL", default="ideogram-v3"),
        "label_prefix": "Ideogram 3.0",
        "seed": True,
        "cost_usd": {
            "FLASH": 0.045,
            "TURBO": 0.045,
            "DEFAULT": 0.090,
            "QUALITY": 0.135,
            "TURBO_CHARACTER": 0.150,
            "DEFAULT_CHARACTER": 0.225,
            "QUALITY_CHARACTER": 0.300,
        },
        "cost_credits": {
            "FLASH": 5,
            "TURBO": 5,
            "DEFAULT": 9,
            "QUALITY": 14,
            "TURBO_CHARACTER": 15,
            "DEFAULT_CHARACTER": 23,
            "QUALITY_CHARACTER": 30,
        },
    },
    "ideogram_4_0": {
        "rendering_speed": env_value("IDEOGRAM_4_RENDERING_SPEED", "IDEOGRAM-4-RENDERING-SPEED", default="TURBO").upper(),
        "provider_model": env_value("IDEOGRAM_4_MODEL", "IDEOGRAM-4-MODEL", default="ideogram-v4"),
        "label_prefix": "Ideogram 4.0",
        "seed": False,
        "cost_usd": {
            "TURBO": 0.045,
            "DEFAULT": 0.090,
            "QUALITY": 0.150,
        },
        "cost_credits": {
            "TURBO": 5,
            "DEFAULT": 9,
            "QUALITY": 15,
        },
    },
}
OPENAI_IMAGE_MODEL_VARIANTS = {
    "gpt_image_1": {
        "provider_model": "gpt-image-1",
        "label": "GPT Image 1",
        "seed": False,
        "default_quality": env_value("GPT_IMAGE_1_QUALITY", "GPT-IMAGE-1-QUALITY", default="medium"),
        "cost_credits": {"low": 2, "medium": 7, "high": 26},
        "cost_usd": {"low": 0.0165, "medium": 0.063, "high": 0.2505},
    },
    "gpt_image_2": {
        "provider_model": "gpt-image-2",
        "label": "GPT Image 2",
        "seed": False,
        "default_quality": env_value("GPT_IMAGE_2_QUALITY", "GPT-IMAGE-2-QUALITY", default="medium"),
        "cost_credits": {"low": 1, "medium": 8, "high": 32},
        "cost_usd": {"low": 0.009, "medium": 0.0795, "high": 0.3165},
    },
}
RECRAFT_MODEL_VARIANTS = {
    "recraft_v4_1": {
        "provider_model": env_value("RECRAFT_V4_1_MODEL", "RECRAFT-V4-1-MODEL", default="recraftv4_1"),
        "label": "Recraft V4.1",
        "seed": True,
        "cost_credits": 6,
        "cost_usd": 0.0525,
        "provider_cost_usd": 0.035,
        "tools": ["image_to_image"],
    },
    "recraft_v4_1_pro": {
        "provider_model": env_value("RECRAFT_V4_1_PRO_MODEL", "RECRAFT-V4-1-PRO-MODEL", default="recraftv4_1_pro"),
        "label": "Recraft V4.1 Pro",
        "seed": False,
        "cost_credits": 21,
        "cost_usd": 0.21,
        "provider_cost_usd": 0.21,
        "tools": ["image_to_image"],
    },
    "recraft_v3": {
        "provider_model": env_value("RECRAFT_V3_MODEL", "RECRAFT-V3-MODEL", default="recraftv3"),
        "label": "Recraft V3",
        "seed": True,
        "cost_credits": 6,
        "cost_usd": 0.06,
        "provider_cost_usd": 0.04,
        "tools": [
            "image_to_image",
            "outpaint",
            "replace_background",
            "generate_background",
            "create_style",
            "vectorize",
            "remove_background",
            "crisp_upscale",
            "creative_upscale",
            "erase_region",
        ],
    },
}
SEEDREAM_MODEL_VARIANTS = {
    "seedream_5_0_lite": {
        "provider_model": BYTEPLUS_SEEDREAM_MODEL_MAP["seedream_5_0_lite"],
        "label": "Seedream 5.0 Lite",
        "seed": True,
        "cost_credits": 6,
        "cost_usd": 0.0525,
    },
    "seedream_5_0": {
        "provider_model": BYTEPLUS_SEEDREAM_MODEL_MAP["seedream_5_0"],
        "label": "Seedream 5.0 Lite",
        "seed": True,
        "cost_credits": 6,
        "cost_usd": 0.0525,
    },
    "seedream_4_5": {
        "provider_model": BYTEPLUS_SEEDREAM_MODEL_MAP["seedream_4_5"],
        "label": "Seedream 4.5",
        "seed": True,
        "cost_credits": 6,
        "cost_usd": 0.06,
    },
    "seedream_5_0_pro": {
        "provider_model": BYTEPLUS_SEEDREAM_MODEL_MAP["seedream_5_0_pro"],
        "label": "Seedream 5.0 Pro",
        "seed": True,
        "cost_credits": 7,
        "cost_usd": 0.0675,
    },
    "seedream_4_0": {
        "provider_model": BYTEPLUS_SEEDREAM_MODEL_MAP["seedream_4_0"],
        "label": "Seedream 4.0",
        "seed": True,
        "cost_credits": 6,
        "cost_usd": 0.0525,
    },
}
FLUX_MODEL_VARIANTS = {
    "flux_pro_kontext": {
        "provider_model": env_value("FLUX_PRO_KONTEXT_MODEL", "FLUX-PRO-KONTEXT-MODEL", default="flux-kontext-pro"),
        "label": "FLUX Pro Text",
        "seed": False,
        "cost_credits": 6,
        "cost_usd": 0.06,
    },
    "flux_2": {
        "provider_model": env_value("FLUX_2_MODEL", "FLUX-2-MODEL", default="flux-2-pro"),
        "label": "FLUX.2",
        "seed": False,
        "cost_credits": 5,
        "cost_usd": 0.045,
    },
    "flux_2_turbo": {
        "provider_model": env_value("FLUX_2_TURBO_MODEL", "FLUX-2-TURBO-MODEL", default="flux-2-flex"),
        "label": "FLUX.2 Turbo",
        "seed": False,
        "cost_credits": 11,
        "cost_usd": 0.105,
    },
}
QWEN_MODEL_VARIANTS = {
    "qwen_image_2_pro": {
        "label": "Qwen Image 2 Pro",
        "seed": True,
        "cost_credits": 12,
        "cost_usd": 0.1125,
    },
    "qwen_image_2": {
        "label": "Qwen Image 2",
        "seed": True,
        "cost_credits": 6,
        "cost_usd": 0.0525,
    },
    "qwen_image": {
        "label": "Qwen Image",
        "seed": False,
        "cost_credits": 7,
        "cost_usd": 0.0675,
    },
}
GOOGLE_IMAGE_MODEL_VARIANTS = {
    "nano_banana_2": {
        "provider_model": env_value("NANO_BANANA_2_MODEL", "NANO-BANANA-2-MODEL", default="gemini-3.1-flash-image"),
        "label": "Nano Banana 2",
        "seed": False,
        "cost_credits": {"0.5k": 7, "1k": 11, "2k": 16, "4k": 23},
        "default_resolution": "1k",
    },
    "nano_banana_2_lite": {
        "provider_model": env_value("NANO_BANANA_2_LITE_MODEL", "NANO-BANANA-2-LITE-MODEL", default="gemini-3.1-flash-lite-image"),
        "label": "Nano Banana 2 Lite",
        "seed": False,
        "cost_credits": {"1k": 6},
        "default_resolution": "1k",
    },
    "nano_banana_pro": {
        "provider_model": env_value("NANO_BANANA_PRO_MODEL", "NANO-BANANA-PRO-MODEL", default="gemini-3-pro-image"),
        "label": "Nano Banana Pro",
        "seed": False,
        "cost_credits": {"1k": 21, "2k": 21, "4k": 36},
        "default_resolution": "1k",
    },
    "nano_banana": {
        "provider_model": env_value("NANO_BANANA_MODEL", "NANO-BANANA-MODEL", default="gemini-2.5-flash-image"),
        "label": "Nano Banana",
        "seed": False,
        "cost_credits": {"1k": 6},
        "default_resolution": "1k",
    },
    "imagen_4_fast": {
        "provider_model": env_value("IMAGEN_4_FAST_MODEL", "IMAGEN-4-FAST-MODEL", default="imagen-4.0-fast-generate-001"),
        "label": "Imagen 4 Fast",
        "seed": False,
        "cost_credits": {"1k": 3},
        "default_resolution": "1k",
        "imagen": True,
    },
    "imagen_4_standard": {
        "provider_model": env_value("IMAGEN_4_STANDARD_MODEL", "IMAGEN-4-STANDARD-MODEL", default="imagen-4.0-generate-001"),
        "label": "Imagen 4 Standard",
        "seed": False,
        "cost_credits": {"1k": 6, "2k": 6},
        "default_resolution": "1k",
        "imagen": True,
    },
    "imagen_4_ultra": {
        "provider_model": env_value("IMAGEN_4_ULTRA_MODEL", "IMAGEN-4-ULTRA-MODEL", default="imagen-4.0-ultra-generate-001"),
        "label": "Imagen 4 Ultra",
        "seed": False,
        "cost_credits": {"1k": 9, "2k": 9},
        "default_resolution": "1k",
        "imagen": True,
    },
}
GROK_MODEL_VARIANTS = {
    "grok": {
        "provider_model": env_value("GROK_IMAGE_MODEL", "GROK-IMAGE-MODEL", default="grok-imagine-image"),
        "label": "Grok",
        "seed": False,
        "cost_credits": {"1k": 3, "2k": 3},
        "input_image_credits": 1,
        "input_image_surcharge_provisional": True,
    },
    "grok_pro": {
        "provider_model": env_value("GROK_IMAGE_PRO_MODEL", "GROK-IMAGE-PRO-MODEL", default="grok-imagine-image-quality"),
        "label": "Grok Pro",
        "seed": False,
        "cost_credits": {"1k": 8, "2k": 11},
        "input_image_credits": 2,
        "input_image_surcharge_provisional": True,
    },
}
RECRAFT_TOOL_CATALOG = {
    "image_to_image": {"label": "Изображение → Изображение", "raster_credits": 6, "vector_credits": 12, "endpoint": "/images/imageToImage"},
    "outpaint": {"label": "Дорисовка изображения", "raster_credits": 6, "vector_credits": 12, "endpoint": "/images/outpaint"},
    "replace_background": {"label": "Замена фона", "raster_credits": 6, "vector_credits": 12, "endpoint": "/images/replaceBackground"},
    "generate_background": {"label": "Генерация фона", "raster_credits": 6, "vector_credits": 12, "endpoint": "/images/generateBackground"},
    "create_style": {"label": "Генерация стиля", "raster_credits": 6, "endpoint": "/styles"},
    "vectorize": {"label": "Векторизация", "raster_credits": 2, "endpoint": "/images/vectorize"},
    "remove_background": {"label": "Удаление фона", "raster_credits": 2, "endpoint": "/images/removeBackground"},
    "crisp_upscale": {"label": "Увеличение разрешения", "raster_credits": 1, "endpoint": "/images/crispUpscale"},
    "creative_upscale": {"label": "Повышение качества", "raster_credits": 38, "endpoint": "/images/creativeUpscale"},
    "erase_region": {"label": "Стирание области", "raster_credits": 1, "endpoint": "/images/eraseRegion"},
}
IMAGE_MODEL_FEATURES = {
    "nano_banana_pro": {"character": True, "object": True, "seed": False},
    "nano_banana_2": {"character": False, "object": False, "seed": False},
    "nano_banana_2_lite": {"character": False, "object": False, "seed": False},
    "nano_banana": {"character": True, "object": True, "seed": False},
    "imagen_4_fast": {"character": False, "object": False, "seed": False},
    "imagen_4_standard": {"character": False, "object": False, "seed": False},
    "imagen_4_ultra": {"character": False, "object": False, "seed": False},
    "gpt_image_2": {"character": True, "object": True, "seed": False},
    "seedream_5_0_lite": {"character": True, "object": True, "seed": True},
    "seedream_5_0": {"character": True, "object": True, "seed": True},
    "seedream_5": {"character": True, "object": True, "seed": True},
    "seedream_5_0_pro": {"character": True, "object": True, "seed": True},
    "seedream_5_pro": {"character": True, "object": True, "seed": True},
    "seedream_4_5": {"character": True, "object": True, "seed": True},
    "seedream_4_0": {"character": True, "object": True, "seed": True},
    "seedream_4": {"character": True, "object": True, "seed": True},
    "grok_pro": {"character": False, "object": False, "seed": False},
    "grok": {"character": False, "object": False, "seed": False},
    "flux_2": {"character": True, "object": True, "seed": False},
    "flux_2_turbo": {"character": True, "object": True, "seed": False},
    "flux_pro_kontext": {"character": True, "object": False, "seed": False},
    "ideogram_3_0": {"character": False, "object": False, "seed": True},
    "ideogram_3": {"character": False, "object": False, "seed": True},
    "ideogram_4_0": {"character": False, "object": False, "seed": False},
    "ideogram_4": {"character": False, "object": False, "seed": False},
    "recraft_v4_1": {"character": False, "object": False, "seed": True},
    "recraft_v3": {"character": False, "object": False, "seed": True},
    "recraft_v4_1_pro": {"character": False, "object": False, "seed": False},
    "gpt_image_1": {"character": True, "object": True, "seed": False},
    "qwen_image": {"character": False, "object": False, "seed": False},
    "qwen_image_2": {"character": False, "object": False, "seed": True},
    "qwen_image_2_pro": {"character": False, "object": False, "seed": True},
    "krea_2": {"character": False, "object": False},
    "microsoft_mai_image_2_5": {"character": False, "object": False},
}
IMAGE_MODELS_JSON = os.getenv("IMAGE_MODELS_JSON")
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY") or os.getenv("ELEVENLABS-API-KEY")
ELEVENLABS_BASE_URL = "https://api.elevenlabs.io"
ELEVENLABS_DEFAULT_VOICE_ID = "21m00Tcm4TlvDq8ikWAM"
ELEVENLABS_DEFAULT_VOICE_NAME = "Rachel"
ELEVENLABS_DEFAULT_MODEL_ID = "eleven_multilingual_v2"
ELEVENLABS_DEFAULT_OUTPUT_FORMAT = "mp3_44100_128"
HEYGEN_API_KEY = os.getenv("HEYGEN_API_KEY")
PAYPAL_CLIENT_ID = os.getenv("PAYPAL_CLIENT_ID")
PAYPAL_CLIENT_SECRET = os.getenv("PAYPAL_CLIENT_SECRET")
PAYPAL_MODE = (os.getenv("PAYPAL_MODE") or "sandbox").strip().lower()
PAYPAL_WEBHOOK_ID = os.getenv("PAYPAL_WEBHOOK_ID")
PAYPAL_API_BASE = "https://api-m.paypal.com" if PAYPAL_MODE == "live" else "https://api-m.sandbox.paypal.com"
PAYPAL_PRO_MONTHLY_PLAN_ID = os.getenv("PAYPAL_PRO_MONTHLY_PLAN_ID", "P-2JN99488MP781262CNJDGCZI")
PAYPAL_PRO_YEARLY_PLAN_ID = os.getenv("PAYPAL_PRO_YEARLY_PLAN_ID", "P-0YT1496917791881BNJDGRMY")
CRYPTO_API_KEY = os.getenv("CRYPTO_API_KEY") or os.getenv("CRIPTO_API_KEY")
CRYPTO_PAY_API_URL = "https://pay.crypt.bot/api"
HEYGEN_BASE_URL = "https://api.heygen.com/v3"
HEYGEN_VOICE_MODEL_ID = "starfish"
HEYGEN_DEFAULT_LANGUAGE = "ru"
HEYGEN_DEFAULT_SPEED = 1.0
HEYGEN_DEFAULT_OUTPUT_FORMAT = "mp3"
DEV_TELEGRAM_ID = int(os.getenv("DEV_TELEGRAM_ID", "7932380565"))
SUBSCRIPTION_BONUS_CREDITS = int(os.getenv("SUBSCRIPTION_BONUS_CREDITS", "100"))

SHOP_ITEMS = {
    "sub_month": {
        "kind": "subscription",
        "title": "SYLVEX Pro · 1 месяц",
        "plan_key": "month",
        "days": 30,
        "credits": 0,
        "bonus_credits": SUBSCRIPTION_BONUS_CREDITS,
        "usd": 5.0,
        "stars": 230,
    },
    "sub_year": {
        "kind": "subscription",
        "title": "SYLVEX Pro · 1 год",
        "plan_key": "year",
        "days": 365,
        "credits": 0,
        "bonus_credits": SUBSCRIPTION_BONUS_CREDITS,
        "usd": 59.0,
        "stars": 2751,
    },
    "pack_100": {"kind": "credits", "title": "100 ⚡", "credits": 100, "usd": 1.0, "stars": 46},
    "pack_500": {"kind": "credits", "title": "500 ⚡", "credits": 500, "usd": 5.0, "stars": 230},
    "pack_1000": {"kind": "credits", "title": "1000 ⚡", "credits": 1000, "usd": 10.0, "stars": 460},
    "pack_2000": {"kind": "credits", "title": "2000 ⚡", "credits": 2000, "usd": 20.0, "stars": 920},
    "pack_3000": {"kind": "credits", "title": "3000 ⚡", "credits": 3000, "usd": 30.0, "stars": 1380},
    "pack_4000": {"kind": "credits", "title": "4000 ⚡", "credits": 4000, "usd": 40.0, "stars": 1840},
    "pack_5000": {"kind": "credits", "title": "5000 ⚡", "credits": 5000, "usd": 50.0, "stars": 2300},
}


# =====================================================
# PYTHON-БЛОК: design
# Выполняет отдельный шаг backend-логики SYLVEX.
# Связан с API, базой данных, провайдерами или подготовкой данных для Mini App.
# =====================================================
def design(title: str, body: str) -> str:
    return f"""
<pre>
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🏷{title}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

{body}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🌐SYLVEX AI creator bot • top ai creation platform©️
</pre>
<a href="https://t.me/sylvexai_bot">Official Bot</a>
"""

# =====================================================
# PYTHON-БЛОК: shop_item
# Выполняет отдельный шаг backend-логики SYLVEX.
# Связан с API, базой данных, провайдерами или подготовкой данных для Mini App.
# =====================================================
def shop_item(pack_id: str):
    return SHOP_ITEMS.get((pack_id or "").strip())


# =====================================================
# PYTHON-БЛОК: shop_payload
# Выполняет отдельный шаг backend-логики SYLVEX.
# Связан с API, базой данных, провайдерами или подготовкой данных для Mini App.
# =====================================================
def shop_payload(provider: str, telegram_id: int, pack_id: str, item: dict) -> str:
    if item["kind"] == "subscription":
        return f"sylvex_{provider}_sub:{telegram_id}:{item['plan_key']}:{item['usd']:.2f}"
    return f"sylvex_{provider}_credits:{telegram_id}:{item['credits']}:{item['usd']:.2f}"


# =====================================================
# PYTHON-БЛОК: bot_stars_payload
# Выполняет отдельный шаг backend-логики SYLVEX.
# Связан с API, базой данных, провайдерами или подготовкой данных для Mini App.
# =====================================================
def bot_stars_payload(telegram_id: int, item: dict, charge_id: str = None) -> str:
    if item["kind"] == "subscription":
        payload = f"sylvex_sub:{telegram_id}:{item['plan_key']}:{item['stars']}"
    else:
        payload = f"sylvex_stars:{telegram_id}:{item['credits']}:{item['stars']}"
    if charge_id:
        payload = f"{payload}:{charge_id}"
    return payload


# =====================================================
# PYTHON-БЛОК: parse_shop_payload
# Выполняет отдельный шаг backend-логики SYLVEX.
# Связан с API, базой данных, провайдерами или подготовкой данных для Mini App.
# =====================================================
def parse_shop_payload(payload: str) -> dict:
    if not payload or not isinstance(payload, str):
        return {}

    parts = payload.split(":")
    if not parts:
        return {}

    result = {
        "kind": None,
        "provider": None,
        "telegram_id": 0,
        "plan_key": None,
        "credits": 0,
        "charge_id": None,
    }

    key = parts[0] or ""
    if key.startswith("sylvex_") and key.endswith("_sub"):
        result["kind"] = "subscription"
        result["provider"] = key[len("sylvex_"):-len("_sub")]
    elif key.startswith("sylvex_") and key.endswith("_credits"):
        result["kind"] = "credits"
        result["provider"] = key[len("sylvex_"):-len("_credits")]
    elif key == "sylvex_sub":
        result["kind"] = "subscription"
    elif key == "sylvex_stars":
        result["kind"] = "credits"
    else:
        return {}

    if len(parts) >= 2:
        try:
            result["telegram_id"] = int(parts[1] or 0)
        except Exception:
            result["telegram_id"] = 0

    if result["kind"] == "subscription":
        if len(parts) >= 3:
            result["plan_key"] = parts[2]
        if len(parts) >= 5:
            result["charge_id"] = parts[4]
    else:
        if len(parts) >= 3:
            try:
                result["credits"] = int(parts[2] or 0)
            except Exception:
                result["credits"] = 0
        if len(parts) >= 5:
            result["charge_id"] = parts[4]

    return result


# =====================================================
# PYTHON-БЛОК: _has_subscription_purchase
# Выполняет отдельный шаг backend-логики SYLVEX.
# Связан с API, базой данных, провайдерами или подготовкой данных для Mini App.
# =====================================================
def _has_subscription_purchase(telegram_id: int) -> bool:
    if not DATABASE_URL or not telegram_id:
        return False

    ensure_payment_tables()
    conn = db_connect(DATABASE_URL)
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT 1
            FROM purchases
            WHERE telegram_id = %s
              AND payload LIKE 'sylvex_%%sub:%%'
            LIMIT 1
        """, (telegram_id,))
        return cursor.fetchone() is not None
    finally:
        cursor.close()
        conn.close()


# =====================================================
# PYTHON-БЛОК: _restore_active_subscription
# Выполняет отдельный шаг backend-логики SYLVEX.
# Связан с API, базой данных, провайдерами или подготовкой данных для Mini App.
# =====================================================
def _restore_active_subscription(telegram_id: int) -> bool:
    if not DATABASE_URL or not telegram_id:
        return False

    ensure_payment_tables()
    conn = db_connect(DATABASE_URL)
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT provider, payload, amount, currency, charge_id, created_at
            FROM purchases
            WHERE telegram_id = %s
              AND payload LIKE 'sylvex_%%sub:%%'
            ORDER BY created_at DESC
            LIMIT 1
        """, (telegram_id,))
        row = cursor.fetchone()
    finally:
        cursor.close()
        conn.close()

    item = SHOP_ITEMS.get("sub_month")
    charge_id = None
    provider = "recovery"
    amount = 0
    currency = "REC"
    payload = None

    if row:
        payload_str = row[1] or ""
        parsed = parse_shop_payload(payload_str)
        plan_key = parsed.get("plan_key") or "month"
        item = SHOP_ITEMS.get(f"sub_{plan_key}") or SHOP_ITEMS.get("sub_month")
        charge_id = row[4] or f"recovery_sub_{telegram_id}_{int(row[5].timestamp()) if row[5] else 0}"
        provider = row[0] or "telegram_stars"
        amount = row[2] or 0
        currency = row[3] or "USD"
        payload = payload_str
    else:
        item = SHOP_ITEMS.get("sub_month")
        charge_id = f"recovery_sub_month_{telegram_id}"
        payload = bot_stars_payload(telegram_id, item, charge_id)

    if not item or not charge_id:
        return False

    inserted = activate_subscription(
        telegram_id=telegram_id,
        item=item,
        provider=provider,
        amount=amount,
        currency=currency,
        payload=payload,
        charge_id=charge_id,
    )

    if inserted and item.get("bonus_credits"):
        add_user_balance(telegram_id, int(item["bonus_credits"]))
        log_user_event(
            telegram_id=telegram_id,
            source="system",
            event_type="subscription_restored",
            event_name=f"restore_{item.get('plan_key')}",
            payload={
                "subscription_type": item.get("plan_key"),
                "charge_id": charge_id,
            },
        )
        log_user_event(
            telegram_id=telegram_id,
            source="system",
            event_type="credits_added",
            event_name="subscription_bonus_restored",
            payload={
                "credits": int(item["bonus_credits"]),
                "charge_id": charge_id,
            },
        )
    return inserted


# =====================================================
# СИНХРОНИЗАЦИЯ С TELEGRAM: create_telegram_stars_invoice_link
# Отправляет готовый результат или статус в Telegram Bot и сохраняет признак отправки в metadata карточки.
# =====================================================
def create_telegram_stars_invoice_link(telegram_id: int, pack_id: str, item: dict, charge_id: str) -> str:
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN is not configured")

    invoice_payload = {
            "title": item["title"],
            "description": f"Оплата {item['title']} в SYLVEX.",
            # The polling Telegram bot currently consumes the canonical
            # four-part payload. Keep the internal invoice id outside the
            # Bot API payload so both deployments parse the same contract.
            "payload": bot_stars_payload(telegram_id, item),
            "currency": "XTR",
            "prices": [
                {
                    "label": item["title"],
                    "amount": int(item["stars"]),
                }
            ],
        }
    response = requests.post(
        f"https://api.telegram.org/bot{BOT_TOKEN}/createInvoiceLink",
        # Bot API requires provider_token to be omitted for Telegram Stars.
        json=invoice_payload,
        timeout=30,
    )

    data = response.json()
    if response.status_code >= 400 or not data.get("ok"):
        prostudio_debug(
            "STARS_INVOICE_CREATE_FAILED",
            telegram_id=telegram_id,
            pack_id=pack_id,
            charge_id=charge_id,
            status=response.status_code,
            telegram_error=data.get("description") or data.get("error_code") or "unknown",
        )
        raise RuntimeError(str(data))

    prostudio_debug(
        "STARS_INVOICE_CREATED",
        telegram_id=telegram_id,
        pack_id=pack_id,
        charge_id=charge_id,
        stars=int(item.get("stars") or 0),
        payload_parts=4,
    )

    return data["result"]


# =====================================================
# PYTHON-БЛОК: crypto_pay_request
# Выполняет отдельный шаг backend-логики SYLVEX.
# Связан с API, базой данных, провайдерами или подготовкой данных для Mini App.
# =====================================================
def crypto_pay_request(method: str, payload=None):
    if not CRYPTO_API_KEY:
        raise RuntimeError("CRYPTO_API_KEY / CRIPTO_API_KEY is not configured")

    response = requests.post(
        f"{CRYPTO_PAY_API_URL}/{method}",
        headers={
            "Crypto-Pay-API-Token": CRYPTO_API_KEY,
            "Content-Type": "application/json",
        },
        json=payload or {},
        timeout=30,
    )
    data = response.json()
    if response.status_code >= 400 or not data.get("ok"):
        raise RuntimeError(str(data))
    return data.get("result")


# =====================================================
# PYTHON-БЛОК: crypto_invoice_url
# Выполняет отдельный шаг backend-логики SYLVEX.
# Связан с API, базой данных, провайдерами или подготовкой данных для Mini App.
# =====================================================
def crypto_invoice_url(invoice: dict) -> str:
    return (
        invoice.get("mini_app_invoice_url")
        or invoice.get("bot_invoice_url")
        or invoice.get("web_app_invoice_url")
        or ""
    )


# =====================================================
# PYTHON-БЛОК: create_crypto_invoice
# Выполняет отдельный шаг backend-логики SYLVEX.
# Связан с API, базой данных, провайдерами или подготовкой данных для Mini App.
# =====================================================
def create_crypto_invoice(telegram_id: int, pack_id: str, item: dict) -> dict:
    invoice = crypto_pay_request(
        "createInvoice",
        {
            "asset": "USDT",
            "amount": f"{item['usd']:.2f}",
            "description": f"SYLVEX {item['title']}",
            "payload": shop_payload("crypto", telegram_id, pack_id, item),
            "expires_in": 1800,
        },
    )
    if not crypto_invoice_url(invoice):
        raise RuntimeError("Crypto Pay did not return invoice URL")
    return invoice


# =====================================================
# PYTHON-БЛОК: get_crypto_invoice
# Выполняет отдельный шаг backend-логики SYLVEX.
# Связан с API, базой данных, провайдерами или подготовкой данных для Mini App.
# =====================================================
def get_crypto_invoice(invoice_id: int):
    result = crypto_pay_request("getInvoices", {"invoice_ids": str(invoice_id)})
    if isinstance(result, dict):
        items = result.get("items") or []
        if items:
            return items[0]
        if result.get("invoice_id"):
            return result
    return None


# =====================================================
# PYTHON-БЛОК: ensure_user_events_table
# Выполняет отдельный шаг backend-логики SYLVEX.
# Связан с API, базой данных, провайдерами или подготовкой данных для Mini App.
# =====================================================
def ensure_user_events_table():
    if not DATABASE_URL:
        return

    conn = db_connect(DATABASE_URL)
    cursor = conn.cursor()
    try:
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_events (
            id SERIAL PRIMARY KEY,
            telegram_id BIGINT NOT NULL,
            source TEXT NOT NULL,
            event_type TEXT NOT NULL,
            event_name TEXT,
            payload JSONB DEFAULT '{}'::jsonb,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)
        conn.commit()
    finally:
        cursor.close()
        conn.close()


# =====================================================
# PYTHON-БЛОК: ensure_payment_tables
# Выполняет отдельный шаг backend-логики SYLVEX.
# Связан с API, базой данных, провайдерами или подготовкой данных для Mini App.
# =====================================================
def ensure_payment_tables():
    if not DATABASE_URL:
        return

    conn = db_connect(DATABASE_URL)
    cursor = conn.cursor()
    try:
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS purchases (
            id SERIAL PRIMARY KEY,
            telegram_id BIGINT NOT NULL,
            provider TEXT NOT NULL,
            credits INTEGER DEFAULT 0,
            amount INTEGER DEFAULT 0,
            currency TEXT DEFAULT 'USD',
            payload TEXT,
            charge_id TEXT UNIQUE,
            status TEXT DEFAULT 'completed',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS subscriptions (
            id SERIAL PRIMARY KEY,
            telegram_id BIGINT NOT NULL,
            subscription_type TEXT,
            payment_method TEXT,
            amount INTEGER DEFAULT 0,
            currency TEXT DEFAULT 'USD',
            starts_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            expires_at TIMESTAMP,
            status TEXT DEFAULT 'active',
            charge_id TEXT UNIQUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS paypal_orders (
            id SERIAL PRIMARY KEY,
            telegram_id BIGINT NOT NULL,
            pack_id TEXT NOT NULL,
            purchase_type TEXT NOT NULL,
            paypal_order_id TEXT UNIQUE NOT NULL,
            paypal_capture_id TEXT UNIQUE,
            amount INTEGER NOT NULL,
            currency TEXT DEFAULT 'USD',
            status TEXT DEFAULT 'created',
            checkout_url TEXT,
            payload TEXT,
            raw_event JSONB DEFAULT '{}'::jsonb,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS paypal_subscriptions (
            id SERIAL PRIMARY KEY,
            telegram_id BIGINT NOT NULL,
            pack_id TEXT NOT NULL DEFAULT 'sub_month',
            plan_id TEXT NOT NULL,
            paypal_subscription_id TEXT UNIQUE NOT NULL,
            amount INTEGER NOT NULL DEFAULT 500,
            currency TEXT DEFAULT 'USD',
            status TEXT DEFAULT 'pending',
            payload TEXT,
            raw_event JSONB DEFAULT '{}'::jsonb,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS subscription_reminders (
            id SERIAL PRIMARY KEY,
            subscription_id INTEGER NOT NULL,
            telegram_id BIGINT NOT NULL,
            days_before INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'sending',
            sent_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(subscription_id, days_before)
        )
        """)
        conn.commit()
    finally:
        cursor.close()
        conn.close()


# =====================================================
# PYTHON-БЛОК: _sanitize_event_payload
# Выполняет отдельный шаг backend-логики SYLVEX.
# Связан с API, базой данных, провайдерами или подготовкой данных для Mini App.
# =====================================================
def _sanitize_event_payload(value, max_text=512, max_items=20, depth=3):
    if depth <= 0:
        return None
    if isinstance(value, dict):
        sanitized = {}
        for i, (k, v) in enumerate(value.items()):
            if i >= max_items:
                break
            sanitized[str(k)] = _sanitize_event_payload(v, max_text, max_items, depth - 1)
        return sanitized
    if isinstance(value, list):
        return [_sanitize_event_payload(v, max_text, max_items, depth - 1) for v in value[:max_items]]
    if isinstance(value, str):
        return value if len(value) <= max_text else value[:max_text] + '…'
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    return str(value)[:max_text]


# =====================================================
# PYTHON-БЛОК: log_user_event
# Выполняет отдельный шаг backend-логики SYLVEX.
# Связан с API, базой данных, провайдерами или подготовкой данных для Mini App.
# =====================================================
def log_user_event(
    telegram_id: int,
    source: str,
    event_type: str,
    event_name: str = "",
    payload: Optional[dict] = None,
):
    if not DATABASE_URL or not telegram_id or not source or not event_type:
        return

    ensure_user_events_table()
    try:
        payload = payload or {}
        sanitized = _sanitize_event_payload(payload)
        payload_str = json.dumps(sanitized, ensure_ascii=False)

        conn = db_connect(DATABASE_URL)
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                INSERT INTO user_events (telegram_id, source, event_type, event_name, payload)
                VALUES (%s, %s, %s, %s, %s::jsonb)
                """,
                (telegram_id, source, event_type, event_name or None, payload_str),
            )
            conn.commit()
        finally:
            cursor.close()
            conn.close()
    except Exception as exc:
        print("LOG EVENT FAILED:", exc)
    try:
        track_referral_activity(telegram_id, event_type, event_name)
    except Exception as exc:
        print("REFERRAL ACTIVITY TRACKING FAILED:", exc)


# =====================================================
# PYTHON-БЛОК: _to_iso
# Выполняет отдельный шаг backend-логики SYLVEX.
# Связан с API, базой данных, провайдерами или подготовкой данных для Mini App.
# =====================================================
def _to_iso(v):
    if v is None:
        return None
    try:
        return v.isoformat()
    except Exception:
        try:
            return str(v)
        except Exception:
            return None


# =====================================================
# ЗАГРУЗКА ФАЙЛОВ: ensure_user_profiles_table
# Получает файл или ссылку, приводит её к безопасному формату и передаёт дальше в генерацию или сохранение.
# =====================================================
def ensure_user_profiles_table():
    if not DATABASE_URL:
        return

    conn = db_connect(DATABASE_URL)
    cursor = conn.cursor()
    try:
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_profiles (
            telegram_id BIGINT PRIMARY KEY,
            display_name TEXT,
            custom_avatar_url TEXT,
            theme_preference JSONB DEFAULT '{}'::jsonb,
            updated_at TIMESTAMP DEFAULT NOW()
        )
        """)
        conn.commit()
    finally:
        cursor.close()
        conn.close()


# =====================================================
# ЗАГРУЗКА ФАЙЛОВ: get_user_profile
# Получает файл или ссылку, приводит её к безопасному формату и передаёт дальше в генерацию или сохранение.
# =====================================================
def get_user_profile(telegram_id: int) -> dict:
    if not DATABASE_URL or not telegram_id:
        return {}

    ensure_user_profiles_table()
    conn = db_connect(DATABASE_URL)
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT display_name, custom_avatar_url, theme_preference
            FROM user_profiles
            WHERE telegram_id = %s
        """, (telegram_id,))
        row = cursor.fetchone()
    finally:
        cursor.close()
        conn.close()

    if not row:
        return {}

    theme = row[2] or {}
    if isinstance(theme, str):
        try:
            theme = json.loads(theme)
        except Exception:
            theme = {}

    return {
        "display_name": row[0],
        "custom_avatar_url": row[1],
        "theme_preference": theme,
    }


# =====================================================
# ЗАГРУЗКА ФАЙЛОВ: save_user_profile
# Получает файл или ссылку, приводит её к безопасному формату и передаёт дальше в генерацию или сохранение.
# =====================================================
def save_user_profile(telegram_id: int, display_name=None, custom_avatar_url=None, theme_preference=None) -> dict:
    if not DATABASE_URL or not telegram_id:
        return {}

    ensure_user_exists(telegram_id)
    ensure_user_profiles_table()

    theme_json = None
    if theme_preference is not None:
        theme_json = json.dumps(theme_preference if isinstance(theme_preference, dict) else {}, ensure_ascii=False)

    conn = db_connect(DATABASE_URL)
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO user_profiles (telegram_id, display_name, custom_avatar_url, theme_preference, updated_at)
            VALUES (
                %s,
                %s,
                %s,
                COALESCE(%s::jsonb, '{}'::jsonb),
                NOW()
            )
            ON CONFLICT (telegram_id) DO UPDATE
            SET display_name = COALESCE(EXCLUDED.display_name, user_profiles.display_name),
                custom_avatar_url = COALESCE(EXCLUDED.custom_avatar_url, user_profiles.custom_avatar_url),
                theme_preference = COALESCE(EXCLUDED.theme_preference, user_profiles.theme_preference),
                updated_at = NOW()
        """, (telegram_id, display_name, custom_avatar_url, theme_json))
        conn.commit()
    finally:
        cursor.close()
        conn.close()

    return get_user_profile(telegram_id)


# =====================================================
# PYTHON-БЛОК: ensure_user_referrals_table
# Выполняет отдельный шаг backend-логики SYLVEX.
# Связан с API, базой данных, провайдерами или подготовкой данных для Mini App.
# =====================================================
def ensure_user_referrals_table():
    if not DATABASE_URL:
        return

    conn = db_connect(DATABASE_URL)
    cursor = conn.cursor()
    try:
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_referrals (
            telegram_id BIGINT PRIMARY KEY,
            code TEXT UNIQUE NOT NULL,
            activated_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT NOW()
        )
        """)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS referral_attributions (
            invited_telegram_id BIGINT PRIMARY KEY,
            inviter_telegram_id BIGINT NOT NULL,
            referral_code TEXT NOT NULL,
            joined_at TIMESTAMP DEFAULT NOW(),
            last_activity_at TIMESTAMP,
            generation_count INTEGER DEFAULT 0,
            subscription_count INTEGER DEFAULT 0,
            last_event_name TEXT
        )
        """)
        cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_referral_attributions_inviter
        ON referral_attributions (inviter_telegram_id)
        """)
        conn.commit()
    finally:
        cursor.close()
        conn.close()


# =====================================================
# PYTHON-БЛОК: referral_code_for
# Выполняет отдельный шаг backend-логики SYLVEX.
# Связан с API, базой данных, провайдерами или подготовкой данных для Mini App.
# =====================================================
def referral_code_for(telegram_id: int) -> str:
    digest = hashlib.sha1(f"sylvex:{telegram_id}".encode("utf-8")).hexdigest()[:10]
    return f"sylvex_{digest}"


# =====================================================
# PYTHON-БЛОК: get_referral_state
# Выполняет отдельный шаг backend-логики SYLVEX.
# Связан с API, базой данных, провайдерами или подготовкой данных для Mini App.
# =====================================================
def get_referral_state(telegram_id: int, activate: bool = False) -> dict:
    if not telegram_id:
        return {}

    code = referral_code_for(telegram_id)
    bot_username = (os.getenv("TELEGRAM_BOT_USERNAME") or "sylvexai_bot").strip().lstrip("@")
    link = f"https://t.me/{bot_username}?startapp=ref_{code}_shop"

    if not DATABASE_URL:
        return {
            "ok": True,
            "telegram_id": telegram_id,
            "code": code,
            "link": link,
            "referrals_count": 0,
            "generation_events": 0,
            "subscription_events": 0,
            "activated_at": None,
        }

    ensure_user_exists(telegram_id)
    ensure_user_referrals_table()
    conn = db_connect(DATABASE_URL)
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO user_referrals (telegram_id, code, activated_at)
            VALUES (%s, %s, CASE WHEN %s THEN NOW() ELSE NULL END)
            ON CONFLICT (telegram_id) DO UPDATE
            SET activated_at = CASE
                WHEN %s AND user_referrals.activated_at IS NULL THEN NOW()
                ELSE user_referrals.activated_at
            END
            RETURNING activated_at
        """, (telegram_id, code, activate, activate))
        row = cursor.fetchone()
        cursor.execute("""
            SELECT COUNT(*), COALESCE(SUM(generation_count), 0),
                   COALESCE(SUM(subscription_count), 0)
            FROM referral_attributions
            WHERE inviter_telegram_id = %s
        """, (telegram_id,))
        referral_totals = cursor.fetchone() or (0, 0, 0)
        conn.commit()
    finally:
        cursor.close()
        conn.close()

    return {
        "ok": True,
        "telegram_id": telegram_id,
        "code": code,
        "link": link,
        "referrals_count": int(referral_totals[0] or 0),
        "generation_events": int(referral_totals[1] or 0),
        "subscription_events": int(referral_totals[2] or 0),
        "activated_at": _to_iso(row[0]) if row and row[0] else None,
    }


def claim_referral(invited_telegram_id: int, referral_code: str) -> dict:
    """Permanently attributes a user to the first valid referrer."""
    if not DATABASE_URL or not invited_telegram_id or not referral_code:
        return {"ok": False, "error": "referral_unavailable"}

    ensure_user_referrals_table()
    conn = db_connect(DATABASE_URL)
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT telegram_id FROM user_referrals WHERE code = %s",
            (referral_code,),
        )
        owner = cursor.fetchone()
        if not owner:
            return {"ok": False, "error": "referral_not_found"}
        inviter_telegram_id = int(owner[0])
        if inviter_telegram_id == int(invited_telegram_id):
            return {"ok": False, "error": "self_referral"}
        cursor.execute("""
            INSERT INTO referral_attributions
                (invited_telegram_id, inviter_telegram_id, referral_code)
            VALUES (%s, %s, %s)
            ON CONFLICT (invited_telegram_id) DO NOTHING
            RETURNING invited_telegram_id
        """, (invited_telegram_id, inviter_telegram_id, referral_code))
        created = bool(cursor.fetchone())
        conn.commit()
    finally:
        cursor.close()
        conn.close()
    return {"ok": True, "claimed": created, "shop": True}


def track_referral_activity(telegram_id: int, event_type: str, event_name: str):
    """Records activity for manual referral reward review by administrators."""
    is_generation = event_name == "generation_completed"
    is_subscription = event_type == "subscription_activated" or event_name == "subscription_activated"
    if not DATABASE_URL or not telegram_id or not (is_generation or is_subscription):
        return
    ensure_user_referrals_table()
    conn = db_connect(DATABASE_URL)
    cursor = conn.cursor()
    try:
        cursor.execute("""
            UPDATE referral_attributions
            SET last_activity_at = NOW(),
                generation_count = generation_count + %s,
                subscription_count = subscription_count + %s,
                last_event_name = %s
            WHERE invited_telegram_id = %s
            RETURNING inviter_telegram_id
        """, (1 if is_generation else 0, 1 if is_subscription else 0, event_name, telegram_id))
        owner = cursor.fetchone()
        if owner:
            cursor.execute("""
                INSERT INTO user_events (telegram_id, source, event_type, event_name, payload)
                VALUES (%s, 'referral_system', 'referral_activity', %s, %s::jsonb)
            """, (int(owner[0]), event_name, json.dumps({"invited_telegram_id": telegram_id})))
        conn.commit()
    finally:
        cursor.close()
        conn.close()


# =====================================================
# PYTHON-БЛОК: get_user_state
# Выполняет отдельный шаг backend-логики SYLVEX.
# Связан с API, базой данных, провайдерами или подготовкой данных для Mini App.
# =====================================================
def get_user_state(telegram_id: int, username: str = None, first_name: str = None) -> dict:
    if not DATABASE_URL or not telegram_id:
        return {}

    ensure_user_exists(telegram_id)
    if username or first_name:
        conn = db_connect(DATABASE_URL)
        cursor = conn.cursor()
        try:
            cursor.execute("""
                UPDATE users
                SET username = COALESCE(%s, username),
                    first_name = COALESCE(%s, first_name)
                WHERE telegram_id = %s
            """, (username, first_name, telegram_id))
            conn.commit()
        finally:
            cursor.close()
            conn.close()

    conn = db_connect(DATABASE_URL)
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT telegram_id, username, first_name, balance, subscription, created_at
            FROM users
            WHERE telegram_id = %s
        """, (telegram_id,))
        user_row = cursor.fetchone()
        if not user_row:
            return {}

        cursor.execute("""
            SELECT subscription_type, expires_at::timestamp
            FROM subscriptions
            WHERE telegram_id = %s
              AND status = 'active'
              AND expires_at::timestamp > NOW()
            ORDER BY expires_at::timestamp DESC
            LIMIT 1
        """, (telegram_id,))
        active_sub = cursor.fetchone()
        cursor.execute("""
            SELECT subscription_type, expires_at::timestamp
            FROM subscriptions
            WHERE telegram_id = %s
            ORDER BY expires_at::timestamp DESC NULLS LAST, id DESC
            LIMIT 1
        """, (telegram_id,))
        latest_sub = cursor.fetchone()

        if active_sub:
            cursor.execute("""
                UPDATE users
                SET subscription = COALESCE(%s, 'active')
                WHERE telegram_id = %s
            """, (active_sub[0], telegram_id))
            conn.commit()
        else:
            cursor.execute("""
                UPDATE subscriptions
                SET status = 'expired'
                WHERE telegram_id = %s
                  AND status = 'active'
                  AND expires_at::timestamp <= NOW()
            """, (telegram_id,))
            cursor.execute("""
                UPDATE users
                SET subscription = NULL
                WHERE telegram_id = %s
                  AND subscription IS NOT NULL
            """, (telegram_id,))
            conn.commit()

        cursor.execute("""
            SELECT COUNT(*)
            FROM generations
            WHERE telegram_id = %s
        """, (telegram_id,))
        total_generations = cursor.fetchone()[0] or 0

        try:
            cursor.execute("""
                SELECT COALESCE(SUM(credits), 0)
                FROM generation_charges
                WHERE telegram_id = %s
            """, (telegram_id,))
            tokens_spent = max(0, int(cursor.fetchone()[0] or 0))
        except Exception:
            tokens_spent = 0

        referrals_count = 0
        community_posts_count = 0
        community_likes_count = 0
        cursor.execute("SELECT to_regclass('public.referral_attributions')")
        if cursor.fetchone()[0]:
            cursor.execute("SELECT COUNT(*) FROM referral_attributions WHERE inviter_telegram_id = %s", (telegram_id,))
            referrals_count = int(cursor.fetchone()[0] or 0)
        cursor.execute("SELECT to_regclass('public.community_posts'), to_regclass('public.community_likes')")
        community_tables = cursor.fetchone() or (None, None)
        if community_tables[0]:
            cursor.execute("SELECT COUNT(*) FROM community_posts WHERE telegram_id = %s", (telegram_id,))
            community_posts_count = int(cursor.fetchone()[0] or 0)
        if community_tables[0] and community_tables[1]:
            cursor.execute("""
                SELECT COUNT(*)
                FROM community_likes likes
                JOIN community_posts posts ON posts.id = likes.post_id
                WHERE posts.telegram_id = %s
            """, (telegram_id,))
            community_likes_count = int(cursor.fetchone()[0] or 0)

        cursor.execute("""
            SELECT event_type, event_name, source, payload, created_at
            FROM user_events
            WHERE telegram_id = %s
            ORDER BY created_at DESC
            LIMIT 20
        """, (telegram_id,))
        events = cursor.fetchall()

        cursor.execute("""
            SELECT provider, credits, amount, currency, payload, charge_id, status, created_at
            FROM purchases
            WHERE telegram_id = %s
            ORDER BY created_at DESC
            LIMIT 10
        """, (telegram_id,))
        purchases = cursor.fetchall()

        cursor.execute("""
            SELECT generation_type, prompt, status, created_at
            FROM generations
            WHERE telegram_id = %s
            ORDER BY created_at DESC
            LIMIT 10
        """, (telegram_id,))
        generations = cursor.fetchall()
        conn.commit()
    finally:
        cursor.close()
        conn.close()

    profile = get_user_profile(telegram_id)
    subscription_status = "active" if active_sub else "free"
    last_subscription_expires_at = _to_iso(latest_sub[1]) if latest_sub and latest_sub[1] else None
    subscription_expired = bool(latest_sub and latest_sub[1] and not active_sub and latest_sub[1].timestamp() <= time.time())
    result = {
        "telegram_id": user_row[0],
        "username": user_row[1],
        "first_name": user_row[2],
        "balance": user_row[3] or 0,
        "status": "active" if active_sub else (user_row[4] or "free"),
        "subscription_status": subscription_status,
        "subscription_plan": active_sub[0] if active_sub else None,
        "subscription_expires_at": _to_iso(active_sub[1]) if active_sub and active_sub[1] else None,
        "last_subscription_expires_at": last_subscription_expires_at,
        "subscription_expired": subscription_expired,
        "display_name": profile.get("display_name"),
        "custom_avatar_url": profile.get("custom_avatar_url"),
        "theme_preference": profile.get("theme_preference") or {},
        "created_at": user_row[5],
        "total_generations": total_generations,
        "generations_count": total_generations,
        "tokens_spent": tokens_spent,
        "referrals_count": referrals_count,
        "community_posts_count": community_posts_count,
        "community_likes_count": community_likes_count,
        "last_actions": [
            {
                "event_type": row[0],
                "event_name": row[1],
                "source": row[2],
                "payload": row[3],
                "created_at": _to_iso(row[4]) if row[4] else None,
            }
            for row in events
        ],
        "last_purchases": [
            {
                "provider": row[0],
                "credits": row[1],
                "amount": row[2],
                "currency": row[3],
                "payload": row[4],
                "charge_id": row[5],
                "status": row[6],
                "created_at": _to_iso(row[7]) if row[7] else None,
            }
            for row in purchases
        ],
        "last_generations": [
            {
                "generation_type": row[0],
                "prompt": row[1],
                "status": row[2],
                "created_at": _to_iso(row[3]) if row[3] else None,
            }
            for row in generations
        ],
    }
    return result


# =====================================================
# PYTHON-БЛОК: get_fast_user_state
# Выполняет отдельный шаг backend-логики SYLVEX.
# Связан с API, базой данных, провайдерами или подготовкой данных для Mini App.
# =====================================================
def get_fast_user_state(telegram_id: int) -> dict:
    if not telegram_id:
        return {
            "balance": 0,
            "subscription": None,
            "subscription_until": None,
            "status": "free",
        }
    if not DATABASE_URL:
        return {
            "balance": 0,
            "subscription": None,
            "subscription_until": None,
            "status": "free",
        }

    ensure_user_exists(telegram_id)
    conn = db_connect(DATABASE_URL)
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT COALESCE(balance, 0)
            FROM users
            WHERE telegram_id = %s
        """, (telegram_id,))
        user_row = cursor.fetchone()

        cursor.execute("""
            SELECT subscription_type, expires_at::timestamp
            FROM subscriptions
            WHERE telegram_id = %s
              AND status = 'active'
              AND expires_at::timestamp > NOW()
            ORDER BY expires_at::timestamp DESC
            LIMIT 1
        """, (telegram_id,))
        active_sub = cursor.fetchone()
        cursor.execute("""
            SELECT subscription_type, expires_at::timestamp
            FROM subscriptions
            WHERE telegram_id = %s
            ORDER BY expires_at::timestamp DESC NULLS LAST, id DESC
            LIMIT 1
        """, (telegram_id,))
        latest_sub = cursor.fetchone()
    finally:
        cursor.close()
        conn.close()

    balance = user_row[0] if user_row else 0
    subscription = active_sub[0] if active_sub else None
    subscription_until = _to_iso(active_sub[1]) if active_sub and active_sub[1] else None
    status = "pro" if active_sub else "free"
    last_subscription_expires_at = _to_iso(latest_sub[1]) if latest_sub and latest_sub[1] else None
    subscription_expired = bool(latest_sub and latest_sub[1] and not active_sub and latest_sub[1].timestamp() <= time.time())
    profile = get_user_profile(telegram_id)

    return {
        "telegram_id": telegram_id,
        "balance": balance or 0,
        "subscription": subscription,
        "subscription_until": subscription_until,
        "status": status,
        "subscription_status": "active" if active_sub else "free",
        "subscription_plan": subscription,
        "subscription_expires_at": subscription_until,
        "last_subscription_expires_at": last_subscription_expires_at,
        "subscription_expired": subscription_expired,
        "display_name": profile.get("display_name"),
        "custom_avatar_url": profile.get("custom_avatar_url"),
        "theme_preference": profile.get("theme_preference") or {},
    }


# =====================================================
# PYTHON-БЛОК: create_purchase_once
# Выполняет отдельный шаг backend-логики SYLVEX.
# Связан с API, базой данных, провайдерами или подготовкой данных для Mini App.
# =====================================================
def create_purchase_once(telegram_id: int, provider: str, credits: int, amount: int, currency: str, payload: str, charge_id: str) -> bool:
    if not DATABASE_URL:
        return False

    ensure_payment_tables()
    conn = db_connect(DATABASE_URL)
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO purchases (telegram_id, provider, credits, amount, currency, payload, charge_id, status)
            VALUES (%s, %s, %s, %s, %s, %s, %s, 'completed')
            ON CONFLICT (charge_id) DO NOTHING
        """, (telegram_id, provider, credits, amount, currency, payload, charge_id))
        created = cursor.rowcount > 0
        conn.commit()
        return created
    finally:
        cursor.close()
        conn.close()


# =====================================================
# PYTHON-БЛОК: activate_subscription
# Выполняет отдельный шаг backend-логики SYLVEX.
# Связан с API, базой данных, провайдерами или подготовкой данных для Mini App.
# =====================================================
def activate_subscription(telegram_id: int, item: dict, provider: str, amount: int, currency: str, payload: str, charge_id: str) -> bool:
    if not DATABASE_URL:
        return False

    ensure_user_exists(telegram_id)
    ensure_payment_tables()
    conn = db_connect(DATABASE_URL)
    cursor = conn.cursor()
    try:
        # Serialize subscription changes for this user so two confirmations
        # cannot overwrite one another or lose already-paid remaining time.
        cursor.execute("SELECT telegram_id FROM users WHERE telegram_id = %s FOR UPDATE", (telegram_id,))
        cursor.execute("""
            DELETE FROM subscription_reminders
            WHERE status = 'sending'
              AND created_at < NOW() - INTERVAL '1 hour'
        """)
        cursor.execute("""
            INSERT INTO subscriptions (
                telegram_id, subscription_type, payment_method, amount, currency, expires_at, status, charge_id
            )
            VALUES (
                %s, %s, %s, %s, %s,
                (
                    SELECT GREATEST(
                        CURRENT_TIMESTAMP,
                        COALESCE(MAX(expires_at::timestamp), CURRENT_TIMESTAMP)
                    ) + (%s || ' days')::interval
                    FROM subscriptions
                    WHERE telegram_id = %s
                      AND status = 'active'
                      AND expires_at::timestamp > CURRENT_TIMESTAMP
                ),
                'active', %s
            )
            ON CONFLICT (charge_id) DO NOTHING
            RETURNING id
        """, (telegram_id, item["plan_key"], provider, amount, currency, item["days"], telegram_id, charge_id))
        inserted_row = cursor.fetchone()
        inserted = bool(inserted_row)
        if inserted:
            cursor.execute("""
                UPDATE subscriptions
                SET status = 'cancelled'
                WHERE telegram_id = %s
                  AND status = 'active'
                  AND id <> %s
            """, (telegram_id, inserted_row[0]))
            cursor.execute("UPDATE users SET subscription = %s WHERE telegram_id = %s", (item.get("plan_key") or "active", telegram_id))
        conn.commit()
        return inserted
    finally:
        cursor.close()
        conn.close()




# =====================================================
# PYTHON-БЛОК: ensure_user_exists
# Выполняет отдельный шаг backend-логики SYLVEX.
# Связан с API, базой данных, провайдерами или подготовкой данных для Mini App.
# =====================================================
def ensure_user_exists(telegram_id: int):
    if not DATABASE_URL or not telegram_id:
        return

    conn = db_connect(DATABASE_URL)
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO users (telegram_id, first_name, balance, subscription)
            VALUES (%s, 'Developer', 0, 'free')
            ON CONFLICT (telegram_id) DO NOTHING
        """, (telegram_id,))
        conn.commit()
    finally:
        cursor.close()
        conn.close()

# =====================================================
# БАЛАНС И СТОИМОСТЬ: add_user_balance
# Рассчитывает стоимость генерации, проверяет токены пользователя или фиксирует списание после успешного результата.
# =====================================================
def add_user_balance(telegram_id: int, credits: int):
    if not DATABASE_URL or not telegram_id or not credits:
        return

    ensure_user_exists(telegram_id)
    conn = db_connect(DATABASE_URL)
    cursor = conn.cursor()
    try:
        cursor.execute(
            "UPDATE users SET balance = COALESCE(balance, 0) + %s WHERE telegram_id = %s",
            (credits, telegram_id),
        )
        conn.commit()
    finally:
        cursor.close()
        conn.close()


# =====================================================
# БАЛАНС И СТОИМОСТЬ: charge_generation_balance
# Рассчитывает стоимость генерации, проверяет токены пользователя или фиксирует списание после успешного результата.
# =====================================================
def charge_generation_balance(telegram_id: int, generation_id: str, result: dict, payload: dict) -> dict:
    credits = int(result.get("cost_credits") or result.get("cost") or result.get("price") or 0)
    if not DATABASE_URL or not telegram_id or not generation_id or credits <= 0:
        print("PROSTUDIO CHARGE SKIPPED:", {
            "telegram_id": telegram_id,
            "generation_id": generation_id,
            "credits": max(0, credits),
            "has_database": bool(DATABASE_URL),
        })
        return {"charged": False, "credits": max(0, credits), "balance_after": None}

    ensure_user_exists(telegram_id)
    ensure_prostudio_table()
    conn = db_connect(DATABASE_URL)
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO generation_charges (
                generation_id, telegram_id, mode, model, provider, credits
            ) VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (generation_id) DO NOTHING
            RETURNING id
        """, (
            generation_id,
            telegram_id,
            payload.get("mode") or payload.get("category") or result.get("type") or "",
            payload.get("model") or result.get("model") or "",
            payload.get("provider") or result.get("provider") or "",
            credits,
        ))
        inserted = cursor.fetchone()
        if inserted:
            cursor.execute("""
                UPDATE users
                SET balance = COALESCE(balance, 0) - %s
                WHERE telegram_id = %s
                  AND COALESCE(balance, 0) >= %s
                RETURNING COALESCE(balance, 0)
            """, (credits, telegram_id, credits))
            row = cursor.fetchone()
            if not row:
                cursor.execute("DELETE FROM generation_charges WHERE generation_id = %s", (generation_id,))
                conn.commit()
                print("PROSTUDIO CHARGE INSUFFICIENT:", {
                    "telegram_id": telegram_id,
                    "generation_id": generation_id,
                    "credits": credits,
                })
                return {"charged": False, "credits": credits, "balance_after": None, "insufficient_balance": True}
            balance_after = int(row[0])
            cursor.execute(
                "UPDATE generation_charges SET balance_after = %s WHERE generation_id = %s",
                (balance_after, generation_id),
            )
            conn.commit()
            print("PROSTUDIO CHARGE SUCCESS:", {
                "telegram_id": telegram_id,
                "generation_id": generation_id,
                "credits": credits,
                "balance_after": balance_after,
            })
            return {"charged": True, "credits": credits, "balance_after": balance_after}

        cursor.execute(
            "SELECT credits, balance_after FROM generation_charges WHERE generation_id = %s",
            (generation_id,),
        )
        row = cursor.fetchone()
        conn.commit()
        print("PROSTUDIO CHARGE ALREADY_EXISTS:", {
            "telegram_id": telegram_id,
            "generation_id": generation_id,
            "credits": int(row[0]) if row else credits,
            "balance_after": int(row[1]) if row and row[1] is not None else None,
        })
        return {
            "charged": False,
            "already_charged": True,
            "credits": int(row[0]) if row else credits,
            "balance_after": int(row[1]) if row and row[1] is not None else None,
        }
    except Exception as exc:
        conn.rollback()
        print("PROSTUDIO CHARGE ERROR:", {
            "telegram_id": telegram_id,
            "generation_id": generation_id,
            "credits": credits,
            "error": str(exc),
        })
        return {"charged": False, "credits": credits, "balance_after": None, "error": str(exc)}
    finally:
        cursor.close()
        conn.close()


# =====================================================
# PYTHON-БЛОК: finalize_shop_payment
# Выполняет отдельный шаг backend-логики SYLVEX.
# Связан с API, базой данных, провайдерами или подготовкой данных для Mini App.
# =====================================================
def finalize_shop_payment(telegram_id: int, provider: str, item: dict, amount: int, currency: str, payload: str, charge_id: str):
    credits = int(item.get("credits") or 0)
    bonus_credits = int(item.get("bonus_credits") or 0)
    created = create_purchase_once(telegram_id, provider, credits or bonus_credits, amount, currency, payload, charge_id)

    if not created:
        return False

    log_user_event(
        telegram_id=telegram_id,
        source="payment",
        event_type="payment_success",
        event_name="payment_success",
        payload={
            "provider": provider,
            "pack_id": item.get("plan_key") or f"credits_{credits}",
            "amount": amount,
            "currency": currency,
            "charge_id": charge_id,
            "payload": payload,
        },
    )

    if item["kind"] == "subscription":
        activated = activate_subscription(telegram_id, item, provider, amount, currency, payload, charge_id)
        if activated:
            log_user_event(
                telegram_id=telegram_id,
                source="payment",
                event_type="subscription_activated",
                event_name=f"activate_{item.get('plan_key')}",
                payload={
                    "subscription_type": item.get("plan_key"),
                    "expires_in_days": item.get("days"),
                    "charge_id": charge_id,
                },
            )
        if bonus_credits:
            add_user_balance(telegram_id, bonus_credits)
            log_user_event(
                telegram_id=telegram_id,
                source="payment",
                event_type="credits_added",
                event_name="subscription_bonus_credits",
                payload={
                    "credits": bonus_credits,
                    "charge_id": charge_id,
                },
            )
        if activated:
            send_subscription_congratulations(telegram_id, item, provider)
    else:
        add_user_balance(telegram_id, credits)
        log_user_event(
            telegram_id=telegram_id,
            source="payment",
            event_type="credits_added",
            event_name="credits_purchase",
            payload={
                "credits": credits,
                "charge_id": charge_id,
            },
        )

    return True


def send_subscription_congratulations(telegram_id: int, item: dict, provider: str = "") -> bool:
    if not BOT_TOKEN or not telegram_id:
        return False
    name = "Пользователь"
    username = ""
    expires_at = None
    balance = 0
    try:
        conn = db_connect(DATABASE_URL)
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT first_name, username, COALESCE(balance, 0) FROM users WHERE telegram_id = %s", (telegram_id,))
            user_row = cursor.fetchone()
            if user_row:
                name = user_row[0] or user_row[1] or name
                username = user_row[1] or ""
                balance = int(user_row[2] or 0)
            cursor.execute("""
                SELECT expires_at::timestamp
                FROM subscriptions
                WHERE telegram_id = %s AND status = 'active'
                ORDER BY expires_at::timestamp DESC LIMIT 1
            """, (telegram_id,))
            sub_row = cursor.fetchone()
            expires_at = sub_row[0] if sub_row else None
        finally:
            cursor.close()
            conn.close()
    except Exception as exc:
        prostudio_error("SUBSCRIPTION_CONGRATULATION_PROFILE_FAILED", exc, telegram_id=telegram_id)

    plan_label = "1 год" if str(item.get("plan_key") or "").lower() == "year" else "1 месяц"
    handle = f"@{html.escape(username)}" if username else "без username"
    expiry_label = expires_at.strftime("%d.%m.%Y %H:%M") if expires_at else "активна"
    text = (
        "🎉 <b>Поздравляем с подпиской SYLVEX Pro!</b>\n\n"
        f"👤 <b>{html.escape(str(name))}</b> · {handle}\n"
        f"🆔 <code>{int(telegram_id)}</code>\n"
        f"💎 План: <b>{plan_label}</b>\n"
        f"📅 Действует до: <b>{expiry_label}</b>\n"
        f"⚡️ Баланс: <b>{balance}</b>\n"
        f"💳 Оплата: <b>{html.escape(str(provider or 'payment'))}</b>\n\n"
        "Все инструменты Pro уже доступны. Можно сразу начинать генерацию."
    )
    try:
        response = requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            json={
                "chat_id": int(telegram_id),
                "text": text,
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
                "reply_markup": {"inline_keyboard": [
                    [{"text": "Начать генерацию", "web_app": {"url": WEBAPP_URL.rstrip("/") + "/webapp/index.html?view=home"}}],
                    [{"text": "Открыть Pro Studio", "web_app": {"url": WEBAPP_URL.rstrip("/") + "/webapp/index.html?view=tools"}}],
                ]},
            },
            timeout=20,
        )
        data = response.json() if response.content else {}
        if response.status_code >= 400 or not data.get("ok"):
            raise RuntimeError(f"Telegram sendMessage failed: {response.status_code} {data}")
        return True
    except Exception as exc:
        prostudio_error("SUBSCRIPTION_CONGRATULATION_FAILED", exc, telegram_id=telegram_id)
        return False


# =====================================================
# PYTHON-БЛОК: reset_developer_subscription
# Выполняет отдельный шаг backend-логики SYLVEX.
# Связан с API, базой данных, провайдерами или подготовкой данных для Mini App.
# =====================================================
def reset_developer_subscription(telegram_id: int, reset_credits: bool = False) -> dict:
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL is not configured")

    ensure_payment_tables()
    ensure_user_exists(telegram_id)

    conn = db_connect(DATABASE_URL)
    cursor = conn.cursor()
    try:
        cursor.execute("""
            UPDATE subscriptions
            SET status = 'cancelled'
            WHERE telegram_id = %s
              AND status = 'active'
        """, (telegram_id,))
        cancelled = cursor.rowcount

        if reset_credits:
            cursor.execute("""
                UPDATE users
                SET subscription = 'free', balance = 0
                WHERE telegram_id = %s
            """, (telegram_id,))
        else:
            cursor.execute("""
                UPDATE users
                SET subscription = 'free'
                WHERE telegram_id = %s
            """, (telegram_id,))

        conn.commit()
    finally:
        cursor.close()
        conn.close()

    return {
        "cancelled_subscriptions": cancelled,
        "reset_credits": reset_credits,
    }


# =====================================================
# POLLING-ПРОЦЕСС: poll_crypto_invoice
# Проверяет статус внешней задачи у AI-провайдера.
# При completed извлекает результат, при failed возвращает понятную ошибку, при processing продолжает ожидание.
# =====================================================
async def poll_crypto_invoice(invoice_id: int, telegram_id: int, pack_id: str):
    item = shop_item(pack_id)
    if not item:
        return

    for _ in range(90):
        await asyncio.sleep(20)
        try:
            invoice = get_crypto_invoice(invoice_id)
        except Exception as exc:
            print("MINIAPP CRYPTO POLL ERROR:", exc)
            return
        if not invoice:
            return
        status = invoice.get("status")
        if status == "paid":
            finalize_shop_payment(
                telegram_id=telegram_id,
                provider="crypto_pay",
                item=item,
                amount=int(round(float(invoice.get("amount") or 0) * 100)),
                currency=invoice.get("asset") or "USDT",
                payload=invoice.get("payload") or "",
                charge_id=f"crypto_invoice_{invoice_id}",
            )
            # Sync user state after successful crypto payment so frontend/bot read updated state
            try:
                sync_user_to_db({
                    "telegram_id": telegram_id,
                    "username": None,
                    "first_name": None,
                    "status": "free",
                    "balance": 0,
                })
            except Exception as exc:
                print("CRYPTO POLL: sync failed", exc)
            return
        if status == "expired":
            return


# =====================================================
# PYTHON-БЛОК: paypal_configured
# Выполняет отдельный шаг backend-логики SYLVEX.
# Связан с API, базой данных, провайдерами или подготовкой данных для Mini App.
# =====================================================
def paypal_configured() -> bool:
    return bool(PAYPAL_CLIENT_ID and PAYPAL_CLIENT_SECRET)


# =====================================================
# PYTHON-БЛОК: paypal_access_token
# Выполняет отдельный шаг backend-логики SYLVEX.
# Связан с API, базой данных, провайдерами или подготовкой данных для Mini App.
# =====================================================
def paypal_access_token(api_base: str = None) -> str:
    if not paypal_configured():
        raise RuntimeError("PayPal credentials are not configured")

    base = api_base or PAYPAL_API_BASE
    response = requests.post(
        f"{base}/v1/oauth2/token",
        auth=(PAYPAL_CLIENT_ID, PAYPAL_CLIENT_SECRET),
        data={"grant_type": "client_credentials"},
        headers={"Accept": "application/json", "Accept-Language": "en_US"},
        timeout=30,
    )
    if response.status_code >= 400:
        print("PAYPAL TOKEN ERROR:", response.status_code, response.text[:1000])
        raise RuntimeError("PayPal token request failed")

    token = response.json().get("access_token")
    if not token:
        raise RuntimeError("PayPal token response did not include access_token")
    return token


# =====================================================
# PYTHON-БЛОК: paypal_headers
# Выполняет отдельный шаг backend-логики SYLVEX.
# Связан с API, базой данных, провайдерами или подготовкой данных для Mini App.
# =====================================================
def paypal_headers(api_base: str = None) -> dict:
    return {
        "Authorization": f"Bearer {paypal_access_token(api_base)}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


# =====================================================
# PYTHON-БЛОК: paypal_return_url
# Выполняет отдельный шаг backend-логики SYLVEX.
# Связан с API, базой данных, провайдерами или подготовкой данных для Mini App.
# =====================================================
def paypal_return_url(telegram_id: int, pack_id: str, status: str) -> str:
    params = urllib.parse.urlencode({
        "view": "shop",
        "payment": status,
        "provider": "paypal",
        "pack_id": pack_id or "",
        "telegram_id": str(telegram_id or ""),
    })
    return SHOP_WEBAPP_URL + ("&" if "?" in SHOP_WEBAPP_URL else "?") + params


# =====================================================
# PYTHON-БЛОК: paypal_purchase_type
# Выполняет отдельный шаг backend-логики SYLVEX.
# Связан с API, базой данных, провайдерами или подготовкой данных для Mini App.
# =====================================================
def paypal_purchase_type(item: dict) -> str:
    return "subscription" if item.get("kind") == "subscription" else "tokens"


# =====================================================
# PYTHON-БЛОК: create_paypal_order
# Выполняет отдельный шаг backend-логики SYLVEX.
# Связан с API, базой данных, провайдерами или подготовкой данных для Mini App.
# =====================================================
def create_paypal_order(telegram_id: int, pack_id: str, item: dict) -> dict:
    amount_value = f"{float(item['usd']):.2f}"
    payload = shop_payload("paypal", telegram_id, pack_id, item)
    body = {
        "intent": "CAPTURE",
        "purchase_units": [
            {
                "reference_id": pack_id,
                "custom_id": payload,
                "description": item.get("title") or "SYLVEX purchase",
                "amount": {
                    "currency_code": "USD",
                    "value": amount_value,
                },
            }
        ],
        "payment_source": {
            "paypal": {
                "experience_context": {
                    "brand_name": "SYLVEX",
                    "shipping_preference": "NO_SHIPPING",
                    "user_action": "PAY_NOW",
                    "return_url": paypal_return_url(telegram_id, pack_id, "success"),
                    "cancel_url": paypal_return_url(telegram_id, pack_id, "cancel"),
                }
            }
        },
    }
    response = requests.post(
        f"{PAYPAL_API_BASE}/v2/checkout/orders",
        headers={**paypal_headers(), "PayPal-Request-Id": f"sylvex-{telegram_id}-{pack_id}-{uuid4().hex}"},
        json=body,
        timeout=30,
    )
    if response.status_code >= 400:
        print("PAYPAL ORDER ERROR:", response.status_code, response.text[:1000])
        raise RuntimeError("PayPal order request failed")
    return response.json()


# =====================================================
# PYTHON-БЛОК: paypal_approve_url
# Выполняет отдельный шаг backend-логики SYLVEX.
# Связан с API, базой данных, провайдерами или подготовкой данных для Mini App.
# =====================================================
def paypal_approve_url(order: dict) -> str:
    for link in order.get("links") or []:
        if link.get("rel") in {"approve", "payer-action"} and link.get("href"):
            return link["href"]
    return ""


# =====================================================
# СОХРАНЕНИЕ В БАЗУ ДАННЫХ: save_paypal_order
# Записывает состояние пользователя, job, metadata или результат генерации в общую базу Mini App и Telegram Bot.
# =====================================================
def save_paypal_order(telegram_id: int, pack_id: str, item: dict, order: dict, checkout_url: str):
    if not DATABASE_URL:
        return

    ensure_payment_tables()
    conn = db_connect(DATABASE_URL)
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO paypal_orders (
                telegram_id, pack_id, purchase_type, paypal_order_id, amount, currency, status, checkout_url, payload, raw_event
            )
            VALUES (%s, %s, %s, %s, %s, 'USD', %s, %s, %s, %s::jsonb)
            ON CONFLICT (paypal_order_id) DO UPDATE
            SET checkout_url = EXCLUDED.checkout_url,
                status = EXCLUDED.status,
                raw_event = EXCLUDED.raw_event,
                updated_at = CURRENT_TIMESTAMP
        """, (
            telegram_id,
            pack_id,
            paypal_purchase_type(item),
            order.get("id"),
            int(round(float(item["usd"]) * 100)),
            (order.get("status") or "created").lower(),
            checkout_url,
            shop_payload("paypal", telegram_id, pack_id, item),
            json.dumps(order),
        ))
        conn.commit()
    finally:
        cursor.close()
        conn.close()


# =====================================================
# PYTHON-БЛОК: verify_paypal_webhook
# Выполняет отдельный шаг backend-логики SYLVEX.
# Связан с API, базой данных, провайдерами или подготовкой данных для Mini App.
# =====================================================
def verify_paypal_webhook(headers, event: dict) -> bool:
    if not PAYPAL_WEBHOOK_ID:
        print("PAYPAL WEBHOOK: PAYPAL_WEBHOOK_ID is not configured")
        return False

    required = {
        "auth_algo": headers.get("paypal-auth-algo"),
        "cert_url": headers.get("paypal-cert-url"),
        "transmission_id": headers.get("paypal-transmission-id"),
        "transmission_sig": headers.get("paypal-transmission-sig"),
        "transmission_time": headers.get("paypal-transmission-time"),
    }
    if not all(required.values()):
        return False

    body = {
        **required,
        "webhook_id": PAYPAL_WEBHOOK_ID,
        "webhook_event": event,
    }
    bases = [PAYPAL_API_BASE]
    alternate = "https://api-m.paypal.com" if PAYPAL_API_BASE != "https://api-m.paypal.com" else "https://api-m.sandbox.paypal.com"
    bases.append(alternate)
    for base in bases:
        try:
            response = requests.post(
                f"{base}/v1/notifications/verify-webhook-signature",
                headers=paypal_headers(base),
                json=body,
                timeout=30,
            )
        except Exception as exc:
            print("PAYPAL WEBHOOK VERIFY ERROR:", base, exc)
            continue
        if response.status_code >= 400:
            print("PAYPAL WEBHOOK VERIFY ERROR:", base, response.status_code, response.text[:1000])
            continue
        if response.json().get("verification_status") == "SUCCESS":
            return True
    return False


# =====================================================
# PYTHON-БЛОК: paypal_capture_details
# Выполняет отдельный шаг backend-логики SYLVEX.
# Связан с API, базой данных, провайдерами или подготовкой данных для Mini App.
# =====================================================
def paypal_capture_details(resource: dict) -> dict:
    order_id = resource.get("supplementary_data", {}).get("related_ids", {}).get("order_id")
    capture_id = resource.get("id")
    amount = resource.get("amount") or {}
    return {
        "order_id": order_id,
        "capture_id": capture_id,
        "status": resource.get("status") or "",
        "amount": int(round(float(amount.get("value") or 0) * 100)),
        "currency": amount.get("currency_code") or "USD",
    }


# =====================================================
# PYTHON-БЛОК: finalize_paypal_capture
# Выполняет отдельный шаг backend-логики SYLVEX.
# Связан с API, базой данных, провайдерами или подготовкой данных для Mini App.
# =====================================================
def finalize_paypal_capture(event: dict) -> bool:
    resource = event.get("resource") or {}
    details = paypal_capture_details(resource)
    order_id = details["order_id"]
    capture_id = details["capture_id"]
    if not order_id or not capture_id:
        return False
    if (details["status"] or "").upper() != "COMPLETED":
        return False
    if not DATABASE_URL:
        return False

    ensure_payment_tables()
    conn = db_connect(DATABASE_URL)
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT telegram_id, pack_id, amount, currency, status, payload
            FROM paypal_orders
            WHERE paypal_order_id = %s
        """, (order_id,))
        row = cursor.fetchone()
        if not row:
            return False

        telegram_id, pack_id, stored_amount, stored_currency, status, payload = row
        if status == "completed":
            return False
        item = shop_item(pack_id)
        if not item:
            return False

        charge_id = f"paypal_capture_{capture_id}"
        created = finalize_shop_payment(
            telegram_id=int(telegram_id),
            provider="paypal",
            item=item,
            amount=details["amount"] or stored_amount,
            currency=details["currency"] or stored_currency or "USD",
            payload=payload or shop_payload("paypal", int(telegram_id), pack_id, item),
            charge_id=charge_id,
        )
        cursor.execute("""
            UPDATE paypal_orders
            SET paypal_capture_id = COALESCE(paypal_capture_id, %s),
                status = CASE WHEN %s THEN 'completed' ELSE status END,
                raw_event = %s::jsonb,
                updated_at = CURRENT_TIMESTAMP
            WHERE paypal_order_id = %s
        """, (capture_id, created, json.dumps(event), order_id))
        conn.commit()
        if created:
            try:
                sync_user_to_db({
                    "telegram_id": int(telegram_id),
                    "username": None,
                    "first_name": None,
                    "status": "free",
                    "balance": 0,
                })
            except Exception as exc:
                print("PAYPAL WEBHOOK: sync failed", exc)
        return created
    finally:
        cursor.close()
        conn.close()


# =====================================================
# PYTHON-БЛОК: paypal_subscription_pack_for_plan
# Выполняет отдельный шаг backend-логики SYLVEX.
# Связан с API, базой данных, провайдерами или подготовкой данных для Mini App.
# =====================================================
def paypal_subscription_pack_for_plan(plan_id: str, plan_type: str = "") -> str:
    normalized_type = (plan_type or "").strip().lower()
    if plan_id == PAYPAL_PRO_MONTHLY_PLAN_ID or normalized_type in {"month", "monthly"}:
        return "sub_month"
    if plan_id == PAYPAL_PRO_YEARLY_PLAN_ID or normalized_type in {"year", "yearly", "annual"}:
        return "sub_year"
    return ""


# =====================================================
# СОХРАНЕНИЕ В БАЗУ ДАННЫХ: save_paypal_subscription
# Записывает состояние пользователя, job, metadata или результат генерации в общую базу Mini App и Telegram Bot.
# =====================================================
def save_paypal_subscription(telegram_id: int, subscription_id: str, plan_id: str, plan_type: str = "") -> bool:
    if not DATABASE_URL:
        return False

    pack_id = paypal_subscription_pack_for_plan(plan_id, plan_type)
    item = shop_item(pack_id)
    if not item or not pack_id:
        return False

    ensure_payment_tables()
    ensure_user_exists(telegram_id)
    conn = db_connect(DATABASE_URL)
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO paypal_subscriptions (
                telegram_id, pack_id, plan_id, paypal_subscription_id, amount, currency, status, payload
            )
            VALUES (%s, %s, %s, %s, %s, 'USD', 'pending', %s)
            ON CONFLICT (paypal_subscription_id) DO UPDATE
            SET telegram_id = EXCLUDED.telegram_id,
                pack_id = EXCLUDED.pack_id,
                plan_id = EXCLUDED.plan_id,
                status = CASE
                    WHEN paypal_subscriptions.status = 'active' THEN paypal_subscriptions.status
                    ELSE 'pending'
                END,
                updated_at = CURRENT_TIMESTAMP
        """, (
            telegram_id,
            pack_id,
            plan_id,
            subscription_id,
            int(round(float(item["usd"]) * 100)),
            shop_payload("paypal_subscription", telegram_id, pack_id, item),
        ))
        conn.commit()
        return True
    finally:
        cursor.close()
        conn.close()


# =====================================================
# PYTHON-БЛОК: paypal_subscription_id_from_event
# Выполняет отдельный шаг backend-логики SYLVEX.
# Связан с API, базой данных, провайдерами или подготовкой данных для Mini App.
# =====================================================
def paypal_subscription_id_from_event(event: dict) -> str:
    resource = event.get("resource") or {}
    event_type = event.get("event_type") or ""
    if event_type.startswith("BILLING.SUBSCRIPTION."):
        return resource.get("id") or ""
    return (
        resource.get("billing_agreement_id")
        or resource.get("billing_subscription_id")
        or resource.get("subscription_id")
        or resource.get("supplementary_data", {}).get("related_ids", {}).get("billing_agreement_id")
        or ""
    )


# =====================================================
# PYTHON-БЛОК: paypal_subscription_payment_details
# Выполняет отдельный шаг backend-логики SYLVEX.
# Связан с API, базой данных, провайдерами или подготовкой данных для Mini App.
# =====================================================
def paypal_subscription_payment_details(event: dict) -> dict:
    resource = event.get("resource") or {}
    amount = resource.get("amount") or {}
    if "total" in amount:
        value = amount.get("total")
        currency = amount.get("currency") or "USD"
    else:
        value = amount.get("value")
        currency = amount.get("currency_code") or "USD"
    charge_id = resource.get("id") or paypal_subscription_id_from_event(event)
    try:
        cents = int(round(float(value or 5.0) * 100))
    except Exception:
        cents = 500
    return {"amount": cents, "currency": currency, "charge_id": charge_id}


# =====================================================
# PYTHON-БЛОК: activate_paypal_subscription_from_event
# Выполняет отдельный шаг backend-логики SYLVEX.
# Связан с API, базой данных, провайдерами или подготовкой данных для Mini App.
# =====================================================
def activate_paypal_subscription_from_event(event: dict) -> bool:
    subscription_id = paypal_subscription_id_from_event(event)
    if not subscription_id or not DATABASE_URL:
        return False

    details = paypal_subscription_payment_details(event)
    ensure_payment_tables()
    conn = db_connect(DATABASE_URL)
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT telegram_id, pack_id, amount, currency, status, payload
            FROM paypal_subscriptions
            WHERE paypal_subscription_id = %s
        """, (subscription_id,))
        row = cursor.fetchone()
        if not row:
            return False

        telegram_id, pack_id, stored_amount, stored_currency, status, payload = row
        item = shop_item(pack_id or "sub_month")
        if not item:
            return False

        event_type = event.get("event_type") or ""
        if status == "active":
            cursor.execute("""
                SELECT expires_at
                FROM subscriptions
                WHERE telegram_id = %s
                  AND status = 'active'
                ORDER BY expires_at DESC
                LIMIT 1
            """, (telegram_id,))
            active_row = cursor.fetchone()
            if active_row and active_row[0]:
                cursor.execute("SELECT CURRENT_TIMESTAMP + INTERVAL '7 days'")
                renewal_window = cursor.fetchone()[0]
                if active_row[0] > renewal_window:
                    return False

        charge_prefix = "paypal_sale" if event_type == "PAYMENT.SALE.COMPLETED" else "paypal_subscription"
        charge_source = details["charge_id"] or subscription_id
        charge_id = f"{charge_prefix}_{charge_source}"
        created = finalize_shop_payment(
            telegram_id=int(telegram_id),
            provider="paypal_subscription",
            item=item,
            amount=details["amount"] or stored_amount,
            currency=details["currency"] or stored_currency or "USD",
            payload=payload or shop_payload("paypal_subscription", int(telegram_id), pack_id, item),
            charge_id=charge_id,
        )
        cursor.execute("""
            UPDATE paypal_subscriptions
            SET status = CASE WHEN %s THEN 'active' ELSE status END,
                raw_event = %s::jsonb,
                updated_at = CURRENT_TIMESTAMP
            WHERE paypal_subscription_id = %s
        """, (created, json.dumps(event), subscription_id))
        conn.commit()
        if created:
            try:
                sync_user_to_db({
                    "telegram_id": int(telegram_id),
                    "username": None,
                    "first_name": None,
                    "status": "free",
                    "balance": 0,
                })
            except Exception as exc:
                print("PAYPAL SUBSCRIPTION WEBHOOK: sync failed", exc)
        return created
    finally:
        cursor.close()
        conn.close()

# =====================================================
# СОХРАНЕНИЕ В БАЗУ ДАННЫХ: save_kling_settings_to_db
# Записывает состояние пользователя, job, metadata или результат генерации в общую базу Mini App и Telegram Bot.
# =====================================================
def save_kling_settings_to_db(data):
    print("SAVE_KLING_FUNCTION_STARTED")
    duration_raw = str(data.get("duration", "5"))
    duration = int(duration_raw.split()[0])

    sound = 1 if data.get("sound") else 0
    prompt_enhance = 1 if data.get("prompt_enhance") else 0

    conn = db_connect(DATABASE_URL)
    cursor = conn.cursor()
    try:
        cursor.execute("""
        INSERT INTO user_ai_settings (
            telegram_id,
            kling_model,
            kling_mode,
            kling_ratio,
            kling_quality,
            kling_duration,
            kling_sound,
            kling_prompt_enhance
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (telegram_id) DO UPDATE SET
            kling_model = EXCLUDED.kling_model,
            kling_mode = EXCLUDED.kling_mode,
            kling_ratio = EXCLUDED.kling_ratio,
            kling_quality = EXCLUDED.kling_quality,
            kling_duration = EXCLUDED.kling_duration,
            kling_sound = EXCLUDED.kling_sound,
            kling_prompt_enhance = EXCLUDED.kling_prompt_enhance
        """, (
            int(data.get("telegram_id")), data.get("model"), data.get("mode"),
            data.get("ratio"), data.get("quality"), duration, sound, prompt_enhance,
        ))
        conn.commit()
    finally:
        cursor.close()
        conn.close()

# =====================================================
# API ENDPOINT: root
# Принимает HTTP-запрос от Mini App или Telegram Bot.
# Маршрут FastAPI: @app.get("/")
# Проверяет входные данные, работает с базой/провайдерами и возвращает JSON-ответ фронтенду.
# =====================================================
@app.get("/")
# =====================================================
# PYTHON-БЛОК: root
# Выполняет отдельный шаг backend-логики SYLVEX.
# Связан с API, базой данных, провайдерами или подготовкой данных для Mini App.
# =====================================================
async def root():
    return RedirectResponse("/webapp/index.html")


# =====================================================
# API ENDPOINT: cabinet
# Принимает HTTP-запрос от Mini App или Telegram Bot.
# Маршрут FastAPI: @app.get("/cabinet")
# Проверяет входные данные, работает с базой/провайдерами и возвращает JSON-ответ фронтенду.
# =====================================================
@app.get("/cabinet")
# =====================================================
# PYTHON-БЛОК: cabinet
# Выполняет отдельный шаг backend-логики SYLVEX.
# Связан с API, базой данных, провайдерами или подготовкой данных для Mini App.
# =====================================================
async def cabinet():
    return RedirectResponse("/webapp/index.html")

# =====================================================
# API ENDPOINT: shop
# Принимает HTTP-запрос от Mini App или Telegram Bot.
# Маршрут FastAPI: @app.get("/shop")
# Проверяет входные данные, работает с базой/провайдерами и возвращает JSON-ответ фронтенду.
# =====================================================
@app.get("/shop")
# =====================================================
# PYTHON-БЛОК: shop
# Выполняет отдельный шаг backend-логики SYLVEX.
# Связан с API, базой данных, провайдерами или подготовкой данных для Mini App.
# =====================================================
async def shop():
    return RedirectResponse("/webapp/index.html?view=shop")

# =====================================================
# API ENDPOINT: payments
# Принимает HTTP-запрос от Mini App или Telegram Bot.
# Маршрут FastAPI: @app.get("/payments")
# Проверяет входные данные, работает с базой/провайдерами и возвращает JSON-ответ фронтенду.
# =====================================================
@app.get("/payments")
# =====================================================
# PYTHON-БЛОК: payments
# Выполняет отдельный шаг backend-логики SYLVEX.
# Связан с API, базой данных, провайдерами или подготовкой данных для Mini App.
# =====================================================
async def payments():
    return FileResponse(WEBAPP_DIR / "payments.html")

# =====================================================
# API ENDPOINT: elevenlabs_page
# Принимает HTTP-запрос от Mini App или Telegram Bot.
# Маршрут FastAPI: @app.get("/elevenlabs")
# Проверяет входные данные, работает с базой/провайдерами и возвращает JSON-ответ фронтенду.
# =====================================================
@app.get("/elevenlabs")
# =====================================================
# PYTHON-БЛОК: elevenlabs_page
# Выполняет отдельный шаг backend-логики SYLVEX.
# Связан с API, базой данных, провайдерами или подготовкой данных для Mini App.
# =====================================================
async def elevenlabs_page():
    return FileResponse(WEBAPP_DIR / "elevenlabs.html")

# =====================================================
# API ENDPOINT: heygen_voice_page
# Принимает HTTP-запрос от Mini App или Telegram Bot.
# Маршрут FastAPI: @app.get("/heygen-voice")
# Проверяет входные данные, работает с базой/провайдерами и возвращает JSON-ответ фронтенду.
# =====================================================
@app.get("/heygen-voice")
# =====================================================
# PYTHON-БЛОК: heygen_voice_page
# Выполняет отдельный шаг backend-логики SYLVEX.
# Связан с API, базой данных, провайдерами или подготовкой данных для Mini App.
# =====================================================
async def heygen_voice_page():
    return FileResponse(WEBAPP_DIR / "heygen-voice.html")

# =====================================================
# PYTHON-БЛОК: ensure_elevenlabs_table
# Выполняет отдельный шаг backend-логики SYLVEX.
# Связан с API, базой данных, провайдерами или подготовкой данных для Mini App.
# =====================================================
def ensure_elevenlabs_table():
    if not DATABASE_URL:
        return

    conn = db_connect(DATABASE_URL)
    cursor = conn.cursor()
    try:
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_voice_settings (
            telegram_id BIGINT,
            provider TEXT DEFAULT 'elevenlabs',
            voice_id TEXT,
            voice_name TEXT,
            model_id TEXT,
            stability REAL DEFAULT 0.5,
            similarity_boost REAL DEFAULT 0.75,
            style REAL DEFAULT 0.0,
            speed REAL DEFAULT 1.0,
            speaker_boost INTEGER DEFAULT 1,
            language TEXT DEFAULT 'ru',
            output_format TEXT DEFAULT 'mp3_44100_128',
            updated_at TEXT,
            PRIMARY KEY (telegram_id, provider)
        )
        """)
        conn.commit()
    finally:
        cursor.close()
        conn.close()

# =====================================================
# PYTHON-БЛОК: default_elevenlabs_settings
# Выполняет отдельный шаг backend-логики SYLVEX.
# Связан с API, базой данных, провайдерами или подготовкой данных для Mini App.
# =====================================================
def default_elevenlabs_settings() -> dict:
    return {
        "voice_id": ELEVENLABS_DEFAULT_VOICE_ID,
        "voice_name": ELEVENLABS_DEFAULT_VOICE_NAME,
        "model_id": ELEVENLABS_DEFAULT_MODEL_ID,
        "stability": 0.5,
        "similarity_boost": 0.75,
        "style": 0.0,
        "speed": 1.0,
        "speaker_boost": True,
        "language": "ru",
        "output_format": ELEVENLABS_DEFAULT_OUTPUT_FORMAT,
    }

# =====================================================
# PYTHON-БЛОК: elevenlabs_headers
# Выполняет отдельный шаг backend-логики SYLVEX.
# Связан с API, базой данных, провайдерами или подготовкой данных для Mini App.
# =====================================================
def elevenlabs_headers(content_type: str = "application/json") -> dict:
    if not ELEVENLABS_API_KEY:
        raise RuntimeError("ELEVENLABS_API_KEY is not configured")

    headers = {"xi-api-key": ELEVENLABS_API_KEY}
    if content_type:
        headers["Content-Type"] = content_type
    return headers

# =====================================================
# PYTHON-БЛОК: fetch_elevenlabs_models
# Выполняет отдельный шаг backend-логики SYLVEX.
# Связан с API, базой данных, провайдерами или подготовкой данных для Mini App.
# =====================================================
def fetch_elevenlabs_models() -> list:
    response = requests.get(
        f"{ELEVENLABS_BASE_URL}/v1/models",
        headers=elevenlabs_headers(None),
        timeout=30,
    )
    if response.status_code >= 400:
        raise RuntimeError(response.text)

    data = response.json()
    models = data if isinstance(data, list) else data.get("models", [])
    result = []
    for model in models:
        model_id = model.get("model_id") or model.get("id")
        if not model_id:
            continue
        if model.get("can_do_text_to_speech", True) is False:
            continue
        result.append({
            "model_id": model_id,
            "name": model.get("name") or model_id,
        })
    return result

# =====================================================
# PYTHON-БЛОК: fetch_elevenlabs_voices
# Выполняет отдельный шаг backend-логики SYLVEX.
# Связан с API, базой данных, провайдерами или подготовкой данных для Mini App.
# =====================================================
def fetch_elevenlabs_voices(limit: int = 80) -> list:
    voices = []
    next_page_token = None

    while len(voices) < limit:
        params = {"page_size": min(100, limit - len(voices))}
        if next_page_token:
            params["next_page_token"] = next_page_token

        response = requests.get(
            f"{ELEVENLABS_BASE_URL}/v2/voices",
            headers=elevenlabs_headers(None),
            params=params,
            timeout=30,
        )
        if response.status_code >= 400:
            raise RuntimeError(response.text)

        data = response.json()
        page_voices = data.get("voices") or data.get("data") or []
        voices.extend(page_voices)
        next_page_token = data.get("next_page_token") or data.get("next_cursor")

        if not next_page_token or not data.get("has_more", bool(next_page_token)):
            break

    result = []
    for voice in voices[:limit]:
        labels = voice.get("labels") or {}
        fine_tuning = voice.get("fine_tuning") or {}
        voice_id = voice.get("voice_id")
        if not voice_id:
            continue
        result.append({
            "voice_id": voice_id,
            "name": voice.get("name") or "Voice",
            "category": voice.get("category") or labels.get("category") or "",
            "gender": labels.get("gender") or labels.get("sex") or "",
            "language": labels.get("language") or labels.get("accent") or voice.get("language") or "multilingual",
            "preview_url": voice.get("preview_url") or voice.get("sample_url") or "",
            "is_owner": voice.get("is_owner"),
            "sharing_enabled": voice.get("sharing") is not None,
            "fine_tuning_state": fine_tuning.get("state"),
        })
    return result

# =====================================================
# СОХРАНЕНИЕ В БАЗУ ДАННЫХ: get_elevenlabs_settings_from_db
# Записывает состояние пользователя, job, metadata или результат генерации в общую базу Mini App и Telegram Bot.
# =====================================================
def get_elevenlabs_settings_from_db(telegram_id: int) -> dict:
    defaults = default_elevenlabs_settings()
    if not DATABASE_URL or not telegram_id:
        return defaults

    ensure_elevenlabs_table()
    conn = db_connect(DATABASE_URL)
    cursor = conn.cursor()
    try:
        cursor.execute("""
        SELECT
            voice_id,
            voice_name,
            model_id,
            stability,
            similarity_boost,
            style,
            speed,
            speaker_boost,
            language,
            output_format
        FROM user_voice_settings
        WHERE telegram_id = %s
          AND provider = 'elevenlabs'
        """, (telegram_id,))
        row = cursor.fetchone()
    finally:
        cursor.close()
        conn.close()

    if not row:
        return defaults

    return {
        "voice_id": row[0] or defaults["voice_id"],
        "voice_name": row[1] or defaults["voice_name"],
        "model_id": row[2] or defaults["model_id"],
        "stability": row[3] if row[3] is not None else defaults["stability"],
        "similarity_boost": row[4] if row[4] is not None else defaults["similarity_boost"],
        "style": row[5] if row[5] is not None else defaults["style"],
        "speed": row[6] if row[6] is not None else defaults["speed"],
        "speaker_boost": bool(row[7]),
        "language": row[8] or defaults["language"],
        "output_format": row[9] or defaults["output_format"],
    }

# =====================================================
# СОХРАНЕНИЕ В БАЗУ ДАННЫХ: save_elevenlabs_settings_to_db
# Записывает состояние пользователя, job, metadata или результат генерации в общую базу Mini App и Telegram Bot.
# =====================================================
def save_elevenlabs_settings_to_db(data: dict):
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL is not configured")

    ensure_elevenlabs_table()
    print("ELEVENLABS SETTINGS SAVE REQUEST:", {
        "telegram_id": data.get("telegram_id"),
        "voice_id": data.get("voice_id"),
        "voice_name": data.get("voice_name"),
        "model_id": data.get("model_id"),
        "stability": data.get("stability"),
        "similarity_boost": data.get("similarity_boost"),
        "style": data.get("style"),
        "speed": data.get("speed"),
        "speaker_boost": data.get("speaker_boost"),
        "language": data.get("language"),
        "output_format": data.get("output_format"),
    })
    conn = db_connect(DATABASE_URL)
    cursor = conn.cursor()
    try:
        cursor.execute("""
        INSERT INTO user_voice_settings (
            telegram_id,
            provider,
            voice_id,
            voice_name,
            model_id,
            stability,
            similarity_boost,
            style,
            speed,
            speaker_boost,
            language,
            output_format,
            updated_at
        ) VALUES (%s, 'elevenlabs', %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW()::TEXT)
        ON CONFLICT (telegram_id, provider) DO UPDATE SET
            voice_id = EXCLUDED.voice_id,
            voice_name = EXCLUDED.voice_name,
            model_id = EXCLUDED.model_id,
            stability = EXCLUDED.stability,
            similarity_boost = EXCLUDED.similarity_boost,
            style = EXCLUDED.style,
            speed = EXCLUDED.speed,
            speaker_boost = EXCLUDED.speaker_boost,
            language = EXCLUDED.language,
            output_format = EXCLUDED.output_format,
            updated_at = EXCLUDED.updated_at
        """, (
            int(data.get("telegram_id")),
            data.get("voice_id") or ELEVENLABS_DEFAULT_VOICE_ID,
            data.get("voice_name") or ELEVENLABS_DEFAULT_VOICE_NAME,
            data.get("model_id") or ELEVENLABS_DEFAULT_MODEL_ID,
            float(data.get("stability", 0.5)),
            float(data.get("similarity_boost", 0.75)),
            float(data.get("style", 0.0)),
            float(data.get("speed", 1.0)),
            1 if data.get("speaker_boost", True) else 0,
            data.get("language") or "ru",
            data.get("output_format") or ELEVENLABS_DEFAULT_OUTPUT_FORMAT,
        ))
        conn.commit()
    finally:
        cursor.close()
        conn.close()

# =====================================================
# PYTHON-БЛОК: default_heygen_voice_settings
# Выполняет отдельный шаг backend-логики SYLVEX.
# Связан с API, базой данных, провайдерами или подготовкой данных для Mini App.
# =====================================================
def default_heygen_voice_settings() -> dict:
    return {
        "voice_id": "",
        "voice_name": "Auto",
        "model_id": HEYGEN_VOICE_MODEL_ID,
        "language": HEYGEN_DEFAULT_LANGUAGE,
        "speed": HEYGEN_DEFAULT_SPEED,
        "output_format": HEYGEN_DEFAULT_OUTPUT_FORMAT,
    }

# =====================================================
# PYTHON-БЛОК: heygen_headers
# Выполняет отдельный шаг backend-логики SYLVEX.
# Связан с API, базой данных, провайдерами или подготовкой данных для Mini App.
# =====================================================
def heygen_headers() -> dict:
    if not HEYGEN_API_KEY:
        raise RuntimeError("HEYGEN_API_KEY is not configured")

    return {
        "x-api-key": HEYGEN_API_KEY,
        "Authorization": f"Bearer {HEYGEN_API_KEY}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

# =====================================================
# PYTHON-БЛОК: fetch_heygen_brand_kits
# Загружает список Brand Kits из HeyGen через официальный GET /v3/brand-kits.
# Возвращает только данные, нужные Mini App для выбора brand_kit_id.
# =====================================================
def fetch_heygen_brand_kits() -> dict:
    response = requests.get(
        f"{HEYGEN_BASE_URL}/brand-kits",
        headers=heygen_headers(),
        timeout=30,
    )
    if response.status_code >= 400:
        raise RuntimeError(response.text)
    data = response.json()
    kits = data.get("data") if isinstance(data.get("data"), list) else []
    return {
        "brand_kits": kits,
        "has_more": bool(data.get("has_more")),
        "default_brand_kit_id": (kits[0] or {}).get("brand_kit_id") if kits else "",
    }

def _heygen_data_list(data: dict) -> list:
    raw = data.get("data") if isinstance(data, dict) else {}
    if isinstance(raw, list):
        return raw
    if isinstance(raw, dict):
        for key in ("items", "list", "avatar_looks", "looks", "avatars"):
            value = raw.get(key)
            if isinstance(value, list):
                return value
    return []

def fetch_heygen_avatar_look(avatar_id: str) -> dict:
    avatar_id = str(avatar_id or "").strip()
    if not avatar_id:
        return {}
    now = time.time()
    cached = HEYGEN_AVATAR_LOOK_CACHE.get(avatar_id)
    if cached and now < float(cached.get("expires_at") or 0):
        return dict(cached.get("value") or {})
    for ownership in ("private", "public"):
        response = requests.get(
            f"{HEYGEN_BASE_URL}/avatars/looks",
            headers=heygen_headers(),
            params={"ownership": ownership, "limit": 100},
            timeout=30,
        )
        if response.status_code >= 400:
            raise RuntimeError(response.text)
        for item in _heygen_data_list(response.json()):
            if str((item or {}).get("id") or "") == avatar_id:
                value = item or {}
                HEYGEN_AVATAR_LOOK_CACHE[avatar_id] = {"expires_at": now + HEYGEN_AVATAR_LOOK_CACHE_TTL, "value": value}
                return value
    HEYGEN_AVATAR_LOOK_CACHE[avatar_id] = {"expires_at": now + HEYGEN_AVATAR_LOOK_CACHE_TTL, "value": {}}
    return {}

def visual_stats_payload(resource_id: str, resource_type: str, telegram_id: int = 0, heygen_avatar_id: str = "") -> dict:
    def stat_int(value) -> int:
        try:
            return int(value or 0)
        except Exception:
            return 0

    stats = {"likes": 0, "selects": 0, "liked": False, "favorite": False, "heygen": {}}
    heygen_avatar_id = str(heygen_avatar_id or "").strip()
    if heygen_avatar_id:
        try:
            heygen = fetch_heygen_avatar_look(heygen_avatar_id)
            stats["heygen"] = {
                "id": heygen.get("id") or heygen_avatar_id,
                "name": heygen.get("name") or "",
                "status": heygen.get("status") or "",
                "preview_image_url": heygen.get("preview_image_url") or heygen.get("preview_image") or heygen.get("image_url") or "",
                "preview_video_url": heygen.get("preview_video_url") or heygen.get("preview_video") or heygen.get("video_url") or "",
                "supported_engines": heygen.get("supported_engines") or heygen.get("engines") or [],
                "likes": stat_int(heygen.get("likes") or heygen.get("likes_count") or heygen.get("like_count")),
                "uses": stat_int(heygen.get("uses") or heygen.get("usage_count") or heygen.get("selects_count")),
            }
        except Exception as exc:
            stats["heygen"] = {"id": heygen_avatar_id, "error": str(exc)[:240]}
    if not DATABASE_URL or not resource_id:
        return stats
    try:
        ensure_prostudio_table()
        conn = db_connect(DATABASE_URL)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT likes_count, selects_count FROM prostudio_visual_stats WHERE resource_id = %s AND resource_type = %s",
            (resource_id, resource_type),
        )
        row = cursor.fetchone()
        if row:
            stats["likes"] = int(row[0] or 0)
            stats["selects"] = int(row[1] or 0)
        if telegram_id:
            cursor.execute(
                "SELECT liked, favorite FROM prostudio_visual_user_state WHERE telegram_id = %s AND resource_id = %s AND resource_type = %s",
                (telegram_id, resource_id, resource_type),
            )
            user_row = cursor.fetchone()
            if user_row:
                stats["liked"] = bool(user_row[0])
                stats["favorite"] = bool(user_row[1])
        cursor.close()
        conn.close()
    except Exception as exc:
        print("VISUAL STATS LOAD FAILED:", exc)
    return stats

def update_visual_interaction(telegram_id: int, resource_id: str, resource_type: str, action: str, value=None) -> dict:
    resource_type = "character" if resource_type in {"character", "characters"} else "object"
    action = str(action or "").strip().lower()
    if not DATABASE_URL or not telegram_id or not resource_id:
        return {"ok": False, "local_only": True}
    ensure_prostudio_table()
    conn = db_connect(DATABASE_URL)
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            INSERT INTO prostudio_visual_user_state (telegram_id, resource_id, resource_type)
            VALUES (%s, %s, %s)
            ON CONFLICT (telegram_id, resource_id, resource_type) DO NOTHING
            """,
            (telegram_id, resource_id, resource_type),
        )
        cursor.execute(
            """
            INSERT INTO prostudio_visual_stats (resource_id, resource_type)
            VALUES (%s, %s)
            ON CONFLICT (resource_id, resource_type) DO NOTHING
            """,
            (resource_id, resource_type),
        )
        if action == "like":
            liked = bool(value)
            cursor.execute(
                "SELECT liked FROM prostudio_visual_user_state WHERE telegram_id = %s AND resource_id = %s AND resource_type = %s",
                (telegram_id, resource_id, resource_type),
            )
            previous = bool((cursor.fetchone() or [False])[0])
            if previous != liked:
                cursor.execute(
                    "UPDATE prostudio_visual_stats SET likes_count = GREATEST(0, likes_count + %s), updated_at = NOW() WHERE resource_id = %s AND resource_type = %s",
                    (1 if liked else -1, resource_id, resource_type),
                )
            cursor.execute(
                "UPDATE prostudio_visual_user_state SET liked = %s, updated_at = NOW() WHERE telegram_id = %s AND resource_id = %s AND resource_type = %s",
                (liked, telegram_id, resource_id, resource_type),
            )
        elif action == "favorite":
            cursor.execute(
                "UPDATE prostudio_visual_user_state SET favorite = %s, updated_at = NOW() WHERE telegram_id = %s AND resource_id = %s AND resource_type = %s",
                (bool(value), telegram_id, resource_id, resource_type),
            )
        elif action == "select":
            cursor.execute(
                "UPDATE prostudio_visual_stats SET selects_count = selects_count + 1, updated_at = NOW() WHERE resource_id = %s AND resource_type = %s",
                (resource_id, resource_type),
            )
            cursor.execute(
                "UPDATE prostudio_visual_user_state SET selected_count = selected_count + 1, updated_at = NOW() WHERE telegram_id = %s AND resource_id = %s AND resource_type = %s",
                (telegram_id, resource_id, resource_type),
            )
        conn.commit()
    finally:
        cursor.close()
        conn.close()
    return {"ok": True}

# =====================================================
# PYTHON-БЛОК: fetch_heygen_voice_page
# Выполняет отдельный шаг backend-логики SYLVEX.
# Связан с API, базой данных, провайдерами или подготовкой данных для Mini App.
# =====================================================
def fetch_heygen_voice_page(
    voice_type: str = "public",
    language: str = "",
    gender: str = "",
    token: str = "",
    limit: int = 100,
) -> dict:
    params = {
        "type": voice_type,
        "engine": HEYGEN_VOICE_MODEL_ID,
        "limit": limit,
    }

    if language:
        params["language"] = language
    if gender:
        params["gender"] = gender
    if token:
        params["token"] = token

    response = requests.get(
        f"{HEYGEN_BASE_URL}/voices",
        headers=heygen_headers(),
        params=params,
        timeout=30,
    )
    if response.status_code >= 400:
        raise RuntimeError(response.text)

    data = response.json()
    return {
        "voices": data.get("data") or [],
        "has_more": data.get("has_more", False),
        "next_token": data.get("next_token"),
    }

# =====================================================
# PYTHON-БЛОК: fetch_heygen_voices
# Выполняет отдельный шаг backend-логики SYLVEX.
# Связан с API, базой данных, провайдерами или подготовкой данных для Mini App.
# =====================================================
def fetch_heygen_voices(limit: int = 100) -> list:
    voices = []

    for voice_type in ("public", "private"):
        token = ""
        while len(voices) < limit:
            page = fetch_heygen_voice_page(
                voice_type=voice_type,
                token=token,
                limit=min(100, limit - len(voices)),
            )
            voices.extend(page["voices"])
            if not page["has_more"] or not page["next_token"]:
                break
            token = page["next_token"]

        if len(voices) >= limit:
            break

    result = []
    seen = set()
    for voice in voices[:limit]:
        voice_id = voice.get("voice_id")
        if not voice_id or voice_id in seen:
            continue
        seen.add(voice_id)
        result.append({
            "voice_id": voice_id,
            "name": voice.get("name") or "Voice",
            "language": voice.get("language") or "",
            "gender": voice.get("gender") or "",
            "type": voice.get("type") or "",
            "preview_audio_url": voice.get("preview_audio_url") or "",
            "support_pause": bool(voice.get("support_pause")),
            "support_locale": bool(voice.get("support_locale")),
        })
    return result

# =====================================================
# СОХРАНЕНИЕ В БАЗУ ДАННЫХ: get_heygen_voice_settings_from_db
# Записывает состояние пользователя, job, metadata или результат генерации в общую базу Mini App и Telegram Bot.
# =====================================================
def get_heygen_voice_settings_from_db(telegram_id: int) -> dict:
    defaults = default_heygen_voice_settings()
    if not DATABASE_URL or not telegram_id:
        return defaults

    ensure_elevenlabs_table()
    conn = db_connect(DATABASE_URL)
    cursor = conn.cursor()
    try:
        cursor.execute("""
        SELECT
            voice_id,
            voice_name,
            model_id,
            speed,
            language,
            output_format
        FROM user_voice_settings
        WHERE telegram_id = %s
          AND provider = 'heygen_voice'
        """, (telegram_id,))
        row = cursor.fetchone()
    finally:
        cursor.close()
        conn.close()

    if not row:
        return defaults

    return {
        "voice_id": row[0] or defaults["voice_id"],
        "voice_name": row[1] or defaults["voice_name"],
        "model_id": row[2] or defaults["model_id"],
        "speed": row[3] if row[3] is not None else defaults["speed"],
        "language": row[4] or defaults["language"],
        "output_format": row[5] or defaults["output_format"],
    }

# =====================================================
# СОХРАНЕНИЕ В БАЗУ ДАННЫХ: save_heygen_voice_settings_to_db
# Записывает состояние пользователя, job, metadata или результат генерации в общую базу Mini App и Telegram Bot.
# =====================================================
def save_heygen_voice_settings_to_db(data: dict):
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL is not configured")

    ensure_elevenlabs_table()
    print("HEYGEN VOICE SETTINGS SAVE REQUEST:", {
        "telegram_id": data.get("telegram_id"),
        "voice_id": data.get("voice_id"),
        "voice_name": data.get("voice_name"),
        "model_id": HEYGEN_VOICE_MODEL_ID,
        "speed": data.get("speed"),
        "language": data.get("language"),
        "output_format": data.get("output_format"),
    })
    conn = db_connect(DATABASE_URL)
    cursor = conn.cursor()
    try:
        cursor.execute("""
        INSERT INTO user_voice_settings (
            telegram_id,
            provider,
            voice_id,
            voice_name,
            model_id,
            speed,
            language,
            output_format,
            updated_at
        ) VALUES (%s, 'heygen_voice', %s, %s, %s, %s, %s, %s, NOW()::TEXT)
        ON CONFLICT (telegram_id, provider) DO UPDATE SET
            voice_id = EXCLUDED.voice_id,
            voice_name = EXCLUDED.voice_name,
            model_id = EXCLUDED.model_id,
            speed = EXCLUDED.speed,
            language = EXCLUDED.language,
            output_format = EXCLUDED.output_format,
            updated_at = EXCLUDED.updated_at
        """, (
            int(data.get("telegram_id")),
            data.get("voice_id") or "",
            data.get("voice_name") or "HeyGen Voice",
            HEYGEN_VOICE_MODEL_ID,
            float(data.get("speed", HEYGEN_DEFAULT_SPEED)),
            data.get("language") or HEYGEN_DEFAULT_LANGUAGE,
            data.get("output_format") or HEYGEN_DEFAULT_OUTPUT_FORMAT,
        ))
        conn.commit()
    finally:
        cursor.close()
        conn.close()

# =====================================================
# PYTHON-БЛОК: safe_log_elevenlabs_preview
# Выполняет отдельный шаг backend-логики SYLVEX.
# Связан с API, базой данных, провайдерами или подготовкой данных для Mini App.
# =====================================================
def safe_log_elevenlabs_preview(data: dict, payload: dict):
    print("ELEVENLABS PREVIEW REQUEST BODY:", {
        "telegram_id": data.get("telegram_id"),
        "voice_id": data.get("voice_id"),
        "voice_name": data.get("voice_name"),
        "model_id": data.get("model_id"),
        "stability": data.get("stability"),
        "similarity_boost": data.get("similarity_boost"),
        "style": data.get("style"),
        "speed": data.get("speed"),
        "speaker_boost": data.get("speaker_boost"),
        "language": data.get("language"),
        "output_format": data.get("output_format"),
        "text_length": len(data.get("text") or ""),
    })
    print("ELEVENLABS PREVIEW PAYLOAD:", {
        "text_length": len(payload.get("text") or ""),
        "model_id": payload.get("model_id"),
        "voice_settings": payload.get("voice_settings"),
    })

# =====================================================
# API ENDPOINT: elevenlabs_bootstrap
# Принимает HTTP-запрос от Mini App или Telegram Bot.
# Маршрут FastAPI: @app.get("/api/elevenlabs/bootstrap")
# Проверяет входные данные, работает с базой/провайдерами и возвращает JSON-ответ фронтенду.
# =====================================================
@app.get("/api/elevenlabs/bootstrap")
# =====================================================
# PYTHON-БЛОК: elevenlabs_bootstrap
# Выполняет отдельный шаг backend-логики SYLVEX.
# Связан с API, базой данных, провайдерами или подготовкой данных для Mini App.
# =====================================================
async def elevenlabs_bootstrap(telegram_id: int = 0):
    warnings = []
    try:
        models = fetch_elevenlabs_models()
    except Exception as exc:
        print("ELEVENLABS MODELS LOAD FAILED:", exc)
        warnings.append(f"models: {exc}")
        models = [{
            "model_id": ELEVENLABS_DEFAULT_MODEL_ID,
            "name": "Eleven Multilingual v2",
        }]

    try:
        voices = fetch_elevenlabs_voices()
    except Exception as exc:
        print("ELEVENLABS VOICES LOAD FAILED:", exc)
        warnings.append(f"voices: {exc}")
        voices = [{
            "voice_id": ELEVENLABS_DEFAULT_VOICE_ID,
            "name": ELEVENLABS_DEFAULT_VOICE_NAME,
            "category": "premade",
            "gender": "female",
            "language": "multilingual",
            "preview_url": "",
        }]

    return {
        "success": True,
        "models": models,
        "voices": voices,
        "settings": get_elevenlabs_settings_from_db(telegram_id),
        "defaults": default_elevenlabs_settings(),
        "warnings": warnings,
        "api_available": not warnings,
    }

# =====================================================
# API ENDPOINT: save_elevenlabs_settings
# Принимает HTTP-запрос от Mini App или Telegram Bot.
# Маршрут FastAPI: @app.post("/api/elevenlabs/settings")
# Проверяет входные данные, работает с базой/провайдерами и возвращает JSON-ответ фронтенду.
# =====================================================
@app.post("/api/elevenlabs/settings")
# =====================================================
# СОХРАНЕНИЕ В БАЗУ ДАННЫХ: save_elevenlabs_settings
# Записывает состояние пользователя, job, metadata или результат генерации в общую базу Mini App и Telegram Bot.
# =====================================================
async def save_elevenlabs_settings(request: Request):
    data = await request.json()
    telegram_id = data.get("telegram_id")
    if not telegram_id:
        return JSONResponse({"success": False, "error": "telegram_id is required"}, status_code=400)

    save_elevenlabs_settings_to_db(data)
    return {"success": True, "message": "ElevenLabs settings saved"}

# =====================================================
# API ENDPOINT: elevenlabs_preview
# Принимает HTTP-запрос от Mini App или Telegram Bot.
# Маршрут FastAPI: @app.post("/api/elevenlabs/preview")
# Проверяет входные данные, работает с базой/провайдерами и возвращает JSON-ответ фронтенду.
# =====================================================
@app.post("/api/elevenlabs/preview")
# =====================================================
# PYTHON-БЛОК: elevenlabs_preview
# Выполняет отдельный шаг backend-логики SYLVEX.
# Связан с API, базой данных, провайдерами или подготовкой данных для Mini App.
# =====================================================
async def elevenlabs_preview(request: Request):
    data = await request.json()
    voice_id = data.get("voice_id") or ELEVENLABS_DEFAULT_VOICE_ID
    model_id = data.get("model_id") or ELEVENLABS_DEFAULT_MODEL_ID
    output_format = data.get("output_format") or ELEVENLABS_DEFAULT_OUTPUT_FORMAT
    text = (data.get("text") or "SYLVEX voice preview.").strip()[:220]

    payload = {
        "text": text,
        "model_id": model_id,
        "voice_settings": {
            "stability": float(data.get("stability", 0.5)),
            "similarity_boost": float(data.get("similarity_boost", 0.75)),
            "style": float(data.get("style", 0.0)),
            "speed": float(data.get("speed", 1.0)),
            "use_speaker_boost": bool(data.get("speaker_boost", True)),
        },
    }

    safe_log_elevenlabs_preview(data, payload)
    print("ELEVENLABS PREVIEW SELECTED VOICE:", voice_id)
    print("ELEVENLABS PREVIEW SELECTED MODEL:", model_id)

    try:
        response = requests.post(
            f"{ELEVENLABS_BASE_URL}/v1/text-to-speech/{voice_id}",
            headers=elevenlabs_headers(),
            params={"output_format": output_format},
            json=payload,
            timeout=60,
        )
    except Exception as exc:
        print("ELEVENLABS PREVIEW REQUEST FAILED:", repr(exc))
        return JSONResponse({
            "success": False,
            "error": str(exc),
        }, status_code=502)

    content_type = response.headers.get("content-type", "")
    print("ELEVENLABS PREVIEW HTTP STATUS:", response.status_code)
    print("ELEVENLABS PREVIEW CONTENT-TYPE:", content_type)

    if response.status_code >= 400:
        print("ELEVENLABS PREVIEW ERROR RESPONSE:", response.text[:2000])
        return JSONResponse({
            "success": False,
            "error": response.text,
            "elevenlabs_status": response.status_code,
            "elevenlabs_content_type": content_type,
        }, status_code=502)

    if not response.content:
        print("ELEVENLABS PREVIEW EMPTY AUDIO RESPONSE")
        return JSONResponse({
            "success": False,
            "error": "ElevenLabs returned empty audio",
            "elevenlabs_status": response.status_code,
            "elevenlabs_content_type": content_type,
        }, status_code=502)

    if "audio" not in content_type and "octet-stream" not in content_type:
        print("ELEVENLABS PREVIEW NON-AUDIO RESPONSE:", response.text[:2000])
        return JSONResponse({
            "success": False,
            "error": "ElevenLabs returned non-audio response",
            "elevenlabs_status": response.status_code,
            "elevenlabs_content_type": content_type,
            "body": response.text[:2000],
        }, status_code=502)

    print("ELEVENLABS PREVIEW AUDIO BYTES:", len(response.content))
    return Response(
        content=response.content,
        media_type=content_type.split(";")[0] if content_type else "audio/mpeg",
        headers={"Cache-Control": "no-store"}
    )

# =====================================================
# API ENDPOINT: public_prostudio_voice_preview
# Генерирует короткий preview выбранного Gemini TTS или Runway TTS голоса для Mini App.
# Не создаёт job, не пишет историю генераций и не списывает баланс.
# =====================================================
@app.post("/api/public/prostudio/voice-preview")
async def public_prostudio_voice_preview(request: Request):
    data = await request.json()
    model = str(data.get("model") or "")
    if model.startswith("elevenlabs_") or model in {"eleven_v3", "eleven_multilingual_v2", "eleven_flash_v2_5", "eleven_flash_v2"}:
        result = await elevenlabs_voice_preview(data)
    elif model.startswith("runway_") or model in {"eleven_multilingual_v2"}:
        result = await runway_voice_preview(data)
    else:
        result = await gemini_tts_voice_preview(data)
    status_code = 200 if result.get("ok") or result.get("success") else 502
    return JSONResponse(result, status_code=status_code)


# =====================================================
# API ENDPOINT: public_prostudio_preset_catalog
# Автоматически собирает файловый каталог персонажей и объектов из backend/preset_catalog.
# =====================================================
@app.get("/api/public/prostudio/preset-catalog")
async def public_prostudio_preset_catalog():
    catalog = load_preset_catalog()
    return JSONResponse(
        {"ok": True, "catalog": catalog, **catalog},
        headers={"Cache-Control": f"public, max-age={PRESET_CATALOG_CACHE_TTL}"},
    )


# =====================================================
# API ENDPOINT: public_prostudio_voice_avatars
# Возвращает аватарки голосов из backend/preset_catalog/voice_avatars.
# =====================================================
@app.get("/api/public/prostudio/voice-avatars")
async def public_prostudio_voice_avatars():
    catalog = load_voice_avatar_catalog()
    return {"ok": True, **catalog}


@app.post("/api/public/prostudio/voice-avatars/ensure")
async def public_prostudio_ensure_voice_avatars(request: Request):
    payload = await request.json()
    voices = payload.get("voices") if isinstance(payload, dict) else []
    batch = [item for item in (voices if isinstance(voices, list) else [])[:100] if isinstance(item, dict)]
    schedule_voice_avatars_batch(batch)
    scheduled = len(batch)
    return {"ok": True, "scheduled": scheduled, **load_voice_avatar_catalog()}


@app.get("/api/public/prostudio/voice-avatar/{avatar_key}")
async def public_prostudio_voice_avatar_image(avatar_key: str):
    safe_key = re.sub(r"[^a-f0-9]", "", str(avatar_key or "").lower())[:40]
    if len(safe_key) != 40:
        return Response(status_code=404)
    storage_key = generated_key("voice-avatars", f"{safe_key}.png")
    if storage_exists(storage_key):
        body, content_type, content_length = await asyncio.to_thread(storage_get_object, storage_key)
        headers = {"Cache-Control": "public, max-age=31536000, immutable"}
        if content_length is not None:
            headers["Content-Length"] = str(content_length)
        return StreamingResponse(storage_iter_object(body), media_type=content_type, headers=headers)
    local_path = VOICE_GENERATED_AVATARS_DIR / f"{safe_key}.png"
    if local_path.exists():
        return FileResponse(local_path, media_type="image/png", headers={"Cache-Control": "public, max-age=31536000, immutable"})
    if DATABASE_URL:
        try:
            conn = db_connect(DATABASE_URL); cursor = conn.cursor()
            cursor.execute("SELECT image_data, content_type FROM prostudio_voice_avatars WHERE avatar_key=%s AND status='ready'", (safe_key,))
            row = cursor.fetchone(); cursor.close(); conn.close()
            if row and row[0]:
                image_bytes = bytes(row[0])
                try:
                    storage_put_bytes(image_bytes, storage_key, row[1] or "image/png")
                except Exception:
                    pass
                return Response(content=image_bytes, media_type=row[1] or "image/png", headers={"Cache-Control": "public, max-age=31536000, immutable"})
        except Exception as exc:
            print("VOICE AVATAR READ FAILED:", exc)
    return Response(status_code=404)


# =====================================================
# API ENDPOINT: public_prostudio_runway_voices
# Возвращает список голосов Runway для шторки выбора озвучки в Mini App.
# =====================================================
@app.get("/api/public/prostudio/runway-voices")
async def public_prostudio_runway_voices():
    result = await fetch_runway_voices()
    if isinstance(result, dict) and isinstance(result.get("voices"), list):
        result["voices"] = attach_voice_avatars(result["voices"], "runway")
    status_code = 200 if result.get("ok") or result.get("success") else 502
    return JSONResponse(result, status_code=status_code)


# =====================================================
# API ENDPOINT: public_prostudio_elevenlabs_voices
# Возвращает список голосов ElevenLabs для шторки выбора озвучки в Mini App.
# =====================================================
@app.get("/api/public/prostudio/elevenlabs-voices")
async def public_prostudio_elevenlabs_voices():
    result = await fetch_elevenlabs_prostudio_voices()
    if isinstance(result, dict) and isinstance(result.get("voices"), list):
        result["voices"] = attach_voice_avatars(result["voices"], "elevenlabs")
    status_code = 200 if result.get("ok") or result.get("success") else 502
    return JSONResponse(result, status_code=status_code)

# =====================================================
# API ENDPOINT: heygen_voice_bootstrap
# Принимает HTTP-запрос от Mini App или Telegram Bot.
# Маршрут FastAPI: @app.get("/api/heygen-voice/bootstrap")
# Проверяет входные данные, работает с базой/провайдерами и возвращает JSON-ответ фронтенду.
# =====================================================
@app.get("/api/heygen-voice/bootstrap")
# =====================================================
# PYTHON-БЛОК: heygen_voice_bootstrap
# Выполняет отдельный шаг backend-логики SYLVEX.
# Связан с API, базой данных, провайдерами или подготовкой данных для Mini App.
# =====================================================
async def heygen_voice_bootstrap(telegram_id: int = 0):
    warnings = []
    try:
        voices = fetch_heygen_voices()
    except Exception as exc:
        print("HEYGEN VOICE LOAD FAILED:", exc)
        warnings.append(str(exc))
        voices = []

    return {
        "success": True,
        "model": {
            "model_id": HEYGEN_VOICE_MODEL_ID,
            "name": "HeyGen Starfish",
        },
        "voices": voices,
        "settings": get_heygen_voice_settings_from_db(telegram_id),
        "defaults": default_heygen_voice_settings(),
        "warnings": warnings,
        "api_available": not warnings,
    }

# =====================================================
# API ENDPOINT: heygen_brand_kits
# Возвращает Brand Kits HeyGen для дальнейшей передачи brand_kit_id в генерацию.
# Маршрут использует официальный запрос HeyGen GET /v3/brand-kits.
# =====================================================
@app.get("/api/public/heygen/brand-kits")
async def heygen_brand_kits():
    try:
        data = fetch_heygen_brand_kits()
        return {"success": True, **data}
    except Exception as exc:
        print("HEYGEN BRAND KITS LOAD FAILED:", exc)
        return JSONResponse(
            {
                "success": False,
                "error": "Не удалось загрузить HeyGen Brand Kits",
                "brand_kits": [],
                "default_brand_kit_id": "",
            },
            status_code=502,
        )


@app.get("/api/public/prostudio/visual-stats")
async def public_prostudio_visual_stats(
    resource_id: str,
    resource_type: str = "character",
    telegram_id: int = 0,
    heygen_avatar_id: str = "",
):
    return {
        "ok": True,
        "stats": visual_stats_payload(resource_id, resource_type, telegram_id, heygen_avatar_id),
    }


@app.post("/api/public/prostudio/visual-interaction")
async def public_prostudio_visual_interaction(request: Request):
    data = await request.json()
    telegram_id = int(data.get("telegram_id") or 0)
    resource_id = str(data.get("resource_id") or "").strip()
    resource_type = str(data.get("resource_type") or "character").strip()
    heygen_avatar_id = str(data.get("heygen_avatar_id") or "").strip()
    result = update_visual_interaction(
        telegram_id,
        resource_id,
        resource_type,
        data.get("action"),
        data.get("value"),
    )
    return {
        "ok": True,
        "result": result,
        "stats": visual_stats_payload(resource_id, resource_type, telegram_id, heygen_avatar_id),
    }

# =====================================================
# API ENDPOINT: save_heygen_voice_settings
# Принимает HTTP-запрос от Mini App или Telegram Bot.
# Маршрут FastAPI: @app.post("/api/heygen-voice/settings")
# Проверяет входные данные, работает с базой/провайдерами и возвращает JSON-ответ фронтенду.
# =====================================================
@app.post("/api/heygen-voice/settings")
# =====================================================
# СОХРАНЕНИЕ В БАЗУ ДАННЫХ: save_heygen_voice_settings
# Записывает состояние пользователя, job, metadata или результат генерации в общую базу Mini App и Telegram Bot.
# =====================================================
async def save_heygen_voice_settings(request: Request):
    data = await request.json()
    telegram_id = data.get("telegram_id")
    if not telegram_id:
        return JSONResponse({"success": False, "error": "telegram_id is required"}, status_code=400)
    if not data.get("voice_id"):
        return JSONResponse({"success": False, "error": "voice_id is required"}, status_code=400)

    save_heygen_voice_settings_to_db(data)
    return {"success": True, "message": "HeyGen Voice settings saved"}

# =====================================================
# API ENDPOINT: public_config
# Принимает HTTP-запрос от Mini App или Telegram Bot.
# Маршрут FastAPI: @app.get("/api/public/config")
# Проверяет входные данные, работает с базой/провайдерами и возвращает JSON-ответ фронтенду.
# =====================================================
@app.get("/api/public/config")
# =====================================================
# PYTHON-БЛОК: public_config
# Выполняет отдельный шаг backend-логики SYLVEX.
# Связан с API, базой данных, провайдерами или подготовкой данных для Mini App.
# =====================================================
async def public_config():
    return {
        "ok": True,
        "webapp_url": WEBAPP_URL,
        "payment_webapp_url": PAYMENT_WEBAPP_URL,
        "shop_webapp_url": SHOP_WEBAPP_URL
    }

# =====================================================
# API ENDPOINT: payment_links
# Принимает HTTP-запрос от Mini App или Telegram Bot.
# Маршрут FastAPI: @app.get("/api/payment-links")
# Проверяет входные данные, работает с базой/провайдерами и возвращает JSON-ответ фронтенду.
# =====================================================
@app.get("/api/payment-links")
# =====================================================
# PYTHON-БЛОК: payment_links
# Выполняет отдельный шаг backend-логики SYLVEX.
# Связан с API, базой данных, провайдерами или подготовкой данных для Mini App.
# =====================================================
async def payment_links():
    products = []
    for pack_id, item in SHOP_ITEMS.items():
        products.append({
            "id": pack_id,
            "pack_id": pack_id,
            "name": item["title"],
            "description": "Подписка SYLVEX Pro" if item["kind"] == "subscription" else f"{item['credits']} токенов SYLVEX",
            "price": int(round(float(item["usd"]) * 100)),
            "price_formatted": f"${float(item['usd']):.2f}",
            "is_subscription": item["kind"] == "subscription",
            "purchase_type": paypal_purchase_type(item),
        })

    return {
        "success": True,
        "source": "paypal",
        "products": products,
        "packages": {},
    }

# =====================================================
# API ENDPOINT: save_settings
# Принимает HTTP-запрос от Mini App или Telegram Bot.
# Маршрут FastAPI: @app.post("/save-settings")
# Проверяет входные данные, работает с базой/провайдерами и возвращает JSON-ответ фронтенду.
# =====================================================
@app.post("/save-settings")
# =====================================================
# СОХРАНЕНИЕ В БАЗУ ДАННЫХ: save_settings
# Записывает состояние пользователя, job, metadata или результат генерации в общую базу Mini App и Telegram Bot.
# =====================================================
async def save_settings(request: Request):
    data = await request.json()
    print("SETTINGS RECEIVED:", data)

    save_kling_settings_to_db(data)
    title = "✅ НАСТРОЙКИ KLING СОХРАНЕНЫ"

    print("SETTINGS SAVED TO POSTGRES")

    telegram_id = data.get("telegram_id")
    message_id = data.get("message_id")

    body = (
        f"Модель: {data.get('model')}\n"
        f"Режим: {data.get('mode')}\n"
        f"Формат: {data.get('ratio')}\n"
        f"Качество: {data.get('quality')}\n"
        f"Длительность: {data.get('duration')}\n"
        f"Звук: {'Вкл' if data.get('sound') else 'Выкл'}\n"
        f"Prompt Enhance: {'Вкл' if data.get('prompt_enhance') else 'Выкл'}\n\n"
        "Теперь отправьте описание видео."
    )

    text = design(title, body)

    return {
        "success": True,
        "message": "✅ Настройки Kling сохранены"
    }

# =====================================================
# СИНХРОНИЗАЦИЯ С TELEGRAM: verify_telegram_init_data
# Отправляет готовый результат или статус в Telegram Bot и сохраняет признак отправки в metadata карточки.
# =====================================================
def verify_telegram_init_data(init_data: str) -> bool:
    if not init_data or not TELEGRAM_AUTH_TOKENS:
        return False

    parsed = dict(urllib.parse.parse_qsl(init_data, keep_blank_values=True))
    received_hash = parsed.pop("hash", None)
    if not received_hash:
        return False

    data_check = "\n".join(f"{key}={parsed[key]}" for key in sorted(parsed))
    for token in TELEGRAM_AUTH_TOKENS:
        secret_key = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
        calculated_hash = hmac.new(secret_key, data_check.encode(), hashlib.sha256).hexdigest()
        if hmac.compare_digest(calculated_hash, received_hash):
            return True
    return False

# =====================================================
# PYTHON-БЛОК: fallback_public_user
# Выполняет отдельный шаг backend-логики SYLVEX.
# Связан с API, базой данных, провайдерами или подготовкой данных для Mini App.
# =====================================================
def fallback_public_user(payload: dict) -> dict:
    unsafe = payload.get("initDataUnsafe") or {}
    tg_user = unsafe.get("user") or {}
    return {
        "telegram_id": tg_user.get("id") or 0,
        "username": tg_user.get("username"),
        "first_name": tg_user.get("first_name") or "Guest",
        "last_name": tg_user.get("last_name"),
        "language_code": tg_user.get("language_code"),
        "photo_url": tg_user.get("photo_url"),
        "is_premium": bool(tg_user.get("is_premium")),
        "status": "premium" if tg_user.get("is_premium") else "free",
        "balance": 0,
        "created_at": None,
    }

# =====================================================
# СОХРАНЕНИЕ В БАЗУ ДАННЫХ: sync_user_to_db
# Записывает состояние пользователя, job, metadata или результат генерации в общую базу Mini App и Telegram Bot.
# =====================================================
def sync_user_to_db(user_data: dict) -> dict:
    if not DATABASE_URL or not user_data.get("telegram_id"):
        return user_data

    return get_user_state(
        telegram_id=int(user_data["telegram_id"]),
        username=user_data.get("username"),
        first_name=user_data.get("first_name") or "Guest",
    )

# =====================================================
# СОХРАНЕНИЕ В БАЗУ ДАННЫХ: save_generation
# Записывает состояние пользователя, job, metadata или результат генерации в общую базу Mini App и Telegram Bot.
# =====================================================
def save_generation(telegram_id: int, generation_type: str, prompt: str, status: str = "done"):
    if not DATABASE_URL or not telegram_id:
        return
    try:
        conn = db_connect(DATABASE_URL)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO generations (telegram_id, generation_type, prompt, status)
            VALUES (%s, %s, %s, %s)
        """, (telegram_id, generation_type, prompt, status))
        conn.commit()
        cursor.close()
        conn.close()
    except Exception as exc:
        print("GENERATION SAVE FAILED:", exc)

# =====================================================
# PYTHON-БЛОК: ensure_prostudio_table
# Выполняет отдельный шаг backend-логики SYLVEX.
# Связан с API, базой данных, провайдерами или подготовкой данных для Mini App.
# =====================================================
def ensure_prostudio_table():
    if not DATABASE_URL:
        return

    with PROSTUDIO_SCHEMA_LOCK:
        conn = db_connect(DATABASE_URL)
        cursor = conn.cursor()
        advisory_locked = False
        try:
            cursor.execute("SELECT pg_advisory_lock(%s)", (742193601,))
            advisory_locked = True
            cursor.execute("""
        CREATE TABLE IF NOT EXISTS prostudio_messages (
            id SERIAL PRIMARY KEY,
            conversation_id TEXT NOT NULL,
            telegram_id BIGINT NOT NULL,
            mode TEXT,
            prompt TEXT,
            response_text TEXT,
            image_url TEXT,
            created_at TIMESTAMP DEFAULT NOW()
        )
        """)
            cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_prostudio_messages_user_conv
            ON prostudio_messages (telegram_id, conversation_id, created_at DESC)
            """)
            cursor.execute("ALTER TABLE prostudio_messages ADD COLUMN IF NOT EXISTS images_json TEXT")
            cursor.execute("ALTER TABLE prostudio_messages ADD COLUMN IF NOT EXISTS thumbnails_json TEXT")
            cursor.execute("ALTER TABLE prostudio_messages ADD COLUMN IF NOT EXISTS thumb_url TEXT")
            cursor.execute("ALTER TABLE prostudio_messages ADD COLUMN IF NOT EXISTS video_url TEXT")
            cursor.execute("ALTER TABLE prostudio_messages ADD COLUMN IF NOT EXISTS videos_json TEXT")
            cursor.execute("ALTER TABLE prostudio_messages ADD COLUMN IF NOT EXISTS audio_url TEXT")
            cursor.execute("ALTER TABLE prostudio_messages ADD COLUMN IF NOT EXISTS audios_json TEXT")
            cursor.execute("ALTER TABLE prostudio_messages ADD COLUMN IF NOT EXISTS metadata_json TEXT")
            cursor.execute("ALTER TABLE prostudio_messages ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'completed'")
            cursor.execute("ALTER TABLE prostudio_messages ADD COLUMN IF NOT EXISTS model TEXT")
            cursor.execute("ALTER TABLE prostudio_messages ADD COLUMN IF NOT EXISTS provider TEXT")
            cursor.execute("ALTER TABLE prostudio_messages ADD COLUMN IF NOT EXISTS cost INTEGER DEFAULT 0")
            cursor.execute("ALTER TABLE prostudio_messages ADD COLUMN IF NOT EXISTS request_json JSONB DEFAULT '{}'::jsonb")
            cursor.execute("ALTER TABLE prostudio_messages ADD COLUMN IF NOT EXISTS response_json JSONB DEFAULT '{}'::jsonb")
            cursor.execute("ALTER TABLE prostudio_messages ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP DEFAULT NOW()")
            cursor.execute("ALTER TABLE prostudio_messages ADD COLUMN IF NOT EXISTS completed_at TIMESTAMP")
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS prostudio_drafts (
                telegram_id BIGINT NOT NULL,
                mode TEXT NOT NULL,
                conversation_id TEXT,
                draft_text TEXT DEFAULT '',
                attachment_json JSONB DEFAULT '{}'::jsonb,
                updated_at TIMESTAMP DEFAULT NOW(),
                PRIMARY KEY (telegram_id, mode)
            )
            """)
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS prostudio_resources (
                id TEXT PRIMARY KEY,
                telegram_id BIGINT NOT NULL,
                resource_type TEXT NOT NULL,
                name TEXT NOT NULL,
                description TEXT DEFAULT '',
                gender TEXT DEFAULT '',
                preview_url TEXT DEFAULT '',
                photos_json JSONB DEFAULT '[]'::jsonb,
                metadata_json JSONB DEFAULT '{}'::jsonb,
                status TEXT DEFAULT 'ready',
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            )
            """)
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS prostudio_voice_avatars (
                provider TEXT NOT NULL,
                voice_id TEXT NOT NULL,
                seed BIGINT NOT NULL,
                avatar_key TEXT UNIQUE NOT NULL,
                image_data BYTEA,
                content_type TEXT DEFAULT 'image/png',
                avatar_path TEXT DEFAULT '',
                status TEXT DEFAULT 'pending',
                error_text TEXT DEFAULT '',
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW(),
                PRIMARY KEY (provider, voice_id)
            )
            """)
            cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_prostudio_voice_avatars_status
            ON prostudio_voice_avatars (status, updated_at)
            """)
            cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_prostudio_resources_user_type
            ON prostudio_resources (telegram_id, resource_type, updated_at DESC)
            """)
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS prostudio_visual_stats (
                resource_id TEXT NOT NULL,
                resource_type TEXT NOT NULL,
                likes_count INTEGER DEFAULT 0,
                selects_count INTEGER DEFAULT 0,
                heygen_stats_json JSONB DEFAULT '{}'::jsonb,
                updated_at TIMESTAMP DEFAULT NOW(),
                PRIMARY KEY (resource_id, resource_type)
            )
            """)
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS prostudio_visual_user_state (
                telegram_id BIGINT NOT NULL,
                resource_id TEXT NOT NULL,
                resource_type TEXT NOT NULL,
                liked BOOLEAN DEFAULT FALSE,
                favorite BOOLEAN DEFAULT FALSE,
                selected_count INTEGER DEFAULT 0,
                updated_at TIMESTAMP DEFAULT NOW(),
                PRIMARY KEY (telegram_id, resource_id, resource_type)
            )
            """)
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS prostudio_generation_jobs (
                id TEXT PRIMARY KEY,
                telegram_id BIGINT NOT NULL,
                conversation_id TEXT,
                mode TEXT NOT NULL,
                model TEXT,
                provider TEXT,
                prompt TEXT DEFAULT '',
                status TEXT DEFAULT 'queued',
                cost INTEGER DEFAULT 0,
                attempts INTEGER DEFAULT 0,
                locked_at TIMESTAMP,
                heartbeat_at TIMESTAMP,
                provider_wait_until TIMESTAMP,
                request_json JSONB DEFAULT '{}'::jsonb,
                response_json JSONB DEFAULT '{}'::jsonb,
                error_json JSONB DEFAULT '{}'::jsonb,
                result_json JSONB DEFAULT '{}'::jsonb,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW(),
                completed_at TIMESTAMP
            )
            """)
            cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_prostudio_jobs_user_mode
            ON prostudio_generation_jobs (telegram_id, mode, updated_at DESC)
            """)
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS generation_charges (
                id SERIAL PRIMARY KEY,
                generation_id TEXT UNIQUE NOT NULL,
                telegram_id BIGINT NOT NULL,
                mode TEXT,
                model TEXT,
                provider TEXT,
                credits INTEGER NOT NULL,
                balance_after INTEGER,
                created_at TIMESTAMP DEFAULT NOW()
            )
            """)
            cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_generation_charges_user
            ON generation_charges (telegram_id, created_at DESC)
            """)
            cursor.execute("ALTER TABLE prostudio_generation_jobs ADD COLUMN IF NOT EXISTS attempts INTEGER DEFAULT 0")
            cursor.execute("ALTER TABLE prostudio_generation_jobs ADD COLUMN IF NOT EXISTS locked_at TIMESTAMP")
            cursor.execute("ALTER TABLE prostudio_generation_jobs ADD COLUMN IF NOT EXISTS heartbeat_at TIMESTAMP")
            cursor.execute("ALTER TABLE prostudio_generation_jobs ADD COLUMN IF NOT EXISTS provider_wait_until TIMESTAMP")
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_prostudio_jobs_provider_wait
                ON prostudio_generation_jobs (status, provider_wait_until, created_at)
            """)
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS prostudio_errors (
                id SERIAL PRIMARY KEY,
                telegram_id BIGINT,
                job_id TEXT,
                provider TEXT,
                model TEXT,
                endpoint TEXT,
                request_id TEXT,
                status TEXT DEFAULT 'failed',
                error_text TEXT,
                request_json JSONB DEFAULT '{}'::jsonb,
                response_json JSONB DEFAULT '{}'::jsonb,
                stack_trace TEXT,
                created_at TIMESTAMP DEFAULT NOW()
            )
            """)
            conn.commit()
        finally:
            if advisory_locked:
                try:
                    cursor.execute("SELECT pg_advisory_unlock(%s)", (742193601,))
                    conn.commit()
                except Exception:
                    conn.rollback()
            cursor.close()
            conn.close()

# =====================================================
# PYTHON-БЛОК: _json_list
# Выполняет отдельный шаг backend-логики SYLVEX.
# Связан с API, базой данных, провайдерами или подготовкой данных для Mini App.
# =====================================================
def _json_list(value) -> list:
    if isinstance(value, list):
        return [item for item in value if item]
    if not value:
        return []
    try:
        data = json.loads(value)
        return [item for item in data if item] if isinstance(data, list) else []
    except Exception:
        return []

# =====================================================
# PYTHON-БЛОК: _json_obj
# Выполняет отдельный шаг backend-логики SYLVEX.
# Связан с API, базой данных, провайдерами или подготовкой данных для Mini App.
# =====================================================
def _json_obj(value) -> dict:
    if isinstance(value, dict):
        return value
    if not value:
        return {}
    try:
        data = json.loads(value)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}

# =====================================================
# PYTHON-БЛОК: _safe_json_dumps
# Выполняет отдельный шаг backend-логики SYLVEX.
# Связан с API, базой данных, провайдерами или подготовкой данных для Mini App.
# =====================================================
def _safe_json_dumps(value) -> str:
    try:
        return json.dumps(value if value is not None else {}, ensure_ascii=False)
    except Exception:
        return "{}"

# =====================================================
# PYTHON-БЛОК: _sql_text
# Выполняет отдельный шаг backend-логики SYLVEX.
# Связан с API, базой данных, провайдерами или подготовкой данных для Mini App.
# =====================================================
def _sql_text(value, max_text: int = 2000) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value[:max_text]
    if isinstance(value, (dict, list)):
        return _safe_json_dumps(_sanitize_event_payload(value, max_text=max_text, max_items=50, depth=5))[:max_text]
    return str(value)[:max_text]

# =====================================================
# PYTHON-БЛОК: prostudio_debug
# Выполняет отдельный шаг backend-логики SYLVEX.
# Связан с API, базой данных, провайдерами или подготовкой данных для Mini App.
# =====================================================
def prostudio_debug(stage: str, **data):
    safe = _sanitize_event_payload(data, max_text=700, max_items=30, depth=4)
    print(f"PROSTUDIO DEBUG {stage}:", safe)

# =====================================================
# ОБРАБОТКА ОШИБОК: prostudio_error
# Преобразует техническую ошибку провайдера в понятное сообщение для пользователя и сохраняет диагностические данные для логов.
# =====================================================
def prostudio_error(stage: str, exc: Exception = None, **data):
    safe = _sanitize_event_payload(data, max_text=1000, max_items=30, depth=4)
    if exc is not None:
        safe["error"] = str(exc)
        safe["traceback"] = traceback.format_exc()
    print(f"PROSTUDIO ERROR {stage}:", safe)

PROSTUDIO_ACTIVE_JOB_STATUSES = ("queued", "processing", "provider_processing")


class ActiveProstudioJobError(RuntimeError):
    def __init__(self, job_id: str, status: str):
        super().__init__("active_generation_exists")
        self.job_id = str(job_id or "")
        self.status = str(status or "queued")


def get_active_prostudio_job(telegram_id: int) -> dict:
    if not DATABASE_URL or not telegram_id:
        return {}
    ensure_prostudio_table()
    conn = db_connect(DATABASE_URL)
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT id, status, mode, model, provider, conversation_id, created_at, updated_at
            FROM prostudio_generation_jobs
            WHERE telegram_id = %s
              AND status IN ('queued', 'processing', 'provider_processing')
            ORDER BY created_at ASC
            LIMIT 1
        """, (int(telegram_id),))
        row = cursor.fetchone()
        if not row:
            job = {}
        else:
            job = {
            "id": row[0],
            "job_id": row[0],
            "status": row[1],
            "mode": row[2],
            "model": row[3],
            "provider": row[4],
            "conversation_id": row[5],
            "created_at": _to_iso(row[6]),
            "updated_at": _to_iso(row[7]),
        }
    finally:
        cursor.close()
        conn.close()
    if job:
        recovery = recover_stale_prostudio_job(job["id"])
        if recovery.get("recovered"):
            return {}
    return job


# =====================================================
# СОХРАНЕНИЕ В БАЗУ ДАННЫХ: create_prostudio_generation_job
# Записывает состояние пользователя, job, metadata или результат генерации в общую базу Mini App и Telegram Bot.
# =====================================================
def create_prostudio_generation_job(payload: dict) -> str:
    job_id = str(uuid4())
    telegram_id = int(payload.get("telegram_id") or 0)
    prostudio_debug(
        "JOB_CREATE_START",
        job_id=job_id,
        telegram_id=telegram_id,
        mode=payload.get("mode") or payload.get("category") or "text",
        model=payload.get("model") or "",
        provider=payload.get("provider") or "",
        has_database=bool(DATABASE_URL),
    )
    if not DATABASE_URL or not telegram_id:
        prostudio_debug("JOB_CREATE_SKIPPED_DB", job_id=job_id, has_database=bool(DATABASE_URL), telegram_id=telegram_id)
        return job_id
    ensure_prostudio_table()
    conn = db_connect(DATABASE_URL)
    cursor = conn.cursor()
    try:
        # Serialize job creation per Telegram user across every web process.
        # The check and INSERT share one transaction, so simultaneous clicks
        # cannot create two active jobs.
        cursor.execute("SELECT pg_advisory_xact_lock(%s)", (telegram_id,))
        cursor.execute("""
            SELECT id, status
            FROM prostudio_generation_jobs
            WHERE telegram_id = %s
              AND status IN ('queued', 'processing', 'provider_processing')
            ORDER BY created_at ASC
            LIMIT 1
        """, (telegram_id,))
        active = cursor.fetchone()
        if active:
            conn.rollback()
            raise ActiveProstudioJobError(active[0], active[1])
        cursor.execute("""
            INSERT INTO prostudio_generation_jobs (
                id, telegram_id, conversation_id, mode, model, provider, prompt, status, request_json
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, 'queued', %s::jsonb)
        """, (
            job_id,
            telegram_id,
            payload.get("conversation_id") or None,
            payload.get("mode") or payload.get("category") or "text",
            payload.get("model") or "",
            payload.get("provider") or "",
            payload.get("prompt") or "",
            _safe_json_dumps(payload),
        ))
        conn.commit()
        prostudio_debug("JOB_CREATE_DONE", job_id=job_id, status="queued")
    except ActiveProstudioJobError:
        raise
    except Exception as exc:
        conn.rollback()
        prostudio_error("JOB_CREATE_FAILED", exc, job_id=job_id, telegram_id=telegram_id)
        raise
    finally:
        cursor.close()
        conn.close()
    return job_id

# =====================================================
# СОХРАНЕНИЕ В БАЗУ ДАННЫХ: update_prostudio_generation_job
# Записывает состояние пользователя, job, metadata или результат генерации в общую базу Mini App и Telegram Bot.
# =====================================================
def update_prostudio_generation_job(job_id: str, status: str, result: Optional[dict] = None, error: Optional[dict] = None, conversation_id: str = ""):
    prostudio_debug(
        "JOB_UPDATE_START",
        job_id=job_id,
        status=status,
        result_keys=sorted((result or {}).keys()) if isinstance(result, dict) else [],
        error_keys=sorted((error or {}).keys()) if isinstance(error, dict) else [],
        conversation_id=conversation_id or "",
    )
    if not DATABASE_URL or not job_id:
        prostudio_debug("JOB_UPDATE_SKIPPED_DB", job_id=job_id, status=status, has_database=bool(DATABASE_URL))
        return False
    try:
        ensure_prostudio_table()
        conn = db_connect(DATABASE_URL)
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE prostudio_generation_jobs
            SET status = %s,
                conversation_id = COALESCE(NULLIF(%s, ''), conversation_id),
                response_json = COALESCE(%s::jsonb, response_json),
                result_json = COALESCE(%s::jsonb, result_json),
                error_json = COALESCE(%s::jsonb, error_json),
                cost = CASE WHEN %s IN ('completed', 'provider_processing') THEN COALESCE(%s, cost) ELSE cost END,
                updated_at = NOW(),
                completed_at = CASE WHEN %s IN ('completed', 'failed') THEN NOW() ELSE completed_at END
            WHERE id = %s
        """, (
            status,
            conversation_id or "",
            _safe_json_dumps(_sanitize_event_payload(result or {}, max_text=1200, max_items=50, depth=5)),
            _safe_json_dumps(_sanitize_event_payload(result or {}, max_text=1200, max_items=50, depth=5)),
            _safe_json_dumps(_sanitize_event_payload(error or {}, max_text=1200, max_items=50, depth=5)),
            status,
            int((result or {}).get("cost_credits") or (result or {}).get("cost") or (result or {}).get("price") or 0),
            status,
            job_id,
        ))
        rowcount = cursor.rowcount
        conn.commit()
        cursor.close()
        conn.close()
        prostudio_debug("JOB_UPDATE_DONE", job_id=job_id, status=status, rowcount=rowcount)
        return rowcount > 0
    except Exception as exc:
        prostudio_error("JOB_UPDATE_FAILED", exc, job_id=job_id, status=status)
        return False

# =====================================================
# СОХРАНЕНИЕ В БАЗУ ДАННЫХ: claim_next_prostudio_generation_job
# Записывает состояние пользователя, job, metadata или результат генерации в общую базу Mini App и Telegram Bot.
# =====================================================
def claim_next_prostudio_generation_job() -> Optional[dict]:
    if not DATABASE_URL:
        prostudio_debug("WORKER_CLAIM_SKIPPED_DB")
        return None
    try:
        ensure_prostudio_table()
        conn = db_connect(DATABASE_URL)
        cursor = conn.cursor()
        try:
            cursor.execute("""
                UPDATE prostudio_generation_jobs
                SET status = 'processing',
                    attempts = COALESCE(attempts, 0) + 1,
                    locked_at = NOW(),
                    heartbeat_at = NOW(),
                    provider_wait_until = NULL,
                    updated_at = NOW()
                WHERE id = (
                    SELECT id
                    FROM prostudio_generation_jobs
                    WHERE status = 'queued'
                      AND COALESCE(attempts, 0) < %s
                      AND (provider_wait_until IS NULL OR provider_wait_until <= NOW())
                    ORDER BY created_at ASC
                    LIMIT 1
                    FOR UPDATE SKIP LOCKED
                )
                RETURNING id, request_json, attempts
            """, (PROSTUDIO_MAX_JOB_ATTEMPTS,))
            row = cursor.fetchone()
            conn.commit()
        finally:
            cursor.close()
            conn.close()
        if not row:
            # An empty queue is the normal worker state. Logging it on every
            # poll (every two seconds by default) floods Railway logs and can
            # hide actionable errors without adding diagnostic value.
            return None
        payload = _json_obj(row[1])
        claimed = {"id": row[0], "payload": payload, "attempts": row[2] or 1}
        prostudio_debug(
            "WORKER_CLAIM_DONE",
            job_id=row[0],
            attempts=row[2] or 1,
            mode=payload.get("mode") or payload.get("category") or "",
            model=payload.get("model") or "",
            provider=payload.get("provider") or "",
        )
        return claimed
    except Exception as exc:
        prostudio_error("WORKER_CLAIM_FAILED", exc)
        return None

# =====================================================
# PYTHON-БЛОК: requeue_stale_prostudio_jobs
# Выполняет отдельный шаг backend-логики SYLVEX.
# Связан с API, базой данных, провайдерами или подготовкой данных для Mini App.
# =====================================================
def requeue_stale_prostudio_jobs():
    """Compatibility entry point: terminally recover abandoned active jobs."""
    if not DATABASE_URL:
        return
    try:
        ensure_prostudio_table()
        conn = db_connect(DATABASE_URL)
        cursor = conn.cursor()
        try:
            cursor.execute("""
                SELECT id
                FROM prostudio_generation_jobs
                WHERE status IN ('queued', 'processing', 'provider_processing')
                  AND COALESCE(heartbeat_at, updated_at, created_at) < NOW() - (%s || ' minutes')::interval
                ORDER BY created_at ASC
                LIMIT 200
            """, (PROSTUDIO_STALE_PROCESSING_MINUTES,))
            job_ids = [str(row[0]) for row in cursor.fetchall()]
        finally:
            cursor.close()
            conn.close()
        for job_id in job_ids:
            recover_stale_prostudio_job(job_id)
    except Exception as exc:
        prostudio_error("STALE_JOB_RECOVERY_FAILED", exc)


def _recover_stale_prostudio_job_once(job_id: str, force: bool = False) -> dict:
    """Atomically fail an abandoned job only when no live provider lease exists."""
    if not DATABASE_URL or not job_id:
        return {"recovered": False, "reason": "database_or_job_missing"}
    ensure_prostudio_table()
    ensure_provider_slot_table(DATABASE_URL)
    threshold_seconds = max(60, int(PROSTUDIO_STALE_PROCESSING_MINUTES) * 60)
    conn = db_connect(DATABASE_URL)
    cursor = conn.cursor()
    detected = None
    released_slots = []
    try:
        cursor.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (f"prostudio-stale:{job_id}",))
        cursor.execute("""
            SELECT id, status, provider, created_at, updated_at, heartbeat_at,
                   EXTRACT(EPOCH FROM (NOW() - created_at)),
                   EXTRACT(EPOCH FROM (NOW() - heartbeat_at)),
                   result_json
            FROM prostudio_generation_jobs
            WHERE id = %s
            FOR UPDATE
        """, (job_id,))
        row = cursor.fetchone()
        if not row:
            conn.rollback()
            return {"recovered": False, "reason": "job_not_found"}
        old_status = str(row[1] or "")
        if old_status not in PROSTUDIO_ACTIVE_JOB_STATUSES:
            conn.rollback()
            return {"recovered": False, "reason": "job_not_active", "status": old_status}

        cursor.execute("""
            SELECT provider, worker_id, heartbeat_at, lease_until,
                   (lease_until > NOW()) AS is_live
            FROM prostudio_provider_slots
            WHERE job_id = %s
            ORDER BY lease_until DESC
        """, (job_id,))
        slot_rows = cursor.fetchall()
        live_slot = next((slot for slot in slot_rows if bool(slot[4])), None)
        heartbeat_age = float(row[7]) if row[7] is not None else None
        reference_time = row[5] or row[4] or row[3]
        cursor.execute("SELECT EXTRACT(EPOCH FROM (NOW() - %s::timestamp))", (reference_time,))
        stale_age = float(cursor.fetchone()[0] or 0)
        if stale_age <= threshold_seconds and not force:
            conn.rollback()
            return {"recovered": False, "reason": "heartbeat_fresh", "status": old_status}
        if live_slot:
            conn.rollback()
            return {
                "recovered": False, "reason": "live_provider_slot", "status": old_status,
                "worker_id": str(live_slot[1] or ""),
            }

        worker_id = str(slot_rows[0][1] or "") if slot_rows else ""
        provider = str(row[2] or (slot_rows[0][0] if slot_rows else "") or "")
        age_seconds = float(row[6] or 0)
        saved_result = _json_obj(row[8])
        cursor.execute(
            "SELECT EXISTS(SELECT 1 FROM generation_charges WHERE generation_id = %s)",
            (job_id,),
        )
        has_charge = bool(cursor.fetchone()[0])
        has_final_result = generation_has_completed_result(saved_result, "")
        reason = "stale_worker_recovered"
        detected = {
            "job_id": job_id, "old_status": old_status,
            "age_seconds": round(age_seconds, 3),
            "heartbeat_age_seconds": round(heartbeat_age, 3) if heartbeat_age is not None else None,
            "worker_id": worker_id, "provider": provider, "reason": reason,
            "has_final_result": has_final_result, "has_charge": has_charge,
        }
        prostudio_debug("PROSTUDIO_STALE_JOB_DETECTED", **detected)
        cursor.execute("""
            DELETE FROM prostudio_provider_slots
            WHERE job_id = %s AND lease_until <= NOW()
            RETURNING provider, worker_id
        """, (job_id,))
        released_slots = cursor.fetchall()
        error_payload = {
            "ok": False,
            "error": reason,
            "message": "Предыдущая генерация была остановлена после перезапуска worker.",
        }
        cursor.execute("""
            UPDATE prostudio_generation_jobs
            SET status = 'failed', error_json = %s::jsonb,
                locked_at = NULL, heartbeat_at = NULL, provider_wait_until = NULL,
                updated_at = NOW(), completed_at = NOW()
            WHERE id = %s AND status = %s
        """, (_safe_json_dumps(error_payload), job_id, old_status))
        if cursor.rowcount != 1:
            conn.rollback()
            return {"recovered": False, "reason": "job_changed_concurrently"}
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cursor.close()
        conn.close()

    for slot_provider, slot_worker in released_slots:
        slot_log = dict(detected)
        slot_log["provider"] = str(slot_provider or detected["provider"])
        slot_log["worker_id"] = str(slot_worker or detected["worker_id"])
        prostudio_debug("PROSTUDIO_STALE_SLOT_RELEASED", **slot_log)
    prostudio_debug("PROSTUDIO_STALE_JOB_RECOVERED", **detected)
    return {"recovered": True, "status": "failed", **detected}


def recover_stale_prostudio_job(job_id: str, force: bool = False) -> dict:
    """Retry the atomic recovery when concurrent runtime DDL causes a deadlock."""
    for attempt in range(1, 5):
        try:
            return _recover_stale_prostudio_job_once(job_id, force=force)
        except (psycopg2.errors.DeadlockDetected, psycopg2.errors.LockNotAvailable) as exc:
            prostudio_debug(
                "PROSTUDIO_STALE_RECOVERY_RETRY",
                job_id=job_id,
                attempt=attempt,
                worker_id=WORKER_ID,
                reason=type(exc).__name__,
            )
            if attempt >= 4:
                raise
            time.sleep(min(2.0, 0.25 * (2 ** (attempt - 1))) + random.uniform(0.0, 0.2))

# =====================================================
# СОХРАНЕНИЕ В БАЗУ ДАННЫХ: heartbeat_prostudio_generation_job
# Записывает состояние пользователя, job, metadata или результат генерации в общую базу Mini App и Telegram Bot.
# =====================================================
def heartbeat_prostudio_generation_job(job_id: str):
    if not DATABASE_URL or not job_id:
        return
    try:
        conn = db_connect(DATABASE_URL)
        cursor = conn.cursor()
        try:
            cursor.execute("""
                UPDATE prostudio_generation_jobs
                SET heartbeat_at = NOW(), updated_at = NOW()
                WHERE id = %s
                  AND status IN ('processing', 'provider_processing')
            """, (job_id,))
            conn.commit()
        finally:
            cursor.close()
            conn.close()
    except Exception as exc:
        prostudio_error("JOB_HEARTBEAT_FAILED", exc, job_id=job_id)


def defer_prostudio_job_for_provider(job_id: str, delay_seconds: float = 2.0):
    """Return a capacity-waiting job to the queue without consuming an attempt."""
    if not DATABASE_URL or not job_id:
        return
    conn = db_connect(DATABASE_URL)
    cursor = conn.cursor()
    try:
        cursor.execute("""
            UPDATE prostudio_generation_jobs
            SET status = 'queued',
                attempts = GREATEST(COALESCE(attempts, 1) - 1, 0),
                locked_at = NULL,
                heartbeat_at = NULL,
                provider_wait_until = NOW() + (%s * INTERVAL '1 second'),
                updated_at = NOW()
            WHERE id = %s AND status = 'processing'
        """, (max(0.2, float(delay_seconds)), job_id))
        conn.commit()
    finally:
        cursor.close()
        conn.close()

# =====================================================
# PYTHON-БЛОК: generation_result_urls
# Выполняет отдельный шаг backend-логики SYLVEX.
# Связан с API, базой данных, провайдерами или подготовкой данных для Mini App.
# =====================================================
def generation_result_urls(result: Optional[dict], mode: str = "") -> list:
    if not isinstance(result, dict):
        return []
    urls = []
    if mode == "image" or result.get("type") == "image":
        urls.extend(_json_list(result.get("images")))
        for key in ("image_url", "result_url", "full_url", "url", "file_url"):
            if result.get(key):
                urls.append(result.get(key))
    elif mode == "video" or result.get("type") == "video":
        urls.extend(_json_list(result.get("videos")))
        for key in ("video_url", "result_url", "full_url", "url", "file_url"):
            if result.get(key):
                urls.append(result.get(key))
    elif mode in {"music", "voice"} or result.get("type") in {"music", "voice", "audio"}:
        urls.extend(_json_list(result.get("audios")))
        for key in ("audio_url", "music_url", "song_url", "result_url", "full_url", "url", "file_url"):
            if result.get(key):
                urls.append(result.get(key))
    else:
        for key in ("result_url", "full_url", "url", "file_url", "text"):
            if result.get(key):
                urls.append(result.get(key))
    return [str(url).strip() for url in urls if isinstance(url, str) and str(url).strip()]

# =====================================================
# PYTHON-БЛОК: generation_has_completed_result
# Выполняет отдельный шаг backend-логики SYLVEX.
# Связан с API, базой данных, провайдерами или подготовкой данных для Mini App.
# =====================================================
def generation_has_completed_result(result: Optional[dict], mode: str = "") -> bool:
    if not isinstance(result, dict) or not result.get("ok"):
        return False
    if mode in {"text", "chat", "pro", "lite"}:
        return bool(result.get("text"))
    return bool(generation_result_urls(result, mode))

# =====================================================
# PYTHON-БЛОК: normalize_generation_status
# Выполняет отдельный шаг backend-логики SYLVEX.
# Связан с API, базой данных, провайдерами или подготовкой данных для Mini App.
# =====================================================
def normalize_generation_status(result: Optional[dict], mode: str = "") -> str:
    if not isinstance(result, dict):
        return "failed"
    raw = str(result.get("status") or "").strip().lower()
    if raw in {"failed", "error", "cancelled", "canceled"}:
        return "failed"
    if generation_has_completed_result(result, mode):
        return "completed"
    if result.get("task_id") or result.get("workId") or result.get("poll_url") or raw in {"processing", "queued", "submitted", "running", "waiting", "pending", "provider_processing"}:
        return "provider_processing"
    return "failed"


# =====================================================
# PYTHON-БЛОК: run_provider_coroutine_off_loop
# Запускает blocking-heavy async провайдеры вне основного event loop FastAPI.
# =====================================================
async def run_provider_coroutine_off_loop(factory):
    return await asyncio.to_thread(lambda: asyncio.run(factory()))


# =====================================================
# БЛОК ОЗВУЧКИ: is_voice_video_voiceover_request
# Определяет режим «Озвучить видео»: voice UI генерирует речь, backend локально накладывает её на видео.
# =====================================================
def is_voice_video_voiceover_request(payload: dict) -> bool:
    voice_options = payload.get("voice_options") if isinstance(payload, dict) else {}
    if not isinstance(voice_options, dict):
        return False
    purpose = str(voice_options.get("upload_purpose") or voice_options.get("uploadPurpose") or "").strip().lower()
    return purpose in {"dub_video", "video_voiceover", "voiceover_video"}


# =====================================================
# БЛОК ОЗВУЧКИ: voice_uploaded_video_url
# Достаёт URL выбранного пользователем видео из voice upload state.
# =====================================================
def voice_uploaded_video_url(payload: dict) -> str:
    voice_options = payload.get("voice_options") if isinstance(payload, dict) else {}
    if not isinstance(voice_options, dict):
        return ""
    candidates = []
    uploads = voice_options.get("uploads")
    if isinstance(uploads, list):
        candidates.extend(uploads)
    attachment = voice_options.get("attachment") or payload.get("attachment")
    if attachment:
        candidates.append(attachment)
    for item in candidates:
        if isinstance(item, str) and item.strip():
            value = item.strip()
            if pathlib.PurePosixPath(urllib.parse.urlparse(value).path or value).suffix.lower() in {".mp4", ".mov", ".m4v", ".webm"}:
                return value
        if isinstance(item, dict):
            kind = str(item.get("kind") or item.get("type") or "").lower()
            mime = str(item.get("mime") or item.get("content_type") or item.get("contentType") or "").lower()
            value = str(item.get("url") or item.get("video_url") or item.get("videoUrl") or item.get("file_url") or item.get("fileUrl") or "").strip()
            suffix = pathlib.PurePosixPath(urllib.parse.urlparse(value).path or value).suffix.lower()
            if value and (kind == "video" or mime.startswith("video/") or suffix in {".mp4", ".mov", ".m4v", ".webm"}):
                return value
    return ""


# =====================================================
# БЛОК ОЗВУЧКИ: build_voice_video_voiceover_result
# Собирает финальный video result после локального наложения сгенерированной речи на видео.
# =====================================================
def build_voice_video_voiceover_result(payload: dict, audio_result: dict, input_video: str) -> dict:
    voice_options = payload.get("voice_options") if isinstance(payload.get("voice_options"), dict) else {}
    audio_url = (
        audio_result.get("audio_url")
        or (_json_list(audio_result.get("audios"))[0] if _json_list(audio_result.get("audios")) else "")
        or audio_result.get("result_url")
        or audio_result.get("url")
        or ""
    )
    if not audio_url:
        return {"ok": False, "type": "video", "error": "Не удалось создать аудио для видео"}
    video_url = _mux_video_with_audio(input_video, audio_url)
    if not video_url:
        return {
            "ok": False,
            "type": "video",
            "error": "Озвучка создана, но не удалось собрать видео с новой аудиодорожкой. Проверьте ffmpeg и исходный файл.",
            "audio_url": audio_url,
            "audios": [audio_url],
            "input_video_url": input_video,
        }
    return {
        "ok": True,
        "type": "video",
        "provider": "local-ffmpeg",
        "model": payload.get("model") or voice_options.get("model") or "voiceover_video",
        "status": "completed",
        "video_url": video_url,
        "videos": [video_url],
        "audio_url": audio_url,
        "audios": [audio_url],
        "voice_options": voice_options,
        "input_video_url": input_video,
        "voice_video_voiceover": True,
        "text": "Видео с озвучкой готово ✅\n" + video_url,
    }


# =====================================================
# ОБРАБОТКА ОШИБОК: user_generation_error_text
# Преобразует техническую ошибку провайдера в понятное сообщение для пользователя и сохраняет диагностические данные для логов.
# =====================================================
def user_generation_error_text(value, fallback: str = "Генерация не прошла. Попробуйте повторить немного позже.") -> str:
    return translate_provider_error(value, fallback=fallback)

# =====================================================
# ОБРАБОТКА ОШИБОК: log_prostudio_error
# Преобразует техническую ошибку провайдера в понятное сообщение для пользователя и сохраняет диагностические данные для логов.
# =====================================================
def log_prostudio_error(payload: dict, error: dict, job_id: str = ""):
    telegram_id = int(payload.get("telegram_id") or 0)
    if not DATABASE_URL:
        return
    try:
        ensure_prostudio_table()
        conn = db_connect(DATABASE_URL)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO prostudio_errors (
                telegram_id, job_id, provider, model, endpoint, request_id, status,
                error_text, request_json, response_json, stack_trace
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s)
        """, (
            telegram_id or None,
            job_id or None,
            _sql_text(error.get("provider") or payload.get("provider") or "", 200),
            _sql_text(error.get("model") or payload.get("model") or "", 200),
            _sql_text(error.get("endpoint") or "", 1000),
            _sql_text(error.get("request_id") or "", 200),
            _sql_text(error.get("status") or "failed", 80),
            _sql_text(error.get("error") or error.get("message") or error, 1000),
            _safe_json_dumps(_sanitize_event_payload(payload, max_text=1200, max_items=40, depth=5)),
            _safe_json_dumps(_sanitize_event_payload(error, max_text=1200, max_items=50, depth=5)),
            _sql_text(error.get("stack_trace") or error.get("traceback") or "", 4000),
        ))
        conn.commit()
        cursor.close()
        conn.close()
    except Exception as exc:
        print("PROSTUDIO ERROR LOG FAILED:", exc)

# =====================================================
# СОХРАНЕНИЕ В БАЗУ ДАННЫХ: save_prostudio_draft
# Записывает состояние пользователя, job, metadata или результат генерации в общую базу Mini App и Telegram Bot.
# =====================================================
def save_prostudio_draft(telegram_id: int, mode: str, draft_text: str = "", conversation_id: str = "", attachment: Optional[dict] = None) -> dict:
    if not DATABASE_URL or not telegram_id:
        return {}
    mode = (mode or "image").strip().lower()
    if mode not in {"image", "video", "music", "voice"}:
        mode = "image"
    try:
        ensure_prostudio_table()
        conn = db_connect(DATABASE_URL)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO prostudio_drafts (telegram_id, mode, conversation_id, draft_text, attachment_json, updated_at)
            VALUES (%s, %s, %s, %s, %s::jsonb, NOW())
            ON CONFLICT (telegram_id, mode) DO UPDATE SET
                conversation_id = EXCLUDED.conversation_id,
                draft_text = EXCLUDED.draft_text,
                attachment_json = EXCLUDED.attachment_json,
                updated_at = NOW()
        """, (telegram_id, mode, conversation_id or None, draft_text or "", _safe_json_dumps(attachment or {})))
        conn.commit()
        cursor.close()
        conn.close()
        return {"mode": mode, "conversation_id": conversation_id, "draft_text": draft_text or "", "attachment": attachment or {}}
    except Exception as exc:
        print("PROSTUDIO DRAFT SAVE FAILED:", exc)
        return {}

# =====================================================
# PYTHON-БЛОК: load_prostudio_drafts
# Выполняет отдельный шаг backend-логики SYLVEX.
# Связан с API, базой данных, провайдерами или подготовкой данных для Mini App.
# =====================================================
def load_prostudio_drafts(telegram_id: int) -> dict:
    if not DATABASE_URL or not telegram_id:
        return {}
    try:
        ensure_prostudio_table()
        conn = db_connect(DATABASE_URL)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT mode, conversation_id, draft_text, attachment_json, updated_at
            FROM prostudio_drafts
            WHERE telegram_id = %s
        """, (telegram_id,))
        rows = cursor.fetchall()
        cursor.close()
        conn.close()
        result = {}
        for mode, conversation_id, draft_text, attachment_json, updated_at in rows:
            result[mode] = {
                "mode": mode,
                "conversation_id": conversation_id,
                "draft_text": draft_text or "",
                "attachment": _json_obj(attachment_json),
                "updated_at": _to_iso(updated_at),
            }
        return result
    except Exception as exc:
        print("PROSTUDIO DRAFT LOAD FAILED:", exc)
        return {}

# =====================================================
# СОХРАНЕНИЕ В БАЗУ ДАННЫХ: save_prostudio_resource
# Записывает состояние пользователя, job, metadata или результат генерации в общую базу Mini App и Telegram Bot.
# =====================================================
def save_prostudio_resource(telegram_id: int, resource: dict) -> dict:
    if not DATABASE_URL or not telegram_id:
        return resource or {}
    kind = (resource.get("resource_type") or resource.get("type") or resource.get("kind") or "").strip().lower()
    if kind in {"characters", "character"}:
        kind = "character"
    elif kind in {"objects", "object"}:
        kind = "object"
    elif kind in {"voices", "voice"}:
        kind = "voice"
    else:
        return {}
    resource_id = resource.get("id") or f"custom_{kind}_{uuid4().hex}"
    photos = (
        _json_list(resource.get("sourceImages"))
        or _json_list(resource.get("source_images"))
        or _json_list(resource.get("photos"))
        or _json_list(resource.get("referenceImages"))
        or _json_list(resource.get("reference_images"))
    )
    preview = resource.get("previewUrl") or resource.get("preview_url") or (photos[0] if photos else "")
    item = {
        "id": resource_id,
        "name": resource.get("name") or "",
        "gender": resource.get("gender") or "",
        "description": resource.get("description") or "",
        "prompt": resource.get("prompt") or resource.get("characterPrompt") or "",
        "previewUrl": preview,
        "avatarUrl": resource.get("avatarUrl") or resource.get("avatar_url") or preview,
        "referenceImages": photos,
        "type": "custom",
        "voice_id": resource.get("voice_id") or resource.get("voiceId") or resource.get("id") or "",
        "avatar_id": resource.get("avatar_id") or resource.get("avatarId") or "",
        "provider": resource.get("provider") or "",
        "model": resource.get("model") or "",
        "status": resource.get("status") or "ready",
        "created_at": resource.get("created_at"),
    }
    try:
        ensure_prostudio_table()
        conn = db_connect(DATABASE_URL)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO prostudio_resources (
                id, telegram_id, resource_type, name, description, gender,
                preview_url, photos_json, metadata_json, status, updated_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s, NOW())
            ON CONFLICT (id) DO UPDATE SET
                name = EXCLUDED.name,
                description = EXCLUDED.description,
                gender = EXCLUDED.gender,
                preview_url = EXCLUDED.preview_url,
                photos_json = EXCLUDED.photos_json,
                metadata_json = EXCLUDED.metadata_json,
                status = EXCLUDED.status,
                updated_at = NOW()
            WHERE prostudio_resources.telegram_id = EXCLUDED.telegram_id
        """, (
            item["id"],
            telegram_id,
            kind,
            item["name"],
            item["description"],
            item["gender"],
            item["previewUrl"],
            _safe_json_dumps(photos),
            _safe_json_dumps(_sanitize_event_payload(resource, max_text=1200, max_items=50, depth=5)),
            item["status"],
        ))
        conn.commit()
        cursor.close()
        conn.close()
        log_user_event(telegram_id, "miniapp", "resource", f"{kind}_saved", {"id": item["id"], "name": item["name"]})
    except Exception as exc:
        print("PROSTUDIO RESOURCE SAVE FAILED:", exc)
    return item

# =====================================================
# PYTHON-БЛОК: load_prostudio_resources
# Выполняет отдельный шаг backend-логики SYLVEX.
# Связан с API, базой данных, провайдерами или подготовкой данных для Mini App.
# =====================================================
def load_prostudio_resources(telegram_id: int) -> dict:
    if not DATABASE_URL or not telegram_id:
        return {"characters": [], "objects": [], "voices": []}
    try:
        ensure_prostudio_table()
        conn = db_connect(DATABASE_URL)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, resource_type, name, description, gender, preview_url, photos_json, metadata_json, status, created_at, updated_at
            FROM prostudio_resources
            WHERE telegram_id = %s
            ORDER BY updated_at DESC
        """, (telegram_id,))
        rows = cursor.fetchall()
        cursor.close()
        conn.close()
        result = {"characters": [], "objects": [], "voices": []}
        for resource_id, kind, name, description, gender, preview, photos_json, metadata_json, status, created_at, updated_at in rows:
            photos = _json_list(photos_json)
            metadata = _json_obj(metadata_json)
            item = {
                "id": resource_id,
                "name": name or "",
                "description": description or "",
                "gender": gender or "",
                "previewUrl": preview or (photos[0] if photos else ""),
                "referenceImages": photos,
                "sourceImages": photos,
                "type": "custom",
                "status": status or "ready",
                "created_at": _to_iso(created_at),
                "updated_at": _to_iso(updated_at),
            }
            if kind == "character":
                item["avatar_id"] = metadata.get("avatar_id") or metadata.get("avatarId") or ""
                item["provider"] = metadata.get("provider") or metadata.get("ai_provider") or ""
                item["model"] = metadata.get("model") or metadata.get("ai_model") or ""
                item["prompt"] = ""
                item["heygenPhotoAvatarId"] = metadata.get("heygenPhotoAvatarId") or metadata.get("heygen_photo_avatar_id") or metadata.get("avatar_id") or ""
                item["heygenAvatarGroupId"] = metadata.get("heygenAvatarGroupId") or metadata.get("heygen_avatar_group_id") or ""
                result["characters"].append(item)
            elif kind == "object":
                result["objects"].append(item)
            elif kind == "voice":
                item["voice_id"] = metadata.get("voice_id") or metadata.get("voiceId") or resource_id
                item["provider"] = metadata.get("provider") or "elevenlabs"
                item["model"] = metadata.get("model") or metadata.get("ai_model") or ""
                item["avatarUrl"] = metadata.get("avatarUrl") or metadata.get("avatar_url") or preview or voice_avatar_url_for(item["voice_id"], item["provider"])
                item["avatar_url"] = item["avatarUrl"]
                result["voices"].append(item)
        return result
    except Exception as exc:
        print("PROSTUDIO RESOURCE LOAD FAILED:", exc)
        return {"characters": [], "objects": [], "voices": []}

# =====================================================
# METADATA КАРТОЧКИ ГЕНЕРАЦИИ: build_prostudio_metadata
# Собирает параметры генерации, ссылки, стоимость, модель и статусы для drawer, истории и Telegram-синхронизации.
# =====================================================
def build_prostudio_metadata(payload: dict, result: dict) -> dict:
    mode = payload.get("mode") or payload.get("category") or result.get("type") or "text"
    if mode not in ("image", "video", "music", "voice"):
        return {}

    options_key = f"{mode}_options"
    options = payload.get(options_key) or {}
    if not isinstance(options, dict):
        options = {}

    images = (
        _json_list(result.get("images"))
        or _json_list(result.get("urls"))
        or _json_list(result.get("output"))
        or ([result.get("image_url")] if result.get("image_url") else [])
        or ([result.get("result_url")] if result.get("result_url") else [])
    )
    thumbs = (
        _json_list(result.get("thumbnails"))
        or ([result.get("thumbnail_url")] if result.get("thumbnail_url") else [])
        or ([result.get("thumb_url")] if result.get("thumb_url") else [])
    )
    videos = _json_list(result.get("videos")) or ([result.get("video_url")] if result.get("video_url") else [])
    audios = _json_list(result.get("audios")) or ([result.get("audio_url")] if result.get("audio_url") else [])
    reference_images = (
        _json_list(options.get("referenceImageUrls"))
        or _json_list(options.get("referenceImages"))
        or _json_list(payload.get("reference_images"))
    )

    model = payload.get("model") or options.get("modelId") or options.get("model") or result.get("model") or ""
    provider = payload.get("provider") or result.get("provider") or ""
    seed = options.get("seed") if mode == "image" and image_model_features(model).get("seed") else None
    result_url = ""
    if mode == "image":
        result_url = images[0] if images else ""
    elif mode == "video":
        result_url = videos[0] if videos else ""
    else:
        result_url = audios[0] if audios else ""
    provider_metadata = _json_obj(result.get("metadata"))
    metadata = {
        "type": mode,
        "result_url": result_url,
        "full_url": result_url,
        "preview_fallback_url": result.get("preview_fallback_url") or result_url,
        "model": model,
        "model_label": result.get("model_label") or result.get("model_name") or options.get("modelLabel") or model,
        "provider": provider,
        "prompt": payload.get("prompt") or "",
        "settings": options,
        "style": options.get("style") or options.get("genre") or "",
        "character": options.get("character") or "",
        "characterId": options.get("characterId"),
        "characterName": options.get("characterName") or "",
        "characterReferences": _json_list(options.get("characterReferences")),
        "objects": options.get("objects") or "",
        "objectId": options.get("objectId"),
        "objectName": options.get("objectName") or options.get("objects") or "",
        "objectReferences": _json_list(options.get("objectReferences")),
        "ratio": options.get("ratio") or options.get("size") or "",
        "size": options.get("size") or options.get("resolution") or options.get("ratio") or "",
        "duration": result.get("duration") or options.get("duration") or "",
        "quality": result.get("quality") or options.get("quality") or "",
        "count": options.get("count") or len(images) or 1,
        "seed": seed,
        "generation_cost": result.get("generation_cost") or "",
        "cost_usd": result.get("cost_usd"),
        "unit_cost_usd": result.get("unit_cost_usd"),
        "cost": result.get("cost"),
        "cost_credits": result.get("cost_credits"),
        "unit_cost_credits": result.get("unit_cost_credits"),
        "balance_charged": result.get("balance_charged"),
        "balance_after": result.get("balance_after"),
        "charge_id": result.get("charge_id") or result.get("generation_id") or result.get("job_id") or "",
        "rendering_speed": result.get("rendering_speed") or options.get("rendering_speed") or "",
        "provider_model": result.get("provider_model") or "",
        "recraft_tools": _json_list(result.get("recraft_tools")),
        "image_options": options if mode == "image" else {},
        "video_options": options if mode == "video" else {},
        "music_options": options if mode == "music" else {},
        "voice_options": options if mode == "voice" else {},
        "reference_images": reference_images,
        "result_images": images,
        "result_thumbnails": thumbs,
        "image_url": images[0] if images else "",
        "thumbnail_url": thumbs[0] if thumbs else "",
        "thumb_url": thumbs[0] if thumbs else "",
        "video_url": videos[0] if videos else "",
        "videos": videos,
        "audio_url": audios[0] if audios else "",
        "audios": audios,
        "image_url_cover": result.get("image_url") if mode in ("music", "voice") else "",
        "title": result.get("title") or "",
        "sent_to_telegram": bool(result.get("sent_to_telegram")),
    }
    if provider_metadata:
        metadata["provider_metadata"] = provider_metadata
        for key in (
            "last_frame_url", "seed", "resolution", "ratio", "duration",
            "frames", "framespersecond", "generate_audio", "usage",
            "service_tier", "draft", "draft_task_id", "execution_expires_after",
        ):
            if provider_metadata.get(key) is not None and metadata.get(key) in (None, ""):
                metadata[key] = provider_metadata.get(key)
    return metadata


# =====================================================
# СИНХРОНИЗАЦИЯ С TELEGRAM: sync_completed_generation_to_telegram
# Отправляет готовый результат или статус в Telegram Bot и сохраняет признак отправки в metadata карточки.
# =====================================================
async def sync_completed_generation_to_telegram(telegram_id: int, mode: str, payload: dict, result: dict) -> bool:
    if not telegram_id or not isinstance(result, dict):
        return False
    if result.get("sent_to_telegram") is True:
        result["telegram_status"] = result.get("telegram_status") or "sent"
        return True
    if not BOT_TOKEN:
        result["sent_to_telegram"] = False
        result["telegram_status"] = "not_sent"
        return False

    result_type = str(result.get("type") or "").lower()
    mode = (result_type or mode or "").lower()
    model = result.get("model") or payload.get("model") or ""
    provider = result.get("provider") or payload.get("provider") or ""
    caption_lines = ["Готово ✅", "SYLVEX Pro Studio"]
    if model:
        caption_lines.append(f"Модель: {model}")
    elif provider:
        caption_lines.append(f"Провайдер: {provider}")
    generation_cost = result.get("generation_cost") or result.get("cost_credits")
    if generation_cost:
        caption_lines.append(f"Стоимость: {generation_cost}")
    caption = "\n".join(caption_lines)

    try:
        if mode == "image":
            images = (
                _json_list(result.get("images"))
                or _json_list(result.get("result_images"))
                or ([result.get("image_url")] if result.get("image_url") else [])
                or ([result.get("result_url")] if result.get("result_url") else [])
            )
            sent = await send_generated_images_to_telegram(telegram_id, images, caption=caption)
        elif mode == "video":
            videos = (
                _json_list(result.get("videos"))
                or ([result.get("video_url")] if result.get("video_url") else [])
                or ([result.get("result_url")] if result.get("result_url") else [])
            )
            sent = await _send_generated_videos_to_telegram(telegram_id, videos, caption=caption)
        elif mode in {"music", "voice"}:
            audios = (
                _json_list(result.get("audios"))
                or ([result.get("audio_url")] if result.get("audio_url") else [])
                or ([result.get("music_url")] if result.get("music_url") else [])
                or ([result.get("result_url")] if result.get("result_url") else [])
            )
            audio_url = audios[0] if audios else ""
            cover_url = (
                result.get("cover_url")
                or result.get("image_url")
                or result.get("thumbnail_url")
                or result.get("thumb_url")
                or ""
            )
            sent = await _send_generated_audio_to_telegram(
                telegram_id,
                audio_url,
                caption=caption,
                image_url=cover_url,
            )
        elif mode in {"text", "chat", "pro", "lite"}:
            text = str(result.get("text") or "").strip()
            if not text:
                sent = False
            else:
                response = requests.post(
                    f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                    json={
                        "chat_id": telegram_id,
                        "text": f"{caption}\n\n{text}"[:4096],
                        "disable_web_page_preview": True,
                    },
                    timeout=60,
                )
                sent = response.status_code < 400 and bool((response.json() if response.content else {}).get("ok"))
        else:
            sent = bool(result.get("sent_to_telegram"))
        result["sent_to_telegram"] = bool(sent)
        result["telegram_status"] = "sent" if sent else "not_sent"
        metadata = result.get("metadata")
        if isinstance(metadata, dict):
            metadata["sent_to_telegram"] = bool(sent)
            metadata["telegram_status"] = result["telegram_status"]
        prostudio_debug("TELEGRAM_SYNC_DONE", telegram_id=telegram_id, mode=mode, sent=bool(sent), job_id=result.get("job_id") or "")
        return bool(sent)
    except Exception as exc:
        result["sent_to_telegram"] = False
        result["telegram_status"] = "failed"
        prostudio_error("TELEGRAM_SYNC_FAILED", exc, telegram_id=telegram_id, mode=mode, job_id=result.get("job_id") or "")
        return False

# =====================================================
# PYTHON-БЛОК: materialize_data_image_url
# Выполняет отдельный шаг backend-логики SYLVEX.
# Связан с API, базой данных, провайдерами или подготовкой данных для Mini App.
# =====================================================
def materialize_data_image_url(url: str) -> str:
    value = str(url or "")
    if not value.startswith("data:image") or "," not in value:
        return value
    try:
        header, raw = value.split(",", 1)
        content = base64.b64decode(raw)
        mime = header.split(";", 1)[0].replace("data:", "").strip().lower()
        if content.startswith(b"\xff\xd8\xff") or mime == "image/jpeg":
            ext = "jpg"
        elif content.startswith(b"\x89PNG\r\n\x1a\n") or mime == "image/png":
            ext = "png"
        elif (content.startswith(b"RIFF") and content[8:12] == b"WEBP") or mime == "image/webp":
            ext = "webp"
        elif content.startswith(b"GIF87a") or content.startswith(b"GIF89a") or mime == "image/gif":
            ext = "gif"
        else:
            ext = "png"
        filename = f"{uuid4().hex}.{ext}"
        key = generated_key("images", filename)
        prostudio_debug("IMAGE_SAVE_START", path=key, ext=ext, bytes=len(content), storage="r2" if r2_enabled() else "local")
        saved_url = storage_put_bytes(content, key, mime)
        prostudio_debug("IMAGE_SAVE_DONE", path=key, url=saved_url, exists=storage_exists(key), bytes=len(content))
        return saved_url
    except Exception as exc:
        prostudio_error("IMAGE_SAVE_FAILED", exc)
        return value


# =====================================================
# PYTHON-БЛОК: materialize_image_urls
# Выполняет отдельный шаг backend-логики SYLVEX.
# Связан с API, базой данных, провайдерами или подготовкой данных для Mini App.
# =====================================================
def materialize_image_urls(image_urls: list) -> list:
    urls = _json_list(image_urls)
    prostudio_debug("IMAGE_MATERIALIZE_START", count=len(urls))
    result = [materialize_data_image_url(url) for url in urls]
    prostudio_debug("IMAGE_MATERIALIZE_DONE", count=len(result), urls=result)
    return result


def public_media_url(url: str) -> str:
    raw = str(url or "").strip()
    if not raw:
        return ""
    materialized = materialize_data_image_url(raw)
    if materialized.startswith("http://") or materialized.startswith("https://"):
        return materialized
    if materialized.startswith("/"):
        return (WEBAPP_URL or "").rstrip("/") + materialized
    return materialized


def _persist_remote_media_url(url: str, category: str) -> str:
    raw = str(url or "").strip()
    if not raw or storage_key_from_url(raw):
        return raw
    try:
        if raw.startswith("data:image"):
            return materialize_data_image_url(raw)
        if raw.startswith("/webapp/generated/") or raw.startswith("/generated/"):
            local_key = storage_key_from_url(raw)
            if local_key:
                local_path = WEBAPP_DIR.parent / local_key
                if local_path.is_file():
                    return storage_put_file(local_path, local_key, remove_local=r2_enabled())
            return raw
        if not raw.startswith(("http://", "https://")):
            return raw
        response = requests.get(raw, timeout=240)
        response.raise_for_status()
        content_type = (response.headers.get("content-type") or "").split(";", 1)[0].strip().lower()
        suffix = pathlib.Path(urllib.parse.urlparse(raw).path).suffix.lower()
        if not suffix or len(suffix) > 8:
            suffix = mimetypes.guess_extension(content_type) or {"images": ".png", "videos": ".mp4", "audio": ".mp3", "documents": ".bin", "thumbs": ".jpg"}.get(category, ".bin")
        filename = f"{uuid4().hex}{suffix}"
        return storage_put_bytes(response.content, generated_key(category, filename), content_type)
    except Exception as exc:
        prostudio_error("R2_MEDIA_PERSIST_FAILED", exc, source=_sql_text(raw, 180), category=category)
        return raw


def persist_generation_media(result: dict, mode: str) -> dict:
    if not isinstance(result, dict):
        return result
    persisted_by_source = {}

    def persist_once(value, category):
        source = str(value or "").strip()
        if not source:
            return value
        if source not in persisted_by_source:
            persisted_by_source[source] = _persist_remote_media_url(source, category)
        return persisted_by_source[source]

    scalar_fields = {
        "image_url": "images", "thumbnail_url": "thumbs", "video_url": "videos",
        "audio_url": "audio", "music_url": "audio", "file_url": "documents",
    }
    list_fields = {
        "images": "images", "thumbnails": "thumbs", "videos": "videos",
        "audio_urls": "audio", "audios": "audio", "files": "documents",
    }
    for field, category in scalar_fields.items():
        if result.get(field):
            result[field] = persist_once(result[field], category)
    primary_category = {
        "image": "images", "video": "videos", "music": "audio", "voice": "audio",
    }.get(str(mode or "").strip().lower(), "documents")
    for field in ("result_url", "full_url", "url", "song_url"):
        if result.get(field):
            result[field] = persist_once(result[field], primary_category)
    for field, category in list_fields.items():
        values = result.get(field)
        if isinstance(values, list):
            result[field] = [persist_once(value, category) for value in values]
    metadata = result.get("metadata")
    if isinstance(metadata, dict):
        for field, category in scalar_fields.items():
            if metadata.get(field):
                metadata[field] = persist_once(metadata[field], category)
    return result


def verify_persisted_generation_media(result: dict, mode: str) -> list[str]:
    """Require durable R2 objects before a production media job can complete."""
    normalized_mode = str(mode or "").strip().lower()
    if normalized_mode not in {"image", "video", "music", "voice"}:
        return []

    if not r2_enabled():
        public_base = str(WEBAPP_URL or "").strip().lower()
        is_local_development = (
            not public_base
            or "localhost" in public_base
            or "127.0.0.1" in public_base
            or public_base.startswith("http://0.0.0.0")
        )
        if is_local_development:
            return []
        raise RuntimeError(
            "Cloudflare R2 is required for production generation results; "
            "check R2_BUCKET, R2_ENDPOINT, R2_ACCESS_KEY_ID and R2_SECRET_ACCESS_KEY"
        )

    candidates = generation_result_urls(result, normalized_mode)
    urls = list(dict.fromkeys(str(value or "").strip() for value in candidates if str(value or "").strip()))
    if not urls:
        raise RuntimeError(f"Persisted {normalized_mode} result has no primary media URL")

    invalid = []
    for url in urls:
        key = storage_key_from_url(url)
        if not key or not storage_exists(key):
            invalid.append(url)
    if invalid:
        raise RuntimeError(
            f"R2 persistence verification failed for {normalized_mode}: "
            + ", ".join(_sql_text(value, 180) for value in invalid[:3])
        )
    return urls


def build_completed_job_result(result: dict, mode: str) -> dict:
    """Build the small durable payload required by Mini App polling."""
    keep = {
        "ok", "type", "status", "provider", "model", "provider_model",
        "image_url", "images", "thumbnail_url", "thumb_url", "thumbnails",
        "video_url", "videos", "audio_url", "audio_urls", "audios", "music_url",
        "result_url", "full_url", "url", "file_url", "title", "text", "duration",
        "cost", "price", "cost_credits", "generation_cost", "unit_cost_credits",
        "balance_charged", "balance_after", "charge_id",
    }
    final_result = {key: value for key, value in result.items() if key in keep}
    final_result["ok"] = True
    final_result["status"] = "completed"
    final_result["type"] = result.get("type") or mode
    final_result["sent_to_telegram"] = False
    urls = generation_result_urls(final_result, mode)
    primary_url = urls[0] if urls else ""
    final_result["metadata"] = {
        "type": final_result["type"],
        "provider": final_result.get("provider") or "",
        "model": final_result.get("model") or "",
        "provider_model": final_result.get("provider_model") or "",
        "result_url": primary_url,
        "full_url": primary_url,
        "image_url": final_result.get("image_url") or "",
        "thumbnail_url": final_result.get("thumbnail_url") or final_result.get("thumb_url") or "",
        "video_url": final_result.get("video_url") or "",
        "audio_url": final_result.get("audio_url") or final_result.get("music_url") or "",
        "sent_to_telegram": False,
    }
    return final_result


def image_file_tuple_from_url(url: str, fallback_name: str = "reference.png") -> tuple | None:
    raw = str(url or "").strip()
    if not raw:
        return None
    content = b""
    mime_type = "image/png"
    filename = fallback_name or "reference.png"
    try:
        if raw.startswith("data:image/") and ";base64," in raw:
            head, data = raw.split(";base64,", 1)
            mime_type = head.replace("data:", "") or mime_type
            ext = mime_type.split("/", 1)[1].replace("jpeg", "jpg") or "png"
            filename = pathlib.Path(filename).stem + "." + ext
            content = base64.b64decode(data)
        elif storage_key_from_url(raw):
            content = storage_read_bytes(raw)
            filename = pathlib.Path(urllib.parse.urlparse(raw).path).name or filename
        elif raw.startswith("/webapp/"):
            local_path = WEBAPP_DIR / raw.replace("/webapp/", "", 1)
            content = local_path.read_bytes()
            filename = local_path.name or filename
        elif raw.startswith("/generated/"):
            local_path = WEBAPP_DIR / raw.replace("/generated/", "generated/", 1)
            content = local_path.read_bytes()
            filename = local_path.name or filename
        elif raw.startswith("/preset_catalog/"):
            relative_path = urllib.parse.unquote(raw.replace("/preset_catalog/", "", 1))
            local_path = (PRESET_CATALOG_DIR / relative_path).resolve()
            catalog_root = PRESET_CATALOG_DIR.resolve()
            if not str(local_path).startswith(str(catalog_root) + os.sep):
                return None
            content = local_path.read_bytes()
            filename = local_path.name or filename
        elif raw.startswith("http://") or raw.startswith("https://"):
            response = requests.get(raw, timeout=90)
            response.raise_for_status()
            content = response.content
            content_type = (response.headers.get("content-type") or "").split(";", 1)[0].strip().lower()
            if content_type.startswith("image/"):
                mime_type = content_type
            parsed_name = pathlib.Path(urllib.parse.urlparse(raw).path).name
            if parsed_name:
                filename = parsed_name
        else:
            return None
        suffix = pathlib.Path(filename).suffix.lower()
        if suffix in {".jpg", ".jpeg"}:
            mime_type = "image/jpeg"
        elif suffix == ".webp":
            mime_type = "image/webp"
        elif suffix == ".gif":
            mime_type = "image/gif"
        elif suffix == ".png":
            mime_type = "image/png"
        if not content:
            return None
        return (filename, content, mime_type)
    except Exception as exc:
        prostudio_error("IMAGE_FILE_LOAD_FAILED", exc, source=_sql_text(raw, 180))
        return None


def byteplus_image_input(value: str, index: int = 0) -> str:
    """Return an accessible URL or an inline Base64 image for BytePlus."""
    raw = str(value or "").strip()
    if not raw:
        return ""
    if raw.startswith("data:image/") and ";base64," in raw:
        head, encoded = raw.split(";base64,", 1)
        mime_type = head.replace("data:", "").strip().lower() or "image/png"
        return f"data:{mime_type};base64,{encoded.strip()}"
    public_base = str(WEBAPP_URL or "").rstrip("/")
    if public_base and raw.startswith(public_base + "/"):
        local_public_path = urllib.parse.urlparse(raw).path
        local_input = byteplus_image_input(local_public_path, index)
        if local_input:
            return local_input
    if raw.startswith("http://") or raw.startswith("https://"):
        return raw
    file_tuple = image_file_tuple_from_url(raw, fallback_name=f"reference-{index + 1}.png")
    if not file_tuple:
        return ""
    _, content, mime_type = file_tuple
    mime_type = str(mime_type or "image/png").lower()
    return f"data:{mime_type};base64,{base64.b64encode(content).decode('ascii')}"


def provider_object_to_dict(value) -> dict:
    if isinstance(value, dict):
        return value
    for method in ("model_dump", "to_dict", "dict"):
        fn = getattr(value, method, None)
        if callable(fn):
            try:
                data = fn()
                if isinstance(data, dict):
                    return data
            except Exception:
                pass
    try:
        return json.loads(json.dumps(value, default=lambda obj: getattr(obj, "__dict__", str(obj))))
    except Exception:
        return {}


# =====================================================
# PYTHON-БЛОК: create_image_thumbnails
# Выполняет отдельный шаг backend-логики SYLVEX.
# Связан с API, базой данных, провайдерами или подготовкой данных для Mini App.
# =====================================================
def create_image_thumbnails(image_urls: list, size: int = 256) -> list:
    thumbs = []
    if not image_urls:
        return thumbs

    for url in image_urls:
        thumb_url = ""
        try:
            from PIL import Image
            import base64
            import io

            if str(url).startswith("data:"):
                raw = str(url).split(",", 1)[1] if "," in str(url) else ""
                content = base64.b64decode(raw)
            elif storage_key_from_url(str(url)):
                content = storage_read_bytes(str(url))
            else:
                r = requests.get(url, timeout=45)
                if r.status_code >= 400 or not r.content:
                    raise ValueError("source_download_failed")
                content = r.content

            with Image.open(io.BytesIO(content)) as img:
                img = img.convert("RGB")
                img.thumbnail((size, size))
                filename = f"{uuid4().hex}.jpg"
                output = io.BytesIO()
                prostudio_debug("THUMBNAIL_CREATE_START", source=_sql_text(url, 180), path=filename, size=size)
                img.save(output, format="JPEG", quality=78, optimize=True)
                thumb_url = storage_put_bytes(output.getvalue(), generated_key("thumbs", filename), "image/jpeg")
                prostudio_debug("THUMBNAIL_CREATE_DONE", path=filename, url=thumb_url, exists=storage_exists(thumb_url), bytes=output.tell())
        except Exception as exc:
            prostudio_error("THUMBNAIL_CREATE_FAILED", exc, source=_sql_text(url, 180))
            thumb_url = ""
        thumbs.append(thumb_url)
    return thumbs

# =====================================================
# PYTHON-БЛОК: attach_image_thumbnails
# Выполняет отдельный шаг backend-логики SYLVEX.
# Связан с API, базой данных, провайдерами или подготовкой данных для Mini App.
# =====================================================
def attach_image_thumbnails(result: dict) -> dict:
    images = (
        _json_list(result.get("images"))
        or _json_list(result.get("urls"))
        or _json_list(result.get("output"))
        or ([result.get("image_url")] if result.get("image_url") else [])
        or ([result.get("result_url")] if result.get("result_url") else [])
    )
    if not images:
        return result
    images = materialize_image_urls(images)
    thumbs = _json_list(result.get("thumbnails"))
    if len(thumbs) != len(images):
        thumbs = create_image_thumbnails(images)
    result["image_url"] = images[0]
    result["result_url"] = images[0]
    result["full_url"] = images[0]
    result["images"] = images
    result["thumbnail_url"] = thumbs[0] if thumbs else ""
    result["thumb_url"] = thumbs[0] if thumbs else ""
    result["thumbnails"] = thumbs or []
    if result.get("thumbnail_url") and not (str(result.get("thumbnail_url")).startswith("http://") or str(result.get("thumbnail_url")).startswith("https://")):
        result["preview_fallback_url"] = images[0]
    print("PROSTUDIO IMAGE THUMBNAILS:", {
        "image_count": len(images),
        "thumb_count": len(result.get("thumbnails") or []),
        "image_url": _sql_text(result.get("image_url"), 180),
        "thumbnail_url": result.get("thumbnail_url"),
        "thumb_url": result.get("thumb_url"),
        "preview_fallback_url": result.get("preview_fallback_url") or "",
    })
    return result

# =====================================================
# СОХРАНЕНИЕ В БАЗУ ДАННЫХ: save_prostudio_message
# Записывает состояние пользователя, job, metadata или результат генерации в общую базу Mini App и Telegram Bot.
# =====================================================
def save_prostudio_message(payload: dict, result: dict) -> str:
    conversation_id = payload.get("conversation_id") or str(uuid4())
    telegram_id = int(payload.get("telegram_id") or 0)
    if not DATABASE_URL or not telegram_id:
        return conversation_id
    metadata = _json_obj(result.get("metadata")) or build_prostudio_metadata(payload, result)
    print("PROSTUDIO MESSAGE SAVE DEBUG:", {
        "conversation_id": conversation_id,
        "telegram_id": telegram_id,
        "mode": payload.get("mode") or "text",
        "model": payload.get("model") or result.get("model") or "",
        "provider": payload.get("provider") or result.get("provider") or "",
        "image_url": result.get("image_url") or "",
        "images": _json_list(result.get("images")),
        "thumbnail_url": result.get("thumbnail_url") or "",
        "thumbnails": _json_list(result.get("thumbnails")),
        "metadata_keys": sorted((metadata or {}).keys()),
        "metadata_image_url": (metadata or {}).get("image_url"),
        "metadata_thumbnail_url": (metadata or {}).get("thumbnail_url"),
        "generation_cost": (metadata or {}).get("generation_cost"),
        "cost_credits": (metadata or {}).get("cost_credits"),
    })

    try:
        prostudio_debug(
            "MESSAGE_DB_WRITE_START",
            conversation_id=conversation_id,
            telegram_id=telegram_id,
            mode=payload.get("mode") or "text",
            image_url=result.get("image_url") or "",
            thumbnail_url=result.get("thumbnail_url") or "",
        )
        ensure_prostudio_table()
        conn = db_connect(DATABASE_URL)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO prostudio_messages (
                conversation_id,
                telegram_id,
                mode,
                prompt,
                response_text,
                image_url,
                images_json,
                thumbnails_json,
                thumb_url,
                video_url,
                videos_json,
                audio_url,
                audios_json,
                metadata_json,
                status,
                model,
                provider,
                cost,
                request_json,
                response_json,
                updated_at,
                completed_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, NOW(), NOW())
        """, (
            conversation_id,
            telegram_id,
            payload.get("mode") or "text",
            payload.get("prompt") or "",
            result.get("text") or "",
            result.get("image_url") or "",
            json.dumps(_json_list(result.get("images")), ensure_ascii=False),
            json.dumps(_json_list(result.get("thumbnails")), ensure_ascii=False),
            result.get("thumb_url") or "",
            result.get("video_url") or "",
            json.dumps(_json_list(result.get("videos")), ensure_ascii=False),
            result.get("audio_url") or "",
            json.dumps(_json_list(result.get("audios")), ensure_ascii=False),
            json.dumps(metadata, ensure_ascii=False),
            result.get("status") or "completed",
            payload.get("model") or "",
            payload.get("provider") or "",
            int(result.get("cost") or result.get("price") or 0),
            _safe_json_dumps(_sanitize_event_payload(payload, max_text=1200, max_items=40, depth=5)),
            _safe_json_dumps(_sanitize_event_payload(result, max_text=1200, max_items=50, depth=5)),
        ))
        conn.commit()
        cursor.close()
        conn.close()
        prostudio_debug("MESSAGE_DB_WRITE_DONE", conversation_id=conversation_id, telegram_id=telegram_id)
    except Exception as exc:
        prostudio_error("MESSAGE_DB_WRITE_FAILED", exc, conversation_id=conversation_id, telegram_id=telegram_id)

    return conversation_id

# =====================================================
# PYTHON-БЛОК: payment_url
# Выполняет отдельный шаг backend-логики SYLVEX.
# Связан с API, базой данных, провайдерами или подготовкой данных для Mini App.
# =====================================================
def payment_url(pack_id: str, method: str = "paypal") -> str:
    params = urllib.parse.urlencode({
        "pack_id": pack_id or "",
        "method": method or "paypal",
    })
    return PAYMENT_WEBAPP_URL + ("&" if "?" in PAYMENT_WEBAPP_URL else "?") + params

# =====================================================
# API ENDPOINT: public_prostudio_conversations
# Принимает HTTP-запрос от Mini App или Telegram Bot.
# Маршрут FastAPI: @app.get("/api/public/prostudio/conversations")
# Проверяет входные данные, работает с базой/провайдерами и возвращает JSON-ответ фронтенду.
# =====================================================
@app.get("/api/public/prostudio/conversations")
# =====================================================
# PYTHON-БЛОК: public_prostudio_conversations
# Выполняет отдельный шаг backend-логики SYLVEX.
# Связан с API, базой данных, провайдерами или подготовкой данных для Mini App.
# =====================================================
async def public_prostudio_conversations(
    telegram_id: int = 0,
    conversation_id: str = "",
    mode: str = "",
    limit: int = 30,
    offset: int = 0,
):
    if not DATABASE_URL or not telegram_id:
        return {"ok": True, "conversations": [], "messages": []}

    try:
        ensure_prostudio_table()
        conn = db_connect(DATABASE_URL)
        cursor = conn.cursor()

        limit = max(1, min(int(limit or 30), 100))
        offset = max(0, int(offset or 0))

        if conversation_id:
            cursor.execute("""
                SELECT
                    prompt, response_text, image_url, images_json, thumbnails_json, thumb_url,
                    video_url, videos_json, audio_url, audios_json, metadata_json, created_at,
                    status, model, provider, cost, response_json
                FROM prostudio_messages
                WHERE telegram_id = %s
                  AND conversation_id = %s
                ORDER BY created_at ASC, id ASC
                LIMIT %s OFFSET %s
            """, (telegram_id, conversation_id, limit, offset))
            rows = cursor.fetchall()
            cursor.close()
            conn.close()
            messages = []
            for (
                prompt, response_text, image_url, images_json, thumbnails_json, thumb_url,
                video_url, videos_json, audio_url, audios_json, metadata_json, created_at,
                status, model, provider, cost, response_json,
            ) in rows:
                images = _json_list(images_json) or ([image_url] if image_url else [])
                thumbs = _json_list(thumbnails_json) or ([thumb_url] if thumb_url else [])
                videos = _json_list(videos_json) or ([video_url] if video_url else [])
                audios = _json_list(audios_json) or ([audio_url] if audio_url else [])
                created_value = created_at.isoformat() if hasattr(created_at, "isoformat") else created_at
                metadata = _json_obj(metadata_json)
                if images:
                    if not metadata:
                        metadata = {
                            "type": "image",
                            "prompt": prompt or "",
                            "result_images": images,
                            "result_thumbnails": thumbs,
                            "image_url": images[0] if images else "",
                            "result_url": images[0] if images else "",
                            "full_url": images[0] if images else "",
                            "thumbnail_url": thumbs[0] if thumbs else "",
                            "thumb_url": thumbs[0] if thumbs else "",
                        }
                if metadata:
                    metadata["created_at"] = metadata.get("created_at") or created_value
                    metadata["status"] = metadata.get("status") or status or "completed"
                    metadata["model"] = metadata.get("model") or model or ""
                    metadata["provider"] = metadata.get("provider") or provider or ""
                    metadata["cost"] = metadata.get("cost") or cost or 0
                    response_data = _json_obj(response_json)
                    if response_data.get("job_id") and not metadata.get("job_id"):
                        metadata["job_id"] = response_data.get("job_id")
                if prompt:
                    messages.append({
                        "role": "user",
                        "prompt": prompt,
                        "created_at": created_value,
                    })
                messages.append({
                    "role": "assistant",
                    "response_text": response_text or "",
                    "image_url": images[0] if images else "",
                    "images": images,
                    "thumbnail_url": thumbs[0] if thumbs else "",
                    "thumb_url": thumbs[0] if thumbs else "",
                    "thumbnails": thumbs,
                    "video_url": videos[0] if videos else "",
                    "videos": videos,
                    "audio_url": audios[0] if audios else "",
                    "audios": audios,
                    "metadata": metadata,
                    "status": status or "completed",
                    "model": model or "",
                    "provider": provider or "",
                    "cost": cost or 0,
                    "created_at": created_value,
                })
            return {"ok": True, "messages": messages, "limit": limit, "offset": offset}

        mode_filter = (mode or "").strip().lower()
        mode_where = "AND mode = %s" if mode_filter in {"image", "video", "music", "voice"} else ""
        params = [telegram_id]
        if mode_where:
            params.append(mode_filter)
        params.extend([min(limit, 80), offset])
        cursor.execute(f"""
            SELECT
                conversation_id,
                COALESCE(NULLIF(MAX(prompt), ''), 'Chat') AS title,
                MAX(created_at) AS updated_at,
                COALESCE(NULLIF(MAX(mode), ''), 'image') AS type,
                MIN(created_at) AS created_at
            FROM prostudio_messages
            WHERE telegram_id = %s
              {mode_where}
            GROUP BY conversation_id
            ORDER BY updated_at DESC
            LIMIT %s OFFSET %s
        """, tuple(params))
        rows = cursor.fetchall()
        cursor.close()
        conn.close()
        return {
            "ok": True,
            "conversations": [
                {
                    "id": row[0],
                    "title": (row[1] or "Chat")[:64],
                    "updated_at": row[2],
                    "type": row[3] or "image",
                    "created_at": row[4],
                }
                for row in rows
            ],
        }
    except Exception as exc:
        print("PROSTUDIO CONVERSATIONS FAILED:", exc)
        return {"ok": True, "conversations": [], "messages": []}

# =====================================================
# API ENDPOINT: delete_public_prostudio_conversation
# Принимает HTTP-запрос от Mini App или Telegram Bot.
# Маршрут FastAPI: @app.delete("/api/public/prostudio/conversations")
# Проверяет входные данные, работает с базой/провайдерами и возвращает JSON-ответ фронтенду.
# =====================================================
@app.delete("/api/public/prostudio/conversations")
# =====================================================
# PYTHON-БЛОК: delete_public_prostudio_conversation
# Выполняет отдельный шаг backend-логики SYLVEX.
# Связан с API, базой данных, провайдерами или подготовкой данных для Mini App.
# =====================================================
async def delete_public_prostudio_conversation(
    telegram_id: int = 0,
    conversation_id: str = "",
):
    if not DATABASE_URL or not telegram_id or not conversation_id:
        return {"ok": True}

    try:
        ensure_prostudio_table()
        conn = db_connect(DATABASE_URL)
        cursor = conn.cursor()
        cursor.execute("""
            DELETE FROM prostudio_messages
            WHERE telegram_id = %s
              AND conversation_id = %s
        """, (telegram_id, conversation_id))
        conn.commit()
        cursor.close()
        conn.close()
    except Exception as exc:
        print("PROSTUDIO CONVERSATION DELETE FAILED:", exc)

    return {"ok": True}


@app.get("/api/public/prostudio/gallery")
async def public_prostudio_gallery(telegram_id: int = 0, limit: int = 80, offset: int = 0):
    """Return completed generated content owned by one Mini App user."""
    if not DATABASE_URL or not telegram_id:
        return {"ok": True, "items": []}
    try:
        ensure_prostudio_table()
        conn = db_connect(DATABASE_URL)
        cursor = conn.cursor()
        safe_limit = max(1, min(int(limit or 80), 100))
        safe_offset = max(0, int(offset or 0))
        cursor.execute("""
            SELECT id, conversation_id, mode, prompt, response_text, image_url, images_json,
                   thumbnails_json, thumb_url, video_url, videos_json, audio_url, audios_json,
                   metadata_json, created_at, status, model, provider, response_json
            FROM prostudio_messages
            WHERE telegram_id = %s
              AND (COALESCE(image_url, '') <> '' OR COALESCE(video_url, '') <> ''
                   OR COALESCE(audio_url, '') <> '' OR COALESCE(response_text, '') <> '')
            ORDER BY created_at DESC, id DESC
            LIMIT %s OFFSET %s
        """, (telegram_id, safe_limit, safe_offset))
        rows = cursor.fetchall()
        cursor.close()
        conn.close()
        items = []
        for row in rows:
            (message_id, conversation_id, mode, prompt, response_text, image_url, images_json,
             thumbnails_json, thumb_url, video_url, videos_json, audio_url, audios_json,
             metadata_json, created_at, status, model, provider, response_json) = row
            images = _json_list(images_json) or ([image_url] if image_url else [])
            thumbs = _json_list(thumbnails_json) or ([thumb_url] if thumb_url else [])
            videos = _json_list(videos_json) or ([video_url] if video_url else [])
            audios = _json_list(audios_json) or ([audio_url] if audio_url else [])
            metadata = _json_obj(metadata_json)
            response_data = _json_obj(response_json)
            kind = str(metadata.get("type") or mode or ("video" if videos else "music" if audios else "image" if images else "text")).lower()
            media_url = (videos[0] if videos else audios[0] if audios else images[0] if images else "")
            preview_url = (
                thumbs[0] if thumbs else images[0] if images else
                metadata.get("thumbnail_url") or metadata.get("cover_url") or
                metadata.get("artwork_url") or metadata.get("image_url") or
                response_data.get("thumbnail_url") or response_data.get("cover_url") or
                response_data.get("image_url") or ""
            )
            items.append({
                "id": message_id, "conversation_id": conversation_id, "type": kind,
                "prompt": prompt or metadata.get("prompt") or "", "text": response_text or "",
                "title": metadata.get("title") or response_data.get("title") or prompt or "",
                "genre": metadata.get("genre") or response_data.get("genre") or "",
                "media_url": media_url, "preview_url": preview_url,
                "job_id": metadata.get("job_id") or response_data.get("job_id") or "",
                "status": status or metadata.get("status") or "completed",
                "model": metadata.get("model_label") or model or "", "provider": provider or "",
                "created_at": created_at.isoformat() if hasattr(created_at, "isoformat") else created_at,
            })
        return {"ok": True, "items": items, "limit": safe_limit, "offset": safe_offset}
    except Exception as exc:
        print("PROSTUDIO GALLERY FAILED:", exc)
        return {"ok": True, "items": []}


@app.delete("/api/public/prostudio/gallery/{message_id}")
async def delete_public_prostudio_gallery_item(message_id: int, telegram_id: int = 0):
    """Delete one generated result without deleting the rest of its conversation."""
    if not DATABASE_URL or not telegram_id or not message_id:
        return {"ok": True}
    try:
        ensure_prostudio_table()
        conn = db_connect(DATABASE_URL)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM prostudio_messages WHERE id = %s AND telegram_id = %s", (message_id, telegram_id))
        conn.commit()
        cursor.close()
        conn.close()
    except Exception as exc:
        print("PROSTUDIO GALLERY DELETE FAILED:", exc)
    return {"ok": True}


def ensure_community_tables():
    if not DATABASE_URL:
        return
    ensure_user_profiles_table()
    conn = db_connect(DATABASE_URL)
    cursor = conn.cursor()
    try:
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS community_posts (
            id BIGSERIAL PRIMARY KEY,
            telegram_id BIGINT NOT NULL,
            source_message_id BIGINT NOT NULL,
            content_type TEXT NOT NULL,
            media_url TEXT,
            media_urls JSONB DEFAULT '[]'::jsonb,
            preview_url TEXT,
            body TEXT,
            model TEXT,
            created_at TIMESTAMP DEFAULT NOW(),
            UNIQUE (telegram_id, source_message_id)
        )
        """)
        cursor.execute("ALTER TABLE community_posts ADD COLUMN IF NOT EXISTS media_urls JSONB DEFAULT '[]'::jsonb")
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS community_likes (
            post_id BIGINT NOT NULL REFERENCES community_posts(id) ON DELETE CASCADE,
            telegram_id BIGINT NOT NULL,
            created_at TIMESTAMP DEFAULT NOW(),
            PRIMARY KEY (post_id, telegram_id)
        )
        """)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS community_comments (
            id BIGSERIAL PRIMARY KEY,
            post_id BIGINT NOT NULL REFERENCES community_posts(id) ON DELETE CASCADE,
            telegram_id BIGINT NOT NULL,
            body TEXT NOT NULL,
            parent_comment_id BIGINT REFERENCES community_comments(id) ON DELETE SET NULL,
            edited_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT NOW()
        )
        """)
        cursor.execute("ALTER TABLE community_comments ADD COLUMN IF NOT EXISTS parent_comment_id BIGINT REFERENCES community_comments(id) ON DELETE SET NULL")
        cursor.execute("ALTER TABLE community_comments ADD COLUMN IF NOT EXISTS edited_at TIMESTAMP")
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS community_comment_likes (
            comment_id BIGINT NOT NULL REFERENCES community_comments(id) ON DELETE CASCADE,
            telegram_id BIGINT NOT NULL,
            created_at TIMESTAMP DEFAULT NOW(),
            PRIMARY KEY (comment_id, telegram_id)
        )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_community_posts_created ON community_posts (created_at DESC)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_community_comments_post ON community_comments (post_id, created_at)")
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS community_friendships (
            requester_id BIGINT NOT NULL,
            addressee_id BIGINT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT NOW(), updated_at TIMESTAMP DEFAULT NOW(),
            PRIMARY KEY (requester_id, addressee_id),
            CHECK (requester_id <> addressee_id)
        )
        """)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS community_messages (
            id BIGSERIAL PRIMARY KEY,
            sender_id BIGINT NOT NULL,
            recipient_id BIGINT NOT NULL DEFAULT 0,
            body TEXT NOT NULL,
            read_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT NOW()
        )
        """)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS community_notifications (
            id BIGSERIAL PRIMARY KEY,
            telegram_id BIGINT NOT NULL,
            actor_id BIGINT NOT NULL,
            kind TEXT NOT NULL,
            post_id BIGINT REFERENCES community_posts(id) ON DELETE CASCADE,
            comment_id BIGINT REFERENCES community_comments(id) ON DELETE CASCADE,
            body TEXT,
            read_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT NOW()
        )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_community_messages_pair ON community_messages (sender_id, recipient_id, created_at DESC)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_community_notifications_user ON community_notifications (telegram_id, created_at DESC)")
        conn.commit()
    finally:
        cursor.close()
        conn.close()


@app.get("/api/public/community/feed")
async def public_community_feed(telegram_id: int = 0, limit: int = 30, offset: int = 0):
    if not DATABASE_URL:
        return {"ok": True, "items": []}
    ensure_community_tables()
    conn = db_connect(DATABASE_URL)
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT p.id, p.telegram_id, p.content_type, p.media_url, p.preview_url,
                   p.body, p.model, p.created_at,
                   COALESCE(up.display_name, u.first_name, 'SYLVEX User'),
                   COALESCE(up.custom_avatar_url, ''), COALESCE(u.username, ''),
                   COUNT(DISTINCT l.telegram_id),
                   BOOL_OR(l.telegram_id = %s), COUNT(DISTINCT c.id), p.media_urls,
                   (SELECT COUNT(*) FROM community_posts author_posts
                    JOIN community_likes author_likes ON author_likes.post_id = author_posts.id
                    WHERE author_posts.telegram_id = p.telegram_id)
            FROM community_posts p
            LEFT JOIN users u ON u.telegram_id = p.telegram_id
            LEFT JOIN user_profiles up ON up.telegram_id = p.telegram_id
            LEFT JOIN community_likes l ON l.post_id = p.id
            LEFT JOIN community_comments c ON c.post_id = p.id
            GROUP BY p.id, up.display_name, up.custom_avatar_url, u.first_name, u.username
            ORDER BY p.created_at DESC
            LIMIT %s OFFSET %s
        """, (telegram_id, max(1, min(int(limit), 50)), max(0, int(offset))))
        rows = cursor.fetchall()
        items = [{
            "id": row[0], "author_id": row[1], "type": row[2], "media_url": row[3] or "",
            "preview_url": row[4] or row[3] or "", "body": row[5] or "", "model": row[6] or "",
            "created_at": _to_iso(row[7]), "author_name": row[8], "author_avatar": row[9] or "",
            "author_username": row[10] or "", "likes": int(row[11] or 0),
            "liked": bool(row[12]), "comments": int(row[13] or 0),
            "media_urls": _json_list(row[14]) or ([row[3]] if row[3] else []),
            "author_likes": int(row[15] or 0), "is_own": bool(telegram_id and int(row[1]) == telegram_id),
        } for row in rows]
        return {"ok": True, "items": items}
    finally:
        cursor.close()
        conn.close()


@app.delete("/api/public/community/posts/{post_id}")
async def public_community_delete_post(post_id: int, request: Request):
    payload = await request.json()
    telegram_id = int(payload.get("telegram_id") or 0)
    init_data = payload.get("initData") or ""
    if not telegram_id:
        return JSONResponse({"ok": False, "error": "telegram_id_required"}, status_code=400)
    if init_data and BOT_TOKEN:
        signed_telegram_id = _telegram_id_from_init_data(init_data)
        if not signed_telegram_id or signed_telegram_id != telegram_id:
            return JSONResponse({"ok": False, "error": "invalid_init_data"}, status_code=401)
    ensure_community_tables()
    conn = db_connect(DATABASE_URL)
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM community_posts WHERE id = %s AND telegram_id = %s RETURNING id", (post_id, telegram_id))
        if not cursor.fetchone():
            return JSONResponse({"ok": False, "error": "post_not_found_or_forbidden"}, status_code=403)
        conn.commit()
        return {"ok": True}
    finally:
        cursor.close()
        conn.close()


@app.post("/api/public/community/posts")
async def public_community_publish(request: Request):
    payload = await request.json()
    telegram_id = int(payload.get("telegram_id") or 0)
    message_ids = payload.get("message_ids") or [payload.get("message_id")]
    message_ids = list(dict.fromkeys(int(value or 0) for value in message_ids if int(value or 0)))[:4]
    message_id = message_ids[0] if message_ids else 0
    init_data = payload.get("initData") or ""
    if not telegram_id or not message_id:
        return JSONResponse({"ok": False, "error": "invalid_request"}, status_code=400)
    if init_data and BOT_TOKEN:
        signed_telegram_id = _telegram_id_from_init_data(init_data)
        if not signed_telegram_id or signed_telegram_id != telegram_id:
            return JSONResponse({"ok": False, "error": "invalid_init_data"}, status_code=401)
    ensure_community_tables()
    conn = db_connect(DATABASE_URL)
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT mode, prompt, response_text, image_url, images_json, thumbnails_json,
                   thumb_url, video_url, videos_json, audio_url, audios_json, metadata_json, model, id
            FROM prostudio_messages WHERE id = ANY(%s) AND telegram_id = %s
        """, (message_ids, telegram_id))
        rows = cursor.fetchall()
        rows.sort(key=lambda item: message_ids.index(int(item[13])))
        if not rows:
            return JSONResponse({"ok": False, "error": "generation_not_found"}, status_code=404)
        row = rows[0]
        mode, prompt, response_text, image_url, images_json, thumbnails_json, thumb_url, video_url, videos_json, audio_url, audios_json, metadata_json, model, _ = row
        images, thumbs = _json_list(images_json), _json_list(thumbnails_json)
        videos, audios = _json_list(videos_json), _json_list(audios_json)
        metadata = _json_obj(metadata_json)
        kind = str(metadata.get("type") or mode or ("video" if videos else "music" if audios else "image" if images else "text")).lower()
        kind = "music" if kind == "audio" else kind
        if kind not in {"image", "video"}:
            return JSONResponse({"ok": False, "error": "unsupported_community_media"}, status_code=400)
        media = (videos[0] if videos else video_url) or (audios[0] if audios else audio_url) or (images[0] if images else image_url) or ""
        preview = (thumbs[0] if thumbs else thumb_url) or (images[0] if images else image_url) or ""
        media_urls = []
        for candidate in rows:
            c_mode, _, _, c_image, c_images, _, _, c_video, c_videos, c_audio, c_audios, c_meta, _, _ = candidate
            c_meta = _json_obj(c_meta)
            c_kind = str(c_meta.get("type") or c_mode or "").lower()
            if len(rows) > 1 and c_kind != "image":
                return JSONResponse({"ok": False, "error": "multiple_media_requires_images"}, status_code=400)
            c_url = ((_json_list(c_images) or [c_image])[0] if (_json_list(c_images) or c_image) else "") or ((_json_list(c_videos) or [c_video])[0] if (_json_list(c_videos) or c_video) else "") or ((_json_list(c_audios) or [c_audio])[0] if (_json_list(c_audios) or c_audio) else "")
            if c_url:
                media_urls.append(c_url)
        caption = str(payload.get("caption") or "").strip()
        if re.search(r"(?:https?://|www\.|t\.me/|@[A-Za-z0-9_]{4,})", caption, re.IGNORECASE):
            return JSONResponse({"ok": False, "error": "external_links_forbidden"}, status_code=400)
        body = caption[:360]
        cursor.execute("""
            INSERT INTO community_posts
                (telegram_id, source_message_id, content_type, media_url, media_urls, preview_url, body, model)
            VALUES (%s, %s, %s, %s, %s::jsonb, %s, %s, %s)
            ON CONFLICT (telegram_id, source_message_id) DO UPDATE SET body = EXCLUDED.body, media_urls = EXCLUDED.media_urls
            RETURNING id
        """, (telegram_id, message_id, kind, media, json.dumps(media_urls), preview, body, model or ""))
        post_id = cursor.fetchone()[0]
        conn.commit()
        return {"ok": True, "post_id": post_id}
    finally:
        cursor.close()
        conn.close()


@app.post("/api/public/community/posts/{post_id}/like")
async def public_community_like(post_id: int, request: Request):
    payload = await request.json()
    telegram_id = int(payload.get("telegram_id") or 0)
    init_data = payload.get("initData") or ""
    if not telegram_id:
        return JSONResponse({"ok": False, "error": "telegram_id_required"}, status_code=400)
    if init_data and BOT_TOKEN:
        signed_telegram_id = _telegram_id_from_init_data(init_data)
        if not signed_telegram_id or signed_telegram_id != telegram_id:
            return JSONResponse({"ok": False, "error": "invalid_init_data"}, status_code=401)
    ensure_community_tables()
    conn = db_connect(DATABASE_URL)
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM community_likes WHERE post_id = %s AND telegram_id = %s RETURNING post_id", (post_id, telegram_id))
        liked = not bool(cursor.fetchone())
        if liked:
            cursor.execute("INSERT INTO community_likes (post_id, telegram_id) VALUES (%s, %s) ON CONFLICT DO NOTHING", (post_id, telegram_id))
            cursor.execute("""INSERT INTO community_notifications (telegram_id, actor_id, kind, post_id, body)
                SELECT telegram_id, %s, 'like', id, 'поставил(а) отметку «Нравится»'
                FROM community_posts WHERE id = %s AND telegram_id <> %s""", (telegram_id, post_id, telegram_id))
        conn.commit()
        return {"ok": True, "liked": liked}
    finally:
        cursor.close()
        conn.close()


@app.get("/api/public/community/posts/{post_id}/comments")
async def public_community_comments(post_id: int, telegram_id: int = 0):
    if not DATABASE_URL:
        return {"ok": True, "items": []}
    ensure_community_tables()
    conn = db_connect(DATABASE_URL)
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT c.id, c.telegram_id, c.body, c.created_at,
                   COALESCE(up.display_name, u.first_name, 'SYLVEX User'), COALESCE(up.custom_avatar_url, ''),
                   c.parent_comment_id, c.edited_at, COUNT(DISTINCT cl.telegram_id),
                   BOOL_OR(cl.telegram_id = %s),
                   COALESCE(parent_up.display_name, parent_u.first_name, '')
            FROM community_comments c
            LEFT JOIN users u ON u.telegram_id = c.telegram_id
            LEFT JOIN user_profiles up ON up.telegram_id = c.telegram_id
            LEFT JOIN community_comment_likes cl ON cl.comment_id = c.id
            LEFT JOIN community_comments parent ON parent.id = c.parent_comment_id
            LEFT JOIN users parent_u ON parent_u.telegram_id = parent.telegram_id
            LEFT JOIN user_profiles parent_up ON parent_up.telegram_id = parent.telegram_id
            WHERE c.post_id = %s
            GROUP BY c.id, up.display_name, up.custom_avatar_url, u.first_name,
                     parent_up.display_name, parent_u.first_name
            ORDER BY c.created_at ASC LIMIT 100
        """, (telegram_id, post_id))
        return {"ok": True, "items": [{"id": r[0], "author_id": r[1], "body": r[2], "created_at": _to_iso(r[3]), "author_name": r[4], "author_avatar": r[5], "parent_comment_id": r[6], "edited_at": _to_iso(r[7]), "likes": int(r[8] or 0), "liked": bool(r[9]), "reply_to_name": r[10] or "", "is_own": bool(telegram_id and int(r[1]) == telegram_id)} for r in cursor.fetchall()]}
    finally:
        cursor.close()
        conn.close()


@app.post("/api/public/community/posts/{post_id}/comments")
async def public_community_comment(post_id: int, request: Request):
    payload = await request.json()
    telegram_id = int(payload.get("telegram_id") or 0)
    body = str(payload.get("body") or "").strip()[:500]
    parent_comment_id = int(payload.get("parent_comment_id") or 0) or None
    init_data = payload.get("initData") or ""
    if not telegram_id or not body:
        return JSONResponse({"ok": False, "error": "invalid_comment"}, status_code=400)
    if init_data and BOT_TOKEN:
        signed_telegram_id = _telegram_id_from_init_data(init_data)
        if not signed_telegram_id or signed_telegram_id != telegram_id:
            return JSONResponse({"ok": False, "error": "invalid_init_data"}, status_code=401)
    ensure_community_tables()
    conn = db_connect(DATABASE_URL)
    cursor = conn.cursor()
    try:
        if parent_comment_id:
            cursor.execute("SELECT 1 FROM community_comments WHERE id = %s AND post_id = %s", (parent_comment_id, post_id))
            if not cursor.fetchone():
                return JSONResponse({"ok": False, "error": "parent_comment_not_found"}, status_code=404)
        cursor.execute("INSERT INTO community_comments (post_id, telegram_id, body, parent_comment_id) VALUES (%s, %s, %s, %s) RETURNING id", (post_id, telegram_id, body, parent_comment_id))
        comment_id = cursor.fetchone()[0]
        cursor.execute("""INSERT INTO community_notifications (telegram_id, actor_id, kind, post_id, comment_id, body)
            SELECT telegram_id, %s, 'comment', id, %s, %s FROM community_posts
            WHERE id = %s AND telegram_id <> %s""", (telegram_id, comment_id, body[:160], post_id, telegram_id))
        conn.commit()
        return {"ok": True, "comment_id": comment_id}
    finally:
        cursor.close()
        conn.close()


@app.patch("/api/public/community/comments/{comment_id}")
async def public_community_edit_comment(comment_id: int, request: Request):
    payload = await request.json()
    telegram_id = int(payload.get("telegram_id") or 0)
    body = str(payload.get("body") or "").strip()[:500]
    init_data = payload.get("initData") or ""
    if not telegram_id or not body:
        return JSONResponse({"ok": False, "error": "invalid_comment"}, status_code=400)
    if init_data and BOT_TOKEN:
        signed_telegram_id = _telegram_id_from_init_data(init_data)
        if not signed_telegram_id or signed_telegram_id != telegram_id:
            return JSONResponse({"ok": False, "error": "invalid_init_data"}, status_code=401)
    ensure_community_tables()
    conn = db_connect(DATABASE_URL)
    cursor = conn.cursor()
    try:
        cursor.execute("UPDATE community_comments SET body = %s, edited_at = NOW() WHERE id = %s AND telegram_id = %s RETURNING id", (body, comment_id, telegram_id))
        if not cursor.fetchone():
            return JSONResponse({"ok": False, "error": "comment_not_found_or_forbidden"}, status_code=403)
        conn.commit()
        return {"ok": True}
    finally:
        cursor.close()
        conn.close()


@app.delete("/api/public/community/comments/{comment_id}")
async def public_community_delete_comment(comment_id: int, request: Request):
    payload = await request.json()
    telegram_id = int(payload.get("telegram_id") or 0)
    init_data = payload.get("initData") or ""
    if not telegram_id:
        return JSONResponse({"ok": False, "error": "telegram_id_required"}, status_code=400)
    if init_data and BOT_TOKEN:
        signed_telegram_id = _telegram_id_from_init_data(init_data)
        if not signed_telegram_id or signed_telegram_id != telegram_id:
            return JSONResponse({"ok": False, "error": "invalid_init_data"}, status_code=401)
    ensure_community_tables()
    conn = db_connect(DATABASE_URL)
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM community_comments WHERE id = %s AND telegram_id = %s RETURNING post_id", (comment_id, telegram_id))
        if not cursor.fetchone():
            return JSONResponse({"ok": False, "error": "comment_not_found_or_forbidden"}, status_code=403)
        conn.commit()
        return {"ok": True}
    finally:
        cursor.close()
        conn.close()


@app.post("/api/public/community/comments/{comment_id}/like")
async def public_community_comment_like(comment_id: int, request: Request):
    payload = await request.json()
    telegram_id = int(payload.get("telegram_id") or 0)
    init_data = payload.get("initData") or ""
    if not telegram_id:
        return JSONResponse({"ok": False, "error": "telegram_id_required"}, status_code=400)
    if init_data and BOT_TOKEN:
        signed_telegram_id = _telegram_id_from_init_data(init_data)
        if not signed_telegram_id or signed_telegram_id != telegram_id:
            return JSONResponse({"ok": False, "error": "invalid_init_data"}, status_code=401)
    ensure_community_tables()
    conn = db_connect(DATABASE_URL)
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM community_comment_likes WHERE comment_id = %s AND telegram_id = %s RETURNING comment_id", (comment_id, telegram_id))
        liked = not bool(cursor.fetchone())
        if liked:
            cursor.execute("INSERT INTO community_comment_likes (comment_id, telegram_id) SELECT id, %s FROM community_comments WHERE id = %s ON CONFLICT DO NOTHING", (telegram_id, comment_id))
        conn.commit()
        return {"ok": True, "liked": liked}
    finally:
        cursor.close()
        conn.close()


@app.get("/api/public/community/hub")
async def public_community_hub(telegram_id: int = 0):
    if not telegram_id or not DATABASE_URL:
        return {"ok": True, "friends": [], "requests": [], "conversations": []}
    ensure_community_tables()
    conn = db_connect(DATABASE_URL)
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT CASE WHEN f.requester_id=%s THEN f.addressee_id ELSE f.requester_id END AS person_id,
                   f.status, f.requester_id,
                   COALESCE(up.display_name,u.first_name,'SYLVEX User'), COALESCE(up.custom_avatar_url,''), COALESCE(u.username,'')
            FROM community_friendships f
            LEFT JOIN users u ON u.telegram_id=CASE WHEN f.requester_id=%s THEN f.addressee_id ELSE f.requester_id END
            LEFT JOIN user_profiles up ON up.telegram_id=CASE WHEN f.requester_id=%s THEN f.addressee_id ELSE f.requester_id END
            WHERE f.requester_id=%s OR f.addressee_id=%s ORDER BY f.updated_at DESC
        """, (telegram_id, telegram_id, telegram_id, telegram_id, telegram_id))
        relations = [{"id":r[0],"status":r[1],"incoming":r[1]=='pending' and int(r[2])!=telegram_id,"name":r[3],"avatar":r[4],"username":r[5]} for r in cursor.fetchall()]
        cursor.execute("""
            SELECT m.person_id, m.created_at, m.body,
                   COALESCE(up.display_name,u.first_name,'SYLVEX User'), COALESCE(up.custom_avatar_url,'')
            FROM (
                SELECT DISTINCT ON (person_id) person_id, created_at, body
                FROM (
                    SELECT CASE WHEN sender_id=%s THEN recipient_id ELSE sender_id END AS person_id, created_at, body
                    FROM community_messages WHERE sender_id=%s OR recipient_id=%s
                ) pairs
                ORDER BY person_id, created_at DESC
            ) m
            LEFT JOIN users u ON u.telegram_id=m.person_id
            LEFT JOIN user_profiles up ON up.telegram_id=m.person_id
            ORDER BY m.created_at DESC LIMIT 50
        """, (telegram_id, telegram_id, telegram_id))
        conversations = [{"id":r[0],"created_at":_to_iso(r[1]),"last_message":r[2] or '',"name":('Общий чат' if int(r[0])==0 else r[3]),"avatar":r[4] or ''} for r in cursor.fetchall()]
        return {"ok":True,"friends":[r for r in relations if r['status']=='accepted'],"requests":[r for r in relations if r['status']=='pending'],"conversations":conversations}
    finally:
        cursor.close(); conn.close()


@app.post("/api/public/community/friends/request")
async def public_community_friend_request(request: Request):
    payload = await request.json(); telegram_id=int(payload.get('telegram_id') or 0); target_id=int(payload.get('target_id') or 0)
    if not telegram_id or not target_id or telegram_id==target_id:
        return JSONResponse({"ok":False,"error":"invalid_request"},status_code=400)
    ensure_community_tables(); conn=db_connect(DATABASE_URL); cursor=conn.cursor()
    try:
        cursor.execute("""INSERT INTO community_friendships (requester_id,addressee_id,status) VALUES (%s,%s,'pending')
            ON CONFLICT (requester_id,addressee_id) DO UPDATE SET status='pending',updated_at=NOW()""",(telegram_id,target_id))
        cursor.execute("INSERT INTO community_notifications (telegram_id,actor_id,kind,body) VALUES (%s,%s,'friend_request','отправил(а) запрос в друзья')",(target_id,telegram_id))
        conn.commit(); return {"ok":True}
    finally: cursor.close(); conn.close()


@app.patch("/api/public/community/friends/{other_id}")
async def public_community_friend_action(other_id: int, request: Request):
    payload=await request.json(); telegram_id=int(payload.get('telegram_id') or 0); action=str(payload.get('action') or '')
    if not telegram_id or action not in {'accept','decline','remove'}:
        return JSONResponse({"ok":False,"error":"invalid_request"},status_code=400)
    ensure_community_tables(); conn=db_connect(DATABASE_URL); cursor=conn.cursor()
    try:
        if action=='accept':
            cursor.execute("UPDATE community_friendships SET status='accepted',updated_at=NOW() WHERE requester_id=%s AND addressee_id=%s RETURNING requester_id",(other_id,telegram_id))
        else:
            cursor.execute("DELETE FROM community_friendships WHERE (requester_id=%s AND addressee_id=%s) OR (requester_id=%s AND addressee_id=%s) RETURNING requester_id",(telegram_id,other_id,other_id,telegram_id))
        if not cursor.fetchone(): return JSONResponse({"ok":False,"error":"relation_not_found"},status_code=404)
        if action=='accept': cursor.execute("INSERT INTO community_notifications (telegram_id,actor_id,kind,body) VALUES (%s,%s,'friend_accept','принял(а) запрос в друзья')",(other_id,telegram_id))
        conn.commit(); return {"ok":True}
    finally: cursor.close(); conn.close()


@app.get("/api/public/community/messages/{other_id}")
async def public_community_messages(other_id: int, telegram_id: int = 0, limit: int = 100):
    if not telegram_id: return {"ok":True,"items":[]}
    ensure_community_tables(); conn=db_connect(DATABASE_URL); cursor=conn.cursor()
    try:
        if other_id==0:
            cursor.execute("""SELECT m.id,m.sender_id,m.recipient_id,m.body,m.created_at,COALESCE(up.display_name,u.first_name,'SYLVEX User'),COALESCE(up.custom_avatar_url,'')
                FROM community_messages m LEFT JOIN users u ON u.telegram_id=m.sender_id LEFT JOIN user_profiles up ON up.telegram_id=m.sender_id
                WHERE m.recipient_id=0 ORDER BY m.created_at DESC LIMIT %s""",(max(1,min(limit,100)),))
        else:
            cursor.execute("""SELECT m.id,m.sender_id,m.recipient_id,m.body,m.created_at,COALESCE(up.display_name,u.first_name,'SYLVEX User'),COALESCE(up.custom_avatar_url,'')
                FROM community_messages m LEFT JOIN users u ON u.telegram_id=m.sender_id LEFT JOIN user_profiles up ON up.telegram_id=m.sender_id
                WHERE (m.sender_id=%s AND m.recipient_id=%s) OR (m.sender_id=%s AND m.recipient_id=%s) ORDER BY m.created_at DESC LIMIT %s""",(telegram_id,other_id,other_id,telegram_id,max(1,min(limit,100))))
            rows=cursor.fetchall()
            cursor.execute("UPDATE community_messages SET read_at=NOW() WHERE sender_id=%s AND recipient_id=%s AND read_at IS NULL",(other_id,telegram_id))
        if other_id==0: rows=cursor.fetchall()
        conn.commit(); rows.reverse()
        return {"ok":True,"items":[{"id":r[0],"sender_id":r[1],"recipient_id":r[2],"body":r[3],"created_at":_to_iso(r[4]),"author_name":r[5],"author_avatar":r[6],"is_own":int(r[1])==telegram_id} for r in rows]}
    finally: cursor.close(); conn.close()


@app.post("/api/public/community/messages")
async def public_community_send_message(request: Request):
    payload=await request.json(); telegram_id=int(payload.get('telegram_id') or 0); recipient_id=int(payload.get('recipient_id') or 0); body=str(payload.get('body') or '').strip()[:2000]
    if not telegram_id or not body: return JSONResponse({"ok":False,"error":"invalid_message"},status_code=400)
    ensure_community_tables(); conn=db_connect(DATABASE_URL); cursor=conn.cursor()
    try:
        cursor.execute("INSERT INTO community_messages (sender_id,recipient_id,body) VALUES (%s,%s,%s) RETURNING id",(telegram_id,recipient_id,body)); message_id=cursor.fetchone()[0]
        if recipient_id: cursor.execute("INSERT INTO community_notifications (telegram_id,actor_id,kind,body) VALUES (%s,%s,'message',%s)",(recipient_id,telegram_id,body[:160]))
        conn.commit(); return {"ok":True,"message_id":message_id}
    finally: cursor.close(); conn.close()


@app.get("/api/public/community/notifications")
async def public_community_notifications(telegram_id: int = 0, limit: int = 80):
    if not telegram_id: return {"ok":True,"items":[],"unread":0}
    ensure_community_tables(); conn=db_connect(DATABASE_URL); cursor=conn.cursor()
    try:
        cursor.execute("""SELECT n.id,n.kind,n.post_id,n.comment_id,n.body,n.read_at,n.created_at,n.actor_id,
                   COALESCE(up.display_name,u.first_name,'SYLVEX User'),COALESCE(up.custom_avatar_url,'')
            FROM community_notifications n LEFT JOIN users u ON u.telegram_id=n.actor_id LEFT JOIN user_profiles up ON up.telegram_id=n.actor_id
            WHERE n.telegram_id=%s ORDER BY n.created_at DESC LIMIT %s""",(telegram_id,max(1,min(limit,100))))
        items=[{"id":r[0],"kind":r[1],"post_id":r[2],"comment_id":r[3],"body":r[4] or '',"read":bool(r[5]),"created_at":_to_iso(r[6]),"actor_id":r[7],"actor_name":r[8],"actor_avatar":r[9]} for r in cursor.fetchall()]
        return {"ok":True,"items":items,"unread":sum(1 for item in items if not item['read'])}
    finally: cursor.close(); conn.close()


@app.post("/api/public/community/notifications/read")
async def public_community_notifications_read(request: Request):
    payload=await request.json(); telegram_id=int(payload.get('telegram_id') or 0)
    if not telegram_id: return JSONResponse({"ok":False,"error":"telegram_id_required"},status_code=400)
    ensure_community_tables(); conn=db_connect(DATABASE_URL); cursor=conn.cursor()
    try: cursor.execute("UPDATE community_notifications SET read_at=NOW() WHERE telegram_id=%s AND read_at IS NULL",(telegram_id,)); conn.commit(); return {"ok":True}
    finally: cursor.close(); conn.close()

# =====================================================
# API ENDPOINT: public_prostudio_sync
# Принимает HTTP-запрос от Mini App или Telegram Bot.
# Маршрут FastAPI: @app.get("/api/public/prostudio/sync")
# Проверяет входные данные, работает с базой/провайдерами и возвращает JSON-ответ фронтенду.
# =====================================================
@app.get("/api/public/prostudio/sync")
# =====================================================
# PYTHON-БЛОК: public_prostudio_sync
# Выполняет отдельный шаг backend-логики SYLVEX.
# Связан с API, базой данных, провайдерами или подготовкой данных для Mini App.
# =====================================================
async def public_prostudio_sync(telegram_id: int = 0, limit: int = 80):
    if not telegram_id:
        return JSONResponse({"ok": False, "error": "telegram_id_required"}, status_code=400)

    resources = load_prostudio_resources(telegram_id)
    drafts = load_prostudio_drafts(telegram_id)
    conversations = []
    jobs = []

    if DATABASE_URL:
        try:
            ensure_prostudio_table()
            conn = db_connect(DATABASE_URL)
            cursor = conn.cursor()
            safe_limit = max(1, min(int(limit or 80), 200))
            cursor.execute("""
                SELECT
                    conversation_id,
                    COALESCE(NULLIF(MAX(prompt), ''), 'Chat') AS title,
                    MAX(created_at) AS updated_at,
                    COALESCE(NULLIF(MAX(mode), ''), 'image') AS type,
                    MIN(created_at) AS created_at
                FROM prostudio_messages
                WHERE telegram_id = %s
                GROUP BY conversation_id
                ORDER BY updated_at DESC
                LIMIT %s
            """, (telegram_id, safe_limit))
            for row in cursor.fetchall():
                conversations.append({
                    "id": row[0],
                    "title": (row[1] or "Chat")[:64],
                    "updated_at": _to_iso(row[2]),
                    "type": row[3] or "image",
                    "created_at": _to_iso(row[4]),
                })

            cursor.execute("""
                SELECT id, conversation_id, mode, model, provider, prompt, status, cost, result_json, error_json, created_at, updated_at, completed_at
                FROM prostudio_generation_jobs
                WHERE telegram_id = %s
                ORDER BY updated_at DESC
                LIMIT %s
            """, (telegram_id, safe_limit))
            for row in cursor.fetchall():
                jobs.append({
                    "id": row[0],
                    "conversation_id": row[1],
                    "mode": row[2],
                    "model": row[3],
                    "provider": row[4],
                    "prompt": row[5],
                    "status": row[6],
                    "cost": row[7] or 0,
                    "result": _json_obj(row[8]),
                    "error": _json_obj(row[9]),
                    "created_at": _to_iso(row[10]),
                    "updated_at": _to_iso(row[11]),
                    "completed_at": _to_iso(row[12]),
                })
            cursor.close()
            conn.close()
        except Exception as exc:
            print("PROSTUDIO SYNC FAILED:", exc)

    return {
        "ok": True,
        "telegram_id": telegram_id,
        "conversations": conversations,
        "drafts": drafts,
        "resources": resources,
        "generation_jobs": jobs,
    }

# =====================================================
# API ENDPOINT: public_prostudio_get_draft
# Принимает HTTP-запрос от Mini App или Telegram Bot.
# Маршрут FastAPI: @app.get("/api/public/prostudio/draft")
# Проверяет входные данные, работает с базой/провайдерами и возвращает JSON-ответ фронтенду.
# =====================================================
@app.get("/api/public/prostudio/draft")
# =====================================================
# PYTHON-БЛОК: public_prostudio_get_draft
# Выполняет отдельный шаг backend-логики SYLVEX.
# Связан с API, базой данных, провайдерами или подготовкой данных для Mini App.
# =====================================================
async def public_prostudio_get_draft(telegram_id: int = 0, mode: str = ""):
    if not telegram_id:
        return JSONResponse({"ok": False, "error": "telegram_id_required"}, status_code=400)
    drafts = load_prostudio_drafts(telegram_id)
    normalized = (mode or "").strip().lower()
    if normalized:
        return {"ok": True, "draft": drafts.get(normalized) or {}}
    return {"ok": True, "drafts": drafts}

# =====================================================
# API ENDPOINT: public_prostudio_save_draft
# Принимает HTTP-запрос от Mini App или Telegram Bot.
# Маршрут FastAPI: @app.post("/api/public/prostudio/draft")
# Проверяет входные данные, работает с базой/провайдерами и возвращает JSON-ответ фронтенду.
# =====================================================
@app.post("/api/public/prostudio/draft")
# =====================================================
# СОХРАНЕНИЕ В БАЗУ ДАННЫХ: public_prostudio_save_draft
# Записывает состояние пользователя, job, metadata или результат генерации в общую базу Mini App и Telegram Bot.
# =====================================================
async def public_prostudio_save_draft(request: Request):
    data = await request.json()
    telegram_id = int(data.get("telegram_id") or 0)
    if not telegram_id:
        return JSONResponse({"ok": False, "error": "telegram_id_required"}, status_code=400)
    draft = save_prostudio_draft(
        telegram_id=telegram_id,
        mode=data.get("mode") or data.get("category") or "image",
        draft_text=data.get("draft_text") or data.get("text") or "",
        conversation_id=data.get("conversation_id") or "",
        attachment=data.get("attachment") or {},
    )
    log_user_event(telegram_id, "miniapp", "draft", "draft_saved", {
        "mode": draft.get("mode"),
        "has_text": bool(draft.get("draft_text")),
    })
    return {"ok": True, "draft": draft}

# =====================================================
# API ENDPOINT: public_prostudio_get_resources
# Принимает HTTP-запрос от Mini App или Telegram Bot.
# Маршрут FastAPI: @app.get("/api/public/prostudio/resources")
# Проверяет входные данные, работает с базой/провайдерами и возвращает JSON-ответ фронтенду.
# =====================================================
@app.get("/api/public/prostudio/resources")
# =====================================================
# PYTHON-БЛОК: public_prostudio_get_resources
# Выполняет отдельный шаг backend-логики SYLVEX.
# Связан с API, базой данных, провайдерами или подготовкой данных для Mini App.
# =====================================================
async def public_prostudio_get_resources(telegram_id: int = 0):
    if not telegram_id:
        return JSONResponse({"ok": False, "error": "telegram_id_required"}, status_code=400)
    return {"ok": True, "resources": load_prostudio_resources(telegram_id)}

# =====================================================
# API ENDPOINT: public_prostudio_save_resource
# Принимает HTTP-запрос от Mini App или Telegram Bot.
# Маршрут FastAPI: @app.post("/api/public/prostudio/resources")
# Проверяет входные данные, работает с базой/провайдерами и возвращает JSON-ответ фронтенду.
# =====================================================
@app.post("/api/public/prostudio/resources")
# =====================================================
# СОХРАНЕНИЕ В БАЗУ ДАННЫХ: public_prostudio_save_resource
# Записывает состояние пользователя, job, metadata или результат генерации в общую базу Mini App и Telegram Bot.
# =====================================================
async def public_prostudio_save_resource(request: Request):
    data = await request.json()
    telegram_id = int(data.get("telegram_id") or 0)
    if not telegram_id:
        return JSONResponse({"ok": False, "error": "telegram_id_required"}, status_code=400)
    item = save_prostudio_resource(telegram_id, data)
    if not item:
        return JSONResponse({"ok": False, "error": "invalid_resource"}, status_code=400)
    return {"ok": True, "resource": item}


@app.post("/api/public/prostudio/runway-avatar")
async def public_prostudio_runway_avatar(request: Request):
    data = await request.json()
    telegram_id = int(data.get("telegram_id") or 0)
    name = str(data.get("name") or "").strip()
    photos = _json_list(data.get("photos")) or _json_list(data.get("referenceImages"))
    if not telegram_id:
        return JSONResponse({"ok": False, "error": "telegram_id_required"}, status_code=400)
    if len(name) < 2:
        return JSONResponse({"ok": False, "error": "name_required"}, status_code=400)
    if not photos:
        return JSONResponse({"ok": False, "error": "reference_image_required"}, status_code=400)

    api_key = env_value("RUNWAY_API_KEY", "RUNWAYML_API_SECRET", "RUNWAYML_API_KEY")
    if not api_key:
        return JSONResponse({"ok": False, "error": "RUNWAY_API_KEY is not configured"}, status_code=500)

    preview_image = public_media_url(photos[0])
    reference_image = preview_image
    if not preview_image.startswith("https://"):
        return JSONResponse({"ok": False, "error": "Runway requires a public HTTPS reference image"}, status_code=400)

    gender = str(data.get("gender") or "").strip()
    description = str(data.get("description") or "").strip()
    personality = (
        f"You are the persistent SYLVEX character named {name}. "
        "Keep the visual identity from the reference image consistent across sessions and generated media. "
        "Respond naturally, briefly, and stay in character when used as an avatar."
    )
    if gender:
        personality += f" Gender/style note: {gender}."
    if description:
        personality += f" Character description: {description[:1200]}."

    endpoint = f"{RUNWAY_API_BASE_URL}/v1/avatars"
    try:
        from runwayml import RunwayML

        client = RunwayML(
            api_key=api_key,
            runway_version=RUNWAY_API_VERSION,
            base_url=RUNWAY_API_BASE_URL,
            timeout=120,
        )
        file_tuple = image_file_tuple_from_url(photos[0], fallback_name=f"{name or 'character'}.png")
        if file_tuple:
            upload = client.uploads.create_ephemeral(file=file_tuple, timeout=240)
            upload_payload = provider_object_to_dict(upload)
            reference_image = upload_payload.get("uri") or getattr(upload, "uri", "") or reference_image
        prostudio_debug(
            "RUNWAY_AVATAR_CREATE_START",
            telegram_id=telegram_id,
            reference_image=reference_image,
            preview_image=preview_image,
            name=name,
            voice_type="runway-live-preset",
            preset_id="clara",
            uploaded_to_runway=reference_image.startswith("runway://"),
        )
        avatar = client.avatars.create(
            name=name,
            reference_image=reference_image,
            voice={"type": "runway-live-preset", "preset_id": "clara"},
            personality=personality[:10000],
            image_processing="optimize",
        )
        payload = provider_object_to_dict(avatar)
    except Exception as exc:
        prostudio_error("RUNWAY_AVATAR_CREATE_FAILED", exc, telegram_id=telegram_id, endpoint=endpoint, reference_image=reference_image, preview_image=preview_image)
        return JSONResponse({
            "ok": False,
            "error": "Runway avatar creation failed",
            "details": str(exc)[:1200],
            "endpoint": endpoint,
        }, status_code=502)

    avatar_id = str(payload.get("id") or payload.get("avatarId") or payload.get("avatar_id") or "")
    if not avatar_id:
        return JSONResponse({"ok": False, "error": "Runway returned no avatar id", "response": payload}, status_code=502)

    resource = {
        "id": f"custom_character_{avatar_id}",
        "resource_type": "character",
        "name": name,
        "gender": gender,
        "description": description,
        "previewUrl": preview_image,
        "referenceImages": [preview_image],
        "sourceImages": photos,
        "avatar_id": avatar_id,
        "provider": "runway",
        "model": "gwm1_avatars",
        "ai_provider": "runway",
        "ai_model": "gwm1_avatars",
        "type": "custom",
        "status": "ready",
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    return {"ok": True, "resource": resource, "avatar": payload}


def _character_identity_prompt(name: str, gender: str, description: str) -> str:
    return ""


async def _generate_openai_character_images(name: str, gender: str, description: str, photos: list) -> list:
    shots = [
        "Create the primary square avatar: centered head-and-shoulders studio portrait, neutral expression, clean neutral background.",
        "Create reference 1: front-facing full-body neutral standing pose, complete default outfit visible, clean studio background.",
        "Create reference 2: three-quarter full-body view of the exact same person and exact same outfit, clean studio background.",
        "Create reference 3: side-profile and upper-body identity reference of the exact same person and exact same outfit, clean studio background.",
    ]
    results = []
    for shot in shots:
        payload = {
            "mode": "image",
            "category": "image",
            "provider": "openai",
            "model": "gpt_image_2",
            "prompt": (
                f"{shot}\n\nUse the uploaded photos as the only source for the person. "
                "No text, watermark, extra people, or collage."
            ),
            "image_options": {
                "modelId": "gpt_image_2",
                "size": "1024x1024",
                "quality": "high",
                "count": 1,
                "referenceImageUrls": photos[:3],
            },
        }
        result = await image_generation(payload)
        if not result.get("ok"):
            diagnostic = (
                result.get("raw_error")
                or result.get("details")
                or result.get("body_preview")
                or result.get("error")
                or "OpenAI character image generation failed"
            )
            raise RuntimeError(
                f"OpenAI character image generation failed"
                f" (status={result.get('status_code') or 'unknown'}, model={result.get('provider_model') or 'gpt-image-2'}): "
                f"{str(diagnostic)[:1200]}"
            )
        urls = materialize_image_urls(_json_list(result.get("images")) or [result.get("image_url")])
        if not urls:
            raise RuntimeError("OpenAI returned no character image")
        results.append(urls[0])
    return results


def _find_provider_id(data, keys: tuple[str, ...]) -> str:
    if isinstance(data, dict):
        for key in keys:
            if data.get(key):
                return str(data[key])
        for value in data.values():
            found = _find_provider_id(value, keys)
            if found:
                return found
    elif isinstance(data, list):
        for value in data:
            found = _find_provider_id(value, keys)
            if found:
                return found
    return ""


def _create_heygen_character(name: str, avatar_url: str, references: list) -> dict:
    api_key = env_value("HEYGEN_API_KEY")
    if not api_key:
        raise RuntimeError("HEYGEN_API_KEY is not configured")
    endpoint = env_value(
        "HEYGEN_PHOTO_AVATAR_CREATE_ENDPOINT",
        default="https://api.heygen.com/v2/photo_avatar/photo_avatar_group",
    )
    def upload_image(value: str, index: int) -> str:
        file_tuple = image_file_tuple_from_url(value, fallback_name=f"{name}-{index + 1}.png")
        if not file_tuple:
            raise RuntimeError(f"Could not read generated character image {index + 1}")
        filename, content, mime_type = file_tuple
        upload_response = requests.post(
            env_value("HEYGEN_ASSET_UPLOAD_ENDPOINT", default="https://upload.heygen.com/v1/asset"),
            headers={
                "X-Api-Key": api_key,
                "Content-Type": mime_type or "image/png",
            },
            data=content,
            timeout=180,
        )
        upload_data = safe_provider_json(
            upload_response,
            "heygen",
            env_value("HEYGEN_ASSET_UPLOAD_ENDPOINT", default="https://upload.heygen.com/v1/asset"),
        )
        if upload_response.status_code >= 400:
            detail = upload_data.get("message") or upload_data.get("error") or upload_response.text[:500]
            raise RuntimeError(f"HeyGen asset upload failed: {detail}")
        uploaded_url = _find_provider_id(
            upload_data,
            ("url", "asset_url", "assetUrl", "image_url", "imageUrl"),
        )
        if not uploaded_url:
            raise RuntimeError(f"HeyGen asset upload returned no URL for {filename}")
        return uploaded_url

    uploaded_images = [
        upload_image(value, index)
        for index, value in enumerate([avatar_url] + references[:3])
    ]
    body = {
        "name": name,
        "image_url": uploaded_images[0],
        "image_urls": uploaded_images,
    }
    response = requests.post(endpoint, headers=heygen_headers(), json=body, timeout=180)
    data = safe_provider_json(response, "heygen", endpoint)
    if response.status_code >= 400:
        detail = data.get("message") or data.get("error") or response.text[:500]
        raise RuntimeError(f"HeyGen character creation failed: {detail}")
    photo_avatar_id = _find_provider_id(
        data, ("photo_avatar_id", "photoAvatarId", "avatar_id", "avatarId", "id")
    )
    group_id = _find_provider_id(data, ("avatar_group_id", "avatarGroupId", "group_id", "groupId"))
    if not photo_avatar_id and not group_id:
        raise RuntimeError("HeyGen returned no character id")
    return {
        "response": data,
        "photo_avatar_id": photo_avatar_id,
        "avatar_group_id": group_id,
    }


@app.post("/api/public/prostudio/character")
async def public_prostudio_create_character(request: Request):
    data = await request.json()
    telegram_id = int(data.get("telegram_id") or 0)
    name = str(data.get("name") or "").strip()
    gender = str(data.get("gender") or "").strip()
    description = str(data.get("description") or "").strip()
    photos = (_json_list(data.get("photos")) or _json_list(data.get("referenceImages")))[:3]
    if not telegram_id:
        return JSONResponse({"ok": False, "error": "telegram_id_required"}, status_code=400)
    if len(name) < 2:
        return JSONResponse({"ok": False, "error": "name_required"}, status_code=400)
    if not photos:
        return JSONResponse({"ok": False, "error": "reference_image_required"}, status_code=400)
    try:
        images = await _generate_openai_character_images(name, gender, description, photos)
        heygen = await asyncio.to_thread(_create_heygen_character, name, images[0], images[1:4])
        identity_prompt = _character_identity_prompt(name, gender, description)
        stable_id = heygen["photo_avatar_id"] or heygen["avatar_group_id"]
        resource = {
            "id": f"custom_character_{stable_id}",
            "resource_type": "character",
            "name": name,
            "gender": gender,
            "description": description,
            "prompt": "",
            "previewUrl": images[0],
            "avatarUrl": images[0],
            "referenceImages": images[1:4],
            "sourceImages": images[1:4],
            "originalSourceImages": photos,
            "avatar_id": heygen["photo_avatar_id"],
            "heygenPhotoAvatarId": heygen["photo_avatar_id"],
            "heygenAvatarGroupId": heygen["avatar_group_id"],
            "provider": "heygen",
            "ai_provider": "openai+heygen",
            "model": "gpt-image-2",
            "ai_model": "gpt-image-2",
            "type": "custom",
            "status": "ready",
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        saved = save_prostudio_resource(telegram_id, resource)
        return {"ok": True, "resource": {**resource, **saved}, "heygen": heygen["response"]}
    except Exception as exc:
        prostudio_error("CHARACTER_CREATE_FAILED", exc, telegram_id=telegram_id, name=name)
        error_text = str(exc)
        if re.search(r"billing hard limit|billing limit|insufficient[_ ]quota", error_text, re.I):
            return JSONResponse({
                "ok": False,
                "error": "Лимит расходов OpenAI исчерпан. Пополните баланс или увеличьте бюджет API-проекта OpenAI.",
                "code": "openai_billing_limit_reached",
                "provider": "openai",
            }, status_code=402)
        return JSONResponse({"ok": False, "error": error_text[:1200]}, status_code=502)


# =====================================================
# API ENDPOINT: public_prostudio_delete_resource
# Удаляет только пользовательский ресурс персонажа/объекта из каталога Mini App.
# =====================================================
@app.delete("/api/public/prostudio/resources/{resource_id}")
async def public_prostudio_delete_resource(resource_id: str, telegram_id: int = 0):
    if not telegram_id:
        return JSONResponse({"ok": False, "error": "telegram_id_required"}, status_code=400)
    if not resource_id or not resource_id.startswith("custom_"):
        return JSONResponse({"ok": False, "error": "only_custom_resources_can_be_deleted"}, status_code=400)
    if not DATABASE_URL:
        return {"ok": True, "deleted": False, "resource_id": resource_id}
    try:
        ensure_prostudio_table()
        conn = db_connect(DATABASE_URL)
        cursor = conn.cursor()
        cursor.execute(
            "DELETE FROM prostudio_resources WHERE id = %s AND telegram_id = %s",
            (resource_id, telegram_id),
        )
        deleted = cursor.rowcount > 0
        conn.commit()
        cursor.close()
        conn.close()
        if deleted:
            log_user_event(telegram_id, "miniapp", "resource", "resource_deleted", {"id": resource_id})
        return {"ok": True, "deleted": deleted, "resource_id": resource_id}
    except Exception as exc:
        prostudio_error("RESOURCE_DELETE_FAILED", exc, resource_id=resource_id, telegram_id=telegram_id)
        return JSONResponse({"ok": False, "error": "resource_delete_failed"}, status_code=500)


# =====================================================
# API ENDPOINT: public_prostudio_upload_media
# Принимает HTTP-запрос от Mini App или Telegram Bot.
# Маршрут FastAPI: @app.post("/api/public/prostudio/upload-media")
# Проверяет входные данные, работает с базой/провайдерами и возвращает JSON-ответ фронтенду.
# =====================================================
@app.post("/api/public/prostudio/upload-media")
# =====================================================
# ЗАГРУЗКА ФАЙЛОВ: public_prostudio_upload_media
# Получает файл или ссылку, приводит её к безопасному формату и передаёт дальше в генерацию или сохранение.
# =====================================================
async def public_prostudio_upload_media(file: UploadFile = File(...), kind: str = "image"):
    media_kind = (kind or "").strip().lower()
    filename = pathlib.Path(file.filename or "").name
    suffix = pathlib.Path(filename).suffix.lower()
    content_type = (file.content_type or "").lower()
    is_video = media_kind == "video" or content_type.startswith("video/")
    is_audio = media_kind == "audio" or content_type.startswith("audio/")
    is_file = media_kind in {"file", "document"} or content_type.startswith(("text/", "application/pdf", "application/json", "application/msword", "application/vnd.openxmlformats-officedocument"))
    if is_video:
        allowed_exts = {".mp4", ".mov", ".m4v", ".webm", ".mpeg", ".mpg", ".avi", ".flv", ".wmv", ".3gp"}
    elif is_audio:
        allowed_exts = {".mp3", ".wav", ".m4a", ".aac", ".ogg", ".oga", ".webm", ".flac", ".aiff", ".aif"}
    elif is_file:
        allowed_exts = {".txt", ".md", ".json", ".csv", ".pdf", ".doc", ".docx"}
    else:
        allowed_exts = {".jpg", ".jpeg", ".png", ".webp"}
    max_bytes = 200 * 1024 * 1024 if is_video else 50 * 1024 * 1024

    if suffix not in allowed_exts:
        return JSONResponse({"ok": False, "error": "Unsupported media format"}, status_code=400)

    content = await file.read()
    if not content:
        return JSONResponse({"ok": False, "error": "Empty file"}, status_code=400)
    if len(content) > max_bytes:
        return JSONResponse({"ok": False, "error": "File is too large"}, status_code=400)

    stored_name = f"{uuid4().hex}{suffix}"
    public_folder = "documents" if is_file else "video-inputs"
    public_path = generated_key(public_folder, stored_name)
    public_url = storage_put_bytes(content, public_path, content_type)
    uploaded_kind = "video" if is_video else ("audio" if is_audio else ("file" if is_file else "image"))
    print("PROSTUDIO MEDIA UPLOAD:", {
        "kind": uploaded_kind,
        "filename": filename,
        "content_type": content_type,
        "bytes": len(content),
        "url": public_url,
    })
    return {
        "ok": True,
        "kind": uploaded_kind,
        "url": public_url,
        "path": public_path,
        "inline_url": (
            f"data:{content_type or 'image/png'};base64,{base64.b64encode(content).decode('ascii')}"
            if uploaded_kind == "image" and len(content) <= 12 * 1024 * 1024
            else ""
        ),
        "content_type": content_type,
        "bytes": len(content),
    }


# =====================================================
# API ENDPOINT: public_prostudio_event
# Принимает HTTP-запрос от Mini App или Telegram Bot.
# Маршрут FastAPI: @app.post("/api/public/prostudio/events")
# Проверяет входные данные, работает с базой/провайдерами и возвращает JSON-ответ фронтенду.
# =====================================================
@app.post("/api/public/prostudio/events")
# =====================================================
# PYTHON-БЛОК: public_prostudio_event
# Выполняет отдельный шаг backend-логики SYLVEX.
# Связан с API, базой данных, провайдерами или подготовкой данных для Mini App.
# =====================================================
async def public_prostudio_event(request: Request):
    data = await request.json()
    telegram_id = int(data.get("telegram_id") or 0)
    if not telegram_id:
        return JSONResponse({"ok": False, "error": "telegram_id_required"}, status_code=400)
    log_user_event(
        telegram_id=telegram_id,
        source=data.get("source") or "miniapp",
        event_type=data.get("event_type") or data.get("type") or "ui",
        event_name=data.get("event_name") or data.get("name") or "",
        payload=data.get("payload") or {},
    )
    return {"ok": True}

# =====================================================
# API ENDPOINT: public_prostudio_generation_jobs
# Принимает HTTP-запрос от Mini App или Telegram Bot.
# Маршрут FastAPI: @app.get("/api/public/prostudio/generation-jobs")
# Проверяет входные данные, работает с базой/провайдерами и возвращает JSON-ответ фронтенду.
# =====================================================
@app.get("/api/public/prostudio/generation-jobs")
# =====================================================
# СОХРАНЕНИЕ В БАЗУ ДАННЫХ: public_prostudio_generation_jobs
# Записывает состояние пользователя, job, metadata или результат генерации в общую базу Mini App и Telegram Bot.
# =====================================================
async def public_prostudio_generation_jobs(telegram_id: int = 0, mode: str = "", limit: int = 50):
    if not telegram_id:
        return JSONResponse({"ok": False, "error": "telegram_id_required"}, status_code=400)
    jobs = []
    if DATABASE_URL:
        try:
            ensure_prostudio_table()
            normalized = (mode or "").strip().lower()
            where_mode = "AND mode = %s" if normalized in {"image", "video", "music", "voice"} else ""
            params = [telegram_id]
            if where_mode:
                params.append(normalized)
            params.append(max(1, min(int(limit or 50), 200)))
            conn = db_connect(DATABASE_URL)
            cursor = conn.cursor()
            cursor.execute(f"""
                SELECT id, conversation_id, mode, model, provider, prompt, status, cost, result_json, error_json, created_at, updated_at, completed_at
                FROM prostudio_generation_jobs
                WHERE telegram_id = %s
                  {where_mode}
                ORDER BY updated_at DESC
                LIMIT %s
            """, tuple(params))
            for row in cursor.fetchall():
                jobs.append({
                    "id": row[0],
                    "conversation_id": row[1],
                    "mode": row[2],
                    "model": row[3],
                    "provider": row[4],
                    "prompt": row[5],
                    "status": row[6],
                    "cost": row[7] or 0,
                    "result": _json_obj(row[8]),
                    "error": _json_obj(row[9]),
                    "created_at": _to_iso(row[10]),
                    "updated_at": _to_iso(row[11]),
                    "completed_at": _to_iso(row[12]),
                })
            cursor.close()
            conn.close()
        except Exception as exc:
            print("PROSTUDIO JOB LIST FAILED:", exc)
    return {"ok": True, "jobs": jobs}


@app.get("/api/public/prostudio/active-job")
async def public_prostudio_active_job(telegram_id: int = 0):
    if not telegram_id:
        return JSONResponse({"ok": False, "error": "telegram_id_required"}, status_code=400)
    try:
        job = get_active_prostudio_job(telegram_id)
    except Exception as exc:
        prostudio_error("ACTIVE_JOB_LOOKUP_FAILED", exc, telegram_id=telegram_id)
        return JSONResponse({"ok": False, "error": "active_job_lookup_failed"}, status_code=500)
    return {
        "ok": True,
        "active": bool(job),
        "active_job_id": job.get("id") or "",
        "status": job.get("status") or "",
        "job": job,
    }


@app.post("/api/admin/prostudio/recover-job/{job_id}")
async def admin_recover_prostudio_job(job_id: str, request: Request):
    data = await request.json()
    telegram_id = int(data.get("telegram_id") or 0)
    init_data = str(data.get("init_data") or "")
    if not PROSTUDIO_ADMIN_ID or telegram_id != PROSTUDIO_ADMIN_ID:
        raise HTTPException(status_code=403, detail="admin_required")
    if BOT_TOKEN and _telegram_id_from_init_data(init_data) != PROSTUDIO_ADMIN_ID:
        raise HTTPException(status_code=403, detail="telegram_auth_failed")
    try:
        recovery = await asyncio.to_thread(
            recover_stale_prostudio_job,
            job_id,
            bool(data.get("force", False)),
        )
    except Exception as exc:
        prostudio_error("PROSTUDIO_ADMIN_STALE_RECOVERY_FAILED", exc, job_id=job_id)
        raise HTTPException(status_code=500, detail="stale_recovery_failed") from exc
    return {"ok": True, **recovery}

# =====================================================
# API ENDPOINT: public_prostudio_job
# Принимает HTTP-запрос от Mini App или Telegram Bot.
# Маршрут FastAPI: @app.get("/api/public/prostudio/job/{job_id}")
# Проверяет входные данные, работает с базой/провайдерами и возвращает JSON-ответ фронтенду.
# =====================================================
@app.get("/api/public/prostudio/job/{job_id}")
# =====================================================
# PYTHON-БЛОК: public_prostudio_job
# Выполняет отдельный шаг backend-логики SYLVEX.
# Связан с API, базой данных, провайдерами или подготовкой данных для Mini App.
# =====================================================
async def public_prostudio_job(job_id: str):
    if not DATABASE_URL:
        return JSONResponse(
            {"ok": False, "error": "database_not_configured"},
            status_code=500,
        )

    try:
        ensure_prostudio_table()

        conn = db_connect(DATABASE_URL)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT
                status,
                result_json,
                error_json,
                conversation_id,
                mode
            FROM prostudio_generation_jobs
            WHERE id = %s
            LIMIT 1
        """, (job_id,))

        row = cursor.fetchone()

        cursor.close()
        conn.close()

        if not row:
            return JSONResponse(
                {"ok": False, "error": "job_not_found"},
                status_code=404,
            )
        result_json = _json_obj(row[1])
        error_json = _json_obj(row[2])
        if isinstance(error_json, dict) and error_json:
            normalized_error = user_generation_error_text(error_json.get("error") or error_json.get("message") or error_json)
            error_json["error"] = normalized_error
            error_json["message"] = normalized_error
        effective_status = row[0]
        job_mode = (row[4] or "").lower()
        if effective_status == "completed" and not generation_has_completed_result(result_json, job_mode):
            effective_status = "provider_processing"
            prostudio_debug("JOB_GET_COMPLETED_WITHOUT_RESULT_HELD", job_id=job_id, mode=job_mode)
        image_url = result_json.get("image_url") if isinstance(result_json, dict) else ""
        thumb_url = result_json.get("thumbnail_url") if isinstance(result_json, dict) else ""
        image_exists = None
        thumb_exists = None
        if isinstance(image_url, str) and image_url.startswith("/webapp/"):
            image_exists = (WEBAPP_DIR / image_url.replace("/webapp/", "", 1)).exists()
        if isinstance(thumb_url, str) and thumb_url.startswith("/webapp/"):
            thumb_exists = (WEBAPP_DIR / thumb_url.replace("/webapp/", "", 1)).exists()
        print("PROSTUDIO JOB GET DEBUG:", {
            "job_id": job_id,
            "status": effective_status,
            "conversation_id": row[3],
            "result_keys": sorted(result_json.keys()) if isinstance(result_json, dict) else [],
            "image_url": _sql_text(image_url, 180),
            "thumbnail_url": _sql_text(thumb_url, 180),
            "image_file_exists": image_exists,
            "thumbnail_file_exists": thumb_exists,
            "images_count": len(_json_list(result_json.get("images"))) if isinstance(result_json, dict) else 0,
            "thumbnails_count": len(_json_list(result_json.get("thumbnails"))) if isinstance(result_json, dict) else 0,
            "metadata_image_url": _sql_text(((result_json.get("metadata") or {}).get("image_url") if isinstance(result_json.get("metadata"), dict) else "") if isinstance(result_json, dict) else "", 180),
            "metadata_thumbnail_url": _sql_text(((result_json.get("metadata") or {}).get("thumbnail_url") if isinstance(result_json.get("metadata"), dict) else "") if isinstance(result_json, dict) else "", 180),
        })

        return {
            "ok": True,
            "generation_id": job_id,
            "job_id": job_id,
            "status": effective_status,
            "mode": job_mode,
            "result": result_json,
            "error": error_json,
            "conversation_id": row[3],
        }

    except Exception as exc:
        prostudio_error("JOB_GET_FAILED", exc, job_id=job_id)
        return JSONResponse(
            {"ok": False, "error": "job_read_failed"},
            status_code=500,
        )


def _telegram_id_from_init_data(init_data: str) -> int:
    """Return the signed Telegram user id, or zero for invalid init data."""
    if not verify_telegram_init_data(init_data):
        return 0
    try:
        parsed = dict(urllib.parse.parse_qsl(init_data, keep_blank_values=True))
        # Regular Mini App launches use `user`; attachment-menu launches may
        # use `receiver`. Both values are covered by Telegram's signature.
        for field in ("user", "receiver"):
            raw = parsed.get(field)
            if not raw:
                continue
            value = json.loads(raw) if isinstance(raw, str) else raw
            if isinstance(value, dict) and value.get("id"):
                return int(value["id"])

        # A signed private-chat id identifies the same Telegram user.
        raw_chat = parsed.get("chat")
        if raw_chat:
            chat = json.loads(raw_chat) if isinstance(raw_chat, str) else raw_chat
            if isinstance(chat, dict) and str(chat.get("type") or "").lower() == "private" and chat.get("id"):
                return int(chat["id"])

        # Telegram-compatible launchers can place a direct id in the signed
        # data-check string. Unsigned frontend values are never accepted.
        for field in ("user_id", "telegram_id"):
            if parsed.get(field):
                return int(parsed[field])

        print("ADMIN TELEGRAM AUTH USER MISSING:", {"signed_fields": sorted(parsed.keys())})
        return 0
    except (TypeError, ValueError, json.JSONDecodeError):
        return 0


# =====================================================
# SYLVEX ADMIN PANEL
# Server-side role checks are mandatory for every action. The UI visibility is
# only a convenience and is never used as an authorization boundary.
# =====================================================
ADMIN_SCHEMA_LOCK = threading.Lock()
ADMIN_SCHEMA_READY = False


def ensure_admin_tables():
    global ADMIN_SCHEMA_READY
    if not DATABASE_URL:
        return
    if ADMIN_SCHEMA_READY:
        return
    with ADMIN_SCHEMA_LOCK:
        if ADMIN_SCHEMA_READY:
            return
        conn = db_connect(DATABASE_URL)
        cursor = conn.cursor()
        try:
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS admin_users (
                telegram_id BIGINT PRIMARY KEY,
                role TEXT NOT NULL DEFAULT 'admin',
                permissions JSONB NOT NULL DEFAULT '[]'::jsonb,
                active BOOLEAN NOT NULL DEFAULT TRUE,
                granted_by BIGINT,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            )
            """)
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS admin_audit_log (
                id BIGSERIAL PRIMARY KEY,
                actor_telegram_id BIGINT NOT NULL,
                action TEXT NOT NULL,
                target_telegram_id BIGINT,
                before_data JSONB NOT NULL DEFAULT '{}'::jsonb,
                after_data JSONB NOT NULL DEFAULT '{}'::jsonb,
                reason TEXT,
                created_at TIMESTAMP DEFAULT NOW()
            )
            """)
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS admin_messages (
                id BIGSERIAL PRIMARY KEY,
                admin_telegram_id BIGINT NOT NULL,
                user_telegram_id BIGINT NOT NULL,
                message TEXT NOT NULL,
                telegram_sent BOOLEAN NOT NULL DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT NOW()
            )
            """)
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS app_presence (
                telegram_id BIGINT PRIMARY KEY,
                current_view TEXT,
                platform TEXT,
                last_seen TIMESTAMP NOT NULL DEFAULT NOW(),
                created_at TIMESTAMP NOT NULL DEFAULT NOW()
            )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_app_presence_last_seen ON app_presence(last_seen DESC)")
            cursor.execute("""
            INSERT INTO admin_users (telegram_id, role, permissions, active, granted_by, updated_at)
            VALUES (%s, 'owner', '["all"]'::jsonb, TRUE, %s, NOW())
            ON CONFLICT (telegram_id) DO UPDATE
            SET role = 'owner', permissions = '["all"]'::jsonb, active = TRUE, updated_at = NOW()
            """, (SUPERADMIN_TELEGRAM_ID, SUPERADMIN_TELEGRAM_ID))
            conn.commit()
            ADMIN_SCHEMA_READY = True
        except Exception:
            conn.rollback()
            raise
        finally:
            cursor.close()
            conn.close()


def _admin_actor(payload: dict, permission: str = "", owner_only: bool = False) -> dict:
    init_data = str((payload or {}).get("initData") or (payload or {}).get("init_data") or "")
    if not init_data:
        raise HTTPException(status_code=403, detail="telegram_init_data_missing")
    if not TELEGRAM_AUTH_TOKENS:
        raise HTTPException(status_code=503, detail="telegram_bot_token_missing")
    if not verify_telegram_init_data(init_data):
        raise HTTPException(status_code=403, detail="telegram_signature_invalid")
    telegram_id = _telegram_id_from_init_data(init_data)
    if not telegram_id:
        raise HTTPException(status_code=403, detail="telegram_user_missing")
    # The project owner is defined by the signed Telegram user id. Do not make
    # first access depend on an admin_users row that may not exist yet.
    if telegram_id == SUPERADMIN_TELEGRAM_ID:
        return {"telegram_id": telegram_id, "role": "owner", "permissions": ["all"]}
    if not DATABASE_URL:
        raise HTTPException(status_code=503, detail="database_unavailable")
    ensure_admin_tables()
    conn = db_connect(DATABASE_URL)
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT role, permissions, active FROM admin_users WHERE telegram_id = %s", (telegram_id,))
        row = cursor.fetchone()
    finally:
        cursor.close()
        conn.close()
    if not row or not row[2]:
        raise HTTPException(status_code=403, detail="admin_access_denied")
    permissions = row[1] or []
    if isinstance(permissions, str):
        try:
            permissions = json.loads(permissions)
        except Exception:
            permissions = []
    actor = {"telegram_id": telegram_id, "role": row[0], "permissions": permissions}
    if owner_only and actor["role"] != "owner":
        raise HTTPException(status_code=403, detail="owner_access_required")
    if permission and actor["role"] != "owner" and "all" not in permissions and permission not in permissions:
        raise HTTPException(status_code=403, detail="admin_permission_denied")
    return actor


def _admin_audit(cursor, actor_id: int, action: str, target_id: int = 0, before=None, after=None, reason: str = ""):
    cursor.execute("""
        INSERT INTO admin_audit_log
            (actor_telegram_id, action, target_telegram_id, before_data, after_data, reason)
        VALUES (%s, %s, NULLIF(%s, 0), %s::jsonb, %s::jsonb, %s)
    """, (actor_id, action, int(target_id or 0), json.dumps(before or {}, default=str),
          json.dumps(after or {}, default=str), str(reason or "")[:500]))


@app.post("/api/admin/me")
async def admin_me(request: Request):
    actor = _admin_actor(await request.json())
    return {"ok": True, "admin": actor}


@app.post("/api/public/presence")
async def public_presence(request: Request):
    payload = await request.json()
    telegram_id = _telegram_id_from_init_data(str(payload.get("initData") or payload.get("init_data") or ""))
    if not telegram_id:
        return JSONResponse({"ok": False, "error": "telegram_auth_required"}, status_code=403)
    ensure_admin_tables()
    current_view = re.sub(r"[^a-z0-9_-]", "", str(payload.get("view") or "home").lower())[:40] or "home"
    platform = re.sub(r"[^a-z0-9_.-]", "", str(payload.get("platform") or "telegram").lower())[:40] or "telegram"
    conn = db_connect(DATABASE_URL)
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO app_presence (telegram_id,current_view,platform,last_seen)
            VALUES (%s,%s,%s,NOW())
            ON CONFLICT (telegram_id) DO UPDATE
            SET current_view=EXCLUDED.current_view,platform=EXCLUDED.platform,last_seen=NOW()
        """, (telegram_id, current_view, platform))
        conn.commit()
        return {"ok": True}
    finally:
        cursor.close()
        conn.close()


@app.post("/api/admin/dashboard")
async def admin_dashboard(request: Request):
    actor = _admin_actor(await request.json(), "view_dashboard")
    ensure_admin_tables()
    conn = db_connect(DATABASE_URL)
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT COUNT(*), COALESCE(SUM(balance),0),
                   COUNT(*) FILTER (WHERE NULLIF(created_at,'')::timestamp >= NOW() - INTERVAL '24 hours')
            FROM users
        """)
        users_count, total_balance, new_users_today = cursor.fetchone()
        cursor.execute("SELECT COUNT(*) FROM subscriptions WHERE status='active' AND NULLIF(expires_at,'')::timestamp > NOW()")
        active_subscriptions = cursor.fetchone()[0]
        cursor.execute("""
            SELECT COUNT(*) FILTER (WHERE created_at >= NOW() - INTERVAL '24 hours'),
                   COUNT(*) FILTER (WHERE status='failed' AND created_at >= NOW() - INTERVAL '24 hours'),
                   COUNT(*),
                   COUNT(*) FILTER (WHERE status IN ('queued','processing','running'))
            FROM prostudio_generation_jobs
        """)
        generations_today, failed_today, generations_total, active_jobs = cursor.fetchone()
        cursor.execute("SELECT COUNT(*) FROM app_presence WHERE last_seen >= NOW() - INTERVAL '5 minutes'")
        online_count = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM admin_users WHERE active = TRUE")
        admins_count = cursor.fetchone()[0]
        cursor.execute("""
            SELECT COALESCE(NULLIF(mode,''),'unknown'), COUNT(*),
                   COUNT(*) FILTER (WHERE created_at >= NOW() - INTERVAL '24 hours')
            FROM prostudio_generation_jobs GROUP BY 1 ORDER BY COUNT(*) DESC
        """)
        tools = [{"type": row[0], "total": int(row[1] or 0), "today": int(row[2] or 0)} for row in cursor.fetchall()]
        return {"ok": True, "stats": {"users": int(users_count or 0), "balance": int(total_balance or 0),
                "subscriptions": int(active_subscriptions or 0), "generations_today": int(generations_today or 0),
                "generations_total": int(generations_total or 0), "failed_today": int(failed_today or 0),
                "active_jobs": int(active_jobs or 0),
                "new_users_today": int(new_users_today or 0), "online": int(online_count or 0),
                "admins": int(admins_count or 0)}, "tools": tools, "admin": actor}
    finally:
        cursor.close()
        conn.close()


@app.post("/api/admin/users/search")
async def admin_users_search(request: Request):
    payload = await request.json()
    _admin_actor(payload, "view_users")
    query = str(payload.get("query") or "").strip()[:100]
    limit = max(1, min(int(payload.get("limit") or 30), 100))
    pattern = f"%{query}%"
    conn = db_connect(DATABASE_URL)
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT u.telegram_id, COALESCE(p.display_name, u.first_name, 'SYLVEX User'),
                   COALESCE(u.username, ''), COALESCE(u.balance, 0), COALESCE(u.subscription, 'free'),
                   u.created_at,
                   (SELECT MAX(NULLIF(s.expires_at,'')::timestamp) FROM subscriptions s
                    WHERE s.telegram_id=u.telegram_id AND s.status='active' AND NULLIF(s.expires_at,'')::timestamp>NOW()),
                   EXISTS(SELECT 1 FROM app_presence ap WHERE ap.telegram_id=u.telegram_id
                          AND ap.last_seen >= NOW() - INTERVAL '5 minutes')
            FROM users u LEFT JOIN user_profiles p ON p.telegram_id=u.telegram_id
            WHERE %s = '' OR u.telegram_id::text ILIKE %s OR COALESCE(u.username,'') ILIKE %s
                  OR COALESCE(p.display_name,u.first_name,'') ILIKE %s
            ORDER BY NULLIF(u.created_at,'')::timestamp DESC NULLS LAST LIMIT %s
        """, (query, pattern, pattern, pattern, limit))
        items = [{"telegram_id": r[0], "name": r[1], "username": r[2], "balance": int(r[3] or 0),
                  "subscription": r[4], "created_at": _to_iso(r[5]), "subscription_until": _to_iso(r[6]),
                  "online": bool(r[7])} for r in cursor.fetchall()]
        return {"ok": True, "items": items}
    finally:
        cursor.close()
        conn.close()


@app.post("/api/admin/users/balance")
async def admin_user_balance(request: Request):
    payload = await request.json()
    actor = _admin_actor(payload, "manage_balance")
    ensure_admin_tables()
    target_id, delta = int(payload.get("user_id") or 0), int(payload.get("delta") or 0)
    reason = str(payload.get("reason") or "Ручная корректировка")[:500]
    if not target_id or not delta or abs(delta) > 1000000:
        raise HTTPException(status_code=400, detail="invalid_balance_change")
    ensure_user_exists(target_id)
    conn = db_connect(DATABASE_URL)
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT COALESCE(balance,0) FROM users WHERE telegram_id=%s FOR UPDATE", (target_id,))
        before = int(cursor.fetchone()[0] or 0)
        after = max(0, before + delta)
        cursor.execute("UPDATE users SET balance=%s WHERE telegram_id=%s", (after, target_id))
        _admin_audit(cursor, actor["telegram_id"], "balance_changed", target_id, {"balance": before}, {"balance": after}, reason)
        conn.commit()
        return {"ok": True, "balance": after}
    except Exception:
        conn.rollback()
        raise
    finally:
        cursor.close()
        conn.close()


@app.post("/api/admin/users/subscription")
async def admin_user_subscription(request: Request):
    payload = await request.json()
    actor = _admin_actor(payload, "manage_subscriptions")
    ensure_admin_tables()
    target_id = int(payload.get("user_id") or 0)
    action = str(payload.get("action") or "extend")
    days = max(1, min(int(payload.get("days") or 30), 730))
    reason = str(payload.get("reason") or "Изменение администратором")[:500]
    if not target_id or action not in {"extend", "cancel"}:
        raise HTTPException(status_code=400, detail="invalid_subscription_change")
    ensure_user_exists(target_id)
    ensure_payment_tables()
    conn = db_connect(DATABASE_URL)
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT subscription FROM users WHERE telegram_id=%s FOR UPDATE", (target_id,))
        before_plan = (cursor.fetchone() or [None])[0]
        cursor.execute("SELECT MAX(NULLIF(expires_at,'')::timestamp) FROM subscriptions WHERE telegram_id=%s AND status='active'", (target_id,))
        before_expiry = (cursor.fetchone() or [None])[0]
        if action == "cancel":
            cursor.execute("UPDATE subscriptions SET status='cancelled' WHERE telegram_id=%s AND status='active'", (target_id,))
            cursor.execute("UPDATE users SET subscription=NULL WHERE telegram_id=%s", (target_id,))
            after = {"subscription": "free", "expires_at": None}
        else:
            plan = str(payload.get("plan") or ("year" if days >= 365 else "month"))[:40]
            cursor.execute("""
                INSERT INTO subscriptions (telegram_id, subscription_type, payment_method, amount, currency,
                                           starts_at, expires_at, status, charge_id)
                VALUES (%s,%s,'admin',0,'CVX',NOW(),GREATEST(COALESCE(%s::timestamp,NOW()),NOW()) + (%s * INTERVAL '1 day'),
                        'active',%s) RETURNING id, expires_at
            """, (target_id, plan, before_expiry, days, f"admin:{actor['telegram_id']}:{uuid4()}"))
            inserted_id, expires_at = cursor.fetchone()
            cursor.execute("UPDATE subscriptions SET status='cancelled' WHERE telegram_id=%s AND status='active' AND id<>%s", (target_id, inserted_id))
            cursor.execute("UPDATE users SET subscription=%s WHERE telegram_id=%s", (plan, target_id))
            after = {"subscription": plan, "expires_at": _to_iso(expires_at)}
        _admin_audit(cursor, actor["telegram_id"], "subscription_changed", target_id,
                     {"subscription": before_plan, "expires_at": _to_iso(before_expiry)}, after, reason)
        conn.commit()
        return {"ok": True, **after}
    except Exception:
        conn.rollback()
        raise
    finally:
        cursor.close()
        conn.close()


@app.post("/api/admin/users/message")
async def admin_user_message(request: Request):
    payload = await request.json()
    actor = _admin_actor(payload, "message_users")
    ensure_admin_tables()
    target_id = int(payload.get("user_id") or 0)
    message = str(payload.get("message") or "").strip()
    if not target_id or not message or len(message) > 4000:
        raise HTTPException(status_code=400, detail="invalid_message")
    if not BOT_TOKEN:
        raise HTTPException(status_code=503, detail="telegram_bot_unavailable")
    def send_message():
        return requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                             json={"chat_id": target_id, "text": message}, timeout=20)
    response = await asyncio.to_thread(send_message)
    result = response.json() if response.content else {}
    sent = response.status_code < 400 and bool(result.get("ok"))
    conn = db_connect(DATABASE_URL)
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO admin_messages (admin_telegram_id,user_telegram_id,message,telegram_sent) VALUES (%s,%s,%s,%s)",
                       (actor["telegram_id"], target_id, message, sent))
        _admin_audit(cursor, actor["telegram_id"], "message_sent" if sent else "message_failed", target_id,
                     {}, {"length": len(message), "sent": sent}, "")
        conn.commit()
    finally:
        cursor.close()
        conn.close()
    if not sent:
        raise HTTPException(status_code=502, detail="telegram_send_failed")
    return {"ok": True}


@app.post("/api/admin/admins/list")
async def admin_list(request: Request):
    payload = await request.json()
    _admin_actor(payload, owner_only=True)
    ensure_admin_tables()
    conn = db_connect(DATABASE_URL)
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT telegram_id,role,permissions,active,granted_by,created_at FROM admin_users ORDER BY role='owner' DESC,created_at")
        return {"ok": True, "items": [{"telegram_id":r[0],"role":r[1],"permissions":r[2] or [],"active":bool(r[3]),
                "granted_by":r[4],"created_at":_to_iso(r[5])} for r in cursor.fetchall()]}
    finally:
        cursor.close()
        conn.close()


@app.post("/api/admin/admins/set")
async def admin_set(request: Request):
    payload = await request.json()
    actor = _admin_actor(payload, owner_only=True)
    ensure_admin_tables()
    target_id = int(payload.get("user_id") or 0)
    active = bool(payload.get("active", True))
    permissions = payload.get("permissions") or ["view_dashboard", "view_users", "message_users"]
    allowed = {"view_dashboard", "view_users", "manage_balance", "manage_subscriptions", "message_users", "view_audit", "view_errors"}
    permissions = [p for p in permissions if p in allowed]
    if not target_id or target_id == SUPERADMIN_TELEGRAM_ID:
        raise HTTPException(status_code=400, detail="invalid_admin_target")
    conn = db_connect(DATABASE_URL)
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT role,permissions,active FROM admin_users WHERE telegram_id=%s", (target_id,))
        before_row = cursor.fetchone()
        cursor.execute("""
            INSERT INTO admin_users (telegram_id,role,permissions,active,granted_by,updated_at)
            VALUES (%s,'admin',%s::jsonb,%s,%s,NOW())
            ON CONFLICT (telegram_id) DO UPDATE SET role='admin',permissions=EXCLUDED.permissions,
                active=EXCLUDED.active,granted_by=EXCLUDED.granted_by,updated_at=NOW()
        """, (target_id, json.dumps(permissions), active, actor["telegram_id"]))
        _admin_audit(cursor, actor["telegram_id"], "admin_access_changed", target_id,
                     {"role": before_row[0], "permissions": before_row[1], "active": before_row[2]} if before_row else {},
                     {"role": "admin", "permissions": permissions, "active": active}, "")
        conn.commit()
        return {"ok": True}
    except Exception:
        conn.rollback()
        raise
    finally:
        cursor.close()
        conn.close()


@app.post("/api/admin/audit")
async def admin_audit(request: Request):
    payload = await request.json()
    _admin_actor(payload, "view_audit")
    ensure_admin_tables()
    conn = db_connect(DATABASE_URL)
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT id,actor_telegram_id,action,target_telegram_id,reason,created_at FROM admin_audit_log ORDER BY id DESC LIMIT 100")
        return {"ok": True, "items": [{"id":r[0],"actor_id":r[1],"action":r[2],"target_id":r[3],
                "reason":r[4] or "","created_at":_to_iso(r[5])} for r in cursor.fetchall()]}
    finally:
        cursor.close()
        conn.close()


@app.post("/api/admin/errors")
async def admin_errors(request: Request):
    payload = await request.json()
    _admin_actor(payload, "view_errors")
    conn = db_connect(DATABASE_URL)
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT id,telegram_id,job_id,provider,model,status,error_text,created_at
            FROM prostudio_errors
            ORDER BY created_at DESC LIMIT 100
        """)
        return {"ok": True, "items": [{
            "id": row[0], "telegram_id": row[1], "job_id": row[2] or "",
            "provider": row[3] or "", "model": row[4] or "", "status": row[5] or "",
            "error": str(row[6] or "")[:1000], "created_at": _to_iso(row[7]),
        } for row in cursor.fetchall()]}
    finally:
        cursor.close()
        conn.close()


def _prostudio_download_filename(mode: str, job_id: str, content_type: str, object_key: str) -> str:
    safe_id = re.sub(r"[^A-Za-z0-9_-]", "", str(job_id or ""))[:36] or "result"
    normalized_mode = str(mode or "").strip().lower()
    mime = str(content_type or "").split(";", 1)[0].strip().lower()
    mime_extensions = {
        "image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp",
        "video/mp4": ".mp4", "video/webm": ".webm",
        "audio/mpeg": ".mp3", "audio/mp3": ".mp3", "audio/wav": ".wav",
        "audio/x-wav": ".wav", "audio/mp4": ".m4a", "audio/ogg": ".ogg",
    }
    fallback_extensions = {"image": ".png", "video": ".mp4", "music": ".mp3", "voice": ".mp3"}
    extension = mime_extensions.get(mime)
    if not extension:
        extension = pathlib.PurePosixPath(object_key or "").suffix.lower()
    if not extension or len(extension) > 8:
        extension = fallback_extensions.get(normalized_mode, ".bin")
    return f"sylvex-{normalized_mode}-{safe_id}{extension}"


@app.get("/api/public/prostudio/download/{job_id}")
async def public_prostudio_download(job_id: str, telegram_id: int = 0, init_data: str = ""):
    """Stream a completed job's durable R2 result without mutating the job."""
    if not telegram_id:
        raise HTTPException(status_code=400, detail="telegram_id_required")
    if BOT_TOKEN:
        signed_telegram_id = _telegram_id_from_init_data(init_data)
        if not signed_telegram_id or signed_telegram_id != int(telegram_id):
            raise HTTPException(status_code=403, detail="telegram_auth_failed")
    if not DATABASE_URL:
        raise HTTPException(status_code=503, detail="database_not_configured")
    if not r2_enabled():
        raise HTTPException(status_code=503, detail="r2_not_configured")

    conn = db_connect(DATABASE_URL)
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT telegram_id, status, mode, result_json
            FROM prostudio_generation_jobs
            WHERE id = %s
            LIMIT 1
        """, (job_id,))
        row = cursor.fetchone()
    finally:
        cursor.close()
        conn.close()

    if not row:
        raise HTTPException(status_code=404, detail="job_not_found")
    if int(row[0] or 0) != int(telegram_id):
        raise HTTPException(status_code=403, detail="job_access_denied")
    if str(row[1] or "").lower() != "completed":
        raise HTTPException(status_code=409, detail="job_not_completed")

    mode = str(row[2] or "").strip().lower()
    if mode not in {"image", "video", "music", "voice"}:
        raise HTTPException(status_code=400, detail="job_has_no_downloadable_media")
    result = _json_obj(row[3])
    media_urls = generation_result_urls(result, mode)
    media_url = media_urls[0] if media_urls else ""
    parsed_path = urllib.parse.unquote(urllib.parse.urlparse(media_url).path)
    if parsed_path.startswith("/webapp/generated/") or parsed_path.startswith("/generated/"):
        raise HTTPException(status_code=409, detail="job_result_is_not_in_r2")
    object_key = storage_key_from_url(media_url)
    if not object_key or not storage_exists(object_key):
        raise HTTPException(status_code=404, detail="r2_result_not_found")

    try:
        body, content_type, content_length = await asyncio.to_thread(storage_get_object, object_key)
    except Exception as exc:
        prostudio_error("PROSTUDIO_DOWNLOAD_R2_FAILED", exc, job_id=job_id, object_key=object_key)
        raise HTTPException(status_code=502, detail="r2_download_failed") from exc

    filename = _prostudio_download_filename(mode, job_id, content_type, object_key)
    headers = {
        "Content-Disposition": f'attachment; filename="{filename}"',
        "Cache-Control": "private, no-store",
        "X-Content-Type-Options": "nosniff",
    }
    if content_length is not None:
        headers["Content-Length"] = str(content_length)
    return StreamingResponse(
        storage_iter_object(body, max_bytes=content_length),
        media_type=content_type or "application/octet-stream",
        headers=headers,
    )


def _share_public_metadata(result: dict, request_payload: dict) -> dict:
    """Build an explicit public whitelist; never expose internal provider payloads."""
    result_meta = _json_obj(result.get("metadata"))
    options = {}
    for source in (
        _json_obj(request_payload.get("image_options")),
        _json_obj(request_payload.get("video_options")),
        _json_obj(request_payload.get("music_options")),
        _json_obj(request_payload.get("voice_options")),
        _json_obj(result_meta.get("settings")),
    ):
        options.update(source)

    def pick(*keys):
        for key in keys:
            for source in (result_meta, result, options, request_payload):
                value = source.get(key) if isinstance(source, dict) else None
                if value not in (None, "", [], {}):
                    return value
        return ""

    return {
        "style": pick("style", "styleName"),
        "character": pick("characterName", "character"),
        "object": pick("objectName", "objects", "object"),
        "size": pick("size", "resolution", "ratio"),
        "width": pick("width"),
        "height": pick("height"),
        "model_label": pick("model_label"),
    }


def _share_request_identity(data: dict) -> tuple[int, str]:
    telegram_id = int(data.get("telegram_id") or 0)
    init_data = str(data.get("init_data") or "")
    if not telegram_id:
        raise HTTPException(status_code=400, detail="telegram_id_required")
    if BOT_TOKEN:
        signed_telegram_id = _telegram_id_from_init_data(init_data)
        if not signed_telegram_id or signed_telegram_id != telegram_id:
            raise HTTPException(status_code=403, detail="telegram_auth_failed")
    return telegram_id, init_data


@app.post("/api/public/prostudio/share/{job_id}")
async def public_prostudio_create_share(job_id: str, request: Request):
    data = await request.json()
    telegram_id, _ = _share_request_identity(data)
    if not DATABASE_URL:
        raise HTTPException(status_code=503, detail="database_not_configured")
    if not r2_enabled():
        raise HTTPException(status_code=503, detail="r2_not_configured")

    conn = db_connect(DATABASE_URL)
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT j.telegram_id, j.status, j.mode, j.provider, j.model, j.prompt,
                   j.cost, j.result_json, j.request_json, j.created_at, j.completed_at,
                   u.username
            FROM prostudio_generation_jobs j
            LEFT JOIN users u ON u.telegram_id = j.telegram_id
            WHERE j.id = %s
            LIMIT 1
        """, (job_id,))
        row = cursor.fetchone()
    finally:
        cursor.close()
        conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="job_not_found")
    if int(row[0] or 0) != telegram_id:
        raise HTTPException(status_code=403, detail="job_access_denied")
    if str(row[1] or "").lower() != "completed":
        raise HTTPException(status_code=409, detail="job_not_completed")
    mode = str(row[2] or "").strip().lower()
    if mode not in {"image", "video", "music", "voice"}:
        raise HTTPException(status_code=400, detail="job_has_no_shareable_media")

    result = _json_obj(row[7])
    request_payload = _json_obj(row[8])
    media_urls = generation_result_urls(result, mode)
    media_url = media_urls[0] if media_urls else ""
    media_key = storage_key_from_url(media_url)
    if not media_key or not storage_exists(media_key):
        raise HTTPException(status_code=409, detail="job_result_is_not_in_r2")
    thumbnail_url = str(result.get("thumbnail_url") or result.get("thumb_url") or "")
    metadata = _share_public_metadata(result, request_payload)
    cost = {
        "credits": result.get("cost_credits", row[6] or 0),
        "usd": result.get("cost_usd", _json_obj(result.get("metadata")).get("cost_usd", "")),
    }
    generation_time = None
    if row[9] and row[10]:
        generation_time = max(0.0, (row[10] - row[9]).total_seconds())
    share = create_or_get_share(
        lambda: db_connect(DATABASE_URL), job_id=job_id,
        owner_telegram_id=telegram_id, owner_username=str(row[11] or ""),
        mode=mode, provider=str(row[3] or ""), model=str(row[4] or ""),
        prompt=str(row[5] or ""), cost=cost, generation_time=generation_time,
        media_url=media_url, thumbnail_url=thumbnail_url, public_metadata=metadata,
    )
    bot_username = (os.getenv("TELEGRAM_BOT_USERNAME") or "sylvexai_bot").strip().lstrip("@")
    share_url = f"https://t.me/{bot_username}?startapp=share_{share['share_id']}"
    return {"ok": True, **share, "share_url": share_url}


@app.get("/api/public/prostudio/share/{share_id}/download")
async def public_prostudio_share_download(share_id: str):
    if not DATABASE_URL:
        raise HTTPException(status_code=503, detail="database_not_configured")
    share = get_public_share(lambda: db_connect(DATABASE_URL), share_id, increment_views=False)
    if not share:
        raise HTTPException(status_code=404, detail="share_not_found")
    if not share.get("allow_download"):
        raise HTTPException(status_code=403, detail="download_disabled")
    object_key = storage_key_from_url(share.get("media_url") or "")
    if not r2_enabled() or not object_key or not storage_exists(object_key):
        raise HTTPException(status_code=404, detail="r2_result_not_found")
    try:
        body, content_type, content_length = await asyncio.to_thread(storage_get_object, object_key)
    except Exception as exc:
        prostudio_error("PROSTUDIO_SHARE_DOWNLOAD_FAILED", exc, share_id=share_id)
        raise HTTPException(status_code=502, detail="r2_download_failed") from exc
    increment_downloads(lambda: db_connect(DATABASE_URL), share_id)
    filename = _prostudio_download_filename(share.get("mode") or "file", share_id, content_type, object_key)
    headers = {
        "Content-Disposition": f'attachment; filename="{filename}"',
        "Cache-Control": "private, no-store",
        "X-Content-Type-Options": "nosniff",
    }
    if content_length is not None:
        headers["Content-Length"] = str(content_length)
    return StreamingResponse(storage_iter_object(body, max_bytes=content_length), media_type=content_type, headers=headers)


@app.get("/api/public/prostudio/share/{share_id}/media")
async def public_prostudio_share_media(share_id: str, request: Request):
    if not DATABASE_URL:
        raise HTTPException(status_code=503, detail="database_not_configured")
    share = get_public_share(lambda: db_connect(DATABASE_URL), share_id, increment_views=False)
    if not share:
        raise HTTPException(status_code=404, detail="share_not_found")
    object_key = storage_key_from_url(share.get("media_url") or "")
    if not r2_enabled() or not object_key or not storage_exists(object_key):
        raise HTTPException(status_code=404, detail="r2_result_not_found")
    try:
        range_header = str(request.headers.get("range") or "")
        body, content_type, content_length, total, start, end = await asyncio.to_thread(
            storage_get_object_range, object_key, range_header
        )
    except Exception as exc:
        prostudio_error("PROSTUDIO_SHARE_MEDIA_FAILED", exc, share_id=share_id)
        raise HTTPException(status_code=502, detail="r2_read_failed") from exc
    headers = {
        "Cache-Control": "public, max-age=3600",
        "X-Content-Type-Options": "nosniff",
        "Accept-Ranges": "bytes",
        "Content-Length": str(content_length),
    }
    status_code = 206 if range_header else 200
    if range_header:
        headers["Content-Range"] = f"bytes {start}-{end}/{total}"
    return StreamingResponse(
        storage_iter_object(body, max_bytes=content_length),
        media_type=content_type,
        headers=headers,
        status_code=status_code,
    )


@app.post("/api/public/prostudio/share/{share_id}/reference")
async def public_prostudio_share_reference(share_id: str, request: Request):
    data = await request.json()
    _share_request_identity(data)
    if not DATABASE_URL:
        raise HTTPException(status_code=503, detail="database_not_configured")
    share = get_public_share(lambda: db_connect(DATABASE_URL), share_id, increment_views=False)
    if not share:
        raise HTTPException(status_code=404, detail="share_not_found")
    if not share.get("allow_reference"):
        raise HTTPException(status_code=403, detail="reference_disabled")
    return {
        "ok": True,
        "reference": {
            "mode": share.get("mode"),
            "media_url": f"{str(WEBAPP_URL or '').rstrip('/')}/api/public/prostudio/share/{share_id}/media",
        },
    }


@app.post("/api/public/prostudio/share/{share_id}/prepared-message")
async def public_prostudio_share_prepared_message(share_id: str, request: Request):
    """Create a Telegram PreparedInlineMessage for the authenticated Mini App user."""
    data = await request.json()
    telegram_id, _ = _share_request_identity(data)
    if not BOT_TOKEN:
        raise HTTPException(status_code=503, detail="telegram_bot_not_configured")
    if not DATABASE_URL:
        raise HTTPException(status_code=503, detail="database_not_configured")

    share = get_public_share(lambda: db_connect(DATABASE_URL), share_id, increment_views=False)
    if not share:
        raise HTTPException(status_code=404, detail="share_not_found")

    public_base = str(WEBAPP_URL or "").rstrip("/")
    bot_username = (os.getenv("TELEGRAM_BOT_USERNAME") or "sylvexai_bot").strip().lstrip("@")
    deep_link = f"https://t.me/{bot_username}?startapp=share_{share_id}"
    media_url = f"{public_base}/api/public/prostudio/share/{share_id}/media"
    logo_url = f"{public_base}/webapp/assets/logo.png"
    mode = str(share.get("mode") or "image").lower()
    model = str(share.get("model") or share.get("provider") or "AI")
    prompt = re.sub(r"\s+", " ", str(share.get("prompt") or "")).strip()
    short_prompt = prompt[:220] + ("…" if len(prompt) > 220 else "")
    description = f"Создано в SYLVEX Pro Studio · {model}"
    if short_prompt:
        description += f"\n{short_prompt}"
    reply_markup = {
        "inline_keyboard": [[{"text": "Открыть в SYLVEX", "url": deep_link}]],
    }
    common = {
        "id": f"share_{share_id}"[:64],
        "reply_markup": reply_markup,
    }
    if mode == "image":
        result = {
            **common, "type": "photo", "photo_url": media_url,
            "thumbnail_url": media_url, "caption": description,
        }
    elif mode == "video":
        result = {
            **common, "type": "video", "video_url": media_url,
            "mime_type": "video/mp4", "thumbnail_url": logo_url,
            "title": "SYLVEX Pro Studio", "caption": description,
        }
    elif mode == "music":
        result = {
            **common, "type": "audio", "audio_url": media_url,
            "title": "SYLVEX Pro Studio", "caption": description,
        }
    else:
        result = {
            **common, "type": "voice", "voice_url": media_url,
            "title": "SYLVEX Pro Studio", "caption": description,
        }

    def save_prepared_message():
        return requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/savePreparedInlineMessage",
            json={
                "user_id": telegram_id,
                "result": result,
                "allow_user_chats": True,
                "allow_bot_chats": True,
                "allow_group_chats": True,
                "allow_channel_chats": True,
            },
            timeout=20,
        )

    try:
        response = await asyncio.to_thread(save_prepared_message)
        payload = response.json() if response.content else {}
        prepared_id = str((payload.get("result") or {}).get("id") or "")
        if response.status_code >= 400 or not payload.get("ok") or not prepared_id:
            raise RuntimeError(str(payload.get("description") or f"telegram_http_{response.status_code}"))
    except Exception as exc:
        prostudio_error("PROSTUDIO_SHARE_PREPARE_FAILED", exc, share_id=share_id, telegram_id=telegram_id)
        raise HTTPException(status_code=502, detail="telegram_share_prepare_failed") from exc
    return {"ok": True, "prepared_message_id": prepared_id, "share_url": deep_link}


@app.get("/api/public/prostudio/share/{share_id}")
async def public_prostudio_get_share(share_id: str):
    if not DATABASE_URL:
        raise HTTPException(status_code=503, detail="database_not_configured")
    share = get_public_share(lambda: db_connect(DATABASE_URL), share_id, increment_views=True)
    if not share:
        raise HTTPException(status_code=404, detail="share_not_found")
    public_share = dict(share)
    public_share["media_url"] = f"/api/public/prostudio/share/{share_id}/media"
    public_share["thumbnail_url"] = public_share["media_url"] if share.get("mode") == "image" else ""
    return {"ok": True, "share": public_share}

# =====================================================
# API ENDPOINT: public_paypal_create_order
# Принимает HTTP-запрос от Mini App или Telegram Bot.
# Маршрут FastAPI: @app.post("/api/public/payments/paypal/create-order")
# Проверяет входные данные, работает с базой/провайдерами и возвращает JSON-ответ фронтенду.
# =====================================================
@app.post("/api/public/payments/paypal/create-order")
# =====================================================
# PYTHON-БЛОК: public_paypal_create_order
# Выполняет отдельный шаг backend-логики SYLVEX.
# Связан с API, базой данных, провайдерами или подготовкой данных для Mini App.
# =====================================================
async def public_paypal_create_order(request: Request):
    data = await request.json()
    pack_id = data.get("pack_id") or data.get("package") or data.get("plan") or ""
    purchase_type = data.get("type") or data.get("purchase_type") or ""
    item = shop_item(pack_id)
    telegram_id = int(data.get("telegram_id") or data.get("user_id") or 0)

    if not item:
        return JSONResponse({"ok": False, "error": "unknown_pack"}, status_code=400)
    expected_type = paypal_purchase_type(item)
    if purchase_type and purchase_type not in {expected_type, item.get("kind")}:
        return JSONResponse({"ok": False, "error": "purchase_type_mismatch"}, status_code=400)
    if not telegram_id:
        return JSONResponse({"ok": False, "error": "user_id_required"}, status_code=400)
    if not paypal_configured():
        return JSONResponse({"ok": False, "error": "paypal_not_configured"}, status_code=502)

    try:
        order = create_paypal_order(telegram_id, pack_id, item)
    except Exception as exc:
        print("PAYPAL CREATE ORDER ERROR:", exc)
        return JSONResponse({"ok": False, "error": "paypal_not_configured"}, status_code=502)

    checkout_url = paypal_approve_url(order)
    if not order.get("id") or not checkout_url:
        return JSONResponse({"ok": False, "error": "paypal_checkout_url_missing"}, status_code=502)

    save_paypal_order(telegram_id, pack_id, item, order, checkout_url)
    log_user_event(
        telegram_id=telegram_id,
        source="mini_app",
        event_type="payment_invoice_created",
        event_name="paypal_order_created",
        payload={
            "pack_id": pack_id,
            "paypal_order_id": order.get("id"),
            "url": checkout_url,
        },
    )

    return {
        "ok": True,
        "url": checkout_url,
        "approval_url": checkout_url,
        "paypal_order_id": order.get("id"),
        "pack_id": pack_id,
        "type": expected_type,
    }


# =====================================================
# API ENDPOINT: public_paypal_subscription_created
# Принимает HTTP-запрос от Mini App или Telegram Bot.
# Маршрут FastAPI: @app.post("/api/public/payments/paypal/subscription-created")
# Проверяет входные данные, работает с базой/провайдерами и возвращает JSON-ответ фронтенду.
# =====================================================
@app.post("/api/public/payments/paypal/subscription-created")
# =====================================================
# PYTHON-БЛОК: public_paypal_subscription_created
# Выполняет отдельный шаг backend-логики SYLVEX.
# Связан с API, базой данных, провайдерами или подготовкой данных для Mini App.
# =====================================================
async def public_paypal_subscription_created(request: Request):
    data = await request.json()
    subscription_id = (data.get("subscription_id") or data.get("subscriptionID") or "").strip()
    plan_id = (data.get("plan_id") or "").strip()
    plan_type = (data.get("plan_type") or "").strip().lower()
    telegram_id = int(data.get("telegram_id") or data.get("user_id") or 0)
    pack_id = paypal_subscription_pack_for_plan(plan_id, plan_type)

    if not telegram_id:
        return JSONResponse({"ok": False, "error": "user_id_required"}, status_code=400)
    if not subscription_id:
        return JSONResponse({"ok": False, "error": "subscription_id_required"}, status_code=400)
    if not pack_id:
        return JSONResponse({"ok": False, "error": "unknown_plan"}, status_code=400)

    saved = save_paypal_subscription(telegram_id, subscription_id, plan_id, plan_type)
    if not saved:
        return JSONResponse({"ok": False, "error": "subscription_save_failed"}, status_code=500)

    log_user_event(
        telegram_id=telegram_id,
        source="mini_app",
        event_type="paypal_subscription_created",
        event_name="paypal_subscription_created",
        payload={
            "subscription_id": subscription_id,
            "plan_id": plan_id,
            "plan_type": plan_type,
            "pack_id": pack_id,
        },
    )
    return {"ok": True, "status": "pending", "subscription_id": subscription_id, "pack_id": pack_id}


# =====================================================
# API ENDPOINT: public_paypal_webhook
# Принимает HTTP-запрос от Mini App или Telegram Bot.
# Маршрут FastAPI: @app.post("/api/public/payments/paypal/webhook")
# Проверяет входные данные, работает с базой/провайдерами и возвращает JSON-ответ фронтенду.
# =====================================================
@app.post("/api/public/payments/paypal/webhook")
# =====================================================
# PYTHON-БЛОК: public_paypal_webhook
# Выполняет отдельный шаг backend-логики SYLVEX.
# Связан с API, базой данных, провайдерами или подготовкой данных для Mini App.
# =====================================================
async def public_paypal_webhook(request: Request):
    raw_body = await request.body()
    try:
        event = json.loads(raw_body.decode("utf-8"))
    except Exception:
        return JSONResponse({"ok": False, "error": "invalid_json"}, status_code=400)

    if not verify_paypal_webhook(request.headers, event):
        return JSONResponse({"ok": False, "error": "invalid_signature"}, status_code=401)

    event_type = event.get("event_type") or ""
    if event_type in {"BILLING.SUBSCRIPTION.ACTIVATED", "PAYMENT.SALE.COMPLETED"}:
        created = activate_paypal_subscription_from_event(event)
        return {"ok": True, "created": created}

    if event_type != "PAYMENT.CAPTURE.COMPLETED":
        return {"ok": True, "ignored": event_type}

    created = finalize_paypal_capture(event)
    if not created:
        created = activate_paypal_subscription_from_event(event)
    return {"ok": True, "created": created}

# =====================================================
# API ENDPOINT: public_stars_invoice
# Принимает HTTP-запрос от Mini App или Telegram Bot.
# Маршрут FastAPI: @app.post("/api/public/payments/stars/invoice")
# Проверяет входные данные, работает с базой/провайдерами и возвращает JSON-ответ фронтенду.
# =====================================================
@app.post("/api/public/payments/stars/invoice")
# =====================================================
# PYTHON-БЛОК: public_stars_invoice
# Выполняет отдельный шаг backend-логики SYLVEX.
# Связан с API, базой данных, провайдерами или подготовкой данных для Mini App.
# =====================================================
async def public_stars_invoice(request: Request):
    data = await request.json()
    pack_id = data.get("pack_id") or ""
    item = shop_item(pack_id)
    telegram_id = int(data.get("telegram_id") or 0)

    if not item:
        return JSONResponse({"ok": False, "error": "unknown_pack"}, status_code=400)
    if not telegram_id:
        return JSONResponse({"ok": False, "error": "telegram_id_required"}, status_code=400)

    charge_id = f"stars_{uuid4().hex}"
    try:
        invoice_url = create_telegram_stars_invoice_link(telegram_id, pack_id, item, charge_id)
    except Exception as exc:
        prostudio_error("STARS_INVOICE_ERROR", exc, telegram_id=telegram_id, pack_id=pack_id, charge_id=charge_id)
        return JSONResponse({"ok": False, "error": "stars_invoice_failed", "detail": str(exc)}, status_code=502)

    log_user_event(
        telegram_id=telegram_id,
        source="mini_app",
        event_type="payment_invoice_created",
        event_name="stars_invoice_created",
        payload={
            "pack_id": pack_id,
            "charge_id": charge_id,
            "invoice_url": invoice_url,
        },
    )

    return {
        "ok": True,
        "invoice_url": invoice_url,
        "pack_id": pack_id,
        "charge_id": charge_id,
    }


def _stars_item_from_payment_payload(payload: str):
    parsed = parse_shop_payload(payload)
    if parsed.get("kind") == "subscription":
        return SHOP_ITEMS.get(f"sub_{parsed.get('plan_key') or ''}")
    if parsed.get("kind") == "credits":
        credits = int(parsed.get("credits") or 0)
        return next((item for item in SHOP_ITEMS.values() if item.get("kind") == "credits" and int(item.get("credits") or 0) == credits), None)
    return None


def _answer_stars_pre_checkout(query_id: str, ok: bool, error_message: str = "") -> bool:
    body = {"pre_checkout_query_id": query_id, "ok": bool(ok)}
    if not ok:
        body["error_message"] = error_message or "Не удалось проверить платёж. Попробуйте ещё раз."
    response = requests.post(
        f"https://api.telegram.org/bot{BOT_TOKEN}/answerPreCheckoutQuery",
        json=body,
        timeout=8,
    )
    data = response.json() if response.content else {}
    return response.status_code < 400 and bool(data.get("ok"))


@app.post("/api/public/payments/stars/webhook")
async def public_stars_webhook(request: Request):
    if TELEGRAM_PAYMENT_WEBHOOK_SECRET:
        supplied_secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
        if not hmac.compare_digest(supplied_secret, TELEGRAM_PAYMENT_WEBHOOK_SECRET):
            return JSONResponse({"ok": False, "error": "invalid_webhook_secret"}, status_code=401)

    update = await request.json()
    pre_checkout = update.get("pre_checkout_query") or {}
    if pre_checkout:
        payload = str(pre_checkout.get("invoice_payload") or "")
        parsed = parse_shop_payload(payload)
        item = _stars_item_from_payment_payload(payload)
        telegram_id = int(parsed.get("telegram_id") or 0)
        payer_id = int((pre_checkout.get("from") or {}).get("id") or 0)
        expected_amount = int(item.get("stars") or 0) if item else 0
        valid = bool(
            item and telegram_id and telegram_id == payer_id
            and pre_checkout.get("currency") == "XTR"
            and int(pre_checkout.get("total_amount") or 0) == expected_amount
        )
        prostudio_debug(
            "STARS_PRE_CHECKOUT_RECEIVED",
            query_id=str(pre_checkout.get("id") or ""),
            telegram_id=telegram_id,
            payer_id=payer_id,
            kind=parsed.get("kind") or "",
            plan_key=parsed.get("plan_key") or "",
            currency=pre_checkout.get("currency") or "",
            amount=int(pre_checkout.get("total_amount") or 0),
            expected_amount=expected_amount,
            valid=valid,
            payload_parts=len(payload.split(":")),
        )
        answered = _answer_stars_pre_checkout(
            str(pre_checkout.get("id") or ""),
            valid,
            "Параметры счёта устарели. Вернитесь в магазин и создайте новый счёт.",
        )
        prostudio_debug("STARS_PRE_CHECKOUT_ANSWERED", query_id=str(pre_checkout.get("id") or ""), approved=valid, answered=answered)
        return {"ok": answered, "approved": valid}

    message = update.get("message") or update.get("edited_message") or {}
    payment = message.get("successful_payment") or {}
    if not payment:
        return {"ok": True, "ignored": True}

    payload = str(payment.get("invoice_payload") or "")
    parsed = parse_shop_payload(payload)
    item = _stars_item_from_payment_payload(payload)
    telegram_id = int(parsed.get("telegram_id") or 0)
    payer_id = int((message.get("from") or {}).get("id") or 0)
    expected_amount = int(item.get("stars") or 0) if item else 0
    if not item or not telegram_id or telegram_id != payer_id or payment.get("currency") != "XTR" or int(payment.get("total_amount") or 0) != expected_amount:
        return JSONResponse({"ok": False, "error": "invalid_successful_payment"}, status_code=400)

    charge_id = str(payment.get("telegram_payment_charge_id") or parsed.get("charge_id") or "")
    prostudio_debug(
        "STARS_SUCCESSFUL_PAYMENT_RECEIVED",
        telegram_id=telegram_id,
        kind=parsed.get("kind") or "",
        plan_key=parsed.get("plan_key") or "",
        amount=expected_amount,
        charge_id=charge_id,
        payload_parts=len(payload.split(":")),
    )
    created = finalize_shop_payment(
        telegram_id=telegram_id,
        provider="telegram_stars",
        item=item,
        amount=expected_amount,
        currency="XTR",
        payload=payload,
        charge_id=charge_id,
    )
    prostudio_debug("STARS_SUCCESSFUL_PAYMENT_FINALIZED", telegram_id=telegram_id, charge_id=charge_id, created=created)
    return {"ok": True, "created": created, "charge_id": charge_id}

# =====================================================
# API ENDPOINT: public_stars_confirm
# Принимает HTTP-запрос от Mini App или Telegram Bot.
# Маршрут FastAPI: @app.post("/api/public/payments/stars/confirm")
# Проверяет входные данные, работает с базой/провайдерами и возвращает JSON-ответ фронтенду.
# =====================================================
@app.post("/api/public/payments/stars/confirm")
# =====================================================
# PYTHON-БЛОК: public_stars_confirm
# Выполняет отдельный шаг backend-логики SYLVEX.
# Связан с API, базой данных, провайдерами или подготовкой данных для Mini App.
# =====================================================
async def public_stars_confirm(request: Request):
    data = await request.json()
    pack_id = data.get("pack_id") or ""
    charge_id = data.get("charge_id") or ""
    telegram_id = int(data.get("telegram_id") or 0)

    item = shop_item(pack_id)
    if not item:
        return JSONResponse({"ok": False, "error": "unknown_pack"}, status_code=400)
    if not telegram_id:
        return JSONResponse({"ok": False, "error": "telegram_id_required"}, status_code=400)
    if not charge_id:
        return JSONResponse({"ok": False, "error": "charge_id_required"}, status_code=400)

    # openInvoice(status="paid") is a UI signal, not cryptographic proof of
    # payment. The polling bot or Telegram webhook is the only component that
    # may activate the purchase after receiving successful_payment.
    user = sync_user_to_db({
        "telegram_id": telegram_id,
        "username": data.get("username") or None,
        "first_name": data.get("first_name") or "Telegram User",
        "status": "free",
        "balance": 0,
    })

    subscription_active = bool(
        item.get("kind") == "subscription"
        and (user or {}).get("subscription_status") == "active"
    )
    prostudio_debug(
        "STARS_CLIENT_CONFIRM_SYNCED",
        telegram_id=telegram_id,
        pack_id=pack_id,
        charge_id=charge_id,
        subscription_active=subscription_active,
    )
    return {
        "ok": True,
        "created": False,
        "user": user,
        "pack_id": pack_id,
        "charge_id": charge_id,
        "subscription_activated": subscription_active,
        "subscription_plan": item.get("plan_key") if item.get("kind") == "subscription" else None,
        "subscription_days": item.get("days") if item.get("kind") == "subscription" else None,
    }

# Developer payment endpoint for simulating successful payments (dev only)
# =====================================================
# API ENDPOINT: public_dev_payment
# Принимает HTTP-запрос от Mini App или Telegram Bot.
# Маршрут FastAPI: @app.post("/api/public/payments/dev/success")
# Проверяет входные данные, работает с базой/провайдерами и возвращает JSON-ответ фронтенду.
# =====================================================
@app.post("/api/public/payments/dev/success")
# =====================================================
# PYTHON-БЛОК: public_dev_payment
# Выполняет отдельный шаг backend-логики SYLVEX.
# Связан с API, базой данных, провайдерами или подготовкой данных для Mini App.
# =====================================================
async def public_dev_payment(request: Request):
    data = await request.json()

    telegram_id = int(data.get("telegram_id") or 0)
    pack_id = data.get("pack_id") or ""
    item = shop_item(pack_id)

    if telegram_id != DEV_TELEGRAM_ID:
        return JSONResponse({"ok": False, "error": "forbidden"}, status_code=403)

    if not item:
        return JSONResponse({"ok": False, "error": "unknown_pack"}, status_code=400)

    created = finalize_shop_payment(
        telegram_id=telegram_id,
        provider="developer",
        item=item,
        amount=0,
        currency="DEV",
        payload=f"developer:{pack_id}",
        charge_id=f"developer_{pack_id}_{uuid4().hex}",
    )

    print("DEV PAYMENT:", {
        "telegram_id": telegram_id,
        "pack_id": pack_id,
        "created": created,
        "kind": item["kind"],
        "plan": item.get("plan_key"),
        "bonus_credits": item.get("bonus_credits", 0),
    })

    user = sync_user_to_db({
        "telegram_id": telegram_id,
        "username": data.get("username") or None,
        "first_name": data.get("first_name") or "Developer",
        "status": "free",
        "balance": 0,
    })

    print("DEV PAYMENT USER:", {
        "telegram_id": user.get("telegram_id"),
        "status": user.get("status"),
        "subscription_plan": user.get("subscription_plan"),
        "subscription_expires_at": user.get("subscription_expires_at"),
        "balance": user.get("balance"),
    })

    return {
        "ok": True,
        "created": created,
        "kind": item["kind"],
        "plan": item.get("plan_key"),
        "bonus_credits": item.get("bonus_credits", 0),
        "user": user,
        "message": "Developer payment completed"
    }


# Developer reset endpoint for resetting developer subscription (dev only)
# =====================================================
# API ENDPOINT: public_dev_reset
# Принимает HTTP-запрос от Mini App или Telegram Bot.
# Маршрут FastAPI: @app.post("/api/public/payments/dev/reset")
# Проверяет входные данные, работает с базой/провайдерами и возвращает JSON-ответ фронтенду.
# =====================================================
@app.post("/api/public/payments/dev/reset")
# =====================================================
# PYTHON-БЛОК: public_dev_reset
# Выполняет отдельный шаг backend-логики SYLVEX.
# Связан с API, базой данных, провайдерами или подготовкой данных для Mini App.
# =====================================================
async def public_dev_reset(request: Request):
    data = await request.json()
    telegram_id = int(data.get("telegram_id") or 0)
    reset_credits = bool(data.get("reset_credits", False))

    if telegram_id != DEV_TELEGRAM_ID:
        return JSONResponse({"ok": False, "error": "forbidden"}, status_code=403)

    try:
        reset_result = reset_developer_subscription(telegram_id, reset_credits=reset_credits)
    except Exception as exc:
        print("DEV RESET ERROR:", exc)
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=502)

    user = sync_user_to_db({
        "telegram_id": telegram_id,
        "username": data.get("username") or None,
        "first_name": data.get("first_name") or "Developer",
        "status": "free",
        "balance": 0,
    })

    print("DEV RESET:", {
        "telegram_id": telegram_id,
        **reset_result,
    })

    return {
        "ok": True,
        **reset_result,
        "user": user,
        "message": "Developer subscription reset completed"
    }

# =====================================================
# API ENDPOINT: public_crypto_invoice
# Принимает HTTP-запрос от Mini App или Telegram Bot.
# Маршрут FastAPI: @app.post("/api/public/payments/crypto/invoice")
# Проверяет входные данные, работает с базой/провайдерами и возвращает JSON-ответ фронтенду.
# =====================================================
@app.post("/api/public/payments/crypto/invoice")
# =====================================================
# PYTHON-БЛОК: public_crypto_invoice
# Выполняет отдельный шаг backend-логики SYLVEX.
# Связан с API, базой данных, провайдерами или подготовкой данных для Mini App.
# =====================================================
async def public_crypto_invoice(request: Request):
    data = await request.json()
    pack_id = data.get("pack_id") or ""
    item = shop_item(pack_id)
    telegram_id = int(data.get("telegram_id") or 0)

    if not item:
        return JSONResponse({"ok": False, "error": "unknown_pack"}, status_code=400)
    if not telegram_id:
        return JSONResponse({"ok": False, "error": "telegram_id_required"}, status_code=400)

    try:
        invoice = create_crypto_invoice(telegram_id, pack_id, item)
    except Exception as exc:
        print("CRYPTO INVOICE ERROR:", exc)
        return JSONResponse({"ok": False, "error": "crypto_not_configured", "detail": str(exc)}, status_code=502)

    invoice_id = int(invoice.get("invoice_id"))
    asyncio.create_task(poll_crypto_invoice(invoice_id, telegram_id, pack_id))

    log_user_event(
        telegram_id=telegram_id,
        source="mini_app",
        event_type="payment_invoice_created",
        event_name="crypto_invoice_created",
        payload={
            "pack_id": pack_id,
            "invoice_id": invoice_id,
            "url": crypto_invoice_url(invoice),
        },
    )

    return {
        "ok": True,
        "url": crypto_invoice_url(invoice),
        "invoice_id": invoice_id,
        "status": invoice.get("status"),
        "pack_id": pack_id,
    }

# =====================================================
# API ENDPOINT: public_telegram_sync
# Принимает HTTP-запрос от Mini App или Telegram Bot.
# Маршрут FastAPI: @app.post("/api/public/telegram/sync")
# Проверяет входные данные, работает с базой/провайдерами и возвращает JSON-ответ фронтенду.
# =====================================================
@app.post("/api/public/telegram/sync")
# =====================================================
# СИНХРОНИЗАЦИЯ С TELEGRAM: public_telegram_sync
# Отправляет готовый результат или статус в Telegram Bot и сохраняет признак отправки в metadata карточки.
# =====================================================
async def public_telegram_sync(request: Request):
    payload = await request.json()
    init_data = payload.get("initData") or ""
    user_data = fallback_public_user(payload)

    # Telegram clients provide signed initData. In browser/dev preview we still
    # return optimistic initDataUnsafe fields so the Mini App can render.
    if init_data and BOT_TOKEN and not verify_telegram_init_data(init_data):
        return JSONResponse({"ok": False, "error": "invalid_init_data", "user": user_data}, status_code=401)

    try:
        user = await asyncio.to_thread(sync_user_to_db, user_data)
    except Exception as exc:
        print("USER SYNC FAILED:", exc)
        user = user_data

    return {"ok": True, "user": user}


# =====================================================
# API ENDPOINT: public_telegram_user_state
# Принимает HTTP-запрос от Mini App или Telegram Bot.
# Маршрут FastAPI: @app.get("/api/public/telegram/user-state")
# Проверяет входные данные, работает с базой/провайдерами и возвращает JSON-ответ фронтенду.
# =====================================================
@app.get("/api/public/telegram/user-state")
# =====================================================
# СИНХРОНИЗАЦИЯ С TELEGRAM: public_telegram_user_state
# Отправляет готовый результат или статус в Telegram Bot и сохраняет признак отправки в metadata карточки.
# =====================================================
async def public_telegram_user_state(telegram_id: int = 0):
    if not telegram_id:
        return JSONResponse({"ok": False, "error": "telegram_id_required"}, status_code=400)
    try:
        return await asyncio.to_thread(get_fast_user_state, int(telegram_id))
    except Exception as exc:
        print("USER STATE FAILED:", exc)
        return JSONResponse({"ok": False, "error": "user_state_failed"}, status_code=500)


# =====================================================
# API ENDPOINT: public_telegram_profile
# Принимает HTTP-запрос от Mini App или Telegram Bot.
# Маршрут FastAPI: @app.post("/api/public/telegram/profile")
# Проверяет входные данные, работает с базой/провайдерами и возвращает JSON-ответ фронтенду.
# =====================================================
@app.get("/api/public/telegram/profile")
async def public_telegram_profile_get(telegram_id: int = 0):
    if not telegram_id:
        return JSONResponse({"ok": False, "error": "telegram_id_required"}, status_code=400)
    try:
        profile = await asyncio.to_thread(get_user_profile, int(telegram_id))
        return {"ok": True, "telegram_id": int(telegram_id), "profile": profile}
    except Exception as exc:
        print("PROFILE LOAD FAILED:", exc)
        return JSONResponse({"ok": False, "error": "profile_load_failed"}, status_code=500)


@app.post("/api/public/telegram/profile")
# =====================================================
# ЗАГРУЗКА ФАЙЛОВ: public_telegram_profile
# Получает файл или ссылку, приводит её к безопасному формату и передаёт дальше в генерацию или сохранение.
# =====================================================
async def public_telegram_profile(request: Request):
    try:
        payload = await request.json()
    except Exception:
        return JSONResponse({"ok": False, "error": "invalid_json"}, status_code=400)
    if not isinstance(payload, dict):
        return JSONResponse({"ok": False, "error": "invalid_payload"}, status_code=400)
    init_data = payload.get("initData") or ""
    try:
        telegram_id = int(payload.get("telegram_id") or 0)
    except (TypeError, ValueError):
        telegram_id = 0

    if not telegram_id:
        user_data = fallback_public_user(payload)
        telegram_id = int(user_data.get("telegram_id") or 0)

    if not telegram_id:
        return JSONResponse({"ok": False, "error": "telegram_id_required"}, status_code=400)

    if init_data and BOT_TOKEN and not verify_telegram_init_data(init_data):
        return JSONResponse({"ok": False, "error": "invalid_init_data"}, status_code=401)

    theme_preference = payload.get("theme_preference")
    if theme_preference is not None and not isinstance(theme_preference, dict):
        return JSONResponse({"ok": False, "error": "invalid_theme_preference"}, status_code=400)
    if theme_preference is not None:
        allowed_theme_keys = {"id", "themeId", "coverIndex"}
        theme_preference = {key: value for key, value in theme_preference.items() if key in allowed_theme_keys}

    def persist_profile_request():
        profile = save_user_profile(
            telegram_id=telegram_id,
            display_name=payload.get("display_name"),
            custom_avatar_url=payload.get("custom_avatar_url"),
            theme_preference=theme_preference,
        )
        user = sync_user_to_db({"telegram_id": telegram_id})
        user.update(profile)
        try:
            log_user_event(
                telegram_id=telegram_id,
                source="mini_app",
                event_type="profile",
                event_name="profile_update",
                payload={
                    "has_display_name": bool(payload.get("display_name")),
                    "has_custom_avatar": bool(payload.get("custom_avatar_url")),
                    "theme_preference": theme_preference or {},
                },
            )
        except Exception as exc:
            print("PROFILE EVENT LOG FAILED:", exc)
        return profile, user

    try:
        profile, user = await asyncio.wait_for(
            asyncio.to_thread(persist_profile_request),
            timeout=12.0,
        )
    except asyncio.TimeoutError:
        print("PROFILE SAVE TIMEOUT:", telegram_id)
        return JSONResponse({"ok": False, "error": "profile_save_timeout"}, status_code=503)
    except Exception as exc:
        print("PROFILE SAVE FAILED:", telegram_id, exc)
        return JSONResponse({"ok": False, "error": "profile_save_failed"}, status_code=500)

    return {"ok": True, "profile": profile, "user": user}


# =====================================================
# API ENDPOINT: public_telegram_referrals
# Принимает HTTP-запрос от Mini App или Telegram Bot.
# Маршрут FastAPI: @app.get("/api/public/telegram/referrals")
# Проверяет входные данные, работает с базой/провайдерами и возвращает JSON-ответ фронтенду.
# =====================================================
@app.get("/api/public/telegram/referrals")
# =====================================================
# СИНХРОНИЗАЦИЯ С TELEGRAM: public_telegram_referrals
# Отправляет готовый результат или статус в Telegram Bot и сохраняет признак отправки в metadata карточки.
# =====================================================
async def public_telegram_referrals(telegram_id: int = 0):
    if not telegram_id:
        return JSONResponse({"ok": False, "error": "telegram_id_required"}, status_code=400)
    return get_referral_state(int(telegram_id), activate=False)


# =====================================================
# API ENDPOINT: public_activate_referrals
# Принимает HTTP-запрос от Mini App или Telegram Bot.
# Маршрут FastAPI: @app.post("/api/public/telegram/referrals")
# Проверяет входные данные, работает с базой/провайдерами и возвращает JSON-ответ фронтенду.
# =====================================================
@app.post("/api/public/telegram/referrals")
# =====================================================
# PYTHON-БЛОК: public_activate_referrals
# Выполняет отдельный шаг backend-логики SYLVEX.
# Связан с API, базой данных, провайдерами или подготовкой данных для Mini App.
# =====================================================
async def public_activate_referrals(request: Request):
    payload = await request.json()
    init_data = payload.get("initData") or ""
    telegram_id = int(payload.get("telegram_id") or 0)

    if not telegram_id:
        user_data = fallback_public_user(payload)
        telegram_id = int(user_data.get("telegram_id") or 0)

    if not telegram_id:
        return JSONResponse({"ok": False, "error": "telegram_id_required"}, status_code=400)

    if init_data and BOT_TOKEN and not verify_telegram_init_data(init_data):
        return JSONResponse({"ok": False, "error": "invalid_init_data"}, status_code=401)

    claim_code = str(payload.get("claim_code") or "").strip()
    if claim_code:
        state = claim_referral(int(telegram_id), claim_code)
        log_user_event(
            telegram_id=telegram_id,
            source="mini_app",
            event_type="referral",
            event_name="referral_opened_shop",
            payload={"code": claim_code, "claimed": state.get("claimed", False)},
        )
        return state

    state = get_referral_state(int(telegram_id), activate=bool(payload.get("activate", True)))
    log_user_event(
        telegram_id=telegram_id,
        source="mini_app",
        event_type="referral",
        event_name="referral_link_activated",
        payload={"code": state.get("code")},
    )
    return state


# =====================================================
# API ENDPOINT: public_log_event
# Принимает HTTP-запрос от Mini App или Telegram Bot.
# Маршрут FastAPI: @app.post("/api/public/events")
# Проверяет входные данные, работает с базой/провайдерами и возвращает JSON-ответ фронтенду.
# =====================================================
@app.post("/api/public/events")
# =====================================================
# PYTHON-БЛОК: public_log_event
# Выполняет отдельный шаг backend-логики SYLVEX.
# Связан с API, базой данных, провайдерами или подготовкой данных для Mini App.
# =====================================================
async def public_log_event(request: Request):
    data = await request.json()
    telegram_id = int(data.get("telegram_id") or 0)
    event_type = data.get("event_type") or "event"
    event_name = data.get("event_name") or ""
    payload = data.get("payload") or {}

    log_user_event(
        telegram_id=telegram_id,
        source="mini_app",
        event_type=event_type,
        event_name=event_name,
        payload=payload,
    )

    return {"ok": True}


# =====================================================
# API ENDPOINT: public_get_events
# Принимает HTTP-запрос от Mini App или Telegram Bot.
# Маршрут FastAPI: @app.get("/api/public/events")
# Проверяет входные данные, работает с базой/провайдерами и возвращает JSON-ответ фронтенду.
# =====================================================
@app.get("/api/public/events")
# =====================================================
# PYTHON-БЛОК: public_get_events
# Выполняет отдельный шаг backend-логики SYLVEX.
# Связан с API, базой данных, провайдерами или подготовкой данных для Mini App.
# =====================================================
async def public_get_events(telegram_id: int = 0):
    if not telegram_id:
        return JSONResponse({"ok": False, "error": "telegram_id_required"}, status_code=400)

    if not DATABASE_URL:
        return JSONResponse({"ok": False, "error": "database_not_configured"}, status_code=500)

    ensure_user_events_table()
    conn = db_connect(DATABASE_URL)
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT id, source, event_type, event_name, payload, created_at
            FROM user_events
            WHERE telegram_id = %s
            ORDER BY created_at DESC
            LIMIT 50
        """, (telegram_id,))
        rows = cursor.fetchall()
    finally:
        cursor.close()
        conn.close()

    events = [
        {
            "id": row[0],
            "source": row[1],
            "event_type": row[2],
            "event_name": row[3],
            "payload": row[4],
            "created_at": _to_iso(row[5]) if row[5] else None,
        }
        for row in rows
    ]

    return {"ok": True, "events": events}


# =====================================================
# PYTHON-БЛОК: openai_headers
# Выполняет отдельный шаг backend-логики SYLVEX.
# Связан с API, базой данных, провайдерами или подготовкой данных для Mini App.
# =====================================================
def openai_headers():
    return {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json",
    }


def openai_auth_headers():
    return {"Authorization": f"Bearer {OPENAI_API_KEY}"}

# =====================================================
# PYTHON-БЛОК: image_size
# Выполняет отдельный шаг backend-логики SYLVEX.
# Связан с API, базой данных, провайдерами или подготовкой данных для Mini App.
# =====================================================
def image_size(label: str) -> dict:
    ratio = label
    if "x" in label:
        try:
            w, h = [int(part) for part in label.lower().split("x", 1)]
            ratio = f"{w // math_gcd(w, h)}:{h // math_gcd(w, h)}"
        except Exception:
            ratio = label
    return {"id": label, "label": ratio, "ratio": ratio, "icon": ratio}

# =====================================================
# PYTHON-БЛОК: math_gcd
# Выполняет отдельный шаг backend-логики SYLVEX.
# Связан с API, базой данных, провайдерами или подготовкой данных для Mini App.
# =====================================================
def math_gcd(a: int, b: int) -> int:
    while b:
        a, b = b, a % b
    return max(a, 1)

# =====================================================
# PYTHON-БЛОК: default_image_capabilities
# Выполняет отдельный шаг backend-логики SYLVEX.
# Связан с API, базой данных, провайдерами или подготовкой данных для Mini App.
# =====================================================
def default_image_capabilities() -> list:
    models = []
    if BYTEPLUS_ARK_API_KEY:
        seedream_common = {
            "provider": "bytedance",
            "sizes": [
                image_size("auto"),
                image_size("1:1"),
                image_size("4:3"),
                image_size("3:4"),
                image_size("16:9"),
                image_size("9:16"),
            ],
            "counts": [1, 2, 3, 4],
            "styles": [
                {"id": "auto", "label": "Авто"},
                {"id": "photoreal", "label": "Фотореализм"},
                {"id": "cinematic", "label": "Кино"},
                {"id": "poster", "label": "Постер"},
                {"id": "3d", "label": "3D"},
            ],
            "characters": [
                {"id": "auto", "label": "Авто"},
                {"id": "portrait", "label": "Портрет"},
                {"id": "product", "label": "Продукт"},
                {"id": "soft", "label": "Soft"},
                {"id": "bold", "label": "Bold"},
            ],
            "supports_upload": True,
            "objects_ready": False,
        }
        models.extend([
            {
                **seedream_common,
                "id": "seedream-5-0-260128",
                "api_model": "seedream-5-0-260128",
                "label": "Seedream 5.0 Lite",
                "description": "BytePlus Seedream 5.0 Lite — фото-генерация высокого качества через ModelArk.",
            },
            {
                **seedream_common,
                "id": "dola-seedream-5-0-pro-260628",
                "api_model": "dola-seedream-5-0-pro-260628",
                "label": "Seedream 5.0 Pro",
                "description": "BytePlus Seedream 5.0 Pro — профессиональная фото-генерация через ModelArk.",
            },
            {
                **seedream_common,
                "id": "seedream-4-5-251128",
                "api_model": "seedream-4-5-251128",
                "label": "Seedream 4.5",
                "description": "BytePlus Seedream 4.5 — улучшенная эстетика, детализация и точность изображения.",
            },
            {
                **seedream_common,
                "id": "seedream-4-0-250828",
                "api_model": "seedream-4-0-250828",
                "label": "Seedream 4.0",
                "description": "BytePlus Seedream 4.0 — генерация изображений и визуальных сцен через ModelArk.",
            },
        ])
    if OPENAI_API_KEY:
        models.append({
            "id": "openai:gpt-image-1",
            "provider": "openai",
            "api_model": "gpt-image-1",
            "label": "GPT Image 1",
            "description": "OpenAI image generation",
            "sizes": [image_size("1024x1024"), image_size("1024x1536"), image_size("1536x1024")],
            "counts": [1],
            "styles": [
                {"id": "auto", "label": "Авто"},
                {"id": "photo", "label": "Фото"},
                {"id": "cinematic", "label": "Кино"},
                {"id": "illustration", "label": "Иллюстрация"},
                {"id": "minimal", "label": "Минимализм"},
            ],
            "characters": [
                {"id": "auto", "label": "Авто"},
                {"id": "portrait", "label": "Портрет"},
                {"id": "fashion", "label": "Fashion"},
                {"id": "product", "label": "Продукт"},
                {"id": "mood_dark", "label": "Dark mood"},
            ],
            "supports_upload": True,
            "objects_ready": True,
        })
    return models

# =====================================================
# PYTHON-БЛОК: get_image_capabilities
# Выполняет отдельный шаг backend-логики SYLVEX.
# Связан с API, базой данных, провайдерами или подготовкой данных для Mini App.
# =====================================================
def get_image_capabilities() -> dict:
    # =====================================================
    # PYTHON-БЛОК: enrich
    # Выполняет отдельный шаг backend-логики SYLVEX.
    # Связан с API, базой данных, провайдерами или подготовкой данных для Mini App.
    # =====================================================
    def enrich(models: list) -> list:
        out = []
        for model in models or []:
            if not isinstance(model, dict):
                continue
            item = dict(model)
            model_id = item.get("id") or item.get("model") or item.get("api_model") or ""
            frontend_id = (
                str(model_id)
                .replace("seedream-5-0-260128", "seedream_5_0_lite")
                .replace("dola-seedream-5-0-pro-260628", "seedream_5_0_pro")
                .replace("seedream-4-5-251128", "seedream_4_5")
                .replace("seedream-4-0-250828", "seedream_4_0")
            )
            item.update(image_model_features(frontend_id))
            out.append(item)
        return out

    if IMAGE_MODELS_JSON:
        try:
            raw = json.loads(IMAGE_MODELS_JSON)
            models = raw.get("models", raw) if isinstance(raw, dict) else raw
            if isinstance(models, list):
                return {"ok": True, "models": enrich(models)}
        except Exception as exc:
            print("IMAGE_MODELS_JSON FAILED:", exc)
    return {"ok": True, "models": enrich(default_image_capabilities())}

# =====================================================
# PYTHON-БЛОК: map_image_model_to_provider_model
# Выполняет отдельный шаг backend-логики SYLVEX.
# Связан с API, базой данных, провайдерами или подготовкой данных для Mini App.
# =====================================================
def map_image_model_to_provider_model(frontend_model: str) -> Optional[str]:
    value = (frontend_model or "").strip()
    if not value:
        return None
    normalized = value.lower()
    provider_cfg = IMAGE_PROVIDER_MODEL_MAP.get(normalized) or IMAGE_PROVIDER_MODEL_MAP.get(normalized.replace("-", "_"))
    if provider_cfg:
        return provider_cfg.get("provider_model")
    return BYTEPLUS_SEEDREAM_MODEL_MAP.get(normalized) or BYTEPLUS_SEEDREAM_MODEL_MAP.get(normalized.replace("-", "_"))

# =====================================================
# PYTHON-БЛОК: image_provider_mapping
# Выполняет отдельный шаг backend-логики SYLVEX.
# Связан с API, базой данных, провайдерами или подготовкой данных для Mini App.
# =====================================================
def image_provider_mapping(frontend_model: str) -> dict:
    value = (frontend_model or "").strip()
    normalized = value.lower()
    return IMAGE_PROVIDER_MODEL_MAP.get(normalized) or IMAGE_PROVIDER_MODEL_MAP.get(normalized.replace("-", "_")) or {}

# =====================================================
# PYTHON-БЛОК: image_model_features
# Выполняет отдельный шаг backend-логики SYLVEX.
# Связан с API, базой данных, провайдерами или подготовкой данных для Mini App.
# =====================================================
def image_model_features(frontend_model: str) -> dict:
    normalized = (frontend_model or "").strip().lower().replace("-", "_")
    features = IMAGE_MODEL_FEATURES.get(normalized) or re.sub(r"_0$", "", normalized)
    if isinstance(features, str):
        features = IMAGE_MODEL_FEATURES.get(features)
    if not features:
        features = {"character": False, "object": False, "seed": False}
    return {
        "character": bool(features.get("character")),
        "object": bool(features.get("object")),
        "seed": bool(features.get("seed")),
    }

# =====================================================
# PYTHON-БЛОК: unknown_byteplus_image_model_response
# Выполняет отдельный шаг backend-логики SYLVEX.
# Связан с API, базой данных, провайдерами или подготовкой данных для Mini App.
# =====================================================
def unknown_byteplus_image_model_response(frontend_model: str) -> dict:
    return {
        "ok": False,
        "error": "Unknown BytePlus image model mapping",
        "frontend_model": frontend_model or "",
        "provider": "bytedance",
    }

# =====================================================
# PYTHON-БЛОК: unknown_image_model_mapping_response
# Выполняет отдельный шаг backend-логики SYLVEX.
# Связан с API, базой данных, провайдерами или подготовкой данных для Mini App.
# =====================================================
def unknown_image_model_mapping_response(frontend_model: str, provider: str = "") -> dict:
    mapping = image_provider_mapping(frontend_model)
    return {
        "ok": False,
        "type": "image",
        "error": "Unknown provider model mapping",
        "frontend_model": frontend_model or "",
        "provider": provider or mapping.get("provider") or "",
        "endpoint": mapping.get("endpoint") or "",
    }

# =====================================================
# PYTHON-БЛОК: find_image_model
# Выполняет отдельный шаг backend-логики SYLVEX.
# Связан с API, базой данных, провайдерами или подготовкой данных для Mini App.
# =====================================================
def find_image_model(model_id: str) -> dict:
    models = get_image_capabilities().get("models") or []
    if model_id:
        mapping = image_provider_mapping(model_id)
        provider_model = mapping.get("provider_model")
        for model in models:
            if model.get("id") == model_id or model.get("api_model") == model_id:
                return model
            if provider_model and model.get("api_model") == provider_model:
                mapped = dict(model)
                mapped["id"] = model_id
                mapped["api_model"] = provider_model
                mapped["provider"] = mapping.get("provider") or mapped.get("provider")
                return mapped
        if mapping and provider_model:
            return {
                "id": model_id,
                "provider": mapping.get("provider"),
                "api_model": provider_model,
                "endpoint": mapping.get("endpoint"),
                "sizes": [image_size("1024x1024")],
                "counts": [1],
            }
    return {}

# =====================================================
# PYTHON-БЛОК: infer_image_model
# Выполняет отдельный шаг backend-логики SYLVEX.
# Связан с API, базой данных, провайдерами или подготовкой данных для Mini App.
# =====================================================
def infer_image_model(model_id: str, provider: str = "") -> dict:
    value = (model_id or "").strip()
    normalized = value.lower().replace("-", "_")
    provider = (provider or "").strip().lower()
    if normalized in ("gpt_image_1", "openai_gpt_image_1"):
        return {"id": value, "provider": "openai", "api_model": "gpt-image-1", "sizes": [image_size("1024x1024")], "counts": [1]}
    if normalized in ("gpt_image_2", "openai_gpt_image_2"):
        return {"id": value, "provider": "openai", "api_model": "gpt-image-2", "sizes": [image_size("1024x1024")], "counts": [1]}
    mapping = image_provider_mapping(value)
    if mapping and mapping.get("provider_model"):
        return {"id": value, "provider": mapping.get("provider"), "api_model": mapping.get("provider_model"), "sizes": [image_size("1:1")], "counts": [1, 2, 3, 4]}
    return {}

# =====================================================
# PYTHON-БЛОК: is_internal_ui_model
# Выполняет отдельный шаг backend-логики SYLVEX.
# Связан с API, базой данных, провайдерами или подготовкой данных для Mini App.
# =====================================================
def is_internal_ui_model(model: str) -> bool:
    return (model or "").strip().lower() in {"sylvex-pro", "sylvex-lite", "sylvex pro", "sylvex lite"}

# =====================================================
# PYTHON-БЛОК: invalid_generation_model_response
# Выполняет отдельный шаг backend-логики SYLVEX.
# Связан с API, базой данных, провайдерами или подготовкой данных для Mini App.
# =====================================================
def invalid_generation_model_response(model: str) -> JSONResponse:
    return JSONResponse(
        {
            "ok": False,
            "error": "Invalid generation model",
            "details": f"{model} is an internal UI label, not an API model. Frontend must send real image/video/music/voice model id.",
        },
        status_code=400,
    )

# =====================================================
# PYTHON-БЛОК: normalize_image_seed
# Выполняет отдельный шаг backend-логики SYLVEX.
# Связан с API, базой данных, провайдерами или подготовкой данных для Mini App.
# =====================================================
def normalize_image_seed(value):
    if value in (None, ""):
        return None
    try:
        seed = int(value)
    except (TypeError, ValueError):
        raise ValueError("Seed must be an integer")
    if seed < 0:
        raise ValueError("Seed must be zero or greater")
    return seed

# =====================================================
# PYTHON-БЛОК: normalize_payload_image_seed
# Выполняет отдельный шаг backend-логики SYLVEX.
# Связан с API, базой данных, провайдерами или подготовкой данных для Mini App.
# =====================================================
def normalize_payload_image_seed(payload: dict):
    opts = payload.get("image_options") or {}
    if not isinstance(opts, dict):
        opts = {}
    seed = normalize_image_seed(opts.get("seed"))
    opts["seed"] = seed
    payload["image_options"] = opts
    return seed

# =====================================================
# PYTHON-БЛОК: is_seedream_request
# Выполняет отдельный шаг backend-логики SYLVEX.
# Связан с API, базой данных, провайдерами или подготовкой данных для Mini App.
# =====================================================
def is_seedream_request(payload: dict) -> bool:
    model = str(payload.get("model") or "")
    provider = str(payload.get("provider") or "").lower()
    opts = payload.get("image_options") or {}
    option_model = str(opts.get("modelId") or opts.get("model_id") or "")
    return provider in ("bytedance", "byteplus") or bool(re.search(r"seedream", f"{model} {option_model}", re.I))

# =====================================================
# PYTHON-БЛОК: build_image_prompt
# Выполняет отдельный шаг backend-логики SYLVEX.
# Связан с API, базой данных, провайдерами или подготовкой данных для Mini App.
# =====================================================
def build_image_prompt(payload: dict) -> str:
    opts = payload.get("image_options") or {}

    character_prompt = str(opts.get("characterPrompt") or "").strip()
    object_prompt = str(opts.get("objectPrompt") or "").strip()

    base_prompt = (
        payload.get("prompt")
        or payload.get("text")
        or payload.get("input")
        or ""
    ).strip()

    parts = []
    character_name = str(opts.get("characterName") or "").strip()
    object_name = str(opts.get("objectName") or opts.get("objects") or "").strip()
    uploaded_refs = (
        _json_list(opts.get("referenceImageUrls"))
        or _json_list(opts.get("reference_image_urls"))
        or _json_list(opts.get("referenceImages"))
        or _json_list(opts.get("images"))
    )
    has_uploaded_image = bool(uploaded_refs or payload.get("attachment"))
    has_character = bool(character_name or opts.get("characterId") or _json_list(opts.get("characterReferences")))
    has_object = bool(object_name or opts.get("objectId") or _json_list(opts.get("objectReferences")))

    if has_character:
        operation = infer_character_operation(
            "image",
            opts.get("characterOperation") or opts.get("operation") or opts.get("generation_mode") or opts.get("mode"),
            has_source_image=has_uploaded_image,
            style=opts.get("style"),
        )
        parts.append(build_character_prompt(operation, character_prompt, base_prompt))
        base_prompt = ""

    if object_prompt:
        parts.append(object_prompt)

    if has_object and (has_character or has_uploaded_image):
        if has_character:
            parts.append(
                "Naturally apply the selected object to the selected character according to the object's purpose and physical function. "
                "For wearable objects, place them on the correct body part; for held or carried objects, integrate them into the character's hands or outfit; preserve realistic scale, contact, shadows, and perspective."
            )
        else:
            parts.append(
                "Integrate the selected object directly into the uploaded image according to the object's purpose and physical function. "
                "Preserve the uploaded image composition, environment, lighting, camera angle, and all existing elements while adding the object naturally with realistic scale, contact, shadows, and perspective."
            )

    if base_prompt:
        parts.append(base_prompt)

    if object_name:
        parts.append(f"Include or naturally integrate the selected object reference: {object_name}. Preserve the object's visual identity from the provided reference images.")

    size = str(
        opts.get("size")
        or opts.get("ratio")
        or opts.get("aspect_ratio")
        or opts.get("aspectRatio")
        or ""
    ).strip()

    ratio_map = {
        "1:1": "Generate a square 1:1 image composition.",
        "16:9": "Generate a horizontal widescreen 16:9 image composition.",
        "9:16": "Generate a vertical portrait 9:16 image composition, suitable for phone screen.",
        "3:4": "Generate a vertical 3:4 image composition.",
        "4:5": "Generate a vertical 4:5 social media image composition.",
        "5:4": "Generate a horizontal 5:4 image composition.",
        "4:3": "Generate a horizontal 4:3 image composition.",
        "21:9": "Generate an ultra-wide cinematic 21:9 image composition.",
    }

    if size and size.lower() != "auto":
        parts.append(ratio_map.get(size, f"Generate the image with {size} aspect ratio."))

    style = str(opts.get("style") or "").strip()
    
    # Add new visual style prompts here. The key must exactly match the Mini App style id from cabinet.js.
    # Example: cabinet.js id "aegean_luxury" -> main.py style_map key "aegean_luxury".
    style_map = {
        "cinematic": "Cinematic style, dramatic lighting, movie still composition, high detail, professional color grading.",
            "photoreal": "Photorealistic style, natural textures, realistic lighting, real camera lens look.",
            "anime": "Anime illustration style, clean line art, expressive lighting, polished character design.",
            "3d": "High quality 3D render style, realistic materials, depth, soft studio lighting.",
            "black_white": "Black and white style, strong contrast, film grain, monochrome photography.",
            "broken_glass": "Broken glass visual style, fractured reflections, sharp glass shards, dramatic refractions.",
            "hand_drawn": "Hand-drawn sketch style, pen drawing texture, visible strokes, artistic illustration.",
            "fog": "Foggy atmospheric style, soft haze, muted contrast, cinematic mist.",
            
            "aegean_luxury": """Transform the uploaded image into a premium White & Blue Aegean Mediterranean luxury editorial scene.
            Preserve the main subject identity, face, facial features, body shape, pose, body direction, expression, important silhouette, original framing, and overall composition. Do not change the person into someone else. Do not change gender, age, face structure, or recognizable identity.
            The image must always be rebuilt into a clean Greek island / Aegean luxury environment dominated by white and blue. The core visual world must include white marble, blue sea, blue sky, white architecture, arched shapes, smooth limestone walls, elegant coastal geometry, and calm expensive Mediterranean atmosphere.
            If the uploaded image contains a person, place the person inside a luxurious white marble Aegean promenade or terrace. The person should appear naturally standing, walking, sitting, or posing according to the original pose, but now located in a refined Greek coastal villa environment. The setting must include large white marble floor tiles, smooth white marble or limestone surfaces, rounded white arches, white columns or marble balustrades, and a huge calm blue sea visible in the distance. The sky must be clear soft blue or lightly cinematic with elegant white clouds.
            If the person appears female, style her in an elegant light white or ivory silky dress, soft flowing fabric, open shoulders or an elegant open-top summer design, refined luxury fashion mood, natural skin texture, soft cinematic daylight, and clean editorial beauty. Keep her face, identity, pose, body shape, and expression.
            If the person appears male, style him in a clean white linen shirt, light white or ivory linen trousers, relaxed Mediterranean luxury styling, and barefoot or minimal elegant summer footwear if necessary. Keep his face, identity, pose, body shape, and expression.
            The environment must always contain strong white-and-blue Aegean design elements: white marble floor slabs, white arches, white limestone walls, white coastal villa forms, deep blue sea horizon, soft blue sky, navy-blue accents, and elegant blue ceramic vases. Add marble pedestals or low marble columns with pleasant blue vases. The vases may contain white flowers, soft olive branches, or minimal coastal floral arrangements. These decorative elements must feel expensive, clean, minimal, and tasteful.
            Use a strict color palette: pure white, ivory, warm limestone, soft marble gray, deep navy blue, muted Aegean blue, clear sky blue, calm sea blue, and very subtle beige skin tones. The dominant colors must always be white and blue. Remove bright saturated colors, dirty city tones, neon colors, harsh greens, heavy browns, random clutter, and ordinary street-photo colors.
            Transform all backgrounds into a premium Aegean coastal luxury setting. Streets, rooms, buildings, cars, urban objects, landscapes, interiors, or any original background elements must be rebuilt into whitewashed Greek island architecture, marble terraces, arched walkways, coastal villa walls, sea-facing promenades, elegant minimal courtyards, and calm open-air Mediterranean spaces. The distant background should include a wide blue sea, clean horizon, soft coastal light, and airy luxury atmosphere.
            Transform objects and materials into refined Aegean luxury materials: polished white marble, matte limestone, ivory plaster, white ceramic, blue ceramic, brushed metal, navy fabric, soft linen, frosted glass, and clean natural stone. Everything must feel premium, calm, minimal, expensive, and editorial.
            Lighting must be clean cinematic Mediterranean daylight or soft muted golden evening light. Use gentle contrast, cool blue-gray shadows, white marble reflections, soft sea light, realistic texture, and high-end editorial depth. The final image must look like a luxury fashion campaign photographed on a Greek island terrace, not like a fantasy image, not like a cartoon, and not like a cheap travel-photo edit.
            Strict style enforcement: the scene must always include white marble surfaces, rounded white arches, a visible blue sea or sea horizon, white-and-blue color harmony, elegant blue vases, and clean Aegean villa atmosphere. The white and blue palette must dominate the entire image. Do not create a generic Mediterranean scene. Do not create a random luxury hotel. Do not create a normal city street. Do not keep the original messy background. Do not use dark heavy colors. Do not overdecorate. Do not make it fantasy, cartoon, plastic, over-sharp, or artificial.
            Final result: a premium White & Blue Aegean luxury editorial image with the original person preserved, dressed in elegant white Mediterranean styling, placed on a white marble promenade or terrace with white arches, blue ceramic vases with white flowers, huge calm blue sea in the distance, blue sky, clean minimal composition, realistic texture, soft cinematic light, and expensive Greek island atmosphere.""",
            
            "quiet_sepia": """Transform the uploaded image into an authentic Quiet Sepia vintage photograph from the 1940s–1960s. This must not look like a modern photo with a sepia filter. The entire image must be historically rebuilt as if it was truly photographed during the mid-20th century.
            Preserve the main subject identity, original composition, pose if present, face structure if present, body position if present, animal anatomy if present, object shape if present, vehicle silhouette if present, architectural layout if present, important silhouettes, framing, and key recognizable details. Do not change the main subject into something else. Keep the subject recognizable, but restyle everything into a believable 1940s–1960s world.
            Aggressively remove or transform all modern elements. Modern clothes, furniture, technology, architecture, accessories, vehicles, lighting, signs, branding, plastic objects, electronics, roads, interiors, and background details must be replaced with historically believable 1940s, 1950s, or early 1960s equivalents. The image must feel physically, visually, emotionally, and historically rooted in that era.
            Micro-detail transformation rule: every visible modern detail, even small accessories, must be carefully inspected and converted into a historically accurate 1940s–1960s equivalent. Do not ignore small objects. Watches, jewelry, glasses, belts, buttons, collars, shoes, bags, straps, buckles, zippers, seams, labels, logos, wall switches, door handles, mirrors, camera bodies, furniture hardware, fabric texture, and background objects must all belong to the mid-20th century.
            If the subject wears a modern watch or smartwatch, transform it into a period-correct vintage wristwatch: small round silver or brushed steel case, simple analog dial, thin hour markers, aged glass, worn leather strap, cracked or creased leather texture, slightly tarnished metal, modest elegant proportions, and quiet old-world character. No digital watch, no smartwatch, no rubber strap, no modern sports watch.
            If the subject holds a modern phone, transform it into a believable period-correct camera or object depending on the pose: a 1940s–1960s rangefinder camera, box camera, folding camera, compact film camera, cigarette case, notebook, or leather wallet. Preserve the hand position and composition, but remove all modern smartphone features such as lenses, screen, case, logo, MagSafe ring, glass slab design, and modern camera bumps.
            If the image contains people, preserve their identity, face structure, pose, body shape, expression, and body direction. Transform their clothing into period-correct 1940s–1960s outfits: wool coats, tailored suits, high-waisted trousers, modest dresses, blouses, cardigans, trench coats, classic shirts, suspenders, leather shoes, hats, scarves, gloves, and vintage accessories. Hairstyles, makeup, posture, and styling must match the mid-20th century. No modern sneakers, hoodies, logos, synthetic sportswear, modern watches, phones, or contemporary fashion.
            If the subject wears modern clothing, transform not only the outfit shape but also the details: fabric weave, collar shape, stitching, buttons, cuffs, belt loops, trouser cut, jacket lapels, shirt texture, coat lining, pocket shape, and shoe material. Replace printed logos and modern graphics with plain period-correct fabric, subtle woven texture, wool, cotton, linen, tweed, leather, or muted vintage patterns.
            If the image contains animals, preserve the animal’s species, pose, body shape, expression, and position. Place the animal naturally inside a believable vintage environment: old countryside yards, cobblestone streets, wooden interiors, classic farms, old European homes, vintage gardens, antique shops, railway stations, or quiet rural roads. Collars, harnesses, baskets, bowls, blankets, and surrounding objects must be period-correct and made from leather, metal, wood, cotton, wool, or ceramic.
            If the image contains vehicles, preserve the vehicle’s general position, angle, silhouette, and visual importance, but transform it into a historically accurate 1940s–1960s vehicle with appropriate body shape, chrome details, round headlights, steel wheels, period tires, vintage license plates, and old paint finish. Modern cars, motorcycles, buses, bicycles, trucks, and transport elements must become believable mid-century equivalents. Remove modern road markings, LED lights, plastic trim, digital displays, and contemporary branding.
            If the image contains objects, products, tools, furniture, or decor, preserve their role, placement, and basic shape, but rebuild them with period-correct materials and design: wood, brass, iron, glass, ceramic, leather, cotton, wool, paper, Bakelite, enamel, and aged metal. Modern electronics, plastic packaging, contemporary labels, digital screens, modern appliances, and synthetic materials must be replaced by antique or mid-century equivalents.
            If the image contains a mirror, door, wall, interior, or room details, rebuild every small element into the correct era: aged wooden doors, brass handles, old keyholes, slightly cloudy mirror glass, plaster walls, wallpaper, vintage picture frames, ceramic switches, Bakelite fixtures, old lamps, worn furniture edges, and natural patina.
            If the image contains architecture, streets, interiors, landscapes, or city scenes, rebuild the environment into a historically accurate 1940s–1960s setting. Modern buildings must become old European apartments, stone houses, brick facades, classic storefronts, train stations, countryside cottages, old workshops, simple cafés, vintage hotel rooms, narrow streets, wooden interiors, or modest mid-century homes. Add period-correct details such as old windows, lace curtains, wooden doors, plaster walls, cobblestone roads, iron railings, vintage lamps, old signs, classic furniture, analog clocks, books, newspapers, radios, typewriters, ceramic dishes, and worn fabrics.
            Use an authentic Quiet Sepia photographic look: warm sepia monochrome tones, soft brown shadows, faded ivory highlights, muted beige midtones, gentle contrast, deep but calm shadows, natural window light, soft overcast daylight, old cinema lighting, analog film grain, dust specks, slight scratches, faded contrast, subtle vignetting, imperfect old lens softness, realistic film blur, and archival paper texture.
            The mood must be quiet, nostalgic, melancholic, elegant, poetic, restrained, and cinematic. The image should feel like a still frame from an old European black-and-white or sepia film, an old family archive, a forgotten newspaper photograph, or a preserved mid-century documentary frame.
            The final image must not look digital, modern, glossy, colorful, cartoonish, fantasy, or artificially filtered. It must look like a real archival photograph from 1940–1960, with believable historical details, authentic materials, period-correct styling, old film texture, and timeless cinematic atmosphere.
            Strict style enforcement: no smartphones, no modern cars, no modern sneakers, no hoodies, no plastic objects, no LED lights, no digital screens, no contemporary branding, no modern architecture, no neon, no modern street signs, no modern fashion, no modern watch, no smartwatch, no rubber strap, no modern phone camera, no clean digital sharpness, no glossy skin, no oversaturated colors, and no simple sepia overlay. Every visible element must belong to the 1940s–1960s visually, materially, historically, and emotionally.
            Final result: an authentic Quiet Sepia 1940s–1960s archival photograph with the original subject preserved, all modern elements and micro-details replaced by historically accurate mid-century equivalents, soft natural light, old European cinema mood, warm sepia monochrome tones, analog film grain, faded contrast, old lens softness, realistic texture, tactile vintage accessories, and quiet nostalgic elegance.""",
            
            "silent_cyan": """Transform the uploaded image into a complete Silent Cyan cinematic scene, not a simple cyan filter or color overlay. Rebuild the entire image into a cold, toxic, misty, acid-cyan world.
            Preserve the main subject identity, shape, pose if present, face if present, animal anatomy if present, vehicle silhouette if present, architecture if present, composition, framing, and important silhouettes. Keep the subject recognizable, but transform all lighting, color, air, shadows, materials, background, and mood.
            Use a strong acid cyan and toxic teal palette: cyan-green chemical light, cold teal shadows, dark blue-green silhouettes, pale ghostly highlights, gray-cyan surfaces, wet reflections, and low-visibility fog. Remove warm colors, bright saturated colors, natural daylight, ordinary clean backgrounds, and cheerful tones.
            Add dense but readable fog everywhere: glowing mist, smoky haze, wet air, floating particles, soft diffusion, cyan bloom, film grain, faded highlights, deep silhouettes, and dreamlike cinematic softness. The fog must wrap around people, animals, vehicles, objects, architecture, landscapes, and background, but it must not fully hide the main shapes.
            If people are present, keep identity and pose, but turn them into cold cinematic figures with damp highlights, muted clothing, teal shadows, acid-cyan rim light, and mysterious thriller mood. If animals are present, keep species and pose, but make them misty, damp, and cyan-lit. If vehicles are present, keep silhouette and angle, but make them wet, shadowy, teal-reflective, and surrounded by fog. If landscapes or buildings are present, turn them into cold foggy cyan environments with low visibility and toxic atmosphere.
            Final result must look like a real psychological-thriller cinematic still: acid cyan fog, toxic teal light, cold mist, wet air, deep silhouettes, faded contrast, film grain, and silent melancholic atmosphere. No simple filter, no warm light, no bright colors, no clean air, no cartoon, no fantasy, no ordinary edited photo.""",

            "urban_ink": """Recreate the uploaded image as a full Urban Ink torn-paper street collage. This must not be a monochrome filter, not a simple black-and-white conversion, not a poster effect, and not a clean digital graphic. The entire image must be physically rebuilt as a rough handmade urban collage made from torn posters, newspaper scraps, photocopy textures, black ink, graffiti marks, paper cuts, damaged print layers, and fragmented street typography.
            Preserve the main subject identity, original composition, pose if present, face direction if present, body position if present, animal anatomy if present, object shape if present, vehicle silhouette if present, architectural layout if present, important silhouettes, framing, and key recognizable details. Do not change the main subject into something else. Keep the main face, body, animal, object, vehicle, building, or silhouette readable and recognizable, but rebuild everything else into raw monochrome collage language.
            Transform the entire scene: background, lighting, shadows, objects, surfaces, materials, edges, atmosphere, and textures must become torn-paper urban collage. Replace photographic realism with physical poster-wall construction: ripped paper layers, glued fragments, overlapping scraps, dirty street-wall surfaces, torn edges, rough ink stains, black brush marks, photocopy noise, halftone grain, scratched paper, damaged print, tape marks, paint smears, and abstract black-and-white graphic shapes.
            Use an extreme black-and-white visual system: deep black ink, dirty white paper, gray photocopy tones, harsh monochrome contrast, bold graphic shadows, rough halftone dots, faded newspaper gray, scratched black surfaces, white torn-paper cuts, and high-impact poster composition. Remove bright colors, natural colors, soft gradients, glossy finishes, clean modern lighting, smooth digital skin, and ordinary photo texture.
            The image must feel like a physical city poster wall: printed, ripped, glued, damaged, scratched, overpainted, partially erased, partially reconstructed, and layered over time. Some parts of the subject and background may be interrupted by paper tears, ink blocks, collage fragments, poster strips, newspaper scraps, or abstract typography, but the main subject must remain visually readable.
            If the image contains people, preserve their identity, face structure, pose, body shape, expression, and body direction. Rebuild them as a torn-paper editorial figure with high-contrast ink shadows, photocopied skin texture, cut-paper facial planes, rough black contour fragments, ripped clothing shapes, halftone grain, newspaper overlays, and graphic urban shadows. The face must remain recognizable and readable, but partially integrated into torn paper, ink marks, and collage layers.
            If the image contains animals, preserve the species, anatomy, pose, expression, and silhouette. Rebuild the animal as a raw monochrome collage figure made from torn paper, ink strokes, newspaper texture, rough halftone, scratched print, and fragmented shadow shapes. Fur, feathers, scales, or skin must become graphic paper texture and ink grain, while the animal remains recognizable.
            If the image contains vehicles, preserve the vehicle’s general silhouette, position, angle, and key recognizable details. Rebuild the vehicle as a street-poster collage object with bold black ink shadows, white paper highlights, torn metal panels, photocopy grain, scratched reflections, damaged license plate fragments, halftone glass, and rough pasted-paper body shapes. The vehicle must stay readable, but it should feel printed, ripped, glued, and reconstructed on a city wall.
            If the image contains buildings, streets, architecture, interiors, or city scenes, rebuild them as a gritty urban poster wall environment. Walls, windows, doors, floors, signs, furniture, streets, and architectural shapes must become layered newspaper scraps, ripped posters, stencil marks, black ink blocks, dirty concrete texture, photocopy noise, graffiti scratches, and fragmented typography. Keep the spatial layout readable, but destroy clean realism.
            If the image contains landscapes, nature, sea, sky, mountains, forests, fields, or open environments, transform them into abstract monochrome urban collage landscapes. Sky becomes torn white paper and gray photocopy haze. Water becomes ripped black-and-white reflection layers. Mountains become rough paper silhouettes. Trees and plants become black ink shapes, scratched lines, newspaper textures, and torn poster fragments. The landscape must remain understandable, but visually rebuilt as street zine collage.
            If the image contains objects, products, food, furniture, tools, decor, or small details, preserve their role, shape, placement, and silhouette. Rebuild them with ripped paper, black ink, photocopy texture, halftone shadows, newspaper fragments, scratched surfaces, pasted labels, stencil marks, and rough monochrome graphic construction. Small details should not be ignored; they must also become collage elements.
            Add fragmented urban typography everywhere in a controlled way: torn letters, partial newspaper headlines, unreadable poster text, broken numbers, stencil marks, graffiti tags, layered symbols, and abstract type fragments. Typography must feel like real street posters and newspaper scraps, not clean digital text. It should support the composition without covering the main face, main object, or important silhouette.
            Edges must feel physical and damaged: ripped borders, uneven paper cuts, glue marks, folded paper corners, peeled poster edges, scratched ink, torn strips, distressed frame edges, and imperfect print registration. The image should feel handmade, tactile, rough, rebellious, and editorial.
            Lighting must be replaced by graphic ink logic: no natural soft photographic light, no realistic gradients, no glossy highlights. Use hard black shadows, white paper highlights, rough gray photocopy midtones, bold contrast, and fragmented light shapes. Shadows must look like printed ink, torn paper, or pasted black shapes.
            The final result must feel like underground zine art, punk editorial design, street poster collage, black ink printmaking, experimental urban photography, photocopied magazine art, and graffiti wall texture combined. It must look physical, damaged, printed, glued, scratched, torn, and reconstructed.
            Strict style enforcement: no simple black-and-white filter, no clean monochrome photo, no smooth digital illustration, no glossy editorial finish, no realistic photo background, no soft gradients, no bright colors, no polished vector art, no clean typography, no neat magazine layout, no normal photographic lighting, no plastic smoothness. Every visible element must be absorbed into the Urban Ink torn-paper collage world.
            Final result: a complete Urban Ink torn-paper street collage with the original subject preserved, extreme black-and-white contrast, ripped paper layers, newspaper scraps, photocopy noise, halftone grain, graffiti marks, black ink stains, bold graphic shadows, fragmented typography, scratched poster-wall texture, damaged edges, and raw underground urban energy.
            Strict negative style block: do not simply make the photo black and white. Do not apply only a monochrome filter. Do not keep clean photo realism, smooth skin, natural lighting, realistic background detail, glossy finish, soft gradients, bright colors, polished vector shapes, clean typography, neat magazine layout, or modern digital smoothness. The entire image must be physically rebuilt as torn paper, black ink, newspaper scraps, photocopy noise, halftone grain, graffiti marks, damaged poster layers, scratched surfaces, and raw street-wall collage.""",

            "pastel_hologram": """Recreate the uploaded image as a full Pastel Hologram transformation. This must not be a pastel filter, not a simple brightness increase, not a soft beauty edit, and not a generic futuristic look. The entire image must be rebuilt as a cinematic pastel holographic world made of glass, crystal, translucent plastic, acrylic, pearl light, iridescent reflections, holographic silver, transparent layers, and soft cyan-pink haze.
            Preserve the main subject identity, original composition, pose if present, face direction if present, body position if present, animal anatomy if present, object shape if present, vehicle silhouette if present, architectural layout if present, important silhouettes, framing, and key recognizable details. Do not change the main subject into something else. Keep the main person, animal, object, vehicle, building, product, landscape, or silhouette recognizable, but transform every material, color, surface, light, texture, and atmosphere into the Pastel Hologram style.
            Replace all ordinary materials with pastel holographic equivalents. Fabric becomes pearlescent synthetic textile, translucent vinyl, reflective silk, glossy organza, iridescent mesh, or soft holographic plastic. Metal becomes soft chrome, icy silver, pearl metal, or holographic reflective alloy. Glass becomes milky crystal, frosted acrylic, transparent resin, or prism-like translucent panels. Wood, concrete, stone, leather, plastic, paper, and natural textures must be transformed into glossy pastel, glassy, crystal, translucent, pearlescent, or iridescent materials.
            Use a strong pastel holographic palette: mint cyan, pale turquoise, pearl white, soft pink, lavender, icy silver, translucent blue, opal purple, milky cream, and faint rainbow reflections. Remove harsh natural colors, dirty browns, heavy blacks, muddy grays, oversaturated reds, ordinary greens, warm orange light, and realistic everyday color tones. The entire image must feel bright, clean, delicate, glossy, transparent, futuristic, ethereal, and surreal.
            Add a strong but soft holographic atmosphere: cyan-pink haze, milky fog, pearl bloom, glowing highlights, gentle lens diffusion, transparent light layers, iridescent edges, glossy reflections, soft prism flares, opal light leaks, luminous panels, and dreamy low contrast. The atmosphere must be visible everywhere, but controlled: it must not hide the main face, body, object, vehicle, architecture, animal, or important silhouette.
            If the image contains people, preserve their identity, face structure, pose, body shape, expression, and body direction. Transform them into pastel holographic fashion subjects with pearlescent skin lighting, soft cyan-pink facial glow, iridescent clothing, translucent vinyl details, reflective silk, holographic accessories, glossy highlights, delicate futuristic styling, and clean cinematic editorial beauty. The face must remain readable and recognizable, with natural human features preserved, not plastic or distorted.
            If the image contains animals, preserve the animal’s species, anatomy, pose, expression, and position. Transform the animal into an ethereal pastel holographic subject with soft cyan-pink rim light, glossy fur or surface highlights, iridescent reflections, translucent atmospheric glow, crystal-like background elements, and delicate futuristic mood. The animal must remain recognizable and natural, not robotic or monstrous.
            If the image contains vehicles, preserve the vehicle’s general shape, position, angle, silhouette, and key recognizable details. Transform the vehicle into a pastel holographic luxury object with soft chrome body panels, icy silver reflections, tinted glass, cyan-pink light streaks, pearlescent paint, glowing edges, reflective acrylic surfaces, and clean futuristic atmosphere. Wheels, windows, headlights, body panels, and reflections must belong to the holographic pastel world.
            If the image contains buildings, streets, architecture, interiors, or city scenes, rebuild them into bright futuristic pastel hologram environments: glass structures, translucent architecture, acrylic walls, luminous panels, pearl-white floors, soft chrome details, crystal columns, misty pastel corridors, glowing windows, reflective surfaces, and airy cyan-pink light. Keep the spatial layout readable, but replace ordinary realism with clean holographic cinematic design.
            If the image contains landscapes, nature, sea, sky, mountains, forests, fields, or open environments, transform them into a surreal pastel hologram landscape. Water becomes glossy cyan glass, liquid crystal, or pearlescent reflective surface. Sky becomes milky turquoise-pink haze with soft luminous clouds. Mountains become translucent crystal silhouettes. Trees and plants become soft frosted glass, pastel resin, pearl leaves, or glowing translucent forms. Rocks, ground, sand, snow, clouds, and natural textures must become delicate crystal, acrylic, pearl, or iridescent materials.
            If the image contains objects, products, food, furniture, tools, decor, or small details, preserve their role, shape, placement, and silhouette, but transform them into glass, acrylic, crystal, transparent resin, glossy pastel material, soft chrome, holographic silver, or pearlescent surfaces. Small details must not be ignored: buttons, jewelry, watches, bags, shoes, cups, handles, lamps, screens, signs, furniture edges, and accessories must all become part of the same pastel holographic material system.
            Lighting must be soft, luminous, futuristic, and cinematic. Use pearl-white light, cyan-pink glow, lavender reflections, mint-blue highlights, icy silver shadows, soft bloom, glossy reflections, transparent light layers, and gentle low-contrast depth. Replace harsh sunlight, warm indoor lighting, dark shadows, ordinary daylight, and realistic photo lighting with a clean pastel holographic glow.
            The image must feel physically rebuilt into a new material world. Every surface should look touchable: smooth glass, frosted acrylic, pearl chrome, translucent plastic, holographic fabric, crystal resin, glossy pastel panels, opal reflections, and soft luminous fog. Nothing should feel like a normal photo with pastel color grading.
            Strict style enforcement: no simple pastel filter, no ordinary brightened photo, no normal realism, no dirty colors, no harsh contrast, no heavy black shadows, no matte everyday materials, no rough natural textures, no boring modern interior, no generic sci-fi darkness, no cyberpunk neon overload, no cartoon, no anime, no plastic skin, no distorted anatomy, no messy background, no cheap glossy effect. Every visible element must be absorbed into the Pastel Hologram material world.
            Final result: a cinematic Pastel Hologram image with the original subject preserved, rebuilt through pearl light, glass, crystal, acrylic, translucent plastic, holographic silver, iridescent reflections, cyan-pink haze, milky fog, glossy surfaces, pastel glow, soft bloom, clean futuristic composition, and ethereal fashion-editorial atmosphere.""",

            "built_bricks": """Transform the uploaded image into a complete Built Bricks toy construction world. This must not be a simple toy filter, cartoon effect, or color change. Rebuild the entire image as if every person, object, building, surface, and background element was physically constructed from interlocking plastic building bricks.
            Preserve the main subject, pose, face direction, body position, important objects, silhouettes, and basic composition, but aggressively transform all materials, shapes, clothing, environment, and details into a brick-built miniature diorama.
            Every visible element must look made from small plastic bricks, studs, plates, tiles, slopes, hinges, and modular block pieces. Human subjects must become brick-style toy minifigures or brick-built characters with simplified plastic faces, blocky hair, cylindrical hands, molded plastic clothing, and toy-like proportions. Clothing must become printed plastic torso pieces, brick-built accessories, or molded toy parts.
            Ordinary objects must become brick-built versions of themselves. Furniture, streets, cars, plants, houses, walls, props, and background details must be reconstructed from interlocking plastic bricks. Smooth real surfaces must be replaced with glossy plastic, visible studs, block seams, modular geometry, and toy-scale construction details.
            The final image must look like a real physical miniature model photographed with a camera, not a digital cartoon. Use bright clean lighting, glossy plastic reflections, shallow depth of field, macro toy photography, crisp brick edges, visible studs, accurate block geometry, and a playful constructed world.
            The scene should feel cheerful, clean, handcrafted, toy-like, colorful, architectural, and miniature. The background may use a clean turquoise or cyan studio backdrop, but the main focus must remain on the brick-built subjects and objects.
            The image must be fully transformed into a Built Bricks style physically, materially, geometrically, and visually.""",

            "neon_cutout": """Recreate the uploaded image as a full Neon Cutout screen-print poster. Do not apply only a neon color filter. Do not simply increase saturation. The entire photo must be rebuilt as a graphic cutout artwork made of flat neon ink layers, stencil silhouettes, acid outlines, and posterized color blocks.
            Keep only the main subject identity, pose, face direction, body position, important silhouettes, and overall framing. Everything else must be transformed: natural colors, lighting, shadows, materials, background, clothing, objects, architecture, plants, and atmosphere.
            Replace all realistic colors with extreme neon inks: hot pink, magenta, acid lime, toxic yellow, cyan green, deep violet, and dark burgundy. Turn skin into unnatural cyan-green and lime tones. Turn shadows into purple and magenta blocks. Turn backgrounds into hot pink neon fields. Turn object edges into bright yellow-lime glowing outlines.
            Every object must look like a cutout shape or screen-printed stencil. Add rough ink texture, poster grain, sharp graphic edges, color misregistration, bold silhouette separation, and high-contrast pop-art energy. The image should look printed on a poster, not photographed.
            Important subjects must remain clear and readable, but all fine realistic detail must be simplified into bold neon shapes. The final result must be aggressive, electric, artificial, urban, psychedelic, and instantly recognizable as Neon Cutout.
            This must be a complete graphic, color, and material transformation into the Neon Cutout style.""",

            "orange_dominion": """Recreate the uploaded image as a full Orange Dominion cinematic transformation. Do not apply only an orange filter. Do not simply make the photo warm. The entire scene must be rebuilt as if it was originally photographed inside a monochrome orange-red world.
            Keep only the main subject identity, pose, face direction, body position, important silhouettes, main objects, and general framing. Everything else must be transformed: color, lighting, background, architecture, clothing, materials, objects, atmosphere, shadows, depth, and mood.
            Use a total orange-red palette: burnt orange, amber, copper, terracotta, rust, crimson-orange, dark sienna, and deep red shadows. Eliminate every natural color. Skin, clothing, furniture, buildings, plants, sky, ground, and objects must all become part of the same orange dominion. Nothing should look normally colored.
            Add warm atmospheric fog, desert haze, soft dust in the air, diffused orange light, smooth red-orange shadows, low contrast highlights, cinematic depth, and a monumental quiet mood. The scene should feel spacious, minimal, and controlled, like a frame from a surreal futuristic art-house film.
            Transform ordinary backgrounds into vast minimalist interiors, arched spaces, desert landscapes, modernist architecture, smooth walls, sculptural forms, empty plazas, or cinematic orange environments. Replace messy or ordinary details with clean, simplified, elegant, warm-toned forms.
            Objects must not just be tinted orange; they must feel physically made for this world, with orange materials, warm shadows, amber highlights, and sculptural silhouettes. The whole image must be visually dominated by orange, with no competing colors.
            The final result must be quiet, powerful, warm, surreal, cinematic, minimalistic, dusty, atmospheric, and elegant. It must look like a real cinematic still from an orange-red world, not a normal photo with color grading.
            This must be a complete color, material, spatial, and atmospheric transformation into the Orange Dominion style.""",

            "retro_american_cartoon": """Recreate the uploaded image as a full 1930s–1950s Retro American Cartoon animation frame. Do not apply a simple cartoon filter. Do not make it anime, manga, modern Disney-like 3D, Pixar, or generic comic art. The entire image must be rebuilt as hand-drawn vintage American cel animation.
            Keep only the main subject identity, pose, face direction, body position, important silhouettes, and overall framing. Everything else must be transformed: face style, hair, clothing, objects, architecture, plants, furniture, lighting, colors, background, texture, and mood.
            Turn people into old American fairy-tale cartoon characters with large expressive eyes, soft rounded faces, delicate lips, clean eyelashes, smooth painted skin, elegant vintage hairstyles, graceful poses, simplified anatomy, and charming hand-drawn proportions. Do not copy any specific character, but use the general visual grammar of classic 1930s–1950s American animated heroines and storybook characters.
            Turn modern clothing into vintage animated wardrobe: classic dresses, puff sleeves, soft collars, elegant shirts, old-fashioned shoes, simple painted folds, clean silhouettes, and theatrical fairy-tale styling. Turn buildings into storybook architecture with charming roofs, clean windows, rounded shapes, painted walls, hand-drawn outlines, and bright classic colors. Turn objects into animated props with simplified shapes, bold outlines, painted highlights, and old cartoon charm.
            Use bright classic animation colors, not realistic photo colors: red, yellow, blue, green, cream, peach, black, and warm painted shadows. Add hand-painted cel texture, vintage ink outlines, soft background painting, slight paper/cel grain, theatrical lighting, and clean color separation.
            The result must look like a real frame from an old American hand-drawn animated movie, not a modern photo with a filter. Every part of the scene must be converted into this world. Faces, objects, houses, landscapes, furniture, and clothing must all share the same vintage cartoon language.
            This must be a complete historical, graphic, material, and emotional transformation into a Retro American Cartoon style.""",

            "retro_pop_graphic": """Recreate the uploaded image as an extreme Retro Pop Graphic comic poster. This must not look like a photo with a filter, not a colorful cartoon effect, not digital painting, and not modern glossy illustration. The original photo must be completely rebuilt from the ground up as a bold printed vintage pop-art poster from the 1950s–1970s comic-book and magazine era.
            Preserve only the essential structure of the original image: the main subject identity, pose, face direction, body angle, key silhouette, composition, framing, and important recognizable forms. Everything else must be aggressively transformed into retro pop-art graphic language: skin, hair, clothing, background, objects, architecture, landscape, lighting, shadows, textures, materials, and atmosphere.
            Use thick black ink outlines everywhere. Every major shape must have strong contour lines, clean graphic edges, and clear separation. Replace realistic details with flat poster shapes, simplified anatomy, stylized comic proportions, expressive illustrated eyes, bold lips, sharp eyebrows, clean smooth faces, and dramatic facial shadows. People must look like true vintage comic-book characters, not realistic humans with a cartoon filter.
            Convert all clothing into stylized retro comic fashion with solid color blocks, hard folds, graphic black shadow areas, simplified fabric shapes, and inked seams. Convert hair into bold illustrated hair masses with black ink strokes, flat highlight shapes, and strong graphic rhythm. No realistic hair strands, no soft photographic blending.
            Convert all objects, buildings, vehicles, interiors, landscapes, and background elements into mid-century printed comic poster forms. Use simplified geometry, thick outlines, exaggerated perspective where useful, hard dark shadows, flat reflections, and strong color separation. Remove photographic realism completely.
            Use a powerful vintage pop-art color system: bright red, yellow, blue, green, navy, black, white, cream, and warm peach skin tones. Use flat primary color blocks with high contrast. Replace all realistic lighting with posterized comic lighting. Replace soft shadows with hard black or dark navy shadow blocks. Shadows must look printed, graphic, sharp, and intentional.
            Add strong halftone dot patterns across skin, shadows, background, and selected color areas. Add visible screen-print texture, ink grain, imperfect registration, vintage paper grain, slight ink bleed, rough print edges, and authentic old poster surface texture. The image must feel physically printed on aged comic paper, not generated as a smooth digital illustration.
            Use dramatic pop-art composition: bold shapes, clean readability, high contrast, sharp silhouette, poster-like balance, strong graphic rhythm, and vintage magazine-cover energy. The final image must be loud, iconic, clean, colorful, and unmistakably retro.
            Avoid realism. Avoid soft shading. Avoid gradients. Avoid airbrush effects. Avoid modern 3D rendering. Avoid cinematic realism. Avoid anime style. Avoid glossy digital art. Avoid photorealistic textures. Avoid simply increasing saturation. This must be a full graphic, color, texture, material, and lighting transformation into an authentic Retro Pop Graphic comic poster.
            Final result: a real vintage printed pop-art comic poster with thick black ink, flat colors, halftone dots, screen-print imperfections, hard graphic shadows, bold simplified forms, and a powerful retro magazine illustration look.""",

            "rose_mint": """Recreate the uploaded image as a full Rose Mint pastel dream transformation. Do not apply only a pink filter. Do not simply make the image brighter. Do not create a generic pastel look. The entire image must be rebuilt into a soft rose-pink, mint-cyan, creamy-white, vanilla-caramel visual universe.
            Keep only the original composition, main subject identity, pose or object position, face direction if present, body position if present, important silhouettes, spatial layout, and overall framing. Everything else must be transformed: color, lighting, shadows, skin if present, clothing if present, hair if present, objects, background, architecture, landscape, water, sky, materials, air, mood, and texture.
            Force the whole image into the Rose Mint palette: blush rose, powder pink, milky white, vanilla cream, pale mint, soft aqua, pastel cyan, delicate peach, creamy beige, and soft caramel highlights. All harsh natural colors must disappear. Dark shadows must become soft mint-gray, muted rose-gray, or creamy lavender-gray. White areas must become creamy vanilla. Black, dirty brown, harsh blue, harsh green, and realistic gray tones must be removed or softened into the Rose Mint palette.
            Every element in the image must be converted into the same soft pastel world. People must become romantic pastel figures with delicate skin tones, light rose cheeks, soft hair, creamy-pink or mint-toned clothing, elegant vintage-inspired styling, and calm dreamy presence. Objects must become porcelain-like, ceramic, frosted glass, sugar-glazed, creamy, pastel-painted, or soft matte materials. Buildings must become charming pastel architecture with creamy walls, rose-tinted surfaces, mint-lit windows, soft arches, and storybook details. Landscapes must become dreamy pastel environments with mint haze, rose light, creamy highlights, and soft cinematic depth. Water must become pastel aqua-mint with creamy reflections and soft rose highlights. Sky must become milky vanilla-blue with blush clouds and delicate mint haze.
            Add strong but soft Rose Mint atmosphere everywhere: milky haze, vanilla light, caramel pastel softness, soft bloom, delicate fog, pink air, mint shadows, low contrast, smooth highlights, creamy glow, and gentle cinematic depth. The fog and softness must be visible across the entire scene, but controlled: it must not hide the main subject, important objects, silhouettes, face, body, architecture, landscape, or framing.
            Replace realistic lighting with pastel dream lighting. Replace hard shadows with muted mint-gray and rose-gray shadow softness. Replace realistic textures with creamy matte surfaces, porcelain softness, frosted-glass glow, sugar-glazed highlights, delicate grain, and dreamy pastel air. The image must not look photographic, harsh, dirty, natural, or ordinary.
            The final result must not look like a normal photo with a pink filter. It must look like the original scene was born inside a Rose Mint pastel dream world. Every surface, object, background, reflection, shadow, material, and atmospheric layer must belong to this style.
            Strict style enforcement: no ordinary photo colors, no harsh realism, no dark dirty shadows, no natural harsh blue sky, no realistic gray mountains, no rough natural browns, no strong black contrast, no simple brightness increase, no generic pastel filter. This must be a complete color, material, lighting, and atmospheric transformation into the Rose Mint style: dreamy, creamy, soft, pastel, elegant, airy, romantic, and unmistakably Rose Mint.""",

            "acid_swamp_cyan": """Transform the uploaded image into a complete Acid Swamp Cyan cinematic fog scene. This must not be a simple green filter, cyan overlay, teal color grade, or ordinary dark edit. Rebuild the entire image into a humid toxic swamp atmosphere filled with acid green fog, cyan-green mist, wet air, low visibility, and softened silhouettes.
            Preserve the main subject identity, original composition, pose if present, face structure if present, body position if present, animal anatomy if present, object shape if present, vehicle silhouette if present, architectural layout if present, important silhouettes, framing, and key recognizable details. Do not change the main subject into something else. Keep the subject recognizable, but make it feel submerged inside a toxic jungle-swamp fog world.
            The core style must feel like a strange misty swamp, deep jungle, toxic marsh, wet tropical fog, abandoned wetland, or forgotten dream covered in acid green haze. The air must feel humid, heavy, poisonous, and alive. The viewer should feel like they are looking through thick greenish fog where only softened silhouettes, damp surfaces, and glowing forms are clearly visible.
            Use a strong toxic swamp palette: acid green, cyan-green, toxic teal, wet emerald shadows, dark blue-green silhouettes, pale greenish highlights, gray-cyan mist, muddy green-black shadows, and faint chemical glow. Warm colors, bright cheerful tones, clean daylight, natural blue sky, dry air, clear backgrounds, and ordinary realistic colors must disappear into the acid swamp atmosphere.
            Add heavy visible fog everywhere: thick swamp mist, acid green haze, cyan-green vapor, humid air particles, smoky layers, floating moisture, low-distance visibility, soft diffusion, glowing toxic air, damp depth, and blurred silhouettes. The fog must wrap around people, animals, vehicles, objects, architecture, trees, water, interiors, landscapes, foreground, background, and negative space. The fog must be strong and visible, but the main subject and important shapes must remain readable.
            Silhouettes must be slightly softened and partially dissolved by the fog. Edges should not be perfectly clean. Distant objects should fade into greenish mist. Background details should become vague, ghostly, and swallowed by the swamp haze. The main subject should remain visible, but surrounded by a strong acidic fog envelope.
            If the image contains people, preserve their identity, face structure, pose, body shape, expression, and body direction. Transform them into silent figures inside toxic swamp fog, with damp skin highlights, muted dark clothing, acid-green rim light, cyan-green shadows, ghostly facial contrast, wet hair or damp fabric feeling, and mysterious thriller presence. Their face must remain readable, but softened by mist and humid air.
            If the image contains animals, preserve the species, anatomy, pose, expression, and position. Transform the animal into a misty swamp creature-like cinematic subject, not a monster, but naturally absorbed into the toxic fog. Fur, feathers, skin, scales, or body surfaces should catch wet greenish highlights, dark teal shadows, and humid mist. The animal must remain recognizable, but feel surrounded by poisonous jungle air.
            If the image contains vehicles, preserve the vehicle’s general shape, position, angle, and silhouette. Transform it into a wet, abandoned, cinematic object inside acid swamp fog. Surfaces must become damp, shadowy, green-cyan reflective, partially obscured by vapor, with dark glass, wet metal, muted paint, and fog curling around wheels, windows, body panels, and headlights. Remove clean sunny reflections and ordinary street-photo realism.
            If the image contains buildings, architecture, streets, interiors, or city scenes, rebuild them into a foggy toxic environment: abandoned wet streets, damp concrete, old walls, mist-filled corridors, jungle-covered ruins, swampy alleys, wet stone, shadowy rooms, humid industrial spaces, or decaying structures swallowed by greenish fog. Architecture must become dark, wet, muted, cyan-green lit, and partially hidden by swamp atmosphere.
            If the image contains landscapes, forests, jungle, water, sea, rivers, mountains, sky, or open environments, transform them into an acid swamp dream landscape. Water must become dark green-cyan, still, reflective, murky, or poisonous-looking. Sky must become pale green-gray, foggy cyan, or completely swallowed by haze. Trees and plants must become dark silhouettes inside humid green fog. Mountains and distant backgrounds must fade into low-visibility mist. Rocks, ground, grass, sand, clouds, and natural textures must become damp, muted, and absorbed into the toxic swamp world.
            If the image contains objects, products, furniture, decor, or small details, preserve their role, shape, and placement, but transform their materials into damp, shadowy, cyan-green, fog-covered surfaces. Metal becomes wet dark teal metal. Glass becomes fogged greenish glass. Fabric becomes damp and desaturated. Wood becomes wet dark brown-green. Plastic, bright colors, clean white surfaces, warm materials, and ordinary modern details must be absorbed into the acid swamp color system.
            Lighting must be unnatural, humid, diffused, and toxic. Use acid green glow, cyan-green chemical haze, teal ambient shadows, deep blue-green darkness, pale ghostly highlights, wet reflections, low contrast in the distance, and smoky depth. Replace normal daylight, warm indoor light, golden sunlight, clean exposure, and cheerful illumination with poisonous swamp fog light.
            Use cinematic texture: subtle film grain, faded highlights, mist diffusion, wet lens softness, fog bloom, atmospheric particles, damp reflections, smoky depth, and realistic humid air. The final image must feel like a real cinematic still from a psychological thriller, jungle horror, foggy swamp noir, or forgotten toxic dream, not like a fantasy illustration and not like a simple color edit.
            Strict style enforcement: no simple green filter, no simple cyan overlay, no clean teal color grade, no bright sunny scene, no dry air, no clear background, no warm light, no cheerful colors, no clean commercial look, no sharp dry silhouettes, no ordinary travel-photo mood, no cartoon, no fantasy magic, no neon rainbow colors, no plastic digital smoothness. Every visible element must be physically absorbed into the acid swamp fog world.
            Final result: a cinematic Acid Swamp Cyan image with the original subject preserved, strong acid green and cyan-green fog, humid toxic air, low visibility, softened silhouettes, wet surfaces, dark teal shadows, pale ghostly highlights, subtle film grain, and a silent mysterious swamp-thriller atmosphere.
            If the image contains a person, the fog must physically wrap around the body like thick swamp vapor. Create layered fog in front of the person, behind the person, around the shoulders, arms, hair, waist, legs, and edges of the silhouette. The fog should partially soften and dissolve the outline, but the face and main body shape must remain readable.
            Add distant backlights behind the person, like car headlights, old lamps, or faint toxic lights shining through the swamp fog. These lights must be blurred, diffused, partially hidden, and visible only through the thick green-cyan mist. The backlight should create a soft rim glow around the person and make the silhouette cinematic.
            The person must feel surrounded, wrapped, and swallowed by humid acid-green swamp steam. The fog should move through the scene in layers: foreground fog crossing the lower body, midground mist around the torso and hands, background haze hiding distant shapes, and glowing vapor behind the subject. The atmosphere must feel wet, heavy, toxic, silent, and mysterious.
            If the image contains people, preserve their identity, face structure, pose, body shape, expression, and body direction. Transform them into silent figures inside toxic swamp fog, with damp skin highlights, muted dark clothing, acid-green rim light, cyan-green shadows, ghostly facial contrast, wet hair or damp fabric feeling, and mysterious thriller presence.
            The fog must not only exist in the background — it must wrap around the person’s body like humid swamp steam. Create thick layered vapor around the shoulders, arms, hair, waist, hands, legs, and silhouette edges. Add foreground fog crossing the lower body, midground mist around the torso and face, and background haze behind the subject. The body outline should be slightly softened and partially dissolved by the fog, but the face and main silhouette must remain readable.
            Add distant blurred headlights or weak toxic lights behind the person, shining through the green-cyan fog. The lights must be diffused, low-visibility, partially hidden by mist, and should create a cinematic rim glow around the subject. The person should feel surrounded, swallowed, and gently enclosed by acid-green swamp vapor, like a figure standing inside a poisonous foggy marsh at night.""",

            "retro_futurism": """Recreate the uploaded image as a full 1950s–1960s Retro Futurism transformation. Do not apply only a vintage filter. Do not create modern sci-fi. Do not make it cyberpunk. The entire image must be rebuilt as a mid-century space-age future world.
            Keep only the main subject identity, pose, face direction, body position, important silhouettes, main objects, and overall framing. Everything else must be transformed: clothing, hair, architecture, vehicles, objects, materials, lighting, background, colors, atmosphere, and mood.
            Force the whole image into an authentic retro-future universe inspired by 1950s and 1960s space-age design. Replace modern clothes with pastel retro space uniforms, elegant vintage dresses, high collars, rounded shoulders, polished hairstyles, and clean old sci-fi fashion. Replace modern buildings with curved space-age architecture, glass domes, rounded roofs, chrome trims, circular windows, futuristic diners, spaceport terminals, and smooth atomic-age structures.
            Replace ordinary vehicles and objects with flying saucers, small retro aircraft, analog control panels, dials, gauges, antenna rings, chrome devices, orbital shapes, glass capsules, pastel machines, and vintage futuristic props. Every object must feel like it belongs to the future imagined in the mid-20th century.
            Use pastel turquoise, dusty pink, cream white, mint, coral, chrome silver, warm peach, amber sunset, and soft teal shadows. Remove modern natural colors, dark cyberpunk tones, realistic modern technology, harsh black sci-fi, and contemporary minimalism. The color palette must feel soft, optimistic, nostalgic, and cinematic.
            Add warm sunset atmosphere, golden lens flare, gentle haze, glossy chrome reflections, smooth plastic, painted metal, curved glass, soft shadows, and a dreamy space-age cinematic glow. The environment must feel like a retro-futuristic spaceport, atomic-age suburb, old sci-fi movie set, or 1960s vision of tomorrow.
            The final result must not look edited. It must look as if the original scene was born inside this retro-futuristic world. Every surface, object, building, piece of clothing, and background element must obey the Retro Futurism style.
            This must be a complete historical, material, architectural, color, and atmospheric transformation into the Retro Futurism style.
            Strict negative style block: no simple vintage filter, no basic sci-fi filter, no modern futuristic city, no cyberpunk, no neon purple, no neon blue, no dark dystopian sci-fi, no black armor, no modern spacesuit, no realistic NASA suit, no modern smartphones, no modern cars, no modern buildings, no contemporary minimalism, no brutalist architecture, no harsh HDR, no sharp digital look, no glossy modern commercial photo, no realistic normal clothing, no realistic normal architecture, no grunge, no horror mood, no post-apocalyptic style, no orange monochrome, no cyan fog, no rose mint, no pastel hologram, no toy bricks, no urban ink collage, no retro comic pop-art, no anime, no manga, no cartoon, no 3D render, no watercolor, no oil painting, no excessive blur, no unreadable subject, no distorted anatomy, no text, no watermark, no logo.""",

            "ballpoint_blue": """Recreate the uploaded image as a full Ballpoint Blue pen drawing. Do not apply only a blue tint. Do not create a generic pencil sketch. Do not use digital comic outlines. The entire scene must be rebuilt as a hand-drawn blue ballpoint pen illustration on warm cream paper.
            Keep only the main subject identity, pose, face direction, body position, important silhouettes, and overall framing. Everything else must be transformed: color, lighting, texture, shadows, materials, background, objects, clothing, architecture, and atmosphere.
            Force the whole image into a blue ink and cream paper world. All real colors must disappear. Every person, object, house, chess piece, tree, field, wall, fabric, and surface must be expressed through blue pen lines, cross-hatching, contour drawing, soft sketch strokes, and negative paper space.
            Use fine blue linework, layered ballpoint ink, cross-hatching, scribbled shading, subtle pressure marks, imperfect handmade contours, visible paper fibers, slight ink pooling, and soft scanned-paper texture. Shadows must be built only from blue pen strokes. Highlights must remain as untouched cream paper.
            Do not make the image too dark, too realistic, too smooth, or too digital. The style must remain airy, minimal, handmade, delicate, and quiet. Important faces, bodies, objects, and silhouettes must stay readable, but they must look drawn, not photographed.
            The final result must look like an original sketchbook page drawn with a blue ballpoint pen: elegant, minimal, textured, analog, calm, and poetic.
            This must be a complete color, material, texture, and drawing-style transformation into the Ballpoint Blue style.
            Strict negative style block: no simple blue filter, no blue photo tint, no generic pencil sketch, no graphite drawing, no charcoal drawing, no black ink, no colorful image, no realistic photo texture, no realistic skin tones, no digital painting, no comic style, no anime, no manga, no cartoon, no 3D render, no watercolor, no oil painting, no marker art, no neon colors, no pastel hologram, no rose mint, no cyan fog, no sepia photo, no urban collage, no retro cartoon, no toy bricks, no orange monochrome, no heavy black shadows, no glossy digital look, no smooth gradients, no airbrush shading, no high saturation, no harsh contrast, no over-detailed background, no cluttered composition, no text, no watermark, no logo.""",

            "radical_red": """Recreate the uploaded image as a full Radical Red constructivist poster transformation. Do not apply only a red color filter. Do not simply make the photo black and white with a red background. The entire scene must be rebuilt as a red-black-white avant-garde graphic collage.
            Keep only the original subject identity, pose, face direction, body position, important silhouettes, main objects, and overall framing. Everything else must be transformed: color, lighting, background, clothing, architecture, objects, landscape, shadows, materials, texture, and composition.
            Force the whole image into a strict Radical Red visual system: deep red dominant fields, grayscale photographic cutouts, black silhouettes, white circles, sharp lines, target rings, geometric bars, abstract blocks, cut-paper fragments, and hard poster shadows. Every visible element must become part of the same graphic system.
            For people: convert the subject into a high-contrast black-and-white poster portrait with clean grayscale skin, deep black hair shadows, white highlights, sharp facial planes, and strong editorial lighting. Add constructivist graphic elements around the face and body: circles, red panels, black bars, white disks, thin lines, vertical cuts, abstract overlays, and target-like shapes. The face must remain recognizable and readable, but it must look like a radical poster portrait, not a normal photo.
            For small objects: convert them into iconic black-and-white graphic forms with hard edges, strong shadows, simplified detail, and clean silhouettes. Add red negative space, white circle accents, black line structures, and poster-like geometry. Small details should not disappear; they should become sharper, cleaner, and more graphic.
            For large scenes: convert buildings, landscapes, skies, mountains, trees, interiors, and streets into layered constructivist collage. Large areas must become flat red planes. Architecture must become grayscale cutout forms. Trees and mountains must become black or gray silhouettes. Skies must become red poster fields with white suns or circles. The whole scene must feel designed, not naturally photographed.
            Remove every natural color, soft photographic realism, smooth gradients, casual modern atmosphere, and ordinary background detail. Replace them with strict red-black-white composition, high contrast, geometric order, collage layering, and radical graphic tension.
            The final result must look like a real printed avant-garde poster or editorial art piece: bold, clean, sharp, red-dominant, geometric, serious, and visually aggressive.
            This must be a complete color, graphic, material, scale, and composition transformation into the Radical Red style.
            Strict negative style block: no simple red filter, no basic red overlay, no normal black-and-white photo, no normal photo with red background, no soft portrait, no realistic skin tones, no natural colors, no blue sky, no green plants, no colorful clothing, no pastel colors, no neon colors, no orange monochrome, no rose mint, no cyan fog, no sepia vintage, no retro cartoon, no pop-art comic, no anime, no manga, no 3D render, no watercolor, no oil painting, no soft gradients, no smooth beauty retouching, no glossy commercial photo, no cinematic warm lighting, no cyberpunk, no grunge texture, no messy uncontrolled collage, no excessive text, no readable words, no brand logos, no low contrast, no weak geometry, no missing circles, no absence of red dominance, no missing graphic poster structure, no hidden face, no unreadable object, no distorted anatomy, no text, no watermark, no logo.""",

            "indie_fisheye": """Recreate the uploaded image as a full-screen Indie Fisheye photograph, not a vintage filter, not a normal wide-angle photo, and not a circular fisheye frame. The image must remain a full rectangular photo, but the fisheye distortion must affect the entire frame from edge to edge.
            Preserve the main subject identity, shape, pose if present, face if present, animal anatomy if present, vehicle silhouette if present, architecture if present, composition, framing, and important details. Keep the subject readable, but transform the whole image as if it was shot through a real full-frame fisheye lens, action camera, or 360-style wide lens on an old indie film camera.
            Use strong full-frame fisheye optics: convex center bulge, rounded perspective, stretched edges, curved horizon, curved vertical lines near the sides, enlarged foreground forms, compressed distant background, close-camera intimacy, soft edge blur, subtle vignette, imperfect focus, film grain, sun flare, lens haze, warm overexposed highlights, and old-camera softness.
            Do not create a circular image. Do not add black round borders. Do not place the photo inside a lens circle. Do not crop into a circle. The entire rectangular image must be distorted like real fisheye footage.
            If people are present, keep identity and face readable, but make the portrait close, personal, spontaneous, slightly rounded, warm, imperfect, and sunlit. If vehicles are present, enlarge the foreground bumper or closest parts, curve the road and background, and add warm analog lens haze. If interiors or buildings are present, curve walls, ceilings, windows, doors, and edges. If landscapes are present, bend the horizon, enlarge foreground ground, and make the sky feel wide and rounded.
            Use faded turquoise, teal green, warm beige, cream, olive shadows, sandy brown, soft blue sky, golden sunlight, natural warm skin tones, film grain, sun spots, analog haze, soft overexposure, and nostalgic summer atmosphere.
            Final result must look like a real imperfect indie fisheye snapshot: full-screen rectangular frame, strong convex lens distortion, rounded close perspective, stretched edges, warm sun flare, soft grain, old-camera texture, dreamy nostalgic mood, and emotionally alive summer feeling.
            Strict negative style block: no circular fisheye frame, no black circular border, no round lens mask, no photo inside a circle, no tiny circular image, no vignette covering the frame, no normal wide-angle photo, no clean digital fisheye effect, no simple vintage filter, no basic summer filter, no perfect modern lens, no HDR, no oversharpening, no glossy commercial photo, no sterile studio lighting, no harsh contrast, no horror mood, no cyberpunk, no neon colors, no overly saturated colors, no orange monochrome, no cyan fog, no rose mint, no pastel hologram, no urban ink collage, no retro cartoon, no toy bricks, no constructivist poster, no black and white, no sepia, no anime, no manga, no cartoon, no 3D render, no oil painting, no watercolor, no excessive blur, no hidden face, no unreadable subject, no extreme warped face, no broken anatomy, no unnatural body distortion, no text, no watermark, no logo.""",

            "illustrated_retro_futurism": """Recreate the uploaded image as a full Illustrated Retro Futurism transformation. Do not apply only a vintage filter. Do not simply add planets in the background. Do not create modern sci-fi, cyberpunk, anime, 3D CGI, or a normal photo with space decoration. The entire image must be rebuilt as a hand-painted 1950s–1960s science fiction magazine illustration.
            Keep only the original subject identity, pose, face direction, body position, important silhouettes, main objects, spatial layout, and overall framing. Everything else must be transformed: clothing, hair, materials, buildings, vehicles, objects, background, sky, lighting, shadows, colors, texture, and atmosphere.
            Force the whole image into a vintage illustrated sci-fi world. Big scenes must become grand retro-futuristic environments: domed houses, space-age observatories, rocket launch platforms, flying saucers, glass towers, circular windows, cosmic terraces, alien mountains, futuristic suburbs, dramatic space skies, giant planets, moons, stars, nebulae, galaxies, rockets, and glowing horizons.
            People must become hand-painted retro space-age heroes: glossy vintage spacesuits, bubble helmets, metallic collars, gloves, boots, belts, old sci-fi uniforms, elegant 1950s–1960s hairstyles, idealized painted faces, heroic poses, and classic adventure-poster presence. The person must remain readable and recognizable, but the wardrobe and atmosphere must fully belong to the old sci-fi illustration world.
            Small objects must become painted retro-futuristic props: chrome machines, analog control panels, rocket-shaped forms, glowing buttons, orbital rings, polished surfaces, enamel colors, glass domes, metallic edges, readable silhouettes, and old magazine-cover detail. Small details must not be erased; they must be redesigned into clear illustrated sci-fi forms.
            Use deep cosmic blues, midnight navy, warm orange sunset, gold, cream, chrome silver, dusty teal, turquoise, red accents, violet shadows, and star-like highlights. Use hand-painted brushwork, vintage paper texture, old magazine grain, theatrical lighting, dramatic painted shadows, glowing highlights, cosmic atmosphere, and strong retro adventure composition.
            The final result must look like an authentic old science fiction cover illustration, not a digital filter or modern concept art. Every person, object, building, sky, background, and tiny detail must obey the same Illustrated Retro Futurism style.
            This must be a complete historical, visual, material, scale, and atmosphere transformation into Illustrated Retro Futurism.
            Strict negative style block: no simple retro filter, no basic vintage color grading, no normal photo with planets added, no modern sci-fi, no cyberpunk, no neon purple, no neon blue, no dark dystopian future, no realistic NASA astronaut suit, no modern spacecraft, no modern cars, no smartphones, no modern city, no contemporary architecture, no clean CGI, no 3D render, no photorealistic space movie still, no anime, no manga, no cartoon, no comic book style, no Pixar, no modern digital concept art, no minimalist sci-fi, no horror sci-fi, no grunge, no post-apocalyptic style, no simple poster filter, no weak transformation, no realistic clothing, no realistic ordinary background, no missing planets, no missing stars, no missing rockets, no missing vintage illustration texture, no flat empty sky, no bad anatomy, no distorted face, no unreadable subject, no excessive blur, no text, no watermark, no logo.""",

            "acid_ink": """Recreate the uploaded image as a full Acid Ink toxic blue-green illustration. Do not apply a simple blue-green filter. Do not only recolor the photo. Do not make it a normal comic, cartoon, or digital painting. The entire scene must be rebuilt as a detailed acid-lime and deep-navy ink engraving.
            Keep only the original subject identity, pose, face direction, body position, important silhouettes, main objects, animals, spatial layout, and overall framing. Everything else must be transformed: color, lighting, texture, shadows, materials, background, clothing, architecture, objects, landscape, and atmosphere.
            Force the entire image into a strict deep-blue and acid-green visual system. Use dark navy shadows, ultramarine blue fields, black-blue contours, toxic lime highlights, electric chartreuse surfaces, dirty green midtones, and engraved ink texture. All natural colors must disappear.
            For people, create readable acid-green poster portraits with deep blue shadows, sharp contour lines, detailed facial hatching, inked hair texture, graphic cheek shadows, and toxic lime highlights. The person must remain recognizable, but they must look printed and illustrated, not photographed.
            For animals, objects, and small details, use precise ink contours, cross-hatching, etched shadows, lime-green highlight planes, stippled texture, and blueprint-like graphic detail. Every small element should become sharper and more iconic, not lost or blurred.
            For big environments, turn houses, cars, streets, landscapes, trees, mountains, interiors, and skies into large acid-blue graphic compositions. Use flat deep-blue skies, lime-green buildings, navy shadow blocks, etched terrain, scratched mountain textures, and strong poster-like contrast.
            The final result must look like a real printed underground illustration, an acid blueprint poster, or a toxic ink engraving. It must not look like a normal photo with a color effect. Every person, object, animal, building, and tiny detail must obey the same Acid Ink style.
            This must be a complete color, ink, material, texture, and scale transformation into Acid Ink.
            Strict negative style block: no simple blue-green filter, no basic duotone overlay, no normal photo with green tint, no realistic skin tones, no natural colors, no warm sunlight, no orange tones, no red tones, no pink tones, no pastel colors, no soft beauty photo, no clean digital look, no glossy commercial photo, no smooth gradients, no airbrush shading, no realistic photography, no watercolor, no oil painting, no anime, no manga, no cartoon, no 3D render, no cyberpunk neon, no soft pastel hologram, no rose mint, no orange dominion, no cyan fog, no urban ink collage, no retro cartoon, no toy bricks, no vintage sepia, no black and white photo, no low contrast, no weak linework, no missing hatching, no missing ink texture, no blurry subject, no hidden face, no unreadable object, no excessive distortion, no text, no watermark, no logo.""",

            "minimal_rainbow_gradient": """Recreate the uploaded image as a full Minimal Rainbow Gradient transformation. Do not apply only a rainbow filter. Do not simply add colorful gradient light. Do not make it neon, cyberpunk, childish, or realistic. The entire scene must be rebuilt as a clean minimal pastel illustration made of soft cream backgrounds, smooth shapes, low contrast, and controlled rainbow gradients.
            Keep only the original subject identity, pose, face direction, body position, important silhouettes, main objects, animals, spatial layout, and overall framing. Everything else must be transformed: color, lighting, texture, shadows, materials, clothing, architecture, objects, landscape, background, and atmosphere.
            Force the whole image into a soft minimal rainbow system: cream white base, ivory beige background, pastel pink, peach, pale yellow, mint green, aqua cyan, lavender, muted violet, and soft gray shadows. All natural colors must disappear or become pastel gradient equivalents. Harsh black shadows must become soft muted gray-green or pale violet. Strong realistic textures must become smooth matte surfaces.
            For people, create a clean minimal portrait with smooth cream skin, simplified elegant facial features, soft lips, calm eyes, minimal linework, and pastel rainbow gradients flowing through hair, clothing, shadows, or background. The person must remain recognizable, but they must look illustrated, serene, soft, and premium.
            For animals and small objects, simplify forms into readable smooth silhouettes with soft gradient shading, creamy highlights, and minimal detail. Keep important shapes clear, but remove visual noise. The object should look like a clean design illustration or smooth pastel sculpture.
            For large scenes, convert houses, cars, interiors, streets, landscapes, skies, trees, and architecture into minimal pastel compositions. Use clean geometric shapes, wide empty space, soft gradient panels, creamy skies, simplified trees, gentle hills, and calm atmospheric depth. Large objects should become smooth, quiet, modern, and softly colored.
            The rainbow gradient must be strongly present but refined: soft transitions, no hard neon bands, no chaotic color splashes, no aggressive saturation. The image must feel like a luxury pastel design poster, calm fashion illustration, or minimal dreamlike editorial artwork.
            The final result must look born inside the Minimal Rainbow Gradient world, not edited afterward. Every person, object, animal, building, and background element must obey the same clean pastel gradient style.
            This must be a complete color, material, shape, lighting, and atmosphere transformation into Minimal Rainbow Gradient.
            Strict negative style block: no simple rainbow filter, no basic gradient overlay, no colorful tint only, no neon rainbow, no acid colors, no harsh saturation, no cyberpunk, no glowing fantasy aura, no childish rainbow, no cartoonish rainbow, no realistic photo texture, no realistic skin pores, no harsh black shadows, no dark cinematic lighting, no gritty texture, no dirty colors, no cluttered background, no high contrast, no HDR, no oversharpening, no glossy commercial photo, no complex noisy details, no heavy outlines, no comic style, no anime, no manga, no 3D render, no oil painting, no watercolor, no urban ink collage, no acid ink, no cyan fog, no orange dominion, no toy bricks, no retro cartoon, no sepia vintage, no black and white, no text, no watermark, no logo, no unreadable subject, no hidden face, no distorted anatomy.""",

            # Add the next style prompt below this line, before the closing brace.
        }
    

    if style and style.lower() not in {"auto", "none"}:
        parts.append(style_map.get(style, f"Apply this visual style: {style}."))

    character = str(opts.get("character") or opts.get("mood") or "").strip()
    character_map = {
        "calm": "Mood/character: calm, soft, balanced, peaceful.",
        "dark": "Mood/character: dark, mysterious, dramatic, intense.",
        "aggressive": "Mood/character: aggressive, powerful, energetic, sharp.",
        "romantic": "Mood/character: romantic, emotional, soft light, warm atmosphere.",
        "futuristic": "Mood/character: futuristic, advanced technology, sleek sci-fi feeling.",
        "business": "Mood/character: professional, clean, premium, business style.",
    }

    if character and character.lower() not in {"auto", "none"}:
        parts.append(character_map.get(character, f"Mood/character direction: {character}."))

    objects = str(opts.get("objects") or opts.get("object") or "").strip()
    if objects:
        parts.append(f"Important objects/elements to include or preserve: {objects}.")

    refs = (
        opts.get("referenceImageUrls")
        or opts.get("reference_image_urls")
        or opts.get("referenceImages")
        or opts.get("images")
        or []
    )

    if isinstance(refs, str):
        refs = [refs]

    refs = [u for u in refs if isinstance(u, str) and u.strip()]

    if refs and not has_character:
        parts.append(
            "Use the uploaded reference images as visual references. "
            "If the user asks to merge/combine photos, combine the important visual elements from all uploaded reference images."
        )

    return "\n".join(parts).strip()

# =====================================================
# PYTHON-БЛОК: normalize_image_response
# Выполняет отдельный шаг backend-логики SYLVEX.
# Связан с API, базой данных, провайдерами или подготовкой данных для Mini App.
# =====================================================
def normalize_image_response(data: dict) -> list:
    images = []
    if not isinstance(data, dict):
        return images

    # =====================================================
    # PYTHON-БЛОК: add_image
    # Выполняет отдельный шаг backend-логики SYLVEX.
    # Связан с API, базой данных, провайдерами или подготовкой данных для Mini App.
    # =====================================================
    def add_image(value, mime_type="image/png"):
        if not isinstance(value, str) or not value.strip():
            return
        raw = value.strip()
        if raw.startswith("http") or raw.startswith("/") or raw.startswith("data:image/"):
            images.append(raw)
        else:
            images.append(f"data:{mime_type or 'image/png'};base64,{raw}")

    for item in data.get("data", []) if isinstance(data.get("data"), list) else []:
        if isinstance(item, dict):
            if item.get("url"):
                add_image(item["url"])
            elif item.get("b64_json"):
                add_image(item["b64_json"])

    # =====================================================
    # PYTHON-БЛОК: walk
    # Выполняет отдельный шаг backend-логики SYLVEX.
    # Связан с API, базой данных, провайдерами или подготовкой данных для Mini App.
    # =====================================================
    def walk(node):
        if isinstance(node, dict):
            mime_type = node.get("mime_type") or node.get("mimeType") or "image/png"
            for key in ("image", "url", "uri", "output_image", "image_url"):
                add_image(node.get(key), mime_type)
            inline = node.get("inlineData") or node.get("inline_data")
            if isinstance(inline, dict):
                add_image(inline.get("data"), inline.get("mimeType") or inline.get("mime_type") or mime_type)
            for key in ("b64_json", "data", "imageBytes", "bytesBase64Encoded"):
                value = node.get(key)
                if isinstance(value, str) and not value.strip().startswith("{"):
                    add_image(value, mime_type)
            for value in node.values():
                if isinstance(value, (dict, list)):
                    walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(data.get("output"))
    clean = []
    for image in images:
        if image and image not in clean:
            clean.append(image)
    return clean

# =====================================================
# PYTHON-БЛОК: safe_provider_json
# Выполняет отдельный шаг backend-логики SYLVEX.
# Связан с API, базой данных, провайдерами или подготовкой данных для Mini App.
# =====================================================
def safe_provider_json(response, provider: str, endpoint: str) -> dict:
    status = getattr(response, "status_code", None) or getattr(response, "status", None)
    try:
        text = response.text
        if callable(text):
            text = text()
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
# PYTHON-БЛОК: safe_image_count
# Выполняет отдельный шаг backend-логики SYLVEX.
# Связан с API, базой данных, провайдерами или подготовкой данных для Mini App.
# =====================================================
def safe_image_count(value, default: int = 1, max_count: int = 4) -> int:
    try:
        count = int(value or default)
    except Exception:
        count = default
    return max(1, min(count, max_count))


# =====================================================
# PYTHON-БЛОК: byteplus_seedream_body
# Выполняет отдельный шаг backend-логики SYLVEX.
# Связан с API, базой данных, провайдерами или подготовкой данных для Mini App.
# =====================================================
def byteplus_seedream_body(model: str, prompt: str, reference_images=None, size: str = "", seed=None) -> dict:
    body = {
        "model": model,
        "prompt": prompt,
        "response_format": "url",
        "size": seedream_size_value(size),
    }
    is_pro_model = "dola-seedream-5-0-pro" in str(model or "").lower()
    if not is_pro_model:
        body["sequential_image_generation"] = "disabled"
        body["stream"] = False
        body["watermark"] = False
    if seed is not None:
        body["seed"] = seed

    refs = []
    for index, value in enumerate(reference_images or []):
        if not isinstance(value, str) or not value.strip():
            continue
        provider_input = byteplus_image_input(value, index)
        if provider_input and provider_input not in refs:
            refs.append(provider_input)

    if refs:
        # Seedream accepts one URL or an ordered list of visual inputs. Keep the
        # source image first, followed by avatar + three character references.
        body["image"] = refs[0] if len(refs) == 1 else refs[:5]

    return body

# =====================================================
# PYTHON-БЛОК: request_byteplus_seedream_image
# Выполняет отдельный шаг backend-логики SYLVEX.
# Связан с API, базой данных, провайдерами или подготовкой данных для Mini App.
# =====================================================
def request_byteplus_seedream_image(model: str, prompt: str, reference_images=None, size: str = "", seed=None) -> tuple:
    refs = [u for u in (reference_images or []) if isinstance(u, str) and u.strip()]
    is_pro_model = "dola-seedream-5-0-pro" in str(model or "").lower()
    try:
        timeout_seconds = int(os.getenv("BYTEPLUS_SEEDREAM_PRO_TIMEOUT" if is_pro_model else "BYTEPLUS_SEEDREAM_TIMEOUT") or (420 if is_pro_model else 240))
    except Exception:
        timeout_seconds = 420 if is_pro_model else 240

    # =====================================================
    # PYTHON-БЛОК: _send
    # Выполняет отдельный шаг backend-логики SYLVEX.
    # Связан с API, базой данных, провайдерами или подготовкой данных для Mini App.
    # =====================================================
    def _send(include_refs: bool):
        request_payload = byteplus_seedream_body(model, prompt, refs if include_refs else [], size=size, seed=seed)
        print("BYTEPLUS IMAGE PAYLOAD:", {k: v for k, v in request_payload.items() if k != "image"})
        print("BYTEPLUS IMAGE TIMEOUT:", timeout_seconds)
        return requests.post(
            f"{BYTEPLUS_ARK_ENDPOINT}/images/generations",
            headers={
                "Authorization": f"Bearer {BYTEPLUS_ARK_API_KEY}",
                "Content-Type": "application/json",
            },
            data=json.dumps(request_payload),
            timeout=timeout_seconds,
        )

    try:
        response = _send(bool(refs))
    except requests.ReadTimeout:
        print("BYTEPLUS IMAGE TIMEOUT, RETRY ONCE WITH THE SAME REFERENCES")
        try:
            response = _send(bool(refs))
        except Exception as exc:
            return [], type(exc).__name__
    except Exception as exc:
        return [], type(exc).__name__

    if response.status_code >= 400:
        return [], f"HTTP {response.status_code}: {response.text[:500]}"

    data = safe_provider_json(response, "bytedance", f"{BYTEPLUS_ARK_ENDPOINT}/images/generations")
    if data.get("ok") is False:
        return [], data.get("error") or "invalid provider response"
    images = normalize_image_response(data)

    if not images:
        return [], "no image returned"

    return images, ""


# =====================================================
# СИНХРОНИЗАЦИЯ С TELEGRAM: send_generated_images_to_telegram
# Отправляет готовый результат или статус в Telegram Bot и сохраняет признак отправки в metadata карточки.
# =====================================================
async def send_generated_images_to_telegram(telegram_id: int, images: list, caption: str = "") -> bool:
    if not BOT_TOKEN or not telegram_id or not images:
        return False

    ok = False

    for index, image in enumerate(images):
        if not image:
            continue

        current_caption = caption if index == 0 else ""

        try:
            image_value = str(image or "").strip()

            is_base64_image = image_value.startswith("data:image") or (
                len(image_value) > 4000 and not image_value.startswith("http")
            )
            is_http_url = image_value.startswith("http://") or image_value.startswith("https://")

            print("TELEGRAM SEND PHOTO:", {
                "telegram_id": telegram_id,
                "is_base64": is_base64_image,
                "is_url": is_http_url,
                "image_length": len(image_value),
            })

            # 1. Base64 / data:image
            if is_base64_image:
                raw = image_value

                if "," in raw:
                    raw = raw.split(",", 1)[1]

                raw = raw.strip()
                image_bytes = base64.b64decode(raw)

                response = requests.post(
                    f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto",
                    data={
                        "chat_id": telegram_id,
                        "caption": current_caption,
                    },
                    files={
                        "photo": ("sylvex-image.png", image_bytes, "image/png"),
                    },
                    timeout=120,
                )

            # 2. URL — сначала скачиваем сами, потом отправляем как файл
            elif is_http_url:
                download_response = requests.get(
                    image_value,
                    timeout=120,
                    headers={
                        "User-Agent": "Mozilla/5.0",
                    },
                )

                print("TELEGRAM PHOTO URL DOWNLOAD:", {
                    "status_code": download_response.status_code,
                    "content_type": download_response.headers.get("content-type"),
                    "bytes": len(download_response.content or b""),
                })

                if download_response.status_code >= 400 or not download_response.content:
                    response = requests.post(
                        f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto",
                        json={
                            "chat_id": telegram_id,
                            "photo": image_value,
                            "caption": current_caption,
                        },
                        timeout=120,
                    )
                else:
                    content_type = download_response.headers.get("content-type") or "image/png"
                    file_name = "sylvex-image.png"

                    if "jpeg" in content_type or "jpg" in content_type:
                        file_name = "sylvex-image.jpg"
                    elif "webp" in content_type:
                        file_name = "sylvex-image.webp"

                    response = requests.post(
                        f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto",
                        data={
                            "chat_id": telegram_id,
                            "caption": current_caption,
                        },
                        files={
                            "photo": (file_name, download_response.content, content_type),
                        },
                        timeout=120,
                    )

            # 3. Остальное — пробуем как обычное значение
            else:
                response = requests.post(
                    f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto",
                    json={
                        "chat_id": telegram_id,
                        "photo": image_value,
                        "caption": current_caption,
                    },
                    timeout=120,
                )

            if response.status_code >= 400:
                print("TELEGRAM SEND PHOTO ERROR:", response.text[:1000])
            else:
                data = response.json()
                print("TELEGRAM SEND PHOTO RESULT:", data)
                ok = ok or bool(data.get("ok"))

        except Exception as exc:
            print("TELEGRAM SEND PHOTO ERROR:", str(exc))

    return ok

# =====================================================
# PYTHON-БЛОК: generateBytePlusSeedreamImage
# Выполняет отдельный шаг backend-логики SYLVEX.
# Связан с API, базой данных, провайдерами или подготовкой данных для Mini App.
# =====================================================
async def generateBytePlusSeedreamImage(payload: dict) -> dict:
    if not BYTEPLUS_ARK_API_KEY:
        return {"ok": False, "error": "Генерация не прошла. Проверь выбранную модель или backend-провайдер."}

    opts = payload.get("image_options") or {}
    requested_model = (
        opts.get("modelId")
        or opts.get("model_id")
        or payload.get("model")
        or "seedream_5_0"
    )
    model_cfg = find_image_model(requested_model) if requested_model else {}
    model = model_cfg.get("api_model") or map_image_model_to_provider_model(requested_model)
    if not model:
        return unknown_byteplus_image_model_response(requested_model)
    prompt = build_image_prompt(payload)
    size = opts.get("size") or opts.get("ratio") or (model_cfg.get("sizes") or [{}])[0].get("id") or "auto"
    count = safe_image_count(opts.get("count") or 1, default=1, max_count=4)
    seed_supported = bool((SEEDREAM_MODEL_VARIANTS.get(seedream_frontend_model(requested_model, model)) or {}).get("seed"))
    seed = normalize_image_seed(opts.get("seed")) if seed_supported else None

    reference_images = []

    for value in (
        opts.get("referenceImageUrls"),
        opts.get("reference_image_urls"),
        opts.get("referenceImages"),
        opts.get("images"),
        opts.get("characterReferences"),
        opts.get("objectReferences"),
    ):
        if isinstance(value, str):
            reference_images.append(value)
        elif isinstance(value, list):
            reference_images.extend(value)

    clean_refs = []
    for url in reference_images:
        if isinstance(url, str) and url.strip() and url not in clean_refs:
            clean_refs.append(url)

    reference_images = clean_refs

    print("BYTEPLUS IMAGE REFERENCES:", {
        "count": len(reference_images),
        "inline": sum(1 for value in reference_images if str(value).startswith("data:image/")),
        "urls": sum(1 for value in reference_images if str(value).startswith(("http://", "https://"))),
    })

    images = []
    # The public /images/generations examples use a single-output request body.
    # Until BytePlus confirms a count field for this endpoint, multiple images are
    # generated by repeated safe calls and normalized into the frontend format.
    for index in range(1, count + 1):
        print(f"BYTEPLUS IMAGE REQUEST {index}/{count}")
        request_images, error = request_byteplus_seedream_image(model, prompt, reference_images, size=size, seed=seed)
        if request_images:
            for url in request_images:
                if url and url not in images:
                    images.append(url)
            print(f"BYTEPLUS IMAGE SUCCESS {index}/{count}")
        else:
            print(f"BYTEPLUS IMAGE FAILED {index}/{count} {error or 'unknown error'}")

        if len(images) >= count:
            break

    if not images:
        return {"ok": False, "error": "Генерация не прошла. Проверь выбранную модель или backend-провайдер."}

    images = images[:count]
    result = attach_image_thumbnails({
        "ok": True,
        "type": "image",
        "image_url": images[0],
        "images": images,
        "provider": "bytedance",
        "model": requested_model,
        "provider_model": model,
        **seedream_cost_info(requested_model, model, len(images)),
    })

    telegram_id = int(payload.get("telegram_id") or 0)
    sent_to_telegram = False
    if telegram_id and not payload.get("skip_telegram"):
        try:
            sent_to_telegram = await send_generated_images_to_telegram(
                telegram_id=telegram_id,
                images=images,
                caption="Готово ✅\nСгенерировано в SYLVEX Pro Studio",
            )
        except Exception as exc:
            print("TELEGRAM SEND GENERATED IMAGES FAILED:", str(exc))

    result["sent_to_telegram"] = sent_to_telegram
    return result

# =====================================================
# ТЕКСТОВАЯ ГЕНЕРАЦИЯ: модели, транскрибация и PDF
# =====================================================
TEXT_MODEL_ALIASES = {
    "gpt-5.6": "gpt-5.6",
    "gpt-5.5": "gpt-5.5",
    "gpt-5": "gpt-5",
    "gpt-5-mini": "gpt-5-mini",
    "gpt-4.1": "gpt-4.1",
    "gpt-4.1-mini": "gpt-4.1-mini",
    "gpt-4o": "gpt-4o",
    "gpt-4o-mini": "gpt-4o-mini",
    "gemini_3_1_pro": "gemini_3_1_pro",
    "gemini_3_1_flash": "gemini_3_1_flash",
    "gemini_2_5_pro": "gemini_2_5_pro",
    "gemini_2_5_flash": "gemini_2_5_flash",
    "grok_4_1": "grok_4_1",
    "grok_4_fast": "grok_4_fast",
    "grok_3": "grok_3",
    "qwen_plus": "qwen_plus",
    "qwen_turbo": "qwen_turbo",
    "qwen_max": "qwen_max",
    "byteplus_seed_2_lite": "byteplus_seed_2_lite",
}

TEXT_MODEL_VARIANTS = {
    "gpt-5.6": {"provider": "openai", "provider_model": env_value("OPENAI_TEXT_GPT56_MODEL", default="gpt-5.6"), "api": "responses"},
    "gpt-5.5": {"provider": "openai", "provider_model": env_value("OPENAI_TEXT_GPT55_MODEL", default="gpt-5.5"), "api": "responses"},
    "gpt-5": {"provider": "openai", "provider_model": env_value("OPENAI_TEXT_GPT5_MODEL", default="gpt-5")},
    "gpt-5-mini": {"provider": "openai", "provider_model": env_value("OPENAI_TEXT_GPT5_MINI_MODEL", default="gpt-5-mini")},
    "gpt-4.1": {"provider": "openai", "provider_model": env_value("OPENAI_TEXT_GPT41_MODEL", default="gpt-4.1")},
    "gpt-4.1-mini": {"provider": "openai", "provider_model": env_value("OPENAI_TEXT_GPT41_MINI_MODEL", default="gpt-4.1-mini")},
    "gpt-4o": {"provider": "openai", "provider_model": env_value("OPENAI_TEXT_GPT4O_MODEL", default="gpt-4o")},
    "gpt-4o-mini": {"provider": "openai", "provider_model": env_value("OPENAI_TEXT_GPT4O_MINI_MODEL", default="gpt-4o-mini")},
    "gemini_3_1_pro": {"provider": "gemini", "provider_model": env_value("GEMINI_TEXT_PRO_MODEL", "GEMINI-TEXT-PRO-MODEL", default="gemini-3.1-pro")},
    "gemini_3_1_flash": {"provider": "gemini", "provider_model": env_value("GEMINI_TEXT_FLASH_MODEL", "GEMINI-TEXT-FLASH-MODEL", default="gemini-3.1-flash")},
    "gemini_2_5_pro": {"provider": "gemini", "provider_model": env_value("GEMINI_TEXT_25_PRO_MODEL", "GEMINI-TEXT-25-PRO-MODEL", default="gemini-2.5-pro")},
    "gemini_2_5_flash": {"provider": "gemini", "provider_model": env_value("GEMINI_TEXT_25_FLASH_MODEL", "GEMINI-TEXT-25-FLASH-MODEL", default="gemini-2.5-flash")},
    "grok_4_1": {"provider": "grok", "provider_model": env_value("GROK_TEXT_4_1_MODEL", "XAI_TEXT_4_1_MODEL", default="grok-4.1")},
    "grok_4_fast": {"provider": "grok", "provider_model": env_value("GROK_TEXT_FAST_MODEL", "XAI_TEXT_FAST_MODEL", default="grok-4-fast-reasoning")},
    "grok_3": {"provider": "grok", "provider_model": env_value("GROK_TEXT_3_MODEL", "XAI_TEXT_3_MODEL", default="grok-3")},
    "qwen_plus": {"provider": "qwen", "provider_model": env_value("QWEN_TEXT_PLUS_MODEL", "QWEN-TEXT-PLUS-MODEL", default="qwen-plus")},
    "qwen_turbo": {"provider": "qwen", "provider_model": env_value("QWEN_TEXT_TURBO_MODEL", "QWEN-TEXT-TURBO-MODEL", default="qwen-turbo")},
    "qwen_max": {"provider": "qwen", "provider_model": env_value("QWEN_TEXT_MAX_MODEL", "QWEN-TEXT-MAX-MODEL", default="qwen-max")},
    "byteplus_seed_2_lite": {"provider": "byteplus", "provider_model": env_value("BYTEPLUS_TEXT_SEED_2_LITE_MODEL", "ARK_TEXT_MODEL", default="seed-2-0-lite-260228")},
}


def normalize_text_model(model: str) -> str:
    raw = str(model or "").strip()
    if is_internal_ui_model(raw) or raw in {"gpt-image-1", "gpt_image_1", "gpt-image-2", "gpt_image_2"}:
        return "gpt-5.5"
    return TEXT_MODEL_ALIASES.get(raw, raw or "gpt-5.5")


def _text_attachment_bytes(attachment: dict) -> tuple[bytes, str, str]:
    if not isinstance(attachment, dict):
        return b"", "attachment", "application/octet-stream"
    name = pathlib.Path(str(attachment.get("name") or "attachment")).name
    mime = str(attachment.get("mime") or attachment.get("content_type") or "application/octet-stream")
    data_base64 = str(attachment.get("dataBase64") or attachment.get("data_base64") or "")
    if data_base64:
        try:
            return base64.b64decode(data_base64), name, mime
        except Exception:
            return b"", name, mime
    url = str(attachment.get("url") or attachment.get("path") or "").strip()
    if not url:
        return b"", name, mime
    try:
        parsed_path = urllib.parse.urlparse(url).path if url.startswith(("http://", "https://")) else url
        if storage_key_from_url(url):
            return storage_read_bytes(url), name, mime
        if parsed_path.startswith("/webapp/"):
            local_path = WEBAPP_DIR / parsed_path.replace("/webapp/", "", 1)
            return local_path.read_bytes(), name or local_path.name, mime
        if parsed_path.startswith("/generated/"):
            local_path = WEBAPP_DIR / parsed_path.replace("/generated/", "generated/", 1)
            return local_path.read_bytes(), name or local_path.name, mime
        response = requests.get(url, timeout=120)
        response.raise_for_status()
        return response.content, name, (response.headers.get("content-type") or mime)
    except Exception as exc:
        print("TEXT ATTACHMENT LOAD FAILED:", repr(exc))
        return b"", name, mime


def text_attachment_plain_text(attachment: dict) -> str:
    content, filename, content_type = _text_attachment_bytes(attachment)
    if not content:
        return ""
    suffix = pathlib.Path(filename or "").suffix.lower()
    mime = (content_type or "").split(";", 1)[0].strip().lower()
    if suffix not in {".txt", ".md", ".json", ".csv"} and mime not in {"text/plain", "text/markdown", "application/json", "text/csv"}:
        return ""
    for encoding in ("utf-8", "utf-16", "cp1251"):
        try:
            text = content.decode(encoding).strip()
            return text[:60000]
        except Exception:
            continue
    return ""


def text_attachment_data_url(attachment: dict) -> str:
    if not isinstance(attachment, dict):
        return ""
    mime = str(attachment.get("mime") or attachment.get("content_type") or "").split(";", 1)[0].strip().lower()
    if not mime.startswith("image/"):
        return ""
    content, _filename, content_type = _text_attachment_bytes(attachment)
    if not content:
        return ""
    mime = (content_type or mime or "image/png").split(";", 1)[0].strip().lower()
    if not mime.startswith("image/"):
        mime = "image/png"
    return "data:" + mime + ";base64," + base64.b64encode(content).decode("utf-8")


def text_attachment_gemini_media_part(attachment: dict) -> dict:
    if not isinstance(attachment, dict):
        return {}
    mime = str(attachment.get("mime") or attachment.get("content_type") or "").split(";", 1)[0].strip().lower()
    media_type = "video" if mime.startswith("video/") else ("audio" if mime.startswith("audio/") else "")
    if not media_type:
        return {}
    url = str(attachment.get("url") or "").strip()
    if not url:
        return {}
    api_key = env_value("GEMINI_API_KEY", "GEMINI-API-KEY", "GOOGLE_API_KEY", "GOOGLE-API-KEY")
    if not api_key:
        return {}
    part = _gemini_upload_file_from_url(url, api_key, media_type)
    if not isinstance(part, dict) or not part.get("uri"):
        return {}
    return {
        "file_data": {
            "mime_type": part.get("mime_type") or mime or "video/mp4",
            "file_uri": part.get("uri"),
        }
    }


def with_text_media_attachment(messages: list, attachment: dict, provider: str) -> list:
    data_url = text_attachment_data_url(attachment)
    gemini_media_part = text_attachment_gemini_media_part(attachment) if provider == "gemini" else {}
    if provider not in {"openai", "gemini", "grok"} or (not data_url and not gemini_media_part):
        return messages
    patched = list(messages or [])
    for index in range(len(patched) - 1, -1, -1):
        item = patched[index]
        if item.get("role") != "user":
            continue
        content = str(item.get("content") or "")
        content_parts = [{"type": "text", "text": content}]
        if data_url:
            content_parts.append({"type": "image_url", "image_url": {"url": data_url}})
        if gemini_media_part:
            content_parts.append({"type": "gemini_file", "part": gemini_media_part})
        patched[index] = {
            "role": "user",
            "content": content_parts,
        }
        break
    return patched


def openai_transcribe_bytes(content: bytes, filename: str, content_type: str, language: str = "") -> tuple[bool, str]:
    if not content:
        return False, "Файл пустой или недоступен"
    if not OPENAI_API_KEY:
        return False, "OPENAI_API_KEY is not configured"
    data = {"model": os.getenv("OPENAI_TRANSCRIBE_MODEL", "whisper-1")}
    if language and language not in {"auto", "ru", "en"}:
        data["language"] = language
    elif language in {"ru", "en"}:
        data["language"] = language
    try:
        response = requests.post(
            f"{OPENAI_API_BASE}/audio/transcriptions",
            headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
            files={"file": (filename or "speech.webm", content, content_type or "audio/webm")},
            data=data,
            timeout=180,
        )
    except requests.RequestException as exc:
        return False, f"OpenAI transcription request failed: {type(exc).__name__}"
    if response.status_code >= 400:
        return False, f"OpenAI transcription failed (status={response.status_code}): {response.text[:1200]}"
    try:
        text = str(response.json().get("text") or "").strip()
    except (TypeError, ValueError):
        return False, "OpenAI transcription returned an invalid response"
    return (True, text) if text else (False, "OpenAI transcription returned empty text")


def gemini_transcribe_bytes(content: bytes, content_type: str, language: str = "") -> tuple[bool, str]:
    """Fallback speech recognition when the primary OpenAI endpoint is unavailable."""
    api_key = env_value("GEMINI_API_KEY", "GEMINI-API-KEY", "GOOGLE_API_KEY", "GOOGLE-API-KEY")
    if not api_key:
        return False, "GEMINI_API_KEY is not configured"
    mime = (content_type or "audio/webm").split(";", 1)[0].strip().lower()
    if not mime.startswith("audio/"):
        mime = "audio/webm"
    language_hint = ""
    if language in {"ru", "en"}:
        language_hint = f" The expected language is {'Russian' if language == 'ru' else 'English'}."
    model = env_value("GEMINI_TRANSCRIBE_MODEL", default="gemini-2.5-flash")
    endpoint_base = env_value(
        "GEMINI_TEXT_ENDPOINT",
        "GEMINI-GENERATE-CONTENT-ENDPOINT",
        default="https://generativelanguage.googleapis.com/v1beta/models",
    ).rstrip("/")
    payload = {
        "contents": [{
            "role": "user",
            "parts": [
                {"text": "Transcribe this voice recording exactly. Return only the transcript, without comments or formatting." + language_hint},
                {"inline_data": {"mime_type": mime, "data": base64.b64encode(content).decode("ascii")}},
            ],
        }],
        "generationConfig": {"temperature": 0},
    }
    try:
        response = requests.post(
            f"{endpoint_base}/{model}:generateContent",
            headers={"x-goog-api-key": api_key, "Content-Type": "application/json"},
            data=json.dumps(payload),
            timeout=180,
        )
    except requests.RequestException as exc:
        return False, f"Gemini transcription request failed: {type(exc).__name__}"
    try:
        data = response.json() if response.content else {}
    except ValueError:
        data = {}
    if response.status_code >= 400:
        return False, f"Gemini transcription failed (status={response.status_code}): {(raw_error_text(data) or response.text)[:1200]}"
    text = "\n".join(
        str(part.get("text") or "")
        for candidate in data.get("candidates") or [] if isinstance(candidate, dict)
        for part in ((candidate.get("content") or {}).get("parts") or [])
        if isinstance(part, dict) and part.get("text")
    ).strip()
    return (True, text) if text else (False, "Gemini transcription returned empty text")


def text_media_transcript(payload: dict, attachment: dict, tool: str) -> tuple[str, str]:
    if tool not in {"audio_to_text", "video_to_text", "video_prompt", "structured_dialogue", "translate", "summarize", "extract", "text", "document", "prompt", "rewrite"}:
        return "", ""
    if not isinstance(attachment, dict):
        return "", "Для транскрибации нужно загрузить аудио или видео."
    mime = str(attachment.get("mime") or attachment.get("content_type") or "").lower()
    url = str(attachment.get("url") or "").strip()
    language = str((payload.get("text_options") or {}).get("language") or payload.get("language") or "auto").lower()

    if tool == "video_to_text" or mime.startswith("video/"):
        if url:
            audio_bytes, filename, content_type, extract_error = _extract_audio_from_video_for_dubbing(url)
            if extract_error:
                return "", "Не удалось извлечь аудио из видео: " + extract_error
            ok, text = openai_transcribe_bytes(audio_bytes, filename, content_type, language)
            return (text, "") if ok else ("", text)
        return "", "Для видео-в-текст нужен загруженный видеофайл."

    content, filename, content_type = _text_attachment_bytes(attachment)
    ok, text = openai_transcribe_bytes(content, filename, content_type, language)
    return (text, "") if ok else ("", text)


def save_text_pdf(text: str, title: str = "SYLVEX Text") -> str:
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer
        from reportlab.lib.units import mm
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
        from xml.sax.saxutils import escape

        filename = f"{uuid4().hex}.pdf"
        temp = tempfile.NamedTemporaryFile(prefix="sylvex-document-", suffix=".pdf", delete=False)
        path = pathlib.Path(temp.name)
        temp.close()
        doc = SimpleDocTemplate(str(path), pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=16 * mm, bottomMargin=16 * mm)
        styles = getSampleStyleSheet()
        font_name = "Helvetica"
        for font_path in (
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
            "/System/Library/Fonts/Supplemental/Arial.ttf",
        ):
            if pathlib.Path(font_path).exists():
                try:
                    pdfmetrics.registerFont(TTFont("SYLVEXUnicode", font_path))
                    font_name = "SYLVEXUnicode"
                    break
                except Exception:
                    pass
        for style_obj in styles.byName.values():
            style_obj.fontName = font_name
        story = [Paragraph(escape(title or "SYLVEX Text"), styles["Title"]), Spacer(1, 8)]
        for block in str(text or "").split("\n"):
            story.append(Paragraph(escape(block) if block.strip() else "&nbsp;", styles["BodyText"]))
            story.append(Spacer(1, 4))
        doc.build(story)
        return storage_put_file(path, generated_key("documents", filename), "application/pdf", remove_local=True)
    except Exception as exc:
        print("TEXT PDF SAVE FAILED:", repr(exc))
        return ""


def text_system_prompt(tool: str, style: str, output_format: str) -> str:
    tool_notes = {
        "text": "Generate high-quality text for the user's task.",
        "document": "Create a structured document with clear sections, headings, and final actionable content.",
        "prompt": "Create production-ready AI prompts with role, goal, context, constraints, output format, and examples when useful.",
        "structured_dialogue": "Turn the source into a structured dialogue: speakers, timestamps or scenes when available, key points, and clean readable lines.",
        "translate": "Translate the supplied text or extracted media/document content. Preserve formatting and meaning, and state the detected source language when helpful.",
        "summarize": "Create a concise structured summary with key points, decisions, action items, and important quotes when present.",
        "rewrite": "Rewrite and improve the supplied content while preserving intent. Make it clearer, cleaner, and ready to publish.",
        "extract": "Extract readable text, facts, entities, tasks, dates, tables, and useful structured information from the supplied content.",
        "image_prompt": "Analyze the supplied image and create a detailed production-ready prompt. Include subject, style, composition, lighting, camera, mood, details, and negative prompt when useful.",
        "video_prompt": "Analyze the supplied video visually and create a detailed production-ready prompt. Describe subject, scenes, motion, camera, composition, lighting, mood, style, timing, transitions, and negative prompt when useful. If transcript is available, use it as extra context without replacing the visual analysis.",
        "audio_to_text": "Transcribe and clean audio into accurate text. Preserve meaning and structure.",
        "video_to_text": "Transcribe video speech and structure it as scenes, dialogue, summary, and action points.",
    }
    style_notes = {
        "neutral": "Use a neutral professional tone.",
        "business": "Use a business-ready concise tone.",
        "creative": "Use a vivid creative tone.",
        "technical": "Use a precise technical tone.",
        "telegram": "Use a compact Telegram-friendly tone.",
    }
    format_note = "If PDF is selected, still return clean Markdown text; the backend will also create a PDF file."
    return (
        "You are SYLVEX Pro Studio Text AI inside a Telegram Mini App. "
        + tool_notes.get(tool, tool_notes["text"]) + " "
        + style_notes.get(style, style_notes["neutral"]) + " "
        + format_note
        + " Always answer in the user's language unless they request another language."
    )


def quick_text_reply(prompt: str, attachment: dict, history: list, tool: str, output_format: str) -> str:
    if attachment or history or tool not in {"text", ""} or output_format == "pdf":
        return ""
    value = re.sub(r"\s+", " ", str(prompt or "").strip().lower())
    greetings = {
        "привет", "здравствуй", "здравствуйте", "салам", "ассаламу алейкум",
        "hello", "hi", "hey", "добрый день", "добрый вечер", "доброе утро",
    }
    if value in greetings:
        return "Привет! Чем помочь?"
    return ""


def openai_compatible_text_request(provider: str, endpoint_base: str, api_key: str, provider_model: str, messages: list, extra_body: Optional[dict] = None) -> tuple[bool, str, dict]:
    if not api_key:
        return False, f"{provider.upper()} API key is not configured", {}
    endpoint = endpoint_base.rstrip("/") + "/chat/completions"
    response = requests.post(
        endpoint,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        data=json.dumps({"model": provider_model, "messages": messages, **(extra_body or {})}),
        timeout=45,
    )
    try:
        data = response.json() if response.content else {}
    except Exception:
        data = {"raw": response.text}
    if response.status_code >= 400:
        return False, raw_error_text(data) or response.text, data if isinstance(data, dict) else {}
    text = ""
    if isinstance(data, dict):
        text = data.get("choices", [{}])[0].get("message", {}).get("content", "")
    return True, text, data if isinstance(data, dict) else {}


def openai_responses_text_request(provider_model: str, messages: list) -> tuple[bool, str, dict]:
    if not OPENAI_API_KEY:
        return False, "OPENAI API key is not configured", {}
    response_input = []
    for message in messages or []:
        role = str(message.get("role") or "user")
        raw_content = message.get("content")
        if isinstance(raw_content, list):
            content = []
            for part in raw_content:
                if not isinstance(part, dict):
                    continue
                if part.get("type") == "text":
                    content.append({"type": "input_text", "text": str(part.get("text") or "")})
                elif part.get("type") == "image_url":
                    image_url = (part.get("image_url") or {}).get("url")
                    if image_url:
                        content.append({"type": "input_image", "image_url": image_url})
        else:
            content = [{"type": "input_text", "text": str(raw_content or "")}]
        response_input.append({"role": role, "content": content})
    response = requests.post(
        OPENAI_API_BASE.rstrip("/") + "/responses",
        headers={"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"},
        data=json.dumps({"model": provider_model, "input": response_input}),
        timeout=90,
    )
    try:
        data = response.json() if response.content else {}
    except Exception:
        data = {"raw": response.text}
    if response.status_code >= 400:
        return False, raw_error_text(data) or response.text, data if isinstance(data, dict) else {}
    text = str(data.get("output_text") or "") if isinstance(data, dict) else ""
    if not text and isinstance(data, dict):
        text = "\n".join(
            str(part.get("text") or "")
            for output in data.get("output") or [] if isinstance(output, dict)
            for part in output.get("content") or [] if isinstance(part, dict) and part.get("type") == "output_text"
        ).strip()
    return True, text, data if isinstance(data, dict) else {}


def gemini_text_request(provider_model: str, messages: list) -> tuple[bool, str, dict]:
    api_key = env_value("GEMINI_API_KEY", "GEMINI-API-KEY", "GOOGLE_API_KEY", "GOOGLE-API-KEY")
    if not api_key:
        return False, "GEMINI_API_KEY is not configured", {}
    system_text = "\n\n".join(str(item.get("content") or "") for item in messages if item.get("role") == "system")
    contents = []
    for item in messages:
        role = item.get("role")
        if role == "system":
            continue
        raw_content = item.get("content")
        parts = []
        if isinstance(raw_content, list):
            for part in raw_content:
                if not isinstance(part, dict):
                    continue
                if part.get("type") == "text":
                    parts.append({"text": str(part.get("text") or "")})
                elif part.get("type") == "image_url":
                    image_url = ((part.get("image_url") or {}).get("url") or "")
                    if image_url.startswith("data:image/") and ";base64," in image_url:
                        head, data = image_url.split(";base64,", 1)
                        parts.append({"inline_data": {"mime_type": head.replace("data:", "") or "image/png", "data": data}})
                elif part.get("type") == "gemini_file":
                    gemini_part = part.get("part")
                    if isinstance(gemini_part, dict):
                        parts.append(gemini_part)
        else:
            parts = [{"text": str(raw_content or "")}]
        contents.append({
            "role": "model" if role == "assistant" else "user",
            "parts": parts or [{"text": ""}],
        })
    endpoint_base = env_value("GEMINI_TEXT_ENDPOINT", "GEMINI-GENERATE-CONTENT-ENDPOINT", default="https://generativelanguage.googleapis.com/v1beta/models").rstrip("/")
    endpoint = f"{endpoint_base}/{provider_model}:generateContent"
    request_payload = {"contents": contents}
    if system_text:
        request_payload["systemInstruction"] = {"parts": [{"text": system_text}]}
    response = requests.post(
        endpoint,
        headers={"x-goog-api-key": api_key, "Content-Type": "application/json"},
        data=json.dumps(request_payload),
        timeout=45,
    )
    try:
        data = response.json() if response.content else {}
    except Exception:
        data = {"raw": response.text}
    if response.status_code >= 400:
        return False, raw_error_text(data) or response.text, data if isinstance(data, dict) else {}
    text_parts = []
    for candidate in (data.get("candidates") or []) if isinstance(data, dict) else []:
        for part in ((candidate.get("content") or {}).get("parts") or []):
            if isinstance(part, dict) and part.get("text"):
                text_parts.append(str(part.get("text")))
    return True, "\n".join(text_parts).strip(), data if isinstance(data, dict) else {}


def call_text_provider(model: str, messages: list, attachment: Optional[dict] = None) -> dict:
    cfg = TEXT_MODEL_VARIANTS.get(model) or TEXT_MODEL_VARIANTS["gpt-5.5"]
    provider = cfg.get("provider") or "openai"
    provider_model = cfg.get("provider_model") or model
    request_messages = with_text_media_attachment(messages, attachment or {}, provider)
    if provider == "gemini":
        ok, text, data = gemini_text_request(provider_model, request_messages)
    elif provider in {"grok", "xai"}:
        api_key = env_value("XAI_API_KEY", "XAI-API-KEY", "GROK_API_KEY", "GROK-API-KEY")
        endpoint_base = env_value("XAI_API_BASE", "GROK_API_BASE", default="https://api.x.ai/v1")
        ok, text, data = openai_compatible_text_request("grok", endpoint_base, api_key, provider_model, request_messages)
        provider = "grok"
    elif provider == "qwen":
        api_key = env_value("DASHSCOPE_API_KEY", "DASHSCOPE-API-KEY", "QWEN_API_KEY", "QWEN-API-KEY")
        endpoint_base = env_value("QWEN_TEXT_API_BASE", "DASHSCOPE_COMPATIBLE_API_BASE", default="https://dashscope-intl.aliyuncs.com/compatible-mode/v1")
        ok, text, data = openai_compatible_text_request("qwen", endpoint_base, api_key, provider_model, request_messages)
    elif provider == "byteplus":
        endpoint_base = BYTEPLUS_ARK_ENDPOINT
        ok, text, data = openai_compatible_text_request("byteplus", endpoint_base, BYTEPLUS_ARK_API_KEY, provider_model, messages, {"thinking": {"type": "disabled"}})
    else:
        if cfg.get("api") == "responses":
            ok, text, data = openai_responses_text_request(provider_model, request_messages)
        else:
            ok, text, data = openai_compatible_text_request("openai", OPENAI_API_BASE, OPENAI_API_KEY, provider_model, request_messages)
        provider = "openai"
    if not ok:
        return {"ok": False, "error": text, "provider": provider, "model": model, "provider_model": provider_model, "metadata": data}
    return {"ok": True, "text": text, "provider": provider, "model": model, "provider_model": provider_model, "metadata": data}


# =====================================================
# PYTHON-БЛОК: text_generation
# Выполняет отдельный шаг backend-логики SYLVEX.
# Связан с API, базой данных, провайдерами или подготовкой данных для Mini App.
# =====================================================
def text_generation(payload: dict) -> dict:
    prompt = (payload.get("prompt") or "").strip()
    history = payload.get("history") or []
    mode = payload.get("mode") or "text"
    model = normalize_text_model(payload.get("model") or "gpt-5.5")
    attachment = payload.get("attachment") or {}
    text_options = payload.get("text_options") or {}
    if not isinstance(text_options, dict):
        text_options = {}
    tool = str(text_options.get("tool") or "text").strip().lower()
    style = str(text_options.get("style") or "neutral").strip().lower()
    output_format = str(text_options.get("format") or "markdown").strip().lower()
    model_cfg = TEXT_MODEL_VARIANTS.get(model) or TEXT_MODEL_VARIANTS["gpt-5.5"]
    model_provider = model_cfg.get("provider") or "openai"
    attachment_mime = str((attachment or {}).get("mime") or (attachment or {}).get("content_type") or "").lower()
    gemini_media_tools = {"video_prompt", "audio_to_text", "video_to_text"}
    if tool in gemini_media_tools and model_provider != "gemini":
        return {"ok": False, "error": "Этот медиа-инструмент доступен только для моделей Gemini.", "model": model, "tool": tool}
    if tool == "video_prompt" and not attachment_mime.startswith("video/"):
        return {"ok": False, "error": "Для создания промта загрузите поддерживаемый видеофайл."}
    if tool == "video_to_text" and not attachment_mime.startswith("video/"):
        return {"ok": False, "error": "Для извлечения текста загрузите поддерживаемый видеофайл."}
    if tool == "audio_to_text" and not attachment_mime.startswith("audio/"):
        return {"ok": False, "error": "Для извлечения текста загрузите поддерживаемый аудиофайл."}

    quick_reply = quick_text_reply(prompt, attachment, history, tool, output_format)
    if quick_reply:
        return {
            "ok": True,
            "type": "text",
            "text": quick_reply,
            "provider": "sylvex-fast",
            "model": "instant-reply",
            "tool": tool,
            "format": output_format,
        }

    transcript = ""
    transcript_error = ""
    direct_gemini_media = model_provider == "gemini" and (
        (tool in {"video_prompt", "video_to_text"} and attachment_mime.startswith("video/"))
        or (tool == "audio_to_text" and attachment_mime.startswith("audio/"))
    )
    should_transcribe_media = bool(attachment) and (
        tool in {"audio_to_text", "video_to_text", "structured_dialogue", "translate", "summarize", "extract"}
        or attachment_mime.startswith("audio/")
        or attachment_mime.startswith("video/")
    ) and not direct_gemini_media
    if should_transcribe_media and attachment_mime.startswith(("audio/", "video/")):
        transcript, transcript_error = text_media_transcript(payload, attachment, tool)
        if transcript_error:
            return {"ok": False, "error": transcript_error}
        prompt = (prompt + "\n\n" if prompt else "") + "Source transcript:\n" + transcript
    elif direct_gemini_media:
        if tool == "video_prompt":
            media_instruction = "Analyze the attached video itself and generate a production-ready prompt from its visible scenes, motion, camera, style, lighting, sound, and pacing."
        elif tool == "video_to_text":
            media_instruction = "Analyze the attached video's visual and audio streams. Return an accurate transcript plus scenes, visible actions, speakers, and timestamps when possible."
        else:
            media_instruction = "Analyze the attached audio or music file. Transcribe all intelligible speech or lyrics and identify speakers, timestamps, language, and important non-speech or musical sections when possible."
        prompt = (prompt + "\n\n" if prompt else "") + media_instruction
    elif attachment:
        attachment_text = text_attachment_plain_text(attachment)
        if attachment_text:
            prompt = (prompt + "\n\n" if prompt else "") + "Attached document text:\n" + attachment_text

    messages = [{"role": "system", "content": text_system_prompt(tool, style, output_format)}]
    for item in history[-10:]:
        role = item.get("role") if item.get("role") in ("user", "assistant") else "user"
        content = item.get("content")
        if content:
            messages.append({"role": role, "content": content})
    if attachment:
        prompt = (prompt + f"\n\nAttachment: {attachment.get('name')} ({attachment.get('mime')})").strip()
    messages.append({"role": "user", "content": f"Mode: {mode}\nTool: {tool}\nPrompt: {prompt}"})

    generated = call_text_provider(model, messages, attachment)
    if not generated.get("ok"):
        return generated
    text = generated.get("text") or ""
    pdf_url = save_text_pdf(text, "SYLVEX Text") if output_format == "pdf" else ""
    if pdf_url:
        text = (text or "").rstrip() + "\n\nPDF: " + pdf_url
    return {
        "ok": True,
        "type": "text",
        "text": text,
        "provider": generated.get("provider") or "openai",
        "model": model,
        "provider_model": generated.get("provider_model") or model,
        "tool": tool,
        "format": output_format,
        "document_url": pdf_url,
        "file_url": pdf_url,
        "files": [pdf_url] if pdf_url else [],
        "transcript": transcript,
        "metadata": generated.get("metadata") or {},
    }

# =====================================================
# PYTHON-БЛОК: openai_image_frontend_model
# Выполняет отдельный шаг backend-логики SYLVEX.
# Связан с API, базой данных, провайдерами или подготовкой данных для Mini App.
# =====================================================
def openai_image_frontend_model(frontend_model: str, provider_model: str = "") -> str:
    raw = str(frontend_model or "").strip().replace("-", "_").lower()
    if raw in OPENAI_IMAGE_MODEL_VARIANTS:
        return raw
    model = str(provider_model or "").strip().replace("-", "_").lower()
    if model == "gpt_image_2":
        return "gpt_image_2"
    return "gpt_image_1"


# =====================================================
# PYTHON-БЛОК: normalize_openai_image_quality
# Выполняет отдельный шаг backend-логики SYLVEX.
# Связан с API, базой данных, провайдерами или подготовкой данных для Mini App.
# =====================================================
def normalize_openai_image_quality(frontend_model: str, provider_model: str, opts: dict) -> str:
    key = openai_image_frontend_model(frontend_model, provider_model)
    cfg = OPENAI_IMAGE_MODEL_VARIANTS.get(key) or OPENAI_IMAGE_MODEL_VARIANTS["gpt_image_1"]
    raw = str((opts or {}).get("quality") or cfg.get("default_quality") or "medium").strip().lower()
    if raw == "standard":
        raw = "medium"
    if raw not in {"low", "medium", "high"}:
        return "medium"
    return raw


# =====================================================
# PYTHON-БЛОК: normalize_openai_image_size
# Выполняет отдельный шаг backend-логики SYLVEX.
# Связан с API, базой данных, провайдерами или подготовкой данных для Mini App.
# =====================================================
def normalize_openai_image_size(size: str, frontend_model: str = "", provider_model: str = "") -> str:
    raw = str(size or "").strip().lower()
    if raw in {"1024x1024", "1536x1024", "1024x1536", "auto"}:
        return raw
    key = openai_image_frontend_model(frontend_model, provider_model)
    if key == "gpt_image_1":
        if raw in {"2:3", "2x3", "9:16", "portrait"}:
            return "1024x1536"
        if raw in {"3:2", "3x2", "16:9", "landscape"}:
            return "1536x1024"
        return "1024x1024"
    if raw in {"1:1", "1x1", "square"}:
        return "1024x1024"
    if raw in {"4:3", "4x3", "16:9", "landscape"}:
        return "1536x1024"
    if raw in {"3:4", "3x4", "9:16", "portrait"}:
        return "1024x1536"
    return "1024x1024"


# =====================================================
# PYTHON-БЛОК: image_reference_urls
# Выполняет отдельный шаг backend-логики SYLVEX.
# Связан с API, базой данных, провайдерами или подготовкой данных для Mini App.
# =====================================================
def image_reference_urls(payload: dict) -> list:
    opts = payload.get("image_options") or {}
    refs = []
    source_values = (
        opts.get("referenceImageUrls"),
        opts.get("reference_image_urls"),
        opts.get("referenceImages"),
        opts.get("images"),
    )
    for value in source_values:
        if isinstance(value, str):
            refs.append(value)
        elif isinstance(value, list):
            refs.extend(value)
    character_refs = _json_list(opts.get("characterReferences"))[:4]
    refs.extend(character_refs)
    refs.extend(_json_list(opts.get("objectReferences")))
    clean = []
    for url in refs:
        if isinstance(url, str) and url.strip() and url not in clean:
            clean.append(url)
    return clean


def openai_image_reference_file(url: str, index: int = 0) -> tuple | None:
    raw = str(url or "").strip()
    if not raw:
        return None
    content = b""
    mime_type = "image/png"
    filename = f"reference-{index + 1}.png"
    try:
        if raw.startswith("data:image/") and ";base64," in raw:
            head, data = raw.split(";base64,", 1)
            mime_type = head.replace("data:", "") or mime_type
            ext = mime_type.split("/", 1)[1].replace("jpeg", "jpg") or "png"
            filename = f"reference-{index + 1}.{ext}"
            content = base64.b64decode(data)
        elif storage_key_from_url(raw):
            content = storage_read_bytes(raw)
            filename = pathlib.Path(urllib.parse.urlparse(raw).path).name or filename
        elif raw.startswith("/webapp/"):
            local_path = WEBAPP_DIR / raw.replace("/webapp/", "", 1)
            content = local_path.read_bytes()
            filename = local_path.name or filename
            suffix = local_path.suffix.lower()
            if suffix in {".jpg", ".jpeg"}:
                mime_type = "image/jpeg"
            elif suffix == ".webp":
                mime_type = "image/webp"
            elif suffix == ".png":
                mime_type = "image/png"
        elif raw.startswith("/generated/"):
            local_path = WEBAPP_DIR / raw.replace("/generated/", "generated/", 1)
            content = local_path.read_bytes()
            filename = local_path.name or filename
            suffix = local_path.suffix.lower()
            if suffix in {".jpg", ".jpeg"}:
                mime_type = "image/jpeg"
            elif suffix == ".webp":
                mime_type = "image/webp"
            elif suffix == ".png":
                mime_type = "image/png"
        else:
            response = requests.get(raw, timeout=60)
            response.raise_for_status()
            content = response.content
            content_type = (response.headers.get("content-type") or "").split(";", 1)[0].strip().lower()
            if content_type.startswith("image/"):
                mime_type = content_type
            parsed_name = pathlib.Path(urllib.parse.urlparse(raw).path).name
            if parsed_name:
                filename = parsed_name
        if not content:
            return None
        return ("image[]", (filename, content, mime_type))
    except Exception as exc:
        prostudio_error("OPENAI_IMAGE_REFERENCE_LOAD_FAILED", exc, source=_sql_text(raw, 180))
        return None

# =====================================================
# PYTHON-БЛОК: validate_image_feature_request
# Выполняет отдельный шаг backend-логики SYLVEX.
# Связан с API, базой данных, провайдерами или подготовкой данных для Mini App.
# =====================================================
def validate_image_feature_request(payload: dict) -> Optional[dict]:
    opts = payload.get("image_options") or {}
    model = opts.get("modelId") or opts.get("model") or payload.get("model") or ""
    features = image_model_features(model)
    has_character = bool(opts.get("characterId") or opts.get("characterReferences"))
    has_object = bool(opts.get("objectId") or opts.get("objectReferences"))
    if has_character and not features["character"]:
        return {"ok": False, "type": "image", "error": "Selected model does not support character references", "model": model}
    if has_object and not features["object"]:
        return {"ok": False, "type": "image", "error": "Selected model does not support object references", "model": model}
    return None


# =====================================================
# PYTHON-БЛОК: image_dimensions
# Выполняет отдельный шаг backend-логики SYLVEX.
# Связан с API, базой данных, провайдерами или подготовкой данных для Mini App.
# =====================================================
def image_dimensions(size: str) -> tuple[int, int]:
    raw = str(size or "").strip().lower()
    if "x" in raw:
        try:
            width, height = [int(part) for part in raw.split("x", 1)]
            return width, height
        except Exception:
            pass
    if raw in {"16:9", "landscape"}:
        return 1536, 864
    if raw in {"9:16", "portrait"}:
        return 864, 1536
    if raw in {"4:3", "4x3"}:
        return 1408, 1056
    if raw in {"3:4", "3x4"}:
        return 1056, 1408
    if raw in {"1:1", "1x1", "auto"}:
        return 1024, 1024
    return 1024, 1024


# =====================================================
# PYTHON-БЛОК: normalize_flux_aspect_ratio
# Выполняет отдельный шаг backend-логики SYLVEX.
# Связан с API, базой данных, провайдерами или подготовкой данных для Mini App.
# =====================================================
def normalize_flux_aspect_ratio(size: str) -> str:
    raw = str(size or "").strip().lower()
    aliases = {
        "square": "1:1",
        "1x1": "1:1",
        "4x3": "4:3",
        "3x4": "3:4",
        "landscape": "16:9",
        "portrait": "9:16",
    }
    value = aliases.get(raw, raw)
    if value in {"1:1", "4:3", "3:4", "16:9", "9:16"}:
        return value
    return "1:1"


# =====================================================
# ОБРАБОТКА ОШИБОК: provider_error_text
# Преобразует техническую ошибку провайдера в понятное сообщение для пользователя и сохраняет диагностические данные для логов.
# =====================================================
def provider_error_text(value, fallback: str = "Provider request failed") -> str:
    return raw_error_text(value, fallback)


# =====================================================
# ОБРАБОТКА ОШИБОК: image_error_response
# Преобразует техническую ошибку провайдера в понятное сообщение для пользователя и сохраняет диагностические данные для логов.
# =====================================================
def image_error_response(provider: str, frontend_model: str, provider_model: str, endpoint: str, error: str, response=None, data: dict = None) -> dict:
    status_code = getattr(response, "status_code", None) if response is not None else None
    body_preview = ""
    details = ""
    if data:
        status_code = data.get("status_code") or status_code
        body_preview = data.get("body_preview") or ""
        details = provider_error_text(data.get("details") or data.get("error") or data.get("message") or "", "")
    if response is not None and not body_preview:
        try:
            body_preview = response.text[:1000]
        except Exception:
            body_preview = ""
    raw_message = provider_error_text(error, "Provider request failed")
    message = translate_provider_error(error, provider=provider, model=frontend_model)
    return {
        "ok": False,
        "type": "image",
        "error": message,
        "message": message,
        "raw_error": raw_message,
        "details": details,
        "provider": provider,
        "frontend_model": frontend_model or "",
        "provider_model": provider_model or "",
        "endpoint": endpoint or "",
        "status_code": status_code,
        "body_preview": body_preview,
    }


# =====================================================
# PYTHON-БЛОК: finalize_image_result
# Выполняет отдельный шаг backend-логики SYLVEX.
# Связан с API, базой данных, провайдерами или подготовкой данных для Mini App.
# =====================================================
async def finalize_image_result(payload: dict, images: list) -> dict:
    result = attach_image_thumbnails({"ok": True, "type": "image", "image_url": images[0], "images": images})
    telegram_id = int(payload.get("telegram_id") or 0)
    result["sent_to_telegram"] = False
    if telegram_id and not payload.get("skip_telegram"):
        try:
            result["sent_to_telegram"] = await send_generated_images_to_telegram(
                telegram_id=telegram_id,
                images=images,
                caption="Готово ✅\nСгенерировано в SYLVEX Pro Studio",
            )
        except Exception as exc:
            print("TELEGRAM SEND GENERATED IMAGES FAILED:", str(exc))
    return result


# =====================================================
# PYTHON-БЛОК: flux_headers
# Выполняет отдельный шаг backend-логики SYLVEX.
# Связан с API, базой данных, провайдерами или подготовкой данных для Mini App.
# =====================================================
def flux_headers() -> dict:
    api_key = os.getenv("BFL_API_KEY") or os.getenv("FLUX_API_KEY") or os.getenv("FLUX-API-KEY")
    if not api_key:
        return {}
    return {"accept": "application/json", "x-key": api_key, "Content-Type": "application/json"}


# =====================================================
# POLLING-ПРОЦЕСС: poll_flux_image
# Проверяет статус внешней задачи у AI-провайдера.
# При completed извлекает результат, при failed возвращает понятную ошибку, при processing продолжает ожидание.
# =====================================================
def poll_flux_image(polling_url: str, frontend_model: str, provider_model: str, max_attempts: int = 180) -> tuple[list, dict]:
    headers = flux_headers()
    for attempt in range(1, max_attempts + 1):
        try:
            response = requests.get(polling_url, headers=headers, timeout=60)
        except requests.RequestException as exc:
            return [], image_error_response("flux", frontend_model, provider_model, polling_url, "Provider request failed", data={"body_preview": str(exc)[:1000]})
        data = safe_provider_json(response, "flux", polling_url)
        if response.status_code >= 400 or data.get("ok") is False:
            return [], image_error_response("flux", frontend_model, provider_model, polling_url, data.get("error") or "Provider request failed", response, data)
        status = data.get("status")
        print("FLUX IMAGE POLL:", {"attempt": attempt, "status": status, "has_image_url": bool((data.get("result") or {}).get("sample"))})
        if status == "Ready":
            image_url = (data.get("result") or {}).get("sample")
            return ([image_url] if image_url else []), {}
        if status in {"Error", "Failed", "Request Moderated", "Content Moderated"}:
            return [], image_error_response("flux", frontend_model, provider_model, polling_url, "Flux generation failed", data=data)
        time.sleep(1)
    return [], image_error_response("flux", frontend_model, provider_model, polling_url, "Flux generation timeout")


# =====================================================
# ЗАПРОС К AI-ПРОВАЙДЕРУ: call_flux_image
# Формирует официальный payload, отправляет запрос во внешний AI API и нормализует ответ для общего lifecycle генерации.
# =====================================================
def call_flux_image(frontend_model: str, provider_model: str, endpoint: str, prompt: str, payload: dict, size: str) -> tuple[list, dict, dict]:
    headers = flux_headers()
    if not headers:
        return [], image_error_response("flux", frontend_model, provider_model, endpoint, "Provider API key is missing"), {}
    refs = image_reference_urls(payload)
    options = payload.get("image_options") or {}
    output_format = options.get("output_format") or "jpeg"
    normalized_provider_model = str(provider_model or "").strip().lower()
    if normalized_provider_model.startswith("flux-kontext-"):
        request_payload = {
            "prompt": prompt,
            "aspect_ratio": normalize_flux_aspect_ratio(size),
            "output_format": output_format,
        }
        for index, ref in enumerate(refs[:4], start=1):
            key = "input_image" if index == 1 else f"input_image_{index}"
            request_payload[key] = ref
    else:
        width, height = image_dimensions(size)
        request_payload = {
            "prompt": prompt,
            "width": width,
            "height": height,
            "output_format": output_format,
        }
        if refs:
            request_payload["input_image"] = refs[0]
    submit_endpoint = f"{endpoint.rstrip('/')}/{provider_model}"
    try:
        response = requests.post(submit_endpoint, headers=headers, json=request_payload, timeout=60)
    except requests.RequestException as exc:
        return [], image_error_response("flux", frontend_model, provider_model, submit_endpoint, "Provider request failed", data={"body_preview": str(exc)[:1000]}), request_payload
    data = safe_provider_json(response, "flux", submit_endpoint)
    if response.status_code >= 400 or data.get("ok") is False:
        return [], image_error_response("flux", frontend_model, provider_model, submit_endpoint, data.get("error") or "Provider request failed", response, data), request_payload
    polling_url = data.get("polling_url")
    if not polling_url:
        return [], image_error_response("flux", frontend_model, provider_model, submit_endpoint, "Flux polling_url not found", data=data), request_payload
    images, error = poll_flux_image(polling_url, frontend_model, provider_model)
    return images, error, request_payload


# =====================================================
# PYTHON-БЛОК: ideogram_headers
# Выполняет отдельный шаг backend-логики SYLVEX.
# Связан с API, базой данных, провайдерами или подготовкой данных для Mini App.
# =====================================================
def ideogram_headers(json_content: bool = True) -> dict:
    api_key = env_value("IDEOGRAM_API_KEY", "IDEOGRAM-API-KEY")
    if not api_key:
        return {}
    headers = {"Api-Key": api_key}
    if json_content:
        headers["Content-Type"] = "application/json"
    return headers


# =====================================================
# PYTHON-БЛОК: ideogram_frontend_model
# Выполняет отдельный шаг backend-логики SYLVEX.
# Связан с API, базой данных, провайдерами или подготовкой данных для Mini App.
# =====================================================
def ideogram_frontend_model(frontend_model: str, provider_model: str = "") -> str:
    raw = str(frontend_model or "").strip().replace("-", "_")
    if raw in IDEOGRAM_MODEL_VARIANTS:
        return raw
    model = str(provider_model or "").lower()
    if "v4" in model or raw in {"ideogram_4", "ideogram_4_0"}:
        return "ideogram_4_0"
    return "ideogram_3_0"


# =====================================================
# PYTHON-БЛОК: ideogram_rendering_speed
# Выполняет отдельный шаг backend-логики SYLVEX.
# Связан с API, базой данных, провайдерами или подготовкой данных для Mini App.
# =====================================================
def ideogram_rendering_speed(frontend_model: str, provider_model: str, opts: Optional[dict] = None) -> str:
    key = ideogram_frontend_model(frontend_model, provider_model)
    cfg = IDEOGRAM_MODEL_VARIANTS.get(key) or {}
    speed = str((opts or {}).get("rendering_speed") or cfg.get("rendering_speed") or "TURBO").upper()
    if key == "ideogram_4_0" and speed == "FLASH":
        return "TURBO"
    valid = {"FLASH", "TURBO", "DEFAULT", "QUALITY"}
    return speed if speed in valid else str(cfg.get("rendering_speed") or "TURBO").upper()


# =====================================================
# PYTHON-БЛОК: ideogram_size_params
# Выполняет отдельный шаг backend-логики SYLVEX.
# Связан с API, базой данных, провайдерами или подготовкой данных для Mini App.
# =====================================================
def ideogram_size_params(frontend_model: str, provider_model: str, size: str) -> dict:
    raw = str(size or "").strip().lower().replace("_", "-")
    if raw in {"", "auto"}:
        return {}
    is_v4 = ideogram_frontend_model(frontend_model, provider_model) == "ideogram_4_0"
    if is_v4:
        mapping = {
            "1:1": {"resolution": "2048x2048"},
            "1x1": {"resolution": "2048x2048"},
            "4:3": {"resolution": "2496x1664"},
            "4x3": {"resolution": "2496x1664"},
            "3:4": {"resolution": "1664x2496"},
            "3x4": {"resolution": "1664x2496"},
            "16:9": {"resolution": "2880x1440"},
            "16x9": {"resolution": "2880x1440"},
            "9:16": {"resolution": "1440x2880"},
            "9x16": {"resolution": "1440x2880"},
        }
        return mapping.get(raw, {"resolution": "2048x2048"})
    mapping = {
        "1:1": {"aspect_ratio": "1x1"},
        "1x1": {"aspect_ratio": "1x1"},
        "1:1-hd": {"resolution": "1024x1024"},
        "1:1 hd": {"resolution": "1024x1024"},
        "4:3": {"aspect_ratio": "4x3"},
        "4x3": {"aspect_ratio": "4x3"},
        "3:4": {"aspect_ratio": "3x4"},
        "3x4": {"aspect_ratio": "3x4"},
        "16:9": {"aspect_ratio": "16x9"},
        "16x9": {"aspect_ratio": "16x9"},
        "9:16": {"aspect_ratio": "9x16"},
        "9x16": {"aspect_ratio": "9x16"},
    }
    return mapping.get(raw, {"aspect_ratio": "1x1"})


# =====================================================
# БАЛАНС И СТОИМОСТЬ: ideogram_cost_info
# Рассчитывает стоимость генерации, проверяет токены пользователя или фиксирует списание после успешного результата.
# =====================================================
def ideogram_cost_info(frontend_model: str, provider_model: str, rendering_speed: str, count: int, has_character: bool = False) -> dict:
    key = ideogram_frontend_model(frontend_model, provider_model)
    cfg = IDEOGRAM_MODEL_VARIANTS.get(key) or IDEOGRAM_MODEL_VARIANTS["ideogram_3_0"]
    speed = str(rendering_speed or cfg.get("rendering_speed") or "TURBO").upper()
    cost_key = f"{speed}_CHARACTER" if has_character and key == "ideogram_3_0" else speed
    unit_usd = float((cfg.get("cost_usd") or {}).get(cost_key, 0))
    unit_credits = int((cfg.get("cost_credits") or {}).get(cost_key, 0))
    image_count = max(1, int(count or 1))
    label_speed = speed.title()
    if has_character and key == "ideogram_3_0":
        label_speed += " + Character"
    return {
        "cost": unit_credits * image_count,
        "cost_credits": unit_credits * image_count,
        "unit_cost_credits": unit_credits,
        "cost_usd": round(unit_usd * image_count, 3),
        "unit_cost_usd": unit_usd,
        "generation_cost": f"${unit_usd * image_count:.3f}",
        "rendering_speed": speed,
        "model_label": f"{cfg.get('label_prefix', 'Ideogram')} {label_speed}",
    }


# =====================================================
# PYTHON-БЛОК: recraft_frontend_model
# Выполняет отдельный шаг backend-логики SYLVEX.
# Связан с API, базой данных, провайдерами или подготовкой данных для Mini App.
# =====================================================
def recraft_frontend_model(frontend_model: str, provider_model: str = "") -> str:
    raw = str(frontend_model or "").strip().replace("-", "_")
    if raw in RECRAFT_MODEL_VARIANTS:
        return raw
    model = str(provider_model or "").lower()
    if "v4_1_pro" in model or "v4.1_pro" in model:
        return "recraft_v4_1_pro"
    if "v3" in model:
        return "recraft_v3"
    return "recraft_v4_1"


# =====================================================
# PYTHON-БЛОК: recraft_headers
# Выполняет отдельный шаг backend-логики SYLVEX.
# Связан с API, базой данных, провайдерами или подготовкой данных для Mini App.
# =====================================================
def recraft_headers() -> dict:
    api_key = env_value("RECRAFT_API_KEY", "RECRAFT-API-KEY")
    if not api_key:
        return {}
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }


# =====================================================
# PYTHON-БЛОК: recraft_size_value
# Выполняет отдельный шаг backend-логики SYLVEX.
# Связан с API, базой данных, провайдерами или подготовкой данных для Mini App.
# =====================================================
def recraft_size_value(size: str) -> str:
    raw = str(size or "").strip()
    if raw.lower() in {"", "auto"}:
        return ""
    supported = {"1:1", "16:9", "9:16", "3:4", "4:3"}
    return raw if raw in supported else "1:1"


# =====================================================
# PYTHON-БЛОК: recraft_available_tools
# Выполняет отдельный шаг backend-логики SYLVEX.
# Связан с API, базой данных, провайдерами или подготовкой данных для Mini App.
# =====================================================
def recraft_available_tools(frontend_model: str, provider_model: str = "") -> list:
    key = recraft_frontend_model(frontend_model, provider_model)
    cfg = RECRAFT_MODEL_VARIANTS.get(key) or {}
    tools = []
    for tool_id in cfg.get("tools") or []:
        item = RECRAFT_TOOL_CATALOG.get(tool_id)
        if item:
            tools.append({"id": tool_id, **item})
    return tools


# =====================================================
# БАЛАНС И СТОИМОСТЬ: recraft_cost_info
# Рассчитывает стоимость генерации, проверяет токены пользователя или фиксирует списание после успешного результата.
# =====================================================
def recraft_cost_info(frontend_model: str, provider_model: str, count: int) -> dict:
    key = recraft_frontend_model(frontend_model, provider_model)
    cfg = RECRAFT_MODEL_VARIANTS.get(key) or RECRAFT_MODEL_VARIANTS["recraft_v4_1"]
    image_count = max(1, int(count or 1))
    unit_credits = int(cfg.get("cost_credits") or 0)
    unit_usd = float(cfg.get("cost_usd") or 0)
    return {
        "cost": unit_credits * image_count,
        "cost_credits": unit_credits * image_count,
        "unit_cost_credits": unit_credits,
        "cost_usd": round(unit_usd * image_count, 4),
        "unit_cost_usd": unit_usd,
        "provider_cost_usd": round(float(cfg.get("provider_cost_usd") or 0) * image_count, 4),
        "generation_cost": f"${unit_usd * image_count:.4f}",
        "model_label": cfg.get("label") or frontend_model or provider_model,
        "recraft_tools": recraft_available_tools(frontend_model, provider_model),
    }


# =====================================================
# PYTHON-БЛОК: seedream_frontend_model
# Выполняет отдельный шаг backend-логики SYLVEX.
# Связан с API, базой данных, провайдерами или подготовкой данных для Mini App.
# =====================================================
def seedream_frontend_model(frontend_model: str, provider_model: str = "") -> str:
    raw = str(frontend_model or "").strip().replace("-", "_").lower()
    if raw in SEEDREAM_MODEL_VARIANTS:
        return raw
    model = str(provider_model or "").lower()
    if "dola-seedream-5-0-pro" in model or "seedream-5-0-pro" in model:
        return "seedream_5_0_pro"
    if "seedream-4-5" in model:
        return "seedream_4_5"
    if "seedream-4-0" in model:
        return "seedream_4_0"
    if "seedream-5-0" in model:
        return "seedream_5_0_lite"
    return "seedream_5_0_lite"


# =====================================================
# PYTHON-БЛОК: seedream_size_value
# Выполняет отдельный шаг backend-логики SYLVEX.
# Связан с API, базой данных, провайдерами или подготовкой данных для Mini App.
# =====================================================
def seedream_size_value(size: str) -> str:
    raw = str(size or "").strip().lower()
    if raw in {"", "auto"}:
        return "2K"
    mapping = {
        "1:1": "2048x2048",
        "1x1": "2048x2048",
        "4:3": "2304x1728",
        "4x3": "2304x1728",
        "3:4": "1728x2304",
        "3x4": "1728x2304",
        "16:9": "2560x1440",
        "16x9": "2560x1440",
        "9:16": "1440x2560",
        "9x16": "1440x2560",
    }
    return mapping.get(raw, "2K")


# =====================================================
# БАЛАНС И СТОИМОСТЬ: seedream_cost_info
# Рассчитывает стоимость генерации, проверяет токены пользователя или фиксирует списание после успешного результата.
# =====================================================
def seedream_cost_info(frontend_model: str, provider_model: str, count: int) -> dict:
    key = seedream_frontend_model(frontend_model, provider_model)
    cfg = SEEDREAM_MODEL_VARIANTS.get(key) or SEEDREAM_MODEL_VARIANTS["seedream_5_0_lite"]
    image_count = max(1, int(count or 1))
    unit_credits = int(cfg.get("cost_credits") or 0)
    unit_usd = float(cfg.get("cost_usd") or 0)
    return {
        "cost": unit_credits * image_count,
        "cost_credits": unit_credits * image_count,
        "unit_cost_credits": unit_credits,
        "cost_usd": round(unit_usd * image_count, 4),
        "unit_cost_usd": unit_usd,
        "generation_cost": f"${unit_usd * image_count:.4f}",
        "model_label": cfg.get("label") or frontend_model or provider_model,
    }


# =====================================================
# PYTHON-БЛОК: flux_frontend_model
# Выполняет отдельный шаг backend-логики SYLVEX.
# Связан с API, базой данных, провайдерами или подготовкой данных для Mini App.
# =====================================================
def flux_frontend_model(frontend_model: str, provider_model: str = "") -> str:
    raw = str(frontend_model or "").strip().replace("-", "_").lower()
    if raw in FLUX_MODEL_VARIANTS:
        return raw
    model = str(provider_model or "").lower()
    if model == "flux-2-flex":
        return "flux_2_turbo"
    return "flux_2"


# =====================================================
# БАЛАНС И СТОИМОСТЬ: flux_cost_info
# Рассчитывает стоимость генерации, проверяет токены пользователя или фиксирует списание после успешного результата.
# =====================================================
def flux_cost_info(frontend_model: str, provider_model: str, count: int) -> dict:
    key = flux_frontend_model(frontend_model, provider_model)
    cfg = FLUX_MODEL_VARIANTS.get(key) or FLUX_MODEL_VARIANTS["flux_2"]
    image_count = max(1, int(count or 1))
    unit_credits = int(cfg.get("cost_credits") or 0)
    unit_usd = float(cfg.get("cost_usd") or 0)
    return {
        "cost": unit_credits * image_count,
        "cost_credits": unit_credits * image_count,
        "unit_cost_credits": unit_credits,
        "cost_usd": round(unit_usd * image_count, 4),
        "unit_cost_usd": unit_usd,
        "generation_cost": f"${unit_usd * image_count:.4f}",
        "model_label": cfg.get("label") or frontend_model or provider_model,
    }


# =====================================================
# PYTHON-БЛОК: qwen_frontend_model
# Выполняет отдельный шаг backend-логики SYLVEX.
# Связан с API, базой данных, провайдерами или подготовкой данных для Mini App.
# =====================================================
def qwen_frontend_model(frontend_model: str, provider_model: str = "") -> str:
    raw = str(frontend_model or "").strip().replace("-", "_").lower()
    if raw in QWEN_MODEL_VARIANTS:
        return raw
    model = str(provider_model or "").strip().replace("-", "_").lower()
    if model in QWEN_MODEL_VARIANTS:
        return model
    if "2_pro" in model or "2_pro" in raw:
        return "qwen_image_2_pro"
    if "_2" in model or "_2" in raw:
        return "qwen_image_2"
    return "qwen_image"


# =====================================================
# БАЛАНС И СТОИМОСТЬ: qwen_cost_info
# Рассчитывает стоимость генерации, проверяет токены пользователя или фиксирует списание после успешного результата.
# =====================================================
def qwen_cost_info(frontend_model: str, provider_model: str, count: int) -> dict:
    key = qwen_frontend_model(frontend_model, provider_model)
    cfg = QWEN_MODEL_VARIANTS.get(key) or QWEN_MODEL_VARIANTS["qwen_image"]
    image_count = max(1, int(count or 1))
    unit_credits = int(cfg.get("cost_credits") or 0)
    unit_usd = float(cfg.get("cost_usd") or 0)
    return {
        "cost": unit_credits * image_count,
        "cost_credits": unit_credits * image_count,
        "unit_cost_credits": unit_credits,
        "cost_usd": round(unit_usd * image_count, 4),
        "unit_cost_usd": unit_usd,
        "generation_cost": f"${unit_usd * image_count:.4f}",
        "model_label": cfg.get("label") or frontend_model or provider_model,
    }


# =====================================================
# PYTHON-БЛОК: qwen_headers
# Выполняет отдельный шаг backend-логики SYLVEX.
# Связан с API, базой данных, провайдерами или подготовкой данных для Mini App.
# =====================================================
def qwen_headers() -> dict:
    api_key = env_value("DASHSCOPE_API_KEY", "DASHSCOPE-API-KEY", "QWEN_API_KEY", "QWEN-API-KEY")
    if not api_key:
        return {}
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }


# =====================================================
# PYTHON-БЛОК: qwen_image_size
# Выполняет отдельный шаг backend-логики SYLVEX.
# Связан с API, базой данных, провайдерами или подготовкой данных для Mini App.
# =====================================================
def qwen_image_size(size: str, frontend_model: str, provider_model: str = "") -> str:
    ratio = str(size or "").strip().lower().replace("x", ":")
    key = qwen_frontend_model(frontend_model, provider_model)
    if ratio in {"", "auto"}:
        return "2048*2048" if key in {"qwen_image_2", "qwen_image_2_pro"} else "1664*928"
    if key in {"qwen_image_2", "qwen_image_2_pro"}:
        return {
            "1:1": "2048*2048",
            "4:3": "2048*1536",
            "3:4": "1536*2048",
            "16:9": "2048*1152",
            "9:16": "1152*2048",
        }.get(ratio, "2048*2048")
    return {
        "1:1": "1328*1328",
        "4:3": "1472*1104",
        "3:4": "1104*1472",
        "16:9": "1664*928",
        "9:16": "928*1664",
    }.get(ratio, "1664*928")


def qwen_image_reference_value(value: str) -> str:
    """Return actual image bytes as a DashScope-compatible data URL when possible."""
    raw = str(value or "").strip()
    if raw.startswith("data:image/") and ";base64," in raw:
        return raw

    public_url = f"{WEBAPP_URL.rstrip('/')}{raw}" if raw.startswith("/") and WEBAPP_URL else raw
    content = b""
    content_type = mimetypes.guess_type(urllib.parse.urlparse(public_url).path)[0] or "image/png"
    try:
        if storage_key_from_url(public_url):
            content = storage_read_bytes(public_url)
        elif public_url.startswith(("http://", "https://")):
            response = requests.get(public_url, timeout=60)
            response.raise_for_status()
            content = response.content
            content_type = str(response.headers.get("content-type") or content_type).split(";", 1)[0].strip()
    except Exception as exc:
        prostudio_error("QWEN_IMAGE_REFERENCE_READ_FAILED", exc, source_type="storage" if storage_key_from_url(public_url) else "url")

    if content:
        if content.startswith(b"\xff\xd8\xff"):
            content_type = "image/jpeg"
        elif content.startswith(b"\x89PNG\r\n\x1a\n"):
            content_type = "image/png"
        elif content.startswith(b"RIFF") and content[8:12] == b"WEBP":
            content_type = "image/webp"
        return f"data:{content_type};base64,{base64.b64encode(content).decode('ascii')}"
    return public_url if public_url.startswith(("http://", "https://")) else ""


def qwen_image_edit_model(provider_model: str, has_images: bool) -> str:
    """Use an editing-capable Qwen model whenever an input image is present."""
    model = str(provider_model or "").strip()
    if not has_images:
        return model
    normalized = model.lower()
    generation_only_models = {
        "qwen-image",
        "qwen-image-max",
        "qwen-image-plus",
        "qwen-image-max-2025-12-30",
        "qwen-image-plus-2026-01-09",
    }
    if normalized in generation_only_models:
        return env_value(
            "QWEN_IMAGE_EDIT_MODEL",
            "QWEN-IMAGE-EDIT-MODEL",
            default="qwen-image-2.0",
        )
    return model


# =====================================================
# ЗАПРОС К AI-ПРОВАЙДЕРУ: call_qwen_image
# Формирует официальный payload, отправляет запрос во внешний AI API и нормализует ответ для общего lifecycle генерации.
# =====================================================
def call_qwen_image(frontend_model: str, provider_model: str, endpoint: str, prompt: str, payload: dict, size: str, count: int = 1) -> tuple[list, dict, dict]:
    headers = qwen_headers()
    if not headers:
        return [], image_error_response("qwen", frontend_model, provider_model, endpoint, "Provider API key is missing: DASHSCOPE_API_KEY"), {}
    opts = payload.get("image_options") or {}
    key = qwen_frontend_model(frontend_model, provider_model)
    received_references = image_reference_urls(payload)
    included_references = []
    for reference in received_references:
        image_value = qwen_image_reference_value(reference)
        if image_value and image_value not in included_references:
            included_references.append(image_value)
        if len(included_references) >= 3:
            break
    effective_provider_model = qwen_image_edit_model(provider_model, bool(included_references))
    seed_supported = bool((QWEN_MODEL_VARIANTS.get(key) or {}).get("seed"))
    seed = normalize_image_seed(opts.get("seed")) if seed_supported else None
    if seed is not None and seed > 2147483647:
        return [], image_error_response("qwen", frontend_model, provider_model, endpoint, "Seed must be between 0 and 2147483647"), {}
    image_count = max(1, int(count or 1))
    per_request_count = image_count if key in {"qwen_image_2", "qwen_image_2_pro"} else 1
    content = [{"image": reference} for reference in included_references]
    content.append({"text": prompt})
    request_parameters = {
        "negative_prompt": str(opts.get("negative_prompt") or "")[:500],
        "prompt_extend": False if included_references else bool(opts.get("prompt_extend", True)),
        "watermark": bool(opts.get("watermark", False)),
        "n": max(1, min(per_request_count, 6)),
    }
    # For editing, omitting size makes DashScope preserve the input image's
    # aspect ratio. Text-to-image keeps the explicitly selected output size.
    if not included_references:
        request_parameters["size"] = qwen_image_size(size, frontend_model, provider_model)
    request_payload = {
        "model": effective_provider_model,
        "input": {
            "messages": [
                {
                    "role": "user",
                    "content": content,
                }
            ]
        },
        "parameters": request_parameters,
    }
    if seed is not None:
        request_payload["parameters"]["seed"] = seed

    all_images = []
    last_payload = request_payload
    attempts = 1 if key in {"qwen_image_2", "qwen_image_2_pro"} else image_count
    for attempt in range(1, attempts + 1):
        try:
            prostudio_debug(
                "QWEN_IMAGE_PROVIDER_REQUEST",
                endpoint=endpoint,
                frontend_model=frontend_model,
                provider_model=effective_provider_model,
                size=request_payload["parameters"].get("size") or "source",
                count=request_payload["parameters"].get("n"),
                reference_count_received=len(received_references),
                image_count=len(included_references),
                inline_image_count=sum(1 for value in included_references if value.startswith("data:image/")),
                reference_count_omitted=max(0, len(received_references) - len(included_references)),
                attempt=attempt,
                seed_present=seed is not None,
            )
            response = requests.post(endpoint, headers=headers, data=json.dumps(request_payload), timeout=180)
        except requests.RequestException as exc:
            prostudio_error("QWEN_IMAGE_PROVIDER_REQUEST_FAILED", exc, endpoint=endpoint, frontend_model=frontend_model, provider_model=effective_provider_model)
            return [], image_error_response("qwen", frontend_model, effective_provider_model, endpoint, "Provider request failed", data={"body_preview": str(exc)[:1000]}), last_payload
        data = safe_provider_json(response, "qwen", endpoint)
        images = normalize_image_response(data)
        prostudio_debug(
            "QWEN_IMAGE_PROVIDER_RESPONSE",
            endpoint=endpoint,
            status_code=response.status_code,
            data_keys=sorted(data.keys()) if isinstance(data, dict) else [],
            image_count=len(images),
        )
        if response.status_code >= 400 or data.get("ok") is False:
            provider_error = provider_error_text(data.get("error") or data.get("message") or data, "Provider request failed")
            return [], image_error_response("qwen", frontend_model, effective_provider_model, endpoint, provider_error, response, data), last_payload
        for url in images:
            if url and url not in all_images:
                all_images.append(url)
        if len(all_images) >= image_count:
            break
    return all_images[:image_count], {}, last_payload


# =====================================================
# PYTHON-БЛОК: google_image_frontend_model
# Выполняет отдельный шаг backend-логики SYLVEX.
# Связан с API, базой данных, провайдерами или подготовкой данных для Mini App.
# =====================================================
def google_image_frontend_model(frontend_model: str, provider_model: str = "") -> str:
    raw = str(frontend_model or "").strip().replace("-", "_").lower()
    if raw in GOOGLE_IMAGE_MODEL_VARIANTS:
        return raw
    model = str(provider_model or "").strip().lower()
    if model == "gemini-3.1-flash-image":
        return "nano_banana_2"
    if model == "gemini-3.1-flash-lite-image":
        return "nano_banana_2_lite"
    if model == "gemini-3-pro-image":
        return "nano_banana_pro"
    if model == "gemini-2.5-flash-image":
        return "nano_banana"
    if model == "imagen-4.0-fast-generate-001":
        return "imagen_4_fast"
    if model == "imagen-4.0-ultra-generate-001":
        return "imagen_4_ultra"
    if model == "imagen-4.0-generate-001":
        return "imagen_4_standard"
    return "nano_banana_2"


# =====================================================
# PYTHON-БЛОК: google_image_aspect_ratio
# Выполняет отдельный шаг backend-логики SYLVEX.
# Связан с API, базой данных, провайдерами или подготовкой данных для Mini App.
# =====================================================
def google_image_aspect_ratio(size: str, imagen: bool = False) -> str:
    raw = str(size or "").strip().lower().replace("x", ":")
    if raw in {"", "auto"}:
        return "1:1" if imagen else "auto"
    supported = {
        "1:1",
        "16:9",
        "9:16",
        "3:4",
        "4:3",
        "1:2",
        "2:1",
        "20:9",
        "9:20",
    }
    if imagen:
        supported = {"1:1", "3:4", "4:3", "9:16", "16:9"}
    return raw if raw in supported else "1:1"


# =====================================================
# PYTHON-БЛОК: google_image_resolution
# Выполняет отдельный шаг backend-логики SYLVEX.
# Связан с API, базой данных, провайдерами или подготовкой данных для Mini App.
# =====================================================
def google_image_resolution(opts: dict, frontend_model: str, provider_model: str = "") -> str:
    key = google_image_frontend_model(frontend_model, provider_model)
    cfg = GOOGLE_IMAGE_MODEL_VARIANTS.get(key) or GOOGLE_IMAGE_MODEL_VARIANTS["nano_banana_2"]
    raw = str(
        (opts or {}).get("resolution")
        or (opts or {}).get("image_resolution")
        or (opts or {}).get("quality")
        or cfg.get("default_resolution")
        or "1k"
    ).strip().lower()
    aliases = {"0.5": "0.5k", "512": "0.5k", "1024": "1k", "2048": "2k", "4096": "4k"}
    raw = aliases.get(raw, raw)
    if raw not in (cfg.get("cost_credits") or {}):
        return str(cfg.get("default_resolution") or "1k").lower()
    return raw


# =====================================================
# PYTHON-БЛОК: google_interactions_image_size
# Выполняет отдельный шаг backend-логики SYLVEX.
# Связан с API, базой данных, провайдерами или подготовкой данных для Mini App.
# =====================================================
def google_interactions_image_size(resolution: str) -> str:
    raw = str(resolution or "").strip().lower()
    if raw in {"0.5k", "0.5", "512", "512px"}:
        return "512"
    if raw in {"2k", "2048"}:
        return "2K"
    if raw in {"4k", "4096"}:
        return "4K"
    return "1K"


# =====================================================
# PYTHON-БЛОК: google_has_input_image
# Выполняет отдельный шаг backend-логики SYLVEX.
# Связан с API, базой данных, провайдерами или подготовкой данных для Mini App.
# =====================================================
def google_has_input_image(payload: dict) -> bool:
    return bool(image_reference_urls(payload))


# =====================================================
# БАЛАНС И СТОИМОСТЬ: google_image_cost_info
# Рассчитывает стоимость генерации, проверяет токены пользователя или фиксирует списание после успешного результата.
# =====================================================
def google_image_cost_info(frontend_model: str, provider_model: str, count: int, resolution: str = "", has_input_image: bool = False) -> dict:
    key = google_image_frontend_model(frontend_model, provider_model)
    cfg = GOOGLE_IMAGE_MODEL_VARIANTS.get(key) or GOOGLE_IMAGE_MODEL_VARIANTS["nano_banana_2"]
    res = google_image_resolution({"resolution": resolution}, key, cfg.get("provider_model") or provider_model)
    image_count = max(1, int(count or 1))
    unit_credits = int((cfg.get("cost_credits") or {}).get(res, 0))
    input_credits = 0
    total_credits = unit_credits * image_count + input_credits
    return {
        "cost": total_credits,
        "cost_credits": total_credits,
        "unit_cost_credits": unit_credits,
        "cost_usd": 0,
        "unit_cost_usd": 0,
        "generation_cost": f"{total_credits} ⚡" if total_credits else "",
        "model_label": cfg.get("label") or frontend_model or provider_model,
        "resolution": res.upper(),
        "input_image_credits": input_credits,
        "input_image_cost_included": bool(has_input_image),
        "input_image_surcharge_provisional": False,
    }


# =====================================================
# PYTHON-БЛОК: grok_frontend_model
# Выполняет отдельный шаг backend-логики SYLVEX.
# Связан с API, базой данных, провайдерами или подготовкой данных для Mini App.
# =====================================================
def grok_frontend_model(frontend_model: str, provider_model: str = "") -> str:
    raw = str(frontend_model or "").strip().replace("-", "_").lower()
    if raw in GROK_MODEL_VARIANTS:
        return raw
    model = str(provider_model or "").strip().lower()
    if model == "grok-imagine-image-quality" or "quality" in model:
        return "grok_pro"
    return "grok"


# =====================================================
# PYTHON-БЛОК: grok_headers
# Выполняет отдельный шаг backend-логики SYLVEX.
# Связан с API, базой данных, провайдерами или подготовкой данных для Mini App.
# =====================================================
def grok_headers() -> dict:
    api_key = env_value("XAI_API_KEY", "XAI-API-KEY", "GROK_API_KEY", "GROK-API-KEY")
    if not api_key:
        return {}
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }


# =====================================================
# PYTHON-БЛОК: grok_aspect_ratio
# Выполняет отдельный шаг backend-логики SYLVEX.
# Связан с API, базой данных, провайдерами или подготовкой данных для Mini App.
# =====================================================
def grok_aspect_ratio(size: str) -> str:
    raw = str(size or "").strip().lower().replace("x", ":")
    supported = {
        "1:1",
        "2:3",
        "3:2",
        "16:9",
        "9:16",
        "3:4",
        "4:3",
        "1:2",
        "2:1",
        "19.5:9",
        "9:19.5",
        "20:9",
        "9:20",
    }
    if raw in supported:
        return raw
    return "1:1"


# =====================================================
# PYTHON-БЛОК: grok_resolution_value
# Выполняет отдельный шаг backend-логики SYLVEX.
# Связан с API, базой данных, провайдерами или подготовкой данных для Mini App.
# =====================================================
def grok_resolution_value(opts: dict) -> str:
    raw = str(
        (opts or {}).get("resolution")
        or (opts or {}).get("quality")
        or (opts or {}).get("image_resolution")
        or "1k"
    ).strip().lower()
    if raw in {"2", "2k"}:
        return "2k"
    return "1k"


# =====================================================
# PYTHON-БЛОК: grok_has_input_image
# Выполняет отдельный шаг backend-логики SYLVEX.
# Связан с API, базой данных, провайдерами или подготовкой данных для Mini App.
# =====================================================
def grok_has_input_image(payload: dict) -> bool:
    opts = payload.get("image_options") or {}
    if image_reference_urls(payload):
        return True
    for key in ("image_url", "input_image", "inputImage", "referenceImageUrl"):
        if isinstance(opts.get(key), str) and opts.get(key).strip():
            return True
    return False


# =====================================================
# PYTHON-БЛОК: grok_input_image_url
# Выполняет отдельный шаг backend-логики SYLVEX.
# Связан с API, базой данных, провайдерами или подготовкой данных для Mini App.
# =====================================================
def grok_input_image_url(payload: dict) -> str:
    opts = payload.get("image_options") or {}
    for key in ("image_url", "input_image", "inputImage", "referenceImageUrl"):
        value = opts.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    refs = image_reference_urls(payload)
    return refs[0] if refs else ""


# =====================================================
# БАЛАНС И СТОИМОСТЬ: grok_cost_info
# Рассчитывает стоимость генерации, проверяет токены пользователя или фиксирует списание после успешного результата.
# =====================================================
def grok_cost_info(frontend_model: str, provider_model: str, count: int, resolution: str = "1k", has_input_image: bool = False) -> dict:
    key = grok_frontend_model(frontend_model, provider_model)
    cfg = GROK_MODEL_VARIANTS.get(key) or GROK_MODEL_VARIANTS["grok"]
    image_count = max(1, int(count or 1))
    res = "2k" if str(resolution or "").strip().lower() in {"2", "2k"} else "1k"
    unit_credits = int((cfg.get("cost_credits") or {}).get(res, 0))
    input_credits = int(cfg.get("input_image_credits") or 0) if has_input_image else 0
    total_credits = unit_credits * image_count + input_credits
    generation_cost = f"{total_credits} ⚡" if total_credits else ""
    return {
        "cost": total_credits,
        "cost_credits": total_credits,
        "unit_cost_credits": unit_credits,
        "cost_usd": 0,
        "unit_cost_usd": 0,
        "generation_cost": generation_cost,
        "model_label": cfg.get("label") or frontend_model or provider_model,
        "resolution": res.upper(),
        "input_image_credits": input_credits,
        "input_image_surcharge_provisional": bool(has_input_image and cfg.get("input_image_surcharge_provisional")),
    }


# =====================================================
# БАЛАНС И СТОИМОСТЬ: openai_image_cost_info
# Рассчитывает стоимость генерации, проверяет токены пользователя или фиксирует списание после успешного результата.
# =====================================================
def openai_image_cost_info(frontend_model: str, provider_model: str, quality: str, count: int) -> dict:
    key = openai_image_frontend_model(frontend_model, provider_model)
    cfg = OPENAI_IMAGE_MODEL_VARIANTS.get(key) or OPENAI_IMAGE_MODEL_VARIANTS["gpt_image_1"]
    image_count = max(1, int(count or 1))
    normalized_quality = str(quality or cfg.get("default_quality") or "medium").strip().lower()
    if normalized_quality not in {"low", "medium", "high"}:
        normalized_quality = "medium"
    unit_credits = int((cfg.get("cost_credits") or {}).get(normalized_quality, 0))
    unit_usd = float((cfg.get("cost_usd") or {}).get(normalized_quality, 0))
    return {
        "cost": unit_credits * image_count,
        "cost_credits": unit_credits * image_count,
        "unit_cost_credits": unit_credits,
        "cost_usd": round(unit_usd * image_count, 4),
        "unit_cost_usd": unit_usd,
        "generation_cost": f"${unit_usd * image_count:.4f}",
        "quality": normalized_quality,
        "model_label": cfg.get("label") or frontend_model or provider_model,
    }


# =====================================================
# ЗАПРОС К AI-ПРОВАЙДЕРУ: call_grok_image
# Формирует официальный payload, отправляет запрос во внешний AI API и нормализует ответ для общего lifecycle генерации.
# =====================================================
def call_grok_image(frontend_model: str, provider_model: str, endpoint: str, prompt: str, payload: dict, size: str, count: int = 1) -> tuple[list, dict, dict]:
    headers = grok_headers()
    if not headers:
        return [], image_error_response("grok", frontend_model, provider_model, endpoint, "Provider API key is missing"), {}
    opts = payload.get("image_options") or {}
    resolution = grok_resolution_value(opts)
    input_image = grok_input_image_url(payload)
    request_payload = {
        "model": provider_model,
        "prompt": prompt,
        "n": max(1, int(count or 1)),
        "aspect_ratio": grok_aspect_ratio(size),
        "resolution": resolution,
    }
    if input_image:
        request_payload["image_url"] = input_image
    try:
        prostudio_debug(
            "GROK_PROVIDER_REQUEST",
            endpoint=endpoint,
            frontend_model=frontend_model,
            provider_model=provider_model,
            aspect_ratio=request_payload.get("aspect_ratio"),
            resolution=request_payload.get("resolution"),
            count=request_payload.get("n"),
            has_input_image=bool(request_payload.get("image_url")),
        )
        response = requests.post(endpoint, headers=headers, json=request_payload, timeout=180)
    except requests.RequestException as exc:
        prostudio_error("GROK_PROVIDER_REQUEST_FAILED", exc, endpoint=endpoint, frontend_model=frontend_model, provider_model=provider_model)
        return [], image_error_response("grok", frontend_model, provider_model, endpoint, "Provider request failed", data={"body_preview": str(exc)[:1000]}), request_payload
    data = safe_provider_json(response, "grok", endpoint)
    prostudio_debug(
        "GROK_PROVIDER_RESPONSE",
        endpoint=endpoint,
        status_code=response.status_code,
        data_keys=sorted(data.keys()) if isinstance(data, dict) else [],
        image_count=len(normalize_image_response(data)) if isinstance(data, dict) else 0,
    )
    if response.status_code >= 400 or data.get("ok") is False:
        return [], image_error_response("grok", frontend_model, provider_model, endpoint, data.get("error") or data.get("message") or "Provider request failed", response, data), request_payload
    images = normalize_image_response(data)
    return images, {}, request_payload


# =====================================================
# PYTHON-БЛОК: google_image_headers
# Выполняет отдельный шаг backend-логики SYLVEX.
# Связан с API, базой данных, провайдерами или подготовкой данных для Mini App.
# =====================================================
def google_image_headers() -> dict:
    api_key = env_value("GEMINI_API_KEY", "GEMINI-API-KEY", "GOOGLE_API_KEY", "GOOGLE-API-KEY")
    if not api_key:
        return {}
    return {
        "x-goog-api-key": api_key,
        "Content-Type": "application/json",
    }


# =====================================================
# PYTHON-БЛОК: google_local_or_remote_image_part
# Выполняет отдельный шаг backend-логики SYLVEX.
# Связан с API, базой данных, провайдерами или подготовкой данных для Mini App.
# =====================================================
def google_local_or_remote_image_part(url: str) -> dict:
    raw = str(url or "").strip()
    if not raw:
        return {}
    mime_type = "image/png"
    try:
        if raw.startswith("data:image/") and ";base64," in raw:
            head, data = raw.split(";base64,", 1)
            mime_type = head.replace("data:", "") or mime_type
            return {"type": "image", "mime_type": mime_type, "data": data}
        if storage_key_from_url(raw):
            data = storage_read_bytes(raw)
            suffix = pathlib.Path(urllib.parse.urlparse(raw).path).suffix.lower()
            if suffix in {".jpg", ".jpeg"}:
                mime_type = "image/jpeg"
            elif suffix == ".webp":
                mime_type = "image/webp"
            return {"type": "image", "mime_type": mime_type, "data": base64.b64encode(data).decode("utf-8")}
        if raw.startswith("/webapp/"):
            local_path = WEBAPP_DIR / raw.replace("/webapp/", "", 1)
            data = local_path.read_bytes()
            suffix = local_path.suffix.lower()
            if suffix in {".jpg", ".jpeg"}:
                mime_type = "image/jpeg"
            elif suffix == ".webp":
                mime_type = "image/webp"
            return {"type": "image", "mime_type": mime_type, "data": base64.b64encode(data).decode("utf-8")}
        if raw.startswith("/generated/"):
            local_path = WEBAPP_DIR / raw.replace("/generated/", "generated/", 1)
            data = local_path.read_bytes()
            suffix = local_path.suffix.lower()
            if suffix in {".jpg", ".jpeg"}:
                mime_type = "image/jpeg"
            elif suffix == ".webp":
                mime_type = "image/webp"
            return {"type": "image", "mime_type": mime_type, "data": base64.b64encode(data).decode("utf-8")}
        response = requests.get(raw, timeout=30)
        response.raise_for_status()
        content_type = (response.headers.get("content-type") or "").split(";")[0].strip().lower()
        if content_type.startswith("image/"):
            mime_type = content_type
        return {"type": "image", "mime_type": mime_type, "data": base64.b64encode(response.content).decode("utf-8")}
    except Exception as exc:
        print("GOOGLE IMAGE REFERENCE LOAD FAILED:", type(exc).__name__)
        return {}


# =====================================================
# PYTHON-БЛОК: google_extract_images
# Выполняет отдельный шаг backend-логики SYLVEX.
# Связан с API, базой данных, провайдерами или подготовкой данных для Mini App.
# =====================================================
def google_extract_images(data: dict) -> list:
    images = []

    # =====================================================
    # PYTHON-БЛОК: add_image
    # Выполняет отдельный шаг backend-логики SYLVEX.
    # Связан с API, базой данных, провайдерами или подготовкой данных для Mini App.
    # =====================================================
    def add_image(value, mime_type="image/png"):
        if isinstance(value, str) and value.strip():
            if value.startswith("http") or value.startswith("/"):
                images.append(value)
            else:
                images.append(f"data:{mime_type or 'image/png'};base64,{value}")

    # =====================================================
    # PYTHON-БЛОК: walk
    # Выполняет отдельный шаг backend-логики SYLVEX.
    # Связан с API, базой данных, провайдерами или подготовкой данных для Mini App.
    # =====================================================
    def walk(node):
        if isinstance(node, dict):
            mime_type = node.get("mime_type") or node.get("mimeType") or "image/png"
            if isinstance(node.get("output_image"), dict):
                walk(node.get("output_image"))
            elif isinstance(node.get("output_image"), str):
                add_image(node.get("output_image"), mime_type)
            for key in ("data", "imageBytes", "bytesBase64Encoded"):
                if node.get(key):
                    add_image(node.get(key), mime_type)
            inline = node.get("inlineData") or node.get("inline_data")
            if isinstance(inline, dict):
                add_image(inline.get("data"), inline.get("mimeType") or inline.get("mime_type") or mime_type)
            for key in ("url", "uri"):
                if isinstance(node.get(key), str) and node.get(key).strip():
                    images.append(node[key].strip())
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(data)
    clean = []
    for url in images:
        if url and url not in clean:
            clean.append(url)
    return clean


# =====================================================
# ЗАПРОС К AI-ПРОВАЙДЕРУ: call_google_image
# Формирует официальный payload, отправляет запрос во внешний AI API и нормализует ответ для общего lifecycle генерации.
# =====================================================
def call_google_image(frontend_model: str, provider_model: str, endpoint: str, prompt: str, payload: dict, size: str, count: int = 1) -> tuple[list, dict, dict]:
    headers = google_image_headers()
    if not headers:
        return [], image_error_response("google", frontend_model, provider_model, endpoint, "Provider API key is missing"), {}
    opts = payload.get("image_options") or {}
    key = google_image_frontend_model(frontend_model, provider_model)
    cfg = GOOGLE_IMAGE_MODEL_VARIANTS.get(key) or GOOGLE_IMAGE_MODEL_VARIANTS["nano_banana_2"]
    resolution = google_image_resolution(opts, key, provider_model)
    is_imagen = bool(cfg.get("imagen") or str(provider_model).startswith("imagen-"))
    aspect_ratio = google_image_aspect_ratio(size, imagen=is_imagen)

    if is_imagen:
        request_payload = {
            "instances": [{"prompt": prompt}],
            "parameters": {
                "sampleCount": max(1, min(int(count or 1), 4)),
                "aspectRatio": aspect_ratio,
            },
        }
        if key in {"imagen_4_standard", "imagen_4_ultra"}:
            request_payload["parameters"]["imageSize"] = resolution.upper()
        request_endpoint = endpoint.replace("{model}", provider_model)
    else:
        input_items = [{"type": "text", "text": prompt}]
        for ref in image_reference_urls(payload):
            part = google_local_or_remote_image_part(ref)
            if part:
                input_items.append(part)
        response_format = {
            "type": "image",
            "mime_type": "image/jpeg",
            "aspect_ratio": aspect_ratio,
            "image_size": google_interactions_image_size(resolution),
            "delivery": "inline",
        }
        request_payload = {
            "model": provider_model,
            "input": input_items,
            "store": False,
            "response_modalities": "image",
            "response_format": response_format,
        }
        request_endpoint = endpoint

    try:
        prostudio_debug(
            "GOOGLE_PROVIDER_REQUEST",
            endpoint=request_endpoint,
            frontend_model=frontend_model,
            provider_model=provider_model,
            aspect_ratio=aspect_ratio,
            resolution=resolution,
            count=count,
            is_imagen=is_imagen,
            has_references=bool(image_reference_urls(payload)),
            response_modalities=request_payload.get("response_modalities") if not is_imagen else [],
            response_format=request_payload.get("response_format") if not is_imagen else {},
        )
        response = requests.post(request_endpoint, headers=headers, data=json.dumps(request_payload), timeout=180)
    except requests.RequestException as exc:
        prostudio_error("GOOGLE_PROVIDER_REQUEST_FAILED", exc, endpoint=request_endpoint, frontend_model=frontend_model, provider_model=provider_model)
        return [], image_error_response("google", frontend_model, provider_model, request_endpoint, "Provider request failed", data={"body_preview": str(exc)[:1000]}), request_payload
    data = safe_provider_json(response, "google", request_endpoint)
    prostudio_debug(
        "GOOGLE_PROVIDER_RESPONSE",
        endpoint=request_endpoint,
        status_code=response.status_code,
        data_keys=sorted(data.keys()) if isinstance(data, dict) else [],
        image_count=len(google_extract_images(data)) if isinstance(data, dict) else 0,
    )
    if response.status_code >= 400 or data.get("ok") is False:
        provider_error = provider_error_text(data.get("error") or data.get("message") or data, "Provider request failed")
        return [], image_error_response("google", frontend_model, provider_model, request_endpoint, provider_error, response, data), request_payload
    return google_extract_images(data), {}, request_payload


# =====================================================
# PYTHON-БЛОК: sanitized_google_request_payload
# Выполняет отдельный шаг backend-логики SYLVEX.
# Связан с API, базой данных, провайдерами или подготовкой данных для Mini App.
# =====================================================
def sanitized_google_request_payload(request_payload: dict) -> dict:
    if not isinstance(request_payload, dict):
        return {}
    clean = json.loads(json.dumps(request_payload))
    input_items = clean.get("input")
    if isinstance(input_items, list):
        for item in input_items:
            if isinstance(item, dict) and item.get("data"):
                item["data"] = "[base64 image omitted]"
            if isinstance(item, dict) and isinstance(item.get("inlineData"), dict) and item["inlineData"].get("data"):
                item["inlineData"]["data"] = "[base64 image omitted]"
            if isinstance(item, dict) and isinstance(item.get("inline_data"), dict) and item["inline_data"].get("data"):
                item["inline_data"]["data"] = "[base64 image omitted]"
    return clean


# =====================================================
# ЗАПРОС К AI-ПРОВАЙДЕРУ: call_recraft_image
# Формирует официальный payload, отправляет запрос во внешний AI API и нормализует ответ для общего lifecycle генерации.
# =====================================================
def call_recraft_image(frontend_model: str, provider_model: str, endpoint: str, prompt: str, payload: dict, size: str, count: int = 1) -> tuple[list, dict, dict]:
    headers = recraft_headers()
    if not headers:
        return [], image_error_response("recraft", frontend_model, provider_model, endpoint, "Provider API key is missing"), {}
    opts = payload.get("image_options") or {}
    frontend_key = recraft_frontend_model(frontend_model, provider_model)
    seed_supported = bool((RECRAFT_MODEL_VARIANTS.get(frontend_key) or {}).get("seed"))
    seed = normalize_image_seed(opts.get("seed")) if seed_supported else None
    request_payload = {
        "prompt": prompt,
        "model": provider_model,
        "n": max(1, min(int(count or 1), 6)),
        "response_format": "url",
    }
    size_value = recraft_size_value(size)
    if size_value:
        request_payload["size"] = size_value
    if seed is not None:
        request_payload["random_seed"] = seed
    try:
        response = requests.post(endpoint, headers=headers, data=json.dumps(request_payload), timeout=120)
    except requests.RequestException as exc:
        return [], image_error_response("recraft", frontend_model, provider_model, endpoint, "Provider request failed", data={"body_preview": str(exc)[:1000]}), request_payload
    data = safe_provider_json(response, "recraft", endpoint)
    if response.status_code >= 400 or data.get("ok") is False:
        return [], image_error_response("recraft", frontend_model, provider_model, endpoint, data.get("error") or data.get("message") or "Provider request failed", response, data), request_payload
    images = normalize_image_response(data)
    return images, {}, request_payload


# =====================================================
# БАЛАНС И СТОИМОСТЬ: estimate_generation_cost
# Рассчитывает стоимость генерации, проверяет токены пользователя или фиксирует списание после успешного результата.
# =====================================================
def estimate_generation_cost(payload: dict) -> dict:
    mode = (payload.get("mode") or payload.get("category") or "").lower()
    if mode == "voice" and is_voice_video_voiceover_request(payload):
        return {"credits": 0, "cost_usd": 0, "generation_cost": ""}
    if mode == "video":
        return estimate_video_generation_cost(payload)
    if mode != "image":
        return {"credits": 0, "cost_usd": 0, "generation_cost": ""}
    opts = payload.get("image_options") or {}
    requested_model = opts.get("modelId") or opts.get("model_id") or payload.get("model")
    mapping = image_provider_mapping(requested_model) if requested_model else {}
    provider = (mapping.get("provider") or payload.get("provider") or "").strip().lower()
    api_model = mapping.get("provider_model") or ""
    if provider == "openai":
        count = safe_image_count(opts.get("count") or 1, default=1, max_count=4)
        quality = normalize_openai_image_quality(requested_model, api_model, opts)
        info = openai_image_cost_info(requested_model, api_model, quality, count)
        return {
            "credits": int(info.get("cost_credits") or info.get("cost") or 0),
            "cost_usd": info.get("cost_usd") or 0,
            "generation_cost": info.get("generation_cost") or "",
            "unit_cost_credits": info.get("unit_cost_credits") or 0,
            "unit_cost_usd": info.get("unit_cost_usd") or 0,
            "quality": info.get("quality") or "",
            "model_label": info.get("model_label") or "",
        }
    if provider == "recraft":
        count = safe_image_count(opts.get("count") or 1, default=1, max_count=4)
        info = recraft_cost_info(requested_model, api_model, count)
        return {
            "credits": int(info.get("cost_credits") or info.get("cost") or 0),
            "cost_usd": info.get("cost_usd") or 0,
            "generation_cost": info.get("generation_cost") or "",
            "unit_cost_credits": info.get("unit_cost_credits") or 0,
            "unit_cost_usd": info.get("unit_cost_usd") or 0,
            "model_label": info.get("model_label") or "",
        }
    if provider in ("byteplus", "bytedance") or re.search(r"seedream", f"{requested_model or ''} {api_model or ''}", re.I):
        count = safe_image_count(opts.get("count") or 1, default=1, max_count=4)
        info = seedream_cost_info(requested_model, api_model, count)
        return {
            "credits": int(info.get("cost_credits") or info.get("cost") or 0),
            "cost_usd": info.get("cost_usd") or 0,
            "generation_cost": info.get("generation_cost") or "",
            "unit_cost_credits": info.get("unit_cost_credits") or 0,
            "unit_cost_usd": info.get("unit_cost_usd") or 0,
            "model_label": info.get("model_label") or "",
        }
    if provider == "flux":
        count = safe_image_count(opts.get("count") or 1, default=1, max_count=4)
        info = flux_cost_info(requested_model, api_model, count)
        return {
            "credits": int(info.get("cost_credits") or info.get("cost") or 0),
            "cost_usd": info.get("cost_usd") or 0,
            "generation_cost": info.get("generation_cost") or "",
            "unit_cost_credits": info.get("unit_cost_credits") or 0,
            "unit_cost_usd": info.get("unit_cost_usd") or 0,
            "model_label": info.get("model_label") or "",
        }
    if provider == "qwen":
        count = safe_image_count(opts.get("count") or 1, default=1, max_count=4)
        info = qwen_cost_info(requested_model, api_model, count)
        return {
            "credits": int(info.get("cost_credits") or info.get("cost") or 0),
            "cost_usd": info.get("cost_usd") or 0,
            "generation_cost": info.get("generation_cost") or "",
            "unit_cost_credits": info.get("unit_cost_credits") or 0,
            "unit_cost_usd": info.get("unit_cost_usd") or 0,
            "model_label": info.get("model_label") or "",
        }
    if provider == "google":
        count = safe_image_count(opts.get("count") or 1, default=1, max_count=4)
        resolution = google_image_resolution(opts, requested_model, api_model)
        info = google_image_cost_info(requested_model, api_model, count, resolution, google_has_input_image(payload))
        return {
            "credits": int(info.get("cost_credits") or info.get("cost") or 0),
            "cost_usd": info.get("cost_usd") or 0,
            "generation_cost": info.get("generation_cost") or "",
            "unit_cost_credits": info.get("unit_cost_credits") or 0,
            "unit_cost_usd": info.get("unit_cost_usd") or 0,
            "resolution": info.get("resolution") or "",
            "model_label": info.get("model_label") or "",
            "input_image_credits": info.get("input_image_credits") or 0,
            "input_image_cost_included": bool(info.get("input_image_cost_included")),
        }
    if provider in ("grok", "xai"):
        count = safe_image_count(opts.get("count") or 1, default=1, max_count=4)
        resolution = grok_resolution_value(opts)
        info = grok_cost_info(requested_model, api_model, count, resolution, grok_has_input_image(payload))
        return {
            "credits": int(info.get("cost_credits") or info.get("cost") or 0),
            "cost_usd": info.get("cost_usd") or 0,
            "generation_cost": info.get("generation_cost") or "",
            "unit_cost_credits": info.get("unit_cost_credits") or 0,
            "unit_cost_usd": info.get("unit_cost_usd") or 0,
            "resolution": info.get("resolution") or "",
            "model_label": info.get("model_label") or "",
            "input_image_credits": info.get("input_image_credits") or 0,
            "input_image_surcharge_provisional": bool(info.get("input_image_surcharge_provisional")),
        }
    if provider != "ideogram":
        return {"credits": 0, "cost_usd": 0, "generation_cost": ""}
    count = safe_image_count(opts.get("count") or 1, default=1, max_count=4)
    speed = ideogram_rendering_speed(requested_model, api_model, opts)
    info = ideogram_cost_info(requested_model, api_model, speed, count, False)
    return {
        "credits": int(info.get("cost_credits") or info.get("cost") or 0),
        "cost_usd": info.get("cost_usd") or 0,
        "generation_cost": info.get("generation_cost") or "",
        "unit_cost_credits": info.get("unit_cost_credits") or 0,
        "unit_cost_usd": info.get("unit_cost_usd") or 0,
        "model_label": info.get("model_label") or "",
    }


# =====================================================
# ЗАГРУЗКА ФАЙЛОВ: ideogram_form_files
# Получает файл или ссылку, приводит её к безопасному формату и передаёт дальше в генерацию или сохранение.
# =====================================================
def ideogram_form_files(request_payload: dict) -> dict:
    return {
        key: (None, str(value))
        for key, value in (request_payload or {}).items()
        if value is not None and value != ""
    }


# =====================================================
# ЗАПРОС К AI-ПРОВАЙДЕРУ: call_ideogram_image
# Формирует официальный payload, отправляет запрос во внешний AI API и нормализует ответ для общего lifecycle генерации.
# =====================================================
def call_ideogram_image(frontend_model: str, provider_model: str, endpoint: str, prompt: str, payload: dict, size: str, count: int = 1) -> tuple[list, dict, dict]:
    headers = ideogram_headers(json_content=False)
    if not headers:
        return [], image_error_response("ideogram", frontend_model, provider_model, endpoint, "Provider API key is missing"), {}
    opts = payload.get("image_options") or {}
    frontend_key = ideogram_frontend_model(frontend_model, provider_model)
    rendering_speed = ideogram_rendering_speed(frontend_model, provider_model, opts)
    seed = normalize_image_seed(opts.get("seed")) if frontend_key == "ideogram_3_0" else None
    is_v4 = frontend_key == "ideogram_4_0"
    request_payload = {
        "rendering_speed": rendering_speed,
        **ideogram_size_params(frontend_model, provider_model, size),
    }
    if is_v4:
        request_payload["text_prompt"] = prompt
    else:
        request_payload["prompt"] = prompt
        request_payload["num_images"] = str(max(1, min(int(count or 1), 4)))
        if seed is not None:
            request_payload["seed"] = str(seed)

    images = []
    attempts = 1 if not is_v4 else max(1, min(int(count or 1), 4))
    try:
        for _ in range(attempts):
            response = requests.post(endpoint, headers=headers, files=ideogram_form_files(request_payload), timeout=120)
            data = safe_provider_json(response, "ideogram", endpoint)
            if response.status_code >= 400 or data.get("ok") is False:
                return [], image_error_response("ideogram", frontend_model, provider_model, endpoint, data.get("error") or "Provider request failed", response, data), request_payload
            for url in normalize_image_response(data):
                if url and url not in images:
                    images.append(url)
            if len(images) >= count:
                break
    except requests.RequestException as exc:
        return [], image_error_response("ideogram", frontend_model, provider_model, endpoint, "Provider request failed", data={"body_preview": str(exc)[:1000]}), request_payload
    return images, {}, request_payload


# =====================================================
# PYTHON-БЛОК: image_generation
# Выполняет отдельный шаг backend-логики SYLVEX.
# Связан с API, базой данных, провайдерами или подготовкой данных для Mini App.
# =====================================================
async def image_generation(payload: dict) -> dict:
    opts = payload.get("image_options") or {}
    prompt = build_image_prompt(payload)
    requested_model = opts.get("modelId") or opts.get("model_id") or payload.get("model")
    frontend_provider = (payload.get("provider") or "").strip().lower()
    prostudio_debug(
        "IMAGE_GENERATION_START",
        job_id=payload.get("job_id") or payload.get("generation_id") or "",
        requested_model=requested_model or "",
        frontend_provider=frontend_provider,
        size=opts.get("size") or opts.get("ratio") or "",
        count=opts.get("count") or 1,
        has_references=bool(image_reference_urls(payload)),
    )
    mapping = image_provider_mapping(requested_model) if requested_model else {}
    model_cfg = find_image_model(requested_model) or infer_image_model(requested_model, frontend_provider)

    if not mapping and requested_model:
        if frontend_provider in ("bytedance", "byteplus") or re.search(r"seedream", str(requested_model or ""), re.I):
            return unknown_byteplus_image_model_response(requested_model)
        return unknown_image_model_mapping_response(requested_model, frontend_provider)

    if not model_cfg and not mapping:
        return {
            "ok": False,
            "type": "image",
            "provider": frontend_provider,
            "model": requested_model or "",
            "error": "Unsupported image provider or model",
        }

    provider = (mapping.get("provider") or model_cfg.get("provider") or frontend_provider or "openai").strip().lower()
    api_model = mapping.get("provider_model") or model_cfg.get("api_model") or ""
    endpoint = mapping.get("endpoint") or model_cfg.get("endpoint") or ""

    if not api_model:
        return unknown_image_model_mapping_response(requested_model, provider)

    size = opts.get("size") or (model_cfg.get("sizes") or [{}])[0].get("id") or "1024x1024"
    count = safe_image_count(opts.get("count") or (model_cfg.get("counts") or [1])[0] or 1, default=1, max_count=4)
    prostudio_debug(
        "IMAGE_PROVIDER_RESOLVED",
        requested_model=requested_model or "",
        provider=provider,
        api_model=api_model,
        endpoint=endpoint,
        size=size,
        count=count,
    )

    if provider in ("byteplus", "bytedance") or re.search(r"seedream", api_model, re.I):
        if not BYTEPLUS_ARK_API_KEY:
            return image_error_response(provider, requested_model, api_model, f"{BYTEPLUS_ARK_ENDPOINT}/images/generations", "Provider API key is missing")

        images = []
        reference_images = image_reference_urls(payload)
        seed_supported = bool((SEEDREAM_MODEL_VARIANTS.get(seedream_frontend_model(requested_model, api_model)) or {}).get("seed"))
        seed = normalize_image_seed(opts.get("seed")) if seed_supported else None
        for index in range(1, count + 1):
            print(f"BYTEPLUS IMAGE REQUEST {index}/{count}")
            request_images, error = request_byteplus_seedream_image(api_model, prompt, reference_images, size=size, seed=seed)
            if request_images:
                for url in request_images:
                    if url and url not in images:
                        images.append(url)
                print(f"BYTEPLUS IMAGE SUCCESS {index}/{count}")
            else:
                print(f"BYTEPLUS IMAGE FAILED {index}/{count} {error or 'unknown error'}")
            if len(images) >= count:
                break
        if not images:
            return image_error_response(provider, requested_model, api_model, f"{BYTEPLUS_ARK_ENDPOINT}/images/generations", "Генерация не прошла. Проверь выбранную модель или backend-провайдер.")
        result = await finalize_image_result(payload, images[:count])
        result.update(seedream_cost_info(requested_model, api_model, len(images[:count])))
        result["provider"] = "bytedance"
        result["model"] = requested_model
        result["provider_model"] = api_model
        return result

    if provider == "openai":
        if not OPENAI_API_KEY:
            return image_error_response(provider, requested_model, api_model, f"{OPENAI_API_BASE}/images/generations", "Provider API key is missing")
        openai_size = normalize_openai_image_size(size, requested_model, api_model)
        openai_quality = normalize_openai_image_quality(requested_model, api_model, opts)
        reference_images = image_reference_urls(payload)

        if reference_images:
            endpoint = f"{OPENAI_API_BASE}/images/edits"
            files = [
                file_part
                for file_part in (
                    openai_image_reference_file(url, index)
                    # One scene/source image plus avatar and three character references.
                    for index, url in enumerate(reference_images[:5])
                )
                if file_part
            ]
            if not files:
                return image_error_response(provider, requested_model, api_model, endpoint, "Не удалось обработать загруженное изображение.")

            request_data = {
                "model": api_model,
                "prompt": prompt,
                "size": openai_size,
                "quality": openai_quality,
                "n": "1",
                "input_fidelity": "high",
            }
            response = None
            request_exception = None
            for attempt in range(1, 3):
                try:
                    response = requests.post(
                        endpoint,
                        headers=openai_auth_headers(),
                        data=request_data,
                        files=files,
                        timeout=int(os.getenv("OPENAI_IMAGE_EDIT_TIMEOUT", "300")),
                    )
                    if response.status_code not in {408, 409, 429, 500, 502, 503, 504}:
                        break
                    print("OPENAI IMAGE EDIT TRANSIENT RESPONSE:", {
                        "attempt": attempt,
                        "status_code": response.status_code,
                        "model": api_model,
                    })
                except requests.RequestException as exc:
                    request_exception = exc
                    print("OPENAI IMAGE EDIT TRANSIENT ERROR:", {
                        "attempt": attempt,
                        "error": type(exc).__name__,
                        "model": api_model,
                    })
                if attempt < 2:
                    time.sleep(2)
            if response is None:
                return image_error_response(
                    provider,
                    requested_model,
                    api_model,
                    endpoint,
                    request_exception or "Provider request failed",
                    data={"body_preview": str(request_exception or "")[:1000]},
                )
            if response.status_code >= 400:
                data = safe_provider_json(response, provider, endpoint)
                return image_error_response(provider, requested_model, api_model, endpoint, data.get("error") or data.get("message") or "Provider request failed", response, data)
            data = safe_provider_json(response, provider, endpoint)
            images = normalize_image_response(data)
            print("OPENAI IMAGE EDIT PAYLOAD:", {"frontend_model": requested_model, "provider_model": api_model, "endpoint": endpoint, "references": len(files), "has_image": bool(images)})
            if images:
                result = await finalize_image_result(payload, images[:1])
                result.update(openai_image_cost_info(requested_model, api_model, openai_quality, 1))
                result["provider"] = "openai"
                result["model"] = requested_model
                result["provider_model"] = api_model
                result["quality"] = openai_quality
                result["request_payload"] = {**request_data, "image_count": len(files)}
                return result
            return image_error_response(provider, requested_model, api_model, endpoint, "Provider returned no image")

        endpoint = f"{OPENAI_API_BASE}/images/generations"
        images = []
        last_payload = {}
        for index in range(1, count + 1):
            request_payload = {
                "model": api_model,
                "prompt": prompt,
                "size": openai_size,
                "quality": openai_quality,
                "n": 1,
            }
            last_payload = request_payload
            try:
                response = requests.post(
                    endpoint,
                    headers=openai_headers(),
                    data=json.dumps(request_payload),
                    timeout=120,
                )
            except requests.RequestException as exc:
                return image_error_response(provider, requested_model, api_model, endpoint, "Provider request failed", data={"body_preview": str(exc)[:1000]})
            if response.status_code >= 400:
                data = safe_provider_json(response, provider, endpoint)
                return image_error_response(provider, requested_model, api_model, endpoint, data.get("error") or data.get("message") or "Provider request failed", response, data)
            data = safe_provider_json(response, provider, endpoint)
            if data.get("ok") is False:
                return image_error_response(provider, requested_model, api_model, endpoint, data.get("error") or "Provider returned invalid response", data=data)
            for url in normalize_image_response(data):
                if url and url not in images:
                    images.append(url)
            print("OPENAI IMAGE PAYLOAD:", {"frontend_model": requested_model, "provider_model": api_model, "endpoint": endpoint, "attempt": index, "payload": request_payload, "has_image": bool(images)})
            if len(images) >= count:
                break
        if images:
            final_images = images[:count]
            result = await finalize_image_result(payload, final_images)
            result.update(openai_image_cost_info(requested_model, api_model, openai_quality, len(final_images) or count))
            result["provider"] = "openai"
            result["model"] = requested_model
            result["provider_model"] = api_model
            result["quality"] = openai_quality
            result["request_payload"] = last_payload
            return result
        return image_error_response(provider, requested_model, api_model, endpoint, "Provider returned no image")

    if provider == "flux":
        images = []
        last_payload = {}
        for index in range(1, count + 1):
            request_images, error, request_payload = call_flux_image(requested_model, api_model, endpoint, prompt, payload, size)
            last_payload = request_payload
            print("FLUX IMAGE PAYLOAD:", {"frontend_model": requested_model, "provider_model": api_model, "endpoint": endpoint, "attempt": index, "payload": request_payload})
            if error:
                return error
            for url in request_images or []:
                if url and url not in images:
                    images.append(url)
            if len(images) >= count:
                break
        if images:
            final_images = images[:count]
            result = await finalize_image_result(payload, final_images)
            result.update(flux_cost_info(requested_model, api_model, len(final_images) or count))
            result["provider"] = "flux"
            result["model"] = requested_model
            result["provider_model"] = api_model
            result["request_payload"] = last_payload
            return result
        return image_error_response(provider, requested_model, api_model, endpoint, "Provider returned no image")

    if provider == "recraft":
        images, error, request_payload = call_recraft_image(requested_model, api_model, endpoint, prompt, payload, size, count)
        print("RECRAFT IMAGE PAYLOAD:", {"frontend_model": requested_model, "provider_model": api_model, "endpoint": endpoint, "payload": request_payload})
        if error:
            return error
        if images:
            final_images = images[:count]
            result = await finalize_image_result(payload, final_images)
            result.update(recraft_cost_info(requested_model, api_model, len(final_images) or count))
            result["provider"] = "recraft"
            result["model"] = requested_model
            result["provider_model"] = api_model
            return result
        return image_error_response(provider, requested_model, api_model, endpoint, "Provider returned no image")

    if provider == "google":
        images, error, request_payload = call_google_image(requested_model, api_model, endpoint, prompt, payload, size, count)
        print("GOOGLE IMAGE PAYLOAD:", {
            "frontend_model": requested_model,
            "provider_model": api_model,
            "endpoint": endpoint,
            "payload_keys": list((request_payload or {}).keys()),
            "has_references": bool(image_reference_urls(payload)),
        })
        if error:
            return error
        if images:
            final_images = images[:count]
            opts = payload.get("image_options") or {}
            result = await finalize_image_result(payload, final_images)
            result.update(google_image_cost_info(
                requested_model,
                api_model,
                len(final_images) or count,
                google_image_resolution(opts, requested_model, api_model),
                google_has_input_image(payload),
            ))
            result["provider"] = "google"
            result["model"] = requested_model
            result["provider_model"] = api_model
            result["request_payload"] = sanitized_google_request_payload(request_payload)
            return result
        return image_error_response(provider, requested_model, api_model, endpoint, "Provider returned no image")

    if provider == "qwen":
        images, error, request_payload = call_qwen_image(requested_model, api_model, endpoint, prompt, payload, size, count)
        qwen_content = (((request_payload or {}).get("input") or {}).get("messages") or [{}])[0].get("content") or []
        qwen_payload_image_count = sum(
            1 for item in qwen_content if isinstance(item, dict) and bool(item.get("image"))
        )
        print("QWEN IMAGE PAYLOAD:", {
            "frontend_model": requested_model,
            "provider_model": (request_payload or {}).get("model") or api_model,
            "endpoint": endpoint,
            "image_count": qwen_payload_image_count,
            "has_references": qwen_payload_image_count > 0,
            "content_types": [
                "image" if isinstance(item, dict) and item.get("image") else "text"
                for item in qwen_content
            ],
        })
        if error:
            return error
        if images:
            final_images = images[:count]
            result = await finalize_image_result(payload, final_images)
            result.update(qwen_cost_info(requested_model, api_model, len(final_images) or count))
            result["provider"] = "qwen"
            result["model"] = requested_model
            result["provider_model"] = (request_payload or {}).get("model") or api_model
            result["request_payload"] = request_payload
            return result
        return image_error_response(provider, requested_model, api_model, endpoint, "Provider returned no image")

    if provider in ("grok", "xai"):
        images, error, request_payload = call_grok_image(requested_model, api_model, endpoint, prompt, payload, size, count)
        print("GROK IMAGE PAYLOAD:", {
            "frontend_model": requested_model,
            "provider_model": api_model,
            "endpoint": endpoint,
            "payload": request_payload,
            "has_input_image": bool(request_payload.get("image_url")),
        })
        if error:
            return error
        if images:
            final_images = images[:count]
            result = await finalize_image_result(payload, final_images)
            result.update(grok_cost_info(
                requested_model,
                api_model,
                len(final_images) or count,
                request_payload.get("resolution") or "1k",
                bool(request_payload.get("image_url")),
            ))
            result["provider"] = "grok"
            result["model"] = requested_model
            result["provider_model"] = api_model
            result["request_payload"] = request_payload
            return result
        return image_error_response(provider, requested_model, api_model, endpoint, "Provider returned no image")

    if provider == "ideogram":
        images, error, request_payload = call_ideogram_image(requested_model, api_model, endpoint, prompt, payload, size, count)
        print("IDEOGRAM IMAGE PAYLOAD:", {"frontend_model": requested_model, "provider_model": api_model, "endpoint": endpoint, "payload": request_payload})
        if error:
            return error
        if images:
            final_images = images[:count]
            result = await finalize_image_result(payload, final_images)
            result.update(ideogram_cost_info(
                requested_model,
                api_model,
                request_payload.get("rendering_speed") or "TURBO",
                len(final_images) or count,
                False,
            ))
            result["provider"] = "ideogram"
            result["model"] = requested_model
            result["provider_model"] = api_model
            return result
        return image_error_response(provider, requested_model, api_model, endpoint, "Provider returned no image")

    return image_error_response(provider, requested_model, api_model, endpoint, "Image provider adapter is not connected")

# =====================================================
# API ENDPOINT: public_prostudio_image_capabilities
# Принимает HTTP-запрос от Mini App или Telegram Bot.
# Маршрут FastAPI: @app.get("/api/public/prostudio/image-capabilities")
# Проверяет входные данные, работает с базой/провайдерами и возвращает JSON-ответ фронтенду.
# =====================================================
@app.get("/api/public/prostudio/image-capabilities")
# =====================================================
# PYTHON-БЛОК: public_prostudio_image_capabilities
# Выполняет отдельный шаг backend-логики SYLVEX.
# Связан с API, базой данных, провайдерами или подготовкой данных для Mini App.
# =====================================================
async def public_prostudio_image_capabilities():
    return get_image_capabilities()

# =====================================================
# PYTHON-БЛОК: prostudio_video_templates_from_env
# Выполняет отдельный шаг backend-логики SYLVEX.
# Связан с API, базой данных, провайдерами или подготовкой данных для Mini App.
# =====================================================
def prostudio_video_templates_from_env() -> list:
    raw = os.getenv("VIDEO_TEMPLATES_JSON", "").strip()
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
    except Exception as exc:
        prostudio_error("VIDEO_TEMPLATES_JSON_PARSE_FAILED", exc)
        return []
    items = parsed.get("templates") if isinstance(parsed, dict) else parsed
    if not isinstance(items, list):
        return []

    # =====================================================
    # PYTHON-БЛОК: _template_int
    # Выполняет отдельный шаг backend-логики SYLVEX.
    # Связан с API, базой данных, провайдерами или подготовкой данных для Mini App.
    # =====================================================
    def _template_int(value, default=0):
        try:
            if isinstance(value, str):
                match = re.search(r"\d+", value)
                return int(match.group(0)) if match else default
            return int(value)
        except Exception:
            return default

    templates = []
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        template_id = str(item.get("id") or f"template_{index + 1}").strip()
        title = str(item.get("title") or item.get("name") or template_id).strip()
        preview_video = str(item.get("preview_video") or item.get("previewVideo") or item.get("video") or "").strip()
        reference_video = str(item.get("reference_video") or item.get("referenceVideo") or preview_video).strip()
        if not template_id or not title or not reference_video:
            continue

        ratios = item.get("ratios") or item.get("aspect_ratios") or item.get("supported_ratios") or ["16:9", "1:1", "9:16"]
        if not isinstance(ratios, list):
            ratios = [ratios]
        ratios = [str(r).strip() for r in ratios if str(r or "").strip() in {"16:9", "1:1", "9:16"}]
        if not ratios:
            ratios = ["16:9"]

        models = item.get("models") or item.get("supported_models") or []
        if not isinstance(models, list):
            models = [models]
        models = [str(model).strip() for model in models if str(model or "").strip()]
        preferred_model = "kling_motion_3_0"
        duration = _template_int(item.get("duration"), 5) or 5
        resolution = str(item.get("resolution") or "720p").strip() or "720p"
        default_ratio = str(item.get("aspect_ratio") or item.get("ratio") or ratios[0]).strip()
        if default_ratio not in ratios:
            default_ratio = ratios[0]

        cost_payload = {
            "mode": "video",
            "provider": "kling",
            "model": preferred_model,
            "prompt": "",
            "video_options": {
                "model": preferred_model,
                "generation_mode": "motion_control",
                "mode": "motion_control",
                "ratio": default_ratio,
                "duration": duration,
                "resolution": resolution,
                "start_image": "template-image",
                "input_video": reference_video,
                "video_url": reference_video,
                "video_input": True,
                "motion_control": True,
                "character_orientation": "image",
            },
        }
        cost = estimate_video_generation_cost(cost_payload)

        fallback_cost = _template_int(item.get("cost_credits") or item.get("cost"), 0)
        calculated_cost = _template_int(cost.get("credits"), 0)

        templates.append({
            "id": template_id,
            "title": title,
            "description": str(item.get("description") or "").strip(),
            "preview_video": preview_video,
            "reference_video": reference_video,
            "aspect_ratio": default_ratio,
            "ratios": ratios,
            "models": ["kling_motion_3_0"],
            "preferred_model": preferred_model,
            "duration": duration,
            "resolution": resolution,
            "cost": calculated_cost or fallback_cost,
            "cost_credits": calculated_cost or fallback_cost,
            "generation_cost": cost.get("generation_cost") or (f"{fallback_cost} ⚡" if fallback_cost else ""),
        })
    return templates

# =====================================================
# PYTHON-БЛОК: prostudio_builtin_video_template_slots
# Выполняет отдельный шаг backend-логики SYLVEX.
# Связан с API, базой данных, провайдерами или подготовкой данных для Mini App.
# =====================================================
def prostudio_builtin_video_template_slots() -> list:
    russian_titles = [
        "Сброс сумки", "Ангел на шоссе", "Чемпион мира", "Воздушная доставка", "Масштабный отлёт камеры",
        "Баннер над городом", "Ужас в зеркале", "ASMR-распаковка", "Фотобудка", "Кубок мира LEGO",
        "Американские горки", "Рамен в Токио", "Полёт над облаками", "Уличная афиша", "Модное селфи",
        "Выход из отеля", "Красная дорожка", "На вершине Земли", "Полёт ангела", "Бой в снежном тоннеле",
        "Музыка в поле", "Погружение в радужку", "За кулисами кино", "Ночное видение", "Горный поход",
        "Концертная арена", "Y2K-глитч", "3D-каркас", "Городской таймлапс", "Высокая мода",
        "Магия огня", "Мир в бутылке", "Гигантская доставка", "Фэнтези-джунгли", "Горное приключение",
        "Поездка по открытой дороге", "Камера 360°", "Подъём камеры", "Эффект удара", "Обзор модного образа",
        "Улыбка на стадионе", "Кошачья встреча", "Звезда в аэропорту", "Реакция болельщика", "Празднование гола",
        "Дождь конфетти", "Спокойствие в огне", "Взлёт дрона", "Золотые частицы", "Реклама на билборде",
        "Эпичный отлёт дрона", "Акробатический переворот", "Приземление продукта", "Превращение улыбки", "Премьера на красной дорожке",
        "Кинематографическая погоня", "Одежда в полёте", "Белки и продукт", "Жидкий хром", "От героя к Земле",
        "Фотокопии", "Слёзы", "K-pop-фанкам", "Весёлые мордочки", "Надутые щёки", "Рокер-питомец",
    ]
    templates = []
    base_dir = WEBAPP_DIR / "assets" / "video-templates"
    for index in range(1, 68):
        slot = f"{index:02d}"
        template_id = f"builtin_video_template_{index}"
        slot_dir = base_dir / slot
        preview_file = slot_dir / "preview.mp4"
        if not preview_file.exists() and (slot_dir / "poster.mp4").exists():
            preview_file = slot_dir / "poster.mp4"
        poster_file = slot_dir / "poster.jpg"
        metadata_file = slot_dir / "template.json"
        prompt_file = slot_dir / "prompt.txt"
        preview_exists = preview_file.exists()
        poster_exists = poster_file.exists()
        if not preview_exists:
            continue
        metadata = {}
        if metadata_file.exists():
            try:
                parsed = json.loads(metadata_file.read_text(encoding="utf-8"))
                if isinstance(parsed, dict):
                    metadata = parsed
            except Exception as exc:
                prostudio_error("VIDEO_TEMPLATE_METADATA_FAILED", exc, slot=slot)
        prompt = ""
        if prompt_file.exists():
            try:
                prompt = prompt_file.read_text(encoding="utf-8").strip()
            except Exception as exc:
                prostudio_error("VIDEO_TEMPLATE_PROMPT_FAILED", exc, slot=slot)
        output = metadata.get("output") if isinstance(metadata.get("output"), dict) else {}
        effect_scene = str(metadata.get("effect_scene") or "").strip()
        is_provider_effect = index in {64, 65, 66} and bool(effect_scene)
        title = russian_titles[index - 1] if index <= len(russian_titles) else str(metadata.get("name") or template_id)
        folder_description = str(metadata.get("description") or "").strip()
        if is_provider_effect:
            descriptions = {
                64: "Оживляет мордочку питомца фирменным эффектом Wiggle Faces.",
                65: "Создаёт забавную анимацию лица с надутыми щёками.",
                66: "Превращает фото питомца в энергичную рок-анимацию.",
            }
            description = folder_description or descriptions[index]
        else:
            description = folder_description or f"Загрузите изображение для видео «{title}»."
        item = {
            "id": template_id,
            "slot": slot,
            "title": title,
            "name": title,
            "description": description,
            "prompt": prompt or str(metadata.get("description") or title),
            "preview_exists": preview_exists,
            "poster_exists": poster_exists,
            "preview_video": f"/webapp/assets/video-templates/{slot}/{preview_file.name}" if preview_exists else "",
            "reference_video": "" if is_provider_effect else f"/webapp/assets/video-templates/{slot}/{preview_file.name}",
            "poster_url": f"/webapp/assets/video-templates/{slot}/poster.jpg" if poster_exists else "",
            "upload_path": f"webapp/assets/video-templates/{slot}/{preview_file.name}",
            "aspect_ratio": str(output.get("aspect_ratio") or "9:16"),
            "ratios": ["16:9", "1:1", "9:16"],
            "duration": int(output.get("duration") or 5),
            "resolution": "720p",
            "catalog_type": "kling_effect" if is_provider_effect else "video_template",
            "is_kling_effect": is_provider_effect,
            "effect_scene": effect_scene if is_provider_effect else "",
            "mode": "std" if is_provider_effect else "",
            "model_name": "kling-v1-6" if is_provider_effect else "",
            "input_count": int((metadata.get("input") or {}).get("count") or 1) if isinstance(metadata.get("input"), dict) else 1,
            "models": ["kling_effects"] if is_provider_effect else ["kling_o3_omni"],
            "preferred_model": "kling_effects" if is_provider_effect else "kling_o3_omni",
            "cost": 95,
            "cost_credits": 95,
            "generation_cost": "95 ⚡",
        }
        templates.append(item)
    return templates

def prostudio_kling_effects_library() -> list:
    effects_file = WEBAPP_DIR / "providers" / "kling" / "effects" / "effects.json"
    if not effects_file.exists():
        return []
    try:
        raw = json.loads(effects_file.read_text(encoding="utf-8"))
    except Exception as exc:
        prostudio_error("KLING_EFFECTS_JSON_PARSE_FAILED", exc)
        return []
    items = raw.get("effects") if isinstance(raw, dict) else raw
    if not isinstance(items, list):
        return []

    effects = []
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        effect_id = str(item.get("id") or item.get("effect_scene") or item.get("scene") or f"effect_{index + 1}").strip()
        if not effect_id:
            continue
        title = str(item.get("title") or item.get("name") or effect_id).strip()
        effect_dir = WEBAPP_DIR / "providers" / "kling" / "effects" / effect_id
        preview_file = effect_dir / "preview.mp4"
        poster_file = effect_dir / "poster.jpg"
        preview_video = str(item.get("preview_video") or item.get("previewVideo") or item.get("demo_video") or item.get("video_url") or "").strip()
        poster_url = str(item.get("poster_url") or item.get("poster") or item.get("thumbnail_url") or item.get("preview_image") or "").strip()
        if not preview_video and preview_file.exists():
            preview_video = f"/webapp/providers/kling/effects/{effect_id}/preview.mp4"
        if not poster_url and poster_file.exists():
            poster_url = f"/webapp/providers/kling/effects/{effect_id}/poster.jpg"
        ratios = item.get("ratios") or item.get("aspect_ratios") or [str(item.get("aspect_ratio") or "9:16")]
        if not isinstance(ratios, list):
            ratios = [ratios]
        ratios = [str(r).strip() for r in ratios if str(r or "").strip() in {"16:9", "1:1", "9:16"}]
        if not ratios:
            ratios = ["16:9", "1:1", "9:16"]
        aspect_ratio = str(item.get("aspect_ratio") or item.get("ratio") or ratios[0]).strip()
        if aspect_ratio not in ratios:
            aspect_ratio = ratios[0]
        cost_credits = int(item.get("cost_credits") or item.get("cost") or 0)
        effects.append({
            "id": effect_id,
            "effect_scene": effect_id,
            "title": title,
            "name": title,
            "description": str(item.get("description") or item.get("hint") or "").strip(),
            "preview_video": preview_video,
            "poster_url": poster_url,
            "aspect_ratio": aspect_ratio,
            "ratios": ratios,
            "duration": int(item.get("duration") or 5),
            "resolution": str(item.get("resolution") or "720p"),
            "mode": str(item.get("mode") or "std"),
            "model_name": str(item.get("model_name") or "kling-v1-6"),
            "input_count": int(item.get("input_count") or item.get("images_required") or (2 if effect_id in {"hug", "kiss", "heart_gesture", "handshake"} else 1)),
            "cost": cost_credits,
            "cost_credits": cost_credits,
            "generation_cost": item.get("generation_cost") or (f"{cost_credits} ⚡" if cost_credits else ""),
            "upload_path": f"webapp/providers/kling/effects/{effect_id}/preview.mp4",
        })
    return effects


@app.get("/api/public/prostudio/kling/effects")
async def public_prostudio_kling_effects():
    return JSONResponse(
        {
            "ok": True,
            "source": "local_effects_json",
            "note": "Kling public API exposes Video Effects task creation/query by effect_scene; no public catalog-list endpoint is documented.",
            "effects": prostudio_kling_effects_library(),
        },
        headers={"Cache-Control": f"public, max-age={VIDEO_TEMPLATE_CATALOG_CACHE_TTL}"},
    )


# =====================================================
# API ENDPOINT: public_prostudio_video_templates
# Принимает HTTP-запрос от Mini App или Telegram Bot.
# Маршрут FastAPI: @app.get("/api/public/prostudio/video-templates")
# Проверяет входные данные, работает с базой/провайдерами и возвращает JSON-ответ фронтенду.
# =====================================================
@app.get("/api/public/prostudio/video-templates")
# =====================================================
# PYTHON-БЛОК: public_prostudio_video_templates
# Выполняет отдельный шаг backend-логики SYLVEX.
# Связан с API, базой данных, провайдерами или подготовкой данных для Mini App.
# =====================================================
async def public_prostudio_video_templates():
    now = time.time()
    cached = VIDEO_TEMPLATE_CATALOG_CACHE.get("value")
    if cached is not None and now < float(VIDEO_TEMPLATE_CATALOG_CACHE.get("expires_at") or 0):
        return JSONResponse(cached, headers={"Cache-Control": f"public, max-age={VIDEO_TEMPLATE_CATALOG_CACHE_TTL}"})
    payload = {
        "ok": True,
        "templates": prostudio_video_templates_from_env() + prostudio_builtin_video_template_slots(),
    }
    VIDEO_TEMPLATE_CATALOG_CACHE["value"] = payload
    VIDEO_TEMPLATE_CATALOG_CACHE["expires_at"] = now + VIDEO_TEMPLATE_CATALOG_CACHE_TTL
    return JSONResponse(payload, headers={"Cache-Control": f"public, max-age={VIDEO_TEMPLATE_CATALOG_CACHE_TTL}"})


def prostudio_photo_catalog_items() -> list:
    base_dir = WEBAPP_DIR / "assets" / "photo-catalog"
    base_dir.mkdir(parents=True, exist_ok=True)
    image_extensions = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
    items = []
    for slot_dir in sorted((path for path in base_dir.iterdir() if path.is_dir()), key=lambda path: path.name.lower()):
        metadata = {}
        metadata_file = slot_dir / "template.json"
        if metadata_file.exists():
            try:
                parsed = json.loads(metadata_file.read_text(encoding="utf-8"))
                if isinstance(parsed, dict):
                    metadata = parsed
            except Exception as exc:
                prostudio_error("PHOTO_CATALOG_TEMPLATE_JSON_FAILED", exc, slot=slot_dir.name)
        image_file = None
        preferred_names = ("photo.jpg", "photo.jpeg", "photo.png", "photo.webp", "preview.jpg", "preview.png", "preview.webp")
        for name in preferred_names:
            candidate = slot_dir / name
            if candidate.exists():
                image_file = candidate
                break
        if image_file is None:
            image_file = next((path for path in sorted(slot_dir.iterdir()) if path.is_file() and path.suffix.lower() in image_extensions), None)
        if image_file is None:
            continue
        slot = slot_dir.name
        image_url = f"/webapp/assets/photo-catalog/{urllib.parse.quote(slot, safe='')}/{urllib.parse.quote(image_file.name, safe='')}"
        items.append({
            "id": str(metadata.get("id") or f"photo_{slot}"),
            "slot": slot,
            "title": str(metadata.get("title") or metadata.get("name") or f"Фото {slot}"),
            "description": str(metadata.get("description") or ""),
            "prompt": str(metadata.get("prompt") or ""),
            "aspect_ratio": str(metadata.get("aspect_ratio") or metadata.get("ratio") or ""),
            "image_url": image_url,
            "model": str(metadata.get("model") or ""),
        })
    return items


@app.get("/api/public/prostudio/photo-catalog")
async def public_prostudio_photo_catalog():
    now = time.time()
    cached = PHOTO_CATALOG_CACHE.get("value")
    if cached is not None and now < float(PHOTO_CATALOG_CACHE.get("expires_at") or 0):
        return JSONResponse(cached, headers={"Cache-Control": f"public, max-age={PHOTO_CATALOG_CACHE_TTL}"})
    payload = {"ok": True, "photos": prostudio_photo_catalog_items()}
    PHOTO_CATALOG_CACHE["value"] = payload
    PHOTO_CATALOG_CACHE["expires_at"] = now + PHOTO_CATALOG_CACHE_TTL
    return JSONResponse(payload, headers={"Cache-Control": f"public, max-age={PHOTO_CATALOG_CACHE_TTL}"})


@app.get("/api/public/prostudio/photo-tool-demos")
async def public_prostudio_photo_tool_demos():
    """Return the first two still images in every photo-tool folder as before/after."""
    base_dir = WEBAPP_DIR / "assets" / "photo-tools"
    image_extensions = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".avif"}
    tool_aliases = {
        "try-on": "try_on",
        "remove-background": "remove_bg",
        "replace-character": "replace_character",
        "animate-photo": "animate_photo",
    }

    def natural_key(path: pathlib.Path):
        return [int(part) if part.isdigit() else part.lower() for part in re.split(r"(\d+)", path.name)]

    demos = {}
    if base_dir.exists():
        for folder in sorted((path for path in base_dir.iterdir() if path.is_dir()), key=lambda path: path.name.lower()):
            images = sorted(
                (path for path in folder.iterdir() if path.is_file() and path.suffix.lower() in image_extensions),
                key=natural_key,
            )
            if len(images) < 2:
                continue
            urls = [
                f"/webapp/assets/photo-tools/{urllib.parse.quote(folder.name, safe='')}/{urllib.parse.quote(path.name, safe='')}"
                for path in images[:2]
            ]
            demos[tool_aliases.get(folder.name, folder.name.replace("-", "_"))] = {
                "before": urls[0],
                "after": urls[1],
            }
    return JSONResponse({"ok": True, "demos": demos}, headers={"Cache-Control": "public, max-age=60"})


def prostudio_quick_image_catalog_items() -> dict:
    base_dir = WEBAPP_DIR / "assets" / "quick-generator" / "image"
    image_extensions = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
    result = {"references": [], "styles": [], "popular_references": [], "objects": []}
    category_dirs = {
        "references": "references",
        "styles": "styles",
        "popular_references": "popular-references",
        "objects": "objects",
    }
    style_names = {
        "01":"Noir Trio", "02":"Neutral Editorial", "03":"Balcony Story", "04":"Neon City", "05":"Equestrian Noir",
        "06":"Miniature Executive", "07":"Lime Editorial", "08":"Glossy Doll", "09":"Midnight Player", "10":"Monumental Steps",
        "11":"Tropical Taxi", "12":"Paris Café", "13":"Lake Luxury", "14":"Identity Scan", "15":"Rugged Portrait",
        "16":"Library Chic", "17":"Motion Echo", "18":"Dual Neon", "19":"Orange Studio", "20":"Cyber Magenta",
        "21":"Soft 3D Muse", "22":"Glam 3D", "23":"Braided 3D", "24":"Copper 3D", "25":"Fairytale 3D",
        "26":"Night Drive", "27":"Cyan Motion", "28":"Executive Portrait", "29":"Beanie Avatar", "30":"Paris Noir",
        "31":"Cloud Corridor", "32":"Instagram Portal", "33":"Lime Supercar", "34":"Electric Blue", "35":"Neon Halo",
        "36":"Pixel Dissolve", "37":"Cinematic Player", "38":"Fashion Doll", "39":"Graphic Sketch", "40":"Sunset Street",
        "41":"Mirror Story", "42":"Future Pop", "43":"Monochrome Agent", "44":"Modern Gentleman", "45":"Signature Portrait",
    }
    for category, folder_name in category_dirs.items():
        category_dir = base_dir / folder_name
        if not category_dir.exists():
            continue
        slots = sorted(category_dir.iterdir(), key=lambda path: path.name.lower())
        for slot_path in slots:
            if slot_path.name.startswith("."):
                continue
            metadata = {}
            search_dir = slot_path if slot_path.is_dir() else category_dir
            metadata_file = search_dir / "template.json"
            if metadata_file.exists():
                try:
                    parsed = json.loads(metadata_file.read_text(encoding="utf-8"))
                    if isinstance(parsed, dict):
                        metadata = parsed
                except Exception as exc:
                    # Many supplied templates contain literal line breaks inside the prompt string.
                    # Preserve that prompt instead of dropping the complete style metadata.
                    try:
                        raw = metadata_file.read_text(encoding="utf-8")
                        id_match = re.search(r'"id"\s*:\s*"([^"]+)"', raw)
                        title_match = re.search(r'"title"\s*:\s*"([^"]*)"', raw)
                        prompt_match = re.search(r'"prompt"\s*:\s*"([\s\S]*)"\s*}\s*$', raw)
                        if not prompt_match:
                            prompt_match = re.search(r'"prompt"\s*:\s*"([\s\S]*)$', raw)
                        prompt_value = prompt_match.group(1) if prompt_match else ""
                        prompt_value = re.sub(r'"?\s*}\s*$', '', prompt_value).strip()
                        metadata = {
                            "id": id_match.group(1) if id_match else "",
                            "title": title_match.group(1) if title_match else "",
                            "prompt": prompt_value.replace('\\"', '"'),
                        }
                    except Exception:
                        prostudio_error("QUICK_IMAGE_CATALOG_TEMPLATE_JSON_FAILED", exc, slot=slot_path.name)
            image_file = slot_path if slot_path.is_file() and slot_path.suffix.lower() in image_extensions else None
            if image_file is None and slot_path.is_dir():
                image_file = next((path for path in sorted(slot_path.iterdir()) if path.is_file() and path.suffix.lower() in image_extensions), None)
            if image_file is None:
                continue
            relative = image_file.relative_to(WEBAPP_DIR).parts
            image_url = "/webapp/" + "/".join(urllib.parse.quote(part, safe="") for part in relative)
            slot = slot_path.stem if slot_path.is_file() else slot_path.name
            default_title = f"{slot}"
            metadata_title = str(metadata.get("title") or metadata.get("name") or "").strip()
            if category == "styles":
                metadata_title = style_names.get(slot, metadata_title or "Visual Style")
            elif category == "objects" and (not metadata_title or metadata_title.lower() == "название фотографии"):
                prompt_lower = str(metadata.get("prompt") or "").lower()
                if "magenta" in prompt_lower and "cyan" in prompt_lower and "portrait" in prompt_lower:
                    metadata_title = "Dual Neon Portrait"
                elif "portrait" in prompt_lower:
                    metadata_title = "Editorial Portrait"
                elif "product" in prompt_lower:
                    metadata_title = "Studio Product"
                else:
                    metadata_title = "Visual Object"
            result[category].append({
                "id": str(metadata.get("id") or f"quick_{category}_{slot}"),
                "title": metadata_title or default_title,
                "description": str(metadata.get("description") or ""),
                "prompt": str(metadata.get("prompt") or ""),
                "image_url": image_url,
                "source": "quick_folder",
            })
    return result


@app.get("/api/public/prostudio/quick-image-catalog")
async def public_prostudio_quick_image_catalog():
    now = time.time()
    cached = QUICK_IMAGE_CATALOG_CACHE.get("value")
    if cached is not None and now < float(QUICK_IMAGE_CATALOG_CACHE.get("expires_at") or 0):
        return JSONResponse(cached, headers={"Cache-Control": f"public, max-age={PHOTO_CATALOG_CACHE_TTL}"})
    payload = {"ok": True, "catalog": prostudio_quick_image_catalog_items()}
    QUICK_IMAGE_CATALOG_CACHE["value"] = payload
    QUICK_IMAGE_CATALOG_CACHE["expires_at"] = now + PHOTO_CATALOG_CACHE_TTL
    return JSONResponse(payload, headers={"Cache-Control": f"public, max-age={PHOTO_CATALOG_CACHE_TTL}"})

# =====================================================
# API ENDPOINT: download_prostudio_image
# Принимает HTTP-запрос от Mini App или Telegram Bot.
# Маршрут FastAPI: @app.get("/api/public/prostudio/download-image")
# Проверяет входные данные, работает с базой/провайдерами и возвращает JSON-ответ фронтенду.
# =====================================================
@app.get("/api/public/prostudio/download-image")
# =====================================================
# PYTHON-БЛОК: download_prostudio_image
# Выполняет отдельный шаг backend-логики SYLVEX.
# Связан с API, базой данных, провайдерами или подготовкой данных для Mini App.
# =====================================================
async def download_prostudio_image(url: str):
    return await download_prostudio_content(url=url, kind="image")

# =====================================================
# API ENDPOINT: download_prostudio_content
# Принимает HTTP-запрос от Mini App или Telegram Bot.
# Маршрут FastAPI: @app.get("/api/public/prostudio/download-content")
# Проверяет входные данные, работает с базой/провайдерами и возвращает JSON-ответ фронтенду.
# =====================================================
@app.get("/api/public/prostudio/download-content")
# =====================================================
# PYTHON-БЛОК: download_prostudio_content
# Выполняет отдельный шаг backend-логики SYLVEX.
# Связан с API, базой данных, провайдерами или подготовкой данных для Mini App.
# =====================================================
async def download_prostudio_content(url: str, kind: str = "file"):
    import mimetypes
    from urllib.parse import urlparse
    import httpx
    from fastapi import HTTPException
    from fastapi.responses import Response

    parsed = urlparse(url or "")
    if parsed.scheme not in ("http", "https"):
        raise HTTPException(status_code=400, detail="invalid_url")

    try:
        async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
            r = await client.get(url)
    except Exception:
        raise HTTPException(status_code=502, detail="content_download_failed")

    if r.status_code >= 400 or not r.content:
        raise HTTPException(status_code=502, detail="content_download_failed")

    safe_kind = (kind or "file").lower()
    if safe_kind not in ("image", "video", "audio", "file"):
        safe_kind = "file"
    fallback_types = {
        "image": "image/jpeg",
        "video": "video/mp4",
        "audio": "audio/mpeg",
        "file": "application/octet-stream",
    }
    content_type = r.headers.get("content-type") or mimetypes.guess_type(parsed.path)[0] or fallback_types[safe_kind]
    ext = mimetypes.guess_extension(content_type.split(";")[0].strip())
    if not ext:
        ext = { "image": ".jpg", "video": ".mp4", "audio": ".mp3", "file": ".bin" }[safe_kind]
    filename = f"sylvex-{safe_kind}{ext}"
    return Response(
        content=r.content,
        media_type=content_type,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store",
        },
    )

# =====================================================
# API ENDPOINT: public_prostudio_generate
# Принимает HTTP-запрос от Mini App или Telegram Bot.
# Маршрут FastAPI: @app.post("/api/public/prostudio/generate")
# Проверяет входные данные, работает с базой/провайдерами и возвращает JSON-ответ фронтенду.
# =====================================================
@app.post("/api/public/prostudio/estimate")
async def public_prostudio_estimate(request: Request):
    """Return the existing authoritative Pro Studio estimate without creating a job."""
    try:
        payload = await request.json()
        estimate = estimate_generation_cost(payload if isinstance(payload, dict) else {})
        return {"ok": True, **estimate}
    except Exception as exc:
        prostudio_error("GENERATION_ESTIMATE_FAILED", exc)
        return JSONResponse({"ok": False, "error": "generation_estimate_failed"}, status_code=400)


@app.post("/api/public/prostudio/grid/plan")
async def public_prostudio_grid_plan(request: Request):
    """Build an editable Grid draft with the existing SYLVEX text provider; never starts media generation."""
    try:
        body = await request.json()
        task = str((body or {}).get("task") or "").strip()
        if not task:
            return JSONResponse({"ok": False, "error": "task_required"}, status_code=400)
        planner_prompt = f"""
You are SYLVEX Grid Planner. Analyze the user's creative task and return ONLY valid JSON, without markdown.
Never start generation. Build an editable draft only.

If the desired final format is ambiguous, return:
{{"action":"clarify","question":"one short question in the user's language"}}

If it is clear, return:
{{
  "action":"plan",
  "nodes":[
    {{"key":"text_1","type":"text","title":"short localized title","instruction":"what this text block produces","output":"ready-to-use semantic prompt or text"}},
    {{"key":"video_1","type":"video","title":"short localized title","prompt":"ready-to-edit final prompt"}}
  ],
  "edges":[{{"from":"text_1","output":"text","to":"video_1","input":"text"}}]
}}

Allowed node types: text, image, video, music, voice. The Task node already exists; never include it.
Allowed outputs: text, image, video, audio. Allowed inputs: task, text, lyrics, image, audio.
Use the shortest useful workflow. A clear video request normally needs Text -> Video. If an image source is materially needed, use Text -> Image -> Video and optionally a second Text -> Video motion prompt.
For every Text node, output must contain the actual ready-to-use content, not technical settings such as aspect ratio, resolution, quality, duration or result count.
Media generation must not start. Prompts must remain editable.

User task:
{task}
""".strip()
        generated = text_generation({
            "prompt": planner_prompt,
            "mode": "text",
            "category": "text",
            "model": str((body or {}).get("model") or "gpt-5.5"),
            "provider": "sylvex-router",
            "text_options": {"tool": "text", "style": "neutral", "format": "json", "language": "auto"},
            "history": [],
            "attachment": None,
        })
        if not generated.get("ok"):
            return JSONResponse(generated, status_code=502)
        raw = str(generated.get("text") or "").strip()
        if raw.startswith("```"):
            raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.I | re.S).strip()
        plan = json.loads(raw)
        if not isinstance(plan, dict) or plan.get("action") not in {"clarify", "plan"}:
            raise ValueError("invalid_planner_response")
        if plan.get("action") == "clarify":
            question = str(plan.get("question") or "").strip()
            if not question:
                raise ValueError("planner_question_missing")
            return {"ok": True, "action": "clarify", "question": question}
        allowed_types = {"text", "image", "video", "music", "voice"}
        allowed_inputs = {"task", "text", "lyrics", "image", "audio"}
        allowed_outputs = {"text", "image", "video", "audio"}
        clean_nodes = []
        keys = set()
        for index, item in enumerate(plan.get("nodes") or []):
            if not isinstance(item, dict) or str(item.get("type") or "") not in allowed_types:
                continue
            key = re.sub(r"[^a-zA-Z0-9_-]", "", str(item.get("key") or f"node_{index}"))[:64]
            if not key or key in keys:
                continue
            keys.add(key)
            clean_nodes.append({
                "key": key,
                "type": str(item.get("type")),
                "title": str(item.get("title") or item.get("type"))[:80],
                "instruction": str(item.get("instruction") or "")[:6000],
                "output": str(item.get("output") or "")[:12000],
                "prompt": str(item.get("prompt") or "")[:12000],
            })
        clean_edges = []
        for item in plan.get("edges") or []:
            if not isinstance(item, dict):
                continue
            source, target = str(item.get("from") or ""), str(item.get("to") or "")
            source_output, target_input = str(item.get("output") or "text"), str(item.get("input") or "text")
            if source in keys and target in keys and source != target and source_output in allowed_outputs and target_input in allowed_inputs:
                clean_edges.append({"from": source, "output": source_output, "to": target, "input": target_input})
        if not clean_nodes:
            raise ValueError("planner_nodes_missing")
        return {"ok": True, "action": "plan", "nodes": clean_nodes, "edges": clean_edges, "provider": generated.get("provider"), "model": generated.get("model")}
    except (json.JSONDecodeError, ValueError) as exc:
        prostudio_error("GRID_PLANNER_INVALID_RESPONSE", exc)
        return JSONResponse({"ok": False, "error": "planner_invalid_response", "message": "Не удалось построить цепочку. Попробуйте уточнить задачу."}, status_code=502)
    except Exception as exc:
        prostudio_error("GRID_PLANNER_FAILED", exc)
        return JSONResponse({"ok": False, "error": "planner_failed", "message": "Не удалось построить цепочку."}, status_code=500)


@app.post("/api/public/home-idea/route")
async def public_home_idea_route(request: Request):
    """Conversational SYLVEX guide: clarify an idea and prepare, but never launch, a generator."""
    try:
        body = await request.json()
        message = str((body or {}).get("message") or "").strip()
        history = (body or {}).get("history") or []
        attachment = (body or {}).get("attachment") or None
        if not message and not attachment:
            return JSONResponse({"ok": False, "error": "message_required"}, status_code=400)
        instruction = f"""
Ты — SYLVEX AI, персональный творческий навигатор внутри Mini App. Никогда не называй себя OpenAI или ChatGPT.
Помоги понять задачу и направь пользователя в правильный генератор. Ответь ТОЛЬКО JSON без markdown:
{{"reply":"краткий естественный ответ или один уточняющий вопрос","ready":true,"mode":"image|video|music|voice|text|grid","model":"идентификатор модели","prompt":"полностью сформулированный запрос для выбранного генератора"}}
Если данных недостаточно, ready=false, mode/model/prompt оставь пустыми и задай только один самый важный вопрос.
Если задача ясна, ready=true. Рекомендуемые модели: image=seedream_5_0_pro, video=seedance_2_0, music=suno_chirp_5_5, voice=elevenlabs_eleven_v3, text=gpt-5.6. Для сложной цепочки нескольких видов контента используй grid.
Не запускай генерацию и не обещай, что она уже началась.
Сообщение пользователя: {message}
""".strip()
        result = await asyncio.to_thread(text_generation, {
            "prompt": instruction, "mode": "text", "category": "text", "model": "gpt-5.6",
            "provider": "openai", "text_options": {"tool": "text", "format": "json", "style": "neutral"},
            "history": history[-12:] if isinstance(history, list) else [], "attachment": attachment,
        })
        if not result.get("ok"):
            return JSONResponse(result, status_code=502)
        raw = str(result.get("text") or "").strip()
        if raw.startswith("```"):
            raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.I | re.S).strip()
        route = json.loads(raw)
        allowed_modes = {"image", "video", "music", "voice", "text", "grid"}
        mode = str(route.get("mode") or "")
        ready = bool(route.get("ready")) and mode in allowed_modes
        return {"ok": True, "reply": str(route.get("reply") or "Готов помочь."), "ready": ready,
                "mode": mode if ready else "", "model": str(route.get("model") or "") if ready else "",
                "prompt": str(route.get("prompt") or "") if ready else ""}
    except Exception as exc:
        prostudio_error("HOME_IDEA_ROUTE_FAILED", exc)
        return JSONResponse({"ok": False, "error": "idea_route_failed", "message": "SYLVEX временно не смог обработать идею."}, status_code=500)


@app.post("/api/public/home-idea/realtime")
async def public_home_idea_realtime(request: Request):
    """Create a protected OpenAI Realtime WebRTC session; the standard API key stays on the server."""
    if not OPENAI_API_KEY:
        return JSONResponse({"ok": False, "error": "openai_not_configured"}, status_code=503)
    sdp = (await request.body()).decode("utf-8", errors="ignore").strip()
    if not sdp:
        return JSONResponse({"ok": False, "error": "sdp_required"}, status_code=400)
    user_id = str(request.query_params.get("telegram_id") or "guest")
    safety_id = hashlib.sha256(("sylvex:" + user_id).encode()).hexdigest()
    session = {
        "type": "realtime", "model": os.getenv("OPENAI_REALTIME_MODEL", "gpt-realtime-2.1"),
        "instructions": "Ты SYLVEX AI. Общайся по-русски естественно и кратко. Помоги пользователю уточнить творческую идею и выбрать создание изображения, видео, музыки, озвучки, текста или сетку. Никогда не называй себя OpenAI или ChatGPT. Не запускай генерацию.",
        "audio": {"input": {"transcription": {"model": "gpt-4o-mini-transcribe"}}, "output": {"voice": "marin"}},
    }
    def create_call():
        return requests.post("https://api.openai.com/v1/realtime/calls",
            headers={"Authorization": f"Bearer {OPENAI_API_KEY}", "OpenAI-Safety-Identifier": safety_id},
            files={"sdp": (None, sdp), "session": (None, json.dumps(session))}, timeout=30)
    try:
        response = await asyncio.to_thread(create_call)
        return Response(content=response.content, status_code=response.status_code,
                        media_type=response.headers.get("content-type", "application/sdp"))
    except Exception as exc:
        prostudio_error("HOME_IDEA_REALTIME_FAILED", exc)
        return JSONResponse({"ok": False, "error": "realtime_unavailable"}, status_code=502)


@app.post("/api/public/prostudio/generate")
# =====================================================
# PYTHON-БЛОК: public_prostudio_generate
# Выполняет отдельный шаг backend-логики SYLVEX.
# Связан с API, базой данных, провайдерами или подготовкой данных для Mini App.
# =====================================================
async def public_prostudio_generate(request: Request):
    payload = await request.json()
    telegram_id = int(payload.get("telegram_id") or 0)
    mode = (payload.get("mode") or payload.get("category") or "text").lower()
    category = (payload.get("category") or mode).lower()
    prompt = (payload.get("prompt") or "").strip()
    selected_model = (payload.get("model") or "").strip()
    selected_provider = (payload.get("provider") or "sylvex-router").strip().lower()
    image_options = payload.get("image_options") or {}
    video_options = payload.get("video_options") or {}
    voice_options = payload.get("voice_options") or {}
    reference_images = (
        _json_list(image_options.get("referenceImageUrls"))
        or _json_list(image_options.get("referenceImages"))
        or _json_list(image_options.get("characterReferences"))
        or _json_list(image_options.get("objectReferences"))
    )
    video_references = (
        video_options.get("reference_images")
        or video_options.get("referenceImageUrls")
        or []
    )
    video_template = video_options.get("video_template") if isinstance(video_options.get("video_template"), dict) else {}
    video_media = (
        video_options.get("start_image")
        or video_options.get("end_image")
        or video_options.get("input_video")
        or video_options.get("video_url")
        or video_options.get("image_url")
        or video_options.get("character_image")
        or video_template.get("reference_video")
        or video_template.get("video_url")
        or video_template.get("template_video_url")
        or video_template.get("preview_video")
    )

    print("PRO STUDIO BACKEND ROUTER:", {
        "mode": mode,
        "category": category,
        "provider": selected_provider,
        "model": selected_model,
        "has_image_options": bool(image_options),
        "has_video_options": bool(video_options),
    })

    generation_modes = {"image", "video", "music", "voice"}
    text_modes = {"text", "chat", "pro", "lite"}
    try:
        active_job = get_active_prostudio_job(telegram_id) if telegram_id else {}
    except Exception as exc:
        prostudio_error("ACTIVE_JOB_PRECHECK_FAILED", exc, telegram_id=telegram_id)
        return JSONResponse({
            "ok": False,
            "error": "active_job_lookup_failed",
            "message": "Не удалось проверить активную генерацию.",
        }, status_code=503)
    if active_job:
        return JSONResponse({
            "ok": False,
            "error": "active_generation_exists",
            "message": "У пользователя уже есть активная генерация.",
            "active_job_id": active_job.get("id") or "",
            "status": active_job.get("status") or "queued",
        }, status_code=409)
    if mode in generation_modes and is_internal_ui_model(selected_model):
        return invalid_generation_model_response(selected_model)

    voice_media = voice_options.get("attachment") or voice_options.get("uploads")
    if not prompt and not payload.get("attachment") and not voice_media and not reference_images and not video_references and not video_media:
        return JSONResponse({"ok": False, "error": "Prompt or attachment is required"}, status_code=400)

    if mode == "image":
        try:
            normalize_payload_image_seed(payload)
            image_options = payload.get("image_options") or {}
        except ValueError as exc:
            return JSONResponse(
                {"ok": False, "type": "image", "error": str(exc)},
                status_code=400,
            )
        feature_error = validate_image_feature_request(payload)
        if feature_error:
            return JSONResponse(feature_error, status_code=400)

        telegram_id = int(payload.get("telegram_id") or 0)
        cost_estimate = estimate_generation_cost(payload)
        required_credits = int(cost_estimate.get("credits") or 0)
        if required_credits > 0:
            user_state = get_user_state(telegram_id) if telegram_id else {"balance": 0}
            balance = int(user_state.get("balance") or 0)
            if balance < required_credits:
                return JSONResponse({
                    "ok": False,
                    "paywall": True,
                    "insufficient_balance": True,
                    "error": "Недостаточно токенов для генерации",
                    "required_credits": required_credits,
                    "balance": balance,
                    "generation_cost": cost_estimate.get("generation_cost") or "",
                    "cost_usd": cost_estimate.get("cost_usd") or 0,
                    "shop_url": SHOP_WEBAPP_URL,
                }, status_code=402)

    if mode == "video":
        telegram_id = int(payload.get("telegram_id") or 0)
        cost_estimate = estimate_generation_cost(payload)
        required_credits = int(cost_estimate.get("credits") or 0)
        if required_credits > 0:
            user_state = get_user_state(telegram_id) if telegram_id else {"balance": 0}
            balance = int(user_state.get("balance") or 0)
            if balance < required_credits:
                return JSONResponse({
                    "ok": False,
                    "paywall": True,
                    "insufficient_balance": True,
                    "error": "Недостаточно токенов для генерации",
                    "required_credits": required_credits,
                    "balance": balance,
                    "generation_cost": cost_estimate.get("generation_cost") or "",
                    "cost_usd": cost_estimate.get("cost_usd") or 0,
                    "shop_url": SHOP_WEBAPP_URL,
                }, status_code=402)

    if mode in generation_modes:
        telegram_id = int(payload.get("telegram_id") or 0)
        user_state = get_user_state(telegram_id) if telegram_id else {"balance": 0}
        balance = int(user_state.get("balance") or 0)
        if balance <= 0:
            return JSONResponse({
                "ok": False,
                "paywall": True,
                "insufficient_balance": True,
                "error": "Недостаточно токенов для генерации",
                "required_credits": 1,
                "balance": balance,
                "shop_url": SHOP_WEBAPP_URL,
            }, status_code=402)

    prostudio_debug(
        "GENERATE_ACCEPTED",
        mode=mode,
        category=category,
        provider=selected_provider,
        model=selected_model,
        telegram_id=int(payload.get("telegram_id") or 0),
        worker_enabled=PROSTUDIO_WORKER_ENABLED,
    )
    if mode in text_modes:
        request_key = str(payload.get("client_request_id") or "").strip()
        cache_key = f"{int(payload.get('telegram_id') or 0)}:{request_key}" if request_key else ""
        if cache_key and cache_key in PROSTUDIO_TEXT_RESPONSE_CACHE:
            return PROSTUDIO_TEXT_RESPONSE_CACHE[cache_key]
        if not selected_model or is_internal_ui_model(selected_model):
            payload["model"] = "gpt-5.5"
        result = text_generation(payload)
        if not result.get("ok"):
            return JSONResponse(result, status_code=502)
        result["conversation_id"] = save_prostudio_message(payload, result)
        if cache_key:
            if len(PROSTUDIO_TEXT_RESPONSE_CACHE) > 200:
                PROSTUDIO_TEXT_RESPONSE_CACHE.clear()
            PROSTUDIO_TEXT_RESPONSE_CACHE[cache_key] = result
        return result

    # Worker owns Telegram delivery. Persist this flag in request_json before
    # the job is inserted so provider adapters cannot send the result early.
    if mode in generation_modes:
        payload["skip_telegram"] = True
    try:
        job_id = create_prostudio_generation_job(payload) if mode in generation_modes else ""
    except ActiveProstudioJobError as exc:
        return JSONResponse({
            "ok": False,
            "error": "active_generation_exists",
            "message": "У пользователя уже есть активная генерация.",
            "active_job_id": exc.job_id,
            "status": exc.status,
        }, status_code=409)
    except Exception:
        return JSONResponse({
            "ok": False,
            "error": "generation_job_create_failed",
            "message": "Не удалось создать задачу генерации.",
        }, status_code=500)
    if job_id:
        payload["job_id"] = job_id
        payload["generation_id"] = job_id
        prostudio_debug("GENERATE_JOB_CREATED", job_id=job_id, mode=mode, worker_enabled=PROSTUDIO_WORKER_ENABLED)
    if job_id:
        log_user_event(
            int(payload.get("telegram_id") or 0),
            "miniapp",
            "generation",
            "generation_queued",
            {"job_id": job_id, "mode": mode, "model": selected_model, "provider": selected_provider},
        )

    prostudio_debug("GENERATE_QUEUED_FOR_WORKER", job_id=job_id)

    return {
        "ok": True,
        "job_id": job_id,
        "generation_id": job_id,
        "status": "queued"
    }


def resolve_prostudio_provider_for_slot(payload: dict, mode: str, selected_model: str, selected_provider: str) -> str:
    """Resolve the real provider before any external generation request."""
    candidate = selected_provider
    if mode == "image":
        if is_seedream_request(payload):
            candidate = "byteplus"
        else:
            mapping = image_provider_mapping(selected_model) if selected_model else {}
            candidate = mapping.get("provider") or candidate
    elif mode in {"text", "chat", "pro", "lite"}:
        config = TEXT_MODEL_VARIANTS.get(selected_model) or TEXT_MODEL_VARIANTS.get("gpt-5.5") or {}
        candidate = config.get("provider") or candidate

    normalized = normalize_provider(candidate)
    if normalized and normalized not in {"SYLVEX_ROUTER", "AUTO"}:
        return normalized

    # Last-resort model inference covers old queued payloads which predate the
    # normalized provider field. It never changes the provider payload itself.
    haystack = f"{selected_provider} {selected_model}".lower()
    model_hints = (
        ("seedream", "BYTEPLUS"), ("byteplus", "BYTEPLUS"),
        ("gemini", "GEMINI"), ("imagen", "GEMINI"), ("nano_banana", "GEMINI"), ("lyria", "GEMINI"),
        ("gpt", "OPENAI"), ("openai", "OPENAI"), ("qwen", "QWEN"),
        ("grok", "GROK"), ("xai", "GROK"), ("kling", "KLING"),
        ("runway", "RUNWAY"), ("eleven", "ELEVENLABS"), ("heygen", "HEYGEN"),
        ("hedra", "HEDRA"), ("higgsfield", "HIGGSFIELD"), ("luma", "LUMA"),
        ("flux", "FLUX"), ("ideogram", "IDEOGRAM"), ("recraft", "RECRAFT"),
        ("fashn", "FASHN"), ("suno", "SUNO"), ("udio", "SUNO"),
    )
    for hint, provider in model_hints:
        if hint in haystack:
            return provider
    raise RuntimeError(
        f"Cannot apply global provider limit: unresolved provider "
        f"for mode={mode}, model={selected_model}, provider={selected_provider}"
    )


async def dispatch_prostudio_provider_request(
    job_id: str,
    payload: dict,
    mode: str,
    selected_model: str,
    selected_provider: str,
    text_modes: set,
) -> dict:
    """Perform one initial provider submission/generation attempt."""
    result = None
    if mode == "image" and is_seedream_request(payload):
        prostudio_debug("JOB_PROVIDER_DISPATCH", job_id=job_id, mode=mode, provider="bytedance", model=selected_model, route="generateBytePlusSeedreamImage")
        result = await generateBytePlusSeedreamImage(payload)
    elif mode == "image":
        prostudio_debug("JOB_PROVIDER_DISPATCH", job_id=job_id, mode=mode, provider=selected_provider, model=selected_model, route="image_generation")
        result = await image_generation(payload)
    elif mode == "video":
        prostudio_debug("JOB_PROVIDER_DISPATCH", job_id=job_id, mode=mode, provider=selected_provider, model=selected_model, route="video_generation")
        result = await run_provider_coroutine_off_loop(lambda: video_generation(payload))
    elif mode == "music":
        prostudio_debug("JOB_PROVIDER_DISPATCH", job_id=job_id, mode=mode, provider=selected_provider, model=selected_model, route="audio_generation")
        result = await audio_generation(payload)
    elif mode == "voice":
        if is_voice_video_voiceover_request(payload):
            input_video = voice_uploaded_video_url(payload)
            if not input_video:
                result = {"ok": False, "type": "video", "error": "Для режима «Озвучить видео» нужно загрузить видео"}
            else:
                voice_payload = json.loads(json.dumps(payload))
                voice_payload["skip_telegram"] = True
                voice_options = voice_payload.setdefault("voice_options", {})
                voice_options["elevenlabs_tool"] = "text_to_speech"
                voice_options["runway_tool"] = "text_to_speech"
                voice_options["upload_purpose"] = "voiceover"
                voice_options["uploadPurpose"] = "voiceover"
                voice_options["uploads"] = []
                voice_options["attachment"] = None
                prostudio_debug("JOB_PROVIDER_DISPATCH", job_id=job_id, mode=mode, provider=selected_provider, model=selected_model, route="voice_video_voiceover_tts")
                audio_result = await audio_generation(voice_payload)
                if not isinstance(audio_result, dict) or not audio_result.get("ok"):
                    result = audio_result if isinstance(audio_result, dict) else {"ok": False, "type": "voice", "error": "Не удалось создать озвучку для видео"}
                else:
                    prostudio_debug("JOB_PROVIDER_DISPATCH", job_id=job_id, mode=mode, provider="local-ffmpeg", model=selected_model, route="voice_video_voiceover_mux")
                    result = build_voice_video_voiceover_result(payload, audio_result, input_video)
            if isinstance(result, dict):
                result["voice_video_voiceover"] = True
        else:
            prostudio_debug("JOB_PROVIDER_DISPATCH", job_id=job_id, mode=mode, provider=selected_provider, model=selected_model, route="voice_generation")
            result = await audio_generation(payload)
    elif mode in text_modes:
        if not selected_model or is_internal_ui_model(selected_model):
            payload["model"] = "gpt-5.5"
        result = await asyncio.to_thread(text_generation, payload)
    else:
        result = {"ok": False, "error": "Unknown generation mode", "mode": mode}

    return result


def _log_circuit_transition(stage: str, provider: str, job_id: str, attempt: int, status_code, delay: float, outcome: dict):
    prostudio_debug(
        stage,
        provider=provider,
        job_id=job_id,
        attempt=attempt,
        status_code=status_code or "",
        delay=round(float(delay or 0), 3),
        circuit_state=outcome.get("state") or "CLOSED",
        failure_count=int(outcome.get("failure_count") or 0),
        worker_id=WORKER_ID,
    )


async def provider_call_with_retry(job_id: str, provider: str, operation) -> dict:
    """Run one logical provider operation with bounded transient retries."""
    async def record_outcome(transient: bool):
        return await asyncio.to_thread(
            circuit_record_outcome, DATABASE_URL, provider, job_id, transient
        )

    return await run_with_provider_retry(
        provider=provider,
        job_id=job_id,
        operation=operation,
        record_outcome=record_outcome,
        log=prostudio_debug,
        worker_id=WORKER_ID,
    )


async def run_prostudio_provider_request(
    job_id: str,
    payload: dict,
    mode: str,
    selected_model: str,
    selected_provider: str,
    text_modes: set,
    provider: str,
) -> tuple[dict, str]:
    """Submit and poll a provider with retry while owning one provider slot."""
    result = await provider_call_with_retry(
        job_id,
        provider,
        lambda: dispatch_prostudio_provider_request(
            job_id, payload, mode, selected_model, selected_provider, text_modes
        ),
    )
    if not isinstance(result, dict) or not result.get("ok"):
        return result, "failed"

    final_status = normalize_generation_status(result, mode)
    result["job_id"] = job_id
    result["generation_id"] = job_id
    result["status"] = final_status
    prostudio_debug("JOB_STATUS_NORMALIZED", job_id=job_id, mode=mode, final_status=final_status)

    if final_status == "provider_processing":
        update_prostudio_generation_job(job_id, "provider_processing", result=result)
        log_user_event(
            int(payload.get("telegram_id") or 0), "worker", "generation",
            "generation_provider_processing",
            {"job_id": job_id, "mode": mode, "task_id": result.get("task_id") or result.get("workId"), "poll_url": result.get("poll_url")},
        )
        while True:
            await asyncio.sleep(5)
            heartbeat_prostudio_generation_job(job_id)
            poll = await provider_call_with_retry(
                job_id,
                provider,
                lambda: run_provider_coroutine_off_loop(lambda: poll_video_generation(result)),
            )
            if not poll.get("ok"):
                return poll, "failed"
            status = poll.get("status")
            if status == "completed":
                return poll, "completed"
            if status == "failed":
                return poll, "failed"

    return result, final_status


# New async function for background job processing
# =====================================================
# ФОНОВАЯ ЗАДАЧА: process_prostudio_generation
# Обрабатывает job после нажатия пользователем кнопки генерации: запускает провайдера, ждёт результат и сохраняет итог.
# =====================================================
async def process_prostudio_generation(job_id: str, payload: dict):
    prostudio_debug(
        "JOB_PROCESS_ENTER",
        job_id=job_id,
        payload_job_id=payload.get("job_id") or "",
        mode=payload.get("mode") or payload.get("category") or "",
        model=payload.get("model") or "",
        provider=payload.get("provider") or "",
    )
    try:
        payload["job_id"] = job_id
        payload["generation_id"] = job_id
        mode = (payload.get("mode") or payload.get("category") or "text").lower()
        category = (payload.get("category") or mode).lower()
        prompt = (payload.get("prompt") or "").strip()
        selected_model = (payload.get("model") or "").strip()
        selected_provider = (payload.get("provider") or "sylvex-router").strip().lower()
        if payload.get("load_test") and not PROSTUDIO_MOCK_GENERATION:
            # A load-test job must never fall through to a real provider, even
            # if the CLI and worker were accidentally configured differently.
            update_prostudio_generation_job(
                job_id,
                "failed",
                error={
                    "ok": False,
                    "mock": True,
                    "error": "PROSTUDIO_MOCK_GENERATION is disabled on worker",
                },
            )
            prostudio_debug(
                "MOCK_GENERATION_REJECTED",
                job_id=job_id,
                telegram_id=int(payload.get("telegram_id") or 0),
                reason="mock_generation_disabled",
            )
            return
        if PROSTUDIO_MOCK_GENERATION:
            mock_duration_seconds = random.randint(5, 15)
            prostudio_debug(
                "MOCK_GENERATION_STARTED",
                job_id=job_id,
                telegram_id=int(payload.get("telegram_id") or 0),
                mode=mode,
                model=selected_model,
                duration_seconds=mock_duration_seconds,
                mock=True,
            )
            await asyncio.sleep(mock_duration_seconds)
            mock_result = {
                "ok": True,
                "mock": True,
                "type": mode,
                "status": "completed",
                "job_id": job_id,
                "generation_id": job_id,
                "provider": "mock",
                "model": selected_model,
                "duration_seconds": mock_duration_seconds,
                "balance_charged": False,
                "sent_to_telegram": False,
            }
            update_prostudio_generation_job(job_id, "completed", result=mock_result)
            prostudio_debug(
                "MOCK_GENERATION_COMPLETED",
                job_id=job_id,
                telegram_id=int(payload.get("telegram_id") or 0),
                mode=mode,
                model=selected_model,
                duration_seconds=mock_duration_seconds,
                mock=True,
            )
            return
        prompt_report = optimize_prompt_for_model(
            prompt,
            model=selected_model,
            provider=selected_provider,
            mode=mode,
        )
        prostudio_debug(
            "PROMPT_OPTIMIZER",
            job_id=job_id,
            mode=mode,
            model=selected_model,
            provider=selected_provider,
            original_length=prompt_report.get("original_length"),
            model_limit=prompt_report.get("limit"),
            optimized=prompt_report.get("optimized"),
            new_length=prompt_report.get("optimized_length"),
            failed_reason=prompt_report.get("failed_reason") or "",
        )
        if prompt and not prompt_report.get("ok"):
            provider_name = "Kling" if "kling" in f"{selected_provider} {selected_model}".lower() else "выбранной модели"
            error_result = {
                "ok": False,
                "type": mode,
                "provider": selected_provider,
                "model": selected_model,
                "error": (
                    f"Ваше описание слишком большое для {provider_name}.\n\n"
                    f"Максимальный размер описания для {provider_name} — {prompt_report.get('limit')} символов.\n\n"
                    "Попробуйте сделать описание немного короче или выберите другую модель."
                ),
                "raw_error": "Prompt optimization failed to reach limit",
                "prompt_limit": prompt_report.get("limit"),
                "prompt_length": prompt_report.get("original_length"),
                "optimized_length": prompt_report.get("optimized_length"),
            }
            update_prostudio_generation_job(job_id, "failed", error=error_result)
            log_prostudio_error(payload, error_result, job_id=job_id)
            return
        if prompt_report.get("optimized"):
            prompt = prompt_report.get("prompt") or prompt
            payload["prompt"] = prompt
            payload["prompt_optimization"] = prompt_report
        image_options = payload.get("image_options") or {}
        video_options = payload.get("video_options") or {}
        reference_images = (
            _json_list(image_options.get("referenceImageUrls"))
            or _json_list(image_options.get("referenceImages"))
            or _json_list(image_options.get("characterReferences"))
            or _json_list(image_options.get("objectReferences"))
        )
        video_references = (
            video_options.get("reference_images")
            or video_options.get("referenceImageUrls")
            or []
        )
        video_template = video_options.get("video_template") if isinstance(video_options.get("video_template"), dict) else {}
        video_media = (
            video_options.get("start_image")
            or video_options.get("end_image")
            or video_options.get("input_video")
            or video_options.get("video_url")
            or video_options.get("image_url")
            or video_options.get("character_image")
            or video_template.get("reference_video")
            or video_template.get("video_url")
            or video_template.get("template_video_url")
            or video_template.get("preview_video")
        )
        generation_modes = {"image", "video", "music", "voice"}
        text_modes = {"text", "chat", "pro", "lite"}
        if mode == "image":
            try:
                normalize_payload_image_seed(payload)
                image_options = payload.get("image_options") or {}
            except ValueError as exc:
                result = {"ok": False, "type": "image", "error": str(exc)}
                if job_id:
                    update_prostudio_generation_job(job_id, "failed", error=result)
                    log_prostudio_error(payload, result, job_id=job_id)
                return
        heartbeat_prostudio_generation_job(job_id)
        prostudio_debug(
            "JOB_PROCESS_STARTED",
            job_id=job_id,
            mode=mode,
            category=category,
            model=selected_model,
            provider=selected_provider,
            has_prompt=bool(prompt),
            has_image_refs=bool(reference_images),
            has_video_refs=bool(video_references),
            has_video_media=bool(video_media),
        )
        provider_for_slot = resolve_prostudio_provider_for_slot(
            payload, mode, selected_model, selected_provider
        )
        circuit = await asyncio.to_thread(
            circuit_before_request,
            DATABASE_URL,
            provider_for_slot,
            job_id,
            WORKER_ID,
        )
        if circuit.get("transition") == "HALF_OPEN":
            _log_circuit_transition(
                "PROVIDER_CIRCUIT_HALF_OPEN", provider_for_slot, job_id, 0,
                None, 0, circuit,
            )
        if not circuit.get("allowed"):
            _log_circuit_transition(
                "PROVIDER_CIRCUIT_BLOCKED", provider_for_slot, job_id, 0,
                None, circuit.get("wait_seconds") or 1, circuit,
            )
            await asyncio.to_thread(
                defer_prostudio_job_for_provider,
                job_id,
                circuit.get("wait_seconds") or 1,
            )
            return
        try:
            try:
                async with provider_slot(
                    DATABASE_URL, provider_for_slot, job_id, prostudio_debug,
                    wait_for_slot=False,
                ):
                    log_user_event(
                        int(payload.get("telegram_id") or 0), "worker", "generation",
                        "generation_started",
                        {"job_id": job_id, "mode": mode, "model": selected_model, "provider": selected_provider},
                    )
                    result, final_status = await run_prostudio_provider_request(
                        job_id, payload, mode, selected_model, selected_provider,
                        text_modes, provider_for_slot,
                    )
            except ProviderSlotUnavailable:
                await asyncio.to_thread(defer_prostudio_job_for_provider, job_id)
                return
        finally:
            await asyncio.shield(
                asyncio.to_thread(
                    circuit_release_probe, DATABASE_URL, provider_for_slot, job_id
                )
            )

        prostudio_debug(
            "JOB_PROVIDER_RESULT",
            job_id=job_id,
            mode=mode,
            ok=bool(result.get("ok")) if isinstance(result, dict) else False,
            status=(result or {}).get("status") if isinstance(result, dict) else "",
            result_keys=sorted((result or {}).keys()) if isinstance(result, dict) else [],
            image_url=(result or {}).get("image_url") if isinstance(result, dict) else "",
            thumbnail_url=(result or {}).get("thumbnail_url") if isinstance(result, dict) else "",
            images_count=len(_json_list((result or {}).get("images"))) if isinstance(result, dict) else 0,
        )
        if not isinstance(result, dict):
            result = {"ok": False, "error": "Provider returned empty result", "type": mode}
        if not result.get("ok"):
            if job_id:
                update_prostudio_generation_job(job_id, "failed", error=result)
                log_prostudio_error(payload, result, job_id=job_id)
                prostudio_debug("JOB_PROCESS_FAILED_PROVIDER_RESULT", job_id=job_id, error=(result or {}).get("error") or "")
            return

        if final_status != "completed":
            error_result = {
                "ok": False,
                "error": "Provider returned no completed result",
                "status": final_status,
                "result": result,
            }
            update_prostudio_generation_job(job_id, "failed", error=error_result)
            log_prostudio_error(payload, error_result, job_id=job_id)
            prostudio_debug("JOB_PROCESS_FAILED_NOT_COMPLETED", job_id=job_id, final_status=final_status)
            return

        if not generation_has_completed_result(result, mode):
            pending_result = dict(result or {})
            pending_result["status"] = "provider_processing"
            update_prostudio_generation_job(job_id, "provider_processing", result=pending_result)
            prostudio_debug("JOB_COMPLETED_WITHOUT_RESULT_HELD", job_id=job_id, mode=mode)
            return

        result = await asyncio.to_thread(persist_generation_media, result, mode)
        persisted_media_urls = await asyncio.to_thread(verify_persisted_generation_media, result, mode)
        r2_ready_at = time.monotonic()
        prostudio_debug("JOB_MEDIA_PERSISTED", job_id=job_id, mode=mode, storage="r2" if r2_enabled() else "local")
        prostudio_debug(
            "JOB_MEDIA_PERSIST_VERIFIED",
            job_id=job_id,
            mode=mode,
            storage="r2" if r2_enabled() else "local",
            media_count=len(persisted_media_urls),
        )
        prostudio_debug(
            "JOB_R2_READY",
            job_id=job_id,
            timestamp=round(r2_ready_at, 6),
            elapsed_ms_since_r2_ready=0,
        )

        telegram_id = int(payload.get("telegram_id") or 0)
        print("PROSTUDIO RESULT BEFORE CHARGE:", {
            "job_id": job_id,
            "mode": mode,
            "ok": result.get("ok"),
            "status": result.get("status"),
            "image_url": result.get("image_url"),
            "images": _json_list(result.get("images")),
            "thumbnail_url": result.get("thumbnail_url"),
            "thumbnails": _json_list(result.get("thumbnails")),
            "provider": result.get("provider"),
            "model": result.get("model"),
            "provider_model": result.get("provider_model"),
            "cost": result.get("cost"),
            "cost_credits": result.get("cost_credits"),
            "generation_cost": result.get("generation_cost"),
        })
        charge = charge_generation_balance(telegram_id, job_id or result.get("generation_id") or str(uuid4()), result, payload)
        if charge.get("error") or charge.get("insufficient_balance"):
            raise RuntimeError(charge.get("error") or "Insufficient balance while finalizing generation")
        result["balance_charged"] = bool(charge.get("charged") or charge.get("already_charged"))
        result["balance_after"] = charge.get("balance_after")
        result["charge_id"] = job_id or result.get("generation_id") or ""
        print("PROSTUDIO CHARGE RESULT:", {
            "job_id": job_id,
            "telegram_id": telegram_id,
            "charge": charge,
            "balance_charged": result.get("balance_charged"),
            "balance_after": result.get("balance_after"),
        })
        charge_done_at = time.monotonic()
        prostudio_debug(
            "JOB_CHARGE_DONE",
            job_id=job_id,
            timestamp=round(charge_done_at, 6),
            elapsed_ms_since_r2_ready=round((charge_done_at - r2_ready_at) * 1000),
        )

        # This is the only result Mini App needs to stop polling. It contains
        # verified R2 URLs and the committed balance outcome, but no slow
        # history/conversation or Telegram side effects.
        completed_result = build_completed_job_result(result, mode)
        if not update_prostudio_generation_job(job_id, "completed", result=completed_result):
            raise RuntimeError("Failed to commit completed Pro Studio job")
        completed_committed_at = time.monotonic()
        prostudio_debug(
            "JOB_COMPLETED_COMMITTED",
            job_id=job_id,
            timestamp=round(completed_committed_at, 6),
            elapsed_ms_since_r2_ready=round((completed_committed_at - r2_ready_at) * 1000),
        )
        prostudio_debug("JOB_PROCESS_COMPLETED", job_id=job_id, conversation_id="", status="completed")

        # History enriches an already completed job and is intentionally not
        # allowed to roll its terminal status back on failure.
        try:
            prostudio_debug("JOB_SAVE_GENERATION_START", job_id=job_id, telegram_id=telegram_id, mode=mode)
            save_generation(telegram_id, mode, prompt or "[attachment]")
            prostudio_debug("JOB_METADATA_BUILD_START", job_id=job_id)
            metadata = build_prostudio_metadata(payload, result)
            if metadata:
                result["metadata"] = metadata
            prostudio_debug(
                "JOB_MESSAGE_SAVE_START",
                job_id=job_id,
                image_url=result.get("image_url") or "",
                thumbnail_url=result.get("thumbnail_url") or "",
                images_count=len(_json_list(result.get("images"))),
                thumbs_count=len(_json_list(result.get("thumbnails"))),
            )
            result["conversation_id"] = save_prostudio_message(payload, result)
            prostudio_debug("JOB_MESSAGE_SAVE_DONE", job_id=job_id, conversation_id=result["conversation_id"])
            update_prostudio_generation_job(
                job_id, "completed", result=result, conversation_id=result["conversation_id"]
            )
            log_user_event(
                telegram_id,
                "backend",
                "generation",
                "generation_completed",
                {"job_id": job_id, "mode": mode, "conversation_id": result["conversation_id"]},
            )
            history_done_at = time.monotonic()
            prostudio_debug(
                "JOB_HISTORY_DONE",
                job_id=job_id,
                success=True,
                timestamp=round(history_done_at, 6),
                elapsed_ms_since_r2_ready=round((history_done_at - r2_ready_at) * 1000),
            )
        except Exception as history_exc:
            prostudio_error("JOB_POST_COMPLETION_HISTORY_FAILED", history_exc, job_id=job_id)
            history_done_at = time.monotonic()
            prostudio_debug(
                "JOB_HISTORY_DONE",
                job_id=job_id,
                success=False,
                timestamp=round(history_done_at, 6),
                elapsed_ms_since_r2_ready=round((history_done_at - r2_ready_at) * 1000),
            )

        # Telegram is another post-completion side effect and cannot alter the
        # terminal PostgreSQL status.
        telegram_sent = await sync_completed_generation_to_telegram(telegram_id, mode, payload, result)
        telegram_done_at = time.monotonic()
        prostudio_debug(
            "JOB_TELEGRAM_SENT",
            job_id=job_id,
            telegram_id=telegram_id,
            sent=bool(telegram_sent),
            timestamp=round(telegram_done_at, 6),
            elapsed_ms_since_r2_ready=round((telegram_done_at - r2_ready_at) * 1000),
        )
    except Exception as exc:
        prostudio_error("JOB_PROCESS_EXCEPTION", exc, job_id=job_id)
        error_result = {"ok": False, "error": str(exc), "traceback": traceback.format_exc()}
        if job_id:
            update_prostudio_generation_job(job_id, "failed", error=error_result)
            log_prostudio_error(payload, error_result, job_id=job_id)

async def _wait_for_prostudio_worker_stop(stop_event: asyncio.Event, timeout: float) -> bool:
    if stop_event.is_set():
        return True
    try:
        await asyncio.wait_for(stop_event.wait(), timeout=max(0.05, float(timeout)))
    except asyncio.TimeoutError:
        return stop_event.is_set()
    return True


async def _prostudio_job_heartbeat_loop(job_id: str, finished_event: asyncio.Event):
    # A bounded companion coroutine is created only for an occupied pool slot.
    # It prevents a healthy long-running provider call from being recovered as stale.
    heartbeat_interval = max(5.0, min(60.0, PROSTUDIO_STALE_PROCESSING_MINUTES * 20.0))
    while not finished_event.is_set():
        try:
            await asyncio.wait_for(finished_event.wait(), timeout=heartbeat_interval)
            return
        except asyncio.TimeoutError:
            await asyncio.to_thread(heartbeat_prostudio_generation_job, job_id)


async def _run_prostudio_generation_pool(
    stop_event: asyncio.Event,
    concurrency: Optional[int] = None,
):
    pool_size = _bounded_prostudio_worker_concurrency(
        PROSTUDIO_WORKER_CONCURRENCY if concurrency is None else concurrency
    )
    active_job_ids = set()
    active_lock = asyncio.Lock()

    async def pool_counts():
        async with active_lock:
            active_count = len(active_job_ids)
        return active_count, max(0, pool_size - active_count)

    async def log_pool_status(job_id: str = ""):
        active_count, free_slots = await pool_counts()
        prostudio_debug(
            "WORKER_POOL_STATUS",
            concurrency=pool_size,
            active_tasks=active_count,
            free_slots=free_slots,
            job_id=job_id or "",
        )

    async def worker_slot(slot_id: int):
        while not stop_event.is_set():
            claimed = None
            try:
                claimed = await asyncio.to_thread(claim_next_prostudio_generation_job)
            except Exception as exc:
                prostudio_error("WORKER_CLAIM_FAILED", exc, slot_id=slot_id)

            if stop_event.is_set():
                # A claim that completed concurrently with shutdown is already
                # marked processing. Process it instead of abandoning it.
                if not claimed:
                    return
            if not claimed or not claimed.get("id") or not claimed.get("payload"):
                if await _wait_for_prostudio_worker_stop(stop_event, PROSTUDIO_WORKER_INTERVAL):
                    return
                continue

            job_id = str(claimed["id"])
            async with active_lock:
                duplicate = job_id in active_job_ids
                if not duplicate:
                    active_job_ids.add(job_id)
                active_count = len(active_job_ids)
            if duplicate:
                prostudio_error(
                    "WORKER_DUPLICATE_JOB_BLOCKED",
                    job_id=job_id,
                    slot_id=slot_id,
                    concurrency=pool_size,
                    active_tasks=active_count,
                    free_slots=max(0, pool_size - active_count),
                )
                continue

            finished_event = asyncio.Event()
            heartbeat_task = asyncio.create_task(
                _prostudio_job_heartbeat_loop(job_id, finished_event),
                name=f"prostudio-heartbeat-{job_id}",
            )
            prostudio_debug(
                "WORKER_TASK_STARTED",
                concurrency=pool_size,
                active_tasks=active_count,
                free_slots=max(0, pool_size - active_count),
                job_id=job_id,
                slot_id=slot_id,
                attempts=claimed.get("attempts"),
            )
            try:
                await process_prostudio_generation(job_id, claimed["payload"])
            except Exception as exc:
                # process_prostudio_generation already isolates provider errors,
                # but keep the pool healthy if an unexpected exception escapes.
                prostudio_error("WORKER_TASK_EXCEPTION", exc, job_id=job_id, slot_id=slot_id)
                update_prostudio_generation_job(
                    job_id,
                    "failed",
                    error={"ok": False, "error": str(exc)},
                )
            finally:
                finished_event.set()
                await asyncio.gather(heartbeat_task, return_exceptions=True)
                async with active_lock:
                    active_job_ids.discard(job_id)
                    active_count = len(active_job_ids)
                prostudio_debug(
                    "WORKER_TASK_FINISHED",
                    concurrency=pool_size,
                    active_tasks=active_count,
                    free_slots=max(0, pool_size - active_count),
                    job_id=job_id,
                    slot_id=slot_id,
                )

    # Recover abandoned work before accepting new jobs. Heartbeats protect all
    # subsequently active pool jobs during periodic recovery passes.
    await asyncio.to_thread(requeue_stale_prostudio_jobs)
    slots = [
        asyncio.create_task(worker_slot(index + 1), name=f"prostudio-worker-slot-{index + 1}")
        for index in range(pool_size)
    ]
    prostudio_debug(
        "WORKER_POOL_STARTED",
        concurrency=pool_size,
        active_tasks=0,
        free_slots=pool_size,
        job_id="",
    )
    status_interval = max(15.0, PROSTUDIO_WORKER_INTERVAL * 10.0)
    try:
        while not stop_event.is_set():
            if await _wait_for_prostudio_worker_stop(stop_event, status_interval):
                break
            await asyncio.to_thread(requeue_stale_prostudio_jobs)
            await log_pool_status()
    finally:
        # Slots are never cancelled here: they stop claiming immediately and
        # finish any job they already own before the pool returns.
        stop_event.set()
        await asyncio.gather(*slots, return_exceptions=True)
        await log_pool_status()


# =====================================================
# ФОНОВАЯ ЗАДАЧА: prostudio_generation_worker_loop
# Обрабатывает job после нажатия пользователем кнопки генерации: запускает провайдера, ждёт результат и сохраняет итог.
# =====================================================
async def prostudio_generation_worker_loop():
    if not PROSTUDIO_WORKER_ENABLED:
        print("PROSTUDIO WORKER DISABLED")
        return
    print("PROSTUDIO WORKER STARTED")
    stop_event = asyncio.Event()
    try:
        await _run_prostudio_generation_pool(stop_event, PROSTUDIO_WORKER_CONCURRENCY)
    except asyncio.CancelledError:
        # Cancellation is treated as a graceful stop request. The pool's
        # cleanup waits for jobs already claimed, while no new jobs are read.
        stop_event.set()
        prostudio_debug(
            "WORKER_POOL_STOPPING",
            concurrency=PROSTUDIO_WORKER_CONCURRENCY,
        )
        raise


def process_subscription_reminders() -> dict:
    if not DATABASE_URL or not BOT_TOKEN:
        return {"checked": 0, "sent": 0}
    ensure_payment_tables()
    conn = db_connect(DATABASE_URL)
    cursor = conn.cursor()
    try:
        cursor.execute("""
            UPDATE subscriptions
            SET status = 'expired'
            WHERE status = 'active'
              AND expires_at IS NOT NULL
              AND expires_at::timestamp <= NOW()
        """)
        cursor.execute("""
            SELECT s.id, s.telegram_id, s.subscription_type, s.expires_at::timestamp,
                   EXTRACT(EPOCH FROM (s.expires_at::timestamp - NOW()))
            FROM subscriptions s
            WHERE s.status = 'active'
              AND s.expires_at::timestamp > NOW()
              AND s.expires_at::timestamp <= NOW() + INTERVAL '8 days'
              AND NOT EXISTS (
                  SELECT 1
                  FROM subscriptions newer
                  WHERE newer.telegram_id = s.telegram_id
                    AND newer.status = 'active'
                    AND newer.expires_at::timestamp > s.expires_at::timestamp
              )
            ORDER BY s.expires_at ASC
        """)
        subscriptions = cursor.fetchall()
        conn.commit()
    finally:
        cursor.close()
        conn.close()

    checked = 0
    sent = 0
    for subscription_id, telegram_id, plan, expires_at, remaining_seconds in subscriptions:
        checked += 1
        seconds = max(0, float(remaining_seconds or 0))
        days_before = int((seconds + 86399) // 86400)
        if days_before not in {7, 5, 2, 1}:
            continue

        claim_conn = db_connect(DATABASE_URL)
        claim_cursor = claim_conn.cursor()
        try:
            claim_cursor.execute("""
                INSERT INTO subscription_reminders
                    (subscription_id, telegram_id, days_before, status)
                VALUES (%s, %s, %s, 'sending')
                ON CONFLICT (subscription_id, days_before) DO NOTHING
                RETURNING id
            """, (subscription_id, telegram_id, days_before))
            claimed = claim_cursor.fetchone()
            claim_conn.commit()
        finally:
            claim_cursor.close()
            claim_conn.close()
        if not claimed:
            continue

        day_word = "день" if days_before == 1 else ("дня" if days_before in {2, 3, 4} else "дней")
        plan_label = "1 год" if str(plan or "").lower() == "year" else "1 месяц"
        text = (
            "⏳ <b>Подписка SYLVEX Pro скоро закончится</b>\n\n"
            f"До окончания осталось: <b>{days_before} {day_word}</b>\n"
            f"Текущий план: <b>{plan_label}</b>\n"
            f"Дата окончания: <b>{expires_at.strftime('%d.%m.%Y %H:%M')}</b>\n\n"
            "Продлите подписку заранее, чтобы сохранить непрерывный доступ к генерациям."
        )
        try:
            response = requests.post(
                f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                json={
                    "chat_id": int(telegram_id),
                    "text": text,
                    "parse_mode": "HTML",
                    "disable_web_page_preview": True,
                    "reply_markup": {
                        "inline_keyboard": [[{
                            "text": "Продлить подписку",
                            "web_app": {"url": WEBAPP_URL.rstrip("/") + "/webapp/index.html?view=shop"},
                        }]]
                    },
                },
                timeout=20,
            )
            result = response.json() if response.content else {}
            if response.status_code >= 400 or not result.get("ok"):
                raise RuntimeError(f"Telegram sendMessage failed: {response.status_code} {result}")
            update_conn = db_connect(DATABASE_URL)
            update_cursor = update_conn.cursor()
            try:
                update_cursor.execute("""
                    UPDATE subscription_reminders
                    SET status = 'sent', sent_at = NOW()
                    WHERE id = %s
                """, (claimed[0],))
                update_conn.commit()
            finally:
                update_cursor.close()
                update_conn.close()
            sent += 1
        except Exception as exc:
            prostudio_error(
                "SUBSCRIPTION_REMINDER_FAILED",
                exc,
                telegram_id=telegram_id,
                subscription_id=subscription_id,
                days_before=days_before,
            )
            retry_conn = db_connect(DATABASE_URL)
            retry_cursor = retry_conn.cursor()
            try:
                retry_cursor.execute("DELETE FROM subscription_reminders WHERE id = %s", (claimed[0],))
                retry_conn.commit()
            finally:
                retry_cursor.close()
                retry_conn.close()
    return {"checked": checked, "sent": sent}


async def subscription_reminder_worker_loop():
    if not SUBSCRIPTION_REMINDER_WORKER_ENABLED:
        print("SUBSCRIPTION REMINDER WORKER DISABLED")
        return
    print("SUBSCRIPTION REMINDER WORKER STARTED")
    while True:
        try:
            result = await asyncio.to_thread(process_subscription_reminders)
            if result.get("sent"):
                prostudio_debug("SUBSCRIPTION_REMINDERS_SENT", **result)
        except Exception as exc:
            prostudio_error("SUBSCRIPTION_REMINDER_WORKER_FAILED", exc)
        await asyncio.sleep(max(300, SUBSCRIPTION_REMINDER_INTERVAL_SECONDS))

# =====================================================
# API ENDPOINT: start_prostudio_generation_worker
# Принимает HTTP-запрос от Mini App или Telegram Bot.
# Маршрут FastAPI: @app.on_event("startup")
# Проверяет входные данные, работает с базой/провайдерами и возвращает JSON-ответ фронтенду.
# =====================================================
@app.on_event("startup")
# =====================================================
# ФОНОВАЯ ЗАДАЧА: start_prostudio_generation_worker
# Обрабатывает job после нажатия пользователем кнопки генерации: запускает провайдера, ждёт результат и сохраняет итог.
# =====================================================
async def start_prostudio_generation_worker():
    if DATABASE_URL:
        await asyncio.to_thread(start_db_pool, DATABASE_URL)
        db_pool_status()
    if PROSTUDIO_WORKER_ENABLED:
        asyncio.create_task(prostudio_generation_worker_loop())
    if SUBSCRIPTION_REMINDER_WORKER_ENABLED and DATABASE_URL and BOT_TOKEN:
        asyncio.create_task(subscription_reminder_worker_loop())


@app.on_event("shutdown")
async def close_postgresql_pool():
    await asyncio.to_thread(close_db_pool)

# =====================================================
# API ENDPOINT: public_prostudio_transcribe
# Принимает HTTP-запрос от Mini App или Telegram Bot.
# Маршрут FastAPI: @app.post("/api/public/prostudio/transcribe")
# Проверяет входные данные, работает с базой/провайдерами и возвращает JSON-ответ фронтенду.
# =====================================================
@app.post("/api/public/prostudio/transcribe")
# =====================================================
# PYTHON-БЛОК: public_prostudio_transcribe
# Выполняет отдельный шаг backend-логики SYLVEX.
# Связан с API, базой данных, провайдерами или подготовкой данных для Mini App.
# =====================================================
async def public_prostudio_transcribe(request: Request):
    form = await request.form()
    file = form.get("file")
    if not file or not hasattr(file, "read"):
        return JSONResponse({"ok": False, "error": "File is required"}, status_code=400)

    content = await file.read()
    if not content:
        return JSONResponse({"ok": False, "error": "Empty file"}, status_code=400)
    if len(content) > 25 * 1024 * 1024:
        return JSONResponse(
            {"ok": False, "error": "Запись превышает допустимый размер 25 МБ"},
            status_code=413,
        )
    filename = getattr(file, "filename", None) or "voice.webm"
    content_type = getattr(file, "content_type", None) or "audio/webm"
    # Provider calls are synchronous; keep them off FastAPI's event loop so a
    # long transcription cannot freeze the Mini App's other API requests.
    ok, text = await asyncio.to_thread(
        openai_transcribe_bytes,
        content,
        filename,
        content_type,
    )
    if not ok:
        openai_error = text
        ok, text = await asyncio.to_thread(gemini_transcribe_bytes, content, content_type)
        if not ok:
            print("PROSTUDIO ERROR TRANSCRIBE_FAILED:", {
                "filename": filename,
                "content_type": content_type,
                "bytes": len(content),
                "openai_error": openai_error,
                "gemini_error": text,
            })
            return JSONResponse(
                {"ok": False, "error": "Сервис распознавания речи временно недоступен. Попробуйте ещё раз позже."},
                status_code=503,
            )
        print("PROSTUDIO TRANSCRIBE FALLBACK:", {
            "provider": "gemini",
            "filename": filename,
            "bytes": len(content),
            "openai_error": openai_error,
        })
    return {"ok": True, "text": text}


@app.post("/api/public/prostudio/voice/text-tool")
async def public_prostudio_voice_text_tool(request: Request):
    """Small editor actions for Voice Studio; never starts audio generation."""
    payload = await request.json()
    action = str(payload.get("action") or "").strip().lower()
    text = str(payload.get("text") or "").strip()
    brief = str(payload.get("brief") or "").strip()
    format_name = str(payload.get("format") or "script").strip()
    source_language = str(payload.get("source_language") or "auto").strip()
    target_language = str(payload.get("target_language") or "en").strip()
    if action not in {"create", "improve", "translate"}:
        return JSONResponse({"ok": False, "error": "Unsupported text action"}, status_code=400)
    if action == "create" and not brief:
        return JSONResponse({"ok": False, "error": "Описание текста обязательно"}, status_code=400)
    if action != "create" and not text:
        return JSONResponse({"ok": False, "error": "Текст обязателен"}, status_code=400)
    if len(text) + len(brief) > 60000:
        return JSONResponse({"ok": False, "error": "Текст слишком длинный"}, status_code=413)

    language_names = {
        "en": "English", "de": "German", "fr": "French", "ru": "Russian",
        "es": "Spanish", "it": "Italian", "tr": "Turkish",
    }
    if action == "create":
        instruction = (
            f"Create a {format_name} voice-over script from this brief:\n{brief}\n\n"
            "Write polished, natural spoken text. Return only the finished script, without headings, notes or Markdown."
        )
    elif action == "translate":
        source_hint = "Detect the source language automatically" if source_language == "auto" else f"The source language is {language_names.get(source_language, source_language)}"
        instruction = (
            f"{source_hint}. Translate the following voice-over text into {language_names.get(target_language, target_language)}. "
            "Preserve speaker labels, pauses, emotion markers, meaning and natural spoken rhythm. "
            f"Return only the translation.\n\n{text}"
        )
    else:
        instruction = (
            "Improve the following text for professional voice-over. Correct grammar, make it natural to speak, "
            "preserve its meaning, language, speaker labels and markup. Return only the improved text.\n\n" + text
        )

    messages = [
        {"role": "system", "content": "You are the SYLVEX Voice Studio script editor. Follow the requested operation precisely."},
        {"role": "user", "content": instruction},
    ]
    provider_errors = {}
    result_text = ""
    if OPENAI_API_KEY:
        openai_model = env_value("OPENAI_VOICE_TEXT_MODEL", default="gpt-5-mini")
        ok, result_text, _data = await asyncio.to_thread(
            openai_compatible_text_request,
            "openai",
            OPENAI_API_BASE,
            OPENAI_API_KEY,
            openai_model,
            messages,
        )
        if not ok:
            provider_errors["openai"] = result_text
            result_text = ""
    if not result_text:
        gemini_model = env_value("GEMINI_VOICE_TEXT_MODEL", default="gemini-2.5-flash")
        ok, result_text, _data = await asyncio.to_thread(gemini_text_request, gemini_model, messages)
        if not ok:
            provider_errors["gemini"] = result_text
            result_text = ""
    if not result_text:
        print("PROSTUDIO ERROR VOICE_TEXT_TOOL_FAILED:", {
            "action": action,
            "text_length": len(text),
            "brief_length": len(brief),
            "providers": provider_errors,
        })
        return JSONResponse(
            {"ok": False, "error": "AI-редактор временно недоступен. Попробуйте немного позже."},
            status_code=503,
        )
    return {"ok": True, "text": result_text.strip(), "action": action}

# =====================================================
# API ENDPOINT: public_prostudio_elevenlabs_voice_clone
# Принимает запись микрофона из Mini App и создаёт новый голос ElevenLabs.
# Возвращает voice_id, чтобы пользователь мог сразу выбрать созданный голос в разделе «Озвучка».
# =====================================================
@app.post("/api/public/prostudio/elevenlabs/voice-clone")
async def public_prostudio_elevenlabs_voice_clone(request: Request):
    form = await request.form()
    file = form.get("file")
    if not file or not hasattr(file, "read"):
        return JSONResponse({"ok": False, "error": "File is required"}, status_code=400)

    content = await file.read()
    if not content:
        return JSONResponse({"ok": False, "error": "Empty file"}, status_code=400)

    try:
        telegram_id = int(form.get("telegram_id") or 0)
    except Exception:
        telegram_id = 0
    try:
        clone_settings = json.loads(str(form.get("settings") or "{}"))
    except Exception:
        clone_settings = {}
    result = await elevenlabs_clone_voice_from_audio(
        file_content=content,
        filename=getattr(file, "filename", None) or "sylvex-voice.webm",
        content_type=getattr(file, "content_type", None) or "audio/webm",
        name=str(form.get("name") or "SYLVEX Voice"),
        description=str(form.get("description") or "Created in SYLVEX Mini App"),
        telegram_id=telegram_id,
        gender=str(form.get("gender") or clone_settings.get("gender") or "neutral"),
        emotion=str(form.get("emotion") or clone_settings.get("emotion") or "neutral"),
        settings=clone_settings if isinstance(clone_settings, dict) else {},
    )
    if not result.get("ok"):
        return JSONResponse(result, status_code=502)
    return result

# =====================================================
# API ENDPOINT: get_cabinet
# Принимает HTTP-запрос от Mini App или Telegram Bot.
# Маршрут FastAPI: @app.get("/api/cabinet/{telegram_id}")
# Проверяет входные данные, работает с базой/провайдерами и возвращает JSON-ответ фронтенду.
# =====================================================
@app.get("/api/cabinet/{telegram_id}")
# =====================================================
# PYTHON-БЛОК: get_cabinet
# Выполняет отдельный шаг backend-логики SYLVEX.
# Связан с API, базой данных, провайдерами или подготовкой данных для Mini App.
# =====================================================
async def get_cabinet(telegram_id: int):

    conn = db_connect(DATABASE_URL)
    cursor = conn.cursor()

    cursor.execute("""
    SELECT
        telegram_id,
        username,
        first_name,
        balance,
        subscription,
        total_generations,
        created_at
    FROM users
    WHERE telegram_id = %s
    """, (telegram_id,))

    user = cursor.fetchone()

    cursor.execute("""
    SELECT
        generation_type,
        prompt,
        status,
        created_at
    FROM generations
    WHERE telegram_id = %s
    ORDER BY id DESC
    LIMIT 10
    """, (telegram_id,))

    generations = cursor.fetchall()

    cursor.close()
    conn.close()

    if not user:
        return JSONResponse(
            {
                "success": False
            }
        )

    return {
        "success": True,
        "user": {
            "telegram_id": user[0],
            "username": user[1],
            "first_name": user[2],
            "balance": user[3],
            "subscription": user[4],
            "total_generations": user[5],
            "created_at": user[6]
        },
        "generations": [
            {
                "generation_type": row[0],
                "prompt": row[1],
                "status": row[2],
                "created_at": row[3]
            }
            for row in generations
        ]
    }
