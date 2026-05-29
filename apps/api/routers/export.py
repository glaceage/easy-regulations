import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.db.session import get_db
from apps.api.models.user import User
from apps.api.schemas.export import JobStatusResponse, PublishRequestResponse
from apps.api.services import jobs as jobs_service
from apps.api.services import revisions as revision_service
from apps.api.services.auth import get_current_user

router = APIRouter(tags=["export"])


@router.post(
    "/api/revisions/{revision_id}/publish-request",
    response_model=PublishRequestResponse,
    status_code=202,
)
async def request_publish_pdf(
    revision_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    revision = await revision_service.get_revision(db, revision_id)
    if revision is None:
        raise HTTPException(status_code=404, detail="修订任务不存在")

    revision_service._assert_can_manage_revision(revision, current_user)

    job_id = await jobs_service.enqueue_export_pdf(str(revision_id))
    return PublishRequestResponse(job_id=job_id)


@router.get("/api/jobs/{job_id}", response_model=JobStatusResponse)
async def get_job_status(
    job_id: str,
    current_user: User = Depends(get_current_user),
):
    _ = current_user
    status = await jobs_service.get_job_status(job_id)
    return JobStatusResponse(**status)
