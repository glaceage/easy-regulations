import uuid

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.models.comment import Comment, CommentStatus
from apps.api.models.revision import RevisionState
from apps.api.models.user import User, UserRole
from apps.api.schemas.comment import CommentCreate, CommentUpdate
from apps.api.services import revisions as revision_service

COMMENT_SUBMIT_STATES = {RevisionState.IN_CONSULTATION, RevisionState.IN_REVISION}
COMMENT_CREATE_ROLES = {
    UserRole.REVIEWER,
    UserRole.OWNER,
    UserRole.POLICY_ADMIN,
    UserRole.SYS_ADMIN,
}
COMMENT_UPDATE_ROLES = {
    UserRole.OWNER,
    UserRole.POLICY_ADMIN,
    UserRole.SYS_ADMIN,
}


def _has_resolution_note(note: str | None) -> bool:
    return bool(note and note.strip())


def _validate_status_resolution(status: CommentStatus, resolution_note: str | None) -> None:
    if status in {CommentStatus.REJECTED, CommentStatus.DEFERRED} and not _has_resolution_note(
        resolution_note
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="rejected or deferred comments require resolution_note",
        )


async def create_comment(
    db: AsyncSession,
    revision_id: uuid.UUID,
    data: CommentCreate,
    user: User,
) -> Comment:
    if user.role not in COMMENT_CREATE_ROLES:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="权限不足")

    revision = await revision_service.get_revision(db, revision_id)
    if revision is None:
        raise HTTPException(status_code=404, detail="修订任务不存在")
    if revision.state not in COMMENT_SUBMIT_STATES:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="当前修订状态不允许提交意见",
        )

    comment = Comment(
        revision_id=revision_id,
        section_id=data.section_id,
        author_id=user.id,
        body=data.body,
        status=CommentStatus.OPEN,
        is_mandatory_reviewer=user.role == UserRole.REVIEWER,
    )
    db.add(comment)
    await db.commit()
    await db.refresh(comment)
    return comment


async def list_comments(db: AsyncSession, revision_id: uuid.UUID) -> list[Comment]:
    revision = await revision_service.get_revision(db, revision_id)
    if revision is None:
        raise HTTPException(status_code=404, detail="修订任务不存在")

    result = await db.execute(
        select(Comment)
        .where(Comment.revision_id == revision_id)
        .order_by(Comment.created_at)
    )
    return list(result.scalars().all())


async def update_comment(
    db: AsyncSession,
    comment_id: uuid.UUID,
    data: CommentUpdate,
    user: User,
) -> Comment:
    if user.role not in COMMENT_UPDATE_ROLES:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="权限不足")

    result = await db.execute(select(Comment).where(Comment.id == comment_id))
    comment = result.scalar_one_or_none()
    if comment is None:
        raise HTTPException(status_code=404, detail="意见不存在")

    revision = await revision_service.get_revision(db, comment.revision_id)
    if revision is None:
        raise HTTPException(status_code=404, detail="修订任务不存在")

    if user.role == UserRole.OWNER and revision.owner_user_id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="权限不足")

    if data.status is None and data.resolution_note is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="至少提供 status 或 resolution_note",
        )

    new_status = data.status if data.status is not None else comment.status
    new_resolution_note = (
        data.resolution_note if data.resolution_note is not None else comment.resolution_note
    )
    _validate_status_resolution(new_status, new_resolution_note)

    if data.status is not None:
        comment.status = data.status
    if data.resolution_note is not None:
        comment.resolution_note = data.resolution_note

    await db.commit()
    await db.refresh(comment)
    return comment
