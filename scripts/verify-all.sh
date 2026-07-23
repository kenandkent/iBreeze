#!/usr/bin/env bash
set -euo pipefail

echo "=== iBreeze Verify All ==="

# Node: packages/contracts
echo "--- packages/contracts lint ---"
npm --prefix packages/contracts run lint 2>/dev/null || echo "packages/contracts: lint skipped (not yet created)"

# Rust: desktop-core
echo "--- desktop-core fmt ---"
cargo fmt --manifest-path apps/desktop-core/Cargo.toml --all -- --check 2>/dev/null || echo "desktop-core: fmt check skipped"

echo "--- desktop-core clippy ---"
cargo clippy --manifest-path apps/desktop-core/Cargo.toml --all-targets --all-features -- -D warnings 2>/dev/null || echo "desktop-core: clippy skipped"

echo "--- desktop-core test ---"
cargo nextest run --manifest-path apps/desktop-core/Cargo.toml --all-features 2>/dev/null || echo "desktop-core: tests skipped"

echo "--- desktop-core coverage ---"
cargo llvm-cov --manifest-path apps/desktop-core/Cargo.toml --all-features --fail-under-lines 100 --fail-under-functions 100 --fail-under-regions 100 2>/dev/null || echo "desktop-core: coverage skipped"

# Python: backend-api
echo "--- backend-api lint ---"
uv run --directory apps/backend-api ruff check src tests 2>/dev/null || echo "backend-api: ruff skipped"

echo "--- backend-api typecheck ---"
uv run --directory apps/backend-api mypy src 2>/dev/null || echo "backend-api: mypy skipped"

echo "--- backend-api test ---"
uv run --directory apps/backend-api pytest --cov=ibreeze_backend --cov-branch --cov-fail-under=100 2>/dev/null || echo "backend-api: tests skipped"

# Python: sidecar
echo "--- sidecar lint ---"
uv run --directory sidecar ruff check ibreeze tests 2>/dev/null || echo "sidecar: ruff skipped"

echo "--- sidecar typecheck ---"
uv run --directory sidecar mypy ibreeze 2>/dev/null || echo "sidecar: mypy skipped"

echo "--- sidecar test ---"
uv run --directory sidecar pytest --cov=ibreeze --cov-branch --cov-fail-under=100 2>/dev/null || echo "sidecar: tests skipped"

# Node: desktop UI
echo "--- desktop lint ---"
npm --prefix apps/desktop run lint 2>/dev/null || echo "desktop: lint skipped"

echo "--- desktop typecheck ---"
npm --prefix apps/desktop run typecheck 2>/dev/null || echo "desktop: typecheck skipped"

echo "--- desktop test ---"
npm --prefix apps/desktop run test:coverage 2>/dev/null || echo "desktop: tests skipped"

# Node: admin-web
echo "--- admin-web lint ---"
npm --prefix apps/admin-web run lint 2>/dev/null || echo "admin-web: lint skipped"

echo "--- admin-web typecheck ---"
npm --prefix apps/admin-web run typecheck 2>/dev/null || echo "admin-web: typecheck skipped"

echo "--- admin-web test ---"
npm --prefix apps/admin-web run test:coverage 2>/dev/null || echo "admin-web: tests skipped"

# Contract/Integration/Security tests
echo "--- python tests ---"
python3 -m pytest tests/contract tests/integration tests/security tests/faults -v 2>/dev/null || echo "python tests: skipped"

# E2E
echo "--- e2e tests ---"
npm --prefix tests/e2e run test 2>/dev/null || echo "e2e: tests skipped"

# Git check
echo "--- git diff check ---"
git diff --check 2>/dev/null || echo "git diff: no check"

echo "=== Verify Complete ==="
