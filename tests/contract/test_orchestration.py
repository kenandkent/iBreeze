"""Tests for Agent Orchestration Platform - P7."""

from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
SIDECAR_DIR = ROOT / "sidecar"


def test_orchestration_exists():
    assert (SIDECAR_DIR / "ibreeze" / "orchestration" / "__init__.py").exists()


def test_orchestration_is_valid():
    init_path = SIDECAR_DIR / "ibreeze" / "orchestration" / "__init__.py"
    content = init_path.read_text()
    compile(content, str(init_path), "exec")
    assert "generate_company_plan" in content
    assert "confirm_and_dispatch" in content
    assert "validate_plan" in content
    assert "ConfirmPlanCommand" in content
    assert "list_workflow_templates" in content
