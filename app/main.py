"""
DocForge — FastAPI Application
Cloud-ready: Render.com / Railway / VPS
"""

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse, HTMLResponse
from contextlib import asynccontextmanager
import logging, time, os
from pathlib import Path

from app.core.config import settings
from app.core.logging import setup_logging
from app.routers.pdf_routers import (
    create, convert, edit, organize,
    compress, ocr, security, sign, watermark
)
from app.routers import ai, files, health

setup_logging()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("DocForge starting — env: %s", settings.APP_ENV)
    for d in [settings.UPLOAD_DIR, settings.OUTPUT_DIR, settings.TEMP_DIR]:
        os.makedirs(d, exist_ok=True)
    yield
    logger.info("DocForge shutting down.")


app = FastAPI(
    title="DocForge API",
    description="Self-hosted PDF & Document Processing — 45+ tools",
    version="2.0.0",
    lifespan=lifespan,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(GZipMiddleware, minimum_size=1000)


@app.middleware("http")
async def timing(request: Request, call_next):
    t = time.perf_counter()
    response = await call_next(request)
    response.headers["X-Process-Time"] = f"{(time.perf_counter()-t)*1000:.1f}ms"
    return response


PREFIX = "/api/v1"
app.include_router(health.router,    prefix=PREFIX,               tags=["Health"])
app.include_router(files.router,     prefix=f"{PREFIX}/files",    tags=["Files"])
app.include_router(create,           prefix=f"{PREFIX}/create",   tags=["Create"])
app.include_router(convert,          prefix=f"{PREFIX}/convert",  tags=["Convert"])
app.include_router(edit,             prefix=f"{PREFIX}/edit",     tags=["Edit"])
app.include_router(organize,         prefix=f"{PREFIX}/organize", tags=["Organize"])
app.include_router(compress,         prefix=f"{PREFIX}/compress", tags=["Compress"])
app.include_router(ocr,              prefix=f"{PREFIX}/ocr",      tags=["OCR"])
app.include_router(security,         prefix=f"{PREFIX}/security", tags=["Security"])
app.include_router(sign,             prefix=f"{PREFIX}/sign",     tags=["Sign"])
app.include_router(watermark,        prefix=f"{PREFIX}/watermark",tags=["Watermark"])
app.include_router(ai.router,        prefix=f"{PREFIX}/ai",       tags=["AI"])


@app.get("/", response_class=HTMLResponse)
async def root():
    return """<!DOCTYPE html>
<html><head><title>DocForge API</title>
<style>body{font-family:system-ui;max-width:600px;margin:60px auto;padding:20px;background:#faf9f7;color:#1a1814}
h1{color:#e8500a}a{color:#e8500a}code{background:#f0ede8;padding:2px 8px;border-radius:4px}</style>
</head><body>
<h1>DocForge PDF API</h1>
<p>Backend is running. 45+ PDF tools available.</p>
<p><a href="/api/docs">Interactive API Documentation</a></p>
<p><a href="/api/v1/health">Health Check</a></p>
</body></html>"""


@app.exception_handler(Exception)
async def global_exc(request: Request, exc: Exception):
    logger.error("Unhandled error %s %s: %s", request.method, request.url, exc, exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
        headers={"Access-Control-Allow-Origin": "*"},
    )
