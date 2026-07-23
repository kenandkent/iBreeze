"""Build bundled runtime assets."""
import hashlib
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).parent.parent
ASSETS_DIR = ROOT / "sidecar" / "ibreeze" / "assets"
MANIFEST_PATH = ASSETS_DIR / "manifest.json"


def compute_sha256(file_path: Path) -> str:
    """Compute SHA256 hash of a file."""
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


def build_assets() -> None:
    """Build assets manifest from actual files."""
    assets = []
    for asset_file in sorted(ASSETS_DIR.iterdir()):
        if asset_file.name.startswith("."):
            continue
        if asset_file.name in ("manifest.json", "manifest.schema.json"):
            continue
        if asset_file.is_file():
            assets.append({
                "name": asset_file.name,
                "version": "0.1.0",
                "size": asset_file.stat().st_size,
                "sha256": compute_sha256(asset_file),
            })

    manifest = {
        "version": "0.1.0",
        "assets": assets,
    }

    with open(MANIFEST_PATH, "w") as f:
        json.dump(manifest, f, indent=2)

    print(f"Built manifest with {len(assets)} assets")


if __name__ == "__main__":
    build_assets()
