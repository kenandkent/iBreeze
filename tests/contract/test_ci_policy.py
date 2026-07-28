"""Test CI workflow policy - ensure required workflows exist and are tracked in git."""

import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
GITHUB_WORKFLOWS_PREFIX = ".github/workflows"

REQUIRED_WORKFLOWS = {
    "ci.yml",
    "contracts.yml",
    "desktop.yml",
    "sidecar.yml",
    "backend.yml",
    "e2e.yml",
    "security.yml",
    "release.yml",
}


def test_ci_workflows_are_tracked_in_git() -> None:
    result = subprocess.run(
        ["git", "ls-files", f"{GITHUB_WORKFLOWS_PREFIX}/"],
        capture_output=True, text=True, cwd=REPO_ROOT,
    )
    assert result.returncode == 0, f"git ls-files failed: {result.stderr}"
    workflows = [f for f in result.stdout.strip().split("\n") if f.strip()]
    assert len(workflows) >= 8, (
        f"Expected at least 8 workflow files, found {len(workflows)}. "
        "All required CI workflows must exist and be committed."
    )


def test_required_workflows_exist() -> None:
    result = subprocess.run(
        ["git", "ls-files", f"{GITHUB_WORKFLOWS_PREFIX}/"],
        capture_output=True, text=True, cwd=REPO_ROOT,
    )
    workflows = {f.removeprefix(f"{GITHUB_WORKFLOWS_PREFIX}/") for f in result.stdout.strip().split("\n") if f.strip()}
    missing = REQUIRED_WORKFLOWS - workflows
    assert not missing, f"Required workflows missing from git tracking: {missing}"
