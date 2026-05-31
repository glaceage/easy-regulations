from __future__ import annotations

from typing import Any

from apps.api.config import Settings, get_settings

DEV_MOCK_MODEL = "dev-mock"


def llm_dev_mock_enabled(settings: Settings | None = None) -> bool:
    settings = settings or get_settings()
    if settings.llm_dev_mock:
        return True
    return settings.auth_mode == "dev" and not settings.xiaomi_api_key.strip()


def mock_draft_suggestions(
    *,
    change_brief: str,
    section_id: str,
    section_title: str,
    section_body: str,
) -> list[dict[str, Any]]:
    brief = change_brief.strip() or "根据业务需要更新本章节表述。"
    base = section_body.strip() or f"### {section_title}\n\n（原章节内容为空）"
    suggested = (
        f"{base}\n\n"
        f"> **【开发模拟】** 依据修订说明「{brief[:120]}」对本节提出的修改建议。"
    )
    return [
        {
            "section_id": section_id,
            "action": "replace",
            "suggested_markdown": suggested,
            "rationale": "开发环境模拟建议：未配置 XIAOMI_API_KEY。在 .env 中填写密钥后将调用真实 LLM。",
        }
    ]


def mock_comment_patch_suggestions(
    *,
    comment_body: str,
    section_id: str,
    section_title: str,
    section_body: str,
) -> list[dict[str, Any]]:
    base = section_body.strip() or f"### {section_title}\n\n（原章节内容为空）"
    suggested = (
        f"{base}\n\n"
        f"> **【开发模拟】** 针对意见「{comment_body.strip()[:200]}」的修改建议。"
    )
    return [
        {
            "section_id": section_id,
            "action": "replace",
            "suggested_markdown": suggested,
            "rationale": "开发环境模拟建议：未配置 XIAOMI_API_KEY。",
        }
    ]
