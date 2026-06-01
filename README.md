# DocForge — Self-Hosted PDF Backend

Production-grade FastAPI backend powering all 45 PDF tools with zero external API fees.

---

## Architecture

```
Browser (docforge-light.html)
        │
        │  HTTP / REST
        ▼
┌─────────────────────────────────────────────────┐
│  Nginx  (port 80/443)                           │
│  • Rate limiting  • SSL termination             │
│  • Static frontend serving                      │
└──────────────────┬──────────────────────────────┘
                   │  proxy /api/*
                   ▼
┌─────────────────────────────────────────────────┐
│  FastAPI  (port 8000, 4 workers)                │
│                                                 │
│  Routers                                        │
│  ├── /api/v1/files      ← upload / download     │
│  ├── /api/v1/create     ← office→PDF, merge     │
│  ├── /api/v1/convert    ← PDF→docx/xlsx/jpg     │
│  ├── /api/v1/edit       ← text, highlight, form │
│  ├── /api/v1/organize   ← split/merge/rotate    │
│  ├── /api/v1/compress   ← GS compression        │
│  ├── /api/v1/ocr        ← Tesseract pipeline    │
│  ├── /api/v1/security   ← protect/unlock/redact │
│  ├── /api/v1/sign       ← visual e-signature    │
│  ├── /api/v1/watermark  ← text/image watermark  │
│  └── /api/v1/ai         ← OpenAI powered        │
│                                                 │
│  Services                                       │
│  ├── pdf_service.py  ← PyMuPDF + GS + LO core  │
│  ├── ai_service.py   ← OpenAI Chat Completions  │
│  └── file_service.py ← upload/storage/cleanup  │
└──────────┬──────────────────────────────────────┘
           │  subprocess calls
           ▼
┌──────────────────────────────────┐
│  System tools (installed in OS)  │
│  ├── LibreOffice  (soffice)      │
│  ├── Ghostscript  (gs)           │
│  ├── Tesseract    (tesseract)    │
│  └── Poppler      (pdftoppm)     │
└──────────────────────────────────┘
```

---

## Quick Start

### Option A — Docker (recommended)

```bash
# 1. Clone / copy this project
git clone https://github.com/yourorg/docforge
cd docforge

# 2. Configure environment
cp .env.example .env
# Edit .env — at minimum set SECRET_KEY and OPENAI_API_KEY

# 3. Build and start
docker compose up --build

# App is live at http://localhost
# API docs at  http://localhost/api/docs
```

### Option B — Local Python

```bash
# Prerequisites (Ubuntu / Debian)
sudo apt install libreoffice ghostscript tesseract-ocr \
     tesseract-ocr-eng tesseract-ocr-ara poppler-utils \
     fonts-liberation

# macOS
brew install libreoffice ghostscript tesseract poppler

# Python setup
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Configure
cp .env.example .env    # edit as needed

# Run
uvicorn app.main:app --reload --port 8000
```

---

## API Reference

All endpoints accept and return JSON (except file upload/download).
Interactive docs: `http://localhost:8000/api/docs`

### Upload a file first
```http
POST /api/v1/files/upload
Content-Type: multipart/form-data
Body: file=<your_file>

Response: { "file_id": "abc123", "filename": "report.pdf", "pages": 12, ... }
```

### Then call any tool with that file_id

| Category    | Endpoint                              | Key params                          |
|-------------|---------------------------------------|-------------------------------------|
| **Create**  | `POST /create/office-to-pdf`          | `file` (multipart)                  |
|             | `POST /create/images-to-pdf`          | `files[]` (multipart)               |
|             | `POST /create/merge`                  | `file_ids[]`, `add_bookmarks`       |
| **Convert** | `POST /convert/pdf-to-office`         | `file_id`, `target` (docx/xlsx/pptx)|
|             | `POST /convert/pdf-to-images`         | `file_id`, `target` (jpg/png)       |
|             | `POST /convert/pdf-to-pdfa`           | `file_id`                           |
| **Edit**    | `POST /edit/add-text`                 | `file_id`, `text`, `page`, `x`, `y` |
|             | `POST /edit/highlight`                | `file_id`, `search_term`, `color`   |
|             | `POST /edit/fill-form`                | `file_id`, `fields` (dict)          |
| **Organize**| `POST /organize/split`                | `file_id`, `mode`, `page_ranges`    |
|             | `POST /organize/reorder`              | `file_id`, `new_order[]`            |
|             | `POST /organize/delete-pages`         | `file_id`, `pages`                  |
|             | `POST /organize/extract-pages`        | `file_id`, `page_ranges`            |
|             | `POST /organize/rotate`               | `file_id`, `angle`, `pages`         |
|             | `POST /organize/add-page-numbers`     | `file_id`, `position`, `format`     |
|             | `POST /organize/crop`                 | `file_id`, `left/top/right/bottom`  |
| **Compress**| `POST /compress/compress`             | `file_id`, `level`                  |
|             | `POST /compress/repair`               | `file_id`                           |
|             | `POST /compress/optimize`             | `file_id`                           |
| **OCR**     | `POST /ocr/ocr`                       | `file_id`, `language`, `output_mode`|
| **Security**| `POST /security/protect`              | `file_id`, `open_password`          |
|             | `POST /security/unlock`               | `file_id`, `password`               |
|             | `POST /security/redact`               | `file_id`, `patterns[]`             |
| **Sign**    | `POST /sign/sign-text`                | `file_id`, `signature_text`, `page` |
| **Watermark**| `POST /watermark/add`                | `file_id`, `text`, `opacity`        |
| **AI**      | `POST /ai/chat`                       | `file_id`, `question`, `format`     |
|             | `POST /ai/summary`                    | `file_id`, `length`                 |
|             | `POST /ai/insights`                   | `file_id`                           |
|             | `POST /ai/qa`                         | `file_id`, `num_questions`          |
|             | `POST /ai/presentation`               | `file_id`, `num_slides`             |
|             | `POST /ai/podcast`                    | `file_id`, `style`, `duration_min`  |

### Download result
```http
GET /api/v1/files/{file_id}/download
```

---

## Connecting the Frontend

In `docforge-light.html`, replace the mock `startProcess()` with a real fetch:

```javascript
async function processFile(toolId, fileId, options = {}) {
  const TOOL_ENDPOINTS = {
    'compress':   '/api/v1/compress/compress',
    'merge':      '/api/v1/create/merge',
    'split':      '/api/v1/organize/split',
    'ocr':        '/api/v1/ocr/ocr',
    'protect':    '/api/v1/security/protect',
    'word-pdf':   '/api/v1/create/office-to-pdf',
    'pdf-word':   '/api/v1/convert/pdf-to-office',
    'ai-chat':    '/api/v1/ai/chat',
    'ai-summary': '/api/v1/ai/summary',
    // ... all 45 tools mapped here
  };

  const endpoint = TOOL_ENDPOINTS[toolId];
  const response = await fetch(endpoint, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ file_id: fileId, ...options }),
  });

  const result = await response.json();

  if (result.output_url) {
    // Trigger download
    window.location.href = result.output_url;
  }
  return result;
}
```

---

## System Requirements

| Tool        | Min version | Purpose                     |
|-------------|-------------|-----------------------------|
| Python      | 3.11+       | Runtime                     |
| LibreOffice | 7.4+        | Office ↔ PDF conversion     |
| Ghostscript | 9.54+       | Compression, PDF/A, optimize|
| Tesseract   | 5.0+        | OCR text extraction         |
| Poppler     | 22.0+       | PDF→image, pdfinfo          |

RAM: 2 GB minimum, 4 GB recommended for concurrent processing.
Disk: 10 GB for uploads/outputs (auto-cleaned every 24h).

---

## Production Checklist

- [ ] Set `APP_ENV=production` and a strong `SECRET_KEY`
- [ ] Set `ALLOWED_ORIGINS` to your actual domain
- [ ] Configure SSL certs in `nginx/ssl/` and uncomment HTTPS block
- [ ] Set `FILE_RETENTION_HOURS` appropriate for your use case
- [ ] Set `OPENAI_API_KEY` if using AI features
- [ ] Point `STORAGE_BACKEND=s3` + credentials for cloud storage
- [ ] Configure log rotation for `logs/` directory
- [ ] Set up cron to hit `DELETE /api/v1/files/cleanup` daily
