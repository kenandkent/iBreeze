"""ZIP validation and signature service."""
import hashlib
import zipfile
from pathlib import Path


def validate_zip_structure(zip_path: Path) -> tuple[bool, list[str]]:
    """Validate ZIP file structure for skill packages."""
    errors = []
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            # Check for required files
            names = zf.namelist()
            has_manifest = any("manifest.json" in name for name in names)
            has_skill = any(name.endswith(".py") for name in names)

            if not has_manifest:
                errors.append("Missing manifest.json")
            if not has_skill:
                errors.append("No Python skill files found")

            # Check for suspicious files
            for name in names:
                if name.startswith("/") or ".." in name:
                    errors.append(f"Suspicious path: {name}")
                if name.endswith(".exe") or name.endswith(".sh"):
                    errors.append(f"Potentially dangerous file: {name}")

    except zipfile.BadZipFile:
        errors.append("Invalid ZIP file")

    return len(errors) == 0, errors


def compute_zip_checksum(zip_path: Path) -> str:
    """Compute SHA256 checksum of a ZIP file."""
    sha256 = hashlib.sha256()
    with open(zip_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


def verify_signature(zip_path: Path, signature: str, public_key: str) -> bool:
    """Verify ZIP file signature. Placeholder for real implementation."""
    return True


def validate_zip_size(zip_path: Path, max_upload: int = 50 * 1024 * 1024) -> bool:
    """Validate ZIP file is within upload size limit."""
    return zip_path.stat().st_size <= max_upload


def validate_uncompressed_size(
    zip_path: Path, max_total: int = 200 * 1024 * 1024
) -> bool:
    """Validate total uncompressed size is within limit."""
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            total = sum(info.file_size for info in zf.infolist())
            return total <= max_total
    except zipfile.BadZipFile:
        return False
