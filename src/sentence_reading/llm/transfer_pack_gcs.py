"""design/186 — GCS transfer packs (cross-device temporary crates)."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

log = logging.getLogger(__name__)

_PACK_ID_RE = re.compile(r"^[a-zA-Z0-9]{16,32}$")
_CACHE_ID_RE = re.compile(r"^[a-zA-Z0-9]{8,32}$")
_REL_SAFE_RE = re.compile(r"^[a-zA-Z0-9._\-]+(?:/[a-zA-Z0-9._\-]+)*$")
_ALLOWED_RELS = frozenset(
    {
        "session.json",
        "manifest.json",
        "layout_map.json",
        "slot_plan.json",
        "source.pdf",
        "source.docx",
    }
)


def transfer_pack_enabled() -> bool:
    v = (os.environ.get("ASR_TRANSFER_PACK") or "1").strip().lower()
    return v not in ("0", "false", "off", "no")


def transfer_pack_ttl_hours() -> int:
    raw = (os.environ.get("ASR_TRANSFER_PACK_TTL_HOURS") or "168").strip()
    try:
        h = int(raw)
    except ValueError:
        return 168
    return max(1, min(h, 24 * 30))


def transfer_pack_abandon_hours() -> int:
    raw = (os.environ.get("ASR_TRANSFER_PACK_ABANDON_HOURS") or "24").strip()
    try:
        h = int(raw)
    except ValueError:
        return 24
    return max(1, min(h, 24 * 14))


def transfer_pack_max_bytes() -> int:
    raw = (os.environ.get("ASR_TRANSFER_PACK_MAX_BYTES") or str(200 * 1024 * 1024)).strip()
    try:
        n = int(raw)
    except ValueError:
        return 200 * 1024 * 1024
    return max(1024 * 1024, min(n, 512 * 1024 * 1024))


def transfer_pack_max_active() -> int:
    raw = (os.environ.get("ASR_TRANSFER_PACK_MAX_ACTIVE") or "3").strip()
    try:
        n = int(raw)
    except ValueError:
        return 3
    return max(1, min(n, 20))


def transfer_pack_lease_sec() -> int:
    raw = (os.environ.get("ASR_TRANSFER_PACK_LEASE_SEC") or "1800").strip()
    try:
        n = int(raw)
    except ValueError:
        return 1800
    return max(60, min(n, 6 * 3600))


def transfer_pack_piece_max() -> int:
    """Client soft target / server per-request body cap (design/186 J14)."""
    raw = (os.environ.get("ASR_TRANSFER_PACK_PIECE_MAX") or str(4 * 1024 * 1024)).strip()
    try:
        n = int(raw)
    except ValueError:
        return 4 * 1024 * 1024
    return max(256 * 1024, min(n, 16 * 1024 * 1024))


def status_fields() -> dict[str, Any]:
    from sentence_reading.llm.transfer_pack_ttl import purge_enabled

    return {
        "transfer_pack": transfer_pack_enabled(),
        "transfer_pack_ttl": purge_enabled(),
        "transfer_pack_ttl_hours": transfer_pack_ttl_hours(),
        "transfer_pack_max_bytes": transfer_pack_max_bytes(),
        "transfer_pack_max_active": transfer_pack_max_active(),
        "transfer_pack_piece_max": transfer_pack_piece_max(),
    }


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_iso(raw: str) -> datetime | None:
    s = (raw or "").strip()
    if not s:
        return None
    try:
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except ValueError:
        return None


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _hash16(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()[:16]


def new_pack_id() -> str:
    return uuid.uuid4().hex


def safe_rel_path(path: str) -> str | None:
    rel = (path or "").strip().replace("\\", "/")
    if not rel or rel.startswith("/") or ".." in rel.split("/"):
        return None
    if not _REL_SAFE_RE.match(rel):
        return None
    if rel in _ALLOWED_RELS:
        return rel
    if rel.startswith("figures/") and rel.endswith(".png"):
        return rel
    return None


def assert_deletable_pack_object(object_name: str, *, uid: str) -> str | None:
    """Allow only users/{uid}/transfer_packs/... — never papers/ or ingest_*."""
    name = (object_name or "").strip().replace("\\", "/")
    uid_s = (uid or "").strip()
    if not name or not uid_s or ".." in name:
        return None
    if "/papers/" in name or "/ingest_" in name:
        return None
    marker = f"/users/{uid_s}/transfer_packs/"
    idx = name.find(marker)
    if idx < 0:
        return None
    return name


def _meta_object(pack_id: str) -> str | None:
    from sentence_reading.llm.gcs_sync import personal_object_name

    pid = (pack_id or "").strip()
    if not _PACK_ID_RE.match(pid):
        return None
    return personal_object_name("transfer_packs", pid, "meta.json")


def _manifest_object(pack_id: str) -> str | None:
    from sentence_reading.llm.gcs_sync import personal_object_name

    pid = (pack_id or "").strip()
    if not _PACK_ID_RE.match(pid):
        return None
    return personal_object_name("transfer_packs", pid, "manifest.json")


def _file_object(pack_id: str, rel: str) -> str | None:
    from sentence_reading.llm.gcs_sync import personal_object_name

    pid = (pack_id or "").strip()
    safe = safe_rel_path(rel)
    if not _PACK_ID_RE.match(pid) or not safe:
        return None
    # Nested: transfer_packs/{id}/files/a/b.png via multiple parts
    parts = ["transfer_packs", pid, "files", *safe.split("/")]
    return personal_object_name(*parts)


def _pack_prefix(pack_id: str) -> str | None:
    from sentence_reading.llm.gcs_sync import personal_object_name

    pid = (pack_id or "").strip()
    if not _PACK_ID_RE.match(pid):
        return None
    return personal_object_name("transfer_packs", pid)


def load_meta(pack_id: str) -> dict[str, Any] | None:
    from sentence_reading.llm.gcs_sync import download_bytes, gcs_client_ready, gcs_config

    obj = _meta_object(pack_id)
    if not obj:
        return None
    ready, _ = gcs_client_ready()
    if not gcs_config().enabled or not ready:
        return None
    raw = download_bytes(obj)
    if not raw:
        return None
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def save_meta(pack_id: str, meta: dict[str, Any]) -> bool:
    from sentence_reading.llm.gcs_sync import gcs_client_ready, gcs_config, upload_bytes

    obj = _meta_object(pack_id)
    if not obj:
        return False
    ready, _ = gcs_client_ready()
    if not gcs_config().enabled or not ready:
        return False
    payload = dict(meta)
    payload["updated_at"] = _utc_now().isoformat()
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return bool(upload_bytes(obj, raw, content_type="application/json"))


def list_pack_ids() -> list[str]:
    from sentence_reading.llm.gcs_sync import list_blobs_under, personal_object_name

    prefix = personal_object_name("transfer_packs")
    if not prefix:
        return []
    names = list_blobs_under(prefix + "/")
    out: set[str] = set()
    marker = prefix.rstrip("/") + "/"
    for name in names:
        n = str(name or "").replace("\\", "/")
        if not n.startswith(marker):
            continue
        rest = n[len(marker) :]
        pid = rest.split("/", 1)[0]
        if _PACK_ID_RE.match(pid):
            out.add(pid)
    return sorted(out)


def count_active_packs() -> int:
    n = 0
    for pid in list_pack_ids():
        meta = load_meta(pid)
        if not meta:
            continue
        st = str(meta.get("status") or "")
        if st in ("pending", "ready"):
            n += 1
    return n


def create_pack(
    *,
    cache_id: str,
    title: str,
    declared_bytes: int,
) -> dict[str, Any]:
    if not transfer_pack_enabled():
        return {"ok": False, "error": "disabled"}
    cid = (cache_id or "").strip()
    if not _CACHE_ID_RE.match(cid):
        return {"ok": False, "error": "bad_cache_id"}
    try:
        declared = int(declared_bytes)
    except (TypeError, ValueError):
        declared = 0
    if declared <= 0 or declared > transfer_pack_max_bytes():
        return {"ok": False, "error": "bytes_quota"}
    if count_active_packs() >= transfer_pack_max_active():
        return {"ok": False, "error": "active_quota"}

    pid = new_pack_id()
    now = _utc_now().isoformat()
    meta = {
        "v": 1,
        "pack_id": pid,
        "cache_id": cid,
        "title": (title or cid).strip()[:200],
        "status": "pending",
        "declared_bytes": declared,
        "bytes": 0,
        "created_at": now,
        "updated_at": now,
        "complete_at": "",
        "expires_at": "",
        "download_lease_until": "",
    }
    if not save_meta(pid, meta):
        return {"ok": False, "error": "save_failed"}
    try:
        from sentence_reading.llm import evidence_bus as eb

        eb.emit(
            "transfer_pack_create",
            ok=True,
            cache_id=cid,
            details={"pack_id_hash16": _hash16(pid), "declared_bytes": declared},
        )
    except Exception:
        pass
    return {"ok": True, "pack_id": pid, "meta": public_meta(meta)}


def public_meta(meta: dict[str, Any]) -> dict[str, Any]:
    """List/detail fields — never include file bodies."""
    return {
        "pack_id": str(meta.get("pack_id") or ""),
        "cache_id": str(meta.get("cache_id") or ""),
        "title": str(meta.get("title") or ""),
        "status": str(meta.get("status") or ""),
        "bytes": int(meta.get("bytes") or 0),
        "declared_bytes": int(meta.get("declared_bytes") or 0),
        "created_at": str(meta.get("created_at") or ""),
        "complete_at": str(meta.get("complete_at") or ""),
        "expires_at": str(meta.get("expires_at") or ""),
    }


def _part_object(pack_id: str, rel: str, part_index: int) -> str | None:
    from sentence_reading.llm.gcs_sync import personal_object_name

    pid = (pack_id or "").strip()
    safe = safe_rel_path(rel)
    if not _PACK_ID_RE.match(pid) or not safe:
        return None
    # Encode nested rel without '/' inside a single GCS segment.
    enc = safe.replace("/", "__")
    return personal_object_name(
        "transfer_packs", pid, "parts", enc, f"{part_index:05d}"
    )


def personal_parts_prefix(pack_id: str, rel: str) -> str | None:
    from sentence_reading.llm.gcs_sync import personal_object_name

    safe = safe_rel_path(rel)
    pid = (pack_id or "").strip()
    if not safe or not _PACK_ID_RE.match(pid):
        return None
    enc = safe.replace("/", "__")
    base = personal_object_name("transfer_packs", pid, "parts", enc)
    return (base + "/") if base else None


def _write_final_file(pack_id: str, safe: str, data: bytes, meta: dict[str, Any]) -> dict[str, Any]:
    from sentence_reading.llm.gcs_sync import gcs_client_ready, gcs_config, upload_bytes

    declared = int(meta.get("declared_bytes") or 0)
    cur = int(meta.get("bytes") or 0)
    if cur + len(data) > max(declared, transfer_pack_max_bytes()):
        return {"ok": False, "error": "bytes_quota"}
    obj = _file_object(pack_id, safe)
    if not obj:
        return {"ok": False, "error": "bad_object"}
    uid = _current_uid() or ""
    if not assert_deletable_pack_object(obj, uid=uid):
        if "/transfer_packs/" not in obj.replace("\\", "/"):
            return {"ok": False, "error": "refused"}
        if "/papers/" in obj or "/ingest_" in obj:
            return {"ok": False, "error": "refused"}
    ready, _ = gcs_client_ready()
    if not gcs_config().enabled or not ready:
        return {"ok": False, "error": "gcs_not_ready"}
    ok = upload_bytes(obj, data, content_type="application/octet-stream")
    if not ok:
        return {"ok": False, "error": "upload_failed"}
    meta["bytes"] = cur + len(data)
    save_meta(pack_id, meta)
    return {
        "ok": True,
        "path": safe,
        "size": len(data),
        "sha256": _sha256_hex(data),
        "bytes": meta["bytes"],
    }


def put_file(pack_id: str, rel: str, data: bytes) -> dict[str, Any]:
    """Single-shot put (body must be ≤ piece max). Prefer put_file_chunk for large files."""
    if not transfer_pack_enabled():
        return {"ok": False, "error": "disabled"}
    meta = load_meta(pack_id)
    if not meta:
        return {"ok": False, "error": "missing"}
    if str(meta.get("status") or "") != "pending":
        return {"ok": False, "error": "not_pending"}
    safe = safe_rel_path(rel)
    if not safe:
        return {"ok": False, "error": "bad_path"}
    if not data:
        return {"ok": False, "error": "empty"}
    if len(data) > transfer_pack_piece_max():
        return {"ok": False, "error": "need_chunk", "piece_max": transfer_pack_piece_max()}
    return _write_final_file(pack_id, safe, data, meta)


def put_file_chunk(
    pack_id: str,
    rel: str,
    data: bytes,
    *,
    part_index: int,
    part_total: int,
    final_sha256: str = "",
) -> dict[str, Any]:
    """Upload one piece; assemble final object when all parts arrive."""
    from sentence_reading.llm.gcs_sync import (
        delete_prefix,
        download_bytes,
        gcs_client_ready,
        gcs_config,
        upload_bytes,
    )

    if not transfer_pack_enabled():
        return {"ok": False, "error": "disabled"}
    meta = load_meta(pack_id)
    if not meta:
        return {"ok": False, "error": "missing"}
    if str(meta.get("status") or "") != "pending":
        return {"ok": False, "error": "not_pending"}
    safe = safe_rel_path(rel)
    if not safe:
        return {"ok": False, "error": "bad_path"}
    try:
        idx = int(part_index)
        total = int(part_total)
    except (TypeError, ValueError):
        return {"ok": False, "error": "bad_part"}
    if total < 1 or idx < 0 or idx >= total:
        return {"ok": False, "error": "bad_part"}
    if not data or len(data) > transfer_pack_piece_max():
        return {"ok": False, "error": "piece_too_large"}
    if total == 1:
        return _write_final_file(pack_id, safe, data, meta)

    part_obj = _part_object(pack_id, safe, idx)
    if not part_obj or "/transfer_packs/" not in part_obj.replace("\\", "/"):
        return {"ok": False, "error": "bad_object"}
    ready, _ = gcs_client_ready()
    if not gcs_config().enabled or not ready:
        return {"ok": False, "error": "gcs_not_ready"}
    if not upload_bytes(part_obj, data, content_type="application/octet-stream"):
        return {"ok": False, "error": "upload_failed"}

    parts_state = meta.get("parts") if isinstance(meta.get("parts"), dict) else {}
    row = parts_state.get(safe) if isinstance(parts_state.get(safe), dict) else {}
    got = set(int(x) for x in (row.get("received") or []) if str(x).isdigit())
    got.add(idx)
    parts_state[safe] = {
        "total": total,
        "received": sorted(got),
        "final_sha256": (final_sha256 or row.get("final_sha256") or "").strip().lower(),
    }
    meta["parts"] = parts_state
    save_meta(pack_id, meta)

    if len(got) < total:
        return {
            "ok": True,
            "path": safe,
            "part_index": idx,
            "part_total": total,
            "assembled": False,
            "received_n": len(got),
        }

    chunks: list[bytes] = []
    for i in range(total):
        po = _part_object(pack_id, safe, i)
        raw = download_bytes(po) if po else None
        if raw is None:
            return {"ok": False, "error": "part_missing", "part_index": i}
        chunks.append(raw)
    blob = b"".join(chunks)
    want = str(parts_state[safe].get("final_sha256") or "").strip().lower()
    if want and _sha256_hex(blob) != want:
        return {"ok": False, "error": "sha_mismatch", "path": safe}
    out = _write_final_file(pack_id, safe, blob, meta)
    if not out.get("ok"):
        return out
    try:
        prefix = personal_parts_prefix(pack_id, safe)
        if prefix:
            delete_prefix(prefix)
    except Exception:
        pass
    parts_state.pop(safe, None)
    meta["parts"] = parts_state
    save_meta(pack_id, meta)
    out["assembled"] = True
    return out


def _current_uid() -> str:
    try:
        from sentence_reading.llm.auth_google import current_gcs_uid

        return str(current_gcs_uid() or "").strip()
    except Exception:
        return ""


def complete_pack(pack_id: str, files: dict[str, Any]) -> dict[str, Any]:
    """Stamp ready + expires_at; persist manifest of {rel: {size, sha256}}."""
    if not transfer_pack_enabled():
        return {"ok": False, "error": "disabled"}
    meta = load_meta(pack_id)
    if not meta:
        return {"ok": False, "error": "missing"}
    if str(meta.get("status") or "") != "pending":
        return {"ok": False, "error": "not_pending"}
    if not isinstance(files, dict) or not files:
        return {"ok": False, "error": "bad_manifest"}
    if "session.json" not in files:
        return {"ok": False, "error": "no_session"}

    cleaned: dict[str, dict[str, Any]] = {}
    total = 0
    for rel, row in files.items():
        safe = safe_rel_path(str(rel))
        if not safe or not isinstance(row, dict):
            return {"ok": False, "error": "bad_manifest_entry"}
        sha = str(row.get("sha256") or "").strip().lower()
        try:
            size = int(row.get("size") or 0)
        except (TypeError, ValueError):
            size = 0
        if not sha or size <= 0:
            return {"ok": False, "error": "bad_manifest_entry"}
        # Verify object exists and sha matches
        raw = read_file_bytes(pack_id, safe)
        if raw is None or len(raw) != size or _sha256_hex(raw) != sha:
            return {"ok": False, "error": "sha_mismatch", "path": safe}
        cleaned[safe] = {"size": size, "sha256": sha}
        total += size

    if total > transfer_pack_max_bytes():
        return {"ok": False, "error": "bytes_quota"}

    from sentence_reading.llm.gcs_sync import gcs_client_ready, gcs_config, upload_bytes

    man_obj = _manifest_object(pack_id)
    if not man_obj:
        return {"ok": False, "error": "bad_object"}
    ready, _ = gcs_client_ready()
    if not gcs_config().enabled or not ready:
        return {"ok": False, "error": "gcs_not_ready"}
    man = {
        "v": 1,
        "pack_id": pack_id,
        "cache_id": meta.get("cache_id"),
        "files": cleaned,
    }
    upload_bytes(
        man_obj,
        json.dumps(man, ensure_ascii=False, separators=(",", ":")).encode("utf-8"),
        content_type="application/json",
    )

    now = _utc_now()
    meta["status"] = "ready"
    meta["bytes"] = total
    meta["complete_at"] = now.isoformat()
    meta["expires_at"] = (now + timedelta(hours=transfer_pack_ttl_hours())).isoformat()
    save_meta(pack_id, meta)
    try:
        from sentence_reading.llm import evidence_bus as eb

        eb.emit(
            "transfer_pack_complete",
            ok=True,
            cache_id=str(meta.get("cache_id") or ""),
            details={
                "pack_id_hash16": _hash16(pack_id),
                "file_n": len(cleaned),
                "bytes": total,
            },
        )
    except Exception:
        pass
    return {"ok": True, "meta": public_meta(meta), "file_count": len(cleaned)}


def read_file_bytes(pack_id: str, rel: str) -> bytes | None:
    from sentence_reading.llm.gcs_sync import download_bytes

    safe = safe_rel_path(rel)
    obj = _file_object(pack_id, safe or "")
    if not obj or not safe:
        return None
    return download_bytes(obj)


def read_file_slice(
    pack_id: str, rel: str, *, offset: int = 0, limit: int | None = None
) -> dict[str, Any]:
    """Read a byte slice for piece downloads (no full-body preview API)."""
    if not transfer_pack_enabled():
        return {"ok": False, "error": "disabled"}
    raw = read_file_bytes(pack_id, rel)
    if raw is None:
        return {"ok": False, "error": "missing"}
    try:
        off = max(0, int(offset))
    except (TypeError, ValueError):
        off = 0
    piece = transfer_pack_piece_max()
    try:
        lim = piece if limit is None else max(1, min(int(limit), piece))
    except (TypeError, ValueError):
        lim = piece
    if off >= len(raw):
        return {
            "ok": True,
            "data": b"",
            "offset": off,
            "size": 0,
            "total": len(raw),
            "eof": True,
            "sha256": _sha256_hex(raw),
        }
    chunk = raw[off : off + lim]
    return {
        "ok": True,
        "data": chunk,
        "offset": off,
        "size": len(chunk),
        "total": len(raw),
        "eof": off + len(chunk) >= len(raw),
        "sha256": _sha256_hex(raw),
    }


def load_manifest(pack_id: str) -> dict[str, Any] | None:
    from sentence_reading.llm.gcs_sync import download_bytes

    obj = _manifest_object(pack_id)
    if not obj:
        return None
    raw = download_bytes(obj)
    if not raw:
        return None
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def list_public_packs() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for pid in list_pack_ids():
        meta = load_meta(pid)
        if not meta:
            continue
        if str(meta.get("status") or "") not in ("pending", "ready"):
            continue
        out.append(public_meta(meta))
    # newest first
    out.sort(key=lambda m: str(m.get("created_at") or ""), reverse=True)
    return out


def touch_download_lease(pack_id: str) -> dict[str, Any]:
    meta = load_meta(pack_id)
    if not meta:
        return {"ok": False, "error": "missing"}
    if str(meta.get("status") or "") != "ready":
        return {"ok": False, "error": "not_ready"}
    until = _utc_now() + timedelta(seconds=transfer_pack_lease_sec())
    meta["download_lease_until"] = until.isoformat()
    save_meta(pack_id, meta)
    return {"ok": True, "download_lease_until": meta["download_lease_until"]}


def delete_pack(pack_id: str) -> dict[str, Any]:
    from sentence_reading.llm.gcs_sync import delete_prefix, gcs_client_ready, gcs_config

    prefix = _pack_prefix(pack_id)
    if not prefix:
        return {"ok": False, "error": "bad_pack_id"}
    # Safety: prefix must be under transfer_packs
    if "/transfer_packs/" not in prefix.replace("\\", "/"):
        return {"ok": False, "error": "refused"}
    ready, _ = gcs_client_ready()
    if not gcs_config().enabled or not ready:
        return {"ok": False, "error": "gcs_not_ready"}
    stats = delete_prefix(prefix + "/")
    return {"ok": True, "stats": stats}
