"""DocForge — Router registry"""
from app.routers import ai, files, health
from app.routers.pdf_routers import (
    create, convert, edit, organize,
    compress, ocr, security, sign, watermark,
)

__all__ = [
    "ai", "files", "health",
    "create", "convert", "edit", "organize",
    "compress", "ocr", "security", "sign", "watermark",
]
