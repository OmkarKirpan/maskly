"""Localhost server. Run: uv run uvicorn app:app --port 8000"""
import io
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image

import maskly

app = FastAPI()
STATIC = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=STATIC), name="static")
Image.MAX_IMAGE_PIXELS = 3840 * 2160 * 2  # FR-2: up to 4K, refuse giant images


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


@app.post("/detect")
async def detect(request: Request, gemma: bool = True):
    # Raw image body, read into memory only: no multipart temp files on disk.
    try:
        img = Image.open(io.BytesIO(await request.body())).convert("RGB")
    except Exception:
        raise HTTPException(400, "Send a PNG or JPG image as the request body")
    return await run_in_threadpool(maskly.detect, img, gemma)
