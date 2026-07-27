"""Automatic log redaction for sensitive patterns."""

from __future__ import annotations

import re
from typing import Any

_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r'Authorization["\s:=]+[^\n]+', re.I), "Authorization [REDACTED]"),
    (re.compile(r'Cookie["\s:=]+[^\n]+', re.I), "Cookie [REDACTED]"),
    (re.compile(r'password["\s:=]+[^\n]+', re.I), "password [REDACTED]"),
    (re.compile(r'token["\s:=]+[^\n]+', re.I), "token [REDACTED]"),
    (re.compile(r'api[_-]?key["\s:=]+[^\n]+', re.I), "api_key [REDACTED]"),
    (re.compile(r'secret["\s:=]+[^\n]+', re.I), "secret [REDACTED]"),
]


def redact_string(text: str) -> str:
    """Redact sensitive patterns from a string."""
    result = text
    for pattern, replacement in _PATTERNS:
        result = pattern.sub(replacement, result)
    return result


def redact_dict(data: dict[str, Any]) -> dict[str, Any]:
    """Recursively redact sensitive values in a dict."""
    redacted: dict[str, Any] = {}
    for k, v in data.items():
        if isinstance(v, str):
            redacted[k] = redact_string(v)
        elif isinstance(v, dict):
            redacted[k] = redact_dict(v)
        elif isinstance(v, list):
            redacted[k] = [
                redact_dict(i) if isinstance(i, dict)
                else redact_string(i) if isinstance(i, str)
                else i
                for i in v
            ]
        else:
            redacted[k] = v
    return redacted
