#!/usr/bin/env python3
"""Check coverage exclusions are valid."""
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).parent.parent
EXCLUSIONS_FILE = ROOT / "coverage-exclusions.yml"


def main() -> int:
    if not EXCLUSIONS_FILE.exists():
        print(f"FAIL: {EXCLUSIONS_FILE} not found")
        return 1

    with open(EXCLUSIONS_FILE) as f:
        data = yaml.safe_load(f)

    if not data or "exclusions" not in data:
        print("FAIL: no exclusions defined")
        return 1

    errors = 0
    for i, exclusion in enumerate(data["exclusions"]):
        required_fields = ["path", "reason", "design_reference", "approved_by"]
        for field in required_fields:
            if field not in exclusion:
                print(f"FAIL: exclusion {i} missing field '{field}'")
                errors += 1
                continue

        path = exclusion["path"]
        reason = exclusion["reason"]

        # Check path doesn't use directory-level wildcard for business logic
        if path.endswith("/*") and "business" in reason.lower():
            print(f"FAIL: exclusion {i} uses directory wildcard for business logic: {path}")
            errors += 1

        # Check reason is not empty
        if not reason.strip():
            print(f"FAIL: exclusion {i} has empty reason")
            errors += 1

    if errors > 0:
        print(f"\n{errors} validation errors")
        return 1

    print(f"OK: {len(data['exclusions'])} exclusions validated")
    return 0


if __name__ == "__main__":
    sys.exit(main())
