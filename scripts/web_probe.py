"""design/403 - open the built Flutter web app in headless Chrome and keep what it said.

usage: python scripts/web_probe.py [--wait-s 25] [--out .cache/web_probe] [--path /]
       python scripts/web_probe.py --app   (design/405: web_app under /app/, /api/ proxied to live)

Serves mobile/build/web on 127.0.0.1, loads it with a throwaway Chrome profile
over the DevTools protocol, waits in real time, and writes OUT.png (screenshot)
and OUT.console.txt (console lines and uncaught exceptions with stacks). Only the
two paths and the counts are printed.
"""

from __future__ import annotations

import argparse
import base64
import http.server
import json
import os
import shutil
import socket
import subprocess
import tempfile
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

import websocket

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "mobile" / "build" / "web"
WEB_APP = ROOT / "src" / "sentence_reading" / "web_app"
LIVE = "https://asr-sentence-reading-984608876300.asia-northeast3.run.app"
_PASS_HEADERS = ("Content-Type", "Accept", "Cookie")
_DROP_REPLY = {"transfer-encoding", "connection", "content-length"}
CHROMES = [
    Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Google/Chrome/Application/chrome.exe",
    Path(os.environ.get("LOCALAPPDATA", "")) / "Google/Chrome/Application/chrome.exe",
    Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
]


def _handler(root: Path, prefix: str, proxy: str | None):
    class Handler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *a, **k):
            super().__init__(*a, directory=str(root), **k)

        def log_message(self, *args):
            pass

        def translate_path(self, path: str) -> str:
            if prefix != "/" and path.startswith(prefix):
                path = "/" + path[len(prefix):]
            return super().translate_path(path)

        def _forward(self, method: str) -> None:
            n = int(self.headers.get("Content-Length") or 0)
            body = self.rfile.read(n) if n else None
            headers = {h: self.headers[h] for h in _PASS_HEADERS if self.headers.get(h)}
            req = urllib.request.Request(proxy + self.path, data=body, method=method, headers=headers)
            try:
                resp = urllib.request.urlopen(req, timeout=60)
            except urllib.error.HTTPError as e:
                resp = e
            data = resp.read()
            self.send_response(resp.status if hasattr(resp, "status") else resp.code)
            for k, v in resp.headers.items():
                if k.lower() not in _DROP_REPLY:
                    self.send_header(k, v)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            if proxy and self.path.startswith("/api/"):
                return self._forward("GET")
            if prefix != "/" and self.path.split("?")[0] == prefix.rstrip("/"):
                self.send_response(302)
                self.send_header("Location", prefix)
                self.end_headers()
                return None
            return super().do_GET()

        def do_POST(self):
            if proxy and self.path.startswith("/api/"):
                return self._forward("POST")
            self.send_error(405)
            return None

    return Handler


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _page_ws(port: int, deadline: float) -> str:
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/json", timeout=2) as r:
                for t in json.load(r):
                    if t.get("type") == "page":
                        return t["webSocketDebuggerUrl"]
        except OSError:
            pass
        time.sleep(0.3)
    raise SystemExit("devtools did not come up")


def _exception_text(d: dict) -> str:
    ex = d.get("exception") or {}
    head = ex.get("description") or d.get("text") or "uncaught"
    tail = []
    st = d.get("stackTrace") or {}
    depth = 0
    while st and depth < 12:
        if st.get("description"):
            tail.append(f"  -- {st['description']}")
        for f in (st.get("callFrames") or [])[:8]:
            name = f.get("functionName") or "?"
            if name.startswith(("_RootZone", "_Future", "_wrapJs", "_awaitOn", "Object.wrapException")):
                continue
            tail.append(f"    at {name} (:{f.get('lineNumber')})")
        st = st.get("parent") or {}
        depth += 1
    return "\n".join(["UNCAUGHT " + head, *tail])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--wait-s", type=float, default=25)
    ap.add_argument("--out", default=str(ROOT / ".cache" / "web_probe"))
    ap.add_argument("--path", default="/")
    ap.add_argument("--app", action="store_true", help="serve web_app at /app/ and proxy /api/ to live")
    args = ap.parse_args()
    root, prefix, proxy = WEB, "/", None
    if args.app:
        root, prefix, proxy = WEB_APP, "/app/", LIVE
        if args.path == "/":
            args.path = "/app/"

    chrome = next((p for p in CHROMES if p.exists()), None)
    if chrome is None:
        print("chrome not found")
        return 2
    if not (root / "index.html").exists():
        print(f"{root} has no index.html; build first")
        return 2

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _handler(root, prefix, proxy))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{server.server_address[1]}{args.path}"

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    png = out.with_suffix(".png")
    console = Path(str(out) + ".console.txt")
    profile = tempfile.mkdtemp(prefix="asr_web_probe_")
    dbg = _free_port()
    proc = subprocess.Popen(
        [
            str(chrome), "--headless=new", "--no-first-run", "--no-default-browser-check",
            f"--user-data-dir={profile}", f"--remote-debugging-port={dbg}",
            "--window-size=430,900", "about:blank",
        ],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    rows: list[str] = []
    n_err = 0
    try:
        ws = websocket.create_connection(
            _page_ws(dbg, time.time() + 30), timeout=5, suppress_origin=True
        )
        seq = 0

        def send(method: str, params: dict | None = None) -> int:
            nonlocal seq
            seq += 1
            ws.send(json.dumps({"id": seq, "method": method, "params": params or {}}))
            return seq

        for m in ("Runtime.enable", "Log.enable", "Page.enable", "Debugger.enable"):
            send(m)
        send("Debugger.setAsyncCallStackDepth", {"maxDepth": 32})
        send("Page.navigate", {"url": url})
        end = time.time() + args.wait_s
        shot_id = None
        dart_text: dict[int, int] = {}
        while True:
            if shot_id is None and time.time() >= end:
                shot_id = send("Page.captureScreenshot", {"format": "png"})
            try:
                msg = json.loads(ws.recv())
            except websocket.WebSocketTimeoutException:
                continue
            if shot_id is not None and msg.get("id") == shot_id:
                png.write_bytes(base64.b64decode(msg["result"]["data"]))
                break
            if msg.get("id") in dart_text:
                value = ((msg.get("result") or {}).get("result") or {}).get("value")
                rows.insert(dart_text.pop(msg["id"]), f"  dart: {value}")
                continue
            method = msg.get("method")
            p = msg.get("params") or {}
            if method == "Runtime.exceptionThrown":
                n_err += 1
                details = p.get("exceptionDetails") or {}
                rows.append(_exception_text(details))
                oid = (details.get("exception") or {}).get("objectId")
                if oid:
                    rid = send(
                        "Runtime.callFunctionOn",
                        {
                            "objectId": oid,
                            "returnByValue": True,
                            "functionDeclaration": (
                                "function(){try{var d=this.dartException;"
                                "return d===undefined?String(this):String(d)}"
                                "catch(e){return 'unreadable: '+e}}"
                            ),
                        },
                    )
                    dart_text[rid] = len(rows)
            elif method == "Runtime.consoleAPICalled":
                parts = [str(a.get("value", a.get("description", ""))) for a in p.get("args", [])]
                level = p.get("type", "log")
                if level in ("error", "assert"):
                    n_err += 1
                rows.append(f"{level.upper()} " + " ".join(parts))
            elif method == "Log.entryAdded":
                e = p.get("entry") or {}
                if e.get("level") == "error":
                    n_err += 1
                rows.append(f"LOG-{e.get('level', '').upper()} {e.get('text', '')} {e.get('url', '')}".rstrip())
        ws.close()
    finally:
        proc.kill()
        server.shutdown()
        time.sleep(0.5)
        shutil.rmtree(profile, ignore_errors=True)

    console.write_text("\n".join(rows) + "\n", encoding="utf-8")
    print(f"screenshot {png}")
    print(f"console {console} lines={len(rows)} errors={n_err}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
