"""Personalized guide generation and retrieval (streaming SSE)"""
import logging
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.core.database import get_db
from app.core.config import settings
from app.api.deps import get_current_user
from app.models.user import User
from app.models.guide import Guide

logger = logging.getLogger(__name__)
router = APIRouter()
limiter = Limiter(key_func=get_remote_address)
_RATE_LIMIT = f"{settings.GUIDE_RATE_LIMIT_PER_HOUR}/hour"


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
    content = await get_guide_content(guide, db)

    if guide.status == "updating":
        return {"status": "updating", "content": content, "badge": "Updating..."}

    return {"status": "current", "content": content}


@router.post("/me/generate")
@limiter.limit(_RATE_LIMIT)
async def generate_guide(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Generate personalized guide — streaming SSE, section by section."""
    missing = []
    if not current_user.country_code:
        missing.append("country_code")
    if not current_user.household_size:
        missing.append("household_size")
    if not current_user.housing_type:
        missing.append("housing_type")
    if missing:
        raise HTTPException(
            status_code=400,
            detail=f"Profile incomplete — missing: {', '.join(missing)}"
        )

    async def stream():
        import json as _json
        try:
            from app.services.content.guide_service import generate_guide_streaming
            async for chunk in generate_guide_streaming(current_user, db):
                yield f"data: {chunk}\n\n"
        except Exception as e:
            logger.error(f"Stream error: {e}")
            yield f"data: {_json.dumps({'type': 'error', 'message': str(e)})}\n\n"

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
