import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.models.audit import AuditEvent


async def record_event(
    db: AsyncSession,
    *,
    actor_id: uuid.UUID | None,
    action: str,
    resource_type: str,
    resource_id: str,
    payload: dict | None = None,
) -> AuditEvent:
    event = AuditEvent(
        actor_id=actor_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        payload=payload if payload is not None else {},
    )
    db.add(event)
    await db.flush()
    return event
