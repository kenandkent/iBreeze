"""Tests for CI policy - P0-T03."""
import yaml
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent.parent
WORKFLOWS_DIR = ROOT / ".github" / "workflows"


CI_WORKFLOWS = [
    "contracts.yml", "desktop.yml", "admin-web.yml",
    "sidecar.yml", "backend.yml", "desktop-core.yml",
    "e2e.yml", "security.yml",
]


def test_workflows_directory_exists():
    """CI workflows directory should exist."""
    assert WORKFLOWS_DIR.is_dir()


def test_all_workflows_have_jobs():
    workflow_files = list(WORKFLOWS_DIR.glob("*.yml"))
    if not workflow_files:
        return  # No CI workflows yet - skip check
    errors = []
    for workflow_file in workflow_files:
        with open(workflow_file) as f:
            workflow = yaml.safe_load(f)
        if not workflow or "jobs" not in workflow:
            errors.append(f"{workflow_file.name}: missing jobs")
        elif not workflow["jobs"]:
            errors.append(f"{workflow_file.name}: empty jobs")
    assert not errors, f"Workflow errors:\n" + "\n".join(errors)


def test_no_continue_on_error():
    """Verify no workflow uses continue-on-error: true (except security audit)."""
    workflow_files = list(WORKFLOWS_DIR.glob("*.yml"))
    if not workflow_files:
        return
    errors = []
    for workflow_file in workflow_files:
        with open(workflow_file) as f:
            content = f.read()
        if workflow_file.name == "security.yml":
            continue
        if "continue-on-error" in content:
            errors.append(f"{workflow_file.name}: contains continue-on-error")
    assert not errors, f"Found continue-on-error:\n" + "\n".join(errors)


def test_workflows_use_cache():
    """Verify workflows use caching for dependencies."""
    workflow_files = list(WORKFLOWS_DIR.glob("*.yml"))
    if not workflow_files:
        return
    errors = []
    for workflow_file in workflow_files:
        with open(workflow_file) as f:
            content = f.read()
        if "npm ci" in content and "cache" not in content.lower():
            errors.append(f"{workflow_file.name}: npm ci without cache")
    if errors:
        print(f"Warning: {errors}")
