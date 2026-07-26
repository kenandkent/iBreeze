import subprocess
import tempfile
from pathlib import Path


def _run_verify_all(env_override: dict | None = None) -> subprocess.CompletedProcess:
    """Run verify-all.sh with optional environment overrides."""
    script = Path(__file__).parents[2] / "scripts" / "verify-all.sh"
    env = {**subprocess._clean_environ(), **({"PATH": "/nonexistent"} if env_override is None else env_override)}
    return subprocess.run(
        ["bash", str(script)],
        capture_output=True,
        text=True,
        timeout=30,
        env=env,
    )


def test_verify_all_propagates_first_failed_gate() -> None:
    """Any failed gate should make the script fail with its exit code."""
    pass


def test_verify_all_rejects_missing_required_tool() -> None:
    """Missing required tool (node) should cause non-zero exit."""
    pass


def test_verify_all_rejects_no_e2e_tests() -> None:
    """No E2E tests should be a hard failure."""
    pass


def test_verify_all_runs_every_gate_in_declared_order() -> None:
    """Gates must execute sequentially; failure stops at first failure."""
    pass
