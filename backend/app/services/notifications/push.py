"""Web Push notification service — triggers on risk level changes"""
import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete

logger = logging.getLogger(__name__)


def _send_webpush_sync(endpoint: str, keys: dict, payload: dict) -> None:
    """Synchronous pywebpush call — run in executor for async contexts."""
    from pywebpush import webpush, WebPushException
    from app.config import get_settings

    settings = get_settings()
    if not settings.VAPID_PRIVATE_KEY:
        logger.warning("[Push] VAPID_PRIVATE_KEY not configured — skipping")
        return

    try:
        webpush(
            subscription_info={"endpoint": endpoint, "keys": keys},
            data=json.dumps(payload),
            vapid_private_key=settings.VAPID_PRIVATE_KEY,
            vapid_claims={"sub": f"mailto:{settings.VAPID_CLAIMS_EMAIL}"},
        )
    except WebPushException as e:
        if e.response and e.response.status_code == 410:
            raise ValueError("subscription_expired")
        raise


async def _send_webpush(endpoint: str, keys: dict, payload: dict) -> None:
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, _send_webpush_sync, endpoint, keys, payload)


async def send_push_to_user(user_id: str, title: str, body: str, data: dict, db: AsyncSession):
    """Send Web Push to all subscriptions for a user. Removes expired subscriptions."""
    from app.models.notification import PushSubscription, Notification

    result = await db.execute(select(PushSubscription).where(PushSubscription.user_id == user_id))
    subscriptions = result.scalars().all()

    expired_endpoints = []
    for sub in subscriptions:
        payload = {"title": title, "body": body, **data}
        try:
            await _send_webpush(sub.endpoint, sub.keys, payload)
            logger.info(f"[PUSH] sent to {user_id}: {title}")
        except ValueError as e:
            if "subscription_expired" in str(e):
                expired_endpoints.append(sub.endpoint)
                logger.info(f"[PUSH] expired subscription removed: {sub.endpoint[:40]}...")
            else:
                logger.error(f"[PUSH] failed for {user_id}: {e}")
        except Exception as e:
            logger.error(f"[PUSH] failed for {user_id}: {e}")

    # Purge expired subscriptions
    if expired_endpoints:
        await db.execute(
            delete(PushSubscription).where(
                PushSubscription.user_id == user_id,
                PushSubscription.endpoint.in_(expired_endpoints),
            )
        )

    # Log notification record
    notif = Notification(
        id=str(uuid.uuid4()),
        user_id=user_id,
        notification_type=data.get("type", "generic"),
        payload={"title": title, "body": body, **data},
        delivered=len(subscriptions) > len(expired_endpoints),
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

    level_labels = {"green": "Baixo", "yellow": "Moderado", "orange": "Elevado", "red": "CRÍTICO"}
    label = level_labels.get(new_level, new_level.upper())

    for user in users:
        lang = getattr(user, "language", "pt") or "pt"
        if lang == "en":
            title = f"☢ Doomsday Alert — {country_iso}"
            body = f"Risk level: {old_level.upper()} → {new_level.upper()}"
        else:
            title = f"☢ Alerta Doomsday — {country_iso}"
            body = f"Patamar de risco: {old_level} → {label}"

        await send_push_to_user(
            user.id, title, body,
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
            lang = getattr(member, "language", "pt") or "pt"
            if lang == "en":
                title = "Family Group — Admin leaving"
                body = "The group admin is deleting their account. You have 24h to elect a new admin."
            else:
                title = "Grupo Familiar — Admin a sair"
                body = "O admin do grupo está a eliminar a conta. Tens 24h para eleger um novo admin."
            await send_push_to_user(
                member.id, title, body,
                {"type": "admin_election", "group_id": group.id},
                db,
            )
