from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.models.audit import AuditEvent
from apps.api.schemas.notification import NotificationResponse
from apps.api.services.audit import record_event


async def notify_users(
    db: AsyncSession,
    *,
    user_ids: list[uuid.UUID],
    message: str,
    revision_id: uuid.UUID,
    policy_id: uuid.UUID | None = None,
) -> None:
    """Audit-backed in-app todo stub (no SMTP/IM)."""
    for uid in user_ids:
        await record_event(
            db,
            actor_id=None,
            action="notification.todo",
            resource_type="user",
            resource_id=str(uid),
            payload={
                "user_id": str(uid),
                "message": message,
                "revision_id": str(revision_id),
                "policy_id": str(policy_id) if policy_id else None,
                "read": False,
            },
        )


async def list_notifications(db: AsyncSession, user_id: uuid.UUID) -> list[NotificationResponse]:
    result = await db.execute(
        select(AuditEvent)
        .where(
            AuditEvent.action == "notification.todo",
            AuditEvent.resource_id == str(user_id),
        )
        .order_by(AuditEvent.created_at.desc())
        .limit(50)
    )
    events = result.scalars().all()
    items: list[NotificationResponse] = []
    for event in events:
        payload = event.payload or {}
        items.append(
            NotificationResponse(
                id=event.id,
                message=str(payload.get("message", "")),
                revision_id=payload.get("revision_id"),
                policy_id=payload.get("policy_id"),
                read=bool(payload.get("read", False)),
                created_at=event.created_at,
            )
        )
    return items
