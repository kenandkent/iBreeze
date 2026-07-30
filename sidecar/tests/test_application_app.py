from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ibreeze.application.app import SidecarApplication
from ibreeze.application.lifecycle import LifecyclePhase
from ibreeze.observability.health import HealthSnapshot


def _make_app(**kwargs) -> SidecarApplication:
    defaults = dict(
        socket_path=Path("/tmp/test.sock"),
        profile_root=Path("/tmp/test_profile"),
        app_version="2.0.0",
        startup_token=b"a" * 32,
        backend_origin="https://api.example.com",
        app_user_id="user-abc",
        masked_identifier="mask-123",
        device_id="dev-xyz",
        profile_mode="offline",
    )
    defaults.update(kwargs)
    return SidecarApplication(**defaults)


class TestSidecarApplicationInit:
    def test_stores_all_fields(self):
        app = _make_app()
        assert app._database_path == Path("/tmp/test_profile/profile.db")
        assert app._socket_path == "/tmp/test.sock"
        assert app._app_version == "2.0.0"
        assert app._startup_token == b"a" * 32
        assert app._backend_origin == "https://api.example.com"
        assert app._app_user_id == "user-abc"
        assert app._masked_identifier == "mask-123"
        assert app._device_id == "dev-xyz"
        assert app._profile_mode == "offline"
        assert app._lifecycle is None
        assert app._rpc_server is None

    def test_database_path_joins_profile_root_and_db_name(self):
        app = _make_app(profile_root=Path("/custom/root"))
        assert app._database_path == Path("/custom/root/profile.db")

    def test_socket_path_converted_to_string(self):
        app = _make_app(socket_path=Path("/var/run/ibreeze.sock"))
        assert app._socket_path == "/var/run/ibreeze.sock"


class TestSidecarApplicationStart:
    @pytest.mark.asyncio
    async def test_creates_lifecycle_and_rpc_server(self):
        mock_lifecycle = AsyncMock()
        mock_rpc_server = AsyncMock()

        with (
            patch("ibreeze.application.app.ApplicationLifecycle", return_value=mock_lifecycle) as m_lc_cls,
            patch("ibreeze.application.app.ProductionRpcServer", return_value=mock_rpc_server) as m_rpc_cls,
        ):
            app = _make_app()
            await app.start()

            m_lc_cls.assert_called_once_with(
                Path("/tmp/test_profile/profile.db"),
                socket_path="/tmp/test.sock",
                backend_origin="https://api.example.com",
                app_user_id="user-abc",
                masked_identifier="mask-123",
                device_id="dev-xyz",
                app_version="2.0.0",
                profile_mode="offline",
            )
            mock_lifecycle.start.assert_awaited_once()

            assert m_rpc_cls.call_args[1]["lifecycle"] is mock_lifecycle
            assert m_rpc_cls.call_args[1]["socket_path"] == Path("/tmp/test.sock")
            assert m_rpc_cls.call_args[1]["startup_token"] == b"a" * 32
            assert m_rpc_cls.call_args[1]["app_version"] == "2.0.0"
            assert isinstance(m_rpc_cls.call_args[1]["launch_id"], str)
            mock_rpc_server.start.assert_awaited_once()

            assert app._lifecycle is mock_lifecycle
            assert app._rpc_server is mock_rpc_server

    @pytest.mark.asyncio
    async def test_passes_all_params_to_lifecycle(self):
        mock_lifecycle = AsyncMock()
        mock_rpc_server = AsyncMock()

        with (
            patch("ibreeze.application.app.ApplicationLifecycle", return_value=mock_lifecycle) as m_lc_cls,
            patch("ibreeze.application.app.ProductionRpcServer", return_value=mock_rpc_server),
        ):
            app = _make_app(
                socket_path=Path("/custom.sock"),
                profile_root=Path("/my/profile"),
                backend_origin="https://other.com",
                app_user_id="uid-42",
                masked_identifier="m-99",
                device_id="d-abc",
                profile_mode="online",
            )
            await app.start()

            m_lc_cls.assert_called_once_with(
                Path("/my/profile/profile.db"),
                socket_path="/custom.sock",
                backend_origin="https://other.com",
                app_user_id="uid-42",
                masked_identifier="m-99",
                device_id="d-abc",
                app_version="2.0.0",
                profile_mode="online",
            )


class TestSidecarApplicationStop:
    @pytest.mark.asyncio
    async def test_stops_rpc_server_and_lifecycle(self):
        mock_lifecycle = AsyncMock()
        mock_rpc_server = AsyncMock()

        app = _make_app()
        app._lifecycle = mock_lifecycle
        app._rpc_server = mock_rpc_server

        await app.stop()

        mock_rpc_server.stop.assert_awaited_once()
        mock_lifecycle.stop.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_stop_when_not_started(self):
        app = _make_app()
        await app.stop()

    @pytest.mark.asyncio
    async def test_stop_when_only_lifecycle_exists(self):
        mock_lifecycle = AsyncMock()
        app = _make_app()
        app._lifecycle = mock_lifecycle
        app._rpc_server = None

        await app.stop()

        mock_lifecycle.stop.assert_awaited_once()


class TestSidecarApplicationHealth:
    @pytest.mark.asyncio
    async def test_returns_unhealthy_when_not_started(self):
        app = _make_app()
        snapshot = await app.health()
        assert snapshot.status == "unhealthy"

    @pytest.mark.asyncio
    async def test_delegates_to_lifecycle_when_started(self):
        mock_snapshot = HealthSnapshot(status="healthy")
        mock_lifecycle = AsyncMock()
        mock_lifecycle.health.return_value = mock_snapshot

        app = _make_app()
        app._lifecycle = mock_lifecycle

        result = await app.health()
        assert result is mock_snapshot
        assert result.status == "healthy"
        mock_lifecycle.health.assert_awaited_once()


class TestSidecarApplicationProperties:
    def test_rpc_server_property(self):
        mock_server = MagicMock()
        app = _make_app()
        app._rpc_server = mock_server
        assert app.rpc_server is mock_server

    def test_rpc_server_raises_when_none(self):
        app = _make_app()
        with pytest.raises(AssertionError):
            _ = app.rpc_server

    def test_lifecycle_property(self):
        mock_lc = MagicMock()
        app = _make_app()
        app._lifecycle = mock_lc
        assert app.lifecycle is mock_lc

    def test_lifecycle_raises_when_none(self):
        app = _make_app()
        with pytest.raises(AssertionError):
            _ = app.lifecycle

    def test_write_queue_delegates_to_lifecycle(self):
        mock_wq = MagicMock()
        mock_lc = MagicMock()
        mock_lc.write_queue = mock_wq
        app = _make_app()
        app._lifecycle = mock_lc
        assert app.write_queue is mock_wq

    def test_read_pool_delegates_to_lifecycle(self):
        mock_rp = MagicMock()
        mock_lc = MagicMock()
        mock_lc.read_pool = mock_rp
        app = _make_app()
        app._lifecycle = mock_lc
        assert app.read_pool is mock_rp

    def test_unit_of_work_delegates_to_lifecycle(self):
        mock_uow = MagicMock()
        mock_lc = MagicMock()
        mock_lc.unit_of_work = mock_uow
        app = _make_app()
        app._lifecycle = mock_lc
        assert app.unit_of_work is mock_uow


class TestSidecarApplicationIsReady:
    def test_false_when_lifecycle_none(self):
        app = _make_app()
        assert app.is_ready is False

    def test_false_when_lifecycle_not_handshake_ready(self):
        mock_lc = MagicMock()
        mock_lc.phase = LifecyclePhase.WRITER_OPENED
        app = _make_app()
        app._lifecycle = mock_lc
        assert app.is_ready is False

    def test_true_when_lifecycle_handshake_ready(self):
        mock_lc = MagicMock()
        mock_lc.phase = LifecyclePhase.HANDSHAKE_READY
        app = _make_app()
        app._lifecycle = mock_lc
        assert app.is_ready is True
