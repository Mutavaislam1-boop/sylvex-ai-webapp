import os
import pathlib
import requests
import psycopg2
from fastapi.responses import JSONResponse


from fastapi import FastAPI, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

app = FastAPI()

BASE_DIR = pathlib.Path(__file__).resolve().parent
WEBAPP_DIR = BASE_DIR 

app.mount("/static", StaticFiles(directory=WEBAPP_DIR), name="static")

app.mount("/image", StaticFiles(directory="image"), name="image")

BOT_TOKEN = os.getenv("BOT_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")
print("MINIAPP DATABASE:", DATABASE_URL)
WEBAPP_URL = "https://sylvex-ai-webapp-production.up.railway.app"


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
async def home():
    return FileResponse(WEBAPP_DIR / "index.html")

@app.get("/cabinet")
async def cabinet():
    return FileResponse(WEBAPP_DIR / "cabinet.html")

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

    if BOT_TOKEN and telegram_id and message_id:
        response = requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/editMessageText",
            json={
                "chat_id": telegram_id,
                "message_id": message_id,
                "text": text,
                "parse_mode": "HTML",
                "disable_web_page_preview": False,
                "reply_markup": {
                    "inline_keyboard": [
                        [
                            {
                                "text": "⚙️ Настройки модели",
                                "web_app": {
                                    "url": f"{WEBAPP_URL}?message_id={message_id}&model=kling"
                                }
                            }
                        ]
                    ]
                }
            },
            timeout=10
        )

        print("TELEGRAM STATUS:", response.status_code)
        print("TELEGRAM RESPONSE:", response.text)

    return {
        "success": True,
        "message": "✅ Настройки Kling сохранены"
    }

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