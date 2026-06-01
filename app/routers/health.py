"""DocForge — Health check router"""
from fastapi import APIRouter
from app.core.config import settings
from app.models.schemas import HealthResponse
import shutil

router = APIRouter()

@router.get("/health", response_model=HealthResponse)
async def health():
    return HealthResponse(
        status="ok",
        version="2.0.0",
        libreoffice=bool(shutil.which(settings.LIBREOFFICE_PATH) or shutil.which("soffice")),
        ghostscript=bool(shutil.which(settings.GHOSTSCRIPT_PATH) or shutil.which("gs")),
        tesseract=bool(shutil.which(settings.TESSERACT_PATH) or shutil.which("tesseract")),
        poppler=bool(shutil.which("pdftoppm")),
        openai=bool(settings.OPENAI_API_KEY),
    )
