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
from apps.api.models.comment import Comment
from apps.api.models.policy import Policy, PolicyStatus, PolicyVersion
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

RAW_VERSION_MD = "# 原始制度\n\n第一条 原始条款。\n"
EDITED_DRAFT_MD = "# 原始制度\n\n第一条 原始条款。\n\n第二条 新增修改内容。\n"
PUBLISHED_V2_MD = "# 原始制度\n\n第一条 已发布修改。\n"


def _patch_jsonb_for_sqlite() -> None:
    for table in TEST_TABLES:
        for column in table.columns:
            if isinstance(column.type, JSONB):
                column.type = JSON()


def _mock_storage(content_by_key: dict[str, str]) -> MagicMock:
    storage = MagicMock()

    def get_bytes(key: str) -> bytes:
        return content_by_key.get(key, "").encode("utf-8")

    storage.get_bytes.side_effect = get_bytes
    storage.put_object.side_effect = lambda key, data: key
    return storage


@pytest.fixture
async def seed_client():
    _patch_jsonb_for_sqlite()
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(lambda conn: Base.metadata.create_all(conn, tables=TEST_TABLES))

    policy_id = uuid.uuid4()
    version_id = uuid.uuid4()
    first_revision_id = uuid.uuid4()
    version_key = "policies/version/raw.md"
    first_draft_key = f"drafts/{first_revision_id}.md"

    async with session_factory() as session:
        owner = User(
            username="owner1",
            display_name="经办人",
            department="人力部",
            role=UserRole.OWNER,
            password_hash=pwd.hash("secret"),
        )
        session.add(owner)
        await session.flush()

        policy = Policy(
            id=policy_id,
            code="HR-SEED",
            title="种子测试制度",
            owner_department="人力部",
        )
        session.add(policy)
        await session.flush()

        version = PolicyVersion(
            id=version_id,
            policy_id=policy.id,
            version_label="v1.0",
            status=PolicyStatus.ACTIVE,
            markdown_key=version_key,
            content_sha256=hashlib.sha256(RAW_VERSION_MD.encode()).hexdigest(),
            section_tree={"sections": []},
        )
        session.add(version)
        await session.flush()
        policy.current_version_id = version.id

        first_revision = Revision(
            id=first_revision_id,
            policy_id=policy.id,
            base_version_id=version.id,
            owner_user_id=owner.id,
            state=RevisionState.DRAFT,
            change_brief="第一次修订说明内容足够长",
            draft_markdown_key=first_draft_key,
            draft_content_sha256=hashlib.sha256(EDITED_DRAFT_MD.encode()).hexdigest(),
            target_version_label="v2.0",
        )
        session.add(first_revision)
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
        ac.policy_id = str(policy_id)  # type: ignore[attr-defined]
        ac.version_key = version_key  # type: ignore[attr-defined]
        ac.first_draft_key = first_draft_key  # type: ignore[attr-defined]
        ac.session_factory = session_factory  # type: ignore[attr-defined]
        yield ac

    await engine.dispose()


@pytest.mark.asyncio
async def test_new_revision_seeds_from_latest_draft_when_unpublished(seed_client):
    storage = _mock_storage(
        {
            seed_client.version_key: RAW_VERSION_MD,  # type: ignore[attr-defined]
            seed_client.first_draft_key: EDITED_DRAFT_MD,  # type: ignore[attr-defined]
        }
    )

    with patch("apps.api.services.revisions.StorageService", return_value=storage):
        created = await seed_client.post(
            "/api/revisions",
            json={
                "policy_id": seed_client.policy_id,  # type: ignore[attr-defined]
                "change_brief": "第二次修订说明内容足够长",
                "target_version_label": "v3.0",
            },
        )

    assert created.status_code == 201
    assert storage.put_object.called
    _, seeded_bytes = storage.put_object.call_args[0]
    seeded_md = seeded_bytes.decode("utf-8")
    assert "第二条 新增修改内容" in seeded_md
    assert "第一条 原始条款" in seeded_md


@pytest.mark.asyncio
async def test_new_revision_seeds_from_published_version_after_publish(seed_client):
    published_key = "policies/version/published-v2.md"
    storage = _mock_storage(
        {
            seed_client.version_key: RAW_VERSION_MD,  # type: ignore[attr-defined]
            seed_client.first_draft_key: EDITED_DRAFT_MD,  # type: ignore[attr-defined]
            published_key: PUBLISHED_V2_MD,
        }
    )

    async with seed_client.session_factory() as session:  # type: ignore[attr-defined]
        policy = (
            await session.execute(select(Policy).where(Policy.code == "HR-SEED"))
        ).scalar_one()
        policy.current_version_id = uuid.uuid4()
        published_version = PolicyVersion(
            id=policy.current_version_id,
            policy_id=policy.id,
            version_label="v2.0",
            status=PolicyStatus.ACTIVE,
            markdown_key=published_key,
            content_sha256=hashlib.sha256(PUBLISHED_V2_MD.encode()).hexdigest(),
            section_tree={"sections": []},
        )
        session.add(published_version)
        revision = (
            await session.execute(select(Revision).where(Revision.target_version_label == "v2.0"))
        ).scalar_one()
        revision.state = RevisionState.PUBLISHED
        await session.commit()

    with patch("apps.api.services.revisions.StorageService", return_value=storage):
        created = await seed_client.post(
            "/api/revisions",
            json={
                "policy_id": seed_client.policy_id,  # type: ignore[attr-defined]
                "change_brief": "第三次修订说明内容足够长",
                "target_version_label": "v3.0",
            },
        )

    assert created.status_code == 201
    assert storage.put_object.called
    _, seeded_bytes = storage.put_object.call_args[0]
    seeded_md = seeded_bytes.decode("utf-8")
    assert "第一条 已发布修改" in seeded_md
    assert "第二条 新增修改内容" not in seeded_md
