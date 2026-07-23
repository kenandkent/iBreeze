"""Tests for backend user management - P1-T03."""
import pytest
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
BACKEND_DIR = ROOT / "apps" / "backend-api"


def test_user_schema_exists():
    assert (BACKEND_DIR / "src" / "ibreeze_backend" / "schemas" / "user.py").exists()


def test_user_service_exists():
    assert (BACKEND_DIR / "src" / "ibreeze_backend" / "services" / "user_service.py").exists()


def test_users_router_exists():
    assert (BACKEND_DIR / "src" / "ibreeze_backend" / "routers" / "users.py").exists()


def test_user_schema_is_valid():
    """Verify user schema compiles."""
    init_path = BACKEND_DIR / "src" / "ibreeze_backend" / "schemas" / "user.py"
    content = init_path.read_text()
    compile(content, str(init_path), "exec")
    assert "class UserCreate" in content
    assert "class UserResponse" in content


def test_user_service_is_valid():
    """Verify user_service compiles."""
    init_path = BACKEND_DIR / "src" / "ibreeze_backend" / "services" / "user_service.py"
    content = init_path.read_text()
    compile(content, str(init_path), "exec")
    assert "async def create_user" in content
    assert "async def get_user" in content
    assert "async def list_users" in content
    assert "async def update_user" in content
    assert "async def delete_user" in content


def test_users_router_is_valid():
    """Verify users router compiles."""
    init_path = BACKEND_DIR / "src" / "ibreeze_backend" / "routers" / "users.py"
    content = init_path.read_text()
    compile(content, str(init_path), "exec")
    assert "@router.post" in content
    assert "@router.get" in content
    assert "@router.put" in content
    assert "@router.delete" in content
