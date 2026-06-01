"""DocForge — Files router"""
from fastapi import APIRouter, UploadFile, File
from fastapi.responses import FileResponse
from app.services.file_service import save_upload, resolve_output, cleanup_old_files
from app.services.pdf_service import get_pdf_info
import mimetypes

router = APIRouter()

@router.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    """Upload a file and get back a file_id for use with tool endpoints."""
    meta = await save_upload(file)
    path = resolve_output(meta["file_id"])
    try:
        info = get_pdf_info(path)
        meta["pages"] = info["pages"]
    except Exception:
        pass
    return meta

@router.get("/{file_id}/download")
async def download_file(file_id: str):
    """Download a processed output file."""
    path = resolve_output(file_id)
    mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    return FileResponse(path=str(path), filename=path.name, media_type=mime)

@router.delete("/cleanup")
async def cleanup(max_age_hours: int = 24):
    """Delete files older than max_age_hours."""
    deleted = cleanup_old_files(max_age_hours)
    return {"deleted": deleted}
