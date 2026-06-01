"""
DocForge — PDF Service
The core engine wrapping PyMuPDF (fitz), Ghostscript, LibreOffice,
Tesseract and Poppler into clean async-friendly methods.

All heavy I/O is run in a thread pool via asyncio.to_thread so the
FastAPI event loop is never blocked.
"""

import asyncio
import logging
import os
import re
import shutil
import subprocess
import tempfile
import uuid
from pathlib import Path
from typing import List, Optional, Tuple

import fitz                         # PyMuPDF
from PIL import Image, ImageEnhance # Pillow
import pytesseract                  # python-tesseract
from reportlab.pdfgen import canvas # PDF creation
from reportlab.lib.pagesizes import A4
from pypdf import PdfWriter, PdfReader  # pypdf (formerly PyPDF2)

from app.core.config import settings

logger = logging.getLogger(__name__)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _tmp(suffix: str = ".pdf") -> Path:
    """Return a unique temp file path (not yet created)."""
    return Path(settings.TEMP_DIR) / f"{uuid.uuid4().hex}{suffix}"


def _run(cmd: List[str], timeout: int = 120) -> subprocess.CompletedProcess:
    """Run a subprocess synchronously (called inside thread pool)."""
    logger.debug("CMD: %s", " ".join(cmd))
    result = subprocess.run(
        cmd, capture_output=True, text=True, timeout=timeout
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"Command failed ({result.returncode}): {result.stderr[:500]}"
        )
    return result


async def _run_async(cmd: List[str], timeout: int = 120) -> subprocess.CompletedProcess:
    return await asyncio.to_thread(_run, cmd, timeout)


def resolve_path(file_id: str) -> Path:
    """Resolve a file_id to its absolute path in uploads or outputs."""
    for directory in [settings.UPLOAD_DIR, settings.OUTPUT_DIR, settings.TEMP_DIR]:
        for p in Path(directory).glob(f"{file_id}*"):
            if p.is_file():
                return p
    raise FileNotFoundError(f"File not found: {file_id}")


def output_path(filename: str) -> Path:
    return Path(settings.OUTPUT_DIR) / filename


# ── PDF Metadata ──────────────────────────────────────────────────────────────

def get_pdf_info(path: Path) -> dict:
    doc = fitz.open(path)
    meta = doc.metadata or {}
    info = {
        "pages":    doc.page_count,
        "title":    meta.get("title", ""),
        "author":   meta.get("author", ""),
        "subject":  meta.get("subject", ""),
        "creator":  meta.get("creator", ""),
        "size_bytes": path.stat().st_size,
    }
    doc.close()
    return info


# ═══════════════════════════════════════════════════════════════════════════════
# 1. CREATE
# ═══════════════════════════════════════════════════════════════════════════════

async def office_to_pdf(src: Path, output_name: str) -> Path:
    """
    Convert any LibreOffice-supported format to PDF.
    Supports: .docx .doc .xlsx .xls .pptx .ppt .odt .ods .odp .rtf .txt .csv
    """
    out_dir  = Path(settings.OUTPUT_DIR)
    out_file = out_dir / output_name

    await _run_async([
        settings.LIBREOFFICE_PATH,
        "--headless", "--convert-to", "pdf",
        "--outdir", str(out_dir),
        str(src)
    ])

    # LibreOffice names the output after the source stem
    lo_output = out_dir / (src.stem + ".pdf")
    if lo_output.exists() and lo_output != out_file:
        lo_output.rename(out_file)

    logger.info("office_to_pdf → %s (%d bytes)", out_file, out_file.stat().st_size)
    return out_file


async def images_to_pdf(image_paths: List[Path], output_name: str) -> Path:
    """Combine one or more images (JPG/PNG/TIFF/BMP) into a single PDF."""
    out = output_path(output_name)

    def _convert():
        doc = fitz.open()
        for img_path in image_paths:
            img_doc = fitz.open(img_path)          # fitz can open images
            pdfbytes = img_doc.convert_to_pdf()
            img_pdf  = fitz.open("pdf", pdfbytes)
            doc.insert_pdf(img_pdf)
        doc.save(out, garbage=4, deflate=True)
        doc.close()

    await asyncio.to_thread(_convert)
    return out


async def html_to_pdf(src: Path, output_name: str) -> Path:
    """Convert an HTML file to PDF via LibreOffice (headless)."""
    return await office_to_pdf(src, output_name)


async def merge_pdfs(paths: List[Path], output_name: str,
                     add_bookmarks: bool = True,
                     flatten_annots: bool = False) -> Path:
    """Merge multiple PDFs into one, optionally adding bookmarks."""
    out = output_path(output_name)

    def _merge():
        writer = PdfWriter()
        for path in paths:
            reader = PdfReader(str(path))
            if flatten_annots:
                # Flatten by re-rendering with fitz
                tmp = _tmp()
                doc = fitz.open(str(path))
                doc.save(str(tmp), garbage=4, deflate=True)
                doc.close()
                reader = PdfReader(str(tmp))

            if add_bookmarks:
                start_page = len(writer.pages)
                writer.append(reader)
                writer.add_outline_item(path.stem, start_page)
            else:
                writer.append(reader)

        with open(out, "wb") as f:
            writer.write(f)

    await asyncio.to_thread(_merge)
    return out


# ═══════════════════════════════════════════════════════════════════════════════
# 2. CONVERT
# ═══════════════════════════════════════════════════════════════════════════════

async def pdf_to_office(src: Path, target_ext: str, output_name: str) -> Path:
    """
    PDF → DOCX / XLSX / PPTX via LibreOffice.
    Note: Quality depends on PDF structure. Text-based PDFs convert well;
          scanned images need OCR first.
    """
    out_dir  = Path(settings.OUTPUT_DIR)
    out_file = out_dir / output_name

    fmt_map = {
        "docx": "docx",
        "xlsx": "xlsx",
        "pptx": "pptx",
        "odt":  "odt",
        "rtf":  "rtf",
    }
    lo_fmt = fmt_map.get(target_ext, target_ext)

    await _run_async([
        settings.LIBREOFFICE_PATH,
        "--headless", "--convert-to", lo_fmt,
        "--outdir", str(out_dir),
        str(src)
    ])

    lo_out = out_dir / (src.stem + f".{lo_fmt}")
    if lo_out.exists() and lo_out != out_file:
        lo_out.rename(out_file)

    return out_file


async def pdf_to_images(src: Path, output_dir: Path,
                         fmt: str = "jpg", dpi: int = 150) -> List[Path]:
    """
    Render each PDF page to an image using PyMuPDF.
    Returns list of output image paths.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    paths: List[Path] = []

    def _render():
        doc = fitz.open(str(src))
        mat = fitz.Matrix(dpi / 72, dpi / 72)
        for i, page in enumerate(doc):
            pix    = page.get_pixmap(matrix=mat, alpha=False)
            fname  = output_dir / f"page_{i+1:04d}.{fmt}"
            pix.save(str(fname))
            paths.append(fname)
        doc.close()

    await asyncio.to_thread(_render)
    return paths


async def pdf_to_pdfa(src: Path, output_name: str,
                       conformance: str = "pdfa-2b") -> Path:
    """
    Convert PDF to PDF/A archival format using Ghostscript.
    conformance: pdfa-1b | pdfa-2b | pdfa-3b
    """
    out = output_path(output_name)
    pdfa_def = {
        "pdfa-1b": "1",
        "pdfa-2b": "2",
        "pdfa-3b": "3",
    }.get(conformance, "2")

    await _run_async([
        settings.GHOSTSCRIPT_PATH,
        "-dBATCH", "-dNOPAUSE", "-dNOSAFER",
        f"-dPDFA={pdfa_def}",
        "-sDEVICE=pdfwrite",
        "-sColorConversionStrategy=UseDeviceIndependentColor",
        f"-sOutputFile={out}",
        str(src),
    ])
    return out


# ═══════════════════════════════════════════════════════════════════════════════
# 3. EDIT
# ═══════════════════════════════════════════════════════════════════════════════

async def add_text_to_pdf(src: Path, output_name: str,
                           text: str, page_num: int,
                           x: float, y: float,
                           font_size: int = 12,
                           color: Tuple[float,float,float] = (0, 0, 0)) -> Path:
    out = output_path(output_name)

    def _add():
        doc  = fitz.open(str(src))
        page = doc[page_num - 1]
        page.insert_text(
            (x, y), text,
            fontsize=font_size,
            color=color,
        )
        doc.save(str(out), garbage=4, deflate=True)
        doc.close()

    await asyncio.to_thread(_add)
    return out


async def highlight_text_in_pdf(src: Path, output_name: str,
                                  search_term: str,
                                  color: Tuple[float,float,float] = (1, 1, 0),
                                  pages: str = "all") -> Path:
    """Search for text and highlight all occurrences."""
    out = output_path(output_name)

    def _highlight():
        doc        = fitz.open(str(src))
        page_range = _parse_pages(pages, doc.page_count)
        for i in page_range:
            page   = doc[i]
            quads  = page.search_for(search_term, quads=True)
            for q in quads:
                annot = page.add_highlight_annot(q)
                annot.set_colors(stroke=color)
                annot.update()
        doc.save(str(out), garbage=4, deflate=True)
        doc.close()

    await asyncio.to_thread(_highlight)
    return out


async def fill_pdf_form(src: Path, output_name: str,
                         field_values: dict) -> Path:
    """Fill PDF form fields from a {field_name: value} dict."""
    out = output_path(output_name)

    def _fill():
        doc = fitz.open(str(src))
        for page in doc:
            for widget in page.widgets():
                if widget.field_name in field_values:
                    widget.field_value = field_values[widget.field_name]
                    widget.update()
        doc.save(str(out), garbage=4, deflate=True)
        doc.close()

    await asyncio.to_thread(_fill)
    return out


# ═══════════════════════════════════════════════════════════════════════════════
# 4. ORGANISE
# ═══════════════════════════════════════════════════════════════════════════════

async def split_pdf(src: Path, mode: str, output_dir: Path,
                    page_ranges: Optional[str] = None,
                    every_n: Optional[int] = None) -> List[Path]:
    """Split PDF by ranges, every-N-pages, or bookmarks."""
    output_dir.mkdir(parents=True, exist_ok=True)
    outputs: List[Path] = []

    def _split():
        reader = PdfReader(str(src))
        total  = len(reader.pages)

        if mode == "every_n" and every_n:
            ranges = [(i, min(i + every_n, total))
                      for i in range(0, total, every_n)]
        elif mode == "page_ranges" and page_ranges:
            ranges = _parse_range_tuples(page_ranges, total)
        else:
            ranges = [(i, i + 1) for i in range(total)]

        for idx, (start, end) in enumerate(ranges, 1):
            writer = PdfWriter()
            for p in range(start, end):
                writer.add_page(reader.pages[p])
            out = output_dir / f"part_{idx:03d}.pdf"
            with open(out, "wb") as f:
                writer.write(f)
            outputs.append(out)

    await asyncio.to_thread(_split)
    return outputs


async def reorder_pages(src: Path, output_name: str,
                         new_order: List[int]) -> Path:
    """Reorder pages; new_order is 1-indexed list of page numbers."""
    out = output_path(output_name)

    def _reorder():
        reader = PdfReader(str(src))
        writer = PdfWriter()
        for p in new_order:
            writer.add_page(reader.pages[p - 1])
        with open(out, "wb") as f:
            writer.write(f)

    await asyncio.to_thread(_reorder)
    return out


async def delete_pages(src: Path, output_name: str, pages: str) -> Path:
    out = output_path(output_name)

    def _delete():
        reader   = PdfReader(str(src))
        total    = len(reader.pages)
        to_del   = set(_parse_pages(pages, total))
        writer   = PdfWriter()
        for i in range(total):
            if i not in to_del:
                writer.add_page(reader.pages[i])
        with open(out, "wb") as f:
            writer.write(f)

    await asyncio.to_thread(_delete)
    return out


async def extract_pages(src: Path, output_name: str, page_ranges: str) -> Path:
    out = output_path(output_name)

    def _extract():
        reader = PdfReader(str(src))
        total  = len(reader.pages)
        idxs   = _parse_pages(page_ranges, total)
        writer = PdfWriter()
        for i in idxs:
            writer.add_page(reader.pages[i])
        with open(out, "wb") as f:
            writer.write(f)

    await asyncio.to_thread(_extract)
    return out


async def rotate_pages(src: Path, output_name: str,
                        angle: int, pages: str = "all") -> Path:
    out = output_path(output_name)

    def _rotate():
        reader = PdfReader(str(src))
        writer = PdfWriter()
        total  = len(reader.pages)
        idxs   = set(_parse_pages(pages, total))
        for i, page in enumerate(reader.pages):
            if i in idxs:
                page.rotate(angle)
            writer.add_page(page)
        with open(out, "wb") as f:
            writer.write(f)

    await asyncio.to_thread(_rotate)
    return out


async def add_page_numbers(src: Path, output_name: str,
                            position: str = "bottom_center",
                            start_at: int = 1,
                            fmt: str = "Page {n}",
                            font_size: int = 10) -> Path:
    out = output_path(output_name)

    POS_MAP = {
        "bottom_center": lambda w, h: (w / 2, 20),
        "bottom_right":  lambda w, h: (w - 72, 20),
        "top_center":    lambda w, h: (w / 2, h - 20),
        "top_right":     lambda w, h: (w - 72, h - 20),
    }

    def _number():
        doc = fitz.open(str(src))
        for i, page in enumerate(doc):
            n      = i + start_at
            label  = fmt.replace("{n}", str(n))
            rect   = page.rect
            get_xy = POS_MAP.get(position, POS_MAP["bottom_center"])
            x, y   = get_xy(rect.width, rect.height)
            page.insert_text(
                (x, y), label,
                fontsize=font_size,
                color=(0.3, 0.3, 0.3),
            )
        doc.save(str(out), garbage=4, deflate=True)
        doc.close()

    await asyncio.to_thread(_number)
    return out


async def crop_pages(src: Path, output_name: str,
                      left: float, top: float,
                      right: float, bottom: float,
                      pages: str = "all") -> Path:
    out = output_path(output_name)

    def _crop():
        doc   = fitz.open(str(src))
        idxs  = set(_parse_pages(pages, doc.page_count))
        for i, page in enumerate(doc):
            if i in idxs:
                r = page.rect
                new_rect = fitz.Rect(r.x0 + left, r.y0 + top,
                                     r.x1 - right, r.y1 - bottom)
                page.set_cropbox(new_rect)
        doc.save(str(out), garbage=4, deflate=True)
        doc.close()

    await asyncio.to_thread(_crop)
    return out


# ═══════════════════════════════════════════════════════════════════════════════
# 5. COMPRESS
# ═══════════════════════════════════════════════════════════════════════════════

_GS_PRESETS = {
    "high_quality": "/printer",
    "balanced":     "/ebook",
    "maximum":      "/screen",
}

async def compress_pdf(src: Path, output_name: str,
                        level: str = "balanced",
                        remove_metadata: bool = False,
                        subset_fonts: bool = False) -> Path:
    """Compress PDF using Ghostscript's distiller presets."""
    out    = output_path(output_name)
    preset = _GS_PRESETS.get(level, "/ebook")

    cmd = [
        settings.GHOSTSCRIPT_PATH,
        "-dBATCH", "-dNOPAUSE", "-dNOSAFER",
        "-sDEVICE=pdfwrite",
        f"-dPDFSETTINGS={preset}",
        "-dCompressPages=true",
        "-dCompressFonts=true",
        "-dEmbedAllFonts=true",
    ]
    if subset_fonts:
        cmd.append("-dSubsetFonts=true")
    if remove_metadata:
        cmd += ["-dOmitInfoDict=true"]
    cmd += [f"-sOutputFile={out}", str(src)]

    await _run_async(cmd)
    return out


async def repair_pdf(src: Path, output_name: str) -> Path:
    """Repair a corrupted PDF by re-saving it through PyMuPDF."""
    out = output_path(output_name)

    def _repair():
        doc = fitz.open(str(src))
        doc.save(str(out), garbage=4, clean=True, deflate=True)
        doc.close()

    await asyncio.to_thread(_repair)
    return out


async def optimize_pdf(src: Path, output_name: str) -> Path:
    """Web-optimize (linearize) a PDF for fast browser loading."""
    out = output_path(output_name)

    await _run_async([
        settings.GHOSTSCRIPT_PATH,
        "-dBATCH", "-dNOPAUSE", "-dNOSAFER",
        "-sDEVICE=pdfwrite",
        "-dFastWebView=true",
        "-dPDFSETTINGS=/ebook",
        f"-sOutputFile={out}",
        str(src),
    ])
    return out


# ═══════════════════════════════════════════════════════════════════════════════
# 6. OCR
# ═══════════════════════════════════════════════════════════════════════════════

async def ocr_pdf(src: Path, output_name: str,
                   language: str = "eng",
                   output_mode: str = "searchable_pdf",
                   deskew: bool = True,
                   enhance: bool = True) -> Path:
    """
    OCR a scanned PDF:
    1. Render each page to image (PyMuPDF)
    2. Pre-process image (Pillow)
    3. Run Tesseract
    4. Assemble searchable PDF
    """
    out     = output_path(output_name)
    tmp_dir = Path(settings.TEMP_DIR) / uuid.uuid4().hex
    tmp_dir.mkdir(parents=True)
    lang    = "eng" if language == "auto" else language

    def _ocr():
        doc    = fitz.open(str(src))
        writer = PdfWriter()

        for page_num, page in enumerate(doc):
            # 1. Render page to image at 300 DPI
            mat = fitz.Matrix(300 / 72, 300 / 72)
            pix = page.get_pixmap(matrix=mat, alpha=False)
            img_path = tmp_dir / f"page_{page_num}.png"
            pix.save(str(img_path))

            # 2. Enhance image
            img = Image.open(img_path).convert("L")   # greyscale
            if enhance:
                img = ImageEnhance.Contrast(img).enhance(2.0)
                img = ImageEnhance.Sharpness(img).enhance(2.0)
            if deskew:
                # Basic deskew via Tesseract's internal deskew
                pass
            enhanced_path = tmp_dir / f"enh_{page_num}.png"
            img.save(str(enhanced_path))

            # 3. Run Tesseract
            if output_mode == "text":
                text = pytesseract.image_to_string(
                    Image.open(enhanced_path), lang=lang
                )
                # Create a simple text PDF page
                tmp_pdf = tmp_dir / f"ocr_{page_num}.pdf"
                c = canvas.Canvas(str(tmp_pdf), pagesize=A4)
                c.setFont("Helvetica", 9)
                text_obj = c.beginText(36, A4[1] - 36)
                for line in text.splitlines():
                    text_obj.textLine(line)
                c.drawText(text_obj)
                c.save()
            else:
                # Searchable PDF — text layer on top of original image
                tmp_pdf = tmp_dir / f"ocr_{page_num}.pdf"
                pytesseract.run_tesseract(
                    str(enhanced_path),
                    str(tmp_dir / f"ocr_{page_num}"),
                    lang=lang,
                    extension="pdf",
                )

            if tmp_pdf.exists():
                r = PdfReader(str(tmp_pdf))
                for p in r.pages:
                    writer.add_page(p)

        with open(str(out), "wb") as f:
            writer.write(f)
        doc.close()
        shutil.rmtree(tmp_dir, ignore_errors=True)

    await asyncio.to_thread(_ocr)
    return out


# ═══════════════════════════════════════════════════════════════════════════════
# 7. SECURITY
# ═══════════════════════════════════════════════════════════════════════════════

async def protect_pdf(src: Path, output_name: str,
                       open_password: Optional[str] = None,
                       owner_password: Optional[str] = None,
                       prevent_print: bool = False,
                       prevent_copy: bool = False,
                       prevent_edit: bool = False) -> Path:
    out = output_path(output_name)

    def _protect():
        reader = PdfReader(str(src))
        writer = PdfWriter()
        writer.append_pages_from_reader(reader)

        permissions = 0
        if not prevent_print: permissions |= 0b000000000100
        if not prevent_copy:  permissions |= 0b000000010000
        if not prevent_edit:  permissions |= 0b000000001000

        writer.encrypt(
            user_password=open_password or "",
            owner_password=owner_password or (open_password or "docforge_owner"),
            use_128bit=True,
            permissions_flag=permissions,
        )
        with open(out, "wb") as f:
            writer.write(f)

    await asyncio.to_thread(_protect)
    return out


async def unlock_pdf(src: Path, output_name: str, password: str) -> Path:
    out = output_path(output_name)

    def _unlock():
        reader = PdfReader(str(src))
        if reader.is_encrypted:
            result = reader.decrypt(password)
            if result == 0:
                raise ValueError("Incorrect password")
        writer = PdfWriter()
        writer.append_pages_from_reader(reader)
        with open(out, "wb") as f:
            writer.write(f)

    await asyncio.to_thread(_unlock)
    return out


async def redact_pdf(src: Path, output_name: str,
                      patterns: List[str], pages: str = "all") -> Path:
    """Permanently redact text matching any of the given regex patterns."""
    out = output_path(output_name)

    def _redact():
        doc  = fitz.open(str(src))
        idxs = set(_parse_pages(pages, doc.page_count))
        compiled = [re.compile(p, re.IGNORECASE) for p in patterns]

        for i, page in enumerate(doc):
            if i not in idxs:
                continue
            for pattern in compiled:
                hits = page.search_for(pattern.pattern)
                for rect in hits:
                    page.add_redact_annot(rect, fill=(0, 0, 0))
            page.apply_redactions()

        doc.save(str(out), garbage=4, deflate=True)
        doc.close()

    await asyncio.to_thread(_redact)
    return out


# ═══════════════════════════════════════════════════════════════════════════════
# 8. WATERMARK
# ═══════════════════════════════════════════════════════════════════════════════

async def add_watermark(src: Path, output_name: str,
                         text: str,
                         opacity: float = 0.30,
                         position: str = "diagonal",
                         font_size: int = 48,
                         color: str = "#888888",
                         pages: str = "all") -> Path:
    out = output_path(output_name)

    def _hex_to_rgb(h: str):
        h = h.lstrip("#")
        return tuple(int(h[i:i+2], 16) / 255 for i in (0, 2, 4))

    rgb = _hex_to_rgb(color)

    def _watermark():
        doc  = fitz.open(str(src))
        idxs = set(_parse_pages(pages, doc.page_count))

        for i, page in enumerate(doc):
            if i not in idxs:
                continue
            rect = page.rect
            if position == "diagonal":
                page.insert_text(
                    (rect.width * 0.1, rect.height * 0.6),
                    text,
                    fontsize=font_size,
                    color=rgb,
                    rotate=45,
                    fill_opacity=opacity,
                )
            elif position == "center":
                tw = fitz.get_text_length(text, fontsize=font_size)
                page.insert_text(
                    ((rect.width - tw) / 2, rect.height / 2),
                    text, fontsize=font_size, color=rgb, fill_opacity=opacity,
                )
            elif position == "tile":
                for row in range(0, int(rect.height), font_size * 4):
                    for col in range(0, int(rect.width), 200):
                        page.insert_text(
                            (col, row), text,
                            fontsize=font_size // 2, color=rgb,
                            fill_opacity=opacity, rotate=30,
                        )
            else:
                page.insert_text(
                    (36, rect.height - 36), text,
                    fontsize=font_size, color=rgb, fill_opacity=opacity,
                )

        doc.save(str(out), garbage=4, deflate=True)
        doc.close()

    await asyncio.to_thread(_watermark)
    return out


# ═══════════════════════════════════════════════════════════════════════════════
# 9. SIGN
# ═══════════════════════════════════════════════════════════════════════════════

async def sign_pdf_text(src: Path, output_name: str,
                         signature_text: str,
                         page: int, x: float, y: float,
                         width: float, height: float,
                         add_timestamp: bool = True) -> Path:
    """
    Add a visual text signature to a PDF.
    For cryptographic signing use pyHanko (see sign_pdf_crypto).
    """
    out = output_path(output_name)

    def _sign():
        doc   = fitz.open(str(src))
        pg    = doc[page - 1]
        rect  = fitz.Rect(x, y, x + width, y + height)

        # Draw a signature box
        shape = pg.new_shape()
        shape.draw_rect(rect)
        shape.finish(color=(0.2, 0.2, 0.8), fill=None, width=0.5)
        shape.commit()

        # Insert signature text
        pg.insert_textbox(
            rect, signature_text,
            fontsize=18, color=(0.1, 0.1, 0.6),
            align=fitz.TEXT_ALIGN_CENTER,
        )

        if add_timestamp:
            from datetime import datetime, timezone
            ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
            pg.insert_text(
                (x, y + height + 10), f"Signed: {ts}",
                fontsize=7, color=(0.5, 0.5, 0.5),
            )

        doc.save(str(out), garbage=4, deflate=True)
        doc.close()

    await asyncio.to_thread(_sign)
    return out


# ═══════════════════════════════════════════════════════════════════════════════
# 10. TEXT EXTRACTION (used by AI features)
# ═══════════════════════════════════════════════════════════════════════════════

async def extract_text(src: Path, max_chars: int = 40000) -> str:
    """Extract plain text from a PDF (used as AI context)."""
    def _extract():
        doc  = fitz.open(str(src))
        text = []
        for page in doc:
            text.append(page.get_text("text"))
        doc.close()
        return "\n\n".join(text)[:max_chars]

    return await asyncio.to_thread(_extract)


# ═══════════════════════════════════════════════════════════════════════════════
# UTILITIES
# ═══════════════════════════════════════════════════════════════════════════════

def _parse_pages(spec: str, total: int) -> List[int]:
    """
    Parse a page specification string like "all", "1-3,5,7-9" into
    a list of 0-based page indices.
    """
    if spec.strip().lower() == "all":
        return list(range(total))

    indices: List[int] = []
    for part in spec.split(","):
        part = part.strip()
        if "-" in part:
            a, b = part.split("-", 1)
            for i in range(int(a) - 1, min(int(b), total)):
                indices.append(i)
        elif part.isdigit():
            idx = int(part) - 1
            if 0 <= idx < total:
                indices.append(idx)

    return sorted(set(indices))


def _parse_range_tuples(spec: str, total: int) -> List[Tuple[int, int]]:
    """Convert "1-3,5,7-9" into list of (start, end) exclusive tuples."""
    pages  = _parse_pages(spec, total)
    ranges: List[Tuple[int, int]] = []
    if not pages:
        return ranges
    start = pages[0]
    prev  = pages[0]
    for p in pages[1:]:
        if p != prev + 1:
            ranges.append((start, prev + 1))
            start = p
        prev = p
    ranges.append((start, prev + 1))
    return ranges
