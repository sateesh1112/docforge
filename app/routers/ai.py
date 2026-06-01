"""
DocForge — AI Router
"""
from fastapi import APIRouter, HTTPException
from app.models.schemas import (
    AiChatRequest, AiSummaryRequest, AiInsightsRequest,
    AiQaRequest, AiPresentationRequest, AiPodcastRequest,
)
from app.services import ai_service
from app.services.file_service import resolve_upload

router = APIRouter()


@router.post("/chat")
async def chat_with_pdf(req: AiChatRequest):
    src = resolve_upload(req.file_id)
    try:
        answer = await ai_service.chat_with_pdf(src, req.question, req.format, req.openai_key)
        return {"answer": answer, "file_id": req.file_id}
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/summary")
async def summarise(req: AiSummaryRequest):
    src = resolve_upload(req.file_id)
    try:
        result = await ai_service.summarise_pdf(
            src, req.length.value, req.key_takeaways, req.action_items, req.openai_key
        )
        return result
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/insights")
async def insights(req: AiInsightsRequest):
    src = resolve_upload(req.file_id)
    try:
        return await ai_service.document_insights(src, req.openai_key)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/qa")
async def qa_extract(req: AiQaRequest):
    src = resolve_upload(req.file_id)
    try:
        return {"qa": await ai_service.qa_extract(src, req.num_questions, req.openai_key)}
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/presentation")
async def presentation(req: AiPresentationRequest):
    src = resolve_upload(req.file_id)
    try:
        return await ai_service.generate_presentation_outline(src, req.num_slides, req.openai_key)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/podcast")
async def podcast(req: AiPodcastRequest):
    src = resolve_upload(req.file_id)
    try:
        return await ai_service.generate_podcast_script(
            src, req.style, req.duration_minutes, req.openai_key
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
