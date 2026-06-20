import os
import requests

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

app = FastAPI()

app.mount("/image", StaticFiles(directory="image"), name="image")

BOT_TOKEN = os.getenv("BOT_TOKEN")
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


@app.get("/")
async def home():
    return FileResponse("index.html")


@app.post("/save-settings")
async def save_settings(request: Request):
    data = await request.json()

    telegram_id = data.get("telegram_id")

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

    text = design(
        "✅ НАСТРОЙКИ KLING СОХРАНЕНЫ",
        body
    )

    if BOT_TOKEN and telegram_id:
        requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            json={
                "chat_id": telegram_id,
                "text": "⌨️ Меню обновлено",
                "reply_markup": {
                    "keyboard": [
                        [
                            {"text": "👤 Мой кабинет"},
                            {"text": "🛒 Магазин"}
                        ],
                        [
                            {"text": "🆘 Помощь"},
                            {"text": "🏠 Главное меню"}
                        ]
                    ],
                    "resize_keyboard": True
                }
            },
            timeout=10
        )

        print("TELEGRAM STATUS:", response.status_code)
        print("TELEGRAM RESPONSE:", response.text)

    print("SETTINGS:", data)

    return {
        "success": True,
        "message": "✅ Настройки Kling сохранены"
    }