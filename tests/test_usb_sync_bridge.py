# -*- coding: utf-8 -*-
"""design/451 — the PC bridge passes near-sync frames between web and phone."""
from __future__ import annotations

import asyncio
import importlib.util
import json
import socket
import struct
from pathlib import Path

import pytest

pytest.importorskip("websockets")

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("usb_sync_bridge", ROOT / "scripts" / "usb_sync_bridge.py")
bridge_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bridge_mod)

ORIGIN = "https://asr-sentence-reading-984608876300.asia-northeast3.run.app"


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


async def _phone_read(reader: asyncio.StreamReader) -> tuple[int, bytes]:
    return await asyncio.wait_for(bridge_mod.read_frame(reader), 5)


async def _phone_control(reader: asyncio.StreamReader) -> dict:
    kind, payload = await _phone_read(reader)
    assert kind == bridge_mod.KIND_CONTROL
    return json.loads(payload)


def _run(coro):
    return asyncio.run(asyncio.wait_for(coro, 30))


def test_adb_devices_and_origin_rules() -> None:
    text = "List of devices attached\nR3CX123\tdevice\nemu-5554\tunauthorized\n\n"
    assert bridge_mod.parse_adb_devices(text) == ["R3CX123"]
    assert bridge_mod.parse_adb_devices("List of devices attached\n\n") == []
    assert bridge_mod.origin_allowed(None)
    assert bridge_mod.origin_allowed(ORIGIN)
    assert bridge_mod.origin_allowed("http://localhost:5000")
    assert not bridge_mod.origin_allowed("https://evil.example.com")
    assert not bridge_mod.origin_allowed("http://asr.run.app")
    assert bridge_mod.encode_frame(1, b"ab") == struct.pack(">IB", 3, 1) + b"ab"


def test_web_and_phone_pair_and_pass_bytes_both_ways() -> None:
    from websockets.asyncio.client import connect

    async def body() -> None:
        web_port, phone_port = _free_port(), _free_port()
        bridge = bridge_mod.Bridge(log=lambda *_: None)
        bridge.cable = True
        ready, stop = asyncio.Event(), asyncio.Event()
        task = asyncio.create_task(
            bridge_mod.serve(
                web_port=web_port,
                phone_port=phone_port,
                use_adb=False,
                bridge=bridge,
                ready=ready,
                stop=stop,
            )
        )
        await asyncio.wait_for(ready.wait(), 5)
        try:
            async with connect(f"ws://127.0.0.1:{web_port}", origin=ORIGIN) as ws:
                hello = json.loads(await asyncio.wait_for(ws.recv(), 5))
                assert hello == {"t": "hello", "cable": True, "web": True, "phone": False}
                reader, writer = await asyncio.open_connection("127.0.0.1", phone_port)
                phone_hello = await _phone_control(reader)
                assert phone_hello["web"] is True and phone_hello["phone"] is True
                assert await _phone_control(reader) == {"t": "paired"}
                assert json.loads(await asyncio.wait_for(ws.recv(), 5)) == {"t": "paired"}

                big = bytes(range(256)) * 300
                await ws.send(big)
                kind, payload = await _phone_read(reader)
                assert kind == bridge_mod.KIND_DATA and payload == big

                writer.write(bridge_mod.encode_frame(bridge_mod.KIND_DATA, b"\x01hi"))
                await writer.drain()
                assert await asyncio.wait_for(ws.recv(), 5) == b"\x01hi"

                writer.close()
                await writer.wait_closed()
                with pytest.raises(Exception):
                    await asyncio.wait_for(ws.recv(), 5)
            assert bridge.web is None and bridge.phone is None
        finally:
            stop.set()
            await task

    _run(body())


def test_a_foreign_page_cannot_open_the_bridge() -> None:
    from websockets.asyncio.client import connect

    async def body() -> None:
        web_port, phone_port = _free_port(), _free_port()
        ready, stop = asyncio.Event(), asyncio.Event()
        task = asyncio.create_task(
            bridge_mod.serve(
                web_port=web_port,
                phone_port=phone_port,
                use_adb=False,
                bridge=bridge_mod.Bridge(log=lambda *_: None),
                ready=ready,
                stop=stop,
            )
        )
        await asyncio.wait_for(ready.wait(), 5)
        try:
            with pytest.raises(Exception):
                async with connect(f"ws://127.0.0.1:{web_port}", origin="https://evil.example.com"):
                    pass
        finally:
            stop.set()
            await task

    _run(body())


def test_a_second_web_page_replaces_the_first() -> None:
    from websockets.asyncio.client import connect

    async def body() -> None:
        web_port, phone_port = _free_port(), _free_port()
        bridge = bridge_mod.Bridge(log=lambda *_: None)
        ready, stop = asyncio.Event(), asyncio.Event()
        task = asyncio.create_task(
            bridge_mod.serve(
                web_port=web_port,
                phone_port=phone_port,
                use_adb=False,
                bridge=bridge,
                ready=ready,
                stop=stop,
            )
        )
        await asyncio.wait_for(ready.wait(), 5)
        try:
            async with connect(f"ws://127.0.0.1:{web_port}", origin=ORIGIN) as first:
                await asyncio.wait_for(first.recv(), 5)
                async with connect(f"ws://127.0.0.1:{web_port}", origin=ORIGIN) as second:
                    hello = json.loads(await asyncio.wait_for(second.recv(), 5))
                    assert hello["cable"] is False
                    with pytest.raises(Exception):
                        await asyncio.wait_for(first.recv(), 5)
        finally:
            stop.set()
            await task

    _run(body())
