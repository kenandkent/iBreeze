"""Canonical path checks for Agent tools."""

from __future__ import annotations

from pathlib import Path


class WorkspaceBoundary:
    """Authorize relative workspace reads/writes and explicit external reads."""

    def __init__(
        self,
        workspace_root: str | Path,
        *,
        external_read_roots: tuple[str | Path, ...] = (),
    ) -> None:
        root = Path(workspace_root).resolve(strict=True)
        if not root.is_dir():
            raise ValueError("WORKSPACE_ACCESS_DENIED")
        self.root = root
        self._external_read_roots = tuple(
            Path(path).resolve(strict=True)
            for path in external_read_roots
        )

    def resolve_workspace_path(
        self,
        relative_path: str,
        *,
        for_write: bool,
    ) -> Path:
        candidate = Path(relative_path)
        if candidate.is_absolute() or ".." in candidate.parts:
            raise ValueError("WORKSPACE_ACCESS_DENIED")
        unresolved = self.root / candidate
        if for_write:
            parent = unresolved.parent.resolve(strict=True)
            self._require_within(parent, self.root)
            if unresolved.exists() or unresolved.is_symlink():
                resolved = unresolved.resolve(strict=True)
                self._require_within(resolved, self.root)
            return unresolved
        resolved = unresolved.resolve(strict=True)
        self._require_within(resolved, self.root)
        return resolved

    def resolve_external_read(self, path: str | Path) -> Path:
        resolved = Path(path).resolve(strict=True)
        if not any(
            self._is_within(resolved, root)
            for root in self._external_read_roots
        ):
            raise ValueError("WORKSPACE_ACCESS_DENIED")
        return resolved

    def authorize_external_write(self, _: str | Path) -> None:
        """External mutation is never executed by Sidecar tools."""
        raise ValueError("HUMAN_APPROVAL_REQUIRED")

    @staticmethod
    def _is_within(candidate: Path, root: Path) -> bool:
        try:
            candidate.relative_to(root)
        except ValueError:
            return False
        return True

    @classmethod
    def _require_within(cls, candidate: Path, root: Path) -> None:
        if not cls._is_within(candidate, root):
            raise ValueError("WORKSPACE_ACCESS_DENIED")
