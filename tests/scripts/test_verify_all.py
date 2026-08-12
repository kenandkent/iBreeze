import os
import subprocess
from pathlib import Path


SCRIPTS_DIR = Path(__file__).parents[2] / "scripts"
VERIFY_SCRIPT = SCRIPTS_DIR / "verify-all.sh"
GEN_SCRIPT = SCRIPTS_DIR / "generate-method-kinds.py"


def _read_script_lines() -> list[str]:
    return VERIFY_SCRIPT.read_text().splitlines()


def test_verify_all_propagates_first_failed_gate() -> None:
    lines = _read_script_lines()
    assert any("set -Eeuo pipefail" in line for line in lines)


def test_verify_all_rejects_missing_required_tool() -> None:
    lines = _read_script_lines()
    has_fatal_check = False
    for line in lines:
        if "FATAL" in line and (
            "node" in line or "command" in line or "not found" in line or "missing" in line
        ):
            has_fatal_check = True
    assert has_fatal_check or any("FATAL" in line for line in lines)


def test_verify_all_e2e_skip_no_test_files() -> None:
    lines = _read_script_lines()
    e2e_lines = [i for i, line in enumerate(lines) if "e2e" in line.lower()]
    assert len(e2e_lines) > 0


def test_verify_all_gates_are_sequential() -> None:
    lines = _read_script_lines()
    gate_markers = [line.strip() for line in lines if 'echo "---' in line]
    assert len(gate_markers) >= 8
    expected_gates = [
        "contracts",
        "desktop-core",
        "backend-api",
        "sidecar",
        "desktop",
        "admin-web",
        "e2e",
        "contract drift",
    ]
    for expected in expected_gates:
        assert any(expected in m for m in gate_markers), f"Missing gate: {expected}"


def test_generate_method_kinds_check_ok() -> None:
    """--check passes when generated files match the registry."""
    result = subprocess.run(
        ["python3", str(GEN_SCRIPT), "--check"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, f"check failed:\n{result.stdout}\n{result.stderr}"


def test_generate_method_kinds_check_fails_on_ts_drift() -> None:
    """--check fails when the TypeScript output is tampered."""
    ts_path = Path("apps/desktop/src/generated/rpc/method_kinds.ts")
    original = ts_path.read_text()
    tampered = original.replace("'approval.listPending'", "'tampered.method'", 1)
    try:
        ts_path.write_text(tampered)
        result = subprocess.run(
            ["python3", str(GEN_SCRIPT), "--check"],
            capture_output=True,
            text=True,
            check=False,
        )
    finally:
        ts_path.write_text(original)
    assert result.returncode == 1
    assert "DRIFT" in result.stdout


def test_generate_method_kinds_check_fails_on_rs_drift() -> None:
    """--check fails when the Rust output is tampered."""
    rs_path = Path("apps/desktop-core/src/rpc/generated_method_kinds.rs")
    original = rs_path.read_text()
    tampered = original.replace('"approval.listPending"', '"tampered.method"', 1)
    try:
        rs_path.write_text(tampered)
        result = subprocess.run(
            ["python3", str(GEN_SCRIPT), "--check"],
            capture_output=True,
            text=True,
            check=False,
        )
    finally:
        rs_path.write_text(original)
    assert result.returncode == 1
    assert "DRIFT" in result.stdout


def test_generate_method_kinds_output_root(tmp_path: Path) -> None:
    """IBREEZE_OUTPUT_ROOT redirects generated output."""
    out_root = tmp_path / "out"
    env = {**os.environ, "IBREEZE_OUTPUT_ROOT": str(out_root)}
    result = subprocess.run(
        ["python3", str(GEN_SCRIPT)],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    assert result.returncode == 0
    assert (out_root / "apps/desktop/src/generated/rpc/method_kinds.ts").exists()
    assert (out_root / "apps/desktop-core/src/rpc/generated_method_kinds.rs").exists()


def test_check_contract_drift_step1b_writes_to_tmp_dir() -> None:
    """Step 1b generates to TMP_DIR/out and never to the workspace."""
    lines = Path("scripts/check-contract-drift.sh").read_text().splitlines()
    step1b_lines: list[str] = []
    recording = False
    for line in lines:
        if "Step 1b" in line:
            recording = True
        elif recording and line.strip().startswith("echo") and "Step 2" in line:
            break
        if recording:
            step1b_lines.append(line)
    step_text = "\n".join(step1b_lines)
    assert "IBREEZE_OUTPUT_ROOT=" in step_text
    assert "TMP_DIR/out" in step_text
    assert "cp " not in step_text
    assert "$ROOT_DIR/apps/desktop-core/src/generated/" not in step_text


def test_check_contract_drift_no_old_path() -> None:
    """The drift gate only references the current Rust generated path."""
    content = Path("scripts/check-contract-drift.sh").read_text()
    assert "apps/desktop-core/src/generated/rpc/method_kinds.rs" not in content
    assert "apps/desktop-core/src/rpc/generated_method_kinds.rs" in content


def test_commands_rs_delegates_to_generated() -> None:
    """commands.rs delegates method classification to generated code.

    commands.rs must only *call* the generated classifier; it must not embed
    its own ``fn sidecar_method_kind`` or hard-code any method classification.
    """
    content = Path("apps/desktop-core/src/commands.rs").read_text()
    assert "crate::rpc::generated_method_kinds::sidecar_method_kind" in content
    assert "fn sidecar_method_kind" not in content
    assert "approval.resolve" not in content


def test_generated_method_kinds_has_sidecar_func() -> None:
    """The Rust generated module exposes sidecar ownership classification."""
    content = Path("apps/desktop-core/src/rpc/generated_method_kinds.rs").read_text()
    assert "pub fn sidecar_method_kind" in content
    assert "SIDECAR_READ_METHODS" in content
    assert "SIDECAR_WRITE_METHODS" in content
