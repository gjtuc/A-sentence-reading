"""design/456 - run the web PDF head reader (mobile/web/pdfjs) on PDFs in headless Chrome.

usage: python scripts/pdf_head_probe.py <pdf> [<pdf> ...] [--out .cache/pdf_head]

Writes OUT/<name>.json (what asrPdfHead returned, for the Dart title tests) and
prints only counts per file: ok, code, pages, head chars, styled lines, whether an
Info.Title exists. Paper text is never printed.
"""

from __future__ import annotations

import argparse
import http.server
import json
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

import websocket

sys.path.insert(0, str(Path(__file__).resolve().parent))
from web_probe import CHROMES, _free_port, _page_ws  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
PDFJS = ROOT / "mobile" / "web" / "pdfjs"
PAGE = b"""<!doctype html><html><head><base href="/"></head><body>
<script src="pdfjs/pdf.min.js"></script><script src="pdfjs/asr_pdf_head.js"></script>
</body></html>"""


def _handler(pdfs: list[Path]):
    class H(http.server.BaseHTTPRequestHandler):
        def log_message(self, *a):  # noqa: D401
            pass

        def _send(self, body: bytes, ctype: str) -> None:
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):  # noqa: N802
            if self.path == "/":
                return self._send(PAGE, "text/html")
            if self.path.startswith("/pdfjs/"):
                f = PDFJS / self.path[len("/pdfjs/"):]
                if f.is_file():
                    return self._send(f.read_bytes(), "text/javascript")
            if self.path.startswith("/pdf/"):
                i = int(self.path[len("/pdf/"):])
                return self._send(pdfs[i].read_bytes(), "application/pdf")
            self.send_response(404)
            self.end_headers()

    return H


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("pdfs", nargs="+")
    ap.add_argument("--out", default=str(ROOT / ".cache" / "pdf_head"))
    args = ap.parse_args()
    pdfs = [Path(p).resolve() for p in args.pdfs]
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    chrome = next((p for p in CHROMES if p.exists()), None)
    if chrome is None:
        print("chrome not found")
        return 2
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _handler(pdfs))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    profile = tempfile.mkdtemp(prefix="asr_pdf_head_")
    dbg = _free_port()
    proc = subprocess.Popen(
        [str(chrome), "--headless=new", "--no-first-run", f"--user-data-dir={profile}",
         f"--remote-debugging-port={dbg}", "about:blank"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    bad = 0
    try:
        ws = websocket.create_connection(_page_ws(dbg, time.time() + 30), timeout=120, suppress_origin=True)
        seq = 0

        def call(method: str, params: dict) -> dict:
            nonlocal seq
            seq += 1
            ws.send(json.dumps({"id": seq, "method": method, "params": params}))
            while True:
                msg = json.loads(ws.recv())
                if msg.get("id") == seq:
                    return msg

        call("Page.enable", {})
        call("Page.navigate", {"url": base + "/"})
        for _ in range(100):
            r = call("Runtime.evaluate", {"expression": "typeof window.asrPdfHead", "returnByValue": True})
            if r.get("result", {}).get("result", {}).get("value") == "function":
                break
            time.sleep(0.1)
        for i, pdf in enumerate(pdfs):
            t0 = time.time()
            expr = (f"fetch('/pdf/{i}').then(r=>r.arrayBuffer())"
                    ".then(b=>window.asrPdfHead(b,2,8000))")
            r = call("Runtime.evaluate", {"expression": expr, "awaitPromise": True, "returnByValue": True})
            raw = r.get("result", {}).get("result", {}).get("value")
            if not isinstance(raw, str):
                print(f"{pdf.name}: no result")
                bad += 1
                continue
            data = json.loads(raw)
            (out / (pdf.stem + ".json")).write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            lines = data.get("headLines") or []
            print(
                f"{pdf.name}: ok={data.get('ok')} code={data.get('code') or '-'} pages={data.get('pageCount')}"
                f" head_chars={len(data.get('headText') or '')} lines={len(lines)}"
                f" bold_lines={sum(1 for l in lines if l.get('bold'))}"
                f" max_pt={max((l.get('size_pt') or 0 for l in lines), default=0):.1f}"
                f" info_title={'yes' if data.get('infoTitle') else 'no'} ms={int((time.time() - t0) * 1000)}"
            )
            if not data.get("ok"):
                bad += 1
    finally:
        proc.kill()
        server.shutdown()
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
