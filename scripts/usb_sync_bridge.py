# -*- coding: utf-8 -*-
"""design/451 — near sync over the USB cable.

The web page and the phone both reach this PC program, and it passes the sync
frames between them. Nothing goes through the server.

- Web: WebSocket on 127.0.0.1:47815 (text = control JSON, binary = data).
- Phone: plain TCP on 127.0.0.1:47816 of the phone, which `adb reverse` maps to
  this PC. Frames are [u32 big-endian length][kind byte][payload]; kind 0 is
  control JSON, kind 1 is data. Plain TCP, because the app forbids cleartext
  HTTP (design/138) and a WebSocket is HTTP.

Each side gets {"t":"hello","cable":..,"web":..,"phone":..} on connect and
{"t":"paired"} once both are there. Data passes unchanged after that. When one
side leaves, the other is closed.

Run: python scripts/usb_sync_bridge.py   (click/05_usb_sync.bat does the same)
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import shutil
import struct
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse

WEB_PORT = 47815
PHONE_PORT = 47816
ADB_POLL_S = 2.0
REVERSE_CHECK_S = 20.0
MAX_FRAME = 8 * 1024 * 1024
KIND_CONTROL = 0
KIND_DATA = 1


def find_adb() -> str | None:
    local = os.environ.get("LOCALAPPDATA", "")
    candidates = []
    for env in ("ANDROID_HOME", "ANDROID_SDK_ROOT"):
        root = os.environ.get(env, "")
        if root:
            candidates.append(Path(root) / "platform-tools" / "adb.exe")
    if local:
        candidates.append(Path(local) / "Android" / "Sdk" / "platform-tools" / "adb.exe")
    for c in candidates:
        if c.is_file():
            return str(c)
    return shutil.which("adb")


def origin_allowed(origin: str | None) -> bool:
    """The app's own pages only (Cloud Run host, or a local web build)."""
    if not origin:
        return True
    try:
        u = urlparse(origin)
    except ValueError:
        return False
    host = (u.hostname or "").lower()
    if u.scheme == "https" and host.endswith(".run.app"):
        return True
    return u.scheme in ("http", "https") and host in ("localhost", "127.0.0.1")


def parse_adb_devices(text: str) -> list[str]:
    """Serials in the `device` state (ready, USB debugging allowed)."""
    out = []
    for line in text.splitlines()[1:]:
        parts = line.split()
        if len(parts) >= 2 and parts[1] == "device":
            out.append(parts[0])
    return out


def encode_frame(kind: int, payload: bytes) -> bytes:
    return struct.pack(">IB", len(payload) + 1, kind) + payload


async def read_frame(reader: asyncio.StreamReader) -> tuple[int, bytes]:
    head = await reader.readexactly(4)
    (n,) = struct.unpack(">I", head)
    if n < 1 or n > MAX_FRAME:
        raise ValueError("bad frame length")
    body = await reader.readexactly(n)
    return body[0], body[1:]


class WebEnd:
    def __init__(self, ws) -> None:
        self.ws = ws

    async def control(self, msg: dict) -> None:
        await self.ws.send(json.dumps(msg))

    async def data(self, payload: bytes) -> None:
        await self.ws.send(payload)

    async def close(self) -> None:
        try:
            await self.ws.close()
        except Exception:
            pass


class PhoneEnd:
    def __init__(self, writer: asyncio.StreamWriter) -> None:
        self.writer = writer

    async def control(self, msg: dict) -> None:
        self.writer.write(encode_frame(KIND_CONTROL, json.dumps(msg).encode("utf-8")))
        await self.writer.drain()

    async def data(self, payload: bytes) -> None:
        self.writer.write(encode_frame(KIND_DATA, payload))
        await self.writer.drain()

    async def close(self) -> None:
        try:
            self.writer.close()
            await self.writer.wait_closed()
        except Exception:
            pass


class Bridge:
    def __init__(self, *, log=print) -> None:
        self.web: WebEnd | None = None
        self.phone: PhoneEnd | None = None
        self.cable = False
        self.log = log

    def hello(self) -> dict:
        return {
            "t": "hello",
            "cable": self.cable,
            "web": self.web is not None,
            "phone": self.phone is not None,
        }

    async def _join(self, side: str, end) -> None:
        old = getattr(self, side)
        if old is not None:
            await old.close()
        setattr(self, side, end)
        await end.control(self.hello())
        if self.web is not None and self.phone is not None:
            self.log("paired: web and phone")
            await self.web.control({"t": "paired"})
            await self.phone.control({"t": "paired"})

    async def _leave(self, side: str, end) -> None:
        if getattr(self, side) is not end:
            return
        setattr(self, side, None)
        other = self.phone if side == "web" else self.web
        if other is not None:
            setattr(self, "phone" if side == "web" else "web", None)
            await other.close()
        self.log(f"{side} left")

    async def on_web(self, ws) -> None:
        end = WebEnd(ws)
        await self._join("web", end)
        self.log("web joined")
        try:
            async for msg in ws:
                if isinstance(msg, (bytes, bytearray)) and self.phone is not None:
                    if self.web is end:
                        await self.phone.data(bytes(msg))
        except Exception:
            pass
        finally:
            await self._leave("web", end)

    async def on_phone(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        end = PhoneEnd(writer)
        try:
            await self._join("phone", end)
        except Exception:
            await end.close()
            return
        self.log("phone joined")
        try:
            while True:
                kind, payload = await read_frame(reader)
                if kind == KIND_DATA and self.web is not None and self.phone is end:
                    await self.web.data(payload)
        except Exception:
            pass
        finally:
            await self._leave("phone", end)
            await end.close()


async def watch_adb(bridge: Bridge, adb: str | None, phone_port: int, stop: asyncio.Event) -> None:
    """Keep `adb reverse` on every attached phone; report the cable in hello."""
    if adb is None:
        bridge.log("adb not found: the phone cannot reach this PC")
        return
    flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    spec = f"tcp:{phone_port}"

    def run(*args: str) -> str:
        try:
            done = subprocess.run(
                [adb, *args], capture_output=True, text=True, timeout=10, creationflags=flags
            )
            return done.stdout
        except Exception:
            return ""

    reversed_at: dict[str, float] = {}
    loop = asyncio.get_running_loop()
    while not stop.is_set():
        serials = parse_adb_devices(await asyncio.to_thread(run, "devices"))
        now = loop.time()
        for s in serials:
            due = now - reversed_at.get(s, -1e9) >= REVERSE_CHECK_S
            if s not in reversed_at or due:
                listed = await asyncio.to_thread(run, "-s", s, "reverse", "--list")
                if spec not in listed:
                    await asyncio.to_thread(run, "-s", s, "reverse", spec, spec)
                    bridge.log(f"adb reverse {spec} on {s}")
                reversed_at[s] = now
        for s in list(reversed_at):
            if s not in serials:
                reversed_at.pop(s)
        cable = bool(serials)
        if cable != bridge.cable:
            bridge.cable = cable
            bridge.log("phone cable: " + ("attached" if cable else "none"))
        try:
            await asyncio.wait_for(stop.wait(), ADB_POLL_S)
        except asyncio.TimeoutError:
            pass


async def serve(
    *,
    web_port: int = WEB_PORT,
    phone_port: int = PHONE_PORT,
    adb: str | None = None,
    use_adb: bool = True,
    bridge: Bridge | None = None,
    ready: asyncio.Event | None = None,
    stop: asyncio.Event | None = None,
) -> None:
    from websockets.asyncio.server import serve as ws_serve

    bridge = bridge or Bridge()
    stop = stop or asyncio.Event()

    def check_origin(connection, request):
        if not origin_allowed(request.headers.get("Origin")):
            return connection.respond(403, "origin not allowed\n")
        return None

    phone_server = await asyncio.start_server(bridge.on_phone, "127.0.0.1", phone_port)
    async with ws_serve(
        bridge.on_web,
        "127.0.0.1",
        web_port,
        process_request=check_origin,
        max_size=MAX_FRAME,
        ping_interval=None,
    ):
        watcher = (
            asyncio.create_task(watch_adb(bridge, adb or find_adb(), phone_port, stop))
            if use_adb
            else None
        )
        bridge.log(f"USB sync helper on: web {web_port}, phone {phone_port}")
        if ready is not None:
            ready.set()
        try:
            await stop.wait()
        finally:
            if watcher is not None:
                watcher.cancel()
            phone_server.close()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--web-port", type=int, default=WEB_PORT)
    ap.add_argument("--phone-port", type=int, default=PHONE_PORT)
    args = ap.parse_args()
    try:
        asyncio.run(serve(web_port=args.web_port, phone_port=args.phone_port))
    except OSError as e:
        # Port taken: another helper is already running.
        print(f"USB sync helper not started: {e}")
        return 0
    except KeyboardInterrupt:
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
