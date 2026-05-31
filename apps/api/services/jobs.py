from __future__ import annotations

import os
from typing import Any

from arq import create_pool
from arq.connections import RedisSettings
from arq.jobs import DeserializationError, Job, JobStatus

from apps.api.config import Settings, get_settings

EXPORT_PDF_TASK = "export_pdf_task"
DOCX_TO_MARKDOWN_TASK = "docx_to_markdown_task"
GENERATE_DRAFT_TASK = "generate_draft_task"
COMMENT_PATCH_TASK = "comment_patch_task"


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


async def enqueue_comment_patch(comment_id: str, settings: Settings | None = None) -> str:
    settings = settings or get_settings()

    if _sync_jobs_enabled(settings):
        from apps.worker.tasks.llm import comment_patch_task

        await comment_patch_task.coroutine({}, comment_id)
        return f"sync-{comment_id}"

    redis_settings = RedisSettings.from_dsn(settings.redis_url)
    pool = await create_pool(redis_settings)
    try:
        job = await pool.enqueue_job(COMMENT_PATCH_TASK, comment_id)
        if job is None:
            raise RuntimeError("Failed to enqueue comment patch job")
        return job.job_id
    finally:
        await pool.close()


async def get_job_status(job_id: str, settings: Settings | None = None) -> dict[str, Any]:
    settings = settings or get_settings()

    if job_id.startswith("sync-"):
        # Sync jobs encode either a revision_id or a comment_id in the suffix; we
        # cannot tell which here, so expose a neutral id rather than mislabeling it.
        return {
            "job_id": job_id,
            "status": JobStatus.complete.value,
            "result": {"id": job_id.removeprefix("sync-"), "sync": True},
            "error": None,
        }

    redis_settings = RedisSettings.from_dsn(settings.redis_url)
    try:
        pool = await create_pool(redis_settings)
    except Exception as exc:  # noqa: BLE001 - status poll must not 500 on queue outage
        return {
            "job_id": job_id,
            "status": "unavailable",
            "result": None,
            "error": f"无法连接任务队列：{exc}",
        }

    try:
        job = Job(job_id, pool)
        job_state = await job.status()
        payload: dict[str, Any] = {
            "job_id": job_id,
            "status": job_state.value,
            "result": None,
            "error": None,
        }

        if job_state == JobStatus.complete:
            try:
                info = await job.result_info()
            except DeserializationError:
                payload["error"] = "后台任务执行失败"
                return payload

            if info is not None:
                if info.success:
                    payload["result"] = info.result
                else:
                    result = info.result
                    payload["error"] = str(result) if result is not None else "后台任务执行失败"
        return payload
    finally:
        await pool.close()
