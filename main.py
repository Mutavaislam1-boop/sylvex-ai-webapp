import os
import pathlib
import json
import hmac
import hashlib
import urllib.parse
import requests
import psycopg2
from fastapi.responses import JSONResponse, RedirectResponse



from fastapi import FastAPI, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

app = FastAPI()

BASE_DIR = pathlib.Path(__file__).resolve().parent
WEBAPP_DIR = BASE_DIR / "webapp"

app.mount("/webapp", StaticFiles(directory=WEBAPP_DIR, html=True), name="webapp")
app.mount("/static", StaticFiles(directory=WEBAPP_DIR), name="static")
app.mount("/image", StaticFiles(directory="image"), name="image")
app.mount("/assets", StaticFiles(directory="webapp/assets"), name="assets")
app.mount("/js", StaticFiles(directory="webapp/js"), name="js")
app.mount("/css", StaticFiles(directory="webapp/css"), name="css")


BOT_TOKEN = os.getenv("BOT_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")
print("MINIAPP DATABASE:", DATABASE_URL)
WEBAPP_URL = os.getenv("WEBAPP_URL", "https://sylvex-ai-webapp-production.up.railway.app")
PAYMENT_WEBAPP_URL = os.getenv("PAYMENT_WEBAPP_URL", WEBAPP_URL.rstrip("/") + "/payments")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_API_BASE = os.getenv("OPENAI_API_BASE", "https://api.openai.com/v1").rstrip("/")


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

@app.get("/payments")
async def payments():
    return FileResponse(WEBAPP_DIR / "payments.html")

@app.get("/api/public/config")
async def public_config():
    return {
        "ok": True,
        "webapp_url": WEBAPP_URL,
        "payment_webapp_url": PAYMENT_WEBAPP_URL
    }

@app.get("/api/payment-links")
async def payment_links():
    return {
        "success": True,
        "packages": {
            "100": os.getenv("LEMON_100_CREDITS_URL", ""),
            "500": os.getenv("LEMON_500_CREDITS_URL", ""),
            "1000": os.getenv("LEMON_1000_CREDITS_URL", "")
        }
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

    conn = psycopg2.connect(DATABASE_URL)
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO users (telegram_id, username, first_name)
            VALUES (%s, %s, %s)
            ON CONFLICT (telegram_id) DO UPDATE SET
                username = EXCLUDED.username,
                first_name = EXCLUDED.first_name
            RETURNING telegram_id, username, first_name, balance, subscription, created_at
        """, (
            int(user_data["telegram_id"]),
            user_data.get("username"),
            user_data.get("first_name") or "Guest",
        ))
        row = cursor.fetchone()
        conn.commit()
    finally:
        cursor.close()
        conn.close()

    subscription = row[4] or user_data.get("status") or "free"
    return {
        **user_data,
        "telegram_id": row[0],
        "username": row[1],
        "first_name": row[2],
        "balance": row[3] or 0,
        "status": subscription,
        "created_at": row[5],
    }

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
    except Exception as exc:
        print("USER SYNC FAILED:", exc)
        user = user_data

    return {"ok": True, "user": user}

def openai_headers():
    return {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json",
    }

def text_generation(payload: dict) -> dict:
    prompt = (payload.get("prompt") or "").strip()
    history = payload.get("history") or []
    mode = payload.get("mode") or "text"
    model = payload.get("model") or "gpt-4o-mini"
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

def image_generation(payload: dict) -> dict:
    prompt = (payload.get("prompt") or "").strip()
    if not OPENAI_API_KEY:
        return {
            "ok": True,
            "type": "text",
            "text": "Image generation is ready. Add OPENAI_API_KEY to generate images.\n\nPrompt: " + prompt
        }

    response = requests.post(
        f"{OPENAI_API_BASE}/images/generations",
        headers=openai_headers(),
        data=json.dumps({"model": "gpt-image-1", "prompt": prompt, "size": "1024x1024"}),
        timeout=120,
    )
    if response.status_code >= 400:
        return {"ok": False, "error": response.text}

    data = response.json().get("data", [{}])[0]
    if data.get("url"):
        return {"ok": True, "type": "image", "image_url": data["url"]}
    if data.get("b64_json"):
        return {"ok": True, "type": "image", "image_url": "data:image/png;base64," + data["b64_json"]}
    return {"ok": False, "error": "No image returned"}

@app.post("/api/public/prostudio/generate")
async def public_prostudio_generate(request: Request):
    payload = await request.json()
    mode = (payload.get("mode") or "text").lower()
    prompt = (payload.get("prompt") or "").strip()
    if not prompt and not payload.get("attachment"):
        return JSONResponse({"ok": False, "error": "Prompt or attachment is required"}, status_code=400)

    result = image_generation(payload) if mode == "image" else text_generation(payload)
    if not result.get("ok"):
        return JSONResponse(result, status_code=502)

    save_generation(int(payload.get("telegram_id") or 0), mode, prompt or "[attachment]")
    return result

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
