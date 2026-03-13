"""Family group management — create, join, checklist"""
import uuid
import secrets
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.api.deps import get_current_user
from app.models.user import User
from app.models.family_group import FamilyGroup
from app.models.checklist import ChecklistItem

router = APIRouter()


@router.post("/create")
async def create_group(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.family_group_id:
        raise HTTPException(status_code=400, detail="Already in a group")

    group = FamilyGroup(
        id=str(uuid.uuid4()),
        admin_id=current_user.id,
        invite_token=secrets.token_urlsafe(32),
    )
    db.add(group)
    current_user.family_group_id = group.id
    await db.commit()
    await db.refresh(group)
    return {"group_id": group.id, "invite_link": f"/join/{group.invite_token}", "admin": True}


@router.post("/join/{invite_token}")
async def join_group(
    invite_token: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(select(FamilyGroup).where(FamilyGroup.invite_token == invite_token))
    group = result.scalar_one_or_none()
    if not group:
        raise HTTPException(status_code=404, detail="Invalid invite link")
    if current_user.family_group_id == group.id:
        raise HTTPException(status_code=400, detail="Already in this group")

    current_user.family_group_id = group.id
    await db.commit()
    return {"group_id": group.id, "admin": group.admin_id == current_user.id}


@router.get("/me")
async def get_my_group(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not current_user.family_group_id:
        return {"group": None}

    result = await db.execute(select(FamilyGroup).where(FamilyGroup.id == current_user.family_group_id))
    group = result.scalar_one_or_none()
    if not group:
        return {"group": None}

    members_result = await db.execute(select(User).where(User.family_group_id == group.id))
    members = members_result.scalars().all()

    return {
        "group_id": group.id,
        "is_admin": group.admin_id == current_user.id,
        "invite_link": f"/join/{group.invite_token}",
        "member_count": len(members),
        "members": [{"id": m.id, "email": m.email} for m in members],
    }


@router.get("/me/checklist")
async def get_group_checklist(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not current_user.family_group_id:
        raise HTTPException(status_code=404, detail="Not in a group")

    result = await db.execute(
        select(ChecklistItem)
        .where(ChecklistItem.family_group_id == current_user.family_group_id)
        .order_by(ChecklistItem.priority.desc())
    )
    items = result.scalars().all()
    return {"items": [
        {
            "id": item.id,
            "text": item.item_text,
            "category": item.category,
            "status": item.status,
            "progress": item.progress,
            "assigned_to": item.assigned_to,
            "calculated_quantity": item.calculated_quantity,
            "quantity_unit": item.quantity_unit,
            "is_new_recommendation": item.is_new_recommendation,
            "origin": "family",
        }
        for item in items
    ]}


@router.patch("/me/checklist/{item_id}")
async def update_checklist_item(
    item_id: str,
    status: str,
    progress: float = 0.0,
    assigned_to: str = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(select(ChecklistItem).where(ChecklistItem.id == item_id))
    item = result.scalar_one_or_none()
    if not item or item.family_group_id != current_user.family_group_id:
        raise HTTPException(status_code=404, detail="Item not found")

    item.status = status
    item.progress = progress
    if assigned_to is not None:
        item.assigned_to = assigned_to
    await db.commit()
    return {"ok": True}


@router.post("/me/admin/transfer/{new_admin_id}")
async def transfer_admin(
    new_admin_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Transfer admin role to another member."""
    result = await db.execute(select(FamilyGroup).where(FamilyGroup.id == current_user.family_group_id))
    group = result.scalar_one_or_none()
    if not group or group.admin_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not group admin")

    group.admin_id = new_admin_id
    group.admin_deletion_deadline = None
    await db.commit()
    return {"new_admin": new_admin_id}
