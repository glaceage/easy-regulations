from __future__ import annotations

import hashlib
import json
import uuid
from pathlib import Path
from typing import Any

import yaml
from arq.worker import func
from botocore.exceptions import ClientError
from openai import AsyncOpenAI
from sqlalchemy import select

from apps.api.ai.client import get_llm_client
from apps.api.ai.suggestions import parse_comment_patch_suggestion, parse_draft_suggestions
from apps.api.config import get_settings
from apps.api.db.session import SessionLocal
from apps.api.models.comment import Comment
from apps.api.models.llm_suggestion import (
    LlmSuggestion,
    LlmSuggestionStatus,
)
from apps.api.models.revision import Revision
from apps.api.services.audit import record_event
from apps.api.services.sections import build_section_tree, extract_section_body
from apps.api.services.storage import StorageService

TEMPLATE_DIR = Path(__file__).resolve().parents[2] / "api" / "ai" / "templates"
DRAFT_TEMPLATE_PATH = TEMPLATE_DIR / "draft_v1.yaml"
COMMENT_PATCH_TEMPLATE_PATH = TEMPLATE_DIR / "comment_patch_v1.yaml"


def _load_template(path: Path) -> dict[str, str]:
    with path.open(encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    return {
        "system": data["system"].strip(),
        "user_template": data["user_template"].strip(),
    }


def load_draft_template() -> dict[str, str]:
    return _load_template(DRAFT_TEMPLATE_PATH)


def load_comment_patch_template() -> dict[str, str]:
    return _load_template(COMMENT_PATCH_TEMPLATE_PATH)


def compute_input_hash(*parts: str) -> str:
    payload = "\n---\n".join(parts)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _load_markdown(storage: StorageService, key: str) -> str:
    if not key:
        return ""
    try:
        return storage.get_bytes(key).decode("utf-8")
    except ClientError:
        return ""


async def call_draft_llm(
    client: AsyncOpenAI,
    *,
    change_brief: str,
    section_id: str,
    section_title: str,
    section_body: str,
    model_name: str,
) -> list[dict[str, Any]]:
    template = load_draft_template()
    user_message = template["user_template"].format(
        change_brief=change_brief,
        section_id=section_id,
        section_title=section_title,
        section_body=section_body or "（空）",
    )
    response = await client.chat.completions.create(
        model=model_name,
        temperature=0.2,
        messages=[
            {"role": "system", "content": template["system"]},
            {"role": "user", "content": user_message},
        ],
        response_format={"type": "json_object"},
    )
    content = response.choices[0].message.content or "[]"
    parsed = json.loads(content)
    if isinstance(parsed, dict):
        for key in ("suggestions", "items", "data"):
            if key in parsed and isinstance(parsed[key], list):
                return parsed[key]
        return [parsed]
    if isinstance(parsed, list):
        return parsed
    return []


async def call_comment_patch_llm(
    client: AsyncOpenAI,
    *,
    comment_body: str,
    section_id: str,
    section_title: str,
    section_body: str,
    model_name: str,
) -> list[dict[str, Any]]:
    template = load_comment_patch_template()
    user_message = template["user_template"].format(
        comment_body=comment_body,
        section_id=section_id,
        section_title=section_title,
        section_body=section_body or "（空）",
    )
    response = await client.chat.completions.create(
        model=model_name,
        temperature=0.2,
        messages=[
            {"role": "system", "content": template["system"]},
            {"role": "user", "content": user_message},
        ],
        response_format={"type": "json_object"},
    )
    content = response.choices[0].message.content or "[]"
    parsed = json.loads(content)
    if isinstance(parsed, dict):
        for key in ("suggestions", "items", "data"):
            if key in parsed and isinstance(parsed[key], list):
                return parsed[key]
        return [parsed]
    if isinstance(parsed, list):
        return parsed
    return []


def _section_title(section_tree: list[dict[str, Any]], section_id: str) -> str:
    for section in section_tree:
        if section["section_id"] == section_id:
            return section["title"]
    return section_id


async def comment_patch_task(ctx: dict[str, Any], comment_id: str) -> dict[str, Any]:
    cid = uuid.UUID(comment_id)
    settings = get_settings()
    storage = StorageService()
    client = get_llm_client()
    model_name = settings.xiaomi_model

    async with SessionLocal() as db:
        result = await db.execute(select(Comment).where(Comment.id == cid))
        comment = result.scalar_one_or_none()
        if comment is None:
            raise ValueError(f"Comment {comment_id} not found")

        rev_result = await db.execute(
            select(Revision).where(Revision.id == comment.revision_id)
        )
        revision = rev_result.scalar_one_or_none()
        if revision is None:
            raise ValueError(f"Revision for comment {comment_id} not found")

        markdown = _load_markdown(storage, revision.draft_markdown_key)
        section_tree = build_section_tree(markdown)
        section_id = comment.section_id
        section_title = _section_title(section_tree, section_id)
        section_body = extract_section_body(markdown, section_id)
        input_hash = compute_input_hash(
            comment.body,
            section_id,
            section_title,
            section_body,
            model_name,
        )

        raw_items = await call_comment_patch_llm(
            client,
            comment_body=comment.body,
            section_id=section_id,
            section_title=section_title,
            section_body=section_body,
            model_name=model_name,
        )
        item = parse_comment_patch_suggestion(raw_items)
        if item is None:
            await record_event(
                db,
                actor_id=revision.owner_user_id,
                action="llm.comment_patch.generated",
                resource_type="comment",
                resource_id=str(comment.id),
                payload={"suggestion_id": None, "section_id": section_id},
            )
            await db.commit()
            return {
                "comment_id": comment_id,
                "suggestion_id": None,
                "section_id": section_id,
            }

        suggestion = LlmSuggestion(
            revision_id=revision.id,
            section_id=item.section_id,
            action=item.action,
            suggested_markdown=item.suggested_markdown,
            rationale=item.rationale,
            status=LlmSuggestionStatus.PENDING,
            model_name=model_name,
            input_hash=input_hash,
        )
        db.add(suggestion)
        await db.flush()
        comment.llm_suggestion_id = suggestion.id

        await record_event(
            db,
            actor_id=revision.owner_user_id,
            action="llm.comment_patch.generated",
            resource_type="comment",
            resource_id=str(comment.id),
            payload={
                "suggestion_id": str(suggestion.id),
                "section_id": item.section_id,
            },
        )
        await db.commit()

    return {
        "comment_id": comment_id,
        "suggestion_id": str(suggestion.id),
        "section_id": item.section_id,
    }


async def generate_draft_task(ctx: dict[str, Any], revision_id: str) -> dict[str, Any]:
    rid = uuid.UUID(revision_id)
    settings = get_settings()
    storage = StorageService()
    client = get_llm_client()
    model_name = settings.xiaomi_model

    async with SessionLocal() as db:
        result = await db.execute(select(Revision).where(Revision.id == rid))
        revision = result.scalar_one_or_none()
        if revision is None:
            raise ValueError(f"Revision {revision_id} not found")

        markdown = _load_markdown(storage, revision.draft_markdown_key)
        section_tree = build_section_tree(markdown)
        created_ids: list[str] = []

        for section in section_tree:
            section_id = section["section_id"]
            section_title = section["title"]
            section_body = extract_section_body(markdown, section_id)
            input_hash = compute_input_hash(
                revision.change_brief,
                section_id,
                section_title,
                section_body,
                model_name,
            )

            raw_items = await call_draft_llm(
                client,
                change_brief=revision.change_brief,
                section_id=section_id,
                section_title=section_title,
                section_body=section_body,
                model_name=model_name,
            )
            items = parse_draft_suggestions(raw_items)
            if not items:
                continue

            for item in items:
                suggestion = LlmSuggestion(
                    revision_id=rid,
                    section_id=item.section_id,
                    action=item.action,
                    suggested_markdown=item.suggested_markdown,
                    rationale=item.rationale,
                    status=LlmSuggestionStatus.PENDING,
                    model_name=model_name,
                    input_hash=input_hash,
                )
                db.add(suggestion)
                await db.flush()
                created_ids.append(str(suggestion.id))

        await record_event(
            db,
            actor_id=revision.owner_user_id,
            action="llm.draft.generated",
            resource_type="revision",
            resource_id=str(revision.id),
            payload={"suggestion_count": len(created_ids), "section_count": len(section_tree)},
        )
        await db.commit()

    return {
        "revision_id": revision_id,
        "suggestion_count": len(created_ids),
        "section_count": len(section_tree),
    }


generate_draft_task = func(generate_draft_task, keep_result=3600)
comment_patch_task = func(comment_patch_task, keep_result=3600)
