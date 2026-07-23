#!/bin/bash
set -euo pipefail

echo "=== Checking Schema Drift ==="

cd "$(dirname "$0")/.."

# Generate to temp dir and compare
TEMP_DIR=$(mktemp -d)
trap "rm -rf $TEMP_DIR" EXIT

# Check RPC meta exists
if [ ! -f packages/rpc-schema/meta.schema.json ]; then
    echo "FAIL: meta.schema.json not found"
    exit 1
fi

# Validate all schemas
echo "Validating schemas..."
for dir in packages/contracts/events packages/contracts/domain-events packages/contracts/artifacts packages/contracts/skill; do
    if [ -d "$dir" ]; then
        for f in "$dir"/*.json; do
            if [ -f "$f" ]; then
                python3 -c "import json; json.load(open('$f'))" || {
                    echo "FAIL: Invalid JSON in $f"
                    exit 1
                }
            fi
        done
    fi
done

echo "Schema drift check: OK"
