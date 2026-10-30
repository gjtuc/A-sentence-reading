# -*- coding: utf-8 -*-
"""design/495 — the helper keeps a copy of the web's papers and answers the phone's probe."""
from __future__ import annotations

import asyncio
import json
import socket
import sys
import time
from pathlib import Path

import pytest

pytest.importorskip("websockets")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import helper_app  # noqa: E402
import helper_store as hs  # noqa: E402
import usb_sync_bridge as bridge_mod  # noqa: E402

ORIGIN = "https://asr-sentence-reading-984608876300.asia-northeast3.run.app"
ACCT = "acct000001"


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _run(coro):
    return asyncio.run(asyncio.wait_for(coro, 30))


def test_names_and_origins() -> None:
    assert hs.safe_rel("session.json") == "session.json"
    assert hs.safe_rel("figures\\f1.png") == "figures/f1.png"
    for bad in ("", "/abs", "../x", "a/../b", "a//b", "c:x", "a/b.", "x" * 121):
        assert hs.safe_rel(bad) is None, bad
    assert hs.store_origin_allowed(ORIGIN)
    assert hs.store_origin_allowed("http://localhost:5000")
    assert not hs.store_origin_allowed("https://someone-else.a.run.app")
    assert not hs.store_origin_allowed(None)


def test_store_round_trip_and_deletes(tmp_path: Path) -> None:
    st = hs.PaperStore(tmp_path)
    st.put_file(ACCT, "paper01", "files", "session.json", b'{"a":1}')
    st.put_file(ACCT, "paper01", "files", "fig/1.png", b"\x89PNG")
    st.put_file(ACCT, "paper01", "extra", "shadowing/voice/a.m4a", b"v")
    saved = st.put_done(
        ACCT,
        "paper01",
        {"title": "T", "hash": "h", "added": 5, "names": ["session.json", "fig/1.png"], "extra": ["shadowing/voice/a.m4a"]},
    )
    listed = st.list(ACCT)
    assert listed["papers"]["paper01"]["names"] == ["session.json", "fig/1.png"]
    assert st.get_file(ACCT, "paper01", "files", "fig/1.png") == b"\x89PNG"
    assert st.get_file(ACCT, "paper01", "extra", "shadowing/voice/a.m4a") == b"v"

    # A delete older than the copy keeps it; a newer one drops it and is remembered.
    assert st.forget(ACCT, {"paper01": saved["saved_at"] - 1}) == []
    assert st.forget(ACCT, {"paper01": saved["saved_at"] + 1}) == ["paper01"]
    assert st.list(ACCT) == {"papers": {}, "gone": {"paper01": saved["saved_at"] + 1}}

    # Saving it again (a browser got it later) clears the delete record.
    st.put_file(ACCT, "paper01", "files", "session.json", b"{}")
    st.put_done(ACCT, "paper01", {"names": ["session.json"]})
    assert st.gone(ACCT) == {}

    with pytest.raises(hs.StoreError):
        st.put_done(ACCT, "paper02", {"names": ["missing.json"]})
    with pytest.raises(hs.StoreError):
        st.list("bad")
    st.put_progress(ACCT, {"paper01": {"i": 3}})
    assert st.progress(ACCT) == {"paper01": {"i": 3}}


async def _serve(tmp_path: Path, **kw):
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
            **kw,
        )
    )
    await asyncio.wait_for(ready.wait(), 5)
    return web_port, probe_port, stop, task


def test_web_page_stores_and_takes_back_over_the_socket(tmp_path: Path) -> None:
    from websockets.asyncio.client import connect

    async def body() -> None:
        web_port, _probe, stop, task = await _serve(tmp_path)
        try:
            async with connect(f"ws://127.0.0.1:{web_port}/store", origin=ORIGIN, max_size=None) as ws:
                hello = json.loads(await asyncio.wait_for(ws.recv(), 5))
                assert hello["t"] == "hello" and hello["store"] is True and hello["helper"] == hs.HELPER_VERSION

                async def ask(req: dict) -> dict:
                    await ws.send(json.dumps(req))
                    return json.loads(await asyncio.wait_for(ws.recv(), 5))

                big = bytes(range(256)) * 40000
                await ws.send(json.dumps({"t": "put_file", "q": 1, "acct": ACCT, "id": "p1", "name": "s.json"}))
                await ws.send(big)
                assert json.loads(await asyncio.wait_for(ws.recv(), 5)) == {"q": 1, "ok": True}
                done = await ask({"t": "put_done", "q": 2, "acct": ACCT, "id": "p1", "meta": {"names": ["s.json"]}})
                assert done["ok"] is True
                listed = await ask({"t": "list", "q": 3, "acct": ACCT})
                assert list(listed["papers"]) == ["p1"]
                head = await ask({"t": "get_file", "q": 4, "acct": ACCT, "id": "p1", "name": "s.json"})
                assert head == {"q": 4, "ok": True, "size": len(big)}
                assert await asyncio.wait_for(ws.recv(), 5) == big
                miss = await ask({"t": "get_file", "q": 5, "acct": ACCT, "id": "p1", "name": "nope"})
                assert miss["ok"] is False
                gone = await ask({"t": "forget", "q": 6, "acct": ACCT, "gone": {"p1": int(time.time() * 1000) + 5000}})
                assert gone["dropped"] == ["p1"]
        finally:
            stop.set()
            await task

    _run(body())


def test_other_sites_cannot_read_the_copies(tmp_path: Path) -> None:
    from websockets.asyncio.client import connect

    async def body() -> None:
        web_port, _probe, stop, task = await _serve(tmp_path)
        try:
            with pytest.raises(Exception):
                async with connect(f"ws://127.0.0.1:{web_port}/store", origin="https://other.a.run.app"):
                    pass
            async with connect(f"ws://127.0.0.1:{web_port}/", origin=ORIGIN) as ws:
                hello = json.loads(await asyncio.wait_for(ws.recv(), 5))
                assert set(hello) == {"t", "cable", "web", "phone"}
        finally:
            stop.set()
            await task

    _run(body())


def test_probe_port_says_hello_and_quit_stops_the_helper(tmp_path: Path) -> None:
    import urllib.request

    async def body() -> None:
        web_port, probe_port, stop, task = await _serve(tmp_path)
        reader, writer = await asyncio.open_connection("127.0.0.1", probe_port)
        line = await asyncio.wait_for(reader.readline(), 5)
        writer.close()
        assert json.loads(line)["helper"] == hs.HELPER_VERSION

        def plain_get() -> None:
            urllib.request.urlopen(f"http://127.0.0.1:{web_port}/store", timeout=3).read()

        with pytest.raises(Exception):
            await asyncio.to_thread(plain_get)
        assert not stop.is_set()

        def quit_get() -> None:
            req = urllib.request.Request(f"http://127.0.0.1:{web_port}/store", headers={"X-Helper-Quit": "1"})
            urllib.request.urlopen(req, timeout=3).read()

        await asyncio.to_thread(quit_get)
        await asyncio.wait_for(task, 5)

    _run(body())


def test_adb_finder_fetches_once_when_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(bridge_mod, "find_adb", lambda: None)
    calls: list[Path] = []

    def fake_fetch(home: Path, log) -> Path:
        calls.append(home)
        p = home / "platform-tools" / "adb.exe"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"x")
        return p

    find = helper_app.adb_finder(lambda *_: None, home=tmp_path, fetch=fake_fetch)
    assert find() is None
    for _ in range(50):
        if (tmp_path / "platform-tools" / "adb.exe").is_file():
            break
        time.sleep(0.05)
    assert find() == str(tmp_path / "platform-tools" / "adb.exe")
    assert calls == [tmp_path]


def test_watch_adb_waits_for_adb_without_crashing() -> None:
    async def body() -> None:
        stop = asyncio.Event()
        logs: list[str] = []
        b = bridge_mod.Bridge(log=logs.append)
        t = asyncio.create_task(bridge_mod.watch_adb(b, lambda: None, 1, stop, probe_port=2))
        await asyncio.sleep(0.2)
        stop.set()
        await asyncio.wait_for(t, 15)
        assert logs == ["adb not found: the phone cannot reach this PC"]

    _run(body())
