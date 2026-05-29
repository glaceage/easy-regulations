import hashlib
import uuid

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.models.policy import Policy, PolicyStatus, PolicyVersion
from apps.api.models.revision import Revision, RevisionState, can_transition
from apps.api.models.user import User, UserRole
from apps.api.schemas.revision import RevisionCreate
from apps.api.services import workflow
from apps.api.services.audit import record_event

CHANGE_BRIEF_MIN_LENGTH = 10
EMPTY_CONTENT_SHA256 = hashlib.sha256(b"").hexdigest()


async def _get_or_create_base_version(db: AsyncSession, policy: Policy) -> PolicyVersion:
    if policy.current_version_id is not None:
        result = await db.execute(
            select(PolicyVersion).where(PolicyVersion.id == policy.current_version_id)
        )
        base_version = result.scalar_one_or_none()
        if base_version is not None:
            return base_version

    base_version = PolicyVersion(
        policy_id=policy.id,
        version_label="v0",
        status=PolicyStatus.ACTIVE,
        markdown_key="",
        content_sha256=EMPTY_CONTENT_SHA256,
        section_tree={},
    )
    db.add(base_version)
    await db.flush()
    return base_version


async def create_revision(db: AsyncSession, data: RevisionCreate, user: User) -> Revision:
    result = await db.execute(select(Policy).where(Policy.id == data.policy_id))
    policy = result.scalar_one_or_none()
    if policy is None:
        raise HTTPException(status_code=404, detail="制度不存在")

    base_version = await _get_or_create_base_version(db, policy)
    revision_id = uuid.uuid4()

    revision = Revision(
        id=revision_id,
        policy_id=policy.id,
        base_version_id=base_version.id,
        owner_user_id=user.id,
        state=RevisionState.DRAFT,
        change_brief=data.change_brief,
        draft_markdown_key=f"drafts/{revision_id}.md",
        draft_content_sha256=EMPTY_CONTENT_SHA256,
        target_version_label=data.target_version_label or "",
    )
    db.add(revision)
    await db.commit()
    await db.refresh(revision)
    return revision


async def get_revision(db: AsyncSession, revision_id: uuid.UUID) -> Revision | None:
    result = await db.execute(select(Revision).where(Revision.id == revision_id))
    return result.scalar_one_or_none()


def _assert_can_manage_revision(revision: Revision, user: User) -> None:
    if user.role in {UserRole.POLICY_ADMIN, UserRole.SYS_ADMIN}:
        return
    if revision.owner_user_id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="权限不足")


async def transition_revision(
    db: AsyncSession,
    revision_id: uuid.UUID,
    target_state: RevisionState,
    user: User,
) -> Revision:
    revision = await get_revision(db, revision_id)
    if revision is None:
        raise HTTPException(status_code=404, detail="修订任务不存在")

    _assert_can_manage_revision(revision, user)

    current_state = revision.state
    if not can_transition(current_state, target_state):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"无法从 {current_state.value} 转换到 {target_state.value}",
        )

    if (
        current_state == RevisionState.DRAFT
        and target_state != RevisionState.CANCELLED
        and len(revision.change_brief.strip()) < CHANGE_BRIEF_MIN_LENGTH
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"离开草稿状态前，变更说明至少需要 {CHANGE_BRIEF_MIN_LENGTH} 个字符",
        )

    if target_state == RevisionState.PENDING_PUBLISH:
        await workflow.assert_can_enter_pending_publish(revision_id, db)

    revision.state = target_state
    await record_event(
        db,
        actor_id=user.id,
        action="revision.transition",
        resource_type="revision",
        resource_id=str(revision.id),
        payload={
            "from_state": current_state.value,
            "to_state": target_state.value,
        },
    )
    await db.commit()
    await db.refresh(revision)
    return revision
