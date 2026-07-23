"""Tests for CI policy - P0-T03."""
import yaml
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent.parent
WORKFLOWS_DIR = ROOT / ".github" / "workflows"


def test_contracts_workflow_exists():
    assert (WORKFLOWS_DIR / "contracts.yml").exists()


def test_desktop_workflow_exists():
    assert (WORKFLOWS_DIR / "desktop.yml").exists()


def test_admin_web_workflow_exists():
    assert (WORKFLOWS_DIR / "admin-web.yml").exists()


def test_sidecar_workflow_exists():
    assert (WORKFLOWS_DIR / "sidecar.yml").exists()


def test_backend_workflow_exists():
    assert (WORKFLOWS_DIR / "backend.yml").exists()


def test_desktop_core_workflow_exists():
    assert (WORKFLOWS_DIR / "desktop-core.yml").exists()


def test_e2e_workflow_exists():
    assert (WORKFLOWS_DIR / "e2e.yml").exists()


def test_security_workflow_exists():
    assert (WORKFLOWS_DIR / "security.yml").exists()


def test_all_workflows_have_jobs():
    errors = []
    for workflow_file in WORKFLOWS_DIR.glob("*.yml"):
        with open(workflow_file) as f:
            workflow = yaml.safe_load(f)
        if not workflow or "jobs" not in workflow:
            errors.append(f"{workflow_file.name}: missing jobs")
        elif not workflow["jobs"]:
            errors.append(f"{workflow_file.name}: empty jobs")
    assert not errors, f"Workflow errors:\n" + "\n".join(errors)


def test_no_continue_on_error():
    """Verify no workflow uses continue-on-error: true (except security audit)."""
    errors = []
    for workflow_file in WORKFLOWS_DIR.glob("*.yml"):
        with open(workflow_file) as f:
            content = f.read()
        # Security audit can use continue-on-error
        if workflow_file.name == "security.yml":
            continue
        if "continue-on-error" in content:
            errors.append(f"{workflow_file.name}: contains continue-on-error")
    assert not errors, f"Found continue-on-error:\n" + "\n".join(errors)


def test_workflows_use_cache():
    """Verify workflows use caching for dependencies."""
    errors = []
    for workflow_file in WORKFLOWS_DIR.glob("*.yml"):
        with open(workflow_file) as f:
            content = f.read()
        if "npm ci" in content and "cache" not in content.lower():
            errors.append(f"{workflow_file.name}: npm ci without cache")
    # Don't fail on this, just warn
    if errors:
        print(f"Warning: {errors}")
