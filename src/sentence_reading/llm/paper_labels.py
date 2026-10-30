"""design/490 - the title and kind a reader gave a paper, per account.

One JSON object per account (`users/{uid}/paper_labels/labels.json`): paper cache
id -> `{at, dev, t?, k?}`. `t` is the title to show, `k` the kind (paper, review,
general). A missing field means "as analysed". The paper's own title, title key and
doc role are untouched, so pairing and duplicate checks keep the analysed title.
The newer `at` wins and replaces the whole label, so clearing on one device clears
the other.
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

__all__ = ["clean_label", "labels", "put", "valid_cache_id", "reset_memory_for_tests"]

MAX_LABELS = 5000
MAX_TITLE = 300
KINDS = ("paper", "review", "general")
CAS_TRIES = 4
_DIR = "paper_labels"
_FILE = "labels.json"

_mem: dict[str, dict[str, Any]] = {}
_lock = threading.Lock()


def clean_label(raw: object) -> dict[str, Any] | None:
    """`{at, dev}` plus `t` (shown title) and `k` (kind) when given, or None."""
    if not isinstance(raw, dict):
        return None
    if _parse_at(raw.get("at")) is None or not _valid_device(raw.get("dev")):
        return None
    out: dict[str, Any] = {"at": raw["at"], "dev": raw["dev"]}
    t = raw.get("t")
    if t is not None:
        if not isinstance(t, str):
            return None
        t = " ".join(t.split())
        if not t or len(t) > MAX_TITLE or not t.isprintable():
            return None
        out["t"] = t
    k = raw.get("k")
    if k is not None:
        if k not in KINDS:
            return None
        out["k"] = k
    return out


def _empty() -> dict[str, Any]:
    return {"version": 1, "rev": 0, "labels": {}}


def _parse_store(raw: bytes | None) -> dict[str, Any]:
    if not raw:
        return _empty()
    try:
        store = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return _empty()
    if not isinstance(store, dict) or not isinstance(store.get("labels"), dict):
        return _empty()
    store["rev"] = int(store.get("rev") or 0)
    return store


def _apply(store: dict[str, Any], cid: str, label: dict[str, Any]) -> bool:
    rows: dict[str, Any] = store["labels"]
    mine = rows.get(cid)
    if isinstance(mine, dict):
        old = _parse_at(mine.get("at"))
        if old is not None and old >= _parse_at(label["at"]):
            return False
    store["rev"] += 1
    rows[cid] = dict(label)
    if len(rows) > MAX_LABELS:
        by_age = sorted(rows.items(), key=lambda kv: str(kv[1].get("at") or ""))
        for k, _ in by_age[: len(rows) - MAX_LABELS]:
            rows.pop(k, None)
    return True


def _use_gcs() -> bool:
    return gcs_client_ready()[0]


def put(uid: str, cid: str, label: dict[str, Any]) -> tuple[str, int]:
    """(status, rev); status ok / stale / store_failed."""
    if not _use_gcs():
        with _lock:
            store = _mem.setdefault(uid, _empty())
            changed = _apply(store, cid, label)
            return ("ok" if changed else "stale"), store["rev"]
    name = personal_object_name(_DIR, _FILE)
    if not name:
        return "store_failed", 0
    for _ in range(CAS_TRIES):
        raw, gen = download_bytes_generation(name, meter=False)
        store = _parse_store(raw)
        if not _apply(store, cid, label):
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


def labels(uid: str) -> tuple[int, dict[str, Any]]:
    """(account rev, every label of the account)."""
    if not _use_gcs():
        with _lock:
            store = json.loads(json.dumps(_mem.get(uid) or _empty()))
    else:
        name = personal_object_name(_DIR, _FILE)
        raw, _ = download_bytes_generation(name, meter=False) if name else (None, 0)
        store = _parse_store(raw)
    return store["rev"], {k: v for k, v in store["labels"].items() if isinstance(v, dict)}


def reset_memory_for_tests() -> None:
    with _lock:
        _mem.clear()
