import uuid

import pytest
from sqlalchemy import JSON, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from apps.api.models.audit import AuditEvent
from apps.api.models.base import Base
from apps.api.services.audit import record_event

TEST_TABLES = [AuditEvent.__table__]


def _patch_jsonb_for_sqlite() -> None:
    for table in TEST_TABLES:
        for column in table.columns:
            if isinstance(column.type, JSONB):
                column.type = JSON()


@pytest.fixture
async def db_session():
    _patch_jsonb_for_sqlite()
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(lambda conn: Base.metadata.create_all(conn, tables=TEST_TABLES))

    async with session_factory() as session:
        yield session

    await engine.dispose()


@pytest.mark.asyncio
async def test_record_event_creates_row(db_session):
    revision_id = uuid.uuid4()
    event = await record_event(
        db_session,
        actor_id=None,
        action="revision.transition",
        resource_type="revision",
        resource_id=str(revision_id),
        payload={"to": "in_consultation"},
    )
    await db_session.commit()

    rows = (await db_session.execute(select(AuditEvent))).scalars().all()
    assert len(rows) == 1
    assert rows[0].id == event.id
    assert rows[0].action == "revision.transition"
    assert rows[0].resource_type == "revision"
    assert rows[0].resource_id == str(revision_id)
    assert rows[0].payload == {"to": "in_consultation"}
