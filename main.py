from fastapi import FastAPI, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

app = FastAPI()

app.mount("/image", StaticFiles(directory="image"), name="image")


@app.get("/")
async def home():
    return FileResponse("index.html")


@app.post("/save-settings")
async def save_settings(request: Request):
    data = await request.json()

    print("SETTINGS:", data)

    return {
        "success": True,
        "message": "Settings saved"
    }