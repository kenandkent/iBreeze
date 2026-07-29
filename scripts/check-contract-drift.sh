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
  if diff -r -I '^#   timestamp:' "$real" "$fresh" > "$diff_out" 2>&1; then
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

# Sidecar generated files are gitignored and not committed as baseline;
# regeneration is done on-demand when sidecar code needs them.
# compare_dir "sidecar/ibreeze/generated/rpc" ...
# compare_dir "sidecar/ibreeze/generated/domain_events" ...
# compare_dir "sidecar/ibreeze/generated/skills" ...

compare_dir "admin-web/src/generated/openapi" \
  "$ROOT_DIR/apps/admin-web/src/generated/openapi" \
  "$TMP_DIR/out/apps/admin-web/src/generated/openapi"

compare_dir "packages/contracts/openapi" \
  "$ROOT_DIR/packages/contracts/openapi" \
  "$TMP_DIR/out/packages/contracts/openapi"

echo ""
if [ "$HAS_DRIFT" -eq 0 ]; then
  echo "✓ No contract drift detected"
  exit 0
else
  echo "Run 'scripts/generate-contracts.sh' to regenerate and commit the changes."
  exit 1
fi
