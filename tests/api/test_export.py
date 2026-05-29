import uuid
from unittest.mock import AsyncMock, patch

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
async def test_publish_request_enqueues_export_job(auth_client):
    policy = await auth_client.post(
        "/api/policies",
        json={"code": "HR-010", "title": "考勤办法", "owner_department": "人力部"},
    )
    revision = await auth_client.post(
        "/api/revisions",
        json={
            "policy_id": policy.json()["id"],
            "change_brief": "根据新劳动法调整年假",
            "target_version_label": "2.0",
        },
    )
    revision_id = revision.json()["id"]
    fake_job_id = "abc123job"

    with patch(
        "apps.api.services.jobs.enqueue_export_pdf",
        new=AsyncMock(return_value=fake_job_id),
    ):
        resp = await auth_client.post(f"/api/revisions/{revision_id}/publish-request")

    assert resp.status_code == 202
    assert resp.json()["job_id"] == fake_job_id


@pytest.mark.asyncio
async def test_get_job_status_returns_complete(auth_client):
    job_id = "job-complete-1"
    fake_status = {
        "job_id": job_id,
        "status": "complete",
        "result": {"pdf_key": "policies/x/y/file.pdf", "revision_id": str(uuid.uuid4())},
        "error": None,
    }

    with patch(
        "apps.api.services.jobs.get_job_status",
        new=AsyncMock(return_value=fake_status),
    ):
        resp = await auth_client.get(f"/api/jobs/{job_id}")

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "complete"
    assert body["result"]["pdf_key"] == "policies/x/y/file.pdf"


@pytest.mark.asyncio
async def test_publish_request_returns_404_for_missing_revision(auth_client):
    missing_id = "00000000-0000-0000-0000-000000000099"
    resp = await auth_client.post(f"/api/revisions/{missing_id}/publish-request")
    assert resp.status_code == 404
