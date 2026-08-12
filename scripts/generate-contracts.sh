#!/usr/bin/env bash
# Generate all contract types from JSON Schema sources
# Usage: ./scripts/generate-contracts.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "=== iBreeze Contract Generation ==="
echo "Root: $ROOT_DIR"

# Temp directory for atomic generation
TMP_DIR=$(mktemp -d)
trap 'rm -rf "$TMP_DIR"' EXIT

cd "$ROOT_DIR"

# Allow overriding output root (used by check-contract-drift.sh for read-only drift check)
OUTPUT_ROOT="${IBREEZE_OUTPUT_ROOT:-$ROOT_DIR}"

echo "--- Step 1: Validate JSON Schemas ---"
# Validate all schema files have correct $schema and no duplicate $id
python3 "$ROOT_DIR/scripts/validate-schemas.py"

echo "--- Step 2: Bundle schemas (inline \$ref) ---"
BUNDLE_DIR="$TMP_DIR/bundled-rpc"
node "$ROOT_DIR/scripts/bundle-schemas.mjs" "$ROOT_DIR/packages/rpc-schema" "$BUNDLE_DIR"

echo "--- Step 3: Generate TypeScript types (RPC) ---"
cd "$ROOT_DIR/packages/contracts"
npm ci --prefer-offline --no-audit 2>/dev/null || npm install

npx json2ts -i "$BUNDLE_DIR" -o "$TMP_DIR/desktop-rpc" \
  --style.singleQuotes --style.semicolons --no-banner \
  --unknownAny false --strictIndexSignatures --enableConstEnums false

echo "--- Step 4: Generate Pydantic models (Sidecar) ---"
cd "$ROOT_DIR/sidecar"
uv run datamodel-codegen \
  --input "$BUNDLE_DIR" \
  --input-file-type jsonschema \
  --output "$TMP_DIR/sidecar-rpc" \
  --output-model-type pydantic_v2.BaseModel \
  --field-constraints --snake-case-field --use-standard-collections \
  --use-default --use-default-kwarg --reuse-model \
  --class-name-suffix "Schema" --base-class "ibreeze.schemas.BaseSchema"

# Also generate from contracts for domain events
uv run datamodel-codegen \
  --input "$ROOT_DIR/packages/contracts/domain-events" \
  --input-file-type jsonschema \
  --output "$TMP_DIR/sidecar-domain-events" \
  --output-model-type pydantic_v2.BaseModel \
  --field-constraints --snake-case-field --use-standard-collections \
  --use-default --use-default-kwarg --reuse-model \
  --class-name-suffix "Event" --base-class "ibreeze.schemas.BaseSchema"

# Generate Skill manifest model
mkdir -p "$TMP_DIR/sidecar-skills"
uv run datamodel-codegen \
  --input "$ROOT_DIR/packages/contracts/skill/skill-manifest.v1.schema.json" \
  --input-file-type jsonschema \
  --output "$TMP_DIR/sidecar-skills/skill_manifest.py" \
  --output-model-type pydantic_v2.BaseModel \
  --field-constraints --snake-case-field --use-standard-collections \
  --use-default --use-default-kwarg --reuse-model \
  --base-class "ibreeze.schemas.BaseSchema"

echo "--- Step 5: Generate Rust types (Desktop Core) ---"
cd "$ROOT_DIR/scripts/schema-gen-rust"
cargo build --release 2>/dev/null || cargo build

# Generate RPC types (from bundled schemas)
"$ROOT_DIR/scripts/schema-gen-rust/target/release/schema-gen-rust" \
  --input "$BUNDLE_DIR" \
  --output "$TMP_DIR/desktop-core-rpc" \
  --mod-name "ibreeze_rpc"

# Generate Contract types (for domain events, etc.)
"$ROOT_DIR/scripts/schema-gen-rust/target/release/schema-gen-rust" \
  --input "$ROOT_DIR/packages/contracts" \
  --output "$TMP_DIR/desktop-core-contracts" \
  --mod-name "ibreeze_contracts"

echo "--- Step 6: Generate OpenAPI spec (Backend API) ---"
cd "$ROOT_DIR/apps/backend-api"
uv run python -c "
from ibreeze_backend.main import app
import json
with open('$TMP_DIR/openapi.json', 'w') as f:
    json.dump(app.openapi(), f, indent=2, sort_keys=True)
"

echo "--- Step 7: Generate TypeScript API client (Admin Web) ---"
cd "$ROOT_DIR/packages/contracts"
npx openapi-typescript "$TMP_DIR/openapi.json" -o "$TMP_DIR/admin-web-api/api.ts" \
  --prepend "export type { } from '@tanstack/react-query'"

echo "--- Step 8: Atomic replace generated files ---"
# Desktop RPC
mkdir -p "$OUTPUT_ROOT/apps/desktop/src/generated/rpc"
rsync -a --delete "$TMP_DIR/desktop-rpc/" "$OUTPUT_ROOT/apps/desktop/src/generated/rpc/"

mkdir -p "$OUTPUT_ROOT/apps/desktop-core/src/generated/rpc"
rsync -a --delete "$TMP_DIR/desktop-core-rpc/" "$OUTPUT_ROOT/apps/desktop-core/src/generated/rpc/"

mkdir -p "$OUTPUT_ROOT/apps/desktop-core/src/generated/contracts"
rsync -a --delete "$TMP_DIR/desktop-core-contracts/" "$OUTPUT_ROOT/apps/desktop-core/src/generated/contracts/"

# Sidecar RPC
mkdir -p "$OUTPUT_ROOT/sidecar/ibreeze/generated"
mkdir -p "$OUTPUT_ROOT/sidecar/ibreeze/generated/rpc"
rsync -a --delete "$TMP_DIR/sidecar-rpc/" "$OUTPUT_ROOT/sidecar/ibreeze/generated/rpc/"

mkdir -p "$OUTPUT_ROOT/sidecar/ibreeze/generated/domain_events"
rsync -a --delete "$TMP_DIR/sidecar-domain-events/" "$OUTPUT_ROOT/sidecar/ibreeze/generated/domain_events/"

mkdir -p "$OUTPUT_ROOT/sidecar/ibreeze/generated/skills"
rsync -a --delete "$TMP_DIR/sidecar-skills/" "$OUTPUT_ROOT/sidecar/ibreeze/generated/skills/"

# Admin Web API
mkdir -p "$OUTPUT_ROOT/apps/admin-web/src/generated/openapi"
rsync -a --delete "$TMP_DIR/admin-web-api/" "$OUTPUT_ROOT/apps/admin-web/src/generated/openapi/"

# OpenAPI spec for contracts
mkdir -p "$OUTPUT_ROOT/packages/contracts/openapi"
cp "$TMP_DIR/openapi.json" "$OUTPUT_ROOT/packages/contracts/openapi/openapi.json"

# Method-kind lookup files are generated from the same registry and must be
# part of this atomic generation, otherwise rsync --delete would remove the
# lookup consumed by the desktop runtime.
IBREEZE_OUTPUT_ROOT="$OUTPUT_ROOT" python3 "$ROOT_DIR/scripts/generate-method-kinds.py"

# Remove verify step — handled by check-contract-drift.sh

echo "=== Contract Generation Complete ==="
echo "Generated files:"
find "$OUTPUT_ROOT/apps/desktop/src/generated" -name "*.ts" 2>/dev/null | head -20 || true
find "$OUTPUT_ROOT/apps/desktop-core/src/generated" -name "*.rs" 2>/dev/null | head -20 || true
find "$OUTPUT_ROOT/sidecar/ibreeze/generated" -name "*.py" 2>/dev/null | head -20 || true
find "$OUTPUT_ROOT/apps/admin-web/src/generated" -name "*.ts" 2>/dev/null | head -10 || true
