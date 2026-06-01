"""
DocForge — AI Router
"""
from fastapi import APIRouter, HTTPException
from app.models.schemas import AiChatRequest, AiSummaryRequest, AiInsightsRequest, JobResponse, JobStatus
from app.services import ai_service
from app.services.file_service import resolve_upload
import time

router = APIRouter()

@router.post("/chat")
async def chat_with_pdf(req: AiChatRequest):
    src = resolve_upload(req.file_id)
    try:
        answer = await ai_service.chat_with_pdf(src, req.question, req.format)
        return {"answer": answer, "file_id": req.file_id}
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/summary")
async def summarise(req: AiSummaryRequest):
    src = resolve_upload(req.file_id)
    try:
        result = await ai_service.summarise_pdf(
            src, req.length.value, req.key_takeaways, req.action_items
        )
        return result
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/insights")
async def insights(req: AiInsightsRequest):
    src = resolve_upload(req.file_id)
    try:
        return await ai_service.document_insights(src)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/qa")
async def qa_extract(file_id: str, num_questions: int = 5):
    src = resolve_upload(file_id)
    try:
        return {"qa": await ai_service.qa_extract(src, num_questions)}
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/presentation")
async def presentation(file_id: str, num_slides: int = 10):
    src = resolve_upload(file_id)
    try:
        return await ai_service.generate_presentation_outline(src, num_slides)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/podcast")
async def podcast(file_id: str, style: str = "conversational", duration_minutes: int = 5):
    src = resolve_upload(file_id)
    try:
        return await ai_service.generate_podcast_script(src, style, duration_minutes)
    except ValueError as e:
        raise HTTPException(400, str(e))
