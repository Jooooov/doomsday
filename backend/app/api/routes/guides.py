"""Personalized guide generation and retrieval (streaming SSE)"""
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.core.database import get_db
from app.api.deps import get_current_user
from app.models.user import User
from app.models.guide import Guide

router = APIRouter()
limiter = Limiter(key_func=get_remote_address)


@router.get("/me")
async def get_my_guide(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(select(Guide).where(Guide.user_id == current_user.id))
    guide = result.scalar_one_or_none()

    if not guide:
        return {"status": "pending", "message": "Preparing your regional guide — you will receive a notification when ready"}

    from app.services.content.guide_service import get_guide_content
    content = await get_guide_content(guide)

    if guide.status == "updating":
        return {"status": "updating", "content": content, "badge": "Updating..."}

    return {"status": "current", "content": content}


@router.post("/me/generate")
@limiter.limit("5/hour")
async def generate_guide(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Generate personalized guide — streaming SSE, section by section."""
    if not current_user.country_code:
        raise HTTPException(status_code=400, detail="Profile incomplete: country_code required")

    async def stream():
        from app.services.content.guide_service import generate_guide_streaming
        async for chunk in generate_guide_streaming(current_user, db):
            yield f"data: {chunk}\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream")


@router.post("/me/rollback")
async def rollback_guide(
    region: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Rollback to previous guide version: rollback --region=PT --to=previous"""
    from app.services.content.guide_service import rollback_guide_version
    return await rollback_guide_version(current_user, region, db)
