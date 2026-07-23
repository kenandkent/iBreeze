"""Tests for schema catalog - P0-T02."""
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent.parent
CONTRACTS_DIR = ROOT / "packages" / "contracts"
RPC_SCHEMA_DIR = ROOT / "packages" / "rpc-schema"

SCHEMA_DIRS = ["events", "domain-events", "artifacts", "skill"]


def test_rpc_meta_schema_exists():
    meta_file = RPC_SCHEMA_DIR / "meta.schema.json"
    assert meta_file.exists(), f"meta.schema.json not found at {meta_file}"


def test_rpc_meta_schema_valid():
    meta_file = RPC_SCHEMA_DIR / "meta.schema.json"
    schema = json.loads(meta_file.read_text())
    assert schema["$schema"].startswith("https://json-schema.org/draft/2020-12")
    assert "$id" in schema
    assert "required" in schema


def test_domain_events_registry_exists():
    registry_file = CONTRACTS_DIR / "domain-events" / "registry.v1.json"
    assert registry_file.exists(), "registry.v1.json not found"


def test_domain_events_registry_valid():
    registry_file = CONTRACTS_DIR / "domain-events" / "registry.v1.json"
    registry = json.loads(registry_file.read_text())
    # This is a JSON Schema definition, check it's valid schema
    assert registry["$schema"].startswith("https://json-schema.org/draft/2020-12")
    assert "required" in registry
    assert "version" in registry["properties"]
    assert "events" in registry["properties"]


def test_all_schemas_have_json_schema_2020_12():
    errors = []
    for dir_name in SCHEMA_DIRS:
        schema_dir = CONTRACTS_DIR / dir_name
        if not schema_dir.exists():
            continue
        for schema_file in schema_dir.glob("*.json"):
            schema = json.loads(schema_file.read_text())
            if not schema.get("$schema", "").startswith("https://json-schema.org/draft/2020-12"):
                errors.append(f"{dir_name}/{schema_file.name}: missing or invalid $schema")
    assert not errors, f"Schema validation errors:\n" + "\n".join(errors)


def test_all_schemas_have_required_fields():
    errors = []
    for dir_name in SCHEMA_DIRS:
        schema_dir = CONTRACTS_DIR / dir_name
        if not schema_dir.exists():
            continue
        for schema_file in schema_dir.glob("*.json"):
            schema = json.loads(schema_file.read_text())
            missing = []
            for field in ["$id", "title", "type"]:
                if field not in schema:
                    missing.append(field)
            if missing:
                errors.append(f"{dir_name}/{schema_file.name}: missing {missing}")
    assert not errors, f"Missing fields:\n" + "\n".join(errors)


def test_no_duplicate_ids():
    seen_ids = {}
    errors = []
    for dir_name in SCHEMA_DIRS:
        schema_dir = CONTRACTS_DIR / dir_name
        if not schema_dir.exists():
            continue
        for schema_file in schema_dir.glob("*.json"):
            schema = json.loads(schema_file.read_text())
            schema_id = schema.get("$id")
            if schema_id:
                if schema_id in seen_ids:
                    errors.append(
                        f"Duplicate $id {schema_id}: "
                        f"{seen_ids[schema_id]} and {dir_name}/{schema_file.name}"
                    )
                else:
                    seen_ids[schema_id] = f"{dir_name}/{schema_file.name}"
    assert not errors, f"Duplicate IDs:\n" + "\n".join(errors)


def test_meta_schema_has_required_fields():
    meta_file = RPC_SCHEMA_DIR / "meta.schema.json"
    schema = json.loads(meta_file.read_text())
    required_fields = ["trace_id", "ipc_session_id", "window_session_id", "idempotency_key"]
    assert set(schema["required"]) == set(required_fields)
