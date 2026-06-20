import os
import requests

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from database.db import save_kling_settings

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
    print("SETTINGS RECEIVED:", data)
    
    telegram_id = data.get("telegram_id")
    message_id = data.get("message_id")
with open("settings.txt", "w") as f:
    f.write(str(data))
    

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

        save_kling_settings(
            telegram_id=int(data["telegram_id"]),
            model=data["model"],
            mode=data["mode"],
            ratio=data["ratio"],
            quality=data["quality"],
            duration=int(
                str(data["duration"]).replace(" секунд", "")
            ),
            sound=1 if data["sound"] else 0,
            prompt_enhance=1 if data["prompt_enhance"] else 0
        )
        print("SETTINGS SAVED TO DB") 
        print("SETTINGS:", data)

        return {
            "success": True,
            "message": "✅ Настройки Kling сохранены"
        }