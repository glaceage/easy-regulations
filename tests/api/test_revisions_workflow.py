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
from apps.api.models.policy import Policy, PolicyVersion
from apps.api.models.revision import Revision
from apps.api.models.user import User, UserRole

pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")

TEST_TABLES = [
    User.__table__,
    Policy.__table__,
    PolicyVersion.__table__,
    Revision.__table__,
    AuditEvent.__table__,
]


def _patch_jsonb_for_sqlite() -> None:
    for table in TEST_TABLES:
        for column in table.columns:
            if isinstance(column.type, JSONB):
                column.type = JSON()


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


@pytest.mark.asyncio
async def test_transition_draft_to_consultation(auth_client):
    policy = await auth_client.post(
        "/api/policies",
        json={"code": "HR-001", "title": "考勤办法", "owner_department": "人力部"},
    )
    assert policy.status_code == 201

    revision = await auth_client.post(
        "/api/revisions",
        json={
            "policy_id": policy.json()["id"],
            "change_brief": "根据新劳动法调整年假",
        },
    )
    assert revision.status_code == 201
    revision_body = revision.json()
    assert revision_body["state"] == "draft"
    assert revision_body["draft_markdown_key"] == f"drafts/{revision_body['id']}.md"

    resp = await auth_client.post(
        f"/api/revisions/{revision_body['id']}/transition",
        json={"target_state": "in_consultation"},
    )
    assert resp.status_code == 200
    assert resp.json()["state"] == "in_consultation"


@pytest.mark.asyncio
async def test_invalid_transition_draft_to_published_returns_409(auth_client):
    policy = await auth_client.post(
        "/api/policies",
        json={"code": "HR-002", "title": "休假办法", "owner_department": "人力部"},
    )
    revision = await auth_client.post(
        "/api/revisions",
        json={
            "policy_id": policy.json()["id"],
            "change_brief": "根据新劳动法调整年假",
        },
    )

    resp = await auth_client.post(
        f"/api/revisions/{revision.json()['id']}/transition",
        json={"target_state": "published"},
    )
    assert resp.status_code == 409
