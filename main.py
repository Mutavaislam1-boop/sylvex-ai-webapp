from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

app = FastAPI()

app.mount("/assets", StaticFiles(directory="image"), name="image")

@app.get("/")
async def home():
    return FileResponse("index.html")