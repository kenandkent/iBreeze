"""Validate all JSON Schema files have correct $schema and no duplicate $id."""
import json
import sys
from pathlib import Path

schemas_dir = Path("packages/contracts")
errors = []
seen_ids = {}

for schema_file in schemas_dir.rglob("*.schema.json"):
    with open(schema_file) as f:
        try:
            data = json.load(f)
        except json.JSONDecodeError as e:
            errors.append(f"{schema_file}: JSON decode error: {e}")
            continue

    if data.get("$schema") != "https://json-schema.org/draft/2020-12/schema":
        errors.append(f"{schema_file}: Missing or incorrect $schema")

    if "$id" in data:
        schema_id = data["$id"]
        if schema_id in seen_ids:
            errors.append(f"{schema_file}: Duplicate $id: {schema_id} (also in {seen_ids[schema_id]})")
        seen_ids[schema_id] = str(schema_file)
    else:
        errors.append(f"{schema_file}: Missing $id")

if errors:
    for e in errors:
        print(f"ERROR: {e}", file=sys.stderr)
    sys.exit(1)

print("All schemas valid")
