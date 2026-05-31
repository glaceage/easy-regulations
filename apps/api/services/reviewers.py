import uuid

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.models.comment import Comment
from apps.api.models.policy import Policy
from apps.api.models.revision import Revision, RevisionState
from apps.api.models.revision_reviewer import RevisionReviewer
from apps.api.models.user import User, UserRole
from apps.api.schemas.reviewer import (
    ReviewAssignmentResponse,
    ReviewerAssignRequest,
    ReviewerResponse,
)
from apps.api.services import revisions as revision_service
from apps.api.services.audit import record_event
from apps.api.services.notifications import notify_users

ASSIGNABLE_STATES = {
    RevisionState.DRAFT,
    RevisionState.IN_CONSULTATION,
    RevisionState.IN_REVISION,
}


async def list_reviewers(db: AsyncSession, revision_id: uuid.UUID) -> list[ReviewerResponse]:
    revision = await revision_service.get_revision(db, revision_id)
    if revision is None:
        raise HTTPException(status_code=404, detail="修订任务不存在")

    count_rows = await db.execute(
        select(Comment.author_id, func.count(Comment.id))
        .where(Comment.revision_id == revision_id)
        .group_by(Comment.author_id)
    )
    counts: dict[uuid.UUID, int] = {author_id: cnt for author_id, cnt in count_rows.all()}

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
            comment_count=int(counts.get(rr.user_id, 0)),
            feedback_status=_feedback_status(
                revision.state,
                is_mandatory=rr.is_mandatory,
                my_comment_count=int(counts.get(rr.user_id, 0)),
            ),
        )
        for rr, user in rows
    ]


def _feedback_status(
    revision_state: RevisionState,
    *,
    is_mandatory: bool,
    my_comment_count: int,
) -> str:
    if revision_state != RevisionState.IN_CONSULTATION:
        return "closed"
    if my_comment_count > 0:
        return "submitted"
    if is_mandatory:
        return "awaiting"
    return "optional"


async def list_my_assignments(
    db: AsyncSession,
    user: User,
) -> list[ReviewAssignmentResponse]:
    if user.role != UserRole.REVIEWER:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="仅评审人可访问")

    comment_counts = (
        select(Comment.revision_id, func.count(Comment.id).label("cnt"))
        .where(Comment.author_id == user.id)
        .group_by(Comment.revision_id)
        .subquery()
    )

    result = await db.execute(
        select(RevisionReviewer, Revision, Policy, comment_counts.c.cnt)
        .join(Revision, RevisionReviewer.revision_id == Revision.id)
        .join(Policy, Revision.policy_id == Policy.id)
        .outerjoin(comment_counts, comment_counts.c.revision_id == Revision.id)
        .where(RevisionReviewer.user_id == user.id)
        .order_by(Revision.updated_at.desc())
    )

    items: list[ReviewAssignmentResponse] = []
    for assignment, revision, policy, comment_count in result.all():
        my_comment_count = int(comment_count or 0)
        items.append(
            ReviewAssignmentResponse(
                assignment_id=assignment.id,
                revision_id=revision.id,
                policy_id=policy.id,
                policy_code=policy.code,
                policy_title=policy.title,
                revision_state=revision.state.value,
                target_version_label=revision.target_version_label,
                change_brief=revision.change_brief,
                is_mandatory=assignment.is_mandatory,
                assigned_at=assignment.created_at,
                my_comment_count=my_comment_count,
                feedback_status=_feedback_status(
                    revision.state,
                    is_mandatory=assignment.is_mandatory,
                    my_comment_count=my_comment_count,
                ),
            )
        )
    return items


async def is_assigned_reviewer(
    db: AsyncSession,
    revision_id: uuid.UUID,
    user_id: uuid.UUID,
) -> bool:
    result = await db.execute(
        select(RevisionReviewer.id).where(
            RevisionReviewer.revision_id == revision_id,
            RevisionReviewer.user_id == user_id,
        )
    )
    return result.scalar_one_or_none() is not None


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

    policy_result = await db.execute(select(Policy).where(Policy.id == revision.policy_id))
    policy = policy_result.scalar_one_or_none()
    policy_title = policy.title if policy else "制度修订"

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
    await notify_users(
        db,
        user_ids=[reviewer_user.id],
        message=(
            f"您已被指定为《{policy_title}》"
            f"（{revision.target_version_label or '修订草案'}）的评审人，"
            "请在「我的评审」中查看并提交意见。"
        ),
        revision_id=revision_id,
        policy_id=revision.policy_id,
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
        comment_count=0,
        feedback_status=_feedback_status(
            revision.state,
            is_mandatory=assignment.is_mandatory,
            my_comment_count=0,
        ),
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

    if revision.state not in ASSIGNABLE_STATES:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="当前状态不允许移除评审人",
        )

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
