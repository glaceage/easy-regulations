import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.db.session import get_db
from apps.api.models.user import User
from apps.api.schemas.notification import NotificationResponse
from apps.api.schemas.reviewer import ReviewerAssignRequest, ReviewerResponse
from apps.api.services import reviewers as reviewer_service
from apps.api.services.auth import get_current_user
from apps.api.services import notifications as notification_service

revision_router = APIRouter(prefix="/api/revisions", tags=["reviewers"])
notification_router = APIRouter(prefix="/api/notifications", tags=["notifications"])


@revision_router.get("/{revision_id}/reviewers", response_model=list[ReviewerResponse])
async def list_revision_reviewers(
    revision_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _ = current_user
    return await reviewer_service.list_reviewers(db, revision_id)


@revision_router.post(
    "/{revision_id}/reviewers",
    response_model=ReviewerResponse,
    status_code=201,
)
async def assign_revision_reviewer(
    revision_id: uuid.UUID,
    body: ReviewerAssignRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await reviewer_service.assign_reviewer(db, revision_id, body, current_user)


@revision_router.delete("/{revision_id}/reviewers/{reviewer_id}", status_code=204)
async def remove_revision_reviewer(
    revision_id: uuid.UUID,
    reviewer_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await reviewer_service.remove_reviewer(db, revision_id, reviewer_id, current_user)


@notification_router.get("", response_model=list[NotificationResponse])
async def list_my_notifications(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await notification_service.list_notifications(db, current_user.id)
