"""design/82 — per-user shadowing practice takes (progress + blob keys).

Store under users/{uid}/shadowing/takes/{cache_id}.json (GCS) with local
disk fallback. Voice bytes reuse /api/voice/blobs (personal voice objects).
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

from sentence_reading.llm.auth_google import sanitize_uid
from sentence_reading.llm.gcs_sync import (
    download_bytes,
    gcs_client_ready,
    personal_object_name,
    upload_bytes,
)
from sentence_reading.llm.shadowing_chunks import safe_cache_id
from sentence_reading.llm.shadowing_practice import shadowing_practice_enabled

log = logging.getLogger(__name__)

_MAX_STORE_BYTES = 1_500_000
_MAX_CHUNK_SLOTS = 40
_SENTENCE_ID_RE = re.compile(r"^[a-zA-Z0-9_.:-]{1,64}$")
_STATUSES = frozenset({"empty", "recorded", "skipped"})


def _project_root() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "pyproject.toml").exists():
            return parent
    return Path.cwd()


def takes_object_name(cache_id: str) -> str | None:
    cid = safe_cache_id(cache_id)
    if not cid:
        return None
    return personal_object_name("shadowing", "takes", f"{cid}.json")


def _local_path(uid: str, cache_id: str) -> Path | None:
    u = sanitize_uid(uid)
    cid = safe_cache_id(cache_id)
    if not u or not cid:
        return None
    return (
        _project_root()
        / "data"
        / "shadowing"
        / "users"
        / u
        / "takes"
        / f"{cid}.json"
    )


def safe_sentence_id(raw: str | None) -> str | None:
    sid = (raw or "").strip()
    if not _SENTENCE_ID_RE.match(sid):
        return None
    return sid


def empty_takes(cache_id: str) -> dict[str, Any]:
    return {
        "version": 1,
        "cache_id": cache_id,
        "cursor": {"sentence_id": None, "chunk_index": 0},
        "sentences": {},
    }


def _decode(raw: bytes | None, cache_id: str) -> dict[str, Any]:
    if not raw or len(raw) > _MAX_STORE_BYTES:
        return empty_takes(cache_id)
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError):
        return empty_takes(cache_id)
    if not isinstance(data, dict):
        return empty_takes(cache_id)
    data["version"] = 1
    data["cache_id"] = cache_id
    if not isinstance(data.get("sentences"), dict):
        data["sentences"] = {}
    cur = data.get("cursor")
    if not isinstance(cur, dict):
        data["cursor"] = {"sentence_id": None, "chunk_index": 0}
    return data


def load_takes(*, uid: str, cache_id: str) -> dict[str, Any]:
    """Load takes for uid+cache_id only — never another user's object."""
    cid = safe_cache_id(cache_id)
    u = sanitize_uid(uid)
    if not cid or not u:
        return empty_takes(cache_id or "")
    ready, _ = gcs_client_ready()
    if ready:
        name = takes_object_name(cid)
        if name:
            raw = download_bytes(name)
            if raw is not None:
                return _decode(raw, cid)
    path = _local_path(u, cid)
    if path and path.is_file():
        try:
            return _decode(path.read_bytes(), cid)
        except OSError:
            return empty_takes(cid)
    return empty_takes(cid)


def save_takes(*, uid: str, cache_id: str, takes: dict[str, Any]) -> None:
    cid = safe_cache_id(cache_id)
    u = sanitize_uid(uid)
    if not cid or not u:
        raise ValueError("invalid_id")
    if not shadowing_practice_enabled():
        # WHY: kill off → refuse writes (fail-closed).
        raise PermissionError("shadowing_disabled")
    payload = dict(takes)
    payload["version"] = 1
    payload["cache_id"] = cid
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode(
        "utf-8"
    )
    if len(raw) > _MAX_STORE_BYTES:
        raise ValueError("takes_too_large")
    ready, _ = gcs_client_ready()
    if ready:
        name = takes_object_name(cid)
        if name:
            upload_bytes(name, raw, content_type="application/json")
    path = _local_path(u, cid)
    if path is None:
        raise ValueError("invalid_id")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)


def delete_takes(*, uid: str, cache_id: str) -> bool:
    """design/102 — delete takes JSON + referenced voice blobs + local file."""
    from sentence_reading.llm.gcs_sync import delete_bytes
    from sentence_reading.llm.voice_gcs import delete_voice_blob

    cid = safe_cache_id(cache_id)
    u = sanitize_uid(uid)
    if not cid or not u:
        return False
    # Load first so we can purge voice blobs.
    takes = load_takes(uid=u, cache_id=cid)
    blob_keys: list[str] = []
    sentences = takes.get("sentences") if isinstance(takes, dict) else None
    if isinstance(sentences, dict):
        for row in sentences.values():
            if not isinstance(row, dict):
                continue
            for c in row.get("chunks") or []:
                if isinstance(c, dict) and c.get("blob_key"):
                    blob_keys.append(str(c["blob_key"]))
    ok = True
    ready, _ = gcs_client_ready()
    if ready:
        name = takes_object_name(cid)
        if name:
            try:
                delete_bytes(name)
            except Exception:  # noqa: BLE001
                ok = False
    path = _local_path(u, cid)
    if path is not None and path.is_file():
        try:
            path.unlink()
        except OSError:
            ok = False
    for bk in blob_keys:
        try:
            delete_voice_blob(bk)
        except Exception:  # noqa: BLE001
            ok = False
    return ok


def _slot(status: str, blob_key: str | None = None, mime: str | None = None) -> dict[str, Any]:
    st = status if status in _STATUSES else "empty"
    out: dict[str, Any] = {"status": st, "blob_key": None, "mime": None}
    if st == "recorded" and blob_key:
        out["blob_key"] = str(blob_key)[:500]
        out["mime"] = (mime or "audio/webm")[:80]
    return out


def ensure_sentence_slots(
    takes: dict[str, Any], *, sentence_id: str, chunk_count: int
) -> dict[str, Any]:
    """Ensure sentence has chunk_count slots (empty). Does not shrink recorded slots."""
    sid = safe_sentence_id(sentence_id)
    if not sid:
        raise ValueError("invalid_sentence_id")
    n = int(chunk_count)
    if n < 1 or n > _MAX_CHUNK_SLOTS:
        raise ValueError("invalid_chunk_count")
    sentences = takes.setdefault("sentences", {})
    row = sentences.get(sid)
    if not isinstance(row, dict):
        row = {"chunks": [], "full_pass": False}
    chunks = row.get("chunks")
    if not isinstance(chunks, list):
        chunks = []
    while len(chunks) < n:
        chunks.append(_slot("empty"))
    # Do not truncate — EDGE: plan grew; keep old takes, client uses plan length.
    row["chunks"] = chunks
    row["full_pass"] = bool(_compute_full_pass(chunks, n))
    sentences[sid] = row
    return takes


def _compute_full_pass(chunks: list[Any], plan_len: int) -> bool:
    """Full pass = every plan slot recorded (not skipped/empty) through last chunk."""
    if plan_len < 1 or len(chunks) < plan_len:
        return False
    for i in range(plan_len):
        c = chunks[i]
        if not isinstance(c, dict) or c.get("status") != "recorded":
            return False
        if not c.get("blob_key"):
            return False
    return True


def apply_take(
    takes: dict[str, Any],
    *,
    sentence_id: str,
    chunk_index: int,
    chunk_count: int,
    status: str,
    blob_key: str | None = None,
    mime: str | None = None,
) -> dict[str, Any]:
    """Record or skip one chunk; update cursor + full_pass."""
    if not shadowing_practice_enabled():
        raise PermissionError("shadowing_disabled")
    sid = safe_sentence_id(sentence_id)
    if not sid:
        raise ValueError("invalid_sentence_id")
    idx = int(chunk_index)
    if idx < 0 or idx >= _MAX_CHUNK_SLOTS:
        raise ValueError("invalid_chunk_index")
    st = (status or "").strip().lower()
    if st not in ("recorded", "skipped"):
        raise ValueError("invalid_status")
    if st == "recorded" and not (blob_key or "").strip():
        raise ValueError("blob_required")
    takes = ensure_sentence_slots(takes, sentence_id=sid, chunk_count=chunk_count)
    row = takes["sentences"][sid]
    chunks = row["chunks"]
    while len(chunks) <= idx:
        chunks.append(_slot("empty"))
    chunks[idx] = _slot(st, blob_key=blob_key, mime=mime)
    row["full_pass"] = bool(_compute_full_pass(chunks, chunk_count))
    # Cursor advances to next chunk in sentence, or stays at end.
    next_i = idx + 1
    takes["cursor"] = {
        "sentence_id": sid,
        "chunk_index": next_i if next_i < chunk_count else idx,
    }
    return takes


def set_cursor(
    takes: dict[str, Any], *, sentence_id: str | None, chunk_index: int = 0
) -> dict[str, Any]:
    sid = safe_sentence_id(sentence_id) if sentence_id else None
    idx = max(0, min(int(chunk_index), _MAX_CHUNK_SLOTS - 1))
    takes["cursor"] = {"sentence_id": sid, "chunk_index": idx}
    return takes


def full_pass_blob_keys(takes: dict[str, Any], sentence_ids: list[str]) -> list[dict[str, Any]]:
    """For section continue-listen: only sentences with full_pass, in given order."""
    out: list[dict[str, Any]] = []
    sentences = takes.get("sentences") if isinstance(takes.get("sentences"), dict) else {}
    for sid in sentence_ids:
        safe = safe_sentence_id(sid)
        if not safe:
            continue
        row = sentences.get(safe)
        if not isinstance(row, dict) or not row.get("full_pass"):
            continue
        chunks = row.get("chunks") if isinstance(row.get("chunks"), list) else []
        keys = []
        for c in chunks:
            if isinstance(c, dict) and c.get("status") == "recorded" and c.get("blob_key"):
                keys.append(
                    {"blob_key": c["blob_key"], "mime": c.get("mime") or "audio/webm"}
                )
        if keys:
            out.append({"sentence_id": safe, "takes": keys})
    return out
