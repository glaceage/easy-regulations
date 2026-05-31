import uuid

from botocore.exceptions import ClientError
from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.db.session import get_db
from apps.api.models.user import User
from apps.api.schemas.export import ImportDocxResponse
from apps.api.schemas.revision import (
    DraftMarkdownResponse,
    DraftMarkdownUpdate,
    PublishResponse,
    RevisionCreate,
    RevisionResponse,
    TransitionRequest,
)
from apps.api.services import jobs as jobs_service
from apps.api.services import revisions as revision_service
from apps.api.services.auth import get_current_user
from apps.api.services.storage import StorageService

router = APIRouter(prefix="/api/revisions", tags=["revisions"])

_CONTENT_TYPES = {
    ".md": "text/markdown; charset=utf-8",
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


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


@router.post("/{revision_id}/publish", response_model=PublishResponse)
async def publish_revision(
    revision_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await revision_service.publish_revision(db, revision_id, current_user)


@router.get("/{revision_id}/draft-markdown", response_model=DraftMarkdownResponse)
async def get_draft_markdown(
    revision_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _ = current_user
    markdown, sha = await revision_service.get_draft_markdown(db, revision_id)
    return DraftMarkdownResponse(markdown=markdown, content_sha256=sha)


@router.put("/{revision_id}/draft-markdown", response_model=DraftMarkdownResponse)
async def save_draft_markdown(
    revision_id: uuid.UUID,
    body: DraftMarkdownUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    markdown, sha = await revision_service.save_draft_markdown(
        db, revision_id, body.markdown, current_user
    )
    return DraftMarkdownResponse(markdown=markdown, content_sha256=sha)


@router.get("/{revision_id}/files")
async def download_revision_file(
    revision_id: uuid.UUID,
    key: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _ = current_user
    revision = await revision_service.get_revision(db, revision_id)
    if revision is None:
        raise HTTPException(status_code=404, detail="修订任务不存在")

    allowed_prefixes = (
        f"drafts/{revision.id}",
        f"policies/{revision.policy_id}/",
    )
    if not key.startswith(allowed_prefixes):
        raise HTTPException(status_code=403, detail="无权访问该文件")

    storage = StorageService()
    try:
        data = storage.get_bytes(key)
    except ClientError as exc:
        raise HTTPException(status_code=404, detail="文件不存在") from exc

    suffix = key[key.rfind(".") :] if "." in key else ""
    media_type = _CONTENT_TYPES.get(suffix, "application/octet-stream")
    return Response(content=data, media_type=media_type)


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


@router.post(
    "/{revision_id}/import-docx",
    response_model=ImportDocxResponse,
    status_code=202,
)
async def import_docx(
    revision_id: uuid.UUID,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    revision = await revision_service.get_revision(db, revision_id)
    if revision is None:
        raise HTTPException(status_code=404, detail="修订任务不存在")

    revision_service._assert_can_manage_revision(revision, current_user)

    if not file.filename or not file.filename.lower().endswith(".docx"):
        raise HTTPException(status_code=400, detail="请上传 .docx 文件")

    docx_bytes = await file.read()
    if not docx_bytes:
        raise HTTPException(status_code=400, detail="文件内容为空")

    storage = StorageService()
    prefix = f"policies/{revision.policy_id}/{revision.id}/"
    docx_key = storage.put_bytes(docx_bytes, suffix=".docx", prefix=prefix)

    job_id = await jobs_service.enqueue_docx_import(str(revision_id), docx_key)
    return ImportDocxResponse(job_id=job_id, docx_key=docx_key)
