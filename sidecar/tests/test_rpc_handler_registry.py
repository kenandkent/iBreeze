from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch, sentinel
from uuid import UUID

import aiosqlite
import pytest

from ibreeze.rpc.handler_registry import (
    _LEGACY_SKIP_PREFIXES,
    _LocalDBWrapper,
    _read_wrapper,
    _write_wrapper_factory,
    register_legacy_handlers,
)
from ibreeze.rpc.dispatcher import Dispatcher
from ibreeze.persistence.write_queue import WriteQueue


class TestLocalDBWrapper:
    async def test_wraps_writer_connection(self):
        writer = AsyncMock(spec=aiosqlite.Connection)
        wrapper = _LocalDBWrapper(writer, "/path/to/profile.db")
        assert wrapper.write_connection is writer
        assert wrapper.db_path == Path("/path/to/profile.db")

    async def test_fetch_val_returns_value(self):
        writer = AsyncMock(spec=aiosqlite.Connection)
        cursor = AsyncMock()
        cursor.fetchone = AsyncMock(return_value=(42,))
        writer.execute = AsyncMock(return_value=cursor)
        wrapper = _LocalDBWrapper(writer, "/dev/null")
        result = await wrapper.fetch_val("SELECT ?", (42,))
        assert result == 42
        writer.execute.assert_called_once_with("SELECT ?", (42,))

    async def test_fetch_val_returns_none_when_no_row(self):
        writer = AsyncMock(spec=aiosqlite.Connection)
        cursor = AsyncMock()
        cursor.fetchone = AsyncMock(return_value=None)
        writer.execute = AsyncMock(return_value=cursor)
        wrapper = _LocalDBWrapper(writer, "/dev/null")
        result = await wrapper.fetch_val("SELECT 1", ())
        assert result is None

    async def test_fetch_one_returns_dict(self):
        writer = AsyncMock(spec=aiosqlite.Connection)
        cursor = AsyncMock()
        cursor.description = [("val",)]
        cursor.fetchone = AsyncMock(return_value=(42,))
        writer.execute = AsyncMock(return_value=cursor)
        wrapper = _LocalDBWrapper(writer, "/dev/null")
        result = await wrapper.fetch_one("SELECT ? AS val", (42,))
        assert result == {"val": 42}

    async def test_fetch_one_returns_none_when_no_row(self):
        writer = AsyncMock(spec=aiosqlite.Connection)
        cursor = AsyncMock()
        cursor.fetchone = AsyncMock(return_value=None)
        writer.execute = AsyncMock(return_value=cursor)
        wrapper = _LocalDBWrapper(writer, "/dev/null")
        result = await wrapper.fetch_one("SELECT 1", ())
        assert result is None

    async def test_execute_write_commits(self):
        writer = AsyncMock(spec=aiosqlite.Connection)
        cursor = AsyncMock()
        writer.execute = AsyncMock(return_value=cursor)
        wrapper = _LocalDBWrapper(writer, "/dev/null")
        result = await wrapper.execute_write("UPDATE t SET x=?", (1,))
        assert result is cursor
        writer.execute.assert_called_once_with("UPDATE t SET x=?", (1,))
        writer.commit.assert_awaited_once()


class TestReadWrapper:
    async def test_ignores_session_parameter(self):
        handler = AsyncMock(return_value="result")
        wrapped = _read_wrapper(handler)
        result = await wrapped({"key": "val"}, sentinel.session)
        assert result == "result"
        handler.assert_called_once_with({"key": "val"})

    async def test_passes_params_to_handler(self):
        handler = AsyncMock(return_value=99)
        wrapped = _read_wrapper(handler)
        result = await wrapped({"a": 1, "b": 2}, None)
        assert result == 99
        handler.assert_called_once_with({"a": 1, "b": 2})


class TestWriteWrapperFactory:
    async def test_submits_through_write_queue(self):
        handler = AsyncMock()
        write_queue = AsyncMock(spec=WriteQueue)
        write_queue.submit = AsyncMock(return_value="queued_result")

        wrapped = _write_wrapper_factory(handler, "test.method", write_queue)
        result = await wrapped({"param": 1}, sentinel.session)

        assert result == "queued_result"
        write_queue.submit.assert_called_once()
        args = write_queue.submit.call_args[0]
        assert args[0] == "legacy.test.method"
        assert isinstance(args[3], type(lambda: None))

    async def test_exec_function_calls_handler_with_params(self):
        handler = AsyncMock(return_value="handler_result")
        write_queue = MagicMock(spec=WriteQueue)
        write_queue.submit = AsyncMock(return_value="queued")

        wrapped = _write_wrapper_factory(handler, "some.method", write_queue)
        await wrapped({"x": 10}, None)

        exec_fn = write_queue.submit.call_args[0][3]
        result = await exec_fn(sentinel.conn)
        assert result == "handler_result"
        handler.assert_called_once_with({"x": 10})

    async def test_exec_ignores_connection_argument(self):
        handler = AsyncMock(return_value=42)
        write_queue = MagicMock(spec=WriteQueue)
        write_queue.submit = AsyncMock(return_value="queued")

        wrapped = _write_wrapper_factory(handler, "m", write_queue)
        await wrapped({}, None)

        exec_fn = write_queue.submit.call_args[0][3]
        result = await exec_fn("any_connection")
        assert result == 42


READ_METHODS_FOR_TEST = frozenset({
    "company.get",
    "company.list",
    "employee.list",
    "department.get",
    "task.get",
    "conversation.list",
})


@pytest.fixture
def rpc_server_methods():
    return {
        "company.get": AsyncMock(),
        "company.create": AsyncMock(),
        "employee.list": AsyncMock(),
        "employee.updateDisplayName": AsyncMock(),
        "review.submit": AsyncMock(),
        "review.listIssues": AsyncMock(),
        "completion.complete": AsyncMock(),
        "rework.start": AsyncMock(),
        "task.get": AsyncMock(),
        "catalog.sync": AsyncMock(),
        "conversation.list": AsyncMock(),
    }


@pytest.fixture
def mock_rpc_server(rpc_server_methods):
    server = MagicMock()
    server.methods = rpc_server_methods
    return server


class TestRegisterLegacyHandlers:
    def test_skips_review_completion_rework_prefixes(
        self, mock_rpc_server, rpc_server_methods,
    ):
        dispatcher = Dispatcher()
        writer = AsyncMock(spec=aiosqlite.Connection)
        write_queue = MagicMock(spec=WriteQueue)

        with (
            patch("ibreeze.rpc_server.RPCServer", return_value=mock_rpc_server),
            patch("ibreeze.rpc_server.READ_METHODS", READ_METHODS_FOR_TEST),
        ):
            count = register_legacy_handlers(
                dispatcher=dispatcher,
                writer=writer,
                profile_path=Path("/profile.db"),
                write_queue=write_queue,
            )

        assert not dispatcher.has_method("review.submit")
        assert not dispatcher.has_method("review.listIssues")
        assert not dispatcher.has_method("completion.complete")
        assert not dispatcher.has_method("rework.start")
        expected_registered = 7  # 11 total - 4 skipped prefixes = 7
        assert count == expected_registered
        assert dispatcher.method_count == expected_registered

    def test_skips_methods_already_in_dispatcher(
        self, mock_rpc_server, rpc_server_methods,
    ):
        dispatcher = Dispatcher()
        dispatcher.register("task.get", AsyncMock())
        dispatcher.register("company.get", AsyncMock())
        writer = AsyncMock(spec=aiosqlite.Connection)
        write_queue = MagicMock(spec=WriteQueue)

        with (
            patch("ibreeze.rpc_server.RPCServer", return_value=mock_rpc_server),
            patch("ibreeze.rpc_server.READ_METHODS", READ_METHODS_FOR_TEST),
        ):
            count = register_legacy_handlers(
                dispatcher=dispatcher,
                writer=writer,
                profile_path=Path("/profile.db"),
                write_queue=write_queue,
            )

        expected_skipped_prefix = 4  # review.*, completion.*, rework.*
        expected_already = 2  # task.get, company.get
        expected_registered = 11 - expected_skipped_prefix - expected_already
        assert count == expected_registered

    def test_registers_read_methods_without_write_queue(
        self, mock_rpc_server, rpc_server_methods,
    ):
        dispatcher = Dispatcher()
        writer = AsyncMock(spec=aiosqlite.Connection)
        write_queue = MagicMock(spec=WriteQueue)
        write_queue.submit = AsyncMock()

        with (
            patch("ibreeze.rpc_server.RPCServer", return_value=mock_rpc_server),
            patch("ibreeze.rpc_server.READ_METHODS", READ_METHODS_FOR_TEST),
        ):
            register_legacy_handlers(
                dispatcher=dispatcher,
                writer=writer,
                profile_path=Path("/profile.db"),
                write_queue=write_queue,
            )

        assert dispatcher.has_method("company.get")
        assert dispatcher.has_method("employee.list")
        assert dispatcher.has_method("conversation.list")
        rpc_server_methods["company.get"].assert_not_called()
        rpc_server_methods["employee.list"].assert_not_called()

    def test_registers_write_methods_with_write_queue(
        self, mock_rpc_server, rpc_server_methods,
    ):
        dispatcher = Dispatcher()
        writer = AsyncMock(spec=aiosqlite.Connection)
        write_queue = MagicMock(spec=WriteQueue)
        write_queue.submit = AsyncMock()

        with (
            patch("ibreeze.rpc_server.RPCServer", return_value=mock_rpc_server),
            patch("ibreeze.rpc_server.READ_METHODS", READ_METHODS_FOR_TEST),
        ):
            register_legacy_handlers(
                dispatcher=dispatcher,
                writer=writer,
                profile_path=Path("/profile.db"),
                write_queue=write_queue,
            )

        assert dispatcher.has_method("company.create")
        assert dispatcher.has_method("employee.updateDisplayName")
        assert dispatcher.has_method("catalog.sync")

    @pytest.mark.asyncio
    async def test_read_method_handler_ignores_session(self, mock_rpc_server, rpc_server_methods):
        dispatcher = Dispatcher()
        writer = AsyncMock(spec=aiosqlite.Connection)
        write_queue = MagicMock(spec=WriteQueue)

        with (
            patch("ibreeze.rpc_server.RPCServer", return_value=mock_rpc_server),
            patch("ibreeze.rpc_server.READ_METHODS", READ_METHODS_FOR_TEST),
        ):
            register_legacy_handlers(
                dispatcher=dispatcher,
                writer=writer,
                profile_path=Path("/profile.db"),
                write_queue=write_queue,
            )

        await dispatcher.dispatch("company.get", {"id": "1"}, sentinel.session)
        rpc_server_methods["company.get"].assert_called_once_with({"id": "1"})

    @pytest.mark.asyncio
    async def test_write_method_handler_submits_to_queue(self, mock_rpc_server, rpc_server_methods):
        dispatcher = Dispatcher()
        writer = AsyncMock(spec=aiosqlite.Connection)
        write_queue = MagicMock(spec=WriteQueue)
        write_queue.submit = AsyncMock(return_value="queued")

        with (
            patch("ibreeze.rpc_server.RPCServer", return_value=mock_rpc_server),
            patch("ibreeze.rpc_server.READ_METHODS", READ_METHODS_FOR_TEST),
        ):
            register_legacy_handlers(
                dispatcher=dispatcher,
                writer=writer,
                profile_path=Path("/profile.db"),
                write_queue=write_queue,
            )

        await dispatcher.dispatch("company.create", {"name": "NewCo"}, sentinel.session)
        args = write_queue.submit.call_args[0]
        assert args[0] == "legacy.company.create"
        assert isinstance(args[3], type(lambda: None))
        rpc_server_methods["company.create"].assert_not_called()

    @pytest.mark.asyncio
    async def test_all_methods_become_read_when_write_queue_is_none(
        self, mock_rpc_server, rpc_server_methods,
    ):
        dispatcher = Dispatcher()
        writer = AsyncMock(spec=aiosqlite.Connection)

        with (
            patch("ibreeze.rpc_server.RPCServer", return_value=mock_rpc_server),
            patch("ibreeze.rpc_server.READ_METHODS", READ_METHODS_FOR_TEST),
        ):
            register_legacy_handlers(
                dispatcher=dispatcher,
                writer=writer,
                profile_path=Path("/profile.db"),
                write_queue=None,
            )

        assert dispatcher.has_method("company.create")
        assert dispatcher.has_method("catalog.sync")
        await dispatcher.dispatch("company.create", {"name": "NewCo"}, sentinel.session)
        rpc_server_methods["company.create"].assert_called_once_with({"name": "NewCo"})

    def test_returns_zero_when_no_methods(self):
        mock_server = MagicMock()
        mock_server.methods = {}
        dispatcher = Dispatcher()
        writer = AsyncMock(spec=aiosqlite.Connection)

        with (
            patch("ibreeze.rpc_server.RPCServer", return_value=mock_server),
            patch("ibreeze.rpc_server.READ_METHODS", READ_METHODS_FOR_TEST),
        ):
            count = register_legacy_handlers(
                dispatcher=dispatcher,
                writer=writer,
                profile_path=Path("/profile.db"),
                write_queue=MagicMock(spec=WriteQueue),
            )

        assert count == 0
        assert dispatcher.method_count == 0


class TestLegacySkipPrefixes:
    def test_contains_expected_prefixes(self):
        assert "review." in _LEGACY_SKIP_PREFIXES
        assert "completion." in _LEGACY_SKIP_PREFIXES
        assert "rework." in _LEGACY_SKIP_PREFIXES
        assert len(_LEGACY_SKIP_PREFIXES) == 3

    def test_prefixes_skip_review_methods(self):
        assert any("review.submit".startswith(p) for p in _LEGACY_SKIP_PREFIXES)
        assert any("review.listIssues".startswith(p) for p in _LEGACY_SKIP_PREFIXES)
        assert any("review.rerun".startswith(p) for p in _LEGACY_SKIP_PREFIXES)

    def test_prefixes_skip_completion_methods(self):
        assert any("completion.complete".startswith(p) for p in _LEGACY_SKIP_PREFIXES)

    def test_prefixes_skip_rework_methods(self):
        assert any("rework.start".startswith(p) for p in _LEGACY_SKIP_PREFIXES)
        assert any("rework.retry".startswith(p) for p in _LEGACY_SKIP_PREFIXES)

    def test_does_not_skip_other_methods(self):
        assert not any("company.get".startswith(p) for p in _LEGACY_SKIP_PREFIXES)
        assert not any("task.create".startswith(p) for p in _LEGACY_SKIP_PREFIXES)
        assert not any("reviewer.assign".startswith(p) for p in _LEGACY_SKIP_PREFIXES)
