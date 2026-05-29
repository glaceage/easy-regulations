from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, Field, field_validator

from apps.api.models.llm_suggestion import LlmSuggestionAction


class DraftSuggestionItem(BaseModel):
    section_id: str = Field(min_length=1, max_length=64)
    action: LlmSuggestionAction
    suggested_markdown: str = ""
    rationale: str = ""

    @field_validator("action", mode="before")
    @classmethod
    def normalize_action(cls, value: Any) -> Any:
        if isinstance(value, str):
            return value.lower()
        return value


def parse_draft_suggestions(raw: list[Any]) -> list[DraftSuggestionItem]:
    return [DraftSuggestionItem.model_validate(item) for item in raw]


def _find_section_span(markdown: str, section_id: str) -> tuple[int, int, re.Match[str]] | None:
    pattern = re.compile(
        rf"^#{{1,6}}\s+.+?\{{#{re.escape(section_id)}\}}\s*$",
        re.MULTILINE,
    )
    match = pattern.search(markdown)
    if not match:
        return None
    start = match.start()
    body_start = match.end()
    next_heading = re.search(r"^#{1,6}\s+", markdown[body_start:], re.MULTILINE)
    end = body_start + next_heading.start() if next_heading else len(markdown)
    return start, end, match


def apply_section_patch(
    markdown: str,
    section_id: str,
    action: LlmSuggestionAction | str,
    suggested_markdown: str,
) -> str:
    action_value = action.value if isinstance(action, LlmSuggestionAction) else action.lower()
    span = _find_section_span(markdown, section_id)
    if span is None:
        if action_value == "insert" and suggested_markdown.strip():
            separator = "\n\n" if markdown and not markdown.endswith("\n") else "\n"
            return markdown + separator + suggested_markdown.strip() + "\n"
        return markdown

    start, end, match = span
    body = markdown[match.end() : end]

    if action_value == "delete":
        prefix = markdown[:start]
        suffix = markdown[end:]
        if prefix and not prefix.endswith("\n\n"):
            prefix = prefix.rstrip("\n") + "\n\n"
        return prefix + suffix.lstrip("\n")

    if action_value == "insert":
        insertion = suggested_markdown.strip()
        if not insertion:
            return markdown
        new_body = body.rstrip("\n") + "\n\n" + insertion + "\n"
        return markdown[: match.end()] + new_body + markdown[end:]

    new_body = "\n" + suggested_markdown.strip() + "\n" if suggested_markdown.strip() else "\n"
    return markdown[: match.end()] + new_body + markdown[end:]
