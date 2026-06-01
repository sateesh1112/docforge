"""
DocForge — File Management Service
Handles upload validation, storage, cleanup and download URL generation.
"""

import hashlib
import logging
import mimetypes
import os
import time
import uuid
from pathlib import Path
from typing import Optional

from fastapi import HTTPException, UploadFile

from app.core.config import settings

logger = logging.getLogger(__name__)

ALLOWED_MIME_TYPES = {
    "application/pdf",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.ms-powerpoint",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "image/jpeg",
    "image/png",
    "image/tiff",
    "image/webp",
    "image/bmp",
    "text/html",
    "text/plain",
    "application/rtf",
    "text/csv",
}

ALLOWED_EXTENSIONS = {
    ".pdf", ".doc", ".docx", ".xls", ".xlsx",
    ".ppt", ".pptx", ".jpg", ".jpeg", ".png",
    ".tif", ".tiff", ".bmp", ".webp",
    ".html", ".htm", ".txt", ".rtf", ".csv", ".odt", ".ods", ".odp",
}

MAX_BYTES = settings.MAX_FILE_SIZE_MB * 1024 * 1024


async def save_upload(file: UploadFile) -> dict:
    """Validate, save and return file metadata."""
    ext = Path(file.filename or "").suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(400, f"File type '{ext}' not supported.")

    content = await file.read()
    if len(content) > MAX_BYTES:
        raise HTTPException(413, f"File exceeds {settings.MAX_FILE_SIZE_MB} MB limit.")

    file_id  = uuid.uuid4().hex
    filename = f"{file_id}{ext}"
    dest     = Path(settings.UPLOAD_DIR) / filename
    dest.write_bytes(content)

    logger.info("Saved upload: %s (%d bytes)", filename, len(content))
    return {
        "file_id":    file_id,
        "filename":   file.filename,
        "size_bytes": len(content),
        "mime_type":  file.content_type or mimetypes.guess_type(file.filename or "")[0] or "application/octet-stream",
        "stored_as":  filename,
        "upload_url": f"/api/v1/files/{file_id}/download",
    }


def resolve_upload(file_id: str) -> Path:
    """Find the uploaded file by its ID."""
    for p in Path(settings.UPLOAD_DIR).glob(f"{file_id}*"):
        if p.is_file():
            return p
    raise HTTPException(404, f"File '{file_id}' not found.")


def resolve_output(file_id: str) -> Path:
    """Find a processed output file by its ID (stem of filename)."""
    for directory in [settings.OUTPUT_DIR, settings.UPLOAD_DIR]:
        for p in Path(directory).glob(f"{file_id}*"):
            if p.is_file():
                return p
    raise HTTPException(404, f"Output file '{file_id}' not found.")


def output_download_url(filename: str) -> str:
    stem = Path(filename).stem
    return f"/api/v1/files/{stem}/download"


def cleanup_old_files(max_age_hours: Optional[int] = None) -> int:
    """Delete files older than max_age_hours. Returns count deleted."""
    max_age = max_age_hours or settings.FILE_RETENTION_HOURS
    cutoff  = time.time() - (max_age * 3600)
    deleted = 0
    for directory in [settings.UPLOAD_DIR, settings.OUTPUT_DIR, settings.TEMP_DIR]:
        for p in Path(directory).iterdir():
            if p.is_file() and p.stat().st_mtime < cutoff:
                try:
                    p.unlink()
                    deleted += 1
                except OSError:
                    pass
    logger.info("Cleanup: deleted %d stale files", deleted)
    return deleted


def file_checksum(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()
