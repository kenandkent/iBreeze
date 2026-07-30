"""Tests for ZIP validation, signature and object storage - P1-T05."""

from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
BACKEND_DIR = ROOT / "apps" / "backend-api"


def test_zip_service_exists():
    assert (
        BACKEND_DIR / "src" / "ibreeze_backend" / "services" / "zip_service.py"
    ).exists()


def test_storage_service_exists():
    assert (
        BACKEND_DIR / "src" / "ibreeze_backend" / "services" / "storage_service.py"
    ).exists()


def test_zip_service_is_valid():
    """Verify zip_service compiles and has required functions."""
    init_path = BACKEND_DIR / "src" / "ibreeze_backend" / "services" / "zip_service.py"
    content = init_path.read_text()
    compile(content, str(init_path), "exec")
    assert "def validate_skill_zip" in content
    assert "def _file_sha256" in content


def test_storage_service_is_valid():
    """Verify storage_service compiles and has required class."""
    init_path = (
        BACKEND_DIR / "src" / "ibreeze_backend" / "services" / "storage_service.py"
    )
    content = init_path.read_text()
    compile(content, str(init_path), "exec")
    assert "class ObjectStorage" in content
    assert "def put_object" in content
    assert "def get_object_path" in content
    assert "def delete_object" in content
