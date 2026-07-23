"""Tests for backend health, container and deployment baseline - P1-T08."""
import pytest
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
BACKEND_DIR = ROOT / "apps" / "backend-api"


def test_health_router_exists():
    assert (BACKEND_DIR / "src" / "ibreeze_backend" / "routers" / "health.py").exists()


def test_main_exists():
    assert (BACKEND_DIR / "src" / "ibreeze_backend" / "main.py").exists()


def test_dockerfile_exists():
    assert (BACKEND_DIR / "Dockerfile").exists()


def test_docker_compose_exists():
    assert (ROOT / "docker-compose.yml").exists()


def test_health_router_is_valid():
    """Verify health router compiles."""
    init_path = BACKEND_DIR / "src" / "ibreeze_backend" / "routers" / "health.py"
    content = init_path.read_text()
    compile(content, str(init_path), "exec")
    assert "@router.get" in content
    assert "health_check" in content
    assert "readiness_check" in content


def test_main_is_valid():
    """Verify main.py compiles and creates FastAPI app."""
    init_path = BACKEND_DIR / "src" / "ibreeze_backend" / "main.py"
    content = init_path.read_text()
    compile(content, str(init_path), "exec")
    assert "FastAPI" in content
    assert "app = FastAPI" in content
    assert "include_router" in content


def test_dockerfile_is_valid():
    """Verify Dockerfile has required instructions."""
    content = (BACKEND_DIR / "Dockerfile").read_text()
    assert "FROM python:3.12" in content
    assert "WORKDIR" in content
    assert "EXPOSE" in content
    assert "CMD" in content
