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
from apps.api.models.revision import Revision, RevisionState
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
async def review_client():
    _patch_jsonb_for_sqlite()
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(lambda conn: Base.metadata.create_all(conn, tables=TEST_TABLES))

    async with session_factory() as session:
        owner = User(
            username="owner1",
            display_name="经办人",
            department="人力部",
            role=UserRole.OWNER,
            password_hash=pwd.hash("secret"),
        )
        reviewer = User(
            username="reviewer1",
            display_name="评审人",
            department="法务部",
            role=UserRole.REVIEWER,
            password_hash=pwd.hash("secret"),
        )
        session.add_all([owner, reviewer])
        await session.flush()

        policy = Policy(code="HR-RV", title="评审测试", owner_department="人力部")
        session.add(policy)
        await session.flush()

        version = PolicyVersion(
            policy_id=policy.id,
            version_label="v1.0",
            markdown_key="policies/x/v1.md",
            content_sha256="abc",
            section_tree={"sections": []},
        )
        session.add(version)
        await session.flush()
        policy.current_version_id = version.id

        revision = Revision(
            policy_id=policy.id,
            base_version_id=version.id,
            owner_user_id=owner.id,
            state=RevisionState.IN_CONSULTATION,
            change_brief="征求意见阶段的评审测试任务",
            draft_markdown_key="drafts/test.md",
            draft_content_sha256="def",
            target_version_label="v2.0",
        )
        session.add(revision)
        await session.flush()

        session.add(
            RevisionReviewer(
                revision_id=revision.id,
                user_id=reviewer.id,
                is_mandatory=True,
                assigned_by_id=owner.id,
            )
        )
        await session.commit()

        revision_id = str(revision.id)

    app = create_app()

    async def override_db():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        login = await ac.post(
            "/api/auth/login", json={"username": "reviewer1", "password": "secret"}
        )
        token = login.json()["access_token"]
        ac.headers["Authorization"] = f"Bearer {token}"
        ac.revision_id = revision_id  # type: ignore[attr-defined]
        ac.policy_id = str(policy.id)  # type: ignore[attr-defined]
        yield ac

    await engine.dispose()


@pytest.mark.asyncio
async def test_list_my_review_assignments(review_client):
    resp = await review_client.get("/api/reviews/assignments")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["policy_code"] == "HR-RV"
    assert body[0]["feedback_status"] == "awaiting"
    assert body[0]["my_comment_count"] == 0


@pytest.mark.asyncio
async def test_reviewer_can_comment_when_assigned(review_client):
    revision_id = review_client.revision_id  # type: ignore[attr-defined]
    resp = await review_client.post(
        f"/api/revisions/{revision_id}/comments",
        json={"section_id": "general", "body": "建议明确年假天数"},
    )
    assert resp.status_code == 201


@pytest.mark.asyncio
async def test_reviewer_cannot_comment_without_assignment(review_client):
    revision_id = review_client.revision_id  # type: ignore[attr-defined]

    owner_login = await review_client.post(
        "/api/auth/login", json={"username": "owner1", "password": "secret"}
    )
    review_client.headers["Authorization"] = f"Bearer {owner_login.json()['access_token']}"
    unassigned = await review_client.post(
        "/api/revisions",
        json={
            "policy_id": review_client.policy_id,  # type: ignore[attr-defined]
            "change_brief": "另一条未指派评审人的修订",
        },
    )
    assert unassigned.status_code == 201
    new_id = unassigned.json()["id"]
    await review_client.post(
        f"/api/revisions/{new_id}/transition",
        json={"target_state": "in_consultation"},
    )

    reviewer_login = await review_client.post(
        "/api/auth/login", json={"username": "reviewer1", "password": "secret"}
    )
    review_client.headers["Authorization"] = f"Bearer {reviewer_login.json()['access_token']}"
    resp = await review_client.post(
        f"/api/revisions/{new_id}/comments",
        json={"section_id": "general", "body": "不应成功"},
    )
    assert resp.status_code == 403
