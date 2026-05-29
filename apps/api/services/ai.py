from __future__ import annotations

import hashlib
import uuid

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.ai.suggestions import apply_section_patch
from apps.api.models.llm_suggestion import LlmSuggestion, LlmSuggestionStatus
from apps.api.models.revision import Revision
from apps.api.models.user import User, UserRole
from apps.api.services.audit import record_event
from apps.api.services.storage import StorageService


async def list_suggestions(db: AsyncSession, revision_id: uuid.UUID) -> list[LlmSuggestion]:
    result = await db.execute(
        select(LlmSuggestion)
        .where(LlmSuggestion.revision_id == revision_id)
        .order_by(LlmSuggestion.created_at.asc())
    )
    return list(result.scalars().all())


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

    storage = StorageService()
    markdown = storage.get_bytes(revision.draft_markdown_key).decode("utf-8")
    updated = apply_section_patch(
        markdown,
        suggestion.section_id,
        suggestion.action,
        suggestion.suggested_markdown,
    )
    md_bytes = updated.encode("utf-8")
    prefix = f"policies/{revision.policy_id}/{revision.id}/"
    md_key = storage.put_bytes(md_bytes, suffix=".md", prefix=prefix)
    revision.draft_markdown_key = md_key
    revision.draft_content_sha256 = hashlib.sha256(md_bytes).hexdigest()

    suggestion.status = LlmSuggestionStatus.ACCEPTED
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
