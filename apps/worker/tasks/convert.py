from __future__ import annotations

import hashlib
import os
import subprocess
import tempfile
import uuid
from typing import Any

from arq.worker import func
from botocore.exceptions import ClientError
from sqlalchemy import select

from apps.api.db.session import SessionLocal
from apps.api.models.policy import Policy
from apps.api.models.revision import Revision
from apps.api.services.export import html_to_pdf, markdown_to_html
from apps.api.services.sections import ensure_section_ids
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


def run_pandoc_docx_to_gfm(docx_bytes: bytes) -> str:
    with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as tmp:
        tmp.write(docx_bytes)
        tmp_path = tmp.name
    try:
        result = subprocess.run(
            ["pandoc", "-f", "docx", "-t", "gfm", tmp_path],
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout
    finally:
        os.unlink(tmp_path)


async def docx_to_markdown_task(
    ctx: dict[str, Any], revision_id: str, docx_key: str
) -> dict[str, str | int]:
    rid = uuid.UUID(revision_id)
    storage = StorageService()
    docx_bytes = storage.get_bytes(docx_key)
    raw_markdown = run_pandoc_docx_to_gfm(docx_bytes)
    markdown, section_tree = ensure_section_ids(raw_markdown)
    md_bytes = markdown.encode("utf-8")

    async with SessionLocal() as db:
        result = await db.execute(select(Revision).where(Revision.id == rid))
        revision = result.scalar_one_or_none()
        if revision is None:
            raise ValueError(f"Revision {revision_id} not found")

        prefix = f"policies/{revision.policy_id}/{revision.id}/"
        md_key = storage.put_bytes(md_bytes, suffix=".md", prefix=prefix)
        revision.draft_markdown_key = md_key
        revision.draft_content_sha256 = hashlib.sha256(md_bytes).hexdigest()
        await db.commit()

    return {
        "revision_id": revision_id,
        "draft_markdown_key": md_key,
        "section_count": len(section_tree),
    }


export_pdf_task = func(export_pdf_task, keep_result=3600)
docx_to_markdown_task = func(docx_to_markdown_task, keep_result=3600)
