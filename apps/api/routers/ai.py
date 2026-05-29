import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.db.session import get_db
from apps.api.models.user import User
from apps.api.schemas.ai import DraftJobResponse, LlmSuggestionResponse
from apps.api.services import ai as ai_service
from apps.api.services import jobs as jobs_service
from apps.api.services import revisions as revision_service
from apps.api.services.auth import get_current_user

router = APIRouter(tags=["ai"])


@router.post(
    "/api/revisions/{revision_id}/ai/draft",
    response_model=DraftJobResponse,
    status_code=202,
)
async def enqueue_draft_generation(
    revision_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    revision = await revision_service.get_revision(db, revision_id)
    if revision is None:
        raise HTTPException(status_code=404, detail="修订任务不存在")

    revision_service._assert_can_manage_revision(revision, current_user)

    job_id = await jobs_service.enqueue_generate_draft(str(revision_id))
    return DraftJobResponse(job_id=job_id)


@router.get(
    "/api/revisions/{revision_id}/ai/suggestions",
    response_model=list[LlmSuggestionResponse],
)
async def list_revision_suggestions(
    revision_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _ = current_user
    revision = await revision_service.get_revision(db, revision_id)
    if revision is None:
        raise HTTPException(status_code=404, detail="修订任务不存在")

    suggestions = await ai_service.list_suggestions(db, revision_id)
    return suggestions


@router.post(
    "/api/ai/suggestions/{suggestion_id}/accept",
    response_model=LlmSuggestionResponse,
)
async def accept_suggestion(
    suggestion_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await ai_service.accept_suggestion(db, suggestion_id, current_user)
