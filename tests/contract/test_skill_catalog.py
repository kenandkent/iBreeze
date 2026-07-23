"""Tests for skill catalog entities and compatibility - P1-T04."""
import pytest
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
BACKEND_DIR = ROOT / "apps" / "backend-api"


def test_skill_model_exists():
    assert (BACKEND_DIR / "src" / "ibreeze_backend" / "models" / "skill.py").exists()


def test_skill_schema_exists():
    assert (BACKEND_DIR / "src" / "ibreeze_backend" / "schemas" / "skill.py").exists()


def test_skill_service_exists():
    assert (BACKEND_DIR / "src" / "ibreeze_backend" / "services" / "skill_service.py").exists()


def test_skill_model_is_valid():
    """Verify skill model compiles."""
    init_path = BACKEND_DIR / "src" / "ibreeze_backend" / "models" / "skill.py"
    content = init_path.read_text()
    compile(content, str(init_path), "exec")
    assert "class Skill" in content
    assert "name" in content
    assert "version" in content
    assert "compatibility" in content


def test_skill_schema_is_valid():
    """Verify skill schema compiles."""
    init_path = BACKEND_DIR / "src" / "ibreeze_backend" / "schemas" / "skill.py"
    content = init_path.read_text()
    compile(content, str(init_path), "exec")
    assert "class SkillCreate" in content
    assert "class SkillResponse" in content


def test_skill_service_is_valid():
    """Verify skill_service compiles and has required functions."""
    init_path = BACKEND_DIR / "src" / "ibreeze_backend" / "services" / "skill_service.py"
    content = init_path.read_text()
    compile(content, str(init_path), "exec")
    assert "async def create_skill" in content
    assert "async def get_skill" in content
    assert "async def list_skills" in content
    assert "async def check_compatibility" in content
