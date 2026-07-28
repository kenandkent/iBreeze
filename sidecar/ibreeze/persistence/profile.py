from __future__ import annotations

import os
from pathlib import Path


class ProfileFileLock:
    def __init__(self, lock_path: Path) -> None:
        self._lock_path = lock_path
        self._lock_file: int | None = None

    @classmethod
    async def acquire(cls, path: Path) -> ProfileFileLock:
        lock_path = path.parent / f"{path.name}.lock"
        lock_file = os.open(str(lock_path), os.O_CREAT | os.O_RDWR | os.O_CLOEXEC, 0o600)
        try:
            import fcntl

            fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (ImportError, BlockingIOError, OSError):
            os.close(lock_file)
            raise RuntimeError(f"cannot acquire profile lock: {lock_path}")
        lock = cls.__new__(cls)
        lock._lock_path = lock_path
        lock._lock_file = lock_file
        return lock

    async def release(self) -> None:
        if self._lock_file is not None:
            try:
                os.close(self._lock_file)
            except OSError:
                pass
            self._lock_file = None
            try:
                self._lock_path.unlink(missing_ok=True)
            except OSError:
                pass


class PreparedProfileDatabase:
    def __init__(self, *, path: Path, lock: ProfileFileLock) -> None:
        self.path = path
        self._lock = lock

    async def release_lock(self) -> None:
        await self._lock.release()
