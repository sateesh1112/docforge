"""
DocForge — AI Service
Wraps the OpenAI Chat Completions API to provide:
  - Chat with PDF
  - Document summarisation
  - Q&A extraction
  - Smart insights (word count, sentiment, key entities, reading time)
  - Presentation outline generation
  - Podcast script generation
"""

import logging
import re
from typing import AsyncGenerator, Optional

import openai

from app.core.config import settings
from app.services.pdf_service import extract_text
from pathlib import Path

logger = logging.getLogger(__name__)

_SYSTEM_BASE = (
    "You are DocForge AI, an expert document analyst embedded in a professional "
    "PDF processing suite. Your responses are clear, accurate, and grounded "
    "strictly in the document content provided. Never hallucinate facts."
)


def _get_client(api_key: Optional[str] = None) -> openai.AsyncOpenAI:
    key = api_key or settings.OPENAI_API_KEY
    if not key:
        raise ValueError(
            "No OpenAI API key configured. "
            "Set OPENAI_API_KEY in .env or provide it via the UI (Ctrl+Shift+A)."
        )
    return openai.AsyncOpenAI(api_key=key)


# ── Chat with PDF ─────────────────────────────────────────────────────────────

async def chat_with_pdf(
    pdf_path: Path,
    question: str,
    fmt: str = "concise",
    api_key: Optional[str] = None,
) -> str:
    """Answer a question about the PDF content."""
    text   = await extract_text(pdf_path, max_chars=40_000)
    client = _get_client(api_key)

    fmt_instructions = {
        "concise":  "Answer in 1-3 sentences. Be direct.",
        "detailed": "Provide a thorough, well-structured answer with context.",
        "bullets":  "Answer using concise bullet points only.",
    }.get(fmt, "Answer concisely.")

    response = await client.chat.completions.create(
        model=settings.OPENAI_MODEL,
        max_tokens=settings.OPENAI_MAX_TOKENS,
        messages=[
            {"role": "system",  "content": _SYSTEM_BASE},
            {"role": "user",    "content": (
                f"DOCUMENT CONTENT:\n{text}\n\n"
                f"QUESTION: {question}\n\n"
                f"FORMAT INSTRUCTION: {fmt_instructions}"
            )},
        ],
        temperature=0.2,
    )
    return response.choices[0].message.content.strip()


# ── Summarisation ─────────────────────────────────────────────────────────────

async def summarise_pdf(
    pdf_path: Path,
    length: str = "standard",
    key_takeaways: bool = True,
    action_items: bool  = False,
    api_key: Optional[str] = None,
) -> dict:
    """Generate a structured summary of the PDF."""
    text   = await extract_text(pdf_path, max_chars=50_000)
    client = _get_client(api_key)

    length_guide = {
        "brief":    "Write a single concise paragraph (max 120 words).",
        "standard": "Write 3-5 paragraphs covering the main sections.",
        "detailed": "Write a comprehensive breakdown: executive summary, section-by-section analysis, and conclusions.",
    }.get(length, "Write 3-5 paragraphs.")

    extras = []
    if key_takeaways:
        extras.append("KEY_TAKEAWAYS: List 3-5 bullet points of the most important points.")
    if action_items:
        extras.append("ACTION_ITEMS: List any actionable tasks mentioned in the document.")

    prompt = (
        f"Summarise the following document.\n\n"
        f"LENGTH: {length_guide}\n\n"
        + ("\n".join(extras) + "\n\n" if extras else "")
        + f"Respond in this JSON structure:\n"
        f'{{"summary": "...", "key_takeaways": ["...", ...], "action_items": ["...", ...]}}\n\n'
        f"DOCUMENT:\n{text}"
    )

    response = await client.chat.completions.create(
        model=settings.OPENAI_MODEL,
        max_tokens=settings.OPENAI_MAX_TOKENS,
        messages=[
            {"role": "system", "content": _SYSTEM_BASE + " Always respond in valid JSON."},
            {"role": "user",   "content": prompt},
        ],
        temperature=0.3,
        response_format={"type": "json_object"},
    )

    import json
    try:
        return json.loads(response.choices[0].message.content)
    except Exception:
        return {"summary": response.choices[0].message.content, "key_takeaways": [], "action_items": []}


# ── Q&A Extraction ────────────────────────────────────────────────────────────

async def qa_extract(
    pdf_path: Path,
    num_questions: int = 5,
    api_key: Optional[str] = None,
) -> list:
    """Auto-generate Q&A pairs from the document."""
    text   = await extract_text(pdf_path, max_chars=40_000)
    client = _get_client(api_key)

    response = await client.chat.completions.create(
        model=settings.OPENAI_MODEL,
        max_tokens=2000,
        messages=[
            {"role": "system", "content": _SYSTEM_BASE + " Always respond in valid JSON."},
            {"role": "user",   "content": (
                f"Generate {num_questions} important question-and-answer pairs from this document.\n"
                f"JSON format: [{{'question': '...', 'answer': '...'}}, ...]\n\n"
                f"DOCUMENT:\n{text}"
            )},
        ],
        temperature=0.4,
        response_format={"type": "json_object"},
    )
    import json
    try:
        data = json.loads(response.choices[0].message.content)
        return data if isinstance(data, list) else data.get("qa", data.get("questions", []))
    except Exception:
        return []


# ── Document Insights ─────────────────────────────────────────────────────────

async def document_insights(
    pdf_path: Path,
    api_key: Optional[str] = None,
) -> dict:
    """Generate smart analytics and insights about the document."""
    text   = await extract_text(pdf_path, max_chars=40_000)
    client = _get_client(api_key)

    # Local stats (no API needed)
    words         = len(text.split())
    chars         = len(text)
    sentences     = len(re.findall(r'[.!?]+', text))
    reading_time  = max(1, round(words / 200))   # avg 200 wpm

    response = await client.chat.completions.create(
        model=settings.OPENAI_MODEL,
        max_tokens=1500,
        messages=[
            {"role": "system", "content": _SYSTEM_BASE + " Always respond in valid JSON."},
            {"role": "user",   "content": (
                "Analyse this document and return JSON with these fields:\n"
                "- topic (str): main subject in ≤8 words\n"
                "- document_type (str): e.g. 'Contract', 'Report', 'Invoice'\n"
                "- sentiment (str): 'positive' | 'neutral' | 'negative'\n"
                "- key_entities (list of str): up to 8 important names/orgs/places\n"
                "- language (str): detected language\n"
                "- complexity (str): 'simple' | 'moderate' | 'complex'\n"
                "- topics (list of str): up to 5 main topics covered\n\n"
                f"DOCUMENT:\n{text}"
            )},
        ],
        temperature=0.2,
        response_format={"type": "json_object"},
    )

    import json
    try:
        ai_data = json.loads(response.choices[0].message.content)
    except Exception:
        ai_data = {}

    return {
        "word_count":    words,
        "char_count":    chars,
        "sentence_count": sentences,
        "reading_time_minutes": reading_time,
        **ai_data,
    }


# ── Presentation Generator ────────────────────────────────────────────────────

async def generate_presentation_outline(
    pdf_path: Path,
    num_slides: int = 10,
    api_key: Optional[str] = None,
) -> dict:
    """Generate a presentation outline from the PDF content."""
    text   = await extract_text(pdf_path, max_chars=40_000)
    client = _get_client(api_key)

    response = await client.chat.completions.create(
        model=settings.OPENAI_MODEL,
        max_tokens=3000,
        messages=[
            {"role": "system", "content": _SYSTEM_BASE + " Always respond in valid JSON."},
            {"role": "user",   "content": (
                f"Create a {num_slides}-slide presentation outline from this document.\n"
                "JSON: {\"title\": \"...\", \"slides\": [{\"slide_num\": 1, \"title\": \"...\", \"bullets\": [\"...\", ...], \"speaker_notes\": \"...\"}]}\n\n"
                f"DOCUMENT:\n{text}"
            )},
        ],
        temperature=0.5,
        response_format={"type": "json_object"},
    )

    import json
    try:
        return json.loads(response.choices[0].message.content)
    except Exception:
        return {"title": "Presentation", "slides": []}


# ── Podcast Script Generator ──────────────────────────────────────────────────

async def generate_podcast_script(
    pdf_path: Path,
    style: str = "conversational",   # conversational | interview | monologue
    duration_minutes: int = 5,
    api_key: Optional[str] = None,
) -> dict:
    """Generate a podcast script from the PDF content."""
    text   = await extract_text(pdf_path, max_chars=40_000)
    client = _get_client(api_key)

    style_map = {
        "conversational": "a lively back-and-forth between two hosts (HOST_A and HOST_B)",
        "interview":      "an interview format with INTERVIEWER and GUEST",
        "monologue":      "a single narrator speaking directly to the audience",
    }
    fmt = style_map.get(style, style_map["conversational"])
    words_target = duration_minutes * 130   # ~130 spoken words/min

    response = await client.chat.completions.create(
        model=settings.OPENAI_MODEL,
        max_tokens=min(settings.OPENAI_MAX_TOKENS, 4096),
        messages=[
            {"role": "system", "content": _SYSTEM_BASE + " Always respond in valid JSON."},
            {"role": "user",   "content": (
                f"Create a podcast script (~{words_target} words) in {fmt} style.\n"
                "JSON: {\"title\": \"...\", \"duration_estimate\": \"5 min\", \"script\": [{\"speaker\": \"HOST_A\", \"line\": \"...\"}]}\n\n"
                f"DOCUMENT:\n{text}"
            )},
        ],
        temperature=0.7,
        response_format={"type": "json_object"},
    )

    import json
    try:
        return json.loads(response.choices[0].message.content)
    except Exception:
        return {"title": "Podcast", "script": []}
