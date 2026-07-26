"""RFC 8785 — JSON Canonicalization Scheme (JCS) for deterministic signing."""

import re
from collections.abc import Mapping
from typing import Any

_ESCAPE: dict[int, str] = {
    0x08: "\\b",
    0x09: "\\t",
    0x0A: "\\n",
    0x0C: "\\f",
    0x0D: "\\r",
    0x22: '\\"',
    0x5C: "\\\\",
}

_ESCAPE_RE = re.compile(r"[\x00-\x1f\u007f\"\\/]")


def _replace_control(m: re.Match[str]) -> str:
    ch = m.group(0)
    cp = ord(ch)
    if cp in _ESCAPE:
        return _ESCAPE[cp]
    if cp == 0x2F:
        return "\\/"
    return f"\\u{cp:04x}"


def _escape_string(s: str) -> str:
    return _ESCAPE_RE.sub(_replace_control, s)


def _serialize_number(val: float) -> str:
    if val != val:
        raise ValueError("NaN is not allowed in canonical JSON")
    if val == float("inf") or val == -float("inf"):
        raise ValueError("Infinity is not allowed in canonical JSON")
    if val == int(val) and abs(val) < (1 << 53):
        return str(int(val))
    result = f"{val:.15g}"
    if "." not in result and "e" not in result and "E" not in result:
        result += ".0"
    return result


def _canonicalize(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        if value < -(1 << 53) or value > (1 << 53):
            raise ValueError(f"Integer out of safe range: {value}")
        return str(value)
    if isinstance(value, float):
        return _serialize_number(value)
    if isinstance(value, str):
        return '"' + _escape_string(value) + '"'
    if isinstance(value, Mapping):
        keys = sorted(value.keys(), key=str)
        items = ",".join(
            _canonicalize(k) + ":" + _canonicalize(value[k]) for k in keys
        )
        return "{" + items + "}"
    if isinstance(value, (list, tuple)):
        items = ",".join(_canonicalize(v) for v in value)
        return "[" + items + "]"
    raise TypeError(f"Unsupported type: {type(value).__name__}")


def canonical_json(value: Any) -> str:
    return _canonicalize(value)


def canonical_bytes(value: Any) -> bytes:
    return canonical_json(value).encode("utf-8")
