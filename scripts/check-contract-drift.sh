#!/usr/bin/env bash
# Check for contract drift between source schemas and generated code
# Usage: ./scripts/check-contract-drift.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "=== iBreeze Contract Drift Check ==="
echo "Root: $ROOT_DIR"

# Create temp directory
TMP_DIR=$(mktemp -d)
trap 'rm -rf "$TMP_DIR"' EXIT

cd "$ROOT_DIR"

echo "--- Step 1: Save current generated state ---"
CURRENT_DIR="$TMP_DIR/current"
mkdir -p "$CURRENT_DIR"

# Copy all current generated files
for target in \
  "$ROOT_DIR/apps/desktop/src/generated" \
  "$ROOT_DIR/apps/desktop-core/src/generated" \
  "$ROOT_DIR/sidecar/ibreeze/generated" \
  "$ROOT_DIR/apps/admin-web/src/generated" \
  "$ROOT_DIR/packages/contracts/openapi"; do
  if [ -d "$target" ]; then
    rsync -a "$target/" "$CURRENT_DIR/$(basename "$target")/"
  fi
done

echo "--- Step 2: Generate fresh contracts ---"
"$ROOT_DIR/scripts/generate-contracts.sh" >/dev/null 2>&1

echo "--- Step 3: Compare with fresh generation ---"
FRESH_DIR="$TMP_DIR/fresh"
mkdir -p "$FRESH_DIR"

for target in \
  "$ROOT_DIR/apps/desktop/src/generated" \
  "$ROOT_DIR/apps/desktop-core/src/generated" \
  "$ROOT_DIR/sidecar/ibreeze/generated" \
  "$ROOT_DIR/apps/admin-web/src/generated" \
  "$ROOT_DIR/packages/contracts/openapi"; do
  if [ -d "$target" ]; then
    rsync -a "$target/" "$FRESH_DIR/$(basename "$target")/"
  fi
done

echo "--- Step 4: Restore original files ---"
for target in \
  "$ROOT_DIR/apps/desktop/src/generated" \
  "$ROOT_DIR/apps/desktop-core/src/generated" \
  "$ROOT_DIR/sidecar/ibreeze/generated" \
  "$ROOT_DIR/apps/admin-web/src/generated" \
  "$ROOT_DIR/packages/contracts/openapi"; do
  if [ -d "$target" ]; then
    rm -rf "$target"/*
    rsync -a "$CURRENT_DIR/$(basename "$target")/" "$target/"
  fi
done

echo "--- Step 5: Check for differences ---"
if diff -r "$CURRENT_DIR" "$FRESH_DIR" > "$TMP_DIR/drift.diff" 2>&1; then
  echo "✓ No contract drift detected"
  exit 0
else
  echo "✗ CONTRACT DRIFT DETECTED!"
  echo ""
  echo "Differences found:"
  cat "$TMP_DIR/drift.diff"
  echo ""
  echo "Run 'scripts/generate-contracts.sh' to regenerate and commit the changes."
  exit 1
fi