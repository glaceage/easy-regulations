import hashlib
import uuid
from unittest.mock import MagicMock, patch

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
from apps.api.models.llm_suggestion import (
    LlmSuggestion,
    LlmSuggestionAction,
    LlmSuggestionStatus,
)
from apps.api.models.policy import Policy, PolicyVersion
from apps.api.models.revision import Revision, RevisionState
from apps.api.models.user import User, UserRole

pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")

TEST_TABLES = [
    User.__table__,
    Policy.__table__,
    PolicyVersion.__table__,
    Revision.__table__,
    AuditEvent.__table__,
    LlmSuggestion.__table__,
]

SAMPLE_MARKDOWN = """# 总则 {#sec-zongze}

旧总则内容。

## 目的 {#sec-mudi}

旧目的内容。
"""


def _patch_jsonb_for_sqlite() -> None:
    for table in TEST_TABLES:
        for column in table.columns:
            if isinstance(column.type, JSONB):
                column.type = JSON()


@pytest.fixture
async def ai_client():
    _patch_jsonb_for_sqlite()
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(lambda conn: Base.metadata.create_all(conn, tables=TEST_TABLES))

    owner_id = uuid.uuid4()
    policy_id = uuid.uuid4()
    base_version_id = uuid.uuid4()
    revision_id = uuid.uuid4()
    suggestion_id = uuid.uuid4()

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
                state=RevisionState.DRAFT,
                change_brief="根据新劳动法调整年假条款",
                draft_markdown_key="drafts/sample.md",
                draft_content_sha256="abc",
                target_version_label="2.0",
            )
        )
        session.add(
            LlmSuggestion(
                id=suggestion_id,
                revision_id=revision_id,
                section_id="sec-zongze",
                action=LlmSuggestionAction.REPLACE,
                suggested_markdown="新总则内容。",
                rationale="对齐变更说明",
                status=LlmSuggestionStatus.PENDING,
                model_name="test-model",
                input_hash="deadbeef",
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
        ac.revision_id = str(revision_id)
        ac.suggestion_id = str(suggestion_id)
        ac.session_factory = session_factory
        yield ac

    await engine.dispose()


@pytest.mark.asyncio
async def test_accept_suggestion_updates_markdown_in_storage(ai_client):
    mock_storage = MagicMock()
    mock_storage.get_bytes.return_value = SAMPLE_MARKDOWN.encode("utf-8")
    mock_storage.put_bytes.return_value = "policies/x/y/updated.md"
    mock_storage.last_sha256 = "newsha256"

    with patch("apps.api.services.ai.StorageService", return_value=mock_storage):
        resp = await ai_client.post(f"/api/ai/suggestions/{ai_client.suggestion_id}/accept")

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "accepted"
    assert body["section_id"] == "sec-zongze"

    saved_md = mock_storage.put_bytes.call_args[0][0].decode("utf-8")
    assert "新总则内容。" in saved_md
    assert "旧总则内容。" not in saved_md
    expected_sha = hashlib.sha256(saved_md.encode("utf-8")).hexdigest()

    async with ai_client.session_factory() as session:
        result = await session.execute(select(Revision))
        revision = result.scalar_one()
        assert revision.draft_markdown_key == "policies/x/y/updated.md"
        assert revision.draft_content_sha256 == expected_sha


@pytest.mark.asyncio
async def test_list_revision_suggestions(ai_client):
    resp = await ai_client.get(f"/api/revisions/{ai_client.revision_id}/ai/suggestions")
    assert resp.status_code == 200
    items = resp.json()
    assert len(items) == 1
    assert items[0]["section_id"] == "sec-zongze"
    assert items[0]["status"] == "pending"
