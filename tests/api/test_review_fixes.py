"""Regression tests for the multi-role review/workflow fixes."""

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
async def client():
    _patch_jsonb_for_sqlite()
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(lambda conn: Base.metadata.create_all(conn, tables=TEST_TABLES))

    async with session_factory() as session:
        session.add_all(
            [
                User(
                    username="owner1",
                    display_name="经办人",
                    role=UserRole.OWNER,
                    password_hash=pwd.hash("secret"),
                ),
                User(
                    username="owner2",
                    display_name="另一经办人",
                    role=UserRole.OWNER,
                    password_hash=pwd.hash("secret"),
                ),
                User(
                    username="reviewer1",
                    display_name="评审人甲",
                    role=UserRole.REVIEWER,
                    password_hash=pwd.hash("secret"),
                ),
                User(
                    username="reviewer2",
                    display_name="评审人乙",
                    role=UserRole.REVIEWER,
                    password_hash=pwd.hash("secret"),
                ),
                User(
                    username="reader1",
                    display_name="只读用户",
                    role=UserRole.READER,
                    password_hash=pwd.hash("secret"),
                ),
                User(
                    username="admin1",
                    display_name="制度管理员",
                    role=UserRole.POLICY_ADMIN,
                    password_hash=pwd.hash("secret"),
                ),
            ]
        )
        await session.commit()

    app = create_app()

    async def override_db():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_db

    transport = ASGITransport(app=app, raise_app_exceptions=True)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    await engine.dispose()


async def _token(ac: AsyncClient, username: str) -> str:
    resp = await ac.post("/api/auth/login", json={"username": username, "password": "secret"})
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


def _hdr(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _make_consultation_revision(ac: AsyncClient, owner_hdr: dict[str, str]) -> str:
    policy = await ac.post(
        "/api/policies",
        json={"code": "HR-FIX", "title": "修复回归测试", "owner_department": "人力部"},
        headers=owner_hdr,
    )
    assert policy.status_code == 201, policy.text
    rev = await ac.post(
        "/api/revisions",
        json={
            "policy_id": policy.json()["id"],
            "change_brief": "按新规调整年假与考勤口径",
            "target_version_label": "v2.0",
        },
        headers=owner_hdr,
    )
    assert rev.status_code == 201, rev.text
    rev_id = rev.json()["id"]
    transition = await ac.post(
        f"/api/revisions/{rev_id}/transition",
        json={"target_state": "in_consultation"},
        headers=owner_hdr,
    )
    assert transition.status_code == 200, transition.text
    return rev_id


@pytest.mark.asyncio
async def test_reject_comment_without_note_returns_409_not_500(client):
    """BUG-1: rejecting without a resolution note must be a clean 409, not a 500."""
    owner = _hdr(await _token(client, "owner1"))
    rev_id = await _make_consultation_revision(client, owner)

    reviewer = _hdr(await _token(client, "reviewer1"))
    assign = await client.post(
        f"/api/revisions/{rev_id}/reviewers",
        json={"username": "reviewer1", "is_mandatory": False},
        headers=owner,
    )
    assert assign.status_code == 201, assign.text
    comment = await client.post(
        f"/api/revisions/{rev_id}/comments",
        json={"section_id": "sec-1", "body": "请明确年假天数"},
        headers=reviewer,
    )
    assert comment.status_code == 201
    comment_id = comment.json()["id"]

    resp = await client.patch(
        f"/api/comments/{comment_id}",
        json={"status": "rejected"},
        headers=owner,
    )
    assert resp.status_code == 409
    assert "处理说明" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_unassigned_user_cannot_read_revision(client):
    """BUG-2: a different owner / unassigned reviewer must get 403 on read."""
    owner = _hdr(await _token(client, "owner1"))
    rev_id = await _make_consultation_revision(client, owner)

    other_owner = _hdr(await _token(client, "owner2"))
    resp = await client.get(f"/api/revisions/{rev_id}", headers=other_owner)
    assert resp.status_code == 403

    unassigned_reviewer = _hdr(await _token(client, "reviewer2"))
    resp = await client.get(
        f"/api/revisions/{rev_id}/comments", headers=unassigned_reviewer
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_consultation_close_gated_on_mandatory_feedback(client):
    """BUG-4: in_consultation -> in_revision blocked until mandatory reviewer responds."""
    owner = _hdr(await _token(client, "owner1"))
    rev_id = await _make_consultation_revision(client, owner)

    assign = await client.post(
        f"/api/revisions/{rev_id}/reviewers",
        json={"username": "reviewer1", "is_mandatory": True},
        headers=owner,
    )
    assert assign.status_code == 201

    blocked = await client.post(
        f"/api/revisions/{rev_id}/transition",
        json={"target_state": "in_revision"},
        headers=owner,
    )
    assert blocked.status_code == 409

    reviewer = _hdr(await _token(client, "reviewer1"))
    comment = await client.post(
        f"/api/revisions/{rev_id}/comments",
        json={"section_id": "sec-1", "body": "建议补充调休细则"},
        headers=reviewer,
    )
    assert comment.status_code == 201

    ok = await client.post(
        f"/api/revisions/{rev_id}/transition",
        json={"target_state": "in_revision"},
        headers=owner,
    )
    assert ok.status_code == 200
    assert ok.json()["state"] == "in_revision"


@pytest.mark.asyncio
async def test_reader_cannot_create_policy_and_anon_blocked(client):
    """BUG-6/BUG-7: readers can't author; policy list requires auth."""
    reader = _hdr(await _token(client, "reader1"))
    resp = await client.post(
        "/api/policies",
        json={"code": "X-1", "title": "非法", "owner_department": "d"},
        headers=reader,
    )
    assert resp.status_code == 403

    anon = await client.get("/api/policies")
    assert anon.status_code in (401, 403)


@pytest.mark.asyncio
async def test_notifications_mark_read(client):
    """BUG-9: assigned reviewer gets a notification; mark-read flips it to read."""
    owner = _hdr(await _token(client, "owner1"))
    rev_id = await _make_consultation_revision(client, owner)
    await client.post(
        f"/api/revisions/{rev_id}/reviewers",
        json={"username": "reviewer1", "is_mandatory": True},
        headers=owner,
    )

    reviewer = _hdr(await _token(client, "reviewer1"))
    listing = await client.get("/api/notifications", headers=reviewer)
    assert listing.status_code == 200
    items = listing.json()
    assert len(items) >= 1
    assert any(not n["read"] for n in items)

    marked = await client.post("/api/notifications/read", headers=reviewer)
    assert marked.status_code == 200
    assert marked.json()["marked"] >= 1

    after = await client.get("/api/notifications", headers=reviewer)
    assert all(n["read"] for n in after.json())


@pytest.mark.asyncio
async def test_owner_sees_reviewer_feedback_status(client):
    """BUG-5: reviewer list exposes feedback_status / comment_count to the owner."""
    owner = _hdr(await _token(client, "owner1"))
    rev_id = await _make_consultation_revision(client, owner)
    await client.post(
        f"/api/revisions/{rev_id}/reviewers",
        json={"username": "reviewer1", "is_mandatory": True},
        headers=owner,
    )

    listing = await client.get(f"/api/revisions/{rev_id}/reviewers", headers=owner)
    assert listing.status_code == 200
    row = listing.json()[0]
    assert row["feedback_status"] == "awaiting"
    assert row["comment_count"] == 0

    reviewer = _hdr(await _token(client, "reviewer1"))
    await client.post(
        f"/api/revisions/{rev_id}/comments",
        json={"section_id": "sec-1", "body": "已审阅，建议通过"},
        headers=reviewer,
    )

    listing = await client.get(f"/api/revisions/{rev_id}/reviewers", headers=owner)
    row = listing.json()[0]
    assert row["feedback_status"] == "submitted"
    assert row["comment_count"] == 1
