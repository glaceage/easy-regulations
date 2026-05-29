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
from apps.api.models.comment import Comment, CommentStatus
from apps.api.models.policy import Policy, PolicyStatus, PolicyVersion
from apps.api.models.revision import Revision, RevisionState
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

DRAFT_MARKDOWN = "# 考勤办法 {#sec-attendance}\n\n年假调整为 10 天。\n"


def _patch_jsonb_for_sqlite() -> None:
    for table in TEST_TABLES:
        for column in table.columns:
            if isinstance(column.type, JSONB):
                column.type = JSON()


@pytest.fixture
async def publish_client():
    _patch_jsonb_for_sqlite()
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(lambda conn: Base.metadata.create_all(conn, tables=TEST_TABLES))

    async with session_factory() as session:
        session.add(
            User(
                username="admin1",
                display_name="制度管理员",
                department="人力部",
                role=UserRole.POLICY_ADMIN,
                password_hash=pwd.hash("secret"),
            )
        )
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
            "/api/auth/login", json={"username": "admin1", "password": "secret"}
        )
        token = login.json()["access_token"]
        ac.headers["Authorization"] = f"Bearer {token}"
        ac.session_factory = session_factory
        yield ac

    await engine.dispose()


def _mock_storage() -> MagicMock:
    storage = MagicMock()
    storage.get_bytes.return_value = DRAFT_MARKDOWN.encode("utf-8")
    storage.put_bytes.side_effect = lambda data, suffix, prefix="": (
        f"{prefix}mock{suffix}"
    )
    storage.last_sha256 = "abc123"
    return storage


async def _ready_revision(client: AsyncClient, *, target_version_label: str = "2.0") -> dict:
    policy = await client.post(
        "/api/policies",
        json={"code": "HR-PUB", "title": "考勤办法", "owner_department": "人力部"},
    )
    assert policy.status_code == 201
    policy_id = policy.json()["id"]

    revision = await client.post(
        "/api/revisions",
        json={
            "policy_id": policy_id,
            "change_brief": "根据新劳动法调整年假与调休规则",
            "target_version_label": target_version_label,
        },
    )
    assert revision.status_code == 201
    revision_id = revision.json()["id"]

    for target_state in ("in_consultation", "in_revision", "pending_publish"):
        resp = await client.post(
            f"/api/revisions/{revision_id}/transition",
            json={"target_state": target_state},
        )
        assert resp.status_code == 200, resp.text

    return {"policy_id": policy_id, "revision_id": revision_id}


@pytest.mark.asyncio
async def test_publish_creates_new_policy_version(publish_client):
    ids = await _ready_revision(publish_client)
    mock_storage = _mock_storage()

    with (
        patch("apps.api.services.revisions.StorageService", return_value=mock_storage),
        patch("apps.api.services.revisions.html_to_pdf", return_value=b"%PDF-1.4"),
    ):
        resp = await publish_client.post(f"/api/revisions/{ids['revision_id']}/publish")

    assert resp.status_code == 200
    body = resp.json()
    assert body["state"] == "published"
    assert body["version_label"] == "2.0"
    assert body["pdf_key"].endswith(".pdf")
    assert body["markdown_key"].endswith(".md")

    async with publish_client.session_factory() as session:
        policy = (
            await session.execute(select(Policy).where(Policy.id == uuid.UUID(ids["policy_id"])))
        ).scalar_one()
        assert policy.current_version_id == uuid.UUID(body["policy_version_id"])

        version = (
            await session.execute(
                select(PolicyVersion).where(PolicyVersion.id == policy.current_version_id)
            )
        ).scalar_one()
        assert version.version_label == "2.0"
        assert version.status == PolicyStatus.ACTIVE
        assert version.pdf_key == body["pdf_key"]
        assert version.markdown_key == body["markdown_key"]
        assert version.section_tree["sections"]
        assert version.section_tree["sections"][0]["section_id"] == "sec-attendance"

        revision = (
            await session.execute(
                select(Revision).where(Revision.id == uuid.UUID(ids["revision_id"]))
            )
        ).scalar_one()
        assert revision.state == RevisionState.PUBLISHED


@pytest.mark.asyncio
async def test_publish_marks_previous_version_superseded(publish_client):
    ids = await _ready_revision(publish_client)

    async with publish_client.session_factory() as session:
        policy = (
            await session.execute(select(Policy).where(Policy.id == uuid.UUID(ids["policy_id"])))
        ).scalar_one()
        old_version = PolicyVersion(
            policy_id=policy.id,
            version_label="1.0",
            status=PolicyStatus.ACTIVE,
            markdown_key="policies/old.md",
            content_sha256="deadbeef" * 8,
            section_tree={},
        )
        session.add(old_version)
        await session.flush()
        policy.current_version_id = old_version.id
        await session.commit()
        old_version_id = old_version.id

    mock_storage = _mock_storage()
    with (
        patch("apps.api.services.revisions.StorageService", return_value=mock_storage),
        patch("apps.api.services.revisions.html_to_pdf", return_value=b"%PDF-1.4"),
    ):
        resp = await publish_client.post(f"/api/revisions/{ids['revision_id']}/publish")

    assert resp.status_code == 200

    async with publish_client.session_factory() as session:
        old = (
            await session.execute(select(PolicyVersion).where(PolicyVersion.id == old_version_id))
        ).scalar_one()
        assert old.status == PolicyStatus.SUPERSEDED


@pytest.mark.asyncio
async def test_publish_requires_policy_admin(publish_client):
    ids = await _ready_revision(publish_client)

    owner_login = await publish_client.post(
        "/api/auth/login", json={"username": "owner1", "password": "secret"}
    )
    publish_client.headers["Authorization"] = f"Bearer {owner_login.json()['access_token']}"

    resp = await publish_client.post(f"/api/revisions/{ids['revision_id']}/publish")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_publish_requires_pending_publish_state(publish_client):
    policy = await publish_client.post(
        "/api/policies",
        json={"code": "HR-DRAFT", "title": "草稿制度", "owner_department": "人力部"},
    )
    revision = await publish_client.post(
        "/api/revisions",
        json={
            "policy_id": policy.json()["id"],
            "change_brief": "根据新劳动法调整年假与调休规则",
            "target_version_label": "2.0",
        },
    )

    resp = await publish_client.post(f"/api/revisions/{revision.json()['id']}/publish")
    assert resp.status_code == 409
    assert "pending_publish" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_publish_blocked_by_open_comments(publish_client):
    ids = await _ready_revision(publish_client)

    async with publish_client.session_factory() as session:
        admin = (await session.execute(select(User).where(User.username == "admin1"))).scalar_one()
        session.add(
            Comment(
                revision_id=uuid.UUID(ids["revision_id"]),
                section_id="sec-1",
                author_id=admin.id,
                body="发布前新增的未处理意见",
                status=CommentStatus.OPEN,
            )
        )
        await session.commit()

    resp = await publish_client.post(f"/api/revisions/{ids['revision_id']}/publish")
    assert resp.status_code == 409
    assert "open comments" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_publish_returns_404_for_missing_revision(publish_client):
    missing_id = "00000000-0000-0000-0000-000000000099"
    resp = await publish_client.post(f"/api/revisions/{missing_id}/publish")
    assert resp.status_code == 404
