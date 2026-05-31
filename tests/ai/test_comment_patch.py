import hashlib
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from passlib.context import CryptContext
from sqlalchemy import JSON, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from apps.api.db.session import get_db
from apps.api.main import create_app
from apps.api.models.audit import AuditEvent
from apps.api.models.base import Base
from apps.api.models.comment import Comment, CommentStatus
from apps.api.models.llm_suggestion import (
    LlmSuggestion,
    LlmSuggestionAction,
    LlmSuggestionStatus,
)
from apps.api.models.policy import Policy, PolicyVersion
from apps.api.models.revision import Revision, RevisionState
from apps.api.models.revision_reviewer import RevisionReviewer
from apps.api.models.user import User, UserRole
from apps.worker.tasks.llm import comment_patch_task

pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")

TEST_TABLES = [
    User.__table__,
    Policy.__table__,
    PolicyVersion.__table__,
    Revision.__table__,
    Comment.__table__,
    RevisionReviewer.__table__,
    AuditEvent.__table__,
    LlmSuggestion.__table__,
]

SAMPLE_MARKDOWN = """# 总则 {#sec-zongze}

旧总则内容。

## 目的 {#sec-mudi}

旧目的内容。
"""

MOCK_LLM_RESPONSE = [
    {
        "section_id": "sec-zongze",
        "action": "replace",
        "suggested_markdown": "新总则内容。",
        "rationale": "回应审阅意见",
    }
]


def _patch_jsonb_for_sqlite() -> None:
    for table in TEST_TABLES:
        for column in table.columns:
            if isinstance(column.type, JSONB):
                column.type = JSON()


@pytest.fixture
async def patch_client():
    _patch_jsonb_for_sqlite()
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(lambda conn: Base.metadata.create_all(conn, tables=TEST_TABLES))

    owner_id = uuid.uuid4()
    policy_id = uuid.uuid4()
    base_version_id = uuid.uuid4()
    revision_id = uuid.uuid4()
    comment_id = uuid.uuid4()

    async with session_factory() as session:
        session.add(
            User(
                id=owner_id,
                username="owner1",
                display_name="经办人",
                department="人力部",
                role=UserRole.OWNER,
                password_hash=pwd.hash("secret"),
            )
        )
        session.add(
            Policy(
                id=policy_id,
                code="HR-100",
                title="考勤办法",
                owner_department="人力部",
            )
        )
        session.add(
            PolicyVersion(
                id=base_version_id,
                policy_id=policy_id,
                version_label="v1",
                markdown_key="",
                content_sha256="0" * 64,
                section_tree={},
            )
        )
        session.add(
            Revision(
                id=revision_id,
                policy_id=policy_id,
                base_version_id=base_version_id,
                owner_user_id=owner_id,
                state=RevisionState.IN_REVISION,
                change_brief="根据新劳动法调整年假条款",
                draft_markdown_key="drafts/sample.md",
                draft_content_sha256="abc",
                target_version_label="2.0",
            )
        )
        session.add(
            Comment(
                id=comment_id,
                revision_id=revision_id,
                section_id="sec-zongze",
                author_id=owner_id,
                body="请将总则改为更清晰的表述",
                status=CommentStatus.OPEN,
            )
        )
        await session.commit()

    app = create_app()

    async def override_db():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        login = await ac.post(
            "/api/auth/login", json={"username": "owner1", "password": "secret"}
        )
        token = login.json()["access_token"]
        ac.headers["Authorization"] = f"Bearer {token}"
        ac.comment_id = str(comment_id)
        ac.revision_id = str(revision_id)
        ac.session_factory = session_factory
        yield ac

    await engine.dispose()


@pytest.mark.asyncio
async def test_comment_patch_task_creates_suggestion_linked_to_comment():
    _patch_jsonb_for_sqlite()
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(lambda conn: Base.metadata.create_all(conn, tables=TEST_TABLES))

    owner_id = uuid.uuid4()
    policy_id = uuid.uuid4()
    base_version_id = uuid.uuid4()
    revision_id = uuid.uuid4()
    comment_id = uuid.uuid4()

    async with session_factory() as session:
        session.add(
            User(
                id=owner_id,
                username="worker",
                display_name="经办人",
                department="人力部",
                role=UserRole.OWNER,
                password_hash=pwd.hash("secret"),
            )
        )
        session.add(
            Policy(
                id=policy_id,
                code="HR-101",
                title="考勤办法",
                owner_department="人力部",
            )
        )
        session.add(
            PolicyVersion(
                id=base_version_id,
                policy_id=policy_id,
                version_label="v1",
                markdown_key="",
                content_sha256="0" * 64,
                section_tree={},
            )
        )
        session.add(
            Revision(
                id=revision_id,
                policy_id=policy_id,
                base_version_id=base_version_id,
                owner_user_id=owner_id,
                state=RevisionState.IN_REVISION,
                change_brief="根据新劳动法调整年假条款",
                draft_markdown_key="drafts/sample.md",
                draft_content_sha256="abc",
                target_version_label="2.0",
            )
        )
        session.add(
            Comment(
                id=comment_id,
                revision_id=revision_id,
                section_id="sec-zongze",
                author_id=owner_id,
                body="请将总则改为更清晰的表述",
                status=CommentStatus.OPEN,
            )
        )
        await session.commit()

    mock_storage = MagicMock()
    mock_storage.get_bytes.return_value = SAMPLE_MARKDOWN.encode("utf-8")

    with (
        patch("apps.worker.tasks.llm.SessionLocal", session_factory),
        patch("apps.worker.tasks.llm.StorageService", return_value=mock_storage),
        patch(
            "apps.worker.tasks.llm.call_comment_patch_llm",
            new=AsyncMock(return_value=MOCK_LLM_RESPONSE),
        ),
    ):
        result = await comment_patch_task.coroutine({}, str(comment_id))

    assert result["suggestion_id"] is not None
    assert result["section_id"] == "sec-zongze"

    async with session_factory() as session:
        suggestion_result = await session.execute(select(LlmSuggestion))
        suggestion = suggestion_result.scalar_one()
        assert suggestion.section_id == "sec-zongze"
        assert suggestion.suggested_markdown == "新总则内容。"
        assert suggestion.status == LlmSuggestionStatus.PENDING

        comment_result = await session.execute(select(Comment))
        comment = comment_result.scalar_one()
        assert comment.llm_suggestion_id == suggestion.id
        assert comment.status == CommentStatus.OPEN

    await engine.dispose()


@pytest.mark.asyncio
async def test_enqueue_comment_patch_returns_job_id(patch_client):
    with patch(
        "apps.api.services.ai.jobs_service.enqueue_comment_patch",
        new=AsyncMock(return_value="job-123"),
    ) as mock_enqueue:
        resp = await patch_client.post(f"/api/comments/{patch_client.comment_id}/ai/patch")

    assert resp.status_code == 202
    assert resp.json()["job_id"] == "job-123"
    mock_enqueue.assert_awaited_once_with(patch_client.comment_id)


@pytest.mark.asyncio
async def test_accept_patch_updates_markdown_and_comment_status(patch_client):
    suggestion_id = uuid.uuid4()

    async with patch_client.session_factory() as session:
        session.add(
            LlmSuggestion(
                id=suggestion_id,
                revision_id=uuid.UUID(patch_client.revision_id),
                section_id="sec-zongze",
                action=LlmSuggestionAction.REPLACE,
                suggested_markdown="新总则内容。",
                rationale="回应审阅意见",
                status=LlmSuggestionStatus.PENDING,
                model_name="test-model",
                input_hash="deadbeef",
            )
        )
        comment_result = await session.execute(select(Comment))
        comment = comment_result.scalar_one()
        comment.llm_suggestion_id = suggestion_id
        await session.commit()

    mock_storage = MagicMock()
    mock_storage.get_bytes.return_value = SAMPLE_MARKDOWN.encode("utf-8")
    mock_storage.put_object.return_value = "drafts/sample.md"

    with patch("apps.api.services.ai.StorageService", return_value=mock_storage):
        resp = await patch_client.post(f"/api/ai/suggestions/{suggestion_id}/accept")

    assert resp.status_code == 200
    assert resp.json()["status"] == "accepted"

    saved_md = mock_storage.put_object.call_args[0][1].decode("utf-8")
    assert "新总则内容。" in saved_md
    assert "旧总则内容。" not in saved_md
    expected_sha = hashlib.sha256(saved_md.encode("utf-8")).hexdigest()

    async with patch_client.session_factory() as session:
        comment_result = await session.execute(select(Comment))
        comment = comment_result.scalar_one()
        assert comment.status == CommentStatus.ACCEPTED

        revision_result = await session.execute(select(Revision))
        revision = revision_result.scalar_one()
        assert revision.draft_markdown_key == "drafts/sample.md"
        assert revision.draft_content_sha256 == expected_sha
