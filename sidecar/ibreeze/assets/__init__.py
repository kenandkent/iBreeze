"""Bundled runtime assets for offline deployments."""

from importlib import resources

ASSETS_PACKAGE = "ibreeze.assets"


def get_asset_path(name: str) -> str:
    """Get the file path for a bundled asset by name."""
    return str(resources.files(ASSETS_PACKAGE).joinpath(name))


def list_assets() -> list[str]:
    """List all bundled asset names."""
    package = resources.files(ASSETS_PACKAGE)
    return [f.name for f in package.iterdir() if f.is_file()]
