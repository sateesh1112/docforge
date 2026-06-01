"""DocForge — Configuration (cloud-compatible)"""

from pydantic_settings import BaseSettings
from pydantic import Field
from pathlib import Path
from typing import List
import shutil, os


class Settings(BaseSettings):
    APP_ENV:  str = Field("production", env="APP_ENV")
    SECRET_KEY: str = Field("docforge-change-me", env="SECRET_KEY")
    ALLOWED_ORIGINS: List[str] = Field(["*"], env="ALLOWED_ORIGINS")

    # On Render/Railway /tmp is writable; use env vars to override
    BASE_DIR: Path = Path("/app")
    UPLOAD_DIR: Path = Field(None)
    OUTPUT_DIR: Path = Field(None)
    TEMP_DIR:   Path = Field(None)

    def model_post_init(self, __context):
        base = Path(os.environ.get("RENDER_VOLUME_PATH", "/tmp/docforge"))
        if self.UPLOAD_DIR is None:
            self.UPLOAD_DIR = Path(os.environ.get("UPLOAD_DIR",  str(base / "uploads")))
        if self.OUTPUT_DIR is None:
            self.OUTPUT_DIR = Path(os.environ.get("OUTPUT_DIR",  str(base / "outputs")))
        if self.TEMP_DIR is None:
            self.TEMP_DIR   = Path(os.environ.get("TEMP_DIR",    str(base / "temp")))

    MAX_FILE_SIZE_MB:     int  = Field(50,  env="MAX_FILE_SIZE_MB")
    MAX_BATCH_FILES:      int  = Field(10,  env="MAX_BATCH_FILES")
    FILE_RETENTION_HOURS: int  = Field(2,   env="FILE_RETENTION_HOURS")

    # System tools — auto-detected
    LIBREOFFICE_PATH: str = Field(
        shutil.which("libreoffice") or shutil.which("soffice") or "libreoffice",
        env="LIBREOFFICE_PATH"
    )
    GHOSTSCRIPT_PATH: str = Field(
        shutil.which("gs") or "gs",
        env="GHOSTSCRIPT_PATH"
    )
    TESSERACT_PATH: str = Field(
        shutil.which("tesseract") or "tesseract",
        env="TESSERACT_PATH"
    )
    POPPLER_PATH: str = Field("", env="POPPLER_PATH")

    # OpenAI
    OPENAI_API_KEY:    str = Field("", env="OPENAI_API_KEY")
    OPENAI_MODEL:      str = Field("gpt-4o", env="OPENAI_MODEL")
    OPENAI_MAX_TOKENS: int = Field(4096, env="OPENAI_MAX_TOKENS")

    WORKERS: int = Field(1, env="WORKERS")
    STORAGE_BACKEND: str = Field("local", env="STORAGE_BACKEND")

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True
        extra = "ignore"


settings = Settings()
