#!/usr/bin/env bash
set -Eeuo pipefail
trap 'code=$?; echo "verify-all failed at line ${LINENO} with exit code ${code}" >&2; exit "${code}"' ERR

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

SCOPE="all"
while [[ $# -gt 0 ]]; do
    case "$1" in
        --scope) SCOPE="$2"; shift 2 ;;
        --help|-h)
            echo "Usage: $0 [--scope SCOPE|SCOPE]"
            echo "Scopes: contracts desktop sidecar backend e2e security drift all"
            echo ""
            echo "  --scope SCOPE   set verification scope"
            echo "  --help, -h      show this help"
            exit 0
            ;;
        *) SCOPE="$1"; shift ;;
    esac
done

echo "=== iBreeze Verify All (scope: ${SCOPE}) ==="

# Global required tools (needed by every scope)
required_tools=(node npm uv)
for tool in "${required_tools[@]}"; do
    if ! command -v "$tool" &>/dev/null; then
        echo "FATAL: required tool '$tool' not found" >&2
        exit 1
    fi
done

run_contracts() {
    # Needs cargo for check-contract-drift.sh (schema-gen-rust compilation)
    if ! command -v cargo &>/dev/null; then
        echo "FATAL: required tool 'cargo' not found" >&2
        exit 1
    fi
    echo "--- packages/contracts install ---"
    npm --prefix packages/contracts ci
    echo "--- packages/contracts lint ---"
    npm --prefix packages/contracts run lint
    echo "--- contract drift ---"
    bash scripts/check-contract-drift.sh
    echo "--- contract registry sync check ---"
    python3 scripts/sync_contract_registry.py --check
}

run_desktop_rust() {
    # Rust-specific tool check
    for tool in cargo cargo-nextest cargo-llvm-cov; do
        if ! command -v "$tool" &>/dev/null; then
            echo "FATAL: required Rust tool '$tool' not found" >&2
            exit 1
        fi
    done
    echo "--- desktop-core frontend dist ---"
    mkdir -p apps/desktop/dist
    echo "--- desktop-core fmt ---"
    cargo fmt --manifest-path apps/desktop-core/Cargo.toml --all -- --check
    echo "--- desktop-core clippy ---"
    cargo clippy --manifest-path apps/desktop-core/Cargo.toml --all-targets --all-features -- -D warnings
    echo "--- desktop-core test (nextest) ---"
    cargo nextest run --manifest-path apps/desktop-core/Cargo.toml --all-features --no-fail-fast
    echo "--- desktop-core coverage ---"
    cargo llvm-cov --manifest-path apps/desktop-core/Cargo.toml --all-features --fail-under-lines 100 --fail-under-functions 100 --fail-under-regions 100
}

audit_app() {
    local prefix="$1"
    local exception_file="$2"
    local audit_out
    audit_out=$(npm audit --prefix "$prefix" --audit-level=high 2>&1) || true
    if echo "$audit_out" | grep -q "found 0 vulnerabilities"; then
        echo "--- npm audit $prefix: 0 vulnerabilities ---"
    elif [ -n "$exception_file" ] && [ -f "$exception_file" ]; then
        local exceptions
        exceptions=$(python3 -c "
import json, sys
with open('$exception_file') as f:
    data = json.load(f)
for adv in data.get('advisories', []):
    print(adv['id'])
" 2>/dev/null)
        local unfixed
        unfixed=$(echo "$audit_out" | python3 -c "
import sys, re
for line in sys.stdin:
    m = re.search(r'https://github.com/advisories/(\S+)', line)
    if m:
        print(m.group(1))
" 2>/dev/null | sort -u)
        local unknown=()
        while IFS= read -r id; do
            [ -z "$id" ] && continue
            if ! echo "$exceptions" | grep -qF "$id"; then
                unknown+=("$id")
            fi
        done <<< "$unfixed"
        if [ ${#unknown[@]} -gt 0 ]; then
            echo "ERROR: audit found new (non-exempted) advisories: ${unknown[*]}" >&2
            exit 1
        fi
        echo "--- npm audit $prefix: $(echo "$unfixed" | wc -l) exempted vulnerabilities ---"
    else
        echo "ERROR: npm audit $prefix failed:" >&2
        echo "$audit_out" >&2
        exit 1
    fi
}

run_desktop_ui() {
    echo "--- desktop install ---"
    npm --prefix apps/desktop ci
    echo "--- desktop audit ---"
    audit_app apps/desktop ""
    echo "--- admin-web install ---"
    npm --prefix apps/admin-web ci
    echo "--- admin-web audit ---"
    audit_app apps/admin-web "apps/admin-web/.audit-exceptions.json"
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
    echo "--- sidecar single-writer check ---"
    python3 scripts/check_single_writer.py
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
    echo "--- e2e tests ---"
    e2e_dir="$ROOT_DIR/tests/e2e"
    if [ -d "$e2e_dir" ] && ls "$e2e_dir"/*.py &>/dev/null 2>&1; then
        uv run pytest "$e2e_dir" -v --tb=short
    else
        echo "(no e2e test files found in $e2e_dir)"
    fi
}

run_security() {
    echo "--- security tests ---"
    uv run --directory sidecar pytest tests/faults tests/security -v
}

run_drift() {
    # Needs cargo for check-contract-drift.sh (schema-gen-rust compilation)
    if ! command -v cargo &>/dev/null; then
        echo "FATAL: required tool 'cargo' not found" >&2
        exit 1
    fi
    echo "--- python contract/integration tests ---"
    test_dirs=""
    for d in tests/contract tests/integration tests/scripts; do
        if [ -d "sidecar/$d" ]; then test_dirs="$test_dirs $d"; fi
    done
    if [ -n "$test_dirs" ]; then
        uv run --directory sidecar pytest $test_dirs -v
    else
        echo "(no test directories found)"
    fi
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
    drift)
        run_security
        run_drift
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
