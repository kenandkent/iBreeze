"""PostgreSQL-backed test configuration and fixtures."""

import os
import uuid as _uuid
from collections.abc import AsyncGenerator, Iterator
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from testcontainers.postgres import PostgresContainer

from ibreeze_backend.db.session import Base
from ibreeze_backend.main import app


@pytest.fixture(scope="session")
def postgres_url() -> Iterator[str]:
    """Start the PostgreSQL 16 instance required by the production contract."""
    docker_config = str(Path(__file__).with_name("docker-config"))
    original_docker_config = os.environ.get("DOCKER_CONFIG")
    os.environ["DOCKER_CONFIG"] = docker_config
    try:
        with PostgresContainer("postgres:16", driver="asyncpg") as postgres:
            yield postgres.get_connection_url()
    finally:
        if original_docker_config is None:
            os.environ.pop("DOCKER_CONFIG", None)
        else:
            os.environ["DOCKER_CONFIG"] = original_docker_config


@pytest_asyncio.fixture(scope="function")
async def db_engine(postgres_url: str):
    """Create a test database engine."""
    engine = create_async_engine(postgres_url, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def db_session(db_engine) -> AsyncGenerator[AsyncSession, None]:
    """Create a test database session."""
    async_session = sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:
        yield session


@pytest_asyncio.fixture(scope="function")
async def client(db_session, db_engine) -> AsyncGenerator[AsyncClient, None]:
    """Create a test HTTP client."""
    from sqlalchemy.ext.asyncio import async_sessionmaker

    import ibreeze_backend.middleware.audit as audit_mod
    import ibreeze_backend.middleware.idempotency as idempotency_mod
    from ibreeze_backend.db.session import get_db_session, request_session
    from ibreeze_backend.middleware.ratelimit import reset_rate_limiter

    async def override_get_db():
        shared_session = request_session.get()
        yield shared_session if shared_session is not None else db_session

    app.dependency_overrides[get_db_session] = override_get_db

    # Point audit middleware at the test database
    audit_mod.async_session_factory = async_sessionmaker(db_engine, expire_on_commit=False)
    idempotency_mod.async_session_factory = async_sessionmaker(
        db_engine,
        expire_on_commit=False,
    )

    reset_rate_limiter()

    transport = ASGITransport(app=app)

    async def add_idempotency_key(request):
        if request.method not in {"GET", "HEAD", "OPTIONS"} and "/auth/" not in request.url.path:
            request.headers.setdefault("Idempotency-Key", str(_uuid.uuid4()))

    async with AsyncClient(
        transport=transport,
        base_url="http://test",
        event_hooks={"request": [add_idempotency_key]},
    ) as ac:
        yield ac

    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def test_user(db_session: AsyncSession):
    """Create a test user."""
    from ibreeze_backend.auth.service import register

    user = await register(
        db_session,
        email=f"test_{_uuid.uuid4().hex[:8]}@example.com",
        password="testpassword123",
    )
    await db_session.commit()
    return user


@pytest_asyncio.fixture
async def test_admin(db_session: AsyncSession):
    """Create a test admin user."""
    from passlib.hash import argon2

    from ibreeze_backend.models.user import User

    admin = User(
        username=f"admin_{_uuid.uuid4().hex[:8]}",
        email=None,
        password_hash=argon2.hash("admin123456"),
        display_name="Test administrator",
        user_type="admin",
        protected=True,
        status="active",
    )
    db_session.add(admin)
    await db_session.commit()
    await db_session.refresh(admin)
    return admin


@pytest_asyncio.fixture
async def admin_tokens(db_session: AsyncSession, test_admin):
    """Get admin authentication tokens (via service, not HTTP, to avoid rate limit)."""
    from ibreeze_backend.auth.service import admin_login

    tokens = await admin_login(
        db_session,
        test_admin.username,
        "admin123456",
        _uuid.uuid4(),
    )
    await db_session.commit()
    return {
        "access_token": tokens["access_token"],
        "refresh_token": tokens["refresh_token"],
    }


@pytest_asyncio.fixture
async def user_tokens(db_session: AsyncSession, test_user):
    """Get user authentication tokens (via service, not HTTP)."""
    from ibreeze_backend.auth.service import APP_AUDIENCE, login

    tokens = await login(
        db_session,
        test_user.email,
        "testpassword123",
        APP_AUDIENCE,
        _uuid.uuid4(),
    )
    await db_session.commit()
    return {
        "access_token": tokens["access_token"],
        "refresh_token": tokens["refresh_token"],
    }
