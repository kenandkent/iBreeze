#!/usr/bin/env bash
# Check for contract drift between source schemas and generated code
# Usage: ./scripts/check-contract-drift.sh
# This script is READ-ONLY - it never modifies files in the workspace.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "=== iBreeze Contract Drift Check ==="
echo "Root: $ROOT_DIR"

TMP_DIR=$(mktemp -d)
trap 'rm -rf "$TMP_DIR"' EXIT

cd "$ROOT_DIR"

echo "--- Step 1: Generate fresh contracts to temp directory ---"
IBREEZE_OUTPUT_ROOT="$TMP_DIR/out" bash "$ROOT_DIR/scripts/generate-contracts.sh" 2>&1

echo "--- Step 1b: Generate method-kind lookups to temp dir ---"
IBREEZE_OUTPUT_ROOT="$TMP_DIR/out" python3 "$ROOT_DIR/scripts/generate-method-kinds.py"

echo "--- Step 2: Compare generated files ---"
HAS_DRIFT=0

compare_dir() {
  local label="$1" real="$2" fresh="$3"
  if [ ! -d "$real" ] && [ ! -d "$fresh" ]; then
    return 0
  fi
  if [ ! -d "$real" ]; then
    echo "  MISSING: $label (real dir does not exist)"
    HAS_DRIFT=1
    return 0
  fi
  if [ ! -d "$fresh" ]; then
    echo "  MISSING: $label (fresh dir does not exist)"
    HAS_DRIFT=1
    return 0
  fi

  local diff_out="$TMP_DIR/$(echo "$label" | tr '/' '_').diff"
  if diff -r -x '__pycache__' -I '^#   timestamp:' "$real" "$fresh" > "$diff_out" 2>&1; then
    echo "  ✓ $label"
  else
    echo "  ✗ $label (diff follows)"
    cat "$diff_out"
    HAS_DRIFT=1
  fi
}

compare_file() {
  local label="$1" real="$2" fresh="$3"
  if [ ! -f "$real" ] && [ ! -f "$fresh" ]; then
    return 0
  fi
  if [ ! -f "$real" ]; then
    echo "  MISSING: $label (real file does not exist)"
    HAS_DRIFT=1
    return 0
  fi
  if [ ! -f "$fresh" ]; then
    echo "  MISSING: $label (fresh file does not exist)"
    HAS_DRIFT=1
    return 0
  fi

  local diff_out="$TMP_DIR/$(echo "$label" | tr '/' '_').diff"
  if diff "$real" "$fresh" > "$diff_out" 2>&1; then
    echo "  ✓ $label"
  else
    echo "  ✗ $label (diff follows)"
    cat "$diff_out"
    HAS_DRIFT=1
  fi
}

compare_dir "desktop/src/generated/rpc" \
  "$ROOT_DIR/apps/desktop/src/generated/rpc" \
  "$TMP_DIR/out/apps/desktop/src/generated/rpc"

compare_dir "desktop-core/src/generated/rpc" \
  "$ROOT_DIR/apps/desktop-core/src/generated/rpc" \
  "$TMP_DIR/out/apps/desktop-core/src/generated/rpc"

compare_dir "desktop-core/src/generated/contracts" \
  "$ROOT_DIR/apps/desktop-core/src/generated/contracts" \
  "$TMP_DIR/out/apps/desktop-core/src/generated/contracts"

compare_dir "sidecar/ibreeze/generated/rpc" \
  "$ROOT_DIR/sidecar/ibreeze/generated/rpc" \
  "$TMP_DIR/out/sidecar/ibreeze/generated/rpc"

compare_dir "sidecar/ibreeze/generated/domain_events" \
  "$ROOT_DIR/sidecar/ibreeze/generated/domain_events" \
  "$TMP_DIR/out/sidecar/ibreeze/generated/domain_events"

compare_dir "sidecar/ibreeze/generated/skills" \
  "$ROOT_DIR/sidecar/ibreeze/generated/skills" \
  "$TMP_DIR/out/sidecar/ibreeze/generated/skills"

compare_dir "admin-web/src/generated/openapi" \
  "$ROOT_DIR/apps/admin-web/src/generated/openapi" \
  "$TMP_DIR/out/apps/admin-web/src/generated/openapi"

compare_dir "packages/contracts/openapi" \
  "$ROOT_DIR/packages/contracts/openapi" \
  "$TMP_DIR/out/packages/contracts/openapi"

# Compare method_kinds.rs individually (not under generated/rpc dir)
compare_file "desktop-core/src/rpc/generated_method_kinds.rs" \
  "$ROOT_DIR/apps/desktop-core/src/rpc/generated_method_kinds.rs" \
  "$TMP_DIR/out/apps/desktop-core/src/rpc/generated_method_kinds.rs"

echo "--- Step 3: Check method kind registry drift ---"
if python3 "$ROOT_DIR/scripts/generate-method-kinds.py" --check; then
  echo "  ✓ method kinds match registry"
else
  echo "  ✗ method kinds drift detected (run generate-method-kinds.py)"
  HAS_DRIFT=1
fi

echo ""
if [ "$HAS_DRIFT" -eq 0 ]; then
  echo "✓ No contract drift detected"
  exit 0
else
  echo "Run 'scripts/generate-contracts.sh' to regenerate and commit the changes."
  exit 1
fi
