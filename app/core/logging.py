"""DocForge — Logging setup"""
import logging
import sys

def setup_logging(level: str = "INFO"):
    fmt = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format=fmt,
        handlers=[
            logging.StreamHandler(sys.stdout),
        ]
    )
    # Quiet noisy libraries
    for lib in ("multipart", "httpx", "httpcore", "openai"):
        logging.getLogger(lib).setLevel(logging.WARNING)
