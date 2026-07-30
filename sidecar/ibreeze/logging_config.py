"""Structured logging configuration for iBreeze sidecar.

Usage:
    from ibreeze.logging_config import setup_logging, get_logger
    setup_logging()
    logger = get_logger("ibreeze.rpc_server")
"""

from __future__ import annotations

import json
import logging
import logging.handlers
import os
import re
from datetime import UTC, datetime
from pathlib import Path

_SENSITIVE_KEYS = frozenset(
    {
        "password",
        "token",
        "api_key",
        "authorization",
        "cookie",
        "secret",
        "credential",
        "access_token",
        "refresh_token",
        "private_key",
        "jwt",
        "bearer",
    }
)

_REDACTED = "[REDACTED]"
_TRUNCATE_LENGTH = 100


class RedactionFilter(logging.Filter):
    """Automatically redact sensitive values from log records."""

    def filter(self, record: logging.LogRecord) -> bool:
        if hasattr(record, "msg") and isinstance(record.msg, str):
            record.msg = self._redact_string(record.msg)
        if hasattr(record, "args") and record.args:
            if isinstance(record.args, dict):
                record.args = {k: _REDACTED if k.lower() in _SENSITIVE_KEYS else v for k, v in record.args.items()}
        return True

    def _redact_string(self, text: str) -> str:
        for key in _SENSITIVE_KEYS:
            pattern = re.compile(rf'{key}["\s:=]+\S+', re.IGNORECASE)
            text = pattern.sub(f"{key} {_REDACTED}", text)
        if len(text) > 500:
            text = text[:500] + "...[truncated]"
        return text


class JSONFormatter(logging.Formatter):
    """JSON log formatter with UTC timestamps."""

    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            "timestamp": datetime.fromtimestamp(record.created, UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key in ("trace_id", "company_id", "task_id", "run_id", "method", "elapsed_ms", "status", "error"):
            val = getattr(record, key, None)
            if val is not None:
                log_entry[key] = val
        return json.dumps(log_entry, ensure_ascii=False)


class ConsoleFormatter(logging.Formatter):
    """Human-readable console formatter."""

    def format(self, record: logging.LogRecord) -> str:
        ts = datetime.fromtimestamp(record.created, UTC).strftime("%Y-%m-%d %H:%M:%S")
        return f"{ts} [{record.levelname:5s}] [{record.name}] {record.getMessage()}"


def setup_logging(
    level: str = "INFO",
    log_dir: str | None = None,
    backup_count: int = 30,  # Days to keep (was: max files)
    retention_days: int = 30,
) -> None:
    """Configure sidecar logging with JSON file output + console.

    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR)
        log_dir: Directory for log files. Defaults to ~/.ibreeze/logs/
        backup_count: Days to keep rotated logs (default 30)
        retention_days: Days to keep old logs (default 30)
    """
    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))

    root.handlers.clear()

    if log_dir is None:
        log_dir = os.path.expanduser("~/.ibreeze/logs")
    Path(log_dir).mkdir(parents=True, exist_ok=True)

    json_handler = logging.handlers.TimedRotatingFileHandler(
        os.path.join(log_dir, "sidecar.jsonl"),
        when="midnight",
        interval=1,
        backupCount=backup_count,
        encoding="utf-8",
        utc=True,
    )
    json_handler.setFormatter(JSONFormatter())
    json_handler.addFilter(RedactionFilter())
    root.addHandler(json_handler)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(ConsoleFormatter())
    console_handler.addFilter(RedactionFilter())
    root.addHandler(console_handler)

    _clean_old_logs(log_dir, retention_days)


def _clean_old_logs(log_dir: str, retention_days: int) -> None:
    """Remove log files older than retention_days."""
    import time as _time

    cutoff = _time.time() - (retention_days * 86400)
    try:
        for f in Path(log_dir).glob("sidecar.jsonl*"):
            if f.is_file() and f.stat().st_mtime < cutoff:
                f.unlink()
    except Exception:
        pass


def get_logger(name: str) -> logging.Logger:
    """Get a named logger."""
    return logging.getLogger(name)
