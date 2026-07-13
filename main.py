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
from typing import Optional
from uuid import uuid4
import requests
import psycopg2
from dotenv import load_dotenv
from fastapi.responses import JSONResponse, RedirectResponse

from services.audio_router import audio_generation
from services.video_router import video_generation

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

load_dotenv()

app = FastAPI()

BASE_DIR = pathlib.Path(__file__).resolve().parent
WEBAPP_DIR = BASE_DIR / "webapp"

app.mount("/webapp", StaticFiles(directory=WEBAPP_DIR, html=True), name="webapp")
app.mount("/static", StaticFiles(directory=WEBAPP_DIR), name="static")
app.mount("/image", StaticFiles(directory="image"), name="image")
app.mount("/assets", StaticFiles(directory="webapp/assets"), name="assets")
app.mount("/js", StaticFiles(directory="webapp/js"), name="js")
app.mount("/css", StaticFiles(directory="webapp/css"), name="css")
app.mount("/generated", StaticFiles(directory=WEBAPP_DIR / "generated"), name="generated")


BOT_TOKEN = os.getenv("BOT_TOKEN")
DATABASE_URL = os.getenv("DATABASE_PUBLIC_URL") or os.getenv("DATABASE_URL")
print("MINIAPP DATABASE CONFIGURED:", bool(DATABASE_URL))
PROSTUDIO_WORKER_ENABLED = os.getenv("PROSTUDIO_WORKER_ENABLED", "1").lower() not in {"0", "false", "no"}
PROSTUDIO_WORKER_INTERVAL = float(os.getenv("PROSTUDIO_WORKER_INTERVAL", "2"))
PROSTUDIO_STALE_PROCESSING_MINUTES = int(os.getenv("PROSTUDIO_STALE_PROCESSING_MINUTES", "30"))
PROSTUDIO_MAX_JOB_ATTEMPTS = int(os.getenv("PROSTUDIO_MAX_JOB_ATTEMPTS", "3"))
WEBAPP_URL = os.getenv("WEBAPP_URL", "https://sylvex-ai-webapp-production.up.railway.app")
PAYMENT_WEBAPP_URL = os.getenv("PAYMENT_WEBAPP_URL", WEBAPP_URL.rstrip("/") + "/payments")
SHOP_WEBAPP_URL = os.getenv("SHOP_WEBAPP_URL", WEBAPP_URL.rstrip("/") + "/webapp/index.html?view=shop")

def env_value(*names: str, default: str = "") -> str:
    for name in names:
        value = os.getenv(name)
        if value:
            return value
    return default

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_API_BASE = os.getenv("OPENAI_API_BASE", "https://api.openai.com/v1").rstrip("/")
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
    "qwen_image": {"provider": "qwen", "provider_model": os.getenv("QWEN_IMAGE_MODEL"), "endpoint": os.getenv("QWEN_IMAGE_ENDPOINT")},
    "qwen_image_2_pro": {"provider": "qwen", "provider_model": os.getenv("QWEN_IMAGE_2_PRO_MODEL"), "endpoint": os.getenv("QWEN_IMAGE_ENDPOINT")},
    "qwen_image_2": {"provider": "qwen", "provider_model": os.getenv("QWEN_IMAGE_2_MODEL"), "endpoint": os.getenv("QWEN_IMAGE_ENDPOINT")},
    "nano_banana_pro": {"provider": "google", "provider_model": os.getenv("NANO_BANANA_PRO_MODEL"), "endpoint": os.getenv("GOOGLE_IMAGE_ENDPOINT")},
    "nano_banana_2": {"provider": "google", "provider_model": os.getenv("NANO_BANANA_2_MODEL"), "endpoint": os.getenv("GOOGLE_IMAGE_ENDPOINT")},
    "nano_banana": {"provider": "google", "provider_model": os.getenv("NANO_BANANA_MODEL"), "endpoint": os.getenv("GOOGLE_IMAGE_ENDPOINT")},
    "grok_pro": {"provider": "grok", "provider_model": os.getenv("GROK_IMAGE_PRO_MODEL"), "endpoint": os.getenv("XAI_IMAGE_ENDPOINT")},
    "grok": {"provider": "grok", "provider_model": os.getenv("GROK_IMAGE_MODEL"), "endpoint": os.getenv("XAI_IMAGE_ENDPOINT")},
    "davinci_ultra": {"provider": "davinci", "provider_model": os.getenv("DAVINCI_ULTRA_MODEL"), "endpoint": os.getenv("DAVINCI_IMAGE_ENDPOINT")},
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
    "nano_banana_pro": {"character": True, "object": True},
    "nano_banana_2": {"character": False, "object": False},
    "nano_banana": {"character": True, "object": True},
    "gpt_image_2": {"character": True, "object": True},
    "seedream_5_0_lite": {"character": True, "object": True, "seed": True},
    "seedream_5_0": {"character": True, "object": True, "seed": True},
    "seedream_5": {"character": True, "object": True, "seed": True},
    "seedream_5_0_pro": {"character": True, "object": True, "seed": True},
    "seedream_5_pro": {"character": True, "object": True, "seed": True},
    "seedream_4_5": {"character": True, "object": True, "seed": True},
    "seedream_4_0": {"character": True, "object": True, "seed": True},
    "seedream_4": {"character": True, "object": True, "seed": True},
    "grok_pro": {"character": False, "object": False},
    "davinci_ultra": {"character": False, "object": False},
    "grok": {"character": False, "object": False},
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
    "gpt_image_1": {"character": False, "object": False},
    "qwen_image": {"character": False, "object": False},
    "qwen_image_2": {"character": False, "object": False},
    "qwen_image_2_pro": {"character": False, "object": False},
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

def shop_item(pack_id: str):
    return SHOP_ITEMS.get((pack_id or "").strip())


def shop_payload(provider: str, telegram_id: int, pack_id: str, item: dict) -> str:
    if item["kind"] == "subscription":
        return f"sylvex_{provider}_sub:{telegram_id}:{item['plan_key']}:{item['usd']:.2f}"
    return f"sylvex_{provider}_credits:{telegram_id}:{item['credits']}:{item['usd']:.2f}"


def bot_stars_payload(telegram_id: int, item: dict, charge_id: str = None) -> str:
    if item["kind"] == "subscription":
        payload = f"sylvex_sub:{telegram_id}:{item['plan_key']}:{item['stars']}"
    else:
        payload = f"sylvex_stars:{telegram_id}:{item['credits']}:{item['stars']}"
    if charge_id:
        payload = f"{payload}:{charge_id}"
    return payload


def parse_shop_payload(payload: str) -> dict:
    if not payload or not isinstance(payload, str):
        return {}

    parts = payload.split(":")
    if not parts:
        return {}

    result = {
        "kind": None,
        "provider": None,
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


def _has_subscription_purchase(telegram_id: int) -> bool:
    if not DATABASE_URL or not telegram_id:
        return False

    ensure_payment_tables()
    conn = psycopg2.connect(DATABASE_URL)
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


def _restore_active_subscription(telegram_id: int) -> bool:
    if not DATABASE_URL or not telegram_id:
        return False

    ensure_payment_tables()
    conn = psycopg2.connect(DATABASE_URL)
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


def create_telegram_stars_invoice_link(telegram_id: int, pack_id: str, item: dict, charge_id: str) -> str:
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN is not configured")

    response = requests.post(
        f"https://api.telegram.org/bot{BOT_TOKEN}/createInvoiceLink",
        json={
            "title": item["title"],
            "description": f"Оплата {item['title']} в SYLVEX.",
            "payload": bot_stars_payload(telegram_id, item, charge_id),
            "provider_token": "",
            "currency": "XTR",
            "prices": [
                {
                    "label": item["title"],
                    "amount": int(item["stars"]),
                }
            ],
        },
        timeout=30,
    )

    data = response.json()
    if response.status_code >= 400 or not data.get("ok"):
        raise RuntimeError(str(data))

    return data["result"]


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


def crypto_invoice_url(invoice: dict) -> str:
    return (
        invoice.get("mini_app_invoice_url")
        or invoice.get("bot_invoice_url")
        or invoice.get("web_app_invoice_url")
        or ""
    )


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


def get_crypto_invoice(invoice_id: int):
    result = crypto_pay_request("getInvoices", {"invoice_ids": str(invoice_id)})
    if isinstance(result, dict):
        items = result.get("items") or []
        if items:
            return items[0]
        if result.get("invoice_id"):
            return result
    return None


def ensure_user_events_table():
    if not DATABASE_URL:
        return

    conn = psycopg2.connect(DATABASE_URL)
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


def ensure_payment_tables():
    if not DATABASE_URL:
        return

    conn = psycopg2.connect(DATABASE_URL)
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
        conn.commit()
    finally:
        cursor.close()
        conn.close()


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

        conn = psycopg2.connect(DATABASE_URL)
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


def ensure_user_profiles_table():
    if not DATABASE_URL:
        return

    conn = psycopg2.connect(DATABASE_URL)
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


def get_user_profile(telegram_id: int) -> dict:
    if not DATABASE_URL or not telegram_id:
        return {}

    ensure_user_profiles_table()
    conn = psycopg2.connect(DATABASE_URL)
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


def save_user_profile(telegram_id: int, display_name=None, custom_avatar_url=None, theme_preference=None) -> dict:
    if not DATABASE_URL or not telegram_id:
        return {}

    ensure_user_exists(telegram_id)
    ensure_user_profiles_table()

    theme_json = None
    if theme_preference is not None:
        theme_json = json.dumps(theme_preference if isinstance(theme_preference, dict) else {}, ensure_ascii=False)

    conn = psycopg2.connect(DATABASE_URL)
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


def ensure_user_referrals_table():
    if not DATABASE_URL:
        return

    conn = psycopg2.connect(DATABASE_URL)
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
        conn.commit()
    finally:
        cursor.close()
        conn.close()


def referral_code_for(telegram_id: int) -> str:
    digest = hashlib.sha1(f"sylvex:{telegram_id}".encode("utf-8")).hexdigest()[:10]
    return f"sylvex_{digest}"


def get_referral_state(telegram_id: int, activate: bool = False) -> dict:
    if not telegram_id:
        return {}

    code = referral_code_for(telegram_id)
    link = f"https://t.me/sylvexai_bot?start={code}"

    if not DATABASE_URL:
        return {
            "ok": True,
            "telegram_id": telegram_id,
            "code": code,
            "link": link,
            "referrals_count": 0,
            "tokens_earned": 0,
            "activated_at": None,
        }

    ensure_user_exists(telegram_id)
    ensure_user_referrals_table()
    conn = psycopg2.connect(DATABASE_URL)
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
        conn.commit()
    finally:
        cursor.close()
        conn.close()

    return {
        "ok": True,
        "telegram_id": telegram_id,
        "code": code,
        "link": link,
        "referrals_count": 0,
        "tokens_earned": 0,
        "activated_at": _to_iso(row[0]) if row and row[0] else None,
    }


def get_user_state(telegram_id: int, username: str = None, first_name: str = None) -> dict:
    if not DATABASE_URL or not telegram_id:
        return {}

    ensure_user_exists(telegram_id)
    if username or first_name:
        conn = psycopg2.connect(DATABASE_URL)
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

    conn = psycopg2.connect(DATABASE_URL)
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

        if active_sub:
            cursor.execute("""
                UPDATE users
                SET subscription = COALESCE(%s, 'active')
                WHERE telegram_id = %s
            """, (active_sub[0], telegram_id))
            conn.commit()
        elif (str(user_row[4] or '').lower() == 'active' or _has_subscription_purchase(telegram_id)):
            restored = _restore_active_subscription(telegram_id)
            if restored:
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
                if active_sub:
                    cursor.execute("""
                        UPDATE users
                        SET subscription = COALESCE(%s, 'active')
                        WHERE telegram_id = %s
                    """, (active_sub[0], telegram_id))
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
                FROM purchases
                WHERE telegram_id = %s
                  AND status = 'completed'
                  AND COALESCE(credits, 0) < 0
            """, (telegram_id,))
            tokens_spent = abs(cursor.fetchone()[0] or 0)
        except Exception:
            tokens_spent = 0

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
    result = {
        "telegram_id": user_row[0],
        "username": user_row[1],
        "first_name": user_row[2],
        "balance": user_row[3] or 0,
        "status": "active" if active_sub else (user_row[4] or "free"),
        "subscription_status": subscription_status,
        "subscription_plan": active_sub[0] if active_sub else None,
        "subscription_expires_at": _to_iso(active_sub[1]) if active_sub and active_sub[1] else None,
        "display_name": profile.get("display_name"),
        "custom_avatar_url": profile.get("custom_avatar_url"),
        "theme_preference": profile.get("theme_preference") or {},
        "created_at": user_row[5],
        "total_generations": total_generations,
        "generations_count": total_generations,
        "tokens_spent": tokens_spent,
        "referrals_count": 0,
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
    conn = psycopg2.connect(DATABASE_URL)
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
    finally:
        cursor.close()
        conn.close()

    balance = user_row[0] if user_row else 0
    subscription = active_sub[0] if active_sub else None
    subscription_until = _to_iso(active_sub[1]) if active_sub and active_sub[1] else None
    status = "pro" if active_sub else "free"

    return {
        "balance": balance or 0,
        "subscription": subscription,
        "subscription_until": subscription_until,
        "status": status,
    }


def create_purchase_once(telegram_id: int, provider: str, credits: int, amount: int, currency: str, payload: str, charge_id: str) -> bool:
    if not DATABASE_URL:
        return False

    ensure_payment_tables()
    conn = psycopg2.connect(DATABASE_URL)
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


def activate_subscription(telegram_id: int, item: dict, provider: str, amount: int, currency: str, payload: str, charge_id: str) -> bool:
    if not DATABASE_URL:
        return False

    ensure_user_exists(telegram_id)
    ensure_payment_tables()
    conn = psycopg2.connect(DATABASE_URL)
    cursor = conn.cursor()
    try:
        cursor.execute("""
            UPDATE subscriptions
            SET status = 'cancelled'
            WHERE telegram_id = %s
              AND status = 'active'
        """, (telegram_id,))
        cursor.execute("""
            INSERT INTO subscriptions (
                telegram_id, subscription_type, payment_method, amount, currency, expires_at, status, charge_id
            )
            VALUES (
                %s, %s, %s, %s, %s, CURRENT_TIMESTAMP + (%s || ' days')::interval, 'active', %s
            )
            ON CONFLICT (charge_id) DO NOTHING
        """, (telegram_id, item["plan_key"], provider, amount, currency, item["days"], charge_id))
        inserted = cursor.rowcount > 0
        cursor.execute("UPDATE users SET subscription = %s WHERE telegram_id = %s", (item.get("plan_key") or "active", telegram_id))
        conn.commit()
        return inserted
    finally:
        cursor.close()
        conn.close()




def ensure_user_exists(telegram_id: int):
    if not DATABASE_URL or not telegram_id:
        return

    conn = psycopg2.connect(DATABASE_URL)
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

def add_user_balance(telegram_id: int, credits: int):
    if not DATABASE_URL or not telegram_id or not credits:
        return

    ensure_user_exists(telegram_id)
    conn = psycopg2.connect(DATABASE_URL)
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
    conn = psycopg2.connect(DATABASE_URL)
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


def reset_developer_subscription(telegram_id: int, reset_credits: bool = False) -> dict:
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL is not configured")

    ensure_payment_tables()
    ensure_user_exists(telegram_id)

    conn = psycopg2.connect(DATABASE_URL)
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


def paypal_configured() -> bool:
    return bool(PAYPAL_CLIENT_ID and PAYPAL_CLIENT_SECRET)


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


def paypal_headers(api_base: str = None) -> dict:
    return {
        "Authorization": f"Bearer {paypal_access_token(api_base)}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def paypal_return_url(telegram_id: int, pack_id: str, status: str) -> str:
    params = urllib.parse.urlencode({
        "view": "shop",
        "payment": status,
        "provider": "paypal",
        "pack_id": pack_id or "",
        "telegram_id": str(telegram_id or ""),
    })
    return SHOP_WEBAPP_URL + ("&" if "?" in SHOP_WEBAPP_URL else "?") + params


def paypal_purchase_type(item: dict) -> str:
    return "subscription" if item.get("kind") == "subscription" else "tokens"


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


def paypal_approve_url(order: dict) -> str:
    for link in order.get("links") or []:
        if link.get("rel") in {"approve", "payer-action"} and link.get("href"):
            return link["href"]
    return ""


def save_paypal_order(telegram_id: int, pack_id: str, item: dict, order: dict, checkout_url: str):
    if not DATABASE_URL:
        return

    ensure_payment_tables()
    conn = psycopg2.connect(DATABASE_URL)
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
    conn = psycopg2.connect(DATABASE_URL)
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


def paypal_subscription_pack_for_plan(plan_id: str, plan_type: str = "") -> str:
    normalized_type = (plan_type or "").strip().lower()
    if plan_id == PAYPAL_PRO_MONTHLY_PLAN_ID or normalized_type in {"month", "monthly"}:
        return "sub_month"
    if plan_id == PAYPAL_PRO_YEARLY_PLAN_ID or normalized_type in {"year", "yearly", "annual"}:
        return "sub_year"
    return ""


def save_paypal_subscription(telegram_id: int, subscription_id: str, plan_id: str, plan_type: str = "") -> bool:
    if not DATABASE_URL:
        return False

    pack_id = paypal_subscription_pack_for_plan(plan_id, plan_type)
    item = shop_item(pack_id)
    if not item or not pack_id:
        return False

    ensure_payment_tables()
    ensure_user_exists(telegram_id)
    conn = psycopg2.connect(DATABASE_URL)
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


def activate_paypal_subscription_from_event(event: dict) -> bool:
    subscription_id = paypal_subscription_id_from_event(event)
    if not subscription_id or not DATABASE_URL:
        return False

    details = paypal_subscription_payment_details(event)
    ensure_payment_tables()
    conn = psycopg2.connect(DATABASE_URL)
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

def save_kling_settings_to_db(data):
    print("SAVE_KLING_FUNCTION_STARTED")
    duration_raw = str(data.get("duration", "5"))
    duration = int(duration_raw.split()[0])

    sound = 1 if data.get("sound") else 0
    prompt_enhance = 1 if data.get("prompt_enhance") else 0

    conn = psycopg2.connect(DATABASE_URL)
    cursor = conn.cursor()

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
        int(data.get("telegram_id")),
        data.get("model"),
        data.get("mode"),
        data.get("ratio"),
        data.get("quality"),
        duration,
        sound,
        prompt_enhance
    ))

    conn.commit()

@app.get("/")
async def root():
    return RedirectResponse("/webapp/index.html")


@app.get("/cabinet")
async def cabinet():
    return RedirectResponse("/webapp/index.html")

@app.get("/shop")
async def shop():
    return RedirectResponse("/webapp/index.html?view=shop")

@app.get("/payments")
async def payments():
    return FileResponse(WEBAPP_DIR / "payments.html")

@app.get("/elevenlabs")
async def elevenlabs_page():
    return FileResponse(WEBAPP_DIR / "elevenlabs.html")

@app.get("/heygen-voice")
async def heygen_voice_page():
    return FileResponse(WEBAPP_DIR / "heygen-voice.html")

def ensure_elevenlabs_table():
    if not DATABASE_URL:
        return

    conn = psycopg2.connect(DATABASE_URL)
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

def elevenlabs_headers(content_type: str = "application/json") -> dict:
    if not ELEVENLABS_API_KEY:
        raise RuntimeError("ELEVENLABS_API_KEY is not configured")

    headers = {"xi-api-key": ELEVENLABS_API_KEY}
    if content_type:
        headers["Content-Type"] = content_type
    return headers

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

def get_elevenlabs_settings_from_db(telegram_id: int) -> dict:
    defaults = default_elevenlabs_settings()
    if not DATABASE_URL or not telegram_id:
        return defaults

    ensure_elevenlabs_table()
    conn = psycopg2.connect(DATABASE_URL)
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
    conn = psycopg2.connect(DATABASE_URL)
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

def default_heygen_voice_settings() -> dict:
    return {
        "voice_id": "",
        "voice_name": "Auto",
        "model_id": HEYGEN_VOICE_MODEL_ID,
        "language": HEYGEN_DEFAULT_LANGUAGE,
        "speed": HEYGEN_DEFAULT_SPEED,
        "output_format": HEYGEN_DEFAULT_OUTPUT_FORMAT,
    }

def heygen_headers() -> dict:
    if not HEYGEN_API_KEY:
        raise RuntimeError("HEYGEN_API_KEY is not configured")

    return {
        "x-api-key": HEYGEN_API_KEY,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

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

def get_heygen_voice_settings_from_db(telegram_id: int) -> dict:
    defaults = default_heygen_voice_settings()
    if not DATABASE_URL or not telegram_id:
        return defaults

    ensure_elevenlabs_table()
    conn = psycopg2.connect(DATABASE_URL)
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
    conn = psycopg2.connect(DATABASE_URL)
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

@app.get("/api/elevenlabs/bootstrap")
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

@app.post("/api/elevenlabs/settings")
async def save_elevenlabs_settings(request: Request):
    data = await request.json()
    telegram_id = data.get("telegram_id")
    if not telegram_id:
        return JSONResponse({"success": False, "error": "telegram_id is required"}, status_code=400)

    save_elevenlabs_settings_to_db(data)
    return {"success": True, "message": "ElevenLabs settings saved"}

@app.post("/api/elevenlabs/preview")
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

@app.get("/api/heygen-voice/bootstrap")
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

@app.post("/api/heygen-voice/settings")
async def save_heygen_voice_settings(request: Request):
    data = await request.json()
    telegram_id = data.get("telegram_id")
    if not telegram_id:
        return JSONResponse({"success": False, "error": "telegram_id is required"}, status_code=400)
    if not data.get("voice_id"):
        return JSONResponse({"success": False, "error": "voice_id is required"}, status_code=400)

    save_heygen_voice_settings_to_db(data)
    return {"success": True, "message": "HeyGen Voice settings saved"}

@app.get("/api/public/config")
async def public_config():
    return {
        "ok": True,
        "webapp_url": WEBAPP_URL,
        "payment_webapp_url": PAYMENT_WEBAPP_URL,
        "shop_webapp_url": SHOP_WEBAPP_URL
    }

@app.get("/api/payment-links")
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

@app.post("/save-settings")
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

def verify_telegram_init_data(init_data: str) -> bool:
    if not init_data or not BOT_TOKEN:
        return False

    parsed = dict(urllib.parse.parse_qsl(init_data, keep_blank_values=True))
    received_hash = parsed.pop("hash", None)
    if not received_hash:
        return False

    data_check = "\n".join(f"{key}={parsed[key]}" for key in sorted(parsed))
    secret_key = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
    calculated_hash = hmac.new(secret_key, data_check.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(calculated_hash, received_hash)

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

def sync_user_to_db(user_data: dict) -> dict:
    if not DATABASE_URL or not user_data.get("telegram_id"):
        return user_data

    return get_user_state(
        telegram_id=int(user_data["telegram_id"]),
        username=user_data.get("username"),
        first_name=user_data.get("first_name") or "Guest",
    )

def save_generation(telegram_id: int, generation_type: str, prompt: str, status: str = "done"):
    if not DATABASE_URL or not telegram_id:
        return
    try:
        conn = psycopg2.connect(DATABASE_URL)
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

def ensure_prostudio_table():
    if not DATABASE_URL:
        return

    conn = psycopg2.connect(DATABASE_URL)
    cursor = conn.cursor()
    try:
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
        CREATE INDEX IF NOT EXISTS idx_prostudio_resources_user_type
        ON prostudio_resources (telegram_id, resource_type, updated_at DESC)
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
        cursor.close()
        conn.close()

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

def _safe_json_dumps(value) -> str:
    try:
        return json.dumps(value if value is not None else {}, ensure_ascii=False)
    except Exception:
        return "{}"

def create_prostudio_generation_job(payload: dict) -> str:
    job_id = str(uuid4())
    telegram_id = int(payload.get("telegram_id") or 0)
    if not DATABASE_URL or not telegram_id:
        return job_id
    try:
        ensure_prostudio_table()
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
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
        cursor.close()
        conn.close()
    except Exception as exc:
        print("PROSTUDIO JOB CREATE FAILED:", exc)
    return job_id

def update_prostudio_generation_job(job_id: str, status: str, result: Optional[dict] = None, error: Optional[dict] = None, conversation_id: str = ""):
    if not DATABASE_URL or not job_id:
        return
    try:
        ensure_prostudio_table()
        conn = psycopg2.connect(DATABASE_URL)
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
        conn.commit()
        cursor.close()
        conn.close()
    except Exception as exc:
        print("PROSTUDIO JOB UPDATE FAILED:", exc)

def claim_next_prostudio_generation_job() -> Optional[dict]:
    if not DATABASE_URL:
        return None
    try:
        ensure_prostudio_table()
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        try:
            cursor.execute("""
                UPDATE prostudio_generation_jobs
                SET status = 'processing',
                    attempts = COALESCE(attempts, 0) + 1,
                    locked_at = NOW(),
                    heartbeat_at = NOW(),
                    updated_at = NOW()
                WHERE id = (
                    SELECT id
                    FROM prostudio_generation_jobs
                    WHERE status = 'queued'
                      AND COALESCE(attempts, 0) < %s
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
            return None
        payload = _json_obj(row[1])
        return {"id": row[0], "payload": payload, "attempts": row[2] or 1}
    except Exception as exc:
        print("PROSTUDIO JOB CLAIM FAILED:", exc)
        return None

def requeue_stale_prostudio_jobs():
    if not DATABASE_URL:
        return
    try:
        ensure_prostudio_table()
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        try:
            cursor.execute("""
                UPDATE prostudio_generation_jobs
                SET status = CASE
                    WHEN COALESCE(attempts, 0) >= %s THEN 'failed'
                    ELSE 'queued'
                END,
                    error_json = CASE
                        WHEN COALESCE(attempts, 0) >= %s THEN %s::jsonb
                        ELSE error_json
                    END,
                    locked_at = NULL,
                    heartbeat_at = NULL,
                    updated_at = NOW(),
                    completed_at = CASE
                        WHEN COALESCE(attempts, 0) >= %s THEN NOW()
                        ELSE completed_at
                    END
                WHERE status IN ('processing', 'provider_processing')
                  AND COALESCE(heartbeat_at, updated_at, created_at) < NOW() - (%s || ' minutes')::interval
            """, (
                PROSTUDIO_MAX_JOB_ATTEMPTS,
                PROSTUDIO_MAX_JOB_ATTEMPTS,
                _safe_json_dumps({"ok": False, "error": "Generation worker timeout"}),
                PROSTUDIO_MAX_JOB_ATTEMPTS,
                PROSTUDIO_STALE_PROCESSING_MINUTES,
            ))
            conn.commit()
        finally:
            cursor.close()
            conn.close()
    except Exception as exc:
        print("PROSTUDIO STALE JOB REQUEUE FAILED:", exc)

def heartbeat_prostudio_generation_job(job_id: str):
    if not DATABASE_URL or not job_id:
        return
    try:
        conn = psycopg2.connect(DATABASE_URL)
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
        print("PROSTUDIO JOB HEARTBEAT FAILED:", exc)

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

def generation_has_completed_result(result: Optional[dict], mode: str = "") -> bool:
    if not isinstance(result, dict) or not result.get("ok"):
        return False
    if mode in {"text", "chat", "pro", "lite"}:
        return bool(result.get("text"))
    return bool(generation_result_urls(result, mode))

def normalize_generation_status(result: Optional[dict], mode: str = "") -> str:
    if not isinstance(result, dict):
        return "failed"
    raw = str(result.get("status") or "").strip().lower()
    if raw in {"failed", "error", "cancelled", "canceled"}:
        return "failed"
    if generation_has_completed_result(result, mode):
        return "completed"
    if result.get("task_id") or result.get("workId") or result.get("poll_url") or raw in {"processing", "queued", "submitted", "running", "pending"}:
        return "provider_processing"
    return "failed"

def log_prostudio_error(payload: dict, error: dict, job_id: str = ""):
    telegram_id = int(payload.get("telegram_id") or 0)
    if not DATABASE_URL:
        return
    try:
        ensure_prostudio_table()
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO prostudio_errors (
                telegram_id, job_id, provider, model, endpoint, request_id, status,
                error_text, request_json, response_json, stack_trace
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s)
        """, (
            telegram_id or None,
            job_id or None,
            error.get("provider") or payload.get("provider") or "",
            error.get("model") or payload.get("model") or "",
            error.get("endpoint") or "",
            error.get("request_id") or "",
            error.get("status") or "failed",
            error.get("error") or error.get("message") or str(error)[:1000],
            _safe_json_dumps(_sanitize_event_payload(payload, max_text=1200, max_items=40, depth=5)),
            _safe_json_dumps(_sanitize_event_payload(error, max_text=1200, max_items=50, depth=5)),
            error.get("stack_trace") or "",
        ))
        conn.commit()
        cursor.close()
        conn.close()
    except Exception as exc:
        print("PROSTUDIO ERROR LOG FAILED:", exc)

def save_prostudio_draft(telegram_id: int, mode: str, draft_text: str = "", conversation_id: str = "", attachment: Optional[dict] = None) -> dict:
    if not DATABASE_URL or not telegram_id:
        return {}
    mode = (mode or "image").strip().lower()
    if mode not in {"image", "video", "music", "voice"}:
        mode = "image"
    try:
        ensure_prostudio_table()
        conn = psycopg2.connect(DATABASE_URL)
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

def load_prostudio_drafts(telegram_id: int) -> dict:
    if not DATABASE_URL or not telegram_id:
        return {}
    try:
        ensure_prostudio_table()
        conn = psycopg2.connect(DATABASE_URL)
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

def save_prostudio_resource(telegram_id: int, resource: dict) -> dict:
    if not DATABASE_URL or not telegram_id:
        return resource or {}
    kind = (resource.get("resource_type") or resource.get("type") or resource.get("kind") or "").strip().lower()
    if kind in {"characters", "character"}:
        kind = "character"
    elif kind in {"objects", "object"}:
        kind = "object"
    else:
        return {}
    resource_id = resource.get("id") or f"custom_{kind}_{uuid4().hex}"
    photos = _json_list(resource.get("photos")) or _json_list(resource.get("referenceImages")) or _json_list(resource.get("reference_images"))
    preview = resource.get("previewUrl") or resource.get("preview_url") or (photos[0] if photos else "")
    item = {
        "id": resource_id,
        "name": resource.get("name") or "",
        "gender": resource.get("gender") or "",
        "description": resource.get("description") or "",
        "previewUrl": preview,
        "referenceImages": photos,
        "type": "custom",
        "status": resource.get("status") or "ready",
        "created_at": resource.get("created_at"),
    }
    try:
        ensure_prostudio_table()
        conn = psycopg2.connect(DATABASE_URL)
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

def load_prostudio_resources(telegram_id: int) -> dict:
    if not DATABASE_URL or not telegram_id:
        return {"characters": [], "objects": []}
    try:
        ensure_prostudio_table()
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, resource_type, name, description, gender, preview_url, photos_json, status, created_at, updated_at
            FROM prostudio_resources
            WHERE telegram_id = %s
            ORDER BY updated_at DESC
        """, (telegram_id,))
        rows = cursor.fetchall()
        cursor.close()
        conn.close()
        result = {"characters": [], "objects": []}
        for resource_id, kind, name, description, gender, preview, photos_json, status, created_at, updated_at in rows:
            photos = _json_list(photos_json)
            item = {
                "id": resource_id,
                "name": name or "",
                "description": description or "",
                "gender": gender or "",
                "previewUrl": preview or (photos[0] if photos else ""),
                "referenceImages": photos,
                "type": "custom",
                "status": status or "ready",
                "created_at": _to_iso(created_at),
                "updated_at": _to_iso(updated_at),
            }
            if kind == "character":
                result["characters"].append(item)
            elif kind == "object":
                result["objects"].append(item)
        return result
    except Exception as exc:
        print("PROSTUDIO RESOURCE LOAD FAILED:", exc)
        return {"characters": [], "objects": []}

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
    return {
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

def create_image_thumbnails(image_urls: list, size: int = 256) -> list:
    thumbs = []
    if not image_urls:
        return thumbs

    thumb_dir = WEBAPP_DIR / "generated" / "thumbs"
    thumb_dir.mkdir(parents=True, exist_ok=True)

    for url in image_urls:
        thumb_url = ""
        try:
            from PIL import Image
            import base64
            import io

            if str(url).startswith("data:"):
                raw = str(url).split(",", 1)[1] if "," in str(url) else ""
                content = base64.b64decode(raw)
            else:
                r = requests.get(url, timeout=45)
                if r.status_code >= 400 or not r.content:
                    raise ValueError("source_download_failed")
                content = r.content

            with Image.open(io.BytesIO(content)) as img:
                img = img.convert("RGB")
                img.thumbnail((size, size))
                filename = f"{uuid4().hex}.jpg"
                path = thumb_dir / filename
                img.save(path, format="JPEG", quality=78, optimize=True)
                thumb_url = f"/webapp/generated/thumbs/{filename}"
        except Exception as exc:
            print("THUMBNAIL CREATE FAILED:", type(exc).__name__)
            thumb_url = ""
        thumbs.append(thumb_url)
    return thumbs

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
        "image_url": result.get("image_url"),
        "thumbnail_url": result.get("thumbnail_url"),
        "thumb_url": result.get("thumb_url"),
        "preview_fallback_url": result.get("preview_fallback_url") or "",
    })
    return result

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
        ensure_prostudio_table()
        conn = psycopg2.connect(DATABASE_URL)
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
    except Exception as exc:
        print("PROSTUDIO MESSAGE SAVE FAILED:", exc)

    return conversation_id

def payment_url(pack_id: str, method: str = "paypal") -> str:
    params = urllib.parse.urlencode({
        "pack_id": pack_id or "",
        "method": method or "paypal",
    })
    return PAYMENT_WEBAPP_URL + ("&" if "?" in PAYMENT_WEBAPP_URL else "?") + params

@app.get("/api/public/prostudio/conversations")
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
        conn = psycopg2.connect(DATABASE_URL)
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

@app.delete("/api/public/prostudio/conversations")
async def delete_public_prostudio_conversation(
    telegram_id: int = 0,
    conversation_id: str = "",
):
    if not DATABASE_URL or not telegram_id or not conversation_id:
        return {"ok": True}

    try:
        ensure_prostudio_table()
        conn = psycopg2.connect(DATABASE_URL)
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

@app.get("/api/public/prostudio/sync")
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
            conn = psycopg2.connect(DATABASE_URL)
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

@app.get("/api/public/prostudio/draft")
async def public_prostudio_get_draft(telegram_id: int = 0, mode: str = ""):
    if not telegram_id:
        return JSONResponse({"ok": False, "error": "telegram_id_required"}, status_code=400)
    drafts = load_prostudio_drafts(telegram_id)
    normalized = (mode or "").strip().lower()
    if normalized:
        return {"ok": True, "draft": drafts.get(normalized) or {}}
    return {"ok": True, "drafts": drafts}

@app.post("/api/public/prostudio/draft")
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

@app.get("/api/public/prostudio/resources")
async def public_prostudio_get_resources(telegram_id: int = 0):
    if not telegram_id:
        return JSONResponse({"ok": False, "error": "telegram_id_required"}, status_code=400)
    return {"ok": True, "resources": load_prostudio_resources(telegram_id)}

@app.post("/api/public/prostudio/resources")
async def public_prostudio_save_resource(request: Request):
    data = await request.json()
    telegram_id = int(data.get("telegram_id") or 0)
    if not telegram_id:
        return JSONResponse({"ok": False, "error": "telegram_id_required"}, status_code=400)
    item = save_prostudio_resource(telegram_id, data)
    if not item:
        return JSONResponse({"ok": False, "error": "invalid_resource"}, status_code=400)
    return {"ok": True, "resource": item}

@app.post("/api/public/prostudio/events")
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

@app.get("/api/public/prostudio/generation-jobs")
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
            conn = psycopg2.connect(DATABASE_URL)
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

@app.get("/api/public/prostudio/job/{job_id}")
async def public_prostudio_job(job_id: str):
    if not DATABASE_URL:
        return JSONResponse(
            {"ok": False, "error": "database_not_configured"},
            status_code=500,
        )

    try:
        ensure_prostudio_table()

        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT
                status,
                result_json,
                error_json,
                conversation_id
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
        print("PROSTUDIO JOB GET DEBUG:", {
            "job_id": job_id,
            "status": row[0],
            "conversation_id": row[3],
            "result_keys": sorted(result_json.keys()) if isinstance(result_json, dict) else [],
            "image_url": result_json.get("image_url") if isinstance(result_json, dict) else "",
            "thumbnail_url": result_json.get("thumbnail_url") if isinstance(result_json, dict) else "",
            "images": _json_list(result_json.get("images")) if isinstance(result_json, dict) else [],
            "thumbnails": _json_list(result_json.get("thumbnails")) if isinstance(result_json, dict) else [],
            "metadata_image_url": ((result_json.get("metadata") or {}).get("image_url") if isinstance(result_json.get("metadata"), dict) else "") if isinstance(result_json, dict) else "",
            "metadata_thumbnail_url": ((result_json.get("metadata") or {}).get("thumbnail_url") if isinstance(result_json.get("metadata"), dict) else "") if isinstance(result_json, dict) else "",
        })

        return {
            "ok": True,
            "generation_id": job_id,
            "job_id": job_id,
            "status": row[0],
            "result": result_json,
            "error": error_json,
            "conversation_id": row[3],
        }

    except Exception as exc:
        print("PROSTUDIO JOB GET FAILED:", exc)
        return JSONResponse(
            {"ok": False, "error": "job_read_failed"},
            status_code=500,
        )

@app.post("/api/public/payments/paypal/create-order")
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


@app.post("/api/public/payments/paypal/subscription-created")
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


@app.post("/api/public/payments/paypal/webhook")
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

@app.post("/api/public/payments/stars/invoice")
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
        print("STARS INVOICE ERROR:", exc)
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

@app.post("/api/public/payments/stars/confirm")
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

    payload = bot_stars_payload(telegram_id, item, charge_id)
    created = finalize_shop_payment(
        telegram_id=telegram_id,
        provider="telegram_stars",
        item=item,
        amount=int(item.get("stars") or 0),
        currency="XTR",
        payload=payload,
        charge_id=charge_id,
    )

    user = sync_user_to_db({
        "telegram_id": telegram_id,
        "username": data.get("username") or None,
        "first_name": data.get("first_name") or "Telegram User",
        "status": "free",
        "balance": 0,
    })

    return {
        "ok": True,
        "created": created,
        "user": user,
        "pack_id": pack_id,
        "charge_id": charge_id,
    }

# Developer payment endpoint for simulating successful payments (dev only)
@app.post("/api/public/payments/dev/success")
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
@app.post("/api/public/payments/dev/reset")
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

@app.post("/api/public/payments/crypto/invoice")
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

@app.post("/api/public/telegram/sync")
async def public_telegram_sync(request: Request):
    payload = await request.json()
    init_data = payload.get("initData") or ""
    user_data = fallback_public_user(payload)

    # Telegram clients provide signed initData. In browser/dev preview we still
    # return optimistic initDataUnsafe fields so the Mini App can render.
    if init_data and BOT_TOKEN and not verify_telegram_init_data(init_data):
        return JSONResponse({"ok": False, "error": "invalid_init_data", "user": user_data}, status_code=401)

    try:
        user = sync_user_to_db(user_data)
        log_user_event(
            telegram_id=user_data.get("telegram_id"),
            source="mini_app",
            event_type="sync",
            event_name="user_sync",
            payload={
                "subscription_plan": user.get("subscription_plan"),
                "subscription_expires_at": user.get("subscription_expires_at"),
                "status": user.get("status"),
                "balance": user.get("balance"),
            },
        )
    except Exception as exc:
        print("USER SYNC FAILED:", exc)
        user = user_data

    return {"ok": True, "user": user}


@app.get("/api/public/telegram/user-state")
async def public_telegram_user_state(telegram_id: int = 0):
    if not telegram_id:
        return JSONResponse({"ok": False, "error": "telegram_id_required"}, status_code=400)
    try:
        return get_fast_user_state(int(telegram_id))
    except Exception as exc:
        print("USER STATE FAILED:", exc)
        return JSONResponse({"ok": False, "error": "user_state_failed"}, status_code=500)


@app.post("/api/public/telegram/profile")
async def public_telegram_profile(request: Request):
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

    profile = save_user_profile(
        telegram_id=telegram_id,
        display_name=payload.get("display_name"),
        custom_avatar_url=payload.get("custom_avatar_url"),
        theme_preference=payload.get("theme_preference"),
    )
    user = sync_user_to_db({"telegram_id": telegram_id})
    user.update(profile)

    log_user_event(
        telegram_id=telegram_id,
        source="mini_app",
        event_type="profile",
        event_name="profile_update",
        payload={
            "has_display_name": bool(payload.get("display_name")),
            "has_custom_avatar": bool(payload.get("custom_avatar_url")),
            "theme_preference": payload.get("theme_preference") or {},
        },
    )

    return {"ok": True, "profile": profile, "user": user}


@app.get("/api/public/telegram/referrals")
async def public_telegram_referrals(telegram_id: int = 0):
    if not telegram_id:
        return JSONResponse({"ok": False, "error": "telegram_id_required"}, status_code=400)
    return get_referral_state(int(telegram_id), activate=False)


@app.post("/api/public/telegram/referrals")
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

    state = get_referral_state(int(telegram_id), activate=bool(payload.get("activate", True)))
    log_user_event(
        telegram_id=telegram_id,
        source="mini_app",
        event_type="referral",
        event_name="referral_link_activated",
        payload={"code": state.get("code")},
    )
    return state


@app.post("/api/public/events")
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


@app.get("/api/public/events")
async def public_get_events(telegram_id: int = 0):
    if not telegram_id:
        return JSONResponse({"ok": False, "error": "telegram_id_required"}, status_code=400)

    if not DATABASE_URL:
        return JSONResponse({"ok": False, "error": "database_not_configured"}, status_code=500)

    ensure_user_events_table()
    conn = psycopg2.connect(DATABASE_URL)
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


def openai_headers():
    return {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json",
    }

def image_size(label: str) -> dict:
    ratio = label
    if "x" in label:
        try:
            w, h = [int(part) for part in label.lower().split("x", 1)]
            ratio = f"{w // math_gcd(w, h)}:{h // math_gcd(w, h)}"
        except Exception:
            ratio = label
    return {"id": label, "label": ratio, "ratio": ratio, "icon": ratio}

def math_gcd(a: int, b: int) -> int:
    while b:
        a, b = b, a % b
    return max(a, 1)

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
            "objects_ready": False,
        })
    return models

def get_image_capabilities() -> dict:
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

def map_image_model_to_provider_model(frontend_model: str) -> Optional[str]:
    value = (frontend_model or "").strip()
    if not value:
        return None
    normalized = value.lower()
    provider_cfg = IMAGE_PROVIDER_MODEL_MAP.get(normalized) or IMAGE_PROVIDER_MODEL_MAP.get(normalized.replace("-", "_"))
    if provider_cfg:
        return provider_cfg.get("provider_model")
    return BYTEPLUS_SEEDREAM_MODEL_MAP.get(normalized) or BYTEPLUS_SEEDREAM_MODEL_MAP.get(normalized.replace("-", "_"))

def image_provider_mapping(frontend_model: str) -> dict:
    value = (frontend_model or "").strip()
    normalized = value.lower()
    return IMAGE_PROVIDER_MODEL_MAP.get(normalized) or IMAGE_PROVIDER_MODEL_MAP.get(normalized.replace("-", "_")) or {}

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

def unknown_byteplus_image_model_response(frontend_model: str) -> dict:
    return {
        "ok": False,
        "error": "Unknown BytePlus image model mapping",
        "frontend_model": frontend_model or "",
        "provider": "bytedance",
    }

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

def is_internal_ui_model(model: str) -> bool:
    return (model or "").strip().lower() in {"sylvex-pro", "sylvex-lite", "sylvex pro", "sylvex lite"}

def invalid_generation_model_response(model: str) -> JSONResponse:
    return JSONResponse(
        {
            "ok": False,
            "error": "Invalid generation model",
            "details": f"{model} is an internal UI label, not an API model. Frontend must send real image/video/music/voice model id.",
        },
        status_code=400,
    )

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

def normalize_payload_image_seed(payload: dict):
    opts = payload.get("image_options") or {}
    if not isinstance(opts, dict):
        opts = {}
    seed = normalize_image_seed(opts.get("seed"))
    opts["seed"] = seed
    payload["image_options"] = opts
    return seed

def is_seedream_request(payload: dict) -> bool:
    model = str(payload.get("model") or "")
    provider = str(payload.get("provider") or "").lower()
    opts = payload.get("image_options") or {}
    option_model = str(opts.get("modelId") or opts.get("model_id") or "")
    return provider in ("bytedance", "byteplus") or bool(re.search(r"seedream", f"{model} {option_model}", re.I))

def build_image_prompt(payload: dict) -> str:
    opts = payload.get("image_options") or {}

    base_prompt = (
        payload.get("prompt")
        or payload.get("text")
        or payload.get("input")
        or ""
    ).strip()

    parts = [base_prompt] if base_prompt else []

    character_name = str(opts.get("characterName") or "").strip()
    object_name = str(opts.get("objectName") or opts.get("objects") or "").strip()
    if character_name:
        parts.append(f"Use the selected character reference as the main person: {character_name}. Preserve identity from the provided reference images.")
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

    if refs:
        parts.append(
            "Use the uploaded reference images as visual references. "
            "If the user asks to merge/combine photos, combine the important visual elements from all uploaded reference images."
        )

    return "\n".join(parts).strip()

def normalize_image_response(data: dict) -> list:
    images = []
    for item in data.get("data", []) if isinstance(data, dict) else []:
        if item.get("url"):
            images.append(item["url"])
        elif item.get("b64_json"):
            images.append("data:image/png;base64," + item["b64_json"])
    return images

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

def safe_image_count(value, default: int = 1, max_count: int = 4) -> int:
    try:
        count = int(value or default)
    except Exception:
        count = default
    return max(1, min(count, max_count))


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

    refs = [u for u in (reference_images or []) if isinstance(u, str) and u.strip()]

    if refs:
        body["image"] = refs[0]

    return body

def request_byteplus_seedream_image(model: str, prompt: str, reference_images=None, size: str = "", seed=None) -> tuple:
    refs = [u for u in (reference_images or []) if isinstance(u, str) and u.strip()]
    is_pro_model = "dola-seedream-5-0-pro" in str(model or "").lower()
    try:
        timeout_seconds = int(os.getenv("BYTEPLUS_SEEDREAM_PRO_TIMEOUT" if is_pro_model else "BYTEPLUS_SEEDREAM_TIMEOUT") or (360 if is_pro_model else 120))
    except Exception:
        timeout_seconds = 360 if is_pro_model else 120

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
        if not is_pro_model:
            return [], "ReadTimeout"
        print("BYTEPLUS IMAGE PRO TIMEOUT, RETRY ONCE")
        try:
            response = _send(bool(refs))
        except Exception as exc:
            return [], type(exc).__name__
    except Exception as exc:
        return [], type(exc).__name__

    if response.status_code >= 400 and refs:
        print(
            "BYTEPLUS IMAGE REFERENCE REQUEST FAILED, RETRY WITHOUT REFERENCES:",
            response.status_code,
            response.text[:500],
        )
        try:
            response = _send(False)
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

    reference_images = (
        opts.get("referenceImageUrls")
        or opts.get("reference_image_urls")
        or opts.get("referenceImages")
        or opts.get("images")
        or []
    )
    if isinstance(reference_images, str):
        reference_images = [reference_images]
    reference_images = [u for u in reference_images if isinstance(u, str) and u.strip()]
    if reference_images:
        print("BYTEPLUS IMAGE REFERENCES:", len(reference_images))

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
    if telegram_id:
        try:
            asyncio.create_task(
                send_generated_images_to_telegram(
                    telegram_id=telegram_id,
                    images=images,
                    caption="Готово ✅\nСгенерировано в SYLVEX Pro Studio",
                )
            )
        except Exception as exc:
            print("TELEGRAM SEND GENERATED IMAGES FAILED:", str(exc))

    result["sent_to_telegram"] = sent_to_telegram
    return result

def text_generation(payload: dict) -> dict:
    prompt = (payload.get("prompt") or "").strip()
    history = payload.get("history") or []
    mode = payload.get("mode") or "text"
    model = payload.get("model") or "gpt-4o-mini"
    if is_internal_ui_model(model):
        model = "gpt-4o-mini"
    attachment = payload.get("attachment") or {}

    messages = [
        {
            "role": "system",
            "content": (
                "You are SYLVEX Pro Studio inside a Telegram Mini App. "
                "Help users create images, videos, music, voiceovers, text, and plans. "
                "Be concise, practical, and production-ready."
            )
        }
    ]
    for item in history[-10:]:
        role = item.get("role") if item.get("role") in ("user", "assistant") else "user"
        content = item.get("content")
        if content:
            messages.append({"role": role, "content": content})
    if attachment:
        prompt = (prompt + f"\n\nAttachment: {attachment.get('name')} ({attachment.get('mime')})").strip()
    messages.append({"role": "user", "content": f"Mode: {mode}\nPrompt: {prompt}"})

    if not OPENAI_API_KEY:
        return {
            "ok": True,
            "type": "text",
            "text": "SYLVEX Pro Studio is connected. Add OPENAI_API_KEY to enable live generation.\n\nPrompt: " + prompt
        }

    response = requests.post(
        f"{OPENAI_API_BASE}/chat/completions",
        headers=openai_headers(),
        data=json.dumps({"model": model if model != "gpt-image-1" else "gpt-4o-mini", "messages": messages}),
        timeout=60,
    )
    if response.status_code >= 400:
        return {"ok": False, "error": response.text}
    data = response.json()
    return {
        "ok": True,
        "type": "text",
        "text": data.get("choices", [{}])[0].get("message", {}).get("content", "")
    }

def normalize_openai_image_size(size: str) -> str:
    raw = str(size or "").strip()
    if raw in {"1024x1024", "1536x1024", "1024x1536", "auto"}:
        return raw
    if raw in {"1:1", "square"}:
        return "1024x1024"
    if raw in {"16:9", "landscape"}:
        return "1536x1024"
    if raw in {"9:16", "portrait"}:
        return "1024x1536"
    return "1024x1024"


def image_reference_urls(payload: dict) -> list:
    opts = payload.get("image_options") or {}
    refs = []
    for value in (
        opts.get("referenceImageUrls"),
        opts.get("reference_image_urls"),
        opts.get("referenceImages"),
        opts.get("images"),
        opts.get("characterReferences"),
        opts.get("objectReferences"),
    ):
        if isinstance(value, str):
            refs.append(value)
        elif isinstance(value, list):
            refs.extend(value)
    clean = []
    for url in refs:
        if isinstance(url, str) and url.strip() and url not in clean:
            clean.append(url)
    return clean

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


def image_error_response(provider: str, frontend_model: str, provider_model: str, endpoint: str, error: str, response=None, data: dict = None) -> dict:
    status_code = getattr(response, "status_code", None) if response is not None else None
    body_preview = ""
    if data:
        status_code = data.get("status_code") or status_code
        body_preview = data.get("body_preview") or ""
    if response is not None and not body_preview:
        try:
            body_preview = response.text[:1000]
        except Exception:
            body_preview = ""
    return {
        "ok": False,
        "type": "image",
        "error": error,
        "provider": provider,
        "frontend_model": frontend_model or "",
        "provider_model": provider_model or "",
        "endpoint": endpoint or "",
        "status_code": status_code,
        "body_preview": body_preview,
    }


async def finalize_image_result(payload: dict, images: list) -> dict:
    result = attach_image_thumbnails({"ok": True, "type": "image", "image_url": images[0], "images": images})
    telegram_id = int(payload.get("telegram_id") or 0)
    result["sent_to_telegram"] = telegram_id > 0
    if telegram_id:
        try:
            result["sent_to_telegram"] = await send_generated_images_to_telegram(
                telegram_id=telegram_id,
                images=images,
                caption="Готово ✅\nСгенерировано в SYLVEX Pro Studio",
            )
        except Exception as exc:
            print("TELEGRAM SEND GENERATED IMAGES FAILED:", str(exc))
    return result


def flux_headers() -> dict:
    api_key = os.getenv("BFL_API_KEY") or os.getenv("FLUX_API_KEY") or os.getenv("FLUX-API-KEY")
    if not api_key:
        return {}
    return {"accept": "application/json", "x-key": api_key, "Content-Type": "application/json"}


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


def ideogram_headers(json_content: bool = True) -> dict:
    api_key = env_value("IDEOGRAM_API_KEY", "IDEOGRAM-API-KEY")
    if not api_key:
        return {}
    headers = {"Api-Key": api_key}
    if json_content:
        headers["Content-Type"] = "application/json"
    return headers


def ideogram_frontend_model(frontend_model: str, provider_model: str = "") -> str:
    raw = str(frontend_model or "").strip().replace("-", "_")
    if raw in IDEOGRAM_MODEL_VARIANTS:
        return raw
    model = str(provider_model or "").lower()
    if "v4" in model or raw in {"ideogram_4", "ideogram_4_0"}:
        return "ideogram_4_0"
    return "ideogram_3_0"


def ideogram_rendering_speed(frontend_model: str, provider_model: str, opts: Optional[dict] = None) -> str:
    key = ideogram_frontend_model(frontend_model, provider_model)
    cfg = IDEOGRAM_MODEL_VARIANTS.get(key) or {}
    speed = str((opts or {}).get("rendering_speed") or cfg.get("rendering_speed") or "TURBO").upper()
    if key == "ideogram_4_0" and speed == "FLASH":
        return "TURBO"
    valid = {"FLASH", "TURBO", "DEFAULT", "QUALITY"}
    return speed if speed in valid else str(cfg.get("rendering_speed") or "TURBO").upper()


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


def recraft_headers() -> dict:
    api_key = env_value("RECRAFT_API_KEY", "RECRAFT-API-KEY")
    if not api_key:
        return {}
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }


def recraft_size_value(size: str) -> str:
    raw = str(size or "").strip()
    if raw.lower() in {"", "auto"}:
        return ""
    supported = {"1:1", "16:9", "9:16", "3:4", "4:3"}
    return raw if raw in supported else "1:1"


def recraft_available_tools(frontend_model: str, provider_model: str = "") -> list:
    key = recraft_frontend_model(frontend_model, provider_model)
    cfg = RECRAFT_MODEL_VARIANTS.get(key) or {}
    tools = []
    for tool_id in cfg.get("tools") or []:
        item = RECRAFT_TOOL_CATALOG.get(tool_id)
        if item:
            tools.append({"id": tool_id, **item})
    return tools


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


def flux_frontend_model(frontend_model: str, provider_model: str = "") -> str:
    raw = str(frontend_model or "").strip().replace("-", "_").lower()
    if raw in FLUX_MODEL_VARIANTS:
        return raw
    model = str(provider_model or "").lower()
    if model == "flux-2-flex":
        return "flux_2_turbo"
    return "flux_2"


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


def estimate_generation_cost(payload: dict) -> dict:
    mode = (payload.get("mode") or payload.get("category") or "").lower()
    if mode != "image":
        return {"credits": 0, "cost_usd": 0, "generation_cost": ""}
    opts = payload.get("image_options") or {}
    requested_model = opts.get("modelId") or opts.get("model_id") or payload.get("model")
    mapping = image_provider_mapping(requested_model) if requested_model else {}
    provider = (mapping.get("provider") or payload.get("provider") or "").strip().lower()
    api_model = mapping.get("provider_model") or ""
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


def ideogram_form_files(request_payload: dict) -> dict:
    return {
        key: (None, str(value))
        for key, value in (request_payload or {}).items()
        if value is not None and value != ""
    }


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


async def image_generation(payload: dict) -> dict:
    opts = payload.get("image_options") or {}
    prompt = build_image_prompt(payload)
    requested_model = opts.get("modelId") or opts.get("model_id") or payload.get("model")
    frontend_provider = (payload.get("provider") or "").strip().lower()
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
        if image_reference_urls(payload):
            return image_error_response(provider, requested_model, api_model, f"{OPENAI_API_BASE}/images/generations", "Selected model does not support image-to-image")

        endpoint = f"{OPENAI_API_BASE}/images/generations"
        openai_size = normalize_openai_image_size(size)
        try:
            response = requests.post(
                endpoint,
                headers=openai_headers(),
                data=json.dumps({
                    "model": api_model,
                    "prompt": prompt,
                    "size": openai_size,
                    "n": 1,
                }),
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
        images = normalize_image_response(data)
        if images:
            return await finalize_image_result(payload, images[:count])
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

@app.get("/api/public/prostudio/image-capabilities")
async def public_prostudio_image_capabilities():
    return get_image_capabilities()

@app.get("/api/public/prostudio/download-image")
async def download_prostudio_image(url: str):
    return await download_prostudio_content(url=url, kind="image")

@app.get("/api/public/prostudio/download-content")
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

@app.post("/api/public/prostudio/generate")
async def public_prostudio_generate(request: Request):
    payload = await request.json()
    mode = (payload.get("mode") or payload.get("category") or "text").lower()
    category = (payload.get("category") or mode).lower()
    prompt = (payload.get("prompt") or "").strip()
    selected_model = (payload.get("model") or "").strip()
    selected_provider = (payload.get("provider") or "sylvex-router").strip().lower()
    image_options = payload.get("image_options") or {}
    video_options = payload.get("video_options") or {}
    reference_images = image_options.get("referenceImageUrls") or []
    video_references = (
        video_options.get("reference_images")
        or video_options.get("referenceImageUrls")
        or []
    )
    video_media = (
        video_options.get("start_image")
        or video_options.get("end_image")
        or video_options.get("input_video")
        or video_options.get("video_url")
        or video_options.get("image_url")
        or video_options.get("character_image")
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
    if mode in generation_modes and is_internal_ui_model(selected_model):
        return invalid_generation_model_response(selected_model)

    if not prompt and not payload.get("attachment") and not reference_images and not video_references and not video_media:
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

    if mode in text_modes:
        if not selected_model or is_internal_ui_model(selected_model):
            payload["model"] = "gpt-4o-mini"
        result = text_generation(payload)
        if not result.get("ok"):
            return JSONResponse(result, status_code=502)
        result["conversation_id"] = save_prostudio_message(payload, result)
        return result

    job_id = create_prostudio_generation_job(payload) if mode in generation_modes else ""
    if job_id:
        log_user_event(
            int(payload.get("telegram_id") or 0),
            "miniapp",
            "generation",
            "generation_queued",
            {"job_id": job_id, "mode": mode, "model": selected_model, "provider": selected_provider},
        )

    if not PROSTUDIO_WORKER_ENABLED:
        asyncio.create_task(process_prostudio_generation(job_id, payload))

    return {
        "ok": True,
        "job_id": job_id,
        "generation_id": job_id,
        "status": "queued"
    }


# New async function for background job processing
async def process_prostudio_generation(job_id: str, payload: dict):
    try:
        mode = (payload.get("mode") or payload.get("category") or "text").lower()
        category = (payload.get("category") or mode).lower()
        prompt = (payload.get("prompt") or "").strip()
        selected_model = (payload.get("model") or "").strip()
        selected_provider = (payload.get("provider") or "sylvex-router").strip().lower()
        image_options = payload.get("image_options") or {}
        video_options = payload.get("video_options") or {}
        reference_images = image_options.get("referenceImageUrls") or []
        video_references = (
            video_options.get("reference_images")
            or video_options.get("referenceImageUrls")
            or []
        )
        video_media = (
            video_options.get("start_image")
            or video_options.get("end_image")
            or video_options.get("input_video")
            or video_options.get("video_url")
            or video_options.get("image_url")
            or video_options.get("character_image")
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
        log_user_event(
            int(payload.get("telegram_id") or 0),
            "worker",
            "generation",
            "generation_started",
            {"job_id": job_id, "mode": mode, "model": selected_model, "provider": selected_provider},
        )
        result = None
        if mode == "image" and is_seedream_request(payload):
            result = await generateBytePlusSeedreamImage(payload)
        elif mode == "image":
            result = await image_generation(payload)
        elif mode == "video":
            result = await video_generation(payload)
        elif mode == "music":
            result = await audio_generation(payload)
        elif mode == "voice":
            result = {
                "ok": False,
                "type": "voice",
                "provider": selected_provider or "voice",
                "model": selected_model,
                "error": "Voice router is not connected yet",
            }
        elif mode in text_modes:
            if not selected_model or is_internal_ui_model(selected_model):
                payload["model"] = "gpt-4o-mini"
            result = text_generation(payload)
        else:
            result = {"ok": False, "error": "Unknown generation mode", "mode": mode}

        if not result.get("ok"):
            if job_id:
                update_prostudio_generation_job(job_id, "failed", error=result)
                log_prostudio_error(payload, result, job_id=job_id)
            return

        final_status = normalize_generation_status(result, mode)
        result["job_id"] = job_id
        result["generation_id"] = job_id
        result["status"] = final_status

        if final_status == "provider_processing":
            update_prostudio_generation_job(job_id, "provider_processing", result=result)
            log_user_event(
                int(payload.get("telegram_id") or 0),
                "worker",
                "generation",
                "generation_provider_processing",
                {
                    "job_id": job_id,
                    "mode": mode,
                    "task_id": result.get("task_id") or result.get("workId"),
                    "poll_url": result.get("poll_url"),
                },
            )
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
            return

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

        save_generation(telegram_id, mode, prompt or "[attachment]")
        metadata = build_prostudio_metadata(payload, result)
        if metadata:
            result["metadata"] = metadata
        result["conversation_id"] = save_prostudio_message(payload, result)
        if job_id:
            print("PROSTUDIO JOB COMPLETED PAYLOAD:", {
                "job_id": job_id,
                "conversation_id": result["conversation_id"],
                "result_keys": sorted(result.keys()),
                "image_url": result.get("image_url"),
                "thumbnail_url": result.get("thumbnail_url"),
                "metadata_image_url": (result.get("metadata") or {}).get("image_url") if isinstance(result.get("metadata"), dict) else "",
                "metadata_thumbnail_url": (result.get("metadata") or {}).get("thumbnail_url") if isinstance(result.get("metadata"), dict) else "",
                "generation_cost": result.get("generation_cost"),
                "cost_credits": result.get("cost_credits"),
            })
            update_prostudio_generation_job(job_id, "completed", result=result, conversation_id=result["conversation_id"])
            log_user_event(
                int(payload.get("telegram_id") or 0),
                "backend",
                "generation",
                "generation_completed",
                {"job_id": job_id, "mode": mode, "conversation_id": result["conversation_id"]},
            )
    except Exception as exc:
        import traceback
        error_result = {"ok": False, "error": str(exc), "traceback": traceback.format_exc()}
        if job_id:
            update_prostudio_generation_job(job_id, "failed", error=error_result)

async def prostudio_generation_worker_loop():
    if not PROSTUDIO_WORKER_ENABLED:
        print("PROSTUDIO WORKER DISABLED")
        return
    print("PROSTUDIO WORKER STARTED")
    while True:
        try:
            requeue_stale_prostudio_jobs()
            claimed = claim_next_prostudio_generation_job()
            if claimed and claimed.get("id") and claimed.get("payload"):
                await process_prostudio_generation(claimed["id"], claimed["payload"])
                continue
        except Exception as exc:
            print("PROSTUDIO WORKER LOOP ERROR:", exc)
        await asyncio.sleep(PROSTUDIO_WORKER_INTERVAL)

@app.on_event("startup")
async def start_prostudio_generation_worker():
    if PROSTUDIO_WORKER_ENABLED:
        asyncio.create_task(prostudio_generation_worker_loop())

@app.post("/api/public/prostudio/transcribe")
async def public_prostudio_transcribe(request: Request):
    form = await request.form()
    file = form.get("file")
    if not file or not hasattr(file, "read"):
        return JSONResponse({"ok": False, "error": "File is required"}, status_code=400)

    content = await file.read()
    if not content:
        return JSONResponse({"ok": False, "error": "Empty file"}, status_code=400)
    if not OPENAI_API_KEY:
        return {"ok": False, "error": "OPENAI_API_KEY is not configured"}

    response = requests.post(
        f"{OPENAI_API_BASE}/audio/transcriptions",
        headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
        files={"file": (
            getattr(file, "filename", None) or "voice.webm",
            content,
            getattr(file, "content_type", None) or "audio/webm",
        )},
        data={"model": os.getenv("OPENAI_TRANSCRIBE_MODEL", "whisper-1")},
        timeout=120,
    )
    if response.status_code >= 400:
        return JSONResponse({"ok": False, "error": response.text}, status_code=502)
    return {"ok": True, "text": response.json().get("text", "")}

@app.get("/api/cabinet/{telegram_id}")
async def get_cabinet(telegram_id: int):

    conn = psycopg2.connect(DATABASE_URL)
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
