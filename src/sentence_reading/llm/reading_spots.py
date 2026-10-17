"""design/411 — reading spots shared by the devices of one account.

A spot is only numbers: paper cache id -> sentence index, figure index, the device
clock time it was read and the device id. No title, no text. Every write bumps the
account `rev`, so a device asks "what changed since rev N" every few seconds and the
other screen follows. One JSON object per account (`users/{uid}/reading_spots/`),
written with a generation check so two devices never erase each other; without GCS
(tests, local) the store lives in this process.
"""

from __future__ import annotations

import datetime as dt
import json
import threading
from typing import Any

from sentence_reading.llm.gcs_sync import (
    download_bytes_generation,
    gcs_client_ready,
    personal_object_name,
    upload_bytes_generation_match,
)

MAX_SPOTS = 500
CAS_TRIES = 4
_DIR = "reading_spots"
_FILE = "spots.json"
_ID_CHARS = frozenset("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-")
_CID_CHARS = _ID_CHARS | frozenset(".")

_mem: dict[str, dict[str, Any]] = {}
_lock = threading.Lock()


def valid_cache_id(cid: object) -> bool:
    s = str(cid or "")
    return 1 <= len(s) <= 96 and all(c in _CID_CHARS for c in s)


def _valid_device(dev: object) -> bool:
    s = str(dev or "")
    return 8 <= len(s) <= 40 and all(c in _ID_CHARS for c in s)


def _parse_at(at: object) -> dt.datetime | None:
    if not isinstance(at, str) or not 10 <= len(at) <= 40:
        return None
    try:
        t = dt.datetime.fromisoformat(at.replace("Z", "+00:00"))
    except ValueError:
        return None
    return t if t.tzinfo else t.replace(tzinfo=dt.timezone.utc)


def clean_spot(raw: object) -> dict[str, Any] | None:
    """`{si, fi, at, dev}` with sane numbers, or None."""
    if not isinstance(raw, dict):
        return None
    si, fi = raw.get("si"), raw.get("fi")
    if not isinstance(si, int) or isinstance(si, bool) or not 0 <= si <= 1_000_000:
        return None
    if not isinstance(fi, int) or isinstance(fi, bool) or not 0 <= fi <= 100_000:
        return None
    if _parse_at(raw.get("at")) is None or not _valid_device(raw.get("dev")):
        return None
    return {"si": si, "fi": fi, "at": raw["at"], "dev": raw["dev"]}


def _empty() -> dict[str, Any]:
    return {"version": 1, "rev": 0, "spots": {}}


def _parse_store(raw: bytes | None) -> dict[str, Any]:
    if not raw:
        return _empty()
    try:
        store = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return _empty()
    if not isinstance(store, dict) or not isinstance(store.get("spots"), dict):
        return _empty()
    store["rev"] = int(store.get("rev") or 0)
    return store


def _apply(store: dict[str, Any], cid: str, spot: dict[str, Any]) -> bool:
    """Newer `at` wins; returns whether the store changed."""
    spots: dict[str, Any] = store["spots"]
    mine = spots.get(cid)
    if isinstance(mine, dict):
        old = _parse_at(mine.get("at"))
        if old is not None and old >= _parse_at(spot["at"]):
            return False
    store["rev"] += 1
    spots[cid] = {**spot, "rev": store["rev"]}
    if len(spots) > MAX_SPOTS:
        for k, _ in sorted(spots.items(), key=lambda kv: int(kv[1].get("rev") or 0))[: len(spots) - MAX_SPOTS]:
            spots.pop(k, None)
    return True


def _use_gcs() -> bool:
    return gcs_client_ready()[0]


def put(uid: str, cid: str, spot: dict[str, Any]) -> tuple[str, int]:
    """(status, rev); status ok / stale / store_failed."""
    if not _use_gcs():
        with _lock:
            store = _mem.setdefault(uid, _empty())
            changed = _apply(store, cid, spot)
            return ("ok" if changed else "stale"), store["rev"]
    name = personal_object_name(_DIR, _FILE)
    if not name:
        return "store_failed", 0
    for _ in range(CAS_TRIES):
        raw, gen = download_bytes_generation(name, meter=False)
        store = _parse_store(raw)
        if not _apply(store, cid, spot):
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


def since(uid: str, rev: int) -> tuple[int, dict[str, Any]]:
    """(account rev, spots changed after `rev`)."""
    if not _use_gcs():
        with _lock:
            store = _mem.get(uid) or _empty()
            store = json.loads(json.dumps(store))
    else:
        name = personal_object_name(_DIR, _FILE)
        raw, _ = download_bytes_generation(name, meter=False) if name else (None, 0)
        store = _parse_store(raw)
    changed = {
        k: v
        for k, v in store["spots"].items()
        if isinstance(v, dict) and int(v.get("rev") or 0) > rev
    }
    return store["rev"], changed


def reset_memory_for_tests() -> None:
    with _lock:
        _mem.clear()
