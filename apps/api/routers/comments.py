import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.db.session import get_db
from apps.api.models.user import User
from apps.api.schemas.ai import DraftJobResponse
from apps.api.schemas.comment import CommentCreate, CommentResponse, CommentUpdate
from apps.api.services import ai as ai_service
from apps.api.services import comments as comment_service
from apps.api.services.auth import get_current_user

revision_router = APIRouter(prefix="/api/revisions", tags=["comments"])
comment_router = APIRouter(prefix="/api/comments", tags=["comments"])


@revision_router.post("/{revision_id}/comments", response_model=CommentResponse, status_code=201)
async def create_revision_comment(
    revision_id: uuid.UUID,
    body: CommentCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await comment_service.create_comment(db, revision_id, body, current_user)


@revision_router.get("/{revision_id}/comments", response_model=list[CommentResponse])
async def list_revision_comments(
    revision_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _ = current_user
    return await comment_service.list_comments(db, revision_id)


@comment_router.patch("/{comment_id}", response_model=CommentResponse)
async def update_comment(
    comment_id: uuid.UUID,
    body: CommentUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await comment_service.update_comment(db, comment_id, body, current_user)


@comment_router.post(
    "/{comment_id}/ai/patch",
    response_model=DraftJobResponse,
    status_code=202,
)
async def enqueue_comment_patch(
    comment_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    job_id = await ai_service.enqueue_comment_patch(db, comment_id, current_user)
    return DraftJobResponse(job_id=job_id)
