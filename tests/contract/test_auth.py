"""Tests for authentication, token family and offline tokens - P1-T02."""
import pytest
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
BACKEND_DIR = ROOT / "apps" / "backend-api"


def test_user_model_exists():
    assert (BACKEND_DIR / "src" / "ibreeze_backend" / "models" / "user.py").exists()


def test_token_family_model_exists():
    assert (BACKEND_DIR / "src" / "ibreeze_backend" / "models" / "token_family.py").exists()


def test_token_service_exists():
    assert (BACKEND_DIR / "src" / "ibreeze_backend" / "services" / "token_service.py").exists()


def test_dependencies_exists():
    assert (BACKEND_DIR / "src" / "ibreeze_backend" / "dependencies.py").exists()


def test_user_model_is_valid():
    """Verify user model compiles."""
    init_path = BACKEND_DIR / "src" / "ibreeze_backend" / "models" / "user.py"
    content = init_path.read_text()
    compile(content, str(init_path), "exec")
    assert "class User" in content
    assert "username" in content
    assert "hashed_password" in content


def test_token_family_model_is_valid():
    """Verify token_family model compiles."""
    init_path = BACKEND_DIR / "src" / "ibreeze_backend" / "models" / "token_family.py"
    content = init_path.read_text()
    compile(content, str(init_path), "exec")
    assert "class TokenFamily" in content
    assert "family_id" in content
    assert "status" in content


def test_token_service_is_valid():
    """Verify token_service compiles and has required functions."""
    init_path = BACKEND_DIR / "src" / "ibreeze_backend" / "services" / "token_service.py"
    content = init_path.read_text()
    compile(content, str(init_path), "exec")
    assert "create_access_token" in content
    assert "verify_token" in content
    assert "async def create_token_family" in content
    assert "async def rotate_token" in content
    assert "async def revoke_family" in content
