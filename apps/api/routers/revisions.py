import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.db.session import get_db
from apps.api.models.user import User
from apps.api.schemas.revision import RevisionCreate, RevisionResponse, TransitionRequest
from apps.api.services import revisions as revision_service
from apps.api.services.auth import get_current_user

router = APIRouter(prefix="/api/revisions", tags=["revisions"])


@router.post("", response_model=RevisionResponse, status_code=201)
async def create_revision(
    body: RevisionCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await revision_service.create_revision(db, body, current_user)


@router.get("/{revision_id}", response_model=RevisionResponse)
async def get_revision(
    revision_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _ = current_user
    revision = await revision_service.get_revision(db, revision_id)
    if revision is None:
        raise HTTPException(status_code=404, detail="修订任务不存在")
    return revision


@router.post("/{revision_id}/transition", response_model=RevisionResponse)
async def transition_revision(
    revision_id: uuid.UUID,
    body: TransitionRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await revision_service.transition_revision(
        db, revision_id, body.target_state, current_user
    )
