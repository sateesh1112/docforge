"""
DocForge — Routers: Create, Convert, Edit, Organize, Compress, OCR
Each section maps directly to a frontend tool button.
"""

from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import FileResponse
import logging
import time
from pathlib import Path

from app.models.schemas import (
    JobResponse, JobStatus,
    MergeRequest, SplitRequest, CompressRequest,
    RotateRequest, ExtractRequest, DeletePagesRequest,
    WatermarkRequest, ProtectRequest, UnlockRequest,
    OcrRequest, RedactRequest, AddPageNumbersRequest,
    CropRequest, ConvertRequest,
)
from app.services import pdf_service as svc
from app.services.file_service import (
    save_upload, resolve_upload, resolve_output,
    output_download_url,
)

logger = logging.getLogger(__name__)


# ─── helper ──────────────────────────────────────────────────────────────────

def _ok(out_path: Path, start: float, pages: int = None) -> JobResponse:
    stem = out_path.stem
    return JobResponse(
        job_id=stem,
        status=JobStatus.DONE,
        message="Processing complete",
        output_url=f"/api/v1/files/{stem}/download",
        filename=out_path.name,
        size_bytes=out_path.stat().st_size,
        pages=pages,
        duration_ms=round((time.perf_counter() - start) * 1000, 1),
    )


# ═══════════════════════════════════════════════════════════════════════════════
# CREATE
# ═══════════════════════════════════════════════════════════════════════════════

router = APIRouter()   # reused per section — see main.py include_router calls


# ── /create ──────────────────────────────────────────────────────────────────

create = APIRouter()

@create.post("/office-to-pdf", response_model=JobResponse)
async def office_to_pdf(file: UploadFile = File(...)):
    """Convert Word / Excel / PowerPoint / ODT / RTF → PDF."""
    t = time.perf_counter()
    meta = await save_upload(file)
    src  = resolve_upload(meta["file_id"])
    out  = await svc.office_to_pdf(src, f"{meta['file_id']}_out.pdf")
    return _ok(out, t)


@create.post("/images-to-pdf", response_model=JobResponse)
async def images_to_pdf(files: list[UploadFile] = File(...)):
    """Combine one or more images into a single PDF."""
    t     = time.perf_counter()
    paths = []
    for f in files:
        meta = await save_upload(f)
        paths.append(resolve_upload(meta["file_id"]))
    file_id = paths[0].stem
    out = await svc.images_to_pdf(paths, f"{file_id}_combined.pdf")
    return _ok(out, t)


@create.post("/html-to-pdf", response_model=JobResponse)
async def html_to_pdf(file: UploadFile = File(...)):
    """Convert an HTML file to PDF."""
    t    = time.perf_counter()
    meta = await save_upload(file)
    src  = resolve_upload(meta["file_id"])
    out  = await svc.html_to_pdf(src, f"{meta['file_id']}_out.pdf")
    return _ok(out, t)


@create.post("/merge", response_model=JobResponse)
async def merge_pdfs(req: MergeRequest):
    """Merge multiple uploaded PDFs into one."""
    t     = time.perf_counter()
    paths = [resolve_upload(fid) for fid in req.file_ids]
    out   = await svc.merge_pdfs(
        paths, req.output_name,
        add_bookmarks=req.add_bookmarks,
        flatten_annots=req.flatten_annots,
    )
    return _ok(out, t)


# ═══════════════════════════════════════════════════════════════════════════════
# CONVERT
# ═══════════════════════════════════════════════════════════════════════════════

convert = APIRouter()

@convert.post("/pdf-to-office", response_model=JobResponse)
async def pdf_to_office(req: ConvertRequest):
    """Convert PDF → DOCX / XLSX / PPTX."""
    t   = time.perf_counter()
    src = resolve_upload(req.file_id)
    ext = req.target.lstrip(".")
    out = await svc.pdf_to_office(
        src, ext,
        req.output_name or f"{src.stem}_converted.{ext}"
    )
    return _ok(out, t)


@convert.post("/pdf-to-images", response_model=JobResponse)
async def pdf_to_images(req: ConvertRequest):
    """Convert each PDF page to a JPG/PNG image (returns zip URL)."""
    import zipfile, uuid as _uuid
    t       = time.perf_counter()
    src     = resolve_upload(req.file_id)
    fmt     = req.target if req.target in ("jpg", "png") else "jpg"
    tmp_dir = Path(svc.settings.TEMP_DIR) / _uuid.uuid4().hex
    imgs    = await svc.pdf_to_images(src, tmp_dir, fmt=fmt)

    zip_name = f"{src.stem}_images.zip"
    zip_path = Path(svc.settings.OUTPUT_DIR) / zip_name

    def _zip():
        with zipfile.ZipFile(str(zip_path), "w", zipfile.ZIP_DEFLATED) as zf:
            for img in imgs:
                zf.write(img, img.name)
        import shutil
        shutil.rmtree(str(tmp_dir), ignore_errors=True)

    import asyncio
    await asyncio.to_thread(_zip)
    return _ok(zip_path, t, pages=len(imgs))


@convert.post("/pdf-to-pdfa", response_model=JobResponse)
async def pdf_to_pdfa(req: ConvertRequest):
    """Convert PDF to PDF/A archival format."""
    t   = time.perf_counter()
    src = resolve_upload(req.file_id)
    out = await svc.pdf_to_pdfa(src, req.output_name or f"{src.stem}_pdfa.pdf")
    return _ok(out, t)


# ═══════════════════════════════════════════════════════════════════════════════
# EDIT
# ═══════════════════════════════════════════════════════════════════════════════

edit = APIRouter()

@edit.post("/add-text", response_model=JobResponse)
async def add_text(
    file_id: str,
    text: str,
    page: int = 1,
    x: float = 72,
    y: float = 72,
    font_size: int = 12,
):
    t   = time.perf_counter()
    src = resolve_upload(file_id)
    out = await svc.add_text_to_pdf(src, f"{file_id}_edited.pdf", text, page, x, y, font_size)
    return _ok(out, t)


@edit.post("/highlight", response_model=JobResponse)
async def highlight_text(
    file_id: str,
    search_term: str,
    color: str = "yellow",
    pages: str = "all",
):
    COLOR_MAP = {
        "yellow": (1, 1, 0), "green": (0, 1, 0),
        "blue": (0, 0.6, 1), "pink": (1, 0.4, 0.8),
    }
    rgb = COLOR_MAP.get(color, (1, 1, 0))
    t   = time.perf_counter()
    src = resolve_upload(file_id)
    out = await svc.highlight_text_in_pdf(src, f"{file_id}_highlighted.pdf", search_term, rgb, pages)
    return _ok(out, t)


@edit.post("/fill-form", response_model=JobResponse)
async def fill_form(file_id: str, fields: dict):
    t   = time.perf_counter()
    src = resolve_upload(file_id)
    out = await svc.fill_pdf_form(src, f"{file_id}_filled.pdf", fields)
    return _ok(out, t)


# ═══════════════════════════════════════════════════════════════════════════════
# ORGANIZE
# ═══════════════════════════════════════════════════════════════════════════════

organize = APIRouter()

@organize.post("/split", response_model=JobResponse)
async def split_pdf(req: SplitRequest):
    import uuid as _uuid
    t       = time.perf_counter()
    src     = resolve_upload(req.file_id)
    out_dir = Path(svc.settings.OUTPUT_DIR) / _uuid.uuid4().hex
    parts   = await svc.split_pdf(
        src, req.mode.value, out_dir,
        page_ranges=req.page_ranges,
        every_n=req.every_n,
    )

    # Zip the parts
    import zipfile, asyncio
    zip_path = Path(svc.settings.OUTPUT_DIR) / f"{src.stem}_split.zip"
    def _zip():
        with zipfile.ZipFile(str(zip_path), "w", zipfile.ZIP_DEFLATED) as zf:
            for p in parts:
                zf.write(p, p.name)
    await asyncio.to_thread(_zip)
    return _ok(zip_path, t, pages=len(parts))


@organize.post("/reorder", response_model=JobResponse)
async def reorder(file_id: str, new_order: list[int]):
    t   = time.perf_counter()
    src = resolve_upload(file_id)
    out = await svc.reorder_pages(src, f"{file_id}_reordered.pdf", new_order)
    return _ok(out, t)


@organize.post("/delete-pages", response_model=JobResponse)
async def delete_pages(req: DeletePagesRequest):
    t   = time.perf_counter()
    src = resolve_upload(req.file_id)
    out = await svc.delete_pages(src, f"{req.file_id}_deleted.pdf", req.pages)
    return _ok(out, t)


@organize.post("/extract-pages", response_model=JobResponse)
async def extract_pages(req: ExtractRequest):
    t   = time.perf_counter()
    src = resolve_upload(req.file_id)
    out = await svc.extract_pages(src, req.output_name, req.page_ranges)
    return _ok(out, t)


@organize.post("/rotate", response_model=JobResponse)
async def rotate(req: RotateRequest):
    t   = time.perf_counter()
    src = resolve_upload(req.file_id)
    out = await svc.rotate_pages(src, f"{req.file_id}_rotated.pdf", req.angle, req.pages or "all")
    return _ok(out, t)


@organize.post("/add-page-numbers", response_model=JobResponse)
async def add_page_numbers(req: AddPageNumbersRequest):
    t   = time.perf_counter()
    src = resolve_upload(req.file_id)
    out = await svc.add_page_numbers(src, f"{req.file_id}_numbered.pdf",
                                      req.position, req.start_at, req.format, req.font_size)
    return _ok(out, t)


@organize.post("/crop", response_model=JobResponse)
async def crop(req: CropRequest):
    t   = time.perf_counter()
    src = resolve_upload(req.file_id)
    out = await svc.crop_pages(src, f"{req.file_id}_cropped.pdf",
                                req.left, req.top, req.right, req.bottom, req.pages)
    return _ok(out, t)


# ═══════════════════════════════════════════════════════════════════════════════
# COMPRESS
# ═══════════════════════════════════════════════════════════════════════════════

compress = APIRouter()

@compress.post("/compress", response_model=JobResponse)
async def compress_pdf(req: CompressRequest):
    t   = time.perf_counter()
    src = resolve_upload(req.file_id)
    out = await svc.compress_pdf(
        src, f"{req.file_id}_compressed.pdf",
        level=req.level.value,
        remove_metadata=req.remove_metadata,
        subset_fonts=req.subset_fonts,
    )
    original  = src.stat().st_size
    compressed = out.stat().st_size
    reduction  = round((1 - compressed / original) * 100, 1)
    r = _ok(out, t)
    r.message = f"Compressed — {reduction}% size reduction ({original:,} → {compressed:,} bytes)"
    return r


@compress.post("/repair", response_model=JobResponse)
async def repair_pdf(file_id: str):
    t   = time.perf_counter()
    src = resolve_upload(file_id)
    out = await svc.repair_pdf(src, f"{file_id}_repaired.pdf")
    return _ok(out, t)


@compress.post("/optimize", response_model=JobResponse)
async def optimize_pdf(file_id: str):
    t   = time.perf_counter()
    src = resolve_upload(file_id)
    out = await svc.optimize_pdf(src, f"{file_id}_optimized.pdf")
    return _ok(out, t)


@compress.post("/archive-pdfa", response_model=JobResponse)
async def archive_pdfa(file_id: str, conformance: str = "pdfa-2b"):
    t   = time.perf_counter()
    src = resolve_upload(file_id)
    out = await svc.pdf_to_pdfa(src, f"{file_id}_archive.pdf", conformance)
    return _ok(out, t)


# ═══════════════════════════════════════════════════════════════════════════════
# OCR
# ═══════════════════════════════════════════════════════════════════════════════

ocr = APIRouter()

@ocr.post("/ocr", response_model=JobResponse)
async def run_ocr(req: OcrRequest):
    t   = time.perf_counter()
    src = resolve_upload(req.file_id)
    out = await svc.ocr_pdf(
        src, f"{req.file_id}_ocr.pdf",
        language=req.language.value,
        output_mode=req.output_mode,
        deskew=req.deskew,
        enhance=req.enhance,
    )
    return _ok(out, t)


# ═══════════════════════════════════════════════════════════════════════════════
# SECURITY
# ═══════════════════════════════════════════════════════════════════════════════

security = APIRouter()

@security.post("/protect", response_model=JobResponse)
async def protect(req: ProtectRequest):
    t   = time.perf_counter()
    src = resolve_upload(req.file_id)
    out = await svc.protect_pdf(
        src, f"{req.file_id}_protected.pdf",
        open_password=req.open_password,
        owner_password=req.owner_password,
        prevent_print=req.prevent_print,
        prevent_copy=req.prevent_copy,
        prevent_edit=req.prevent_edit,
    )
    return _ok(out, t)


@security.post("/unlock", response_model=JobResponse)
async def unlock(req: UnlockRequest):
    t   = time.perf_counter()
    src = resolve_upload(req.file_id)
    out = await svc.unlock_pdf(src, f"{req.file_id}_unlocked.pdf", req.password)
    return _ok(out, t)


@security.post("/redact", response_model=JobResponse)
async def redact(req: RedactRequest):
    t   = time.perf_counter()
    src = resolve_upload(req.file_id)
    out = await svc.redact_pdf(src, f"{req.file_id}_redacted.pdf", req.patterns, req.pages)
    return _ok(out, t)


# ═══════════════════════════════════════════════════════════════════════════════
# SIGN
# ═══════════════════════════════════════════════════════════════════════════════

sign = APIRouter()

@sign.post("/sign-text", response_model=JobResponse)
async def sign_text(
    file_id: str,
    signature_text: str,
    page: int = 1,
    x: float = 72, y: float = 600,
    width: float = 200, height: float = 60,
    add_timestamp: bool = True,
):
    t   = time.perf_counter()
    src = resolve_upload(file_id)
    out = await svc.sign_pdf_text(
        src, f"{file_id}_signed.pdf",
        signature_text, page, x, y, width, height, add_timestamp
    )
    return _ok(out, t)


# ═══════════════════════════════════════════════════════════════════════════════
# WATERMARK
# ═══════════════════════════════════════════════════════════════════════════════

watermark = APIRouter()

@watermark.post("/add", response_model=JobResponse)
async def add_watermark(req: WatermarkRequest):
    t   = time.perf_counter()
    src = resolve_upload(req.file_id)
    out = await svc.add_watermark(
        src, f"{req.file_id}_watermarked.pdf",
        text=req.text or "CONFIDENTIAL",
        opacity=req.opacity,
        position=req.position.value,
        font_size=req.font_size,
        color=req.color,
        pages=req.pages,
    )
    return _ok(out, t)
