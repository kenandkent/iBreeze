from __future__ import annotations

from pathlib import Path

import pytest

from ibreeze.persistence.profile import PreparedProfileDatabase, ProfileFileLock


@pytest.mark.asyncio
class TestProfileFileLock:
    async def test_acquire_and_release(self, tmp_path: Path):
        path = tmp_path / "profile.db"
        lock = await ProfileFileLock.acquire(path)
        assert lock._lock_file is not None
        lock_path = path.parent / f"{path.name}.lock"
        assert lock_path.exists()
        await lock.release()
        assert lock._lock_file is None

    async def test_acquire_twice_fails(self, tmp_path: Path):
        path = tmp_path / "profile.db"
        lock1 = await ProfileFileLock.acquire(path)
        with pytest.raises(RuntimeError, match="cannot acquire profile lock"):
            await ProfileFileLock.acquire(path)
        await lock1.release()

    async def test_release_twice_no_error(self, tmp_path: Path):
        path = tmp_path / "profile.db"
        lock = await ProfileFileLock.acquire(path)
        await lock.release()
        await lock.release()

    async def test_release_cleans_up_lock_file(self, tmp_path: Path):
        path = tmp_path / "profile.db"
        lock = await ProfileFileLock.acquire(path)
        lock_path = path.parent / f"{path.name}.lock"
        assert lock_path.exists()
        await lock.release()
        assert not lock_path.exists()


class TestPreparedProfileDatabase:
    async def test_release_lock(self, tmp_path: Path):
        path = tmp_path / "profile.db"
        lock = await ProfileFileLock.acquire(path)
        ppd = PreparedProfileDatabase(path=path, lock=lock)
        assert ppd.path == path
        await ppd.release_lock()
        assert lock._lock_file is None
