"""Additional coverage tests for ibreeze/logging_config.py."""

from __future__ import annotations

import json
import logging
import logging.handlers
import os
import time
from pathlib import Path

from ibreeze.logging_config import (
    ConsoleFormatter,
    JSONFormatter,
    RedactionFilter,
    _clean_old_logs,
    get_logger,
    setup_logging,
)


class TestRedactionFilter:
    def test_redacts_sensitive_dict_args(self) -> None:
        record = logging.LogRecord(
            "ibreeze.rpc",
            logging.INFO,
            __file__,
            1,
            "user=%(username)s pw=%(password)s key=%(api_key)s",
            {"username": "alice", "password": "s3cret", "api_key": "k123"},
            None,
        )
        RedactionFilter().filter(record)
        assert record.args["password"] == "[REDACTED]"
        assert record.args["api_key"] == "[REDACTED]"
        assert record.args["username"] == "alice"

    def test_skips_non_string_msg(self) -> None:
        record = logging.LogRecord("ibreeze.rpc", logging.INFO, __file__, 1, None, (), None)
        assert RedactionFilter().filter(record) is True

    def test_skips_empty_args(self) -> None:
        record = logging.LogRecord("ibreeze.rpc", logging.INFO, __file__, 1, "plain", (), None)
        assert RedactionFilter().filter(record) is True

    def test_skips_non_dict_args(self) -> None:
        record = logging.LogRecord("ibreeze.rpc", logging.INFO, __file__, 1, "one %s two %s", ("a", "b"), None)
        RedactionFilter().filter(record)
        assert record.args == ("a", "b")

    def test_redacts_sensitive_key_tokens(self) -> None:
        record = logging.LogRecord(
            "ibreeze.rpc",
            logging.INFO,
            __file__,
            1,
            'token="abc123" password=supersecret cookie="c"',
            (),
            None,
        )
        RedactionFilter().filter(record)
        assert "abc123" not in record.msg
        assert "supersecret" not in record.msg
        assert "[REDACTED]" in record.msg

    def test_truncates_long_message(self) -> None:
        long_text = "x" * 600
        rendered = RedactionFilter()._redact_string(long_text)
        assert rendered == ("x" * 500) + "...[truncated]"

    def test_short_message_not_truncated(self) -> None:
        rendered = RedactionFilter()._redact_string("short")
        assert rendered == "short"


class TestJSONFormatter:
    def test_format_with_extra_attrs(self) -> None:
        record = logging.LogRecord("ibreeze.rpc", logging.INFO, __file__, 1, "hello %s", ("world",), None)
        record.trace_id = "trace-1"
        record.company_id = "company-1"
        record.task_id = "task-1"
        record.run_id = "run-1"
        record.method = "list"
        record.elapsed_ms = 12
        record.status = "ok"
        record.error = None
        payload = json.loads(JSONFormatter().format(record))
        assert payload["message"] == "hello world"
        assert payload["level"] == "INFO"
        assert payload["logger"] == "ibreeze.rpc"
        assert payload["trace_id"] == "trace-1"
        assert payload["company_id"] == "company-1"
        assert payload["task_id"] == "task-1"
        assert payload["run_id"] == "run-1"
        assert payload["method"] == "list"
        assert payload["elapsed_ms"] == 12
        assert payload["status"] == "ok"
        assert "error" not in payload
        assert "timestamp" in payload

    def test_format_without_extra_attrs(self) -> None:
        record = logging.LogRecord("ibreeze.rpc", logging.INFO, __file__, 1, "plain", (), None)
        payload = json.loads(JSONFormatter().format(record))
        assert set(payload) == {"timestamp", "level", "logger", "message"}


class TestConsoleFormatter:
    def test_format(self) -> None:
        record = logging.LogRecord("ibreeze.rpc", logging.INFO, __file__, 1, "booted", (), None)
        rendered = ConsoleFormatter().format(record)
        assert record.levelname in rendered
        assert "ibreeze.rpc" in rendered
        assert "booted" in rendered


class TestSetupLogging:
    def test_setup_with_log_dir(self, tmp_path: Path) -> None:
        root = logging.getLogger()
        original_handlers = list(root.handlers)
        original_level = root.level
        try:
            setup_logging(level="DEBUG", log_dir=str(tmp_path), backup_count=2, retention_days=30)
            assert (tmp_path / "sidecar.jsonl").exists()
            handler_types = [type(h) for h in root.handlers]
            assert logging.handlers.TimedRotatingFileHandler in handler_types
            assert logging.StreamHandler in handler_types
            assert root.level == logging.DEBUG
        finally:
            root.handlers[:] = original_handlers
            root.setLevel(original_level)

    def test_setup_default_log_dir(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.setattr(os.path, "expanduser", lambda *args, **kwargs: str(tmp_path))
        root = logging.getLogger()
        original_handlers = list(root.handlers)
        original_level = root.level
        try:
            setup_logging(level="WARNING", log_dir=None, retention_days=30)
            assert (tmp_path / "sidecar.jsonl").exists()
        finally:
            root.handlers[:] = original_handlers
            root.setLevel(original_level)

    def test_clean_old_logs_removes_expired(self, tmp_path: Path) -> None:
        old_file = tmp_path / "sidecar.jsonl.2020-01-01"
        old_file.write_text("old")
        past = time.time() - 40 * 86400
        os.utime(old_file, (past, past))
        root = logging.getLogger()
        original_handlers = list(root.handlers)
        original_level = root.level
        try:
            setup_logging(log_dir=str(tmp_path), retention_days=30)
            assert not old_file.exists()
            assert (tmp_path / "sidecar.jsonl").exists()
        finally:
            root.handlers[:] = original_handlers
            root.setLevel(original_level)

    def test_clean_old_logs_error_swallowed(self, tmp_path: Path, monkeypatch) -> None:
        def boom(self, pattern):  # noqa: ARG001 - signature matches Path.glob
            raise OSError("boom")

        monkeypatch.setattr(Path, "glob", boom)
        _clean_old_logs(str(tmp_path), 30)

    def test_get_logger(self) -> None:
        assert get_logger("ibreeze.rpc.test").name == "ibreeze.rpc.test"
