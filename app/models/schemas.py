"""
DocForge — Pydantic schemas shared across all routers.
"""

from pydantic import BaseModel, Field
from typing import Optional, List
from enum import Enum
import uuid


# ── Enums ─────────────────────────────────────────────────────────────────────

class JobStatus(str, Enum):
    QUEUED     = "queued"
    PROCESSING = "processing"
    DONE       = "done"
    ERROR      = "error"


class CompressionLevel(str, Enum):
    HIGH_QUALITY = "high_quality"   # light compression, best visuals
    BALANCED     = "balanced"       # recommended default
    MAXIMUM      = "maximum"        # smallest file, lower quality


class OcrLanguage(str, Enum):
    ENG  = "eng"
    ARA  = "ara"
    FRA  = "fra"
    DEU  = "deu"
    SPA  = "spa"
    CHI  = "chi_sim"
    AUTO = "auto"


class WatermarkPosition(str, Enum):
    DIAGONAL = "diagonal"
    CENTER   = "center"
    TOP_LEFT = "top_left"
    TOP_RIGHT= "top_right"
    TILE     = "tile"


class SplitMode(str, Enum):
    PAGE_RANGES = "page_ranges"
    EVERY_N     = "every_n"
    BOOKMARKS   = "bookmarks"


class SignatureType(str, Enum):
    DRAW   = "draw"
    TYPE   = "type"
    IMAGE  = "image"
    CERT   = "certificate"


class AiSummaryLength(str, Enum):
    BRIEF    = "brief"
    STANDARD = "standard"
    DETAILED = "detailed"


# ── Base response ─────────────────────────────────────────────────────────────

class JobResponse(BaseModel):
    job_id:      str         = Field(default_factory=lambda: str(uuid.uuid4()))
    status:      JobStatus   = JobStatus.QUEUED
    message:     str         = "Job queued"
    output_url:  Optional[str] = None
    output_urls: Optional[List[str]] = None
    filename:    Optional[str] = None
    size_bytes:  Optional[int] = None
    pages:       Optional[int] = None
    duration_ms: Optional[float] = None
    error:       Optional[str] = None


class FileInfo(BaseModel):
    file_id:    str
    filename:   str
    size_bytes: int
    pages:      Optional[int]   = None
    mime_type:  str
    upload_url: str


class HealthResponse(BaseModel):
    status:      str
    version:     str
    libreoffice: bool
    ghostscript: bool
    tesseract:   bool
    poppler:     bool
    openai:      bool


# ── Tool-specific request schemas ─────────────────────────────────────────────

class MergeRequest(BaseModel):
    file_ids:       List[str]
    add_bookmarks:  bool = True
    flatten_annots: bool = False
    output_name:    str  = "merged.pdf"


class SplitRequest(BaseModel):
    file_id:     str
    mode:        SplitMode = SplitMode.PAGE_RANGES
    page_ranges: Optional[str]  = None   # "1-3,5,7-9"
    every_n:     Optional[int]  = None   # split every N pages


class CompressRequest(BaseModel):
    file_id:          str
    level:            CompressionLevel = CompressionLevel.BALANCED
    compress_images:  bool = True
    remove_metadata:  bool = False
    subset_fonts:     bool = False


class RotateRequest(BaseModel):
    file_id:  str
    angle:    int            # 90 | 180 | 270
    pages:    Optional[str] = None   # "all" | "1-3,5"


class ExtractRequest(BaseModel):
    file_id:     str
    page_ranges: str         # "1-3,5,7"
    output_name: str = "extracted.pdf"


class DeletePagesRequest(BaseModel):
    file_id: str
    pages:   str             # "2,4-6"


class WatermarkRequest(BaseModel):
    file_id:   str
    text:      Optional[str]   = "CONFIDENTIAL"
    image_id:  Optional[str]   = None
    opacity:   float           = 0.30
    position:  WatermarkPosition = WatermarkPosition.DIAGONAL
    font_size: int             = 48
    color:     str             = "#888888"
    pages:     str             = "all"


class ProtectRequest(BaseModel):
    file_id:         str
    open_password:   Optional[str] = None
    owner_password:  Optional[str] = None
    prevent_print:   bool = False
    prevent_copy:    bool = False
    prevent_edit:    bool = False


class UnlockRequest(BaseModel):
    file_id:  str
    password: str


class OcrRequest(BaseModel):
    file_id:        str
    language:       OcrLanguage = OcrLanguage.ENG
    output_mode:    str         = "searchable_pdf"  # searchable_pdf | text
    deskew:         bool        = True
    enhance:        bool        = True


class RedactRequest(BaseModel):
    file_id:  str
    patterns: List[str]          # regex patterns to redact
    pages:    str = "all"


class AddPageNumbersRequest(BaseModel):
    file_id:  str
    position: str   = "bottom_center"   # bottom_center | top_right | etc.
    start_at: int   = 1
    format:   str   = "Page {n}"
    font_size:int   = 10


class CropRequest(BaseModel):
    file_id: str
    left:    float   # pt
    top:     float
    right:   float
    bottom:  float
    pages:   str = "all"


class SignRequest(BaseModel):
    file_id:        str
    signature_type: SignatureType = SignatureType.TYPE
    signature_text: Optional[str] = None
    signature_image_id: Optional[str] = None
    page:           int   = 1
    x:              float = 72
    y:              float = 72
    width:          float = 200
    height:         float = 60
    add_timestamp:  bool  = True


class AiChatRequest(BaseModel):
    file_id:    str
    question:   str
    format:     str = "concise"   # concise | detailed | bullets
    openai_key: Optional[str] = None


class AiSummaryRequest(BaseModel):
    file_id:       str
    length:        AiSummaryLength = AiSummaryLength.STANDARD
    key_takeaways: bool = True
    action_items:  bool = False
    openai_key:    Optional[str] = None


class AiInsightsRequest(BaseModel):
    file_id:    str
    openai_key: Optional[str] = None


class AiQaRequest(BaseModel):
    file_id:       str
    num_questions: int = 5
    openai_key:    Optional[str] = None


class AiPresentationRequest(BaseModel):
    file_id:    str
    num_slides: int = 10
    openai_key: Optional[str] = None


class AiPodcastRequest(BaseModel):
    file_id:          str
    style:            str = "conversational"
    duration_minutes: int = 5
    openai_key:       Optional[str] = None


class ConvertRequest(BaseModel):
    file_id:     str
    target:      str      # "pdf", "docx", "xlsx", "pptx", "jpg", "png", "pdfa"
    output_name: Optional[str] = None
