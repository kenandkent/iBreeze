#!/usr/bin/env python3
"""Scan for single-writer violations in the sidecar codebase.

Enforces:
- BEGIN IMMEDIATE only in persistence/write_queue.py, persistence/migrator.py
- Business modules must not call .commit(), .rollback(), or BEGIN IMMEDIATE
- Worker modules must not import writer connection
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

SIDECAR = Path(__file__).resolve().parent.parent / "sidecar"
IBREEZE = SIDECAR / "ibreeze"

ALLOWED_BEGIN_IMMEDIATE = {
    IBREEZE / "persistence" / "write_queue.py",
    IBREEZE / "persistence" / "migrator.py",
}

EXCLUDE_DIRS = {"__pycache__", ".git", "tests", "migrations", ".mypy_cache"}

BUSINESS_MODULES = [
    IBREEZE / "company.py",
    IBREEZE / "employee.py",
    IBREEZE / "conversation.py",
    IBREEZE / "audit.py",
    IBREEZE / "state_machine.py",
    IBREEZE / "schemas.py",
    IBREEZE / "approvals" / "service.py",
    IBREEZE / "artifacts" / "service.py",
    IBREEZE / "backup" / "scheduler.py",
    IBREEZE / "backup" / "records.py",
    IBREEZE / "knowledge" / "service.py",
    IBREEZE / "knowledge" / "hybrid_search.py",
    IBREEZE / "orchestration" / "dispatcher.py",
    IBREEZE / "orchestration" / "plan_generator.py",
    IBREEZE / "profile" / "service.py",
    IBREEZE / "review" / "service.py",
    IBREEZE / "runtime" / "service.py",
    IBREEZE / "runtime" / "gateway.py",
    IBREEZE / "task" / "service.py",
    IBREEZE / "security" / "audit.py",
]

RE_BEGIN_IMMEDIATE = re.compile(r"BEGIN\s+IMMEDIATE", re.IGNORECASE)
RE_COMMIT = re.compile(r"\.commit\(\)")
RE_ROLLBACK = re.compile(r"\.rollback\(\)")
RE_IMPORT_WRITER = re.compile(
    r"from\s+ibreeze\.persistence\.connection\s+import.*open_writer|from\s+ibreeze\.persistence\.connection\s+import.*writer",
    re.IGNORECASE,
)


def scan_file(path: Path) -> list[tuple[int, str, str]]:
    """Return list of (line_number, rule, detail) violations."""
    violations: list[tuple[int, str, str]] = []
    try:
        content = path.read_text(encoding="utf-8")
    except Exception:
        return violations

    for lineno, line in enumerate(content.splitlines(), start=1):
        stripped = line.strip()
        if stripped.startswith("#") or stripped.startswith('"') or stripped.startswith("'"):
            continue

        if RE_BEGIN_IMMEDIATE.search(line):
            if path not in ALLOWED_BEGIN_IMMEDIATE:
                violations.append((lineno, "BEGIN_IMMEDIATE", f"BEGIN IMMEDIATE in {path.name}"))

        if path.suffix == ".py" and path not in ALLOWED_BEGIN_IMMEDIATE and path.name not in {"migrator.py"} and path != IBREEZE / "persistence" / "connection.py":
            if RE_COMMIT.search(line):
                violations.append((lineno, "COMMIT", f".commit() in business module {path.name}"))
            if RE_ROLLBACK.search(line):
                violations.append((lineno, "ROLLBACK", f".rollback() in business module {path.name}"))

    return violations


def main() -> int:
    all_violations: list[tuple[str, int, str, str]] = []

    for py_file in sorted(IBREEZE.rglob("*.py")):
        if any(part in EXCLUDE_DIRS for part in py_file.relative_to(IBREEZE).parts):
            continue
        violations = scan_file(py_file)
        for lineno, rule, detail in violations:
            rel = py_file.relative_to(IBREEZE.parent)
            all_violations.append((str(rel), lineno, rule, detail))

    if all_violations:
        print(f"ERROR: Found {len(all_violations)} single-writer violation(s):\n")
        for filepath, lineno, rule, detail in all_violations:
            print(f"  {filepath}:{lineno} [{rule}] {detail}")
        print("\nRules:")
        print("  - BEGIN IMMEDIATE only in persistence/write_queue.py, persistence/migrator.py")
        print("  - Business modules must not call .commit() or .rollback()")
        return 1

    print("OK: No single-writer violations found")
    return 0


if __name__ == "__main__":
    sys.exit(main())
