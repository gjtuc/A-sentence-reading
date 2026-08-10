"""
Chunked PDF upload sessions under users/{uid}/ingest_chunks/ (design/72).

WHY: multipart mid-transfer kill forced a full re-POST; chunks resume from offset.
EDGE: contiguous offsets only; resume requires prefix_sha256 match (integrity).
INVARIANT: owner from session UID only — never trust body user_id.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import threading
import uuid
from datetime import datetime, timezone
from typing import Any

from sentence_reading.llm.auth_google import current_gcs_uid, set_gcs_uid
from sentence_reading.llm.gcs_sync import (
    delete_bytes,
    download_bytes,
    gcs_config,
    personal_object_name,
    upload_bytes,
)

log = logging.getLogger(__name__)

_UPLOAD_ID_RE = re.compile(r"^upl_[a-f0-9]{12}$")
_HASH_RE = re.compile(r"^[a-f0-9]{64}$")
CHUNK_SIZE = 256 * 1024  # 256 KiB — all PDFs (product: every file is chunked)
_MAX_BYTES = 50 * 1024 * 1024

# Process-local fallback when GCS is off (unit tests / local without bucket).
_LOCK = threading.Lock()
_MEM_META: dict[str, dict[str, Any]] = {}
_MEM_PARTS: dict[str, dict[int, bytes]] = {}
# Running sha256 of bytes[0:received_offset] — rebuilt from parts after process restart.
_MEM_PREFIX_HASHER: dict[str, Any] = {}


def chunked_upload_enabled() -> bool:
    """Kill switch: ASR_CHUNKED_UPLOAD=0 disables new chunk sessions."""
    raw = (os.environ.get("ASR_CHUNKED_UPLOAD") or "1").strip().lower()
    return raw not in ("0", "false", "off", "no")


def valid_upload_id(upload_id: str) -> bool:
    return bool(_UPLOAD_ID_RE.match((upload_id or "").strip()))


def _with_uid(uid: str | None):
    class _Ctx:
        def __enter__(self):
            self._prev = current_gcs_uid()
            if uid:
                set_gcs_uid(uid)
            return self

        def __exit__(self, *args):
            set_gcs_uid(self._prev)

    return _Ctx()


def _meta_object(upload_id: str, *, uid: str) -> str | None:
    if not valid_upload_id(upload_id) or not uid:
        return None
    with _with_uid(uid):
        return personal_object_name("ingest_chunks", upload_id, "meta.json")


def _part_object(upload_id: str, offset: int, *, uid: str) -> str | None:
    if not valid_upload_id(upload_id) or offset < 0:
        return None
    with _with_uid(uid):
        return personal_object_name(
            "ingest_chunks", upload_id, f"{int(offset)}.part"
        )


def _gcs_on() -> bool:
    return bool(gcs_config().enabled)


def _save_meta(meta: dict[str, Any]) -> bool:
    uid = str(meta.get("owner_uid") or "").strip()
    upload_id = str(meta.get("upload_id") or "").strip()
    if not uid or not valid_upload_id(upload_id):
        return False
    with _LOCK:
        _MEM_META[upload_id] = dict(meta)
    if not _gcs_on():
        return True
    obj = _meta_object(upload_id, uid=uid)
    if not obj:
        return False
    raw = json.dumps(meta, ensure_ascii=False, separators=(",", ":")).encode(
        "utf-8"
    )
    return upload_bytes(obj, raw, content_type="application/json")


def _load_meta(upload_id: str, *, owner_uid: str) -> dict[str, Any] | None:
    uid = (owner_uid or "").strip()
    if not uid or not valid_upload_id(upload_id):
        return None
    with _LOCK:
        mem = _MEM_META.get(upload_id)
        if isinstance(mem, dict) and str(mem.get("owner_uid") or "") == uid:
            return dict(mem)
    if not _gcs_on():
        return None
    obj = _meta_object(upload_id, uid=uid)
    if not obj:
        return None
    raw = download_bytes(obj)
    if not raw:
        return None
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    if str(data.get("owner_uid") or "") != uid:
        return None
    if str(data.get("upload_id") or "") != upload_id:
        return None
    with _LOCK:
        _MEM_META[upload_id] = dict(data)
    return dict(data)


def _save_part(
    upload_id: str, offset: int, data: bytes, *, owner_uid: str
) -> bool:
    uid = (owner_uid or "").strip()
    if not uid or not data:
        return False
    with _LOCK:
        _MEM_PARTS.setdefault(upload_id, {})[int(offset)] = bytes(data)
    if not _gcs_on():
        return True
    obj = _part_object(upload_id, offset, uid=uid)
    if not obj:
        return False
    return upload_bytes(obj, bytes(data), content_type="application/octet-stream")


def _load_part(
    upload_id: str, offset: int, *, owner_uid: str
) -> bytes | None:
    uid = (owner_uid or "").strip()
    with _LOCK:
        part = _MEM_PARTS.get(upload_id, {}).get(int(offset))
        if part is not None:
            return bytes(part)
    if not _gcs_on():
        return None
    obj = _part_object(upload_id, offset, uid=uid)
    if not obj:
        return None
    return download_bytes(obj)


def delete_upload_session(upload_id: str, *, owner_uid: str) -> None:
    """Best-effort wipe of meta + known parts (fail-closed cleanup)."""
    uid = (owner_uid or "").strip()
    meta = _load_meta(upload_id, owner_uid=uid)
    digests = {}
    if meta:
        digests = meta.get("chunk_digests") or {}
    with _LOCK:
        _MEM_META.pop(upload_id, None)
        _MEM_PARTS.pop(upload_id, None)
        _MEM_PREFIX_HASHER.pop(upload_id, None)
    if not _gcs_on() or not uid:
        return
    obj = _meta_object(upload_id, uid=uid)
    if obj:
        delete_bytes(obj)
    if isinstance(digests, dict):
        for key in digests:
            try:
                off = int(key)
            except (TypeError, ValueError):
                continue
            pobj = _part_object(upload_id, off, uid=uid)
            if pobj:
                delete_bytes(pobj)


def create_upload_session(
    *,
    owner_uid: str,
    content_hash: str,
    filename: str,
    size: int,
) -> dict[str, Any] | None:
    uid = (owner_uid or "").strip()
    ch = (content_hash or "").strip().lower()
    name = (filename or "").strip()[:180]
    if not uid or not _HASH_RE.match(ch) or not name:
        return None
    if size < 1 or size > _MAX_BYTES:
        return None
    upload_id = f"upl_{uuid.uuid4().hex[:12]}"
    meta: dict[str, Any] = {
        "upload_id": upload_id,
        "owner_uid": uid,
        "content_hash": ch,
        "filename": name,
        "size": int(size),
        "chunk_size": CHUNK_SIZE,
        "received_offset": 0,
        "prefix_sha256": "",
        "chunk_digests": {},
        "created_at": datetime.now(timezone.utc).isoformat(),
        "complete": False,
    }
    if not _save_meta(meta):
        return None
    return public_upload_view(meta)


def public_upload_view(meta: dict[str, Any]) -> dict[str, Any]:
    return {
        "ok": True,
        "upload_id": str(meta.get("upload_id") or ""),
        "content_hash": str(meta.get("content_hash") or ""),
        "filename": str(meta.get("filename") or ""),
        "size": int(meta.get("size") or 0),
        "chunk_size": int(meta.get("chunk_size") or CHUNK_SIZE),
        "received_offset": int(meta.get("received_offset") or 0),
        "prefix_sha256": str(meta.get("prefix_sha256") or ""),
        "complete": bool(meta.get("complete")),
    }


def append_chunk(
    upload_id: str,
    *,
    owner_uid: str,
    offset: int,
    data: bytes,
    chunk_sha256: str | None = None,
) -> dict[str, Any]:
    """
    Append one contiguous chunk at expected offset.
    Returns public view or raises ValueError with safe message key.
    """
    meta = _load_meta(upload_id, owner_uid=owner_uid)
    if meta is None:
        raise LookupError("upload_not_found")
    if meta.get("complete"):
        raise ValueError("upload_already_complete")
    expected = int(meta.get("received_offset") or 0)
    size = int(meta.get("size") or 0)
    chunk_size = int(meta.get("chunk_size") or CHUNK_SIZE)
    if offset != expected:
        # WHY: refuse sparse/out-of-order writes — integrity model is prefix-based.
        raise ValueError("offset_mismatch")
    if not isinstance(data, (bytes, bytearray)) or len(data) == 0:
        raise ValueError("empty_chunk")
    if len(data) > chunk_size:
        raise ValueError("chunk_too_large")
    if expected + len(data) > size:
        raise ValueError("chunk_past_end")
    # Last chunk may be smaller; non-last must be full size.
    if expected + len(data) < size and len(data) != chunk_size:
        raise ValueError("chunk_size_mismatch")
    digest = hashlib.sha256(bytes(data)).hexdigest()
    if chunk_sha256:
        want = chunk_sha256.strip().lower()
        if want != digest:
            raise ValueError("chunk_hash_mismatch")
    if not _save_part(upload_id, expected, bytes(data), owner_uid=owner_uid):
        raise RuntimeError("chunk_store_failed")
    new_offset = expected + len(data)
    # WHY: client resume checks sha256(local[0:offset]) == prefix_sha256.
    prefix_sha = _update_prefix_hash(
        upload_id,
        expected,
        bytes(data),
        owner_uid=owner_uid,
        meta=meta,
    )
    digests = dict(meta.get("chunk_digests") or {})
    digests[str(expected)] = digest
    meta["chunk_digests"] = digests
    meta["received_offset"] = new_offset
    meta["prefix_sha256"] = prefix_sha
    if not _save_meta(meta):
        raise RuntimeError("meta_store_failed")
    return public_upload_view(meta)


def _update_prefix_hash(
    upload_id: str,
    offset: int,
    chunk: bytes,
    *,
    owner_uid: str,
    meta: dict[str, Any],
) -> str:
    """Extend running sha256; rebuild from stored parts if hasher missing."""
    with _LOCK:
        hasher = _MEM_PREFIX_HASHER.get(upload_id)
    if hasher is None:
        if offset == 0:
            hasher = hashlib.sha256()
        else:
            # Process restart mid-upload — rebuild prefix hash once.
            prefix = _assemble_prefix(
                upload_id, offset, owner_uid=owner_uid, meta=meta
            )
            if prefix is None or len(prefix) != offset:
                raise RuntimeError("prefix_assemble_failed")
            hasher = hashlib.sha256()
            hasher.update(prefix)
        with _LOCK:
            _MEM_PREFIX_HASHER[upload_id] = hasher
    hasher.update(chunk)
    return hasher.hexdigest()


def _assemble_prefix(
    upload_id: str,
    end: int,
    *,
    owner_uid: str,
    meta: dict[str, Any],
) -> bytes | None:
    chunk_size = int(meta.get("chunk_size") or CHUNK_SIZE)
    out = bytearray()
    off = 0
    while off < end:
        part = _load_part(upload_id, off, owner_uid=owner_uid)
        if part is None:
            return None
        need = min(len(part), end - off)
        out.extend(part[:need])
        off += len(part)
        if len(part) == 0:
            return None
        # Guard against infinite loop on corrupt meta
        if off > end + chunk_size:
            return None
    return bytes(out)


def assemble_and_verify(
    upload_id: str, *, owner_uid: str
) -> tuple[bytes, dict[str, Any]]:
    meta = _load_meta(upload_id, owner_uid=owner_uid)
    if meta is None:
        raise LookupError("upload_not_found")
    size = int(meta.get("size") or 0)
    received = int(meta.get("received_offset") or 0)
    if received != size:
        raise ValueError("upload_incomplete")
    raw = _assemble_prefix(
        upload_id, size, owner_uid=owner_uid, meta=meta
    )
    if raw is None or len(raw) != size:
        raise RuntimeError("assemble_failed")
    digest = hashlib.sha256(raw).hexdigest()
    if digest != str(meta.get("content_hash") or "").lower():
        # EDGE: fail-closed — never start ingest on tampered/concat mismatch.
        raise ValueError("content_hash_mismatch")
    if size >= 5 and not raw.startswith(b"%PDF"):
        raise ValueError("invalid_pdf")
    return raw, meta


def get_upload(
    upload_id: str, *, owner_uid: str
) -> dict[str, Any] | None:
    meta = _load_meta(upload_id, owner_uid=owner_uid)
    if meta is None:
        return None
    return public_upload_view(meta)


def clear_memory_for_tests() -> None:
    with _LOCK:
        _MEM_META.clear()
        _MEM_PARTS.clear()
        _MEM_PREFIX_HASHER.clear()
