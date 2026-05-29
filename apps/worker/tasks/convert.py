from __future__ import annotations

import uuid
from typing import Any

from arq.worker import func
from botocore.exceptions import ClientError
from sqlalchemy import select

from apps.api.db.session import SessionLocal
from apps.api.models.policy import Policy
from apps.api.models.revision import Revision
from apps.api.services.export import html_to_pdf, markdown_to_html
from apps.api.services.storage import StorageService


async def _load_revision_context(revision_id: uuid.UUID) -> tuple[Revision, str, str]:
    async with SessionLocal() as db:
        result = await db.execute(select(Revision).where(Revision.id == revision_id))
        revision = result.scalar_one_or_none()
        if revision is None:
            raise ValueError(f"Revision {revision_id} not found")

        policy_result = await db.execute(select(Policy).where(Policy.id == revision.policy_id))
        policy = policy_result.scalar_one_or_none()
        title = policy.title if policy else "制度文档"
        version = revision.target_version_label or "draft"
        return revision, title, version


def _load_markdown(storage: StorageService, key: str) -> str:
    if not key:
        return ""
    try:
        return storage.get_bytes(key).decode("utf-8")
    except ClientError:
        return ""


async def export_pdf_task(ctx: dict[str, Any], revision_id: str) -> dict[str, str]:
    rid = uuid.UUID(revision_id)
    revision, title, version = await _load_revision_context(rid)

    storage = StorageService()
    markdown = _load_markdown(storage, revision.draft_markdown_key)
    html_content = markdown_to_html(markdown, title=title, version=version)
    pdf_bytes = html_to_pdf(html_content)

    prefix = f"policies/{revision.policy_id}/{revision.id}/"
    pdf_key = storage.put_bytes(pdf_bytes, suffix=".pdf", prefix=prefix)
    return {"pdf_key": pdf_key, "revision_id": revision_id}


export_pdf_task = func(export_pdf_task, keep_result=3600)
