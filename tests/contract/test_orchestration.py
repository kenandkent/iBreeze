"""Tests for Agent Orchestration Platform - P7."""
import pytest
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
SIDECAR_DIR = ROOT / "sidecar"


def test_orchestration_exists():
    assert (SIDECAR_DIR / "ibreeze" / "orchestration.py").exists()


def test_orchestration_is_valid():
    init_path = SIDECAR_DIR / "ibreeze" / "orchestration.py"
    content = init_path.read_text()
    compile(content, str(init_path), "exec")
    assert "def create_orchestration" in content
    assert "def list_orchestrations" in content
    assert "def get_orchestration" in content
    assert "def add_node" in content
    assert "def add_edge" in content
