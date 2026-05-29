import hashlib
import uuid

from botocore.exceptions import ClientError
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.models.policy import Policy, PolicyStatus, PolicyVersion
from apps.api.models.revision import Revision, RevisionState, can_transition
from apps.api.models.user import User, UserRole
from apps.api.schemas.revision import PublishResponse, RevisionCreate
from apps.api.services import workflow
from apps.api.services.audit import record_event
from apps.api.services.export import html_to_pdf, markdown_to_html
from apps.api.services.sections import build_section_tree
from apps.api.services.storage import StorageService

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


def _assert_policy_admin(user: User) -> None:
    if user.role != UserRole.POLICY_ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="仅制度管理员可发布",
        )


def _load_draft_markdown(storage: StorageService, key: str) -> str:
    if not key:
        return ""
    try:
        return storage.get_bytes(key).decode("utf-8")
    except ClientError:
        return ""


def _export_revision_pdf(
    storage: StorageService,
    *,
    markdown: str,
    policy_title: str,
    version_label: str,
    prefix: str,
) -> str:
    html_content = markdown_to_html(
        markdown,
        title=policy_title,
        version=version_label,
    )
    pdf_bytes = html_to_pdf(html_content)
    return storage.put_bytes(pdf_bytes, suffix=".pdf", prefix=prefix)


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


async def publish_revision(
    db: AsyncSession,
    revision_id: uuid.UUID,
    user: User,
) -> PublishResponse:
    _assert_policy_admin(user)

    revision = await get_revision(db, revision_id)
    if revision is None:
        raise HTTPException(status_code=404, detail="修订任务不存在")

    if revision.state != RevisionState.PENDING_PUBLISH:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"无法发布：当前状态为 {revision.state.value}，需要 pending_publish",
        )

    if not revision.target_version_label.strip():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="无法发布：目标版本号不能为空",
        )

    await workflow.assert_can_publish(revision_id, db)

    policy_result = await db.execute(select(Policy).where(Policy.id == revision.policy_id))
    policy = policy_result.scalar_one_or_none()
    if policy is None:
        raise HTTPException(status_code=404, detail="制度不存在")

    storage = StorageService()
    markdown = _load_draft_markdown(storage, revision.draft_markdown_key)
    md_bytes = markdown.encode("utf-8")
    content_sha256 = hashlib.sha256(md_bytes).hexdigest()
    section_tree = {"sections": build_section_tree(markdown)}

    version_prefix = f"policies/{policy.id}/versions/"
    markdown_key = storage.put_bytes(md_bytes, suffix=".md", prefix=version_prefix)

    export_prefix = f"policies/{policy.id}/{revision.id}/"
    pdf_key = _export_revision_pdf(
        storage,
        markdown=markdown,
        policy_title=policy.title,
        version_label=revision.target_version_label,
        prefix=export_prefix,
    )

    if policy.current_version_id is not None:
        current_result = await db.execute(
            select(PolicyVersion).where(PolicyVersion.id == policy.current_version_id)
        )
        current_version = current_result.scalar_one_or_none()
        if current_version is not None:
            current_version.status = PolicyStatus.SUPERSEDED

    new_version = PolicyVersion(
        policy_id=policy.id,
        version_label=revision.target_version_label,
        status=PolicyStatus.ACTIVE,
        markdown_key=markdown_key,
        pdf_key=pdf_key,
        content_sha256=content_sha256,
        section_tree=section_tree,
        published_by_id=user.id,
    )
    db.add(new_version)
    await db.flush()

    policy.current_version_id = new_version.id
    revision.state = RevisionState.PUBLISHED

    await record_event(
        db,
        actor_id=user.id,
        action="revision.publish",
        resource_type="revision",
        resource_id=str(revision.id),
        payload={
            "policy_id": str(policy.id),
            "policy_version_id": str(new_version.id),
            "version_label": new_version.version_label,
            "pdf_key": pdf_key,
        },
    )

    await db.commit()
    await db.refresh(revision)
    await db.refresh(new_version)

    return PublishResponse(
        revision_id=revision.id,
        state=revision.state,
        policy_version_id=new_version.id,
        version_label=new_version.version_label,
        pdf_key=pdf_key,
        markdown_key=markdown_key,
    )
