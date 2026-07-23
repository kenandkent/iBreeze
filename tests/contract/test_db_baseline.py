"""Tests for PostgreSQL, SQLAlchemy and Alembic baseline - P1-T01."""
import pytest
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
BACKEND_DIR = ROOT / "apps" / "backend-api"


def test_settings_exists():
    assert (BACKEND_DIR / "src" / "ibreeze_backend" / "settings.py").exists()


def test_db_session_exists():
    assert (BACKEND_DIR / "src" / "ibreeze_backend" / "db" / "session.py").exists()


def test_db_init_exists():
    assert (BACKEND_DIR / "src" / "ibreeze_backend" / "db" / "__init__.py").exists()


def test_models_base_exists():
    assert (BACKEND_DIR / "src" / "ibreeze_backend" / "models" / "base.py").exists()


def test_models_init_exists():
    assert (BACKEND_DIR / "src" / "ibreeze_backend" / "models" / "__init__.py").exists()


def test_alembic_ini_exists():
    assert (BACKEND_DIR / "alembic.ini").exists()


def test_alembic_versions_exists():
    versions_dir = BACKEND_DIR / "alembic" / "versions"
    assert versions_dir.exists()
    migrations = list(versions_dir.glob("*.py"))
    assert len(migrations) > 0, "No migrations found"


def test_initial_migration_exists():
    assert (BACKEND_DIR / "alembic" / "versions" / "001_initial.py").exists()


def test_settings_is_valid():
    """Verify settings.py compiles and has Settings class."""
    init_path = BACKEND_DIR / "src" / "ibreeze_backend" / "settings.py"
    content = init_path.read_text()
    compile(content, str(init_path), "exec")
    assert "class Settings" in content
    assert "database_url" in content


def test_db_session_is_valid():
    """Verify session.py compiles."""
    init_path = BACKEND_DIR / "src" / "ibreeze_backend" / "db" / "session.py"
    content = init_path.read_text()
    compile(content, str(init_path), "exec")
    assert "class Base" in content
    assert "get_db_session" in content


def test_models_base_is_valid():
    """Verify models/base.py compiles."""
    init_path = BACKEND_DIR / "src" / "ibreeze_backend" / "models" / "base.py"
    content = init_path.read_text()
    compile(content, str(init_path), "exec")
    assert "class TimestampMixin" in content
    assert "class UUIDPrimaryKeyMixin" in content
