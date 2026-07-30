"""Tests for ibreeze.rpc.frame module."""

from __future__ import annotations

import asyncio
import json
import struct
from unittest.mock import AsyncMock, MagicMock

import pytest

from ibreeze.rpc.frame import (
    ConnectionClosedError,
    FrameError,
    InvalidLengthError,
    NotAnObjectError,
    TooLargeError,
    encode_frame,
    read_frame,
    write_frame,
)


class TestEncodeFrame:
    def test_encodes_simple_dict(self):
        data = encode_frame({"hello": "world"})
        struct.unpack(">I", data[:4])[0]
        payload = data[4:].decode("utf-8")
        assert json.loads(payload) == {"hello": "world"}

    def test_encodes_unicode(self):
        data = encode_frame({"key": "值"})
        struct.unpack(">I", data[:4])[0]
        payload = data[4:].decode("utf-8")
        assert json.loads(payload) == {"key": "值"}

    def test_raises_invalid_length_for_empty_payload(self):
        import ibreeze.rpc.frame as frame_mod
        original = frame_mod.json.dumps

        def fake_dumps(obj, **kwargs):
            return ""

        frame_mod.json.dumps = fake_dumps
        try:
            with pytest.raises(InvalidLengthError, match="zero-length frame"):
                encode_frame({})
        finally:
            frame_mod.json.dumps = original

    def test_raises_too_large_error(self):
        import ibreeze.rpc.frame as frame_mod
        original = frame_mod.json.dumps

        def fake_dumps(obj, **kwargs):
            return "x" * (frame_mod.MAX_FRAME_BYTES + 1)

        frame_mod.json.dumps = fake_dumps
        try:
            with pytest.raises(TooLargeError, match="frame too large"):
                encode_frame({"big": True})
        finally:
            frame_mod.json.dumps = original


class TestReadFrame:
    async def test_reads_valid_frame(self):
        obj = {"test": "data", "num": 42}
        data = encode_frame(obj)
        reader = asyncio.StreamReader()
        reader.feed_data(data)
        result = await read_frame(reader)
        assert result == obj

    async def test_raises_on_connection_closed_during_header(self):
        reader = asyncio.StreamReader()
        reader.feed_eof()
        with pytest.raises(ConnectionClosedError, match="connection closed while reading header"):
            await read_frame(reader)

    async def test_raises_on_zero_length_frame(self):
        reader = asyncio.StreamReader()
        reader.feed_data(struct.pack(">I", 0))
        with pytest.raises(InvalidLengthError, match="zero-length frame"):
            await read_frame(reader)

    async def test_raises_on_too_large_frame(self):
        import ibreeze.rpc.frame as frame_mod
        reader = asyncio.StreamReader()
        reader.feed_data(struct.pack(">I", frame_mod.MAX_FRAME_BYTES + 1))
        with pytest.raises(TooLargeError, match="frame too large"):
            await read_frame(reader)

    async def test_raises_on_non_object_json(self):
        reader = asyncio.StreamReader()
        data = json.dumps([1, 2, 3]).encode("utf-8")
        reader.feed_data(struct.pack(">I", len(data)) + data)
        with pytest.raises(NotAnObjectError, match="top-level value is list"):
            await read_frame(reader)

    async def test_raises_on_invalid_utf8(self):
        reader = asyncio.StreamReader()
        invalid = b"\xff\xfe"
        reader.feed_data(struct.pack(">I", len(invalid)) + invalid)
        with pytest.raises(FrameError, match="invalid utf-8"):
            await read_frame(reader)


class TestWriteFrame:
    async def test_writes_frame(self):
        obj = {"key": "value"}
        data = encode_frame(obj)

        writer = MagicMock()
        writer.write = MagicMock()
        writer.drain = AsyncMock()

        await write_frame(writer, obj)
        writer.write.assert_called_once_with(data)
        writer.drain.assert_awaited_once()

    async def test_drain_called(self):
        writer = MagicMock()
        drain_called = False

        async def mock_drain():
            nonlocal drain_called
            drain_called = True

        writer.write = MagicMock()
        writer.drain = mock_drain

        await write_frame(writer, {"a": 1})
        assert drain_called
