"""Object storage service for skill packages."""
import hashlib
import shutil
from pathlib import Path


class ObjectStorage:
    """Local filesystem object storage for skill packages."""

    def __init__(self, base_path: Path | None = None):
        self.base_path = base_path or Path("storage/skills")
        self.base_path.mkdir(parents=True, exist_ok=True)

    def store(self, skill_id: str, version: str, zip_path: Path) -> Path:
        """Store a skill ZIP file."""
        skill_dir = self.base_path / skill_id
        skill_dir.mkdir(parents=True, exist_ok=True)
        dest = skill_dir / f"{version}.zip"
        shutil.copy2(zip_path, dest)
        return dest

    def retrieve(self, skill_id: str, version: str) -> Path | None:
        """Retrieve a skill ZIP file."""
        path = self.base_path / skill_id / f"{version}.zip"
        return path if path.exists() else None

    def delete(self, skill_id: str, version: str) -> bool:
        """Delete a skill ZIP file."""
        path = self.base_path / skill_id / f"{version}.zip"
        if path.exists():
            path.unlink()
            return True
        return False

    def list_versions(self, skill_id: str) -> list[str]:
        """List all versions for a skill."""
        skill_dir = self.base_path / skill_id
        if not skill_dir.exists():
            return []
        return sorted(p.stem for p in skill_dir.glob("*.zip"))

    def get_download_url(self, skill_id: str, version: str) -> str | None:
        """Return local file path as download URL placeholder."""
        path = self.base_path / skill_id / f"{version}.zip"
        return str(path) if path.exists() else None

    def get_object_sha256(self, skill_id: str, version: str) -> str | None:
        """Compute SHA-256 of a stored skill package."""
        path = self.base_path / skill_id / f"{version}.zip"
        if not path.exists():
            return None
        sha256 = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha256.update(chunk)
        return sha256.hexdigest()
