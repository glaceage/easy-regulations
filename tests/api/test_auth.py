import pytest
from httpx import ASGITransport, AsyncClient
from passlib.context import CryptContext
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from apps.api.db.session import get_db
from apps.api.main import create_app
from apps.api.models.base import Base
from apps.api.models.user import User, UserRole

pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")


@pytest.fixture
async def client():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(
            lambda conn: Base.metadata.create_all(conn, tables=[User.__table__])
        )

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
        yield ac

    await engine.dispose()


@pytest.mark.asyncio
async def test_login_returns_token(client):
    response = await client.post(
        "/api/auth/login", json={"username": "owner1", "password": "secret"}
    )
    assert response.status_code == 200
    assert "access_token" in response.json()
