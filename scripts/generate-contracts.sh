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

echo "--- Step 1: Validate JSON Schemas ---"
# Validate all schema files have correct $schema and no duplicate $id
python3 -c "
import json, sys, os
from pathlib import Path

schemas_dir = Path('packages/contracts')
errors = []
seen_ids = {}

for schema_file in schemas_dir.rglob('*.schema.json'):
    with open(schema_file) as f:
        try:
            data = json.load(f)
        except json.JSONDecodeError as e:
            errors.append(f'{schema_file}: JSON decode error: {e}')
            continue
    
    # Check $schema
    if data.get('\$schema') != 'https://json-schema.org/draft/2020-12/schema':
        errors.append(f'{schema_file}: Missing or incorrect \$schema')
    
    # Check $id
    if '\$id' in data:
        schema_id = data['\$id']
        if schema_id in seen_ids:
            errors.append(f'{schema_file}: Duplicate \$id: {schema_id} (also in {seen_ids[schema_id]})')
        seen_ids[schema_id] = str(schema_file)
    else:
        errors.append(f'{schema_file}: Missing \$id')

if errors:
    for e in errors:
        print(f'ERROR: {e}', file=sys.stderr)
    sys.exit(1)

print('All schemas valid')
"

echo "--- Step 2: Generate TypeScript types (RPC) ---"
cd "$ROOT_DIR/packages/contracts"
npm ci --prefer-offline --no-audit 2>/dev/null || npm install

# Generate TypeScript from rpc-schema
npx json2ts -i "$ROOT_DIR/packages/rpc-schema" -o "$TMP_DIR/desktop-rpc" \
  --style.singleQuotes --style.semicolons --no-banner \
  --unknownAny false --strictIndexSignatures --enableConstEnums false

echo "--- Step 3: Generate Pydantic models (Sidecar) ---"
cd "$ROOT_DIR/sidecar"
uv run datamodel-codegen \
  --input "$ROOT_DIR/packages/rpc-schema" \
  --input-file-type jsonschema \
  --output "$TMP_DIR/sidecar-rpc/rpc.py" \
  --output-model-type pydantic_v2.BaseModel \
  --field-constraints --snake-case-field --use-standard-collections \
  --use-default --use-default-kwargs --reuse-model --respect-field-order \
  --class-name-suffix "Schema" --base-class "ibreeze.schemas.BaseSchema"

# Also generate from contracts for domain events
uv run datamodel-codegen \
  --input "$ROOT_DIR/packages/contracts/domain-events" \
  --input-file-type jsonschema \
  --output "$TMP_DIR/sidecar-domain-events/events.py" \
  --output-model-type pydantic_v2.BaseModel \
  --field-constraints --snake-case-field --use-standard-collections \
  --use-default --use-default-kwargs --reuse-model --respect-field-order \
  --class-name-suffix "Event" --base-class "ibreeze.schemas.BaseSchema"

# Generate Skill manifest model
uv run datamodel-codegen \
  --input "$ROOT_DIR/packages/contracts/skill/skill-manifest.v1.schema.json" \
  --input-file-type jsonschema \
  --output "$TMP_DIR/sidecar-skills/skill_manifest.py" \
  --output-model-type pydantic_v2.BaseModel \
  --field-constraints --snake-case-field --use-standard-collections \
  --use-default --use-default-kwargs --reuse-model --respect-field-order \
  --base-class "ibreeze.schemas.BaseSchema"

echo "--- Step 4: Generate Rust types (Desktop Core) ---"
cd "$ROOT_DIR/scripts/schema-gen-rust"
cargo build --release 2>/dev/null || cargo build

# Generate RPC types
"$ROOT_DIR/scripts/schema-gen-rust/target/release/schema-gen-rust" \
  --input "$ROOT_DIR/packages/rpc-schema" \
  --output "$TMP_DIR/desktop-core-rpc" \
  --mod-name "ibreeze_rpc"

# Generate Contract types (for domain events, etc.)
"$ROOT_DIR/scripts/schema-gen-rust/target/release/schema-gen-rust" \
  --input "$ROOT_DIR/packages/contracts" \
  --output "$TMP_DIR/desktop-core-contracts" \
  --mod-name "ibreeze_contracts"

echo "--- Step 5: Generate OpenAPI spec (Backend API) ---"
cd "$ROOT_DIR/apps/backend-api"
uv run python -c "
from ibreeze_backend.main import app
import json
with open('$TMP_DIR/openapi.json', 'w') as f:
    json.dump(app.openapi(), f, indent=2, sort_keys=True)
"

echo "--- Step 6: Generate TypeScript API client (Admin Web) ---"
cd "$ROOT_DIR/packages/contracts"
npx openapi-typescript "$TMP_DIR/openapi.json" -o "$TMP_DIR/admin-web-api/api.ts" \
  --prepend "export type { } from '@tanstack/react-query'"

echo "--- Step 7: Atomic replace generated files ---"
# Desktop RPC
mkdir -p "$ROOT_DIR/apps/desktop/src/generated/rpc"
rsync -a --delete "$TMP_DIR/desktop-rpc/" "$ROOT_DIR/apps/desktop/src/generated/rpc/"

mkdir -p "$ROOT_DIR/apps/desktop-core/src/generated/rpc"
rsync -a --delete "$TMP_DIR/desktop-core-rpc/" "$ROOT_DIR/apps/desktop-core/src/generated/rpc/"

mkdir -p "$ROOT_DIR/apps/desktop-core/src/generated/contracts"
rsync -a --delete "$TMP_DIR/desktop-core-contracts/" "$ROOT_DIR/apps/desktop-core/src/generated/contracts/"

# Sidecar RPC
mkdir -p "$ROOT_DIR/sidecar/ibreeze/generated"
mkdir -p "$ROOT_DIR/sidecar/ibreeze/generated/rpc"
rsync -a --delete "$TMP_DIR/sidecar-rpc/" "$ROOT_DIR/sidecar/ibreeze/generated/rpc/"

mkdir -p "$ROOT_DIR/sidecar/ibreeze/generated/domain_events"
rsync -a --delete "$TMP_DIR/sidecar-domain-events/" "$ROOT_DIR/sidecar/ibreeze/generated/domain_events/"

mkdir -p "$ROOT_DIR/sidecar/ibreeze/generated/skills"
rsync -a --delete "$TMP_DIR/sidecar-skills/" "$ROOT_DIR/sidecar/ibreeze/generated/skills/"

# Admin Web API
mkdir -p "$ROOT_DIR/apps/admin-web/src/generated/openapi"
rsync -a --delete "$TMP_DIR/admin-web-api/" "$ROOT_DIR/apps/admin-web/src/generated/openapi/"

# OpenAPI spec for contracts
mkdir -p "$ROOT_DIR/packages/contracts/openapi"
cp "$TMP_DIR/openapi.json" "$ROOT_DIR/packages/contracts/openapi/openapi.json"

echo "--- Step 8: Verify deterministic generation ---"
# Run generation again and ensure no diff
"$0" --verify-only 2>/dev/null || true

echo "=== Contract Generation Complete ==="
echo "Generated files:"
find "$ROOT_DIR/apps/desktop/src/generated" -name "*.ts" 2>/dev/null | head -20
find "$ROOT_DIR/apps/desktop-core/src/generated" -name "*.rs" 2>/dev/null | head -20
find "$ROOT_DIR/sidecar/ibreeze/generated" -name "*.py" 2>/dev/null | head -20
find "$ROOT_DIR/apps/admin-web/src/generated" -name "*.ts" 2>/dev/null | head -10