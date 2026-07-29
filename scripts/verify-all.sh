#!/usr/bin/env bash
set -Eeuo pipefail
trap 'code=$?; echo "verify-all failed at line ${LINENO} with exit code ${code}" >&2; exit "${code}"' ERR

SCOPE="all"
while [[ $# -gt 0 ]]; do
    case "$1" in
        --scope) SCOPE="$2"; shift 2 ;;
        --help|-h)
            echo "Usage: $0 [--scope SCOPE|SCOPE]"
            echo "Scopes: contracts desktop sidecar backend e2e security all"
            echo ""
            echo "  --scope SCOPE   set verification scope"
            echo "  --help, -h      show this help"
            exit 0
            ;;
        *) SCOPE="$1"; shift ;;
    esac
done

echo "=== iBreeze Verify All (scope: ${SCOPE}) ==="

required_tools=(node npm uv cargo)
missing_optional=()
for tool in "${required_tools[@]}"; do
    if ! command -v "$tool" &>/dev/null; then
        echo "FATAL: required tool '$tool' not found" >&2
        exit 1
    fi
done

if ! command -v cargo-nextest &>/dev/null; then
    missing_optional+=("cargo-nextest")
    echo "WARNING: cargo-nextest not found, will fallback to cargo test" >&2
fi

if ! command -v cargo-llvm-cov &>/dev/null; then
    missing_optional+=("cargo-llvm-cov")
    echo "WARNING: cargo-llvm-cov not found, will skip coverage checks" >&2
fi

run_contracts() {
    echo "--- packages/contracts install ---"
    npm --prefix packages/contracts ci
    echo "--- packages/contracts lint ---"
    npm --prefix packages/contracts run lint
    echo "--- contract drift ---"
    bash scripts/check-contract-drift.sh
}

run_desktop_rust() {
    echo "--- desktop-core fmt ---"
    cargo fmt --manifest-path apps/desktop-core/Cargo.toml --all -- --check
    echo "--- desktop-core clippy ---"
    cargo clippy --manifest-path apps/desktop-core/Cargo.toml --all-targets --all-features -- -D warnings
    if command -v cargo-nextest &>/dev/null; then
        echo "--- desktop-core test (nextest) ---"
        cargo nextest run --manifest-path apps/desktop-core/Cargo.toml --all-features
    else
        echo "--- desktop-core test (cargo test) ---"
        cargo test --manifest-path apps/desktop-core/Cargo.toml --all-features
    fi
    if command -v cargo-llvm-cov &>/dev/null; then
        echo "--- desktop-core coverage ---"
        cargo llvm-cov --manifest-path apps/desktop-core/Cargo.toml --all-features --fail-under-lines 100 --fail-under-functions 100 --fail-under-regions 100
    else
        echo "--- desktop-core coverage (skipped, cargo-llvm-cov not found) ---"
    fi
}

run_desktop_ui() {
    echo "--- desktop install ---"
    npm --prefix apps/desktop ci
    echo "--- admin-web install ---"
    npm --prefix apps/admin-web ci
    echo "--- desktop lint ---"
    npm --prefix apps/desktop run lint
    echo "--- desktop typecheck ---"
    npm --prefix apps/desktop run typecheck
    echo "--- desktop test ---"
    npm --prefix apps/desktop run test:coverage
    echo "--- admin-web lint ---"
    npm --prefix apps/admin-web run lint
    echo "--- admin-web typecheck ---"
    npm --prefix apps/admin-web run typecheck
    echo "--- admin-web test ---"
    npm --prefix apps/admin-web run test:coverage
}

run_sidecar() {
    echo "--- sidecar lint ---"
    uv run --directory sidecar ruff check ibreeze tests
    echo "--- sidecar typecheck ---"
    uv run --directory sidecar mypy ibreeze
    echo "--- sidecar test ---"
    uv run --directory sidecar pytest tests/ -v --cov=ibreeze --cov-branch --cov-fail-under=100
}

run_backend() {
    echo "--- backend-api lint ---"
    uv run --directory apps/backend-api ruff check src tests
    echo "--- backend-api typecheck ---"
    uv run --directory apps/backend-api mypy src
    echo "--- backend-api test ---"
    uv run --directory apps/backend-api pytest tests/ -v --cov=ibreeze_backend --cov-branch --cov-fail-under=100
}

run_e2e() {
    echo "--- e2e install ---"
    npm --prefix tests/e2e ci
    echo "--- e2e playwright browsers ---"
    npx playwright install chromium --with-deps 2>&1 || echo "Playwright binary install skipped"
    echo "--- e2e tests ---"
    if ls tests/e2e/*.spec.ts 2>/dev/null | head -1 >/dev/null 2>&1; then
        npm --prefix tests/e2e run test
    else
        echo "ERROR: no e2e test files found (expected at least 1 .spec.ts)"
        exit 1
    fi
}

run_security() {
    echo "--- security tests ---"
    uv run --directory sidecar pytest tests/faults tests/security -v
}

run_drift() {
    echo "--- python contract/integration tests ---"
    uv run --directory sidecar pytest tests/contract tests/integration tests/scripts -v
    echo "--- contract drift ---"
    bash scripts/check-contract-drift.sh
    echo "--- git diff check ---"
    git diff --check
}

case "$SCOPE" in
    contracts)
        run_contracts
        ;;
    desktop)
        run_desktop_rust
        run_desktop_ui
        ;;
    sidecar)
        run_sidecar
        ;;
    backend)
        run_backend
        ;;
    e2e)
        run_e2e
        ;;
    security)
        run_security
        ;;
    all)
        run_contracts
        run_desktop_rust
        run_desktop_ui
        run_sidecar
        run_backend
        run_e2e
        run_security
        run_drift
        ;;
    *)
        echo "ERROR: unknown scope '${SCOPE}'. Valid: contracts|desktop|sidecar|backend|e2e|security|all" >&2
        exit 1
        ;;
esac

echo "=== Verify Complete (scope: ${SCOPE}) ==="
