import uuid

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.models.comment import Comment, CommentStatus
from apps.api.models.revision_reviewer import RevisionReviewer


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

    await _assert_mandatory_reviewers_feedback(revision_id, db, comments)


async def _assert_mandatory_reviewers_feedback(
    revision_id: uuid.UUID,
    db: AsyncSession,
    comments: list[Comment],
) -> None:
    """Mandatory assigned reviewers must have submitted at least one comment."""
    reviewer_result = await db.execute(
        select(RevisionReviewer).where(
            RevisionReviewer.revision_id == revision_id,
            RevisionReviewer.is_mandatory.is_(True),
        )
    )
    mandatory = list(reviewer_result.scalars().all())
    if not mandatory:
        return

    comment_author_ids = {c.author_id for c in comments}
    missing = [rr for rr in mandatory if rr.user_id not in comment_author_ids]
    if missing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot enter pending_publish: mandatory reviewers have not submitted feedback",
        )
