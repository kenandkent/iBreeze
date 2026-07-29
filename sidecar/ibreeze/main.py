"""iBreeze Sidecar process entry point."""

from __future__ import annotations

import asyncio
import base64
import sys
from pathlib import Path

import click

from ibreeze.application.app import SidecarApplication
from ibreeze.logging_config import setup_logging
from ibreeze.rpc.production_server import PROTOCOL_VERSION


async def _run(
    *,
    socket_path: Path,
    profile_root: Path,
    app_version: str,
    startup_token: bytes,
    backend_origin: str,
    app_user_id: str,
    masked_identifier: str,
    device_id: str,
    profile_mode: str,
) -> None:
    app = SidecarApplication(
        socket_path=socket_path,
        profile_root=profile_root,
        app_version=app_version,
        startup_token=startup_token,
        backend_origin=backend_origin,
        app_user_id=app_user_id,
        masked_identifier=masked_identifier,
        device_id=device_id,
        profile_mode=profile_mode,
    )
    try:
        await app.start()
        await app.rpc_server.serve_forever()
    finally:
        await app.stop()


@click.command()
@click.option(
    "--socket",
    "socket_path",
    required=True,
    type=click.Path(path_type=Path),
)
@click.option(
    "--profile",
    "profile_root",
    required=True,
    type=click.Path(path_type=Path),
)
@click.option("--app-version", required=True)
@click.option("--protocol-version", required=True, type=int)
@click.option("--backend-origin", required=True)
@click.option("--app-user-id", required=True, type=click.UUID)
@click.option("--masked-identifier", required=True)
@click.option("--device-id", required=True, type=click.UUID)
@click.option(
    "--profile-mode",
    required=True,
    type=click.Choice(["online", "offline"]),
)
def main(
    socket_path: Path,
    profile_root: Path,
    app_version: str,
    protocol_version: int,
    backend_origin: str,
    app_user_id: object,
    masked_identifier: str,
    device_id: object,
    profile_mode: str,
) -> None:
    """Start the supervised Sidecar using a token read once from stdin."""
    setup_logging()
    if protocol_version != PROTOCOL_VERSION:
        raise click.ClickException("protocol version mismatch")
    encoded_token = sys.stdin.buffer.readline(256).strip()
    try:
        startup_token = base64.b64decode(encoded_token, validate=True)
    except ValueError as exc:
        raise click.ClickException("invalid startup token") from exc
    if len(startup_token) != 32:
        raise click.ClickException("invalid startup token length")
    profile_root.mkdir(mode=0o700, parents=True, exist_ok=True)
    asyncio.run(
        _run(
            socket_path=socket_path,
            profile_root=profile_root,
            app_version=app_version,
            startup_token=startup_token,
            backend_origin=backend_origin,
            app_user_id=str(app_user_id),
            masked_identifier=masked_identifier,
            device_id=str(device_id),
            profile_mode=profile_mode,
        )
    )


if __name__ == "__main__":
    main()
