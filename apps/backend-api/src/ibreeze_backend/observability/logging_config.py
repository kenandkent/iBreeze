"""Structured logging configuration with redaction."""

import json
import logging
import re
import sys
from datetime import UTC, datetime

REDACTED = "***REDACTED***"

_SENSITIVE_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"(?i)(password|passwd|pwd)\s*[=:]\s*\S+"),
    re.compile(r"(?i)(token|api[_-]?key|secret|authorization)\s*[=:]\s*\S+"),
    re.compile(r"(?i)(cookie)\s*[=:]\s*\S+"),
]

_SENSITIVE_HEADERS: set[str] = {
    "authorization",
    "cookie",
    "set-cookie",
    "x-api-key",
}


class RedactionFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = self._redact_string(record.msg)
        if record.args:
            if isinstance(record.args, dict):
                record.args = {
                    k: self._redact_string(str(v)) if isinstance(v, str) else v for k, v in record.args.items()
                }
            elif isinstance(record.args, tuple):
                record.args = tuple(self._redact_string(str(a)) if isinstance(a, str) else a for a in record.args)
        return True

    def _redact_string(self, text: str) -> str:
        for pattern in _SENSITIVE_PATTERNS:
            text = pattern.sub(lambda m: m.group(0).split("=")[0].split(":")[0] + "=" + REDACTED, text)
        return text


class JSONFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        log_entry: dict[str, object] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.msg,
        }
        if hasattr(record, "request_id"):
            log_entry["request_id"] = record.request_id  # type: ignore[attr-defined]
        if record.exc_info and record.exc_info[0] is not None:
            log_entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_entry, default=str)


class ConsoleFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        timestamp = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S")
        return f"{timestamp} [{record.levelname}] {record.name}: {record.msg}"


def setup_logging(level: str = "INFO", json_format: bool = True) -> None:
    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))

    for handler in root.handlers[:]:
        root.removeHandler(handler)

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JSONFormatter() if json_format else ConsoleFormatter())
    handler.addFilter(RedactionFilter())
    root.addHandler(handler)

    for noisy in ("uvicorn.access", "uvicorn.error", "sqlalchemy.engine"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
