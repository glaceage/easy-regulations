from __future__ import annotations

import os
from typing import Any

from arq import create_pool
from arq.connections import RedisSettings
from arq.jobs import Job, JobStatus

from apps.api.config import Settings, get_settings

EXPORT_PDF_TASK = "export_pdf_task"
DOCX_TO_MARKDOWN_TASK = "docx_to_markdown_task"
GENERATE_DRAFT_TASK = "generate_draft_task"


def _sync_jobs_enabled(settings: Settings) -> bool:
    return settings.auth_mode == "dev" and os.environ.get("SYNC_JOBS") == "1"


async def enqueue_export_pdf(revision_id: str, settings: Settings | None = None) -> str:
    settings = settings or get_settings()

    if _sync_jobs_enabled(settings):
        from apps.worker.tasks.convert import export_pdf_task

        await export_pdf_task.coroutine({}, revision_id)
        return f"sync-{revision_id}"

    redis_settings = RedisSettings.from_dsn(settings.redis_url)
    pool = await create_pool(redis_settings)
    try:
        job = await pool.enqueue_job(EXPORT_PDF_TASK, revision_id)
        if job is None:
            raise RuntimeError("Failed to enqueue export job")
        return job.job_id
    finally:
        await pool.close()


async def enqueue_docx_import(
    revision_id: str, docx_key: str, settings: Settings | None = None
) -> str:
    settings = settings or get_settings()

    if _sync_jobs_enabled(settings):
        from apps.worker.tasks.convert import docx_to_markdown_task

        await docx_to_markdown_task.coroutine({}, revision_id, docx_key)
        return f"sync-{revision_id}"

    redis_settings = RedisSettings.from_dsn(settings.redis_url)
    pool = await create_pool(redis_settings)
    try:
        job = await pool.enqueue_job(DOCX_TO_MARKDOWN_TASK, revision_id, docx_key)
        if job is None:
            raise RuntimeError("Failed to enqueue docx import job")
        return job.job_id
    finally:
        await pool.close()


async def enqueue_generate_draft(revision_id: str, settings: Settings | None = None) -> str:
    settings = settings or get_settings()

    if _sync_jobs_enabled(settings):
        from apps.worker.tasks.llm import generate_draft_task

        await generate_draft_task.coroutine({}, revision_id)
        return f"sync-{revision_id}"

    redis_settings = RedisSettings.from_dsn(settings.redis_url)
    pool = await create_pool(redis_settings)
    try:
        job = await pool.enqueue_job(GENERATE_DRAFT_TASK, revision_id)
        if job is None:
            raise RuntimeError("Failed to enqueue draft generation job")
        return job.job_id
    finally:
        await pool.close()


async def get_job_status(job_id: str, settings: Settings | None = None) -> dict[str, Any]:
    settings = settings or get_settings()

    if job_id.startswith("sync-"):
        revision_id = job_id.removeprefix("sync-")
        return {
            "job_id": job_id,
            "status": JobStatus.complete.value,
            "result": {"revision_id": revision_id, "sync": True},
            "error": None,
        }

    redis_settings = RedisSettings.from_dsn(settings.redis_url)
    pool = await create_pool(redis_settings)
    try:
        job = Job(job_id, pool)
        status = await job.status()
        payload: dict[str, Any] = {
            "job_id": job_id,
            "status": status.value,
            "result": None,
            "error": None,
        }

        if status == JobStatus.complete:
            info = await job.result_info()
            if info is not None:
                if info.success:
                    payload["result"] = info.result
                else:
                    result = info.result
                    payload["error"] = str(result) if result is not None else "Job failed"
        return payload
    finally:
        await pool.close()
