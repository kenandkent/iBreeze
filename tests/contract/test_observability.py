"""Tests for observability, security and performance - P11."""
import pytest
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
SIDECAR_DIR = ROOT / "sidecar"


def test_logging_config_exists():
    assert (SIDECAR_DIR / "ibreeze" / "logging_config.py").exists()


def test_security_config_exists():
    assert (SIDECAR_DIR / "ibreeze" / "security_config.py").exists()


def test_performance_exists():
    assert (SIDECAR_DIR / "ibreeze" / "performance.py").exists()


def test_logging_config_is_valid():
    init_path = SIDECAR_DIR / "ibreeze" / "logging_config.py"
    content = init_path.read_text()
    compile(content, str(init_path), "exec")
    assert "def setup_logging" in content
    assert "def get_logger" in content


def test_security_config_is_valid():
    init_path = SIDECAR_DIR / "ibreeze" / "security_config.py"
    content = init_path.read_text()
    compile(content, str(init_path), "exec")
    assert "def generate_api_key" in content
    assert "def validate_api_key" in content
    assert "class SecurityConfig" in content


def test_performance_is_valid():
    init_path = SIDECAR_DIR / "ibreeze" / "performance.py"
    content = init_path.read_text()
    compile(content, str(init_path), "exec")
    assert "class PerformanceMetrics" in content
    assert "def track_performance" in content
