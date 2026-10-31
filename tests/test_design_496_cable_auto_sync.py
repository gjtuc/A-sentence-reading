# -*- coding: utf-8 -*-
"""design/496 — the helper tells the phone a web page is watching and the page when the phone joins."""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import pytest

pytest.importorskip("websockets")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tests"))

import helper_store as hs  # noqa: E402
import usb_sync_bridge as bridge_mod  # noqa: E402
from test_design_495_helper_store import ORIGIN, _free_port, _run  # noqa: E402


async def _serve(tmp_path: Path):
    web_port, phone_port, probe_port = _free_port(), _free_port(), _free_port()
    ready, stop = asyncio.Event(), asyncio.Event()
    task = asyncio.create_task(
        bridge_mod.serve(
            web_port=web_port,
            phone_port=phone_port,
            probe_port=probe_port,
            use_adb=False,
            bridge=bridge_mod.Bridge(log=lambda *_: None),
            store=hs.PaperStore(tmp_path),
            ready=ready,
            stop=stop,
        )
    )
    await asyncio.wait_for(ready.wait(), 5)
    return web_port, phone_port, probe_port, stop, task


async def _probe(port: int) -> dict:
    reader, writer = await asyncio.open_connection("127.0.0.1", port)
    try:
        return json.loads(await asyncio.wait_for(reader.readline(), 5))
    finally:
        writer.close()


def test_helper_version_is_two() -> None:
    assert int(hs.HELPER_VERSION) >= 2


def test_watch_says_watching_and_tells_when_the_phone_joins(tmp_path: Path) -> None:
    from websockets.asyncio.client import connect

    async def body() -> None:
        web_port, phone_port, probe_port, stop, task = await _serve(tmp_path)
        try:
            assert (await _probe(probe_port))["watch"] is False
            async with connect(f"ws://127.0.0.1:{web_port}/watch", origin=ORIGIN) as ws:
                hello = json.loads(await asyncio.wait_for(ws.recv(), 5))
                assert hello["t"] == "hello" and hello["watch"] is True and hello["phone"] is False
                assert hello["helper"] == hs.HELPER_VERSION
                probed = await _probe(probe_port)
                assert probed["watch"] is True and probed["phone"] is False

                reader, writer = await asyncio.open_connection("127.0.0.1", phone_port)
                try:
                    told = json.loads(await asyncio.wait_for(ws.recv(), 5))
                    assert told == {"t": "phone"}
                    assert (await _probe(probe_port))["phone"] is True
                finally:
                    writer.close()
            for _ in range(50):
                if (await _probe(probe_port))["watch"] is False:
                    break
                await asyncio.sleep(0.05)
            assert (await _probe(probe_port))["watch"] is False
        finally:
            stop.set()
            await asyncio.wait_for(task, 5)

    _run(body())


def test_watch_refuses_other_sites(tmp_path: Path) -> None:
    from websockets.asyncio.client import connect
    from websockets.exceptions import InvalidStatus

    async def body() -> None:
        web_port, _phone, _probe_port, stop, task = await _serve(tmp_path)
        try:
            for origin in ("https://someone-else.a.run.app", None):
                with pytest.raises(InvalidStatus):
                    async with connect(f"ws://127.0.0.1:{web_port}/watch", origin=origin):
                        pass
        finally:
            stop.set()
            await asyncio.wait_for(task, 5)

    _run(body())
