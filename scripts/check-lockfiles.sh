#!/bin/bash
set -euo pipefail

echo "=== Checking Lockfiles ==="

cd "$(dirname "$0")/.."

# Check npm lockfiles
for pkg in apps/desktop apps/admin-web tests/e2e packages/contracts; do
    if [ -f "$pkg/package.json" ]; then
        if [ ! -f "$pkg/package-lock.json" ]; then
            echo "FAIL: $pkg/package-lock.json not found"
            exit 1
        fi
        echo "OK: $pkg lockfile exists"
    fi
done

# Check Cargo.lock
if [ -f "apps/desktop-core/Cargo.toml" ]; then
    if [ ! -f "apps/desktop-core/Cargo.lock" ]; then
        echo "FAIL: apps/desktop-core/Cargo.lock not found"
        exit 1
    fi
    echo "OK: desktop-core lockfile exists"
fi

# Check uv.lock
for pkg in sidecar apps/backend-api; do
    if [ -f "$pkg/pyproject.toml" ]; then
        if [ ! -f "$pkg/uv.lock" ]; then
            echo "FAIL: $pkg/uv.lock not found"
            exit 1
        fi
        echo "OK: $pkg lockfile exists"
    fi
done

echo "=== All lockfiles present ==="
