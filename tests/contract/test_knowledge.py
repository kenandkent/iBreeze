"""Tests for knowledge, search and backup domain - P8."""
import pytest
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
SIDECAR_DIR = ROOT / "sidecar"


def test_knowledge_exists():
    assert (SIDECAR_DIR / "ibreeze" / "knowledge.py").exists()


def test_knowledge_is_valid():
    init_path = SIDECAR_DIR / "ibreeze" / "knowledge.py"
    content = init_path.read_text()
    compile(content, str(init_path), "exec")
    assert "def create_knowledge_entry" in content
    assert "def list_knowledge_entries" in content
    assert "def get_knowledge_entry" in content
    assert "def search_knowledge_entries" in content
    assert "def archive_knowledge_entry" in content
    assert "def get_knowledge_stats" in content
