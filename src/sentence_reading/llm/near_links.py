"""design/410 — one-time links that let a phone and the web of one account find each other.

Only the two WebRTC session descriptions pass through here. Papers move device to device.
Links live in GCS under the account (`users/{uid}/near_links/`) so any Cloud Run instance
sees them; without GCS (tests, local) they live in this process.
"""

from __future__ import annotations

import json
import secrets
import threading
import time
from typing import Any

from sentence_reading.llm.gcs_sync import (
    delete_bytes,
    download_bytes,
    gcs_client_ready,
    list_blobs_under,
    personal_object_name,
    upload_bytes,
)

LINK_LIFE_S = 180
MAX_SDP_BYTES = 64 * 1024
_DIR = "near_links"
_ID_CHARS = frozenset("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-")

_mem: dict[str, dict[str, Any]] = {}
_lock = threading.Lock()


def valid_link_id(link_id: object) -> bool:
    s = str(link_id or "")
    return 16 <= len(s) <= 40 and all(c in _ID_CHARS for c in s)


def clean_description(raw: object, kind: str) -> dict[str, str] | None:
    """A WebRTC description `{type, sdp}` of the expected kind, or None."""
    if not isinstance(raw, dict):
        return None
    if raw.get("type") != kind:
        return None
    sdp = raw.get("sdp")
    if not isinstance(sdp, str) or not sdp.strip():
        return None
    if len(sdp.encode("utf-8")) > MAX_SDP_BYTES:
        return None
    return {"type": kind, "sdp": sdp}


def _use_gcs() -> bool:
    return gcs_client_ready()[0]


def _object(link_id: str) -> str | None:
    return personal_object_name(_DIR, f"{link_id}.json")


def _mem_key(uid: str, link_id: str) -> str:
    return f"{uid}/{link_id}"


def _load(uid: str, link_id: str) -> dict[str, Any] | None:
    if not _use_gcs():
        with _lock:
            row = _mem.get(_mem_key(uid, link_id))
            return dict(row) if row else None
    name = _object(link_id)
    if not name:
        return None
    raw = download_bytes(name, meter=False)
    if not raw:
        return None
    try:
        row = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    return row if isinstance(row, dict) else None


def _save(uid: str, link_id: str, row: dict[str, Any]) -> bool:
    if not _use_gcs():
        with _lock:
            _mem[_mem_key(uid, link_id)] = dict(row)
        return True
    name = _object(link_id)
    if not name:
        return False
    data = json.dumps(row, ensure_ascii=False).encode("utf-8")
    return upload_bytes(name, data, content_type="application/json", meter=False)


def _drop(uid: str, link_id: str) -> None:
    if not _use_gcs():
        with _lock:
            _mem.pop(_mem_key(uid, link_id), None)
        return
    name = _object(link_id)
    if name:
        delete_bytes(name)


def _link_ids(uid: str) -> list[str]:
    if not _use_gcs():
        head = f"{uid}/"
        with _lock:
            return [k[len(head):] for k in _mem if k.startswith(head)]
    folder = personal_object_name(_DIR)
    if not folder:
        return []
    out: list[str] = []
    for name in list_blobs_under(folder):
        leaf = name.rsplit("/", 1)[-1]
        if leaf.endswith(".json") and valid_link_id(leaf[: -len(".json")]):
            out.append(leaf[: -len(".json")])
    return out


def _expired(row: dict[str, Any], now: float) -> bool:
    try:
        return float(row.get("expires_at") or 0) <= now
    except (TypeError, ValueError):
        return True


def create(uid: str, offer: dict[str, str], *, now: float | None = None) -> str | None:
    """Store the host offer; returns the new link id (None when storage failed)."""
    t = time.time() if now is None else now
    relay_wipe(uid)
    link_id = secrets.token_urlsafe(18)
    row = {
        "offer": offer,
        "answer": None,
        "claimed": False,
        "created_at": t,
        "expires_at": t + LINK_LIFE_S,
    }
    return link_id if _save(uid, link_id, row) else None


def claim_newest(uid: str, *, now: float | None = None) -> tuple[str, str | None, dict[str, str] | None]:
    """The joiner takes the newest open link of this account.

    Returns (status, link_id, offer); status is ok / none.
    Expired links found on the way are removed.
    """
    t = time.time() if now is None else now
    best: tuple[float, str, dict[str, Any]] | None = None
    for link_id in _link_ids(uid):
        row = _load(uid, link_id)
        if row is None:
            continue
        if _expired(row, t):
            _drop(uid, link_id)
            continue
        if row.get("claimed"):
            continue
        created = float(row.get("created_at") or 0)
        if best is None or created > best[0]:
            best = (created, link_id, row)
    if best is None:
        return "none", None, None
    _, link_id, row = best
    row["claimed"] = True
    if not _save(uid, link_id, row):
        return "none", None, None
    return "ok", link_id, row.get("offer")


def put_answer(uid: str, link_id: str, answer: dict[str, str], *, now: float | None = None) -> str:
    """ok / not_found / expired / not_claimed / answered."""
    t = time.time() if now is None else now
    row = _load(uid, link_id)
    if row is None:
        return "not_found"
    if _expired(row, t):
        _drop(uid, link_id)
        return "expired"
    if not row.get("claimed"):
        return "not_claimed"
    if row.get("answer"):
        return "answered"
    row["answer"] = answer
    return "ok" if _save(uid, link_id, row) else "not_found"


def peek(uid: str, link_id: str, *, now: float | None = None) -> tuple[str, dict[str, Any]]:
    """Host polling: (status, {claimed, answer}); status ok / not_found / expired."""
    t = time.time() if now is None else now
    row = _load(uid, link_id)
    if row is None:
        return "not_found", {}
    if _expired(row, t):
        _drop(uid, link_id)
        return "expired", {}
    return "ok", {"claimed": bool(row.get("claimed")), "answer": row.get("answer")}


def remove(uid: str, link_id: str) -> None:
    _drop(uid, link_id)


# --- relay: the same frames through the server when the devices cannot reach each other.
# A bundle waits under the account until the other side reads the next one, then it is
# deleted. Leftovers of an earlier run are wiped when the account opens a new link.

RELAY_DIR = "near_relay"
RELAY_MAX_BYTES = 4 * 1024 * 1024
RELAY_SIDES = ("h", "j")


def _relay_object(link_id: str, side: str, seq: int) -> str | None:
    return personal_object_name(RELAY_DIR, link_id, side, f"{seq:08d}.bin")


def _relay_mem_key(uid: str, link_id: str, side: str, seq: int) -> str:
    return f"{uid}/relay/{link_id}/{side}/{seq:08d}"


def relay_put(uid: str, link_id: str, side: str, seq: int, data: bytes) -> bool:
    if not _use_gcs():
        with _lock:
            _mem[_relay_mem_key(uid, link_id, side, seq)] = {"data": bytes(data)}
        return True
    name = _relay_object(link_id, side, seq)
    if not name:
        return False
    return upload_bytes(name, bytes(data), content_type="application/octet-stream", meter=False)


def relay_take(uid: str, link_id: str, side: str, seq: int) -> bytes | None:
    """Bundle `seq` (None = not there yet). Asking for it means `seq - 1` arrived, so that one goes."""
    if not _use_gcs():
        with _lock:
            if seq > 0:
                _mem.pop(_relay_mem_key(uid, link_id, side, seq - 1), None)
            row = _mem.get(_relay_mem_key(uid, link_id, side, seq))
            return bytes(row["data"]) if row else None
    if seq > 0:
        prev = _relay_object(link_id, side, seq - 1)
        if prev:
            delete_bytes(prev)
    name = _relay_object(link_id, side, seq)
    if not name:
        return None
    return download_bytes(name, meter=False)


def relay_wipe(uid: str, link_id: str | None = None) -> int:
    """Delete relay bundles of one link (or of every link of the account)."""
    if not _use_gcs():
        head = f"{uid}/relay/" + (f"{link_id}/" if link_id else "")
        with _lock:
            keys = [k for k in _mem if k.startswith(head)]
            for k in keys:
                _mem.pop(k, None)
        return len(keys)
    folder = personal_object_name(RELAY_DIR, link_id) if link_id else personal_object_name(RELAY_DIR)
    if not folder:
        return 0
    n = 0
    for name in list_blobs_under(folder):
        if delete_bytes(name):
            n += 1
    return n


def reset_memory_for_tests() -> None:
    with _lock:
        _mem.clear()
