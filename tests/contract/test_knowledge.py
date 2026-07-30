"""Tests for knowledge, search and backup domain - P8."""

from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
SIDECAR_DIR = ROOT / "sidecar"


def test_knowledge_exists():
    assert (SIDECAR_DIR / "ibreeze" / "knowledge" / "__init__.py").exists()


def test_knowledge_is_valid():
    init_path = SIDECAR_DIR / "ibreeze" / "knowledge" / "__init__.py"
    content = init_path.read_text()
    compile(content, str(init_path), "exec")
    assert "import_knowledge" in content
    assert "list_knowledge" in content
    assert "get_knowledge" in content
    assert "search_knowledge" in content
    assert "remove_knowledge" in content
    assert "hybrid_search" in content
