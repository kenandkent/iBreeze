"""Tests for catalog release, manifest and emergency disable - P1-T06."""
import pytest
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
BACKEND_DIR = ROOT / "apps" / "backend-api"


def test_catalog_release_model_exists():
    assert (BACKEND_DIR / "src" / "ibreeze_backend" / "models" / "catalog_release.py").exists()


def test_catalog_service_exists():
    assert (BACKEND_DIR / "src" / "ibreeze_backend" / "services" / "catalog_service.py").exists()


def test_catalog_release_model_is_valid():
    """Verify catalog_release model compiles."""
    init_path = BACKEND_DIR / "src" / "ibreeze_backend" / "models" / "catalog_release.py"
    content = init_path.read_text()
    compile(content, str(init_path), "exec")
    assert "class CatalogRelease" in content
    assert "version" in content
    assert "manifest" in content
    assert "status" in content


def test_catalog_service_is_valid():
    """Verify catalog_service compiles and has required functions."""
    init_path = BACKEND_DIR / "src" / "ibreeze_backend" / "services" / "catalog_service.py"
    content = init_path.read_text()
    compile(content, str(init_path), "exec")
    assert "async def generate_manifest" in content
    assert "async def create_release" in content
    assert "async def publish_release" in content
    assert "async def emergency_disable_skill" in content
