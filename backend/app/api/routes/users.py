"""User profile management + GDPR endpoints"""
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete

from app.core.database import get_db
from app.api.deps import get_current_user
from app.models.user import User
from app.models.guide import Guide
from app.models.checklist import ChecklistItem
from app.schemas.user import UserOut, UserProfileUpdate

router = APIRouter()


@router.get("/me", response_model=UserOut)
async def get_me(current_user: User = Depends(get_current_user)):
    return current_user


@router.patch("/me", response_model=UserOut)
async def update_profile(
    payload: UserProfileUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    update_data = payload.model_dump(exclude_none=True)
    # GDPR: revoke health data consent -> clear stored data
    if "health_data_consent" in update_data and not update_data["health_data_consent"]:
        current_user.health_conditions = None
    for key, value in update_data.items():
        setattr(current_user, key, value)
    await db.commit()
    await db.refresh(current_user)
    return current_user


@router.delete("/me")
async def delete_account(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """GDPR: full account deletion. 24h grace period if user is group admin."""
    from app.models.family_group import FamilyGroup
    from app.services.notifications.push import notify_group_admin_deletion

    result = await db.execute(
        select(FamilyGroup).where(FamilyGroup.admin_id == current_user.id)
    )
    group = result.scalar_one_or_none()
    if group:
        group.admin_deletion_deadline = datetime.now(timezone.utc) + timedelta(hours=24)
        await notify_group_admin_deletion(group, db)

    # Anonymize immediately; hard delete runs after grace period
    current_user.deleted_at = datetime.now(timezone.utc)
    current_user.email = f"deleted_{current_user.id}@purged"
    current_user.hashed_password = None
    current_user.health_conditions = None
    current_user.google_id = None
    await db.commit()
    return {"message": "Account scheduled for deletion"}


@router.get("/me/export")
async def export_data(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """GDPR: export all user data as downloadable JSON."""
    guides_result = await db.execute(select(Guide).where(Guide.user_id == current_user.id))
    guides = guides_result.scalars().all()

    checklist_result = await db.execute(
        select(ChecklistItem).where(ChecklistItem.user_id == current_user.id)
    )
    checklist = checklist_result.scalars().all()

    export = {
        "user": {
            "id": current_user.id,
            "email": current_user.email,
            "country_code": current_user.country_code,
            "zip_code": current_user.zip_code,
            "household_size": current_user.household_size,
            "housing_type": current_user.housing_type,
            "language": current_user.language,
            "created_at": current_user.created_at.isoformat(),
        },
        "guides": [
            {"id": g.id, "status": g.status, "created_at": g.created_at.isoformat()}
            for g in guides
        ],
        "checklist": [
            {"id": c.id, "text": c.item_text, "category": c.category, "status": c.status}
            for c in checklist
        ],
        "health_conditions": current_user.health_conditions if current_user.health_data_consent else None,
        "exported_at": datetime.now(timezone.utc).isoformat(),
    }
    return JSONResponse(
        content=export,
        headers={"Content-Disposition": "attachment; filename=doomsday-export.json"},
    )
