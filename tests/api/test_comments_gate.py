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
from apps.api.models.user import User, UserRole

pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")

TEST_TABLES = [
    User.__table__,
    Policy.__table__,
    PolicyVersion.__table__,
    Revision.__table__,
    Comment.__table__,
    AuditEvent.__table__,
]


def _patch_jsonb_for_sqlite() -> None:
    for table in TEST_TABLES:
        for column in table.columns:
            if isinstance(column.type, JSONB):
                column.type = JSON()


async def _revision_in_revision(auth_client: AsyncClient) -> str:
    policy = await auth_client.post(
        "/api/policies",
        json={"code": "HR-CMT", "title": "评论门禁测试", "owner_department": "人力部"},
    )
    assert policy.status_code == 201

    revision = await auth_client.post(
        "/api/revisions",
        json={
            "policy_id": policy.json()["id"],
            "change_brief": "根据新劳动法调整年假与调休规则",
        },
    )
    assert revision.status_code == 201
    revision_id = revision.json()["id"]

    for target_state in ("in_consultation", "in_revision"):
        resp = await auth_client.post(
            f"/api/revisions/{revision_id}/transition",
            json={"target_state": target_state},
        )
        assert resp.status_code == 200, resp.text

    return revision_id


@pytest.fixture
async def auth_client():
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


@pytest.fixture
async def revision_in_revision(auth_client):
    return await _revision_in_revision(auth_client)


@pytest.mark.asyncio
async def test_open_comment_blocks_pending_publish(auth_client, revision_in_revision):
    await auth_client.post(
        f"/api/revisions/{revision_in_revision}/comments",
        json={"section_id": "sec-1", "body": "请明确年假天数"},
    )
    resp = await auth_client.post(
        f"/api/revisions/{revision_in_revision}/transition",
        json={"target_state": "pending_publish"},
    )
    assert resp.status_code == 409
    assert "open comments" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_resolved_comments_allow_pending_publish(auth_client, revision_in_revision):
    comment = await auth_client.post(
        f"/api/revisions/{revision_in_revision}/comments",
        json={"section_id": "sec-1", "body": "请明确年假天数"},
    )
    assert comment.status_code == 201

    resolved = await auth_client.patch(
        f"/api/comments/{comment.json()['id']}",
        json={"status": "accepted"},
    )
    assert resolved.status_code == 200

    resp = await auth_client.post(
        f"/api/revisions/{revision_in_revision}/transition",
        json={"target_state": "pending_publish"},
    )
    assert resp.status_code == 200
    assert resp.json()["state"] == "pending_publish"
