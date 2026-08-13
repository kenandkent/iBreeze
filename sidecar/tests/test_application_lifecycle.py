from __future__ import annotations

from pathlib import Path
from unittest.mock import ANY, AsyncMock, MagicMock, patch

import pytest

from ibreeze.application.lifecycle import ApplicationLifecycle, LifecyclePhase
from ibreeze.observability.health import HealthSnapshot, ProfileHealth
from ibreeze.workers.spec import WorkerHealth


def _wire_profile_queue(lifecycle: ApplicationLifecycle, writer: AsyncMock) -> AsyncMock:
    """Execute queued profile callbacks against the mocked writer."""
    queue = AsyncMock()

    async def submit(**kwargs):
        return await kwargs["execute"](writer)

    queue.submit.side_effect = submit
    lifecycle._write_queue = queue
    return queue


class TestApplicationLifecycleInit:
    def test_init_defaults(self):
        profile_path = Path("/tmp/test.db")
        lc = ApplicationLifecycle(profile_path)
        assert lc._profile_path == profile_path
        assert lc._socket_path is None
        assert lc._backend_origin == ""
        assert lc._app_user_id == ""
        assert lc._masked_identifier == ""
        assert lc._device_id == ""
        assert lc._app_version == "0.0.0"
        assert lc._profile_mode == "offline"
        assert lc._phase == LifecyclePhase.INIT
        assert lc._prepared is None
        assert lc._writer is None
        assert lc._read_pool is None
        assert lc._write_queue is None
        assert lc._unit_of_work is None
        assert lc._workers is None

    def test_init_all_params(self):
        profile_path = Path("/tmp/test.db")
        lc = ApplicationLifecycle(
            profile_path,
            socket_path="/tmp/sock",
            backend_origin="https://api.example.com",
            app_user_id="user-abc",
            masked_identifier="mask-123",
            device_id="dev-xyz",
            app_version="2.0.0",
            profile_mode="online",
        )
        assert lc._profile_path == profile_path
        assert lc._socket_path == "/tmp/sock"
        assert lc._backend_origin == "https://api.example.com"
        assert lc._app_user_id == "user-abc"
        assert lc._masked_identifier == "mask-123"
        assert lc._device_id == "dev-xyz"
        assert lc._app_version == "2.0.0"
        assert lc._profile_mode == "online"

    def test_dispatcher_and_reverse_table_created(self):
        lc = ApplicationLifecycle(Path("/tmp/test.db"))
        assert lc._dispatcher is not None
        assert lc._reverse_table is not None


class TestApplicationLifecycleProperties:
    def test_phase_property(self):
        lc = ApplicationLifecycle(Path("/tmp/test.db"))
        assert lc.phase == LifecyclePhase.INIT

    def test_writer_property_raises_when_none(self):
        lc = ApplicationLifecycle(Path("/tmp/test.db"))
        with pytest.raises(AssertionError):
            _ = lc.writer

    def test_read_pool_property_raises_when_none(self):
        lc = ApplicationLifecycle(Path("/tmp/test.db"))
        with pytest.raises(AssertionError):
            _ = lc.read_pool

    def test_write_queue_property_raises_when_none(self):
        lc = ApplicationLifecycle(Path("/tmp/test.db"))
        with pytest.raises(AssertionError):
            _ = lc.write_queue

    def test_unit_of_work_property_raises_when_none(self):
        lc = ApplicationLifecycle(Path("/tmp/test.db"))
        with pytest.raises(AssertionError):
            _ = lc.unit_of_work

    def test_workers_property_raises_when_none(self):
        lc = ApplicationLifecycle(Path("/tmp/test.db"))
        with pytest.raises(AssertionError):
            _ = lc.workers

    def test_dispatcher_property(self):
        lc = ApplicationLifecycle(Path("/tmp/test.db"))
        assert lc.dispatcher is lc._dispatcher

    def test_reverse_table_property(self):
        lc = ApplicationLifecycle(Path("/tmp/test.db"))
        assert lc.reverse_table is lc._reverse_table


class TestApplicationLifecycleStart:
    @pytest.mark.asyncio
    async def test_start_success(self, tmp_path):
        profile_path = tmp_path / "test.db"

        mock_prepared = MagicMock()
        mock_writer = AsyncMock()
        mock_read_pool = MagicMock()
        mock_write_queue = MagicMock()
        mock_uow = MagicMock()
        mock_ws_instance = AsyncMock()

        with (
            patch("ibreeze.application.lifecycle.prepare", return_value=mock_prepared) as mock_prepare,
            patch("ibreeze.application.lifecycle.open_writer", return_value=mock_writer) as m_open_writer,
            patch("ibreeze.application.lifecycle.ReadPool") as mock_rp_cls,
            patch("ibreeze.application.lifecycle.WriteQueue", return_value=mock_write_queue) as m_wq_cls,
            patch("ibreeze.application.lifecycle.UnitOfWork", return_value=mock_uow) as m_uow_cls,
            patch("ibreeze.application.lifecycle.WorkerSupervisor", return_value=mock_ws_instance) as m_ws_cls,
            patch("ibreeze.application.lifecycle.register_public_handlers", return_value=None) as m_reg_public,
            patch("ibreeze.application.lifecycle.startup_config") as m_startup_config,
        ):
            mock_rp_cls.open = AsyncMock(return_value=mock_read_pool)

            lc = ApplicationLifecycle(profile_path, socket_path="/tmp/sock")
            lc._ensure_profile_identity = AsyncMock()
            lc._init_review_completion_handlers = AsyncMock()

            await lc.start()

            assert lc._phase == LifecyclePhase.HANDSHAKE_READY
            assert lc._prepared is mock_prepared
            assert lc._writer is mock_writer
            assert lc._read_pool is mock_read_pool
            assert lc._write_queue is mock_write_queue
            assert lc._unit_of_work is mock_uow
            assert lc._workers is mock_ws_instance

            mock_prepare.assert_called_once_with(profile_path)
            m_open_writer.assert_called_once_with(profile_path)
            mock_rp_cls.open.assert_called_once_with(profile_path)
            m_wq_cls.assert_called_once_with(mock_writer)
            m_uow_cls.assert_called_once_with(connection=mock_writer)
            m_ws_cls.assert_called_once_with(
                writer=mock_writer,
                write_queue=mock_write_queue,
                read_pool=mock_read_pool,
                command_bus=lc.command_bus,
            )
            mock_ws_instance.start.assert_called_once()
            m_reg_public.assert_called_once_with(lc)
            m_startup_config.assert_called_once_with()
            lc._ensure_profile_identity.assert_called_once()
            lc._init_review_completion_handlers.assert_called_once()

    @pytest.mark.asyncio
    async def test_start_no_socket_path(self, tmp_path):
        profile_path = tmp_path / "test.db"

        with (
            patch("ibreeze.application.lifecycle.prepare") as mock_prepare,
            patch("ibreeze.application.lifecycle.open_writer") as m_open_writer,
            patch("ibreeze.application.lifecycle.ReadPool") as mock_rp_cls,
            patch("ibreeze.application.lifecycle.WriteQueue"),
            patch("ibreeze.application.lifecycle.UnitOfWork"),
            patch("ibreeze.application.lifecycle.WorkerSupervisor") as m_ws_cls,
            patch("ibreeze.application.lifecycle.register_public_handlers", return_value=None),
        ):
            mock_prepared = MagicMock()
            mock_prepare.return_value = mock_prepared
            m_open_writer.return_value = AsyncMock()
            mock_rp_cls.open = AsyncMock(return_value=MagicMock())
            m_ws_cls.return_value = AsyncMock()

            lc = ApplicationLifecycle(profile_path)
            lc._ensure_profile_identity = AsyncMock()
            lc._init_review_completion_handlers = AsyncMock()

            await lc.start()

            assert lc._phase == LifecyclePhase.HANDSHAKE_READY

    @pytest.mark.asyncio
    async def test_start_registers_system_handlers(self, tmp_path):
        mock_read_pool = MagicMock()

        with (
            patch("ibreeze.application.lifecycle.prepare"),
            patch("ibreeze.application.lifecycle.open_writer"),
            patch("ibreeze.application.lifecycle.ReadPool") as mock_rp_cls,
            patch("ibreeze.application.lifecycle.WriteQueue"),
            patch("ibreeze.application.lifecycle.UnitOfWork"),
            patch("ibreeze.application.lifecycle.WorkerSupervisor") as m_ws_cls,
            patch("ibreeze.application.lifecycle.register_public_handlers", return_value=None),
        ):
            mock_rp_cls.open = AsyncMock(return_value=mock_read_pool)
            m_ws_cls.return_value = AsyncMock()

            lc = ApplicationLifecycle(tmp_path / "test.db")
            lc._ensure_profile_identity = AsyncMock()
            lc._init_review_completion_handlers = AsyncMock()

            await lc.start()

            assert lc._dispatcher.has_method("system.health")
            assert lc._dispatcher.has_method("system.shutdown")


class TestApplicationLifecycleEnsureProfileIdentity:
    @pytest.mark.asyncio
    async def test_success(self):
        lc = ApplicationLifecycle(
            Path("/tmp/test.db"), backend_origin="https://example.com", app_user_id="user-1", masked_identifier="mask-1", device_id="dev-1"
        )
        lc._prepared = MagicMock()

        mock_cursor = AsyncMock()
        mock_cursor.fetchone = AsyncMock(
            return_value={
                "id": "profile-uuid",
                "schema_epoch": 1,
                "backend_origin": "https://example.com",
                "app_user_id": "user-1",
                "masked_identifier": "mask-1",
                "device_id": "dev-1",
                "created_at": "2026-01-01T00:00:00Z",
                "last_opened_at": "2026-01-01T00:00:00Z",
            }
        )
        mock_writer = AsyncMock()
        mock_writer.execute.return_value = mock_cursor
        lc._writer = mock_writer
        queue = _wire_profile_queue(lc, mock_writer)

        with patch("ibreeze.application.lifecycle._now_iso", return_value="2026-07-30T12:00:00Z"):
            await lc._ensure_profile_identity()

        mock_writer.execute.assert_any_call(
            "SELECT id, schema_epoch, backend_origin, app_user_id, masked_identifier, device_id FROM local_profile"
        )
        # Verify UPDATE goes through WriteQueue instead of direct writer
        queue.submit.assert_awaited_once_with(
            command_name="ensure_profile_identity",
            trace_id=ANY,
            deadline_at=ANY,
            execute=ANY,
        )

    @pytest.mark.asyncio
    async def test_raises_when_not_prepared(self):
        lc = ApplicationLifecycle(Path("/tmp/test.db"))
        lc._prepared = None
        lc._writer = AsyncMock()

        with pytest.raises(RuntimeError, match="LIFECYCLE_INVALID: profile not prepared"):
            await lc._ensure_profile_identity()

    @pytest.mark.asyncio
    async def test_raises_when_no_row(self):
        lc = ApplicationLifecycle(Path("/tmp/test.db"))
        lc._prepared = MagicMock()

        mock_cursor = AsyncMock()
        mock_cursor.fetchone = AsyncMock(return_value=None)
        mock_writer = AsyncMock()
        mock_writer.execute.return_value = mock_cursor
        lc._writer = mock_writer
        _wire_profile_queue(lc, mock_writer)

        with pytest.raises(RuntimeError, match="PROFILE_NOT_FOUND: no local_profile record"):
            await lc._ensure_profile_identity()

    @pytest.mark.asyncio
    async def test_raises_on_backend_origin_mismatch(self):
        lc = ApplicationLifecycle(Path("/tmp/test.db"), backend_origin="https://expected.com")
        lc._prepared = MagicMock()

        mock_cursor = AsyncMock()
        mock_cursor.fetchone = AsyncMock(
            return_value={
                "id": "uuid",
                "schema_epoch": 1,
                "backend_origin": "https://wrong.com",
                "app_user_id": "",
                "masked_identifier": "",
                "device_id": "",
                "created_at": "",
                "last_opened_at": "",
            }
        )
        mock_writer = AsyncMock()
        mock_writer.execute.return_value = mock_cursor
        lc._writer = mock_writer
        _wire_profile_queue(lc, mock_writer)

        with pytest.raises(RuntimeError, match="backend_origin"):
            await lc._ensure_profile_identity()

    @pytest.mark.asyncio
    async def test_raises_on_multiple_mismatches(self):
        lc = ApplicationLifecycle(
            Path("/tmp/test.db"),
            backend_origin="https://expected.com",
            app_user_id="expected-user",
            masked_identifier="expected-mask",
            device_id="expected-dev",
        )
        lc._prepared = MagicMock()

        mock_cursor = AsyncMock()
        mock_cursor.fetchone = AsyncMock(
            return_value={
                "id": "uuid",
                "schema_epoch": 1,
                "backend_origin": "wrong-origin",
                "app_user_id": "wrong-user",
                "masked_identifier": "wrong-mask",
                "device_id": "wrong-dev",
                "created_at": "",
                "last_opened_at": "",
            }
        )
        mock_writer = AsyncMock()
        mock_writer.execute.return_value = mock_cursor
        lc._writer = mock_writer
        _wire_profile_queue(lc, mock_writer)

        with pytest.raises(RuntimeError) as exc_info:
            await lc._ensure_profile_identity()
        msg = str(exc_info.value)
        assert "backend_origin" in msg
        assert "app_user_id" in msg
        assert "masked_identifier" in msg
        assert "device_id" in msg

    @pytest.mark.asyncio
    async def test_online_mode_creates_profile_when_empty(self):
        lc = ApplicationLifecycle(
            Path("/tmp/test.db"),
            backend_origin="https://example.com",
            app_user_id="user-1",
            masked_identifier="mask-1",
            device_id="dev-1",
            app_version="1.2.3",
            profile_mode="online",
        )
        lc._prepared = MagicMock()

        mock_cursor = AsyncMock()
        mock_cursor.fetchone = AsyncMock(return_value=None)
        mock_writer = AsyncMock()
        mock_writer.execute.return_value = mock_cursor
        lc._writer = mock_writer
        queue = _wire_profile_queue(lc, mock_writer)

        fake_uuid = "00000000-0000-0000-0000-000000000001"
        with (
            patch("ibreeze.application.lifecycle._now_iso", return_value="2026-07-30T12:00:00Z"),
            patch("ibreeze.application.lifecycle.uuid4", return_value=fake_uuid),
        ):
            await lc._ensure_profile_identity()

        queue.submit.assert_awaited_once_with(
            command_name="ensure_profile_identity",
            trace_id=ANY,
            deadline_at=ANY,
            execute=ANY,
        )

    @pytest.mark.asyncio
    async def test_online_mode_init_profile_sql_correct(self):
        """Verify the SQL passed to WriteQueue for init_profile is correct."""
        lc = ApplicationLifecycle(
            Path("/tmp/test.db"),
            backend_origin="https://example.com",
            app_user_id="user-1",
            masked_identifier="mask-1",
            device_id="dev-1",
            app_version="1.2.3",
            profile_mode="online",
        )
        lc._prepared = MagicMock()

        mock_cursor = AsyncMock()
        mock_cursor.fetchone = AsyncMock(return_value=None)
        mock_writer = AsyncMock()
        mock_writer.execute.return_value = mock_cursor
        lc._writer = mock_writer
        queue = _wire_profile_queue(lc, mock_writer)

        fake_uuid = "00000000-0000-0000-0000-000000000001"
        with (
            patch("ibreeze.application.lifecycle._now_iso", return_value="2026-07-30T12:00:00Z"),
            patch("ibreeze.application.lifecycle.uuid4", return_value=fake_uuid),
        ):
            await lc._ensure_profile_identity()

        call_args = lc._write_queue.submit.await_args
        assert call_args is not None
        execute_fn = call_args.kwargs["execute"]

        await execute_fn(mock_writer)

        expected_sql = (
            "INSERT INTO local_profile "
            "(id, schema_epoch, created_by_app_version, backend_origin, "
            "app_user_id, masked_identifier, device_id, created_at, "
            "last_opened_at) "
            "VALUES (?, 1, ?, ?, ?, ?, ?, ?, ?)"
        )
        queue.submit.assert_awaited_once_with(
            command_name="ensure_profile_identity",
            trace_id=ANY,
            deadline_at=ANY,
            execute=ANY,
        )
        mock_writer.execute.assert_any_call(
            expected_sql,
            (fake_uuid, "1.2.3", "https://example.com", "user-1", "mask-1", "dev-1", "2026-07-30T12:00:00Z", "2026-07-30T12:00:00Z"),
        )

    @pytest.mark.asyncio
    async def test_offline_mode_still_raises_when_empty(self):
        lc = ApplicationLifecycle(Path("/tmp/test.db"), profile_mode="offline")
        lc._prepared = MagicMock()

        mock_cursor = AsyncMock()
        mock_cursor.fetchone = AsyncMock(return_value=None)
        mock_writer = AsyncMock()
        mock_writer.execute.return_value = mock_cursor
        lc._writer = mock_writer
        _wire_profile_queue(lc, mock_writer)

        with pytest.raises(RuntimeError, match="PROFILE_NOT_FOUND: no local_profile record"):
            await lc._ensure_profile_identity()

    @pytest.mark.asyncio
    async def test_raises_on_schema_epoch_unsupported(self):
        lc = ApplicationLifecycle(Path("/tmp/test.db"))
        lc._prepared = MagicMock()

        mock_cursor = AsyncMock()
        mock_cursor.fetchone = AsyncMock(
            return_value={
                "id": "uuid",
                "schema_epoch": 2,
                "backend_origin": "",
                "app_user_id": "",
                "masked_identifier": "",
                "device_id": "",
                "created_at": "",
                "last_opened_at": "",
            }
        )
        mock_writer = AsyncMock()
        mock_writer.execute.return_value = mock_cursor
        lc._writer = mock_writer
        _wire_profile_queue(lc, mock_writer)

        with pytest.raises(RuntimeError, match="PROFILE_SCHEMA_UNSUPPORTED: schema_epoch=2"):
            await lc._ensure_profile_identity()


class TestApplicationLifecycleStop:
    @pytest.mark.asyncio
    async def test_stop_full(self):
        lc = ApplicationLifecycle(Path("/tmp/test.db"))
        lc._write_queue = AsyncMock()
        lc._workers = AsyncMock()
        lc._writer = AsyncMock()
        lc._read_pool = AsyncMock()
        lc._prepared = AsyncMock()

        await lc.stop()

        lc._write_queue.stop.assert_awaited_once_with(timeout=10.0)
        lc._workers.stop.assert_awaited_once()
        lc._writer.execute.assert_awaited_once_with("PRAGMA wal_checkpoint(TRUNCATE)")
        lc._read_pool.close.assert_awaited_once()
        assert lc._writer.close.await_count == 1
        lc._prepared.release_lock.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_stop_wal_checkpoint_exception_does_not_propagate(self):
        lc = ApplicationLifecycle(Path("/tmp/test.db"))
        lc._write_queue = AsyncMock()
        lc._workers = AsyncMock()
        mock_writer = AsyncMock()
        mock_writer.execute.side_effect = RuntimeError("wal oops")
        lc._writer = mock_writer
        lc._read_pool = AsyncMock()
        lc._prepared = AsyncMock()

        await lc.stop()

        mock_writer.close.assert_awaited_once()
        lc._prepared.release_lock.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_stop_partial_none_components(self):
        lc = ApplicationLifecycle(Path("/tmp/test.db"))
        lc._write_queue = None
        lc._workers = None
        lc._writer = None
        lc._read_pool = None
        lc._prepared = None

        await lc.stop()


class TestApplicationLifecycleHealth:
    @pytest.mark.asyncio
    async def test_health_returns_snapshot(self):
        lc = ApplicationLifecycle(Path("/tmp/test.db"))
        lc._writer = MagicMock()
        lc._write_queue = MagicMock()
        lc._write_queue.depth = 2
        lc._workers = MagicMock()
        worker_health = [
            WorkerHealth(name="w1", state="healthy", heartbeat_at="2026-01-01T00:00:00Z"),
            WorkerHealth(name="w2", state="healthy", heartbeat_at="2026-01-01T00:00:00Z"),
        ]
        lc._workers.health.return_value = worker_health
        lc._profile_path = Path("/tmp/test.db")

        with (
            patch("ibreeze.observability.health._get_migration_version_async", return_value=8),
            patch("ibreeze.observability.health._get_disk_free", return_value=500000000),
        ):
            snapshot = await lc.health()

        assert isinstance(snapshot, HealthSnapshot)
        assert snapshot.profile.migration_version == 8
        assert snapshot.queues.write_depth == 2
        assert len(snapshot.workers) == 2
        assert snapshot.status == "healthy"

    @pytest.mark.asyncio
    async def test_health_handle_system_health(self):
        lc = ApplicationLifecycle(Path("/tmp/test.db"))
        lc._writer = MagicMock()
        lc._write_queue = MagicMock()
        lc._write_queue.depth = 5
        lc._workers = MagicMock()
        lc._workers.health.return_value = [
            WorkerHealth(name="analysis", state="healthy", heartbeat_at=""),
        ]
        lc._profile_path = Path("/tmp/test.db")

        snapshot = HealthSnapshot(
            status="healthy",
            observed_at="2026-07-30T00:00:00Z",
            profile=ProfileHealth(migration_version=3),
            queues=MagicMock(write_depth=5),
            workers=(WorkerHealth(name="analysis", state="healthy", heartbeat_at=""),),
            disk_free_bytes=999999999,
        )
        with patch.object(lc, "health", return_value=snapshot):
            result = await lc._handle_system_health({})

        assert result["status"] == "healthy"
        assert result["migration_version"] == 3
        assert result["write_depth"] == 5
        assert result["workers"] == [("analysis", "healthy")]

    @pytest.mark.asyncio
    async def test_handle_system_shutdown_schedules_callback(self):
        lc = ApplicationLifecycle(Path("/tmp/test.db"))

        with patch.object(lc, "_shutdown_called"):
            result = await lc._handle_system_shutdown({})
            assert result == {"status": "shutting_down"}
            await lc.health()  # yield to event loop so call_soon fires
            await lc.health()
            await lc.health()

    def test_shutdown_called_logs(self):
        lc = ApplicationLifecycle(Path("/tmp/test.db"))
        lc._shutdown_called()


class TestApplicationLifecycleInitReviewCompletionHandlers:
    @pytest.mark.asyncio
    async def test_registers_all_review_and_completion_handlers(self):
        lc = ApplicationLifecycle(Path("/tmp/test.db"))
        lc._unit_of_work = MagicMock()

        with (
            patch("ibreeze.application.lifecycle.ReviewRepository"),
            patch("ibreeze.application.lifecycle.ResolveIssueHandler"),
            patch("ibreeze.application.lifecycle.SubmitReviewGuards"),
            patch("ibreeze.application.lifecycle.SubmitReviewHandler"),
            patch("ibreeze.application.lifecycle.AcceptEmployeeTaskHandler"),
            patch("ibreeze.application.lifecycle.EmployeeGate"),
            patch("ibreeze.application.lifecycle.CompleteDepartmentTaskHandler"),
            patch("ibreeze.application.lifecycle.DepartmentGate"),
            patch("ibreeze.application.lifecycle.CompleteCompanyTaskHandler"),
            patch("ibreeze.application.lifecycle.CompanyGate"),
        ):
            await lc._init_review_completion_handlers()

        expected_review = ["review.resolveIssue", "review.submit", "review.listIssues", "review.rerun"]
        for method in expected_review:
            assert lc._dispatcher.has_method(method), f"{method} not registered"
        assert lc._dispatcher.method_count == 4
        for command_name in ("StartReview", "StartIssueFix", "VerifyIssue", "CloseIssue", "RejectIssue"):
            assert command_name in lc.command_bus._handlers

    @pytest.mark.asyncio
    async def test_registers_handlers_without_external_patches(self):
        lc = ApplicationLifecycle(Path("/tmp/test.db"))
        lc._unit_of_work = MagicMock()

        await lc._init_review_completion_handlers()

        assert lc._dispatcher.has_method("review.submit")
        assert lc._dispatcher.has_method("review.resolveIssue")
        assert lc._dispatcher.has_method("review.listIssues")
        assert lc._dispatcher.has_method("review.rerun")
        assert lc._dispatcher.method_count == 4


class TestApplicationLifecycleDispatcher:
    @pytest.mark.asyncio
    async def test_dispatch_routes_to_registered_handler(self):
        lc = ApplicationLifecycle(Path("/tmp/test.db"))
        handler = AsyncMock(return_value={"handled": True})
        lc._dispatcher.register("test.echo", handler)

        result = await lc._dispatcher.dispatch("test.echo", {"msg": "hello"}, None)
        assert result == {"handled": True}
        handler.assert_called_once_with({"msg": "hello"}, None)

    @pytest.mark.asyncio
    async def test_dispatch_raises_on_unknown_method(self):
        lc = ApplicationLifecycle(Path("/tmp/test.db"))
        from ibreeze.rpc.multiplexer import MethodNotAllowedError

        with pytest.raises(MethodNotAllowedError, match="METHOD_NOT_ALLOWED"):
            await lc._dispatcher.dispatch("nonexistent", {}, None)

    def test_method_count_tracks_registrations(self):
        lc = ApplicationLifecycle(Path("/tmp/test.db"))
        assert lc._dispatcher.method_count == 0
        lc._dispatcher.register("a", AsyncMock())
        assert lc._dispatcher.method_count == 1
        lc._dispatcher.register("b", AsyncMock())
        assert lc._dispatcher.method_count == 2


class _PhaseTrackingLifecycle(ApplicationLifecycle):
    def __init__(self, *args, **kwargs):
        self.phase_history: list[LifecyclePhase] = []
        super().__init__(*args, **kwargs)

    def __setattr__(self, name, value):
        if name == "_phase" and hasattr(self, "phase_history"):
            self.phase_history.append(value)
        super().__setattr__(name, value)


class TestApplicationLifecyclePhaseTransitions:
    @pytest.mark.asyncio
    async def test_phase_transitions_through_all_states(self, tmp_path):
        profile_path = tmp_path / "test.db"

        with (
            patch("ibreeze.application.lifecycle.prepare"),
            patch("ibreeze.application.lifecycle.open_writer"),
            patch("ibreeze.application.lifecycle.ReadPool") as mock_rp_cls,
            patch("ibreeze.application.lifecycle.WriteQueue"),
            patch("ibreeze.application.lifecycle.UnitOfWork"),
            patch("ibreeze.application.lifecycle.WorkerSupervisor") as m_ws_cls,
            patch("ibreeze.application.lifecycle.register_public_handlers", return_value=None),
        ):
            mock_rp_cls.open = AsyncMock(return_value=MagicMock())
            m_ws_cls.return_value = AsyncMock()

            lc = _PhaseTrackingLifecycle(profile_path, socket_path="/tmp/sock")
            lc._ensure_profile_identity = AsyncMock()
            lc._init_review_completion_handlers = AsyncMock()
            await lc.start()

            expected_phases = [
                LifecyclePhase.INIT,
                LifecyclePhase.LOCK_ACQUIRED,
                LifecyclePhase.UDS_HANDSHAKE_ONLY,
                LifecyclePhase.BOOTSTRAP_DB,
                LifecyclePhase.MIGRATION,
                LifecyclePhase.WRITER_OPENED,
                LifecyclePhase.READ_POOL_OPENED,
                LifecyclePhase.WRITE_QUEUE_STARTED,
                LifecyclePhase.IDENTITY_VERIFIED,
                LifecyclePhase.WORKER_SUPERVISOR_STARTED,
                LifecyclePhase.RPC_DISPATCHER_ENABLED,
                LifecyclePhase.HANDSHAKE_READY,
            ]
            assert lc.phase_history == expected_phases, f"Phase mismatch: {lc.phase_history}"
