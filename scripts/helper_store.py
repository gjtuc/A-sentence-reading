# -*- coding: utf-8 -*-
"""design/495 — the helper keeps a second copy of the web's papers on this PC.

A browser keeps papers in its own storage, which goes when the user clears
browsing data. The web page sends each paper here as well, over the helper's
WebSocket at /store, and takes back what it lost.

Layout under the store root (one folder per account key):

    {acct}/papers/{id}/meta.json   title, hash, added, saved_at, names, extra
    {acct}/papers/{id}/files/...   the paper's transfer-pack files
    {acct}/papers/{id}/extra/...   user files (voice takes)
    {acct}/gone.json               id -> ms the user deleted it in some browser
    {acct}/progress.json           reading positions, as the web last sent them

Requests are JSON text with a request number "q"; the reply echoes it. A file
body travels as one binary message right after its JSON (put_file from the web,
get_file reply from here).
"""
from __future__ import annotations

import json
import os
import re
import shutil
import time
from pathlib import Path
from urllib.parse import urlparse

HELPER_VERSION = "1"
MAX_FILE = 64 * 1024 * 1024
_ACCT_RE = re.compile(r"^[A-Za-z0-9_\-]{6,64}$")
_ID_RE = re.compile(r"^[A-Za-z0-9_\-]{1,80}$")
_PART_RE = re.compile(r"^[^\\/:*?\"<>|\x00-\x1f]{1,120}$")
_KINDS = ("files", "extra")


def default_store_root() -> Path:
    raw = os.environ.get("ASR_HELPER_STORE", "").strip()
    if raw:
        return Path(raw)
    base = os.environ.get("LOCALAPPDATA") or str(Path.home())
    return Path(base) / "SentenceReading" / "helper-papers"


def store_origin_allowed(origin: str | None) -> bool:
    """Only the app's own pages may read the copies (not any *.run.app site)."""
    if not origin:
        return False
    try:
        u = urlparse(origin)
    except ValueError:
        return False
    host = (u.hostname or "").lower()
    if u.scheme == "https" and host.startswith("asr-sentence-reading") and host.endswith(".run.app"):
        return True
    return u.scheme in ("http", "https") and host in ("localhost", "127.0.0.1")


def safe_rel(name: str) -> str | None:
    """A relative file name inside a paper folder, or None."""
    raw = str(name or "").replace("\\", "/").strip()
    if not raw or raw.startswith("/"):
        return None
    parts = raw.split("/")
    if len(parts) > 6:
        return None
    for p in parts:
        if p in ("", ".", "..") or not _PART_RE.match(p) or p.endswith((" ", ".")):
            return None
    return "/".join(parts)


def _now_ms() -> int:
    return int(time.time() * 1000)


def _read_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def _write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)


def _as_ms(v) -> int:
    if isinstance(v, bool):
        return 0
    if isinstance(v, (int, float)) and v > 0:
        return int(v)
    return 0


class StoreError(Exception):
    pass


class PaperStore:
    def __init__(self, root: Path | None = None) -> None:
        self.root = Path(root) if root is not None else default_store_root()

    def _acct(self, acct: str) -> Path:
        if not _ACCT_RE.match(str(acct or "")):
            raise StoreError("bad_acct")
        return self.root / acct

    def _paper(self, acct: str, cid: str) -> Path:
        if not _ID_RE.match(str(cid or "")):
            raise StoreError("bad_id")
        return self._acct(acct) / "papers" / cid

    def _incoming(self, acct: str, cid: str) -> Path:
        self._paper(acct, cid)
        return self._acct(acct) / "incoming" / cid

    def gone(self, acct: str) -> dict[str, int]:
        raw = _read_json(self._acct(acct) / "gone.json", {})
        if not isinstance(raw, dict):
            return {}
        return {str(k): _as_ms(v) for k, v in raw.items() if _ID_RE.match(str(k)) and _as_ms(v)}

    def list(self, acct: str) -> dict:
        papers: dict[str, dict] = {}
        base = self._acct(acct) / "papers"
        if base.is_dir():
            for d in sorted(base.iterdir()):
                meta = _read_json(d / "meta.json", None)
                if not d.is_dir() or not _ID_RE.match(d.name) or not isinstance(meta, dict):
                    continue
                papers[d.name] = meta
        return {"papers": papers, "gone": self.gone(acct)}

    def put_file(self, acct: str, cid: str, kind: str, name: str, data: bytes) -> None:
        rel = safe_rel(name)
        if rel is None or kind not in _KINDS:
            raise StoreError("bad_name")
        if len(data) > MAX_FILE:
            raise StoreError("too_big")
        path = self._incoming(acct, cid) / kind / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def put_done(self, acct: str, cid: str, meta: dict) -> dict:
        """Swap the received files in as this paper's copy; the delete record yields."""
        inc = self._incoming(acct, cid)
        names = [n for n in (meta.get("names") or []) if isinstance(n, str)]
        extra = [n for n in (meta.get("extra") or []) if isinstance(n, str)]
        for kind, want in (("files", names), ("extra", extra)):
            for n in want:
                rel = safe_rel(n)
                if rel is None or not (inc / kind / rel).is_file():
                    shutil.rmtree(inc, ignore_errors=True)
                    raise StoreError("missing_file")
        if not names:
            shutil.rmtree(inc, ignore_errors=True)
            raise StoreError("no_files")
        saved = {
            "id": cid,
            "title": str(meta.get("title") or "")[:400],
            "hash": str(meta.get("hash") or "")[:128],
            "added": _as_ms(meta.get("added")),
            "saved_at": _now_ms(),
            "names": names,
            "extra": extra,
        }
        _write_json(inc / "meta.json", saved)
        dest = self._paper(acct, cid)
        old = dest.with_name(dest.name + ".old")
        shutil.rmtree(old, ignore_errors=True)
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.exists():
            os.replace(dest, old)
        os.replace(inc, dest)
        shutil.rmtree(old, ignore_errors=True)
        gone = self.gone(acct)
        if gone.pop(cid, None) is not None:
            _write_json(self._acct(acct) / "gone.json", gone)
        return saved

    def get_file(self, acct: str, cid: str, kind: str, name: str) -> bytes:
        rel = safe_rel(name)
        if rel is None or kind not in _KINDS:
            raise StoreError("bad_name")
        path = self._paper(acct, cid) / kind / rel
        if not path.is_file():
            raise StoreError("not_found")
        return path.read_bytes()

    def forget(self, acct: str, gone: dict) -> list[str]:
        """Remember deletes (newest per id); drop copies saved before them."""
        record = self.gone(acct)
        dropped: list[str] = []
        for k, v in (gone or {}).items():
            cid, at = str(k), _as_ms(v)
            if not _ID_RE.match(cid) or not at:
                continue
            if at > record.get(cid, 0):
                record[cid] = at
            d = self._paper(acct, cid)
            meta = _read_json(d / "meta.json", None)
            if isinstance(meta, dict) and _as_ms(meta.get("saved_at")) <= at:
                shutil.rmtree(d, ignore_errors=True)
                dropped.append(cid)
        _write_json(self._acct(acct) / "gone.json", record)
        return dropped

    def progress(self, acct: str) -> dict:
        raw = _read_json(self._acct(acct) / "progress.json", {})
        return raw if isinstance(raw, dict) else {}

    def put_progress(self, acct: str, rows: dict) -> None:
        if not isinstance(rows, dict):
            raise StoreError("bad_rows")
        _write_json(self._acct(acct) / "progress.json", rows)


async def store_session(ws, store: PaperStore, hello: dict) -> None:
    """One web page's requests on /store, in order."""
    await ws.send(json.dumps(hello))
    pending: dict | None = None
    async for msg in ws:
        if isinstance(msg, (bytes, bytearray)):
            if pending is None:
                continue
            req, pending = pending, None
            await ws.send(json.dumps(_put_file(store, req, bytes(msg))))
            continue
        try:
            req = json.loads(msg)
        except ValueError:
            continue
        if not isinstance(req, dict):
            continue
        if req.get("t") == "put_file":
            pending = req
            continue
        reply, body = _answer(store, req)
        await ws.send(json.dumps(reply))
        if body is not None:
            await ws.send(body)


def _put_file(store: PaperStore, req: dict, data: bytes) -> dict:
    q = req.get("q")
    try:
        store.put_file(
            str(req.get("acct") or ""),
            str(req.get("id") or ""),
            str(req.get("kind") or "files"),
            str(req.get("name") or ""),
            data,
        )
    except (StoreError, OSError) as e:
        return {"q": q, "ok": False, "error": str(e) or "io"}
    return {"q": q, "ok": True}


def _answer(store: PaperStore, req: dict) -> tuple[dict, bytes | None]:
    q = req.get("q")
    t = req.get("t")
    acct = str(req.get("acct") or "")
    cid = str(req.get("id") or "")
    try:
        if t == "list":
            return {"q": q, "ok": True, **store.list(acct)}, None
        if t == "put_done":
            meta = req.get("meta") if isinstance(req.get("meta"), dict) else {}
            return {"q": q, "ok": True, "saved": store.put_done(acct, cid, meta)}, None
        if t == "get_file":
            body = store.get_file(acct, cid, str(req.get("kind") or "files"), str(req.get("name") or ""))
            return {"q": q, "ok": True, "size": len(body)}, body
        if t == "forget":
            gone = req.get("gone") if isinstance(req.get("gone"), dict) else {}
            return {"q": q, "ok": True, "dropped": store.forget(acct, gone)}, None
        if t == "progress":
            return {"q": q, "ok": True, "rows": store.progress(acct)}, None
        if t == "put_progress":
            store.put_progress(acct, req.get("rows"))
            return {"q": q, "ok": True}, None
    except (StoreError, OSError) as e:
        return {"q": q, "ok": False, "error": str(e) or "io"}, None
    return {"q": q, "ok": False, "error": "unknown"}, None
