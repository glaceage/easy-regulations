import shutil
import subprocess
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

SAMPLE_PANDOC_OUTPUT = """# 总则

## 目的

为规范考勤管理。
"""


@pytest.mark.skipif(shutil.which("pandoc") is None, reason="pandoc not installed")
def test_pandoc_available():
    result = subprocess.run(["pandoc", "--version"], capture_output=True, text=True)
    assert result.returncode == 0


@pytest.mark.asyncio
async def test_docx_to_markdown_task_adds_section_ids():
    revision_id = "00000000-0000-0000-0000-000000000001"
    docx_key = "policies/x/y/upload.docx"

    fake_revision = MagicMock()
    fake_revision.id = revision_id
    fake_revision.policy_id = "00000000-0000-0000-0000-000000000002"
    fake_revision.draft_markdown_key = "drafts/old.md"

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = fake_revision

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value=mock_result)
    mock_session.commit = AsyncMock()

    mock_session_ctx = AsyncMock()
    mock_session_ctx.__aenter__.return_value = mock_session
    mock_session_ctx.__aexit__.return_value = None

    mock_storage = MagicMock()
    mock_storage.get_bytes.return_value = b"PK fake docx"
    mock_storage.put_bytes.return_value = "policies/x/y/converted.md"

    with (
        patch("apps.worker.tasks.convert.SessionLocal", return_value=mock_session_ctx),
        patch("apps.worker.tasks.convert.StorageService", return_value=mock_storage),
        patch(
            "apps.worker.tasks.convert.run_pandoc_docx_to_gfm",
            return_value=SAMPLE_PANDOC_OUTPUT,
        ),
    ):
        from apps.worker.tasks.convert import docx_to_markdown_task

        result = await docx_to_markdown_task.coroutine({}, revision_id, docx_key)

    assert result["revision_id"] == revision_id
    assert result["draft_markdown_key"] == "policies/x/y/converted.md"
    assert result["section_count"] == 2

    saved_md = mock_storage.put_bytes.call_args[0][0].decode("utf-8")
    assert "{#sec-" in saved_md
    assert fake_revision.draft_markdown_key == "policies/x/y/converted.md"
    assert fake_revision.draft_content_sha256
    mock_session.commit.assert_awaited_once()
