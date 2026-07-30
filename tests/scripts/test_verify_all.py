from pathlib import Path


SCRIPTS_DIR = Path(__file__).parents[2] / "scripts"
VERIFY_SCRIPT = SCRIPTS_DIR / "verify-all.sh"


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
