from __future__ import annotations

import hashlib
import uuid

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.ai.suggestions import apply_section_patch
from apps.api.models.comment import Comment, CommentStatus
from apps.api.models.llm_suggestion import LlmSuggestion, LlmSuggestionStatus
from apps.api.models.revision import Revision, RevisionState
from apps.api.models.user import User, UserRole
from apps.api.services import jobs as jobs_service
from apps.api.services import revisions as revision_service
from apps.api.services.audit import record_event
from apps.api.services.storage import StorageService


async def list_suggestions(db: AsyncSession, revision_id: uuid.UUID) -> list[LlmSuggestion]:
    result = await db.execute(
        select(LlmSuggestion)
        .where(LlmSuggestion.revision_id == revision_id)
        .order_by(LlmSuggestion.created_at.asc())
    )
    return list(result.scalars().all())


async def enqueue_comment_patch(
    db: AsyncSession,
    comment_id: uuid.UUID,
    user: User,
) -> str:
    result = await db.execute(select(Comment).where(Comment.id == comment_id))
    comment = result.scalar_one_or_none()
    if comment is None:
        raise HTTPException(status_code=404, detail="意见不存在")

    revision = await revision_service.get_revision(db, comment.revision_id)
    if revision is None:
        raise HTTPException(status_code=404, detail="修订任务不存在")

    revision_service._assert_can_manage_revision(revision, user)
    return await jobs_service.enqueue_comment_patch(str(comment_id))


async def accept_suggestion(
    db: AsyncSession,
    suggestion_id: uuid.UUID,
    user: User,
) -> LlmSuggestion:
    result = await db.execute(select(LlmSuggestion).where(LlmSuggestion.id == suggestion_id))
    suggestion = result.scalar_one_or_none()
    if suggestion is None:
        raise HTTPException(status_code=404, detail="AI 建议不存在")

    if suggestion.status != LlmSuggestionStatus.PENDING:
        raise HTTPException(status_code=409, detail="该建议已处理")

    rev_result = await db.execute(select(Revision).where(Revision.id == suggestion.revision_id))
    revision = rev_result.scalar_one_or_none()
    if revision is None:
        raise HTTPException(status_code=404, detail="修订任务不存在")

    if (
        user.role not in {UserRole.POLICY_ADMIN, UserRole.SYS_ADMIN}
        and revision.owner_user_id != user.id
    ):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="权限不足")

    if revision.state not in {RevisionState.DRAFT, RevisionState.IN_REVISION}:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="仅在起草或改稿阶段可采纳 AI 建议",
        )

    storage = StorageService()
    draft_key = revision.draft_markdown_key or f"drafts/{revision.id}.md"
    markdown = revision_service._load_draft_markdown(storage, draft_key)
    updated = apply_section_patch(
        markdown,
        suggestion.section_id,
        suggestion.action,
        suggestion.suggested_markdown,
    )
    md_bytes = updated.encode("utf-8")
    storage.put_object(draft_key, md_bytes)
    revision.draft_markdown_key = draft_key
    revision.draft_content_sha256 = hashlib.sha256(md_bytes).hexdigest()

    suggestion.status = LlmSuggestionStatus.ACCEPTED

    comment_result = await db.execute(
        select(Comment).where(Comment.llm_suggestion_id == suggestion.id)
    )
    linked_comment = comment_result.scalar_one_or_none()
    if linked_comment is not None:
        linked_comment.status = CommentStatus.ACCEPTED

    await record_event(
        db,
        actor_id=user.id,
        action="llm.suggestion.accepted",
        resource_type="llm_suggestion",
        resource_id=str(suggestion.id),
        payload={
            "revision_id": str(revision.id),
            "section_id": suggestion.section_id,
            "action": suggestion.action.value,
        },
    )
    await db.commit()
    await db.refresh(suggestion)
    return suggestion
