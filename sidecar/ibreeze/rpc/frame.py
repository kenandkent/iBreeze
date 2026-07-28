import asyncio
import json
import struct
from typing import Any

MAX_FRAME_BYTES = 16 * 1024 * 1024


class FrameError(Exception):
    pass


class InvalidLengthError(FrameError):
    pass


class TooLargeError(FrameError):
    pass


class NotAnObjectError(FrameError):
    pass


class ConnectionClosedError(FrameError):
    pass


def encode_frame(obj: dict[str, Any]) -> bytes:
    payload = json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    length = len(payload)
    if length == 0:
        raise InvalidLengthError("zero-length frame")
    if length > MAX_FRAME_BYTES:
        raise TooLargeError(f"frame too large: {length} > {MAX_FRAME_BYTES}")
    return struct.pack(">I", length) + payload


async def read_frame(reader: asyncio.StreamReader) -> dict[str, Any]:
    try:
        header = await reader.readexactly(4)
    except asyncio.IncompleteReadError:
        raise ConnectionClosedError("connection closed while reading header")
    length = struct.unpack(">I", header)[0]
    if length == 0:
        raise InvalidLengthError("zero-length frame")
    if length > MAX_FRAME_BYTES:
        raise TooLargeError(f"frame too large: {length} > {MAX_FRAME_BYTES}")
    try:
        body = await reader.readexactly(length)
    except asyncio.IncompleteReadError:
        raise ConnectionClosedError("connection closed while reading body")
    try:
        text = body.decode("utf-8")
    except UnicodeDecodeError as e:
        raise FrameError(f"invalid utf-8: {e}")
    obj = json.loads(text)
    if not isinstance(obj, dict):
        raise NotAnObjectError(f"top-level value is {type(obj).__name__}, expected object")
    return obj


async def write_frame(writer: asyncio.StreamWriter, obj: dict[str, Any]) -> None:
    data = encode_frame(obj)
    writer.write(data)
    await writer.drain()
