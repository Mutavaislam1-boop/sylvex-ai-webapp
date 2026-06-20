import os
import requests

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

app = FastAPI()

app.mount("/image", StaticFiles(directory="image"), name="image")

BOT_TOKEN = os.getenv("BOT_TOKEN")


@app.get("/")
async def home():
    return FileResponse("index.html")


@app.post("/save-settings")
async def save_settings(request: Request):
    data = await request.json()

    telegram_id = data.get("telegram_id")

    text = (
        "✅ НАСТРОЙКИ KLING СОХРАНЕНЫ\n\n"
        f"Модель: {data.get('model')}\n"
        f"Режим: {data.get('mode')}\n"
        f"Формат: {data.get('ratio')}\n"
        f"Качество: {data.get('quality')}\n"
        f"Длительность: {data.get('duration')}\n"
        f"Звук: {'Вкл' if data.get('sound') else 'Выкл'}\n"
        f"Prompt Enhance: {'Вкл' if data.get('prompt_enhance') else 'Выкл'}\n\n"
        "Теперь отправьте описание видео."
    )

    if BOT_TOKEN and telegram_id:
        requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            json={
                "chat_id": telegram_id,
                "text": text
            },
            timeout=10
        )

    print("SETTINGS:", data)

    return {
        "success": True,
        "message": "✅ Настройки Kling сохранены"
    }