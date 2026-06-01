# DocForge — Production Dockerfile
# Base: Python 3.12 slim + all system PDF tools pre-installed

FROM python:3.12-slim AS base

LABEL maintainer="DocForge"
LABEL description="Self-hosted PDF & Document Processing Backend"

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# ── System dependencies ───────────────────────────────────────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
    # LibreOffice — Office ↔ PDF conversion
    libreoffice \
    libreoffice-writer \
    libreoffice-calc \
    libreoffice-impress \
    # Ghostscript — compression, PDF/A, linearisation
    ghostscript \
    # Tesseract OCR + language packs
    tesseract-ocr \
    tesseract-ocr-eng \
    tesseract-ocr-ara \
    tesseract-ocr-fra \
    tesseract-ocr-deu \
    tesseract-ocr-spa \
    tesseract-ocr-chi-sim \
    # Poppler utilities — PDF→image, pdfinfo
    poppler-utils \
    # Image processing dependencies for Pillow
    libwebp-dev \
    libjpeg-dev \
    libpng-dev \
    libtiff-dev \
    # Font support
    fonts-liberation \
    fonts-dejavu \
    fonts-freefont-ttf \
    # Build tools
    gcc \
    curl \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# ── Python dependencies ───────────────────────────────────────────────────────
WORKDIR /app
COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

# ── Application code ──────────────────────────────────────────────────────────
COPY app/ ./app/
COPY scripts/ ./scripts/

# ── Create runtime directories ────────────────────────────────────────────────
RUN mkdir -p uploads outputs temp logs frontend \
    && chmod 755 uploads outputs temp logs

# ── Non-root user ────────────────────────────────────────────────────────────
RUN useradd -m -u 1001 docforge \
    && chown -R docforge:docforge /app
USER docforge

# ── Healthcheck ───────────────────────────────────────────────────────────────
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8000/api/v1/health || exit 1

EXPOSE 8000

# ── Start server ─────────────────────────────────────────────────────────────
CMD ["uvicorn", "app.main:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--workers", "4", \
     "--proxy-headers", \
     "--forwarded-allow-ips", "*"]
