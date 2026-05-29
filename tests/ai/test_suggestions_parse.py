import pytest
from pydantic import ValidationError

from apps.api.ai.suggestions import apply_section_patch, parse_draft_suggestions
from apps.api.models.llm_suggestion import LlmSuggestionAction


def test_parse_draft_suggestions_valid():
    raw = [
        {
            "section_id": "sec-1",
            "action": "replace",
            "suggested_markdown": "新文本",
            "rationale": "说明",
        }
    ]
    result = parse_draft_suggestions(raw)
    assert result[0].section_id == "sec-1"
    assert result[0].action == LlmSuggestionAction.REPLACE
    assert result[0].suggested_markdown == "新文本"


def test_parse_draft_suggestions_normalizes_action_case():
    raw = [
        {
            "section_id": "sec-2",
            "action": "INSERT",
            "suggested_markdown": "追加",
            "rationale": "",
        }
    ]
    result = parse_draft_suggestions(raw)
    assert result[0].action == LlmSuggestionAction.INSERT


def test_parse_draft_suggestions_rejects_invalid_action():
    raw = [{"section_id": "sec-1", "action": "noop", "suggested_markdown": "", "rationale": ""}]
    with pytest.raises(ValidationError):
        parse_draft_suggestions(raw)


def test_apply_section_patch_replace():
    markdown = "# 总则 {#sec-zongze}\n\n旧内容。\n\n## 目的 {#sec-mudi}\n\n目的说明。\n"
    updated = apply_section_patch(markdown, "sec-zongze", "replace", "新内容。")
    assert "新内容。" in updated
    assert "旧内容。" not in updated
    assert "## 目的 {#sec-mudi}" in updated


def test_apply_section_patch_delete():
    markdown = "# 总则 {#sec-zongze}\n\n旧内容。\n\n## 目的 {#sec-mudi}\n\n目的说明。\n"
    updated = apply_section_patch(markdown, "sec-zongze", "delete", "")
    assert "sec-zongze" not in updated
    assert "## 目的 {#sec-mudi}" in updated
