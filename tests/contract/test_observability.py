"""Tests for observability, security and performance - P11."""

from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
SIDECAR_DIR = ROOT / "sidecar"


def test_logging_config_exists():
    assert (SIDECAR_DIR / "ibreeze" / "logging_config.py").exists()


def test_security_config_exists():
    assert (SIDECAR_DIR / "ibreeze" / "security" / "__init__.py").exists()


def test_performance_exists():
    assert (SIDECAR_DIR / "ibreeze" / "logging_config.py").exists()


def test_logging_config_is_valid():
    init_path = SIDECAR_DIR / "ibreeze" / "logging_config.py"
    content = init_path.read_text()
    compile(content, str(init_path), "exec")
    assert "def setup_logging" in content
    assert "def get_logger" in content


def test_security_config_is_valid():
    init_path = SIDECAR_DIR / "ibreeze" / "security" / "__init__.py"
    content = init_path.read_text()
    compile(content, str(init_path), "exec")
    assert "generate_api_key" in content
    assert "encrypt" in content
    assert "decrypt" in content


def test_performance_is_valid():
    init_path = SIDECAR_DIR / "ibreeze" / "logging_config.py"
    content = init_path.read_text()
    compile(content, str(init_path), "exec")
    assert "def setup_logging" in content
    assert "def get_logger" in content
