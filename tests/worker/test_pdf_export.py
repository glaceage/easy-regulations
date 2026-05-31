from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from apps.api.services.export import markdown_to_html


def test_markdown_to_html_includes_title():
    html = markdown_to_html("# 制度\n\n内容", title="考勤办法", version="2.0")
    assert "考勤办法" in html
    assert "2.0" in html
    assert "制度" in html
    assert "内容" in html


def test_markdown_to_html_has_chinese_css():
    html = markdown_to_html("内容", title="测试", version="1.0")
    assert "Noto Sans CJK SC" in html
    assert 'lang="zh-CN"' in html


def test_markdown_to_html_strips_section_anchor_from_headings():
    html = markdown_to_html("# 总则 {#sec-zongze}\n\n正文。", title="测试", version="1.0")
    assert "总则" in html
    assert "sec-zongze" not in html
    assert "{#" not in html


def test_html_to_pdf_raises_clear_import_error(monkeypatch):
    import builtins

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "weasyprint":
            raise ImportError("no weasyprint")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    from apps.api.services.export import html_to_pdf

    with pytest.raises(ImportError, match="WeasyPrint is required"):
        html_to_pdf("<html></html>")


@pytest.mark.asyncio
async def test_export_pdf_task_uploads_pdf():
    revision_id = "00000000-0000-0000-0000-000000000001"
    fake_revision = MagicMock()
    fake_revision.id = revision_id
    fake_revision.policy_id = "00000000-0000-0000-0000-000000000002"
    fake_revision.draft_markdown_key = "drafts/test.md"
    fake_revision.target_version_label = "2.0"

    fake_policy = MagicMock()
    fake_policy.title = "考勤办法"

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.side_effect = [fake_revision, fake_policy]

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value=mock_result)

    mock_session_ctx = AsyncMock()
    mock_session_ctx.__aenter__.return_value = mock_session
    mock_session_ctx.__aexit__.return_value = None

    mock_storage = MagicMock()
    mock_storage.get_bytes.return_value = "# 制度\n\n内容".encode()
    mock_storage.put_bytes.return_value = "policies/x/y/out.pdf"

    with (
        patch("apps.worker.tasks.convert.SessionLocal", return_value=mock_session_ctx),
        patch("apps.worker.tasks.convert.StorageService", return_value=mock_storage),
        patch("apps.worker.tasks.convert.html_to_pdf", return_value=b"%PDF-1.4"),
    ):
        from apps.worker.tasks.convert import export_pdf_task

        coroutine = export_pdf_task.coroutine
        result = await coroutine({}, revision_id)

    assert result["pdf_key"] == "policies/x/y/out.pdf"
    assert result["revision_id"] == revision_id
    mock_storage.put_bytes.assert_called_once()
