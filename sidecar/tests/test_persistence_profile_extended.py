from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from ibreeze.persistence.profile import PreparedProfileDatabase, ProfileFileLock


@pytest.mark.asyncio
class TestProfileFileLockErrorPaths:
    async def test_acquire_fails_on_blocking_io_error(self, tmp_path):
        path = tmp_path / "profile.db"
        with (
            patch("os.open", return_value=99),
            patch("fcntl.flock", side_effect=BlockingIOError),
            patch("os.close"),
        ):
            with pytest.raises(RuntimeError, match="cannot acquire profile lock"):
                await ProfileFileLock.acquire(path)

    async def test_acquire_fails_on_os_error(self, tmp_path):
        path = tmp_path / "profile.db"
        with (
            patch("os.open", return_value=99),
            patch("fcntl.flock", side_effect=OSError("permission denied")),
            patch("os.close"),
        ):
            with pytest.raises(RuntimeError, match="cannot acquire profile lock"):
                await ProfileFileLock.acquire(path)

    async def test_acquire_closes_fd_on_failure(self, tmp_path):
        path = tmp_path / "profile.db"
        with (
            patch("os.open", return_value=99),
            patch("fcntl.flock", side_effect=BlockingIOError),
            patch("os.close") as close_spy,
        ):
            with pytest.raises(RuntimeError, match="cannot acquire profile lock"):
                await ProfileFileLock.acquire(path)
            close_spy.assert_called_once_with(99)

    async def test_release_close_fd_error_swallowed(self, tmp_path):
        path = tmp_path / "profile.db"
        lock = await ProfileFileLock.acquire(path)
        with patch("os.close", side_effect=OSError("bad fd")):
            await lock.release()
        assert lock._lock_file is None

    async def test_release_unlink_error_swallowed(self, tmp_path):
        path = tmp_path / "profile.db"
        lock = await ProfileFileLock.acquire(path)
        with patch.object(Path, "unlink", side_effect=OSError("permission denied")):
            await lock.release()
        assert lock._lock_file is None

    async def test_release_when_no_lock_file(self):
        lock = ProfileFileLock.__new__(ProfileFileLock)
        lock._lock_path = Path("/nonexistent/nope.lock")
        lock._lock_file = None
        await lock.release()

    async def test_acquire_import_error_swallowed(self, tmp_path):
        path = tmp_path / "profile.db"
        with (
            patch("builtins.__import__", side_effect=ImportError("no fcntl")),
        ):
            with pytest.raises(RuntimeError, match="cannot acquire profile lock"):
                await ProfileFileLock.acquire(path)

    async def test_acquire_creates_lock_file(self, tmp_path):
        path = tmp_path / "profile.db"
        lock_path = path.parent / f"{path.name}.lock"
        lock = await ProfileFileLock.acquire(path)
        try:
            assert lock_path.exists()
        finally:
            await lock.release()

    async def test_release_removes_lock_file(self, tmp_path):
        path = tmp_path / "profile.db"
        lock_path = path.parent / f"{path.name}.lock"
        lock = await ProfileFileLock.acquire(path)
        await lock.release()
        assert not lock_path.exists()


@pytest.mark.asyncio
class TestPreparedProfileDatabaseExtended:
    async def test_release_lock_delegates_to_lock(self, tmp_path):
        path = tmp_path / "profile.db"
        lock_mock = AsyncMock(spec=ProfileFileLock)
        ppd = PreparedProfileDatabase(path=path, lock=lock_mock)
        await ppd.release_lock()
        lock_mock.release.assert_awaited_once()

    async def test_release_lock_with_real_lock(self, tmp_path):
        path = tmp_path / "profile.db"
        lock = await ProfileFileLock.acquire(path)
        ppd = PreparedProfileDatabase(path=path, lock=lock)
        await ppd.release_lock()
        assert lock._lock_file is None
        lock_path = path.parent / f"{path.name}.lock"
        assert not lock_path.exists()

    async def test_path_property(self, tmp_path):
        path = tmp_path / "profile.db"
        lock_mock = AsyncMock(spec=ProfileFileLock)
        ppd = PreparedProfileDatabase(path=path, lock=lock_mock)
        assert ppd.path == path
