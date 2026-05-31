import uuid

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.models.revision import RevisionState
from apps.api.models.revision_reviewer import RevisionReviewer
from apps.api.models.user import User, UserRole
from apps.api.schemas.reviewer import ReviewerAssignRequest, ReviewerResponse
from apps.api.services import revisions as revision_service
from apps.api.services.audit import record_event

ASSIGNABLE_STATES = {
    RevisionState.DRAFT,
    RevisionState.IN_CONSULTATION,
    RevisionState.IN_REVISION,
}


async def list_reviewers(db: AsyncSession, revision_id: uuid.UUID) -> list[ReviewerResponse]:
    revision = await revision_service.get_revision(db, revision_id)
    if revision is None:
        raise HTTPException(status_code=404, detail="修订任务不存在")

    result = await db.execute(
        select(RevisionReviewer, User)
        .join(User, RevisionReviewer.user_id == User.id)
        .where(RevisionReviewer.revision_id == revision_id)
        .order_by(RevisionReviewer.created_at)
    )
    rows = result.all()
    return [
        ReviewerResponse(
            id=rr.id,
            revision_id=rr.revision_id,
            user_id=rr.user_id,
            username=user.username,
            display_name=user.display_name,
            is_mandatory=rr.is_mandatory,
            note=rr.note,
            created_at=rr.created_at,
        )
        for rr, user in rows
    ]


async def assign_reviewer(
    db: AsyncSession,
    revision_id: uuid.UUID,
    data: ReviewerAssignRequest,
    user: User,
) -> ReviewerResponse:
    revision = await revision_service.get_revision(db, revision_id)
    if revision is None:
        raise HTTPException(status_code=404, detail="修订任务不存在")

    revision_service._assert_can_manage_revision(revision, user)

    if revision.state not in ASSIGNABLE_STATES:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="当前状态不允许指定评审人",
        )

    user_result = await db.execute(select(User).where(User.username == data.username.strip()))
    reviewer_user = user_result.scalar_one_or_none()
    if reviewer_user is None:
        raise HTTPException(status_code=404, detail="用户不存在")
    if reviewer_user.role != UserRole.REVIEWER:
        raise HTTPException(status_code=409, detail="仅可指定评审人角色的用户")

    existing = await db.execute(
        select(RevisionReviewer).where(
            RevisionReviewer.revision_id == revision_id,
            RevisionReviewer.user_id == reviewer_user.id,
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(status_code=409, detail="该评审人已指定")

    assignment = RevisionReviewer(
        revision_id=revision_id,
        user_id=reviewer_user.id,
        is_mandatory=data.is_mandatory,
        assigned_by_id=user.id,
        note=data.note.strip(),
    )
    db.add(assignment)
    await record_event(
        db,
        actor_id=user.id,
        action="revision.reviewer.assigned",
        resource_type="revision",
        resource_id=str(revision_id),
        payload={
            "reviewer_user_id": str(reviewer_user.id),
            "username": reviewer_user.username,
            "is_mandatory": data.is_mandatory,
        },
    )
    await db.commit()
    await db.refresh(assignment)

    return ReviewerResponse(
        id=assignment.id,
        revision_id=assignment.revision_id,
        user_id=assignment.user_id,
        username=reviewer_user.username,
        display_name=reviewer_user.display_name,
        is_mandatory=assignment.is_mandatory,
        note=assignment.note,
        created_at=assignment.created_at,
    )


async def remove_reviewer(
    db: AsyncSession,
    revision_id: uuid.UUID,
    reviewer_id: uuid.UUID,
    user: User,
) -> None:
    revision = await revision_service.get_revision(db, revision_id)
    if revision is None:
        raise HTTPException(status_code=404, detail="修订任务不存在")

    revision_service._assert_can_manage_revision(revision, user)

    result = await db.execute(
        select(RevisionReviewer).where(
            RevisionReviewer.id == reviewer_id,
            RevisionReviewer.revision_id == revision_id,
        )
    )
    assignment = result.scalar_one_or_none()
    if assignment is None:
        raise HTTPException(status_code=404, detail="评审人指定不存在")

    await db.delete(assignment)
    await record_event(
        db,
        actor_id=user.id,
        action="revision.reviewer.removed",
        resource_type="revision",
        resource_id=str(revision_id),
        payload={"reviewer_user_id": str(assignment.user_id)},
    )
    await db.commit()
