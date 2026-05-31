import hashlib
import uuid

from botocore.exceptions import ClientError
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.models.policy import Policy, PolicyStatus, PolicyVersion
from apps.api.models.revision import Revision, RevisionState, can_transition
from apps.api.models.revision_reviewer import RevisionReviewer
from apps.api.models.user import User, UserRole
from apps.api.schemas.revision import PublishResponse, RevisionCreate, RevisionMetaUpdate
from apps.api.services import workflow
from apps.api.services.audit import record_event
from apps.api.services.export import html_to_pdf, markdown_to_html
from apps.api.services.notifications import notify_users
from apps.api.services.sections import build_section_tree, ensure_section_ids
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


async def _resolve_seed_markdown(
    db: AsyncSession,
    policy: Policy,
    storage: StorageService,
) -> tuple[str, PolicyVersion]:
    """Pick the best starting markdown for a new revision.

    Priority:
    1. Latest in-progress revision draft (draft / consultation / revision / pending publish)
    2. Current published policy version
    3. Latest published revision draft (fallback if version object is missing content)
    4. Minimal template
    """
    base_version = await _get_or_create_base_version(db, policy)
    published_md = _load_draft_markdown(storage, base_version.markdown_key)

    in_progress_states = {
        RevisionState.DRAFT,
        RevisionState.IN_CONSULTATION,
        RevisionState.IN_REVISION,
        RevisionState.PENDING_PUBLISH,
    }
    latest_active = await db.execute(
        select(Revision)
        .where(
            Revision.policy_id == policy.id,
            Revision.state.in_(in_progress_states),
        )
        .order_by(Revision.updated_at.desc())
        .limit(1)
    )
    active_revision = latest_active.scalar_one_or_none()
    if active_revision is not None:
        active_md = _load_draft_markdown(storage, active_revision.draft_markdown_key)
        if active_md.strip():
            return active_md, base_version

    if published_md.strip():
        return published_md, base_version

    latest_published = await db.execute(
        select(Revision)
        .where(
            Revision.policy_id == policy.id,
            Revision.state == RevisionState.PUBLISHED,
        )
        .order_by(Revision.updated_at.desc())
        .limit(1)
    )
    published_revision = latest_published.scalar_one_or_none()
    if published_revision is not None:
        revision_md = _load_draft_markdown(storage, published_revision.draft_markdown_key)
        if revision_md.strip():
            return revision_md, base_version

    template = f"# {policy.title}\n\n在此编辑制度正文（Markdown）。\n"
    return template, base_version


async def create_revision(db: AsyncSession, data: RevisionCreate, user: User) -> Revision:
    result = await db.execute(select(Policy).where(Policy.id == data.policy_id))
    policy = result.scalar_one_or_none()
    if policy is None:
        raise HTTPException(status_code=404, detail="制度不存在")

    revision_id = uuid.uuid4()
    draft_key = f"drafts/{revision_id}.md"

    storage = StorageService()
    seed_markdown, base_version = await _resolve_seed_markdown(db, policy, storage)
    seed_markdown, _ = ensure_section_ids(seed_markdown)
    md_bytes = seed_markdown.encode("utf-8")
    storage.put_object(draft_key, md_bytes)

    revision = Revision(
        id=revision_id,
        policy_id=policy.id,
        base_version_id=base_version.id,
        owner_user_id=user.id,
        state=RevisionState.DRAFT,
        change_brief=data.change_brief,
        draft_markdown_key=draft_key,
        draft_content_sha256=hashlib.sha256(md_bytes).hexdigest(),
        target_version_label=data.target_version_label or "",
    )
    db.add(revision)
    await db.commit()
    await db.refresh(revision)
    return revision


async def get_revision(db: AsyncSession, revision_id: uuid.UUID) -> Revision | None:
    result = await db.execute(select(Revision).where(Revision.id == revision_id))
    return result.scalar_one_or_none()


async def list_revisions_for_policy(
    db: AsyncSession, policy_id: uuid.UUID
) -> list[Revision]:
    result = await db.execute(
        select(Revision)
        .where(Revision.policy_id == policy_id)
        .order_by(Revision.updated_at.desc())
    )
    return list(result.scalars().all())


def _assert_can_manage_revision(revision: Revision, user: User) -> None:
    if user.role in {UserRole.POLICY_ADMIN, UserRole.SYS_ADMIN}:
        return
    if revision.owner_user_id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="权限不足")


async def assert_can_view_revision(
    db: AsyncSession, revision: Revision, user: User
) -> None:
    """Read access: admins, the owner, or an assigned reviewer of this revision."""
    if user.role in {UserRole.POLICY_ADMIN, UserRole.SYS_ADMIN}:
        return
    if revision.owner_user_id == user.id:
        return
    assigned = await db.execute(
        select(RevisionReviewer.id).where(
            RevisionReviewer.revision_id == revision.id,
            RevisionReviewer.user_id == user.id,
        )
    )
    if assigned.scalar_one_or_none() is not None:
        return
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权查看该修订")


async def get_viewable_revision(
    db: AsyncSession, revision_id: uuid.UUID, user: User
) -> Revision:
    """Fetch a revision and enforce read access in one step."""
    revision = await get_revision(db, revision_id)
    if revision is None:
        raise HTTPException(status_code=404, detail="修订任务不存在")
    await assert_can_view_revision(db, revision, user)
    return revision


def _assert_policy_admin(user: User) -> None:
    if user.role not in {UserRole.POLICY_ADMIN, UserRole.SYS_ADMIN}:
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


DRAFT_EDITABLE_STATES = {RevisionState.DRAFT, RevisionState.IN_REVISION}
META_EDITABLE_STATES = {
    RevisionState.DRAFT,
    RevisionState.IN_REVISION,
    RevisionState.PENDING_PUBLISH,
}


async def get_draft_markdown(
    db: AsyncSession,
    revision_id: uuid.UUID,
) -> tuple[str, str]:
    revision = await get_revision(db, revision_id)
    if revision is None:
        raise HTTPException(status_code=404, detail="修订任务不存在")

    storage = StorageService()
    key = revision.draft_markdown_key or f"drafts/{revision.id}.md"
    markdown = _load_draft_markdown(storage, key)
    sha = revision.draft_content_sha256 or hashlib.sha256(markdown.encode("utf-8")).hexdigest()
    return markdown, sha


async def save_draft_markdown(
    db: AsyncSession,
    revision_id: uuid.UUID,
    markdown: str,
    user: User,
) -> tuple[str, str]:
    revision = await get_revision(db, revision_id)
    if revision is None:
        raise HTTPException(status_code=404, detail="修订任务不存在")

    _assert_can_manage_revision(revision, user)

    if revision.state not in DRAFT_EDITABLE_STATES:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="仅在起草或改稿阶段可保存正文",
        )

    storage = StorageService()
    key = revision.draft_markdown_key or f"drafts/{revision.id}.md"
    markdown, _ = ensure_section_ids(markdown)
    md_bytes = markdown.encode("utf-8")
    storage.put_object(key, md_bytes)
    sha = hashlib.sha256(md_bytes).hexdigest()
    revision.draft_markdown_key = key
    revision.draft_content_sha256 = sha

    await record_event(
        db,
        actor_id=user.id,
        action="revision.draft.saved",
        resource_type="revision",
        resource_id=str(revision.id),
        payload={"content_sha256": sha},
    )
    await db.commit()
    return markdown, sha


async def update_revision_meta(
    db: AsyncSession,
    revision_id: uuid.UUID,
    data: RevisionMetaUpdate,
    user: User,
) -> Revision:
    revision = await get_revision(db, revision_id)
    if revision is None:
        raise HTTPException(status_code=404, detail="修订任务不存在")

    _assert_can_manage_revision(revision, user)

    if revision.state not in META_EDITABLE_STATES:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="仅在起草、改稿或发布审核阶段可修改修订信息",
        )

    if data.change_brief is None and data.target_version_label is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="至少提供 change_brief 或 target_version_label",
        )

    if data.change_brief is not None:
        revision.change_brief = data.change_brief.strip()
    if data.target_version_label is not None:
        revision.target_version_label = data.target_version_label.strip()

    await record_event(
        db,
        actor_id=user.id,
        action="revision.meta.updated",
        resource_type="revision",
        resource_id=str(revision.id),
        payload={
            "change_brief": revision.change_brief,
            "target_version_label": revision.target_version_label,
        },
    )
    await db.commit()
    await db.refresh(revision)
    return revision


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

    if (
        current_state == RevisionState.IN_CONSULTATION
        and target_state == RevisionState.IN_REVISION
    ):
        await workflow.assert_consultation_complete(revision_id, db)

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

    if target_state == RevisionState.IN_CONSULTATION:
        reviewer_rows = await db.execute(
            select(RevisionReviewer.user_id).where(
                RevisionReviewer.revision_id == revision_id,
            )
        )
        reviewer_ids = [row[0] for row in reviewer_rows.all()]
        if reviewer_ids:
            await notify_users(
                db,
                user_ids=reviewer_ids,
                message="修订任务已进入征求意见阶段，请提交评审意见。",
                revision_id=revision.id,
                policy_id=revision.policy_id,
            )

    if target_state == RevisionState.PENDING_PUBLISH:
        admin_rows = await db.execute(
            select(User.id).where(User.role == UserRole.POLICY_ADMIN, User.is_active.is_(True))
        )
        admin_ids = [row[0] for row in admin_rows.all()]
        if admin_ids:
            await notify_users(
                db,
                user_ids=admin_ids,
                message="修订任务已提交发布审核，请制度管理员复核并发布。",
                revision_id=revision.id,
                policy_id=revision.policy_id,
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
