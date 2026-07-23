"""Shared fixtures for functional tests."""
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

_backend_root = Path(__file__).resolve().parents[2] / "apps" / "backend-api" / "src"
_sidecar_root = Path(__file__).resolve().parents[2] / "sidecar"
for _p in (_backend_root, _sidecar_root):
    _ps = str(_p)
    if _ps not in sys.path:
        sys.path.insert(0, _ps)


@pytest.fixture
def mock_db_session():
    """Create a mock async database session."""
    session = AsyncMock()
    session.execute = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.delete = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    return session


@pytest.fixture
def mock_scalar_result():
    """Factory for mock scalar query results."""

    def _factory(value):
        result = MagicMock()
        result.scalar_one_or_none.return_value = value
        result.scalar.return_value = value
        return result

    return _factory


@pytest.fixture
def mock_scalars_result():
    """Factory for mock multi-row query results."""

    def _factory(items):
        result = MagicMock()
        scalars = MagicMock()
        scalars.all.return_value = items
        result.scalars.return_value = scalars
        return result

    return _factory


@pytest.fixture
def mock_user():
    """Mock admin user for testing."""
    user = MagicMock()
    user.id = "00000000-0000-0000-0000-000000000001"
    user.email = "admin@ibreeze.local"
    user.username = "admin"
    user.user_type = "admin"
    user.role = "admin"
    user.is_active = True
    user.protected = True
    user.hashed_password = "$argon2id$..."
    return user


@pytest.fixture
def mock_app_user():
    """Mock app_user for testing."""
    user = MagicMock()
    user.id = "00000000-0000-0000-0000-000000000002"
    user.email = "app@ibreeze.local"
    user.username = "app_user"
    user.user_type = "app_user"
    user.role = "user"
    user.is_active = True
    user.protected = False
    user.hashed_password = "$argon2id$..."
    return user


@pytest.fixture
def admin_headers():
    """Authorization headers for admin requests."""
    return {"Authorization": "Bearer mock_admin_token"}


@pytest.fixture
def app_headers():
    """Authorization headers for app user requests."""
    return {"Authorization": "Bearer mock_app_token"}
