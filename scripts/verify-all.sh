#!/usr/bin/env bash
set -Eeuo pipefail
trap 'code=$?; echo "verify-all failed at line ${LINENO} with exit code ${code}" >&2; exit "${code}"' ERR

echo "=== iBreeze Verify All ==="

required_tools=(node npm cargo)
for tool in "${required_tools[@]}"; do
    if ! command -v "$tool" &>/dev/null; then
        echo "FATAL: required tool '$tool' not found" >&2
        exit 1
    fi
done

# Node: packages/contracts
echo "--- packages/contracts lint ---"
npm --prefix packages/contracts run lint

# Rust: desktop-core
echo "--- desktop-core fmt ---"
cargo fmt --manifest-path apps/desktop-core/Cargo.toml --all -- --check

echo "--- desktop-core clippy ---"
cargo clippy --manifest-path apps/desktop-core/Cargo.toml --all-targets --all-features -- -D warnings

echo "--- desktop-core test ---"
if command -v cargo-nextest &>/dev/null; then
    cargo nextest run --manifest-path apps/desktop-core/Cargo.toml --all-features
else
    echo "WARNING: cargo-nextest not found, falling back to cargo test"
    cargo test --manifest-path apps/desktop-core/Cargo.toml --all-features
fi

echo "--- desktop-core coverage ---"
if command -v cargo-llvm-cov &>/dev/null; then
    cargo llvm-cov --manifest-path apps/desktop-core/Cargo.toml --all-features --fail-under-lines 100 --fail-under-functions 100 --fail-under-regions 100
else
    echo "WARNING: cargo-llvm-cov not found, skipping coverage"
fi

# Python: backend-api
echo "--- backend-api lint ---"
uv run --directory apps/backend-api ruff check src tests

echo "--- backend-api typecheck ---"
uv run --directory apps/backend-api mypy src

echo "--- backend-api test ---"
uv run --directory apps/backend-api pytest --cov=ibreeze_backend --cov-branch --cov-fail-under=62

# Python: sidecar
echo "--- sidecar lint ---"
uv run --directory sidecar ruff check ibreeze tests

echo "--- sidecar typecheck ---"
uv run --directory sidecar mypy ibreeze

echo "--- sidecar test ---"
uv run --directory sidecar pytest --cov=ibreeze --cov-branch --cov-fail-under=77

# Node: desktop UI
echo "--- desktop lint ---"
npm --prefix apps/desktop run lint

echo "--- desktop typecheck ---"
npm --prefix apps/desktop run typecheck

echo "--- desktop test ---"
npm --prefix apps/desktop run test:coverage

# Node: admin-web
echo "--- admin-web lint ---"
npm --prefix apps/admin-web run lint

echo "--- admin-web typecheck ---"
npm --prefix apps/admin-web run typecheck

echo "--- admin-web test ---"
npm --prefix apps/admin-web run test:coverage

# Contract/Integration/Security tests
echo "--- python tests ---"
python3 -m pytest tests/contract tests/integration tests/faults tests/scripts -v

# E2E
echo "--- e2e tests ---"
if [ -n "$(ls -A tests/e2e/*.spec.ts 2>/dev/null || ls -A tests/e2e/tests/*.spec.ts 2>/dev/null)" ]; then
  npm --prefix tests/e2e run test
else
  echo "SKIP: no e2e test files found"
fi

# Drift check
echo "--- contract drift ---"
bash scripts/check-contract-drift.sh

# Git check
echo "--- git diff check ---"
git diff --check

echo "=== Verify Complete ==="
