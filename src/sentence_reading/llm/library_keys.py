"""design/457 - which papers sit in the library of each device of one account.

The import list marks a file "already in the library" by its PDF sha256 (`h`) or
the paper's title key (`t`). A device only knows its own library, so each device
sends its whole list here and reads the others'. A paper that leaves a library
leaves the device's next list, so its mark goes with it.

One JSON object per account (`users/{uid}/library_keys/keys.json`):
`{version, rev, devices: {dev: {at, items: [{c, h?, t?}]}}}`. A device not heard
from for STALE_DAYS is left out of reads and dropped on the next write.
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
from sentence_reading.llm.reading_done import _HEX, valid_title_key
from sentence_reading.llm.reading_spots import _parse_at, _valid_device, valid_cache_id

MAX_ITEMS = 3000
MAX_DEVICES = 12
STALE_DAYS = 120
CAS_TRIES = 4
_DIR = "library_keys"
_FILE = "keys.json"

_mem: dict[str, dict[str, Any]] = {}
_lock = threading.Lock()


def clean_list(raw: object) -> tuple[str, str, list[dict[str, str]]] | None:
    """(dev, at, items) from `{dev, at, items: [{c, h?, t?}]}`, or None."""
    if not isinstance(raw, dict):
        return None
    dev, at, items = raw.get("dev"), raw.get("at"), raw.get("items")
    if not _valid_device(dev) or _parse_at(at) is None or not isinstance(items, list):
        return None
    if len(items) > MAX_ITEMS:
        return None
    out: list[dict[str, str]] = []
    for it in items:
        if not isinstance(it, dict) or not valid_cache_id(it.get("c")):
            return None
        row = {"c": it["c"]}
        h = it.get("h")
        if h is not None:
            if not isinstance(h, str) or len(h) != 64 or not set(h) <= _HEX:
                return None
            row["h"] = h
        t = it.get("t")
        if t is not None:
            if not valid_title_key(t):
                return None
            row["t"] = t
        out.append(row)
    return dev, at, out


def _empty() -> dict[str, Any]:
    return {"version": 1, "rev": 0, "devices": {}}


def _parse_store(raw: bytes | None) -> dict[str, Any]:
    if not raw:
        return _empty()
    try:
        store = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return _empty()
    if not isinstance(store, dict) or not isinstance(store.get("devices"), dict):
        return _empty()
    store["rev"] = int(store.get("rev") or 0)
    return store


def _fresh(entry: object, now: dt.datetime) -> bool:
    if not isinstance(entry, dict) or not isinstance(entry.get("items"), list):
        return False
    at = _parse_at(entry.get("at"))
    return at is not None and now - at <= dt.timedelta(days=STALE_DAYS)


def _apply(store: dict[str, Any], dev: str, at: str, items: list[dict[str, str]], now: dt.datetime) -> bool:
    """A newer list replaces the device's; returns whether the store changed."""
    devices: dict[str, Any] = store["devices"]
    for k in [k for k, v in devices.items() if not _fresh(v, now)]:
        devices.pop(k, None)
    mine = devices.get(dev)
    if isinstance(mine, dict):
        old = _parse_at(mine.get("at"))
        if old is not None and old >= _parse_at(at):
            return False
    devices[dev] = {"at": at, "items": items}
    if len(devices) > MAX_DEVICES:
        by_age = sorted(devices.items(), key=lambda kv: str(kv[1].get("at") or ""))
        for k, _ in by_age[: len(devices) - MAX_DEVICES]:
            devices.pop(k, None)
    store["rev"] += 1
    return True


def _use_gcs() -> bool:
    return gcs_client_ready()[0]


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def put(uid: str, dev: str, at: str, items: list[dict[str, str]]) -> tuple[str, int]:
    """(status, rev); status ok / stale / store_failed."""
    if not _use_gcs():
        with _lock:
            store = _mem.setdefault(uid, _empty())
            changed = _apply(store, dev, at, items, _now())
            return ("ok" if changed else "stale"), store["rev"]
    name = personal_object_name(_DIR, _FILE)
    if not name:
        return "store_failed", 0
    for _ in range(CAS_TRIES):
        raw, gen = download_bytes_generation(name, meter=False)
        store = _parse_store(raw)
        if not _apply(store, dev, at, items, _now()):
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


def lists(uid: str) -> tuple[int, dict[str, Any]]:
    """(account rev, {dev: {at, items}}) of the devices heard from lately."""
    if not _use_gcs():
        with _lock:
            store = json.loads(json.dumps(_mem.get(uid) or _empty()))
    else:
        name = personal_object_name(_DIR, _FILE)
        raw, _ = download_bytes_generation(name, meter=False) if name else (None, 0)
        store = _parse_store(raw)
    now = _now()
    return store["rev"], {k: v for k, v in store["devices"].items() if _fresh(v, now)}


def reset_memory_for_tests() -> None:
    with _lock:
        _mem.clear()
