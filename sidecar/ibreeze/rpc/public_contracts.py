"""Small dependency-free validator for generated public RPC schemas.

The desktop bundle does not ship ``jsonschema``.  The generated contracts use
the JSON-Schema subset below (objects, arrays, primitive constraints, enums,
oneOf and local ``$ref``), so validating it here keeps request/response
boundaries strict without adding a runtime dependency.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, cast
from uuid import UUID


class ContractValidationError(ValueError):
    pass


_ROOT = Path(__file__).resolve().parents[3] / "packages/rpc-schema"
_CACHE: dict[str, dict[str, Any]] = {}


def _load(name: str) -> dict[str, Any] | None:
    if name in _CACHE:
        return _CACHE[name]
    path = _ROOT / name
    if not path.exists():
        return None
    value = cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))
    _CACHE[name] = value
    return value


def _resolve(schema: dict[str, Any], base: str) -> dict[str, Any]:
    ref = schema.get("$ref")
    if not isinstance(ref, str):
        return schema
    if ref.startswith("#/"):
        value: Any = _load(base)
        if value is None:
            return schema
        for part in ref[2:].split("/"):
            value = value[part]
        return value if isinstance(value, dict) else schema
    return schema


def _fail(path: str, message: str) -> None:
    raise ContractValidationError(f"{path or '$'}: {message}")


def _validate(value: Any, schema: dict[str, Any], *, path: str, base: str, strict_additional: bool = False) -> None:
    schema = _resolve(schema, base)
    if "oneOf" in schema:
        errors = []
        for branch in schema["oneOf"]:
            try:
                _validate(value, branch, path=path, base=base, strict_additional=strict_additional)
                return
            except ContractValidationError as exc:
                errors.append(str(exc))
        _fail(path, "does not match oneOf")
    if "anyOf" in schema:
        for branch in schema["anyOf"]:
            try:
                _validate(value, branch, path=path, base=base, strict_additional=strict_additional)
                return
            except ContractValidationError:
                pass
        _fail(path, "does not match anyOf")
    if "const" in schema and value != schema["const"]:
        _fail(path, "must equal const")
    if "enum" in schema and value not in schema["enum"]:
        _fail(path, "value is not in enum")

    kind = schema.get("type")
    # JSON Schema permits a union of primitive types (for example
    # ``["string", "null"]``).  The catalog/RPC schemas use this form for
    # nullable cursors; treating the list as an implicit ``anyOf`` keeps the
    # dependency-free validator aligned with the canonical schema instead of
    # silently skipping type checks.
    if isinstance(kind, list):
        for branch in kind:
            try:
                _validate(value, {**schema, "type": branch}, path=path, base=base, strict_additional=strict_additional)
                return
            except ContractValidationError:
                pass
        _fail(path, f"must match one of {kind}")
    if kind == "object":
        if not isinstance(value, dict):
            _fail(path, "must be an object")
        properties = schema.get("properties", {})
        for name in schema.get("required", []):
            if name not in value:
                _fail(f"{path}.{name}", "is required")
        if strict_additional and schema.get("additionalProperties") is False:
            unknown = set(value) - set(properties)
            if unknown:
                _fail(f"{path}.{sorted(unknown)[0]}", "additional property is not allowed")
        for name, child in properties.items():
            if name in value:
                _validate(value[name], child, path=f"{path}.{name}", base=base, strict_additional=strict_additional)
        return
    if kind == "array":
        if not isinstance(value, list):
            _fail(path, "must be an array")
        if "minItems" in schema and len(value) < schema["minItems"]:
            _fail(path, "has too few items")
        if "maxItems" in schema and len(value) > schema["maxItems"]:
            _fail(path, "has too many items")
        if isinstance(schema.get("items"), dict):
            for index, item in enumerate(value):
                _validate(item, schema["items"], path=f"{path}[{index}]", base=base, strict_additional=strict_additional)
        return
    if kind == "string":
        if not isinstance(value, str):
            _fail(path, "must be a string")
        if len(value) < schema.get("minLength", 0) or len(value) > schema.get("maxLength", 2**31 - 1):
            _fail(path, "length is outside allowed range")
        pattern = schema.get("pattern")
        if pattern and re.fullmatch(pattern, value) is None:
            _fail(path, "does not match pattern")
        if schema.get("format") == "uuid":
            try:
                UUID(value)
            except (ValueError, AttributeError, TypeError):
                _fail(path, "must be a UUID")
        return
    if kind == "integer":
        if isinstance(value, bool) or not isinstance(value, int):
            _fail(path, "must be an integer")
        if "minimum" in schema and value < schema["minimum"]:
            _fail(path, "is below minimum")
        if "maximum" in schema and value > schema["maximum"]:
            _fail(path, "is above maximum")
        return
    if kind == "number" and (isinstance(value, bool) or not isinstance(value, (int, float))):
        _fail(path, "must be a number")
    if kind == "boolean" and not isinstance(value, bool):
        _fail(path, "must be a boolean")
    if kind == "null" and value is not None:
        _fail(path, "must be null")


def _method_schema(method: str, suffix: str) -> tuple[dict[str, Any], str] | None:
    registry = _load("registry.v1.json")
    if registry is None:
        return None
    entry = next((item for item in registry["methods"] if item["method"] == method), None)
    if entry is None:
        return None
    filename = entry["request_schema"] if suffix == "request" else entry["response_schema"]
    schema = _load(filename)
    return (schema, filename) if schema is not None else None


def method_is_write(method: str) -> bool | None:
    """Return the canonical registry kind for a public method.

    ``None`` means the method is not a public registry entry (for example an
    internal supervisor notification).  The production RPC boundary uses the
    result to enforce the same idempotency-key contract as the Rust client.
    """
    registry = _load("registry.v1.json")
    if registry is None:
        return None
    entry = next((item for item in registry["methods"] if item["method"] == method), None)
    if entry is None:
        return None
    return bool(entry.get("kind") == "write")


# Read-only introspection for integration checks and diagnostics.  The set is
# derived from the canonical registry at import time; supervisor-only system
# methods are added explicitly because they are owned by the RPC server and
# intentionally do not live in the public business registry.
_registry = _load("registry.v1.json")
PUBLIC_METHODS = frozenset(
    {
        "system.handshake",
        "system.health",
        "system.shutdown",
        *(
            item["method"]
            for item in (_registry or {}).get("methods", [])
            if isinstance(item, dict) and isinstance(item.get("method"), str)
        ),
    }
)


def validate_request(method: str, params: dict[str, Any]) -> None:
    resolved = _method_schema(method, "request")
    if resolved is None:
        return
    schema, filename = resolved
    _validate(params, schema, path="$", base=filename, strict_additional=True)


def validate_response(method: str, result: Any) -> None:
    resolved = _method_schema(method, "response")
    if resolved is None:
        return
    schema, filename = resolved
    _validate(result, schema, path="$", base=filename)
