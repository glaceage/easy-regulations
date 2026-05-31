import pytest
from httpx import ASGITransport, AsyncClient
from passlib.context import CryptContext
from sqlalchemy import JSON
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from apps.api.db.session import get_db
from apps.api.main import create_app
from apps.api.models.audit import AuditEvent
from apps.api.models.base import Base
from apps.api.models.comment import Comment
from apps.api.models.policy import Policy, PolicyVersion
from apps.api.models.revision import Revision
from apps.api.models.revision_reviewer import RevisionReviewer
from apps.api.models.user import User, UserRole

pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")

TEST_TABLES = [
    User.__table__,
    Policy.__table__,
    PolicyVersion.__table__,
    Revision.__table__,
    Comment.__table__,
    RevisionReviewer.__table__,
    AuditEvent.__table__,
]


def _patch_jsonb_for_sqlite() -> None:
    for table in TEST_TABLES:
        for column in table.columns:
            if isinstance(column.type, JSONB):
                column.type = JSON()


@pytest.fixture
async def draft_client():
    _patch_jsonb_for_sqlite()
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(lambda conn: Base.metadata.create_all(conn, tables=TEST_TABLES))

    async with session_factory() as session:
        session.add(
            User(
                username="owner1",
                display_name="经办人",
                department="人力部",
                role=UserRole.OWNER,
                password_hash=pwd.hash("secret"),
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
        yield ac

    await engine.dispose()


@pytest.mark.asyncio
async def test_draft_markdown_get_put_roundtrip(draft_client):
    policy = await draft_client.post(
        "/api/policies",
        json={"code": "HR-DM", "title": "草案测试", "owner_department": "人力部"},
    )
    revision = await draft_client.post(
        "/api/revisions",
        json={
            "policy_id": policy.json()["id"],
            "change_brief": "测试草案读写",
            "target_version_label": "v2.0",
        },
    )
    revision_id = revision.json()["id"]

    get_resp = await draft_client.get(f"/api/revisions/{revision_id}/draft-markdown")
    assert get_resp.status_code == 200
    assert "markdown" in get_resp.json()

    updated = "# 测试正文\n\n已更新。\n"
    put_resp = await draft_client.put(
        f"/api/revisions/{revision_id}/draft-markdown",
        json={"markdown": updated},
    )
    assert put_resp.status_code == 200
    saved = put_resp.json()["markdown"]
    assert "已更新" in saved
    assert "{#" in saved

    get_again = await draft_client.get(f"/api/revisions/{revision_id}/draft-markdown")
    assert "已更新" in get_again.json()["markdown"]
    assert "{#" in get_again.json()["markdown"]


@pytest.mark.asyncio
async def test_pending_publish_cannot_transition_to_published(draft_client):
    policy = await draft_client.post(
        "/api/policies",
        json={"code": "HR-PP", "title": "发布门禁", "owner_department": "人力部"},
    )
    revision = await draft_client.post(
        "/api/revisions",
        json={
            "policy_id": policy.json()["id"],
            "change_brief": "测试禁止直接发布流程门禁",
            "target_version_label": "v2.0",
        },
    )
    revision_id = revision.json()["id"]

    for target_state in ("in_consultation", "in_revision", "pending_publish"):
        resp = await draft_client.post(
            f"/api/revisions/{revision_id}/transition",
            json={"target_state": target_state},
        )
        assert resp.status_code == 200, resp.text

    resp = await draft_client.post(
        f"/api/revisions/{revision_id}/transition",
        json={"target_state": "published"},
    )
    assert resp.status_code == 409
