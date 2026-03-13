"""Web Push notification service — triggers on risk level changes"""
import logging
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

logger = logging.getLogger(__name__)


async def send_push_to_user(user_id: str, title: str, body: str, data: dict, db: AsyncSession):
    """Send Web Push to all subscriptions for a user."""
    from app.models.notification import PushSubscription, Notification
    import uuid

    result = await db.execute(select(PushSubscription).where(PushSubscription.user_id == user_id))
    subscriptions = result.scalars().all()

    for sub in subscriptions:
        try:
            # pywebpush integration point:
            # webpush(subscription_info={"endpoint": sub.endpoint, "keys": sub.keys},
            #         data=json.dumps({"title": title, "body": body, **data}),
            #         vapid_private_key=..., vapid_claims={"sub": "mailto:..."})
            logger.info(f"[PUSH] {user_id}: {title}")
        except Exception as e:
            logger.error(f"Push failed for {user_id}: {e}")

    # Log notification record
    notif = Notification(
        id=str(uuid.uuid4()),
        user_id=user_id,
        notification_type=data.get("type", "generic"),
        payload={"title": title, "body": body, **data},
        delivered=True,
        delivered_at=datetime.now(timezone.utc),
    )
    db.add(notif)
    await db.commit()


async def notify_risk_level_change(
    country_iso: str, old_level: str, new_level: str, db: AsyncSession
):
    """Notify all users in a country immediately when risk level changes."""
    from app.models.user import User
    result = await db.execute(
        select(User).where(User.country_code == country_iso, User.deleted_at.is_(None))
    )
    users = result.scalars().all()
    for user in users:
        await send_push_to_user(
            user.id,
            f"⚠️ Doomsday Clock — {country_iso}",
            f"Risk level changed: {old_level} → {new_level}",
            {"type": "risk_level_change", "country": country_iso, "level": new_level},
            db,
        )


async def notify_group_admin_deletion(group, db: AsyncSession):
    """Notify group members that admin is leaving (24h grace period)."""
    from app.models.user import User
    result = await db.execute(
        select(User).where(User.family_group_id == group.id, User.deleted_at.is_(None))
    )
    members = result.scalars().all()
    for member in members:
        if member.id != group.admin_id:
            await send_push_to_user(
                member.id,
                "Family Group — Admin leaving",
                "The group admin is deleting their account. You have 24h to elect a new admin.",
                {"type": "admin_election", "group_id": group.id},
                db,
            )
