from __future__ import annotations

import json
from typing import Any


def _reject_float(value: Any) -> None:
    if isinstance(value, float):
        raise ValueError("ROUTING_POLICY_FLOAT_FORBIDDEN")
    if isinstance(value, dict):
        for item in value.values():
            _reject_float(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            _reject_float(item)


def _canonicalize(value: Any) -> Any:
    """Return a JSON-compatible tree with RFC 8785 object-key ordering.

    RFC 8785 sorts JSON strings by their UTF-16 code units.  Python's default
    ``sort_keys=True`` orders Unicode code points, which differs for some
    supplementary-plane characters and can make policy hashes diverge from
    Rust/JavaScript implementations.
    """

    if isinstance(value, dict):
        return {
            key: _canonicalize(value[key])
            for key in sorted(value, key=lambda item: str(item).encode("utf-16-be", "surrogatepass"))
        }
    if isinstance(value, (list, tuple)):
        return [_canonicalize(item) for item in value]
    return value


def canonical_json(value: Any) -> str:
    """Canonical routing JSON; policy numeric values are strings or integers."""
    _reject_float(value)
    return json.dumps(_canonicalize(value), ensure_ascii=False, separators=(",", ":"))
