from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from ibreeze.observability.health import (
    ProfileHealth,
    QueueHealth,
    health_snapshot,
)
from ibreeze.workers.spec import WorkerHealth


def test_profile_health_default():
    ph = ProfileHealth()
    assert ph.schema_epoch == 1
    assert ph.database_status == "unknown"


def test_queue_health_default():
    qh = QueueHealth()
    assert qh.write_depth == 0


class TestHealthSnapshot:
    def test_healthy_all_ok(self):
        writer = MagicMock()
        write_queue = MagicMock()
        write_queue.depth = 3

        worker1 = MagicMock()
        worker1.health.return_value = [
            WorkerHealth(name="w1", state="healthy", heartbeat_at="2026-01-01T00:00:00Z"),
        ]

        with patch("ibreeze.observability.health._get_migration_version", return_value=5):
            with patch("ibreeze.observability.health._get_loop_lag_ms", return_value=2):
                with patch("ibreeze.observability.health._get_disk_free", return_value=999999999):
                    result = health_snapshot(writer, write_queue, worker1, Path("/tmp"))
        assert result.status == "healthy"

    def test_unhealthy_writer_none(self):
        result = health_snapshot(None, MagicMock(), MagicMock(), Path("/tmp"))
        assert result.status == "unhealthy"

    def test_unhealthy_migration_missing(self):
        writer = MagicMock()
        write_queue = MagicMock()
        write_queue.depth = 0

        with patch("ibreeze.observability.health._get_migration_version", return_value=0):
            with patch("ibreeze.observability.health._get_loop_lag_ms", return_value=0):
                with patch("ibreeze.observability.health._get_disk_free", return_value=0):
                    result = health_snapshot(writer, write_queue, None, Path("/tmp"))
        assert result.status == "unhealthy"

    def test_degraded_any_failed(self):
        writer = MagicMock()
        write_queue = MagicMock()
        write_queue.depth = 0

        workers = MagicMock()
        workers.health.return_value = [
            WorkerHealth(name="w1", state="failed", heartbeat_at="2026-01-01T00:00:00Z"),
        ]

        with patch("ibreeze.observability.health._get_migration_version", return_value=5):
            with patch("ibreeze.observability.health._get_loop_lag_ms", return_value=0):
                with patch("ibreeze.observability.health._get_disk_free", return_value=0):
                    result = health_snapshot(writer, write_queue, workers, Path("/tmp"))
        assert result.status == "degraded"

    def test_degraded_any_starting(self):
        writer = MagicMock()
        write_queue = MagicMock()
        write_queue.depth = 0

        workers = MagicMock()
        workers.health.return_value = [
            WorkerHealth(name="w1", state="starting", heartbeat_at="2026-01-01T00:00:00Z"),
        ]

        with patch("ibreeze.observability.health._get_migration_version", return_value=5):
            with patch("ibreeze.observability.health._get_loop_lag_ms", return_value=0):
                with patch("ibreeze.observability.health._get_disk_free", return_value=0):
                    result = health_snapshot(writer, write_queue, workers, Path("/tmp"))
        assert result.status == "degraded"

    def test_no_workers(self):
        writer = MagicMock()
        write_queue = MagicMock()
        write_queue.depth = 0

        with patch("ibreeze.observability.health._get_migration_version", return_value=5):
            with patch("ibreeze.observability.health._get_loop_lag_ms", return_value=0):
                with patch("ibreeze.observability.health._get_disk_free", return_value=0):
                    result = health_snapshot(writer, write_queue, None, Path("/tmp"))
        assert result.status == "healthy"

    def test_snapshot_has_all_fields(self):
        writer = MagicMock()
        write_queue = MagicMock()
        write_queue.depth = 0

        with patch("ibreeze.observability.health._get_migration_version", return_value=5):
            with patch("ibreeze.observability.health._get_loop_lag_ms", return_value=1):
                with patch("ibreeze.observability.health._get_disk_free", return_value=500):
                    result = health_snapshot(writer, write_queue, None, Path("/tmp"))
        assert result.observed_at != ""
        assert result.event_loop_lag_ms == 1
        assert result.disk_free_bytes == 500


class TestGetDiskFree:
    def test_disk_free_returns_zero_on_error(self):
        from ibreeze.observability.health import _get_disk_free
        result = _get_disk_free(Path("/nonexistent_path_xyz"))
        assert result == 0


class TestGetMigrationVersion:
    def test_returns_zero_when_writer_none(self):
        from ibreeze.observability.health import _get_migration_version
        result = _get_migration_version(None)
        assert result == 0
