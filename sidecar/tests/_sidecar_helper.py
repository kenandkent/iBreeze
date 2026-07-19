"""Sidecar subprocess helper for tests.

Usage:
    python -m tests._sidecar_helper <socket_path>
"""

from __future__ import annotations

import asyncio
import json
import os
import signal
import sys
from datetime import datetime, timezone
from pathlib import Path


def log_event(event: str, **kwargs: object) -> None:
    record = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "level": "info",
        "event": event,
        **kwargs,
    }
    print(json.dumps(record), flush=True)


async def run(socket_path: str) -> None:
    from acos.rpc.server import RPCServer

    server = RPCServer(socket_path=socket_path)

    shutdown_event = asyncio.Event()

    async def _handle_shutdown(_params: dict) -> dict:
        shutdown_event.set()
        return {"status": "shutting_down"}

    server.register_method("sys.shutdown", _handle_shutdown)

    await server.start()
    log_event("helper.started", socket=socket_path)

    stop = asyncio.Event()

    def _on_signal(*_args: object) -> None:
        stop.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, _on_signal)

    done, _pending = await asyncio.wait(
        [
            asyncio.create_task(stop.wait()),
            asyncio.create_task(shutdown_event.wait()),
        ],
        return_when=asyncio.FIRST_COMPLETED,
    )

    await server.stop()
    p = Path(socket_path)
    if p.exists():
        p.unlink()

    log_event("helper.stopped")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python -m tests._sidecar_helper <socket_path>", file=sys.stderr)
        sys.exit(1)
    asyncio.run(run(sys.argv[1]))
