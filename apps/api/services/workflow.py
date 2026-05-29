import uuid

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.models.comment import Comment, CommentStatus


async def assert_can_publish(revision_id: uuid.UUID, db: AsyncSession) -> None:
    """Validate publish gate: all comments resolved per pending_publish rules."""
    await assert_can_enter_pending_publish(revision_id, db)


async def assert_can_enter_pending_publish(revision_id: uuid.UUID, db: AsyncSession) -> None:
    result = await db.execute(select(Comment).where(Comment.revision_id == revision_id))
    comments = result.scalars().all()

    if any(c.status == CommentStatus.OPEN for c in comments):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot enter pending_publish: open comments remain",
        )

    missing_resolution = [
        c
        for c in comments
        if c.status in {CommentStatus.REJECTED, CommentStatus.DEFERRED}
        and not (c.resolution_note and c.resolution_note.strip())
    ]
    if missing_resolution:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Cannot enter pending_publish: rejected or deferred comments "
                "without resolution_note"
            ),
        )
