"""design/442 — papers the reader marked as read to the end, per account.

One JSON object per account (`users/{uid}/reading_done/done.json`): paper cache id
-> `{done, at, dev, h}`. `h` is the PDF's sha256, so the import list can mark the
file and the mark outlives a paper deleted and imported again. design/457 adds `t`,
the paper's title key, so another download of the same paper is marked too. The newer `at` wins,
so un-marking on one device clears it on the other. Reading spots (design/411) drop
their oldest rows past 500, so the mark is kept apart from them.

Written with a generation check like the spots; without GCS (tests, local) the store
lives in this process.
"""

from __future__ import annotations

import json
import threading
from typing import Any

from sentence_reading.llm.gcs_sync import (
    download_bytes_generation,
    gcs_client_ready,
    personal_object_name,
    upload_bytes_generation_match,
)
from sentence_reading.llm.reading_spots import _parse_at, _valid_device, valid_cache_id

MAX_MARKS = 5000
MAX_TITLE_KEY = 300
CAS_TRIES = 4
_DIR = "reading_done"
_FILE = "done.json"
_HEX = frozenset("0123456789abcdef")

_mem: dict[str, dict[str, Any]] = {}
_lock = threading.Lock()


def valid_title_key(t: object) -> bool:
    """design/457 - a normalized title (lowercase words), short and printable."""
    return isinstance(t, str) and 1 <= len(t) <= MAX_TITLE_KEY and t.isprintable() and t == t.strip()


def clean_mark(raw: object) -> dict[str, Any] | None:
    """`{done, at, dev}` plus `h` (64-hex hash) and `t` (title key) when given, or None."""
    if not isinstance(raw, dict):
        return None
    done = raw.get("done")
    if not isinstance(done, bool):
        return None
    if _parse_at(raw.get("at")) is None or not _valid_device(raw.get("dev")):
        return None
    out: dict[str, Any] = {"done": done, "at": raw["at"], "dev": raw["dev"]}
    h = raw.get("h")
    if h is not None:
        if not isinstance(h, str) or len(h) != 64 or not set(h) <= _HEX:
            return None
        out["h"] = h
    t = raw.get("t")
    if t is not None:
        if not valid_title_key(t):
            return None
        out["t"] = t
    return out


def _empty() -> dict[str, Any]:
    return {"version": 1, "rev": 0, "marks": {}}


def _parse_store(raw: bytes | None) -> dict[str, Any]:
    if not raw:
        return _empty()
    try:
        store = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return _empty()
    if not isinstance(store, dict) or not isinstance(store.get("marks"), dict):
        return _empty()
    store["rev"] = int(store.get("rev") or 0)
    return store


def _apply(store: dict[str, Any], cid: str, mark: dict[str, Any]) -> bool:
    """Newer `at` wins; returns whether the store changed.

    design/457 - the same `at` and `done` again only fills `h` / `t` the stored
    mark lacks, so a device can add the title key to a mark made before it.
    """
    marks: dict[str, Any] = store["marks"]
    mine = marks.get(cid)
    if isinstance(mine, dict):
        old = _parse_at(mine.get("at"))
        new = _parse_at(mark["at"])
        if old is not None and old == new and mine.get("done") == mark["done"]:
            fill = {k: mark[k] for k in ("h", "t") if k in mark and k not in mine}
            if not fill:
                return False
            store["rev"] += 1
            mine.update(fill)
            return True
        if old is not None and old >= new:
            return False
    store["rev"] += 1
    marks[cid] = dict(mark)
    if len(marks) > MAX_MARKS:
        by_age = sorted(marks.items(), key=lambda kv: str(kv[1].get("at") or ""))
        for k, _ in by_age[: len(marks) - MAX_MARKS]:
            marks.pop(k, None)
    return True


def _use_gcs() -> bool:
    return gcs_client_ready()[0]


def put(uid: str, cid: str, mark: dict[str, Any]) -> tuple[str, int]:
    """(status, rev); status ok / stale / store_failed."""
    if not _use_gcs():
        with _lock:
            store = _mem.setdefault(uid, _empty())
            changed = _apply(store, cid, mark)
            return ("ok" if changed else "stale"), store["rev"]
    name = personal_object_name(_DIR, _FILE)
    if not name:
        return "store_failed", 0
    for _ in range(CAS_TRIES):
        raw, gen = download_bytes_generation(name, meter=False)
        store = _parse_store(raw)
        if not _apply(store, cid, mark):
            return "stale", store["rev"]
        data = json.dumps(store, ensure_ascii=False).encode("utf-8")
        res = upload_bytes_generation_match(
            name, data, if_generation_match=gen, content_type="application/json", meter=False
        )
        if res == "ok":
            return "ok", store["rev"]
        if res != "conflict":
            break
    return "store_failed", 0


def marks(uid: str) -> tuple[int, dict[str, Any]]:
    """(account rev, every mark of the account)."""
    if not _use_gcs():
        with _lock:
            store = json.loads(json.dumps(_mem.get(uid) or _empty()))
    else:
        name = personal_object_name(_DIR, _FILE)
        raw, _ = download_bytes_generation(name, meter=False) if name else (None, 0)
        store = _parse_store(raw)
    return store["rev"], {k: v for k, v in store["marks"].items() if isinstance(v, dict)}


def reset_memory_for_tests() -> None:
    with _lock:
        _mem.clear()
