"""Push notification subscription (Service Workers — registered users only)"""
import uuid
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from pydantic import BaseModel

from app.core.database import get_db
from app.api.deps import get_current_user
from app.models.user import User
from app.models.notification import PushSubscription

router = APIRouter()


class PushSubscriptionCreate(BaseModel):
    endpoint: str
    keys: dict  # {p256dh: str, auth: str}


@router.post("/subscribe")
async def subscribe(
    payload: PushSubscriptionCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Register Service Worker push subscription. Exclusive to registered users."""
    result = await db.execute(
        select(PushSubscription).where(
            PushSubscription.user_id == current_user.id,
            PushSubscription.endpoint == payload.endpoint,
        )
    )
    sub = result.scalar_one_or_none()
    if sub:
        sub.keys = payload.keys
    else:
        sub = PushSubscription(
            id=str(uuid.uuid4()),
            user_id=current_user.id,
            endpoint=payload.endpoint,
            keys=payload.keys,
        )
        db.add(sub)
    await db.commit()
    return {"subscribed": True}


@router.delete("/unsubscribe")
async def unsubscribe(
    endpoint: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await db.execute(
        delete(PushSubscription).where(
            PushSubscription.user_id == current_user.id,
            PushSubscription.endpoint == endpoint,
        )
    )
    await db.commit()
    return {"unsubscribed": True}
