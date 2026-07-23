"""Test configuration and fixtures."""
import asyncio
import uuid as _uuid
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.dialects.postgresql import INET as PG_INET, JSONB, UUID as PG_UUID
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker

from ibreeze_backend.db.session import Base
from ibreeze_backend.main import app


# Allow PostgreSQL-specific types to work with SQLite in tests
@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(element, compiler, **kw):
    return "JSON"


@compiles(PG_UUID, "sqlite")
def _compile_uuid_sqlite(element, compiler, **kw):
    return "CHAR(32)"


@compiles(PG_INET, "sqlite")
def _compile_inet_sqlite(element, compiler, **kw):
    return "VARCHAR(45)"


# Patch PostgreSQL UUID bind/result processors for SQLite compatibility
_orig_bind = PG_UUID.bind_processor
_orig_result = PG_UUID.result_processor


def _patched_bind(self, dialect):
    if dialect.name == "sqlite":
        def process(value):
            if value is not None:
                if isinstance(value, _uuid.UUID):
                    return value.hex
                return _uuid.UUID(value).hex
            return None
        return process
    return _orig_bind(self, dialect)


def _patched_result(self, dialect, coltype):
    if dialect.name == "sqlite":
        def process(value):
            if value is not None:
                return _uuid.UUID(value) if isinstance(value, str) else value
            return None
        return process
    return _orig_result(self, dialect, coltype)


PG_UUID.bind_processor = _patched_bind
PG_UUID.result_processor = _patched_result

# Patch SQLite DateTime result processor to always return timezone-aware (UTC) datetimes
import datetime as _datetime
from sqlalchemy.dialects.sqlite import DATETIME as SQLITE_DATETIME

_orig_sqlite_dt_result = SQLITE_DATETIME.result_processor


def _patched_sqlite_dt_result(self, dialect, coltype):
    impl = _orig_sqlite_dt_result(self, dialect, coltype)
    if impl is None:
        return None

    def _process(value):
        dt = impl(value)
        if dt is not None and dt.tzinfo is None:
            dt = dt.replace(tzinfo=_datetime.timezone.utc)
        return dt

    return _process


SQLITE_DATETIME.result_processor = _patched_sqlite_dt_result


# 使用内存数据库进行测试
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="function")
async def db_engine():
    """Create a test database engine."""
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def db_session(db_engine) -> AsyncGenerator[AsyncSession, None]:
    """Create a test database session."""
    async_session = sessionmaker(
        db_engine, class_=AsyncSession, expire_on_commit=False
    )
    async with async_session() as session:
        yield session


@pytest_asyncio.fixture(scope="function")
async def client(db_session, db_engine) -> AsyncGenerator[AsyncClient, None]:
    """Create a test HTTP client."""
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from ibreeze_backend.db.session import get_db_session
    from ibreeze_backend.middleware.ratelimit import reset_rate_limiter
    import ibreeze_backend.middleware.audit as audit_mod

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db_session] = override_get_db

    # Point audit middleware at the test database
    audit_mod.async_session_factory = async_sessionmaker(
        db_engine, expire_on_commit=False
    )

    reset_rate_limiter()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def test_user(db_session: AsyncSession):
    """Create a test user."""
    from ibreeze_backend.auth.service import register, login

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
    from ibreeze_backend.models.user import User
    from passlib.hash import argon2

    admin = User(
        username=f"admin_{_uuid.uuid4().hex[:8]}",
        email=f"admin_{_uuid.uuid4().hex[:8]}@example.com",
        hashed_password=argon2.hash("admin123456"),
        user_type="admin",
        protected=True,
        is_active=True,
    )
    db_session.add(admin)
    await db_session.commit()
    await db_session.refresh(admin)
    return admin


@pytest_asyncio.fixture
async def admin_tokens(db_session: AsyncSession, test_admin):
    """Get admin authentication tokens (via service, not HTTP, to avoid rate limit)."""
    from ibreeze_backend.auth.service import admin_login

    tokens = await admin_login(db_session, test_admin.email, "admin123456")
    await db_session.commit()
    return {
        "access_token": tokens["access_token"],
        "refresh_token": tokens["refresh_token"],
    }


@pytest_asyncio.fixture
async def user_tokens(db_session: AsyncSession, test_user):
    """Get user authentication tokens (via service, not HTTP)."""
    from ibreeze_backend.auth.service import login

    tokens = await login(db_session, test_user.email, "testpassword123", "app")
    await db_session.commit()
    return {
        "access_token": tokens["access_token"],
        "refresh_token": tokens["refresh_token"],
    }
