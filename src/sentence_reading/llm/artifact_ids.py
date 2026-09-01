"""
design/169i — artifact identity helpers (hash/locator; no paper text).
"""

from __future__ import annotations

import hashlib
import re
import secrets
import uuid
from pathlib import Path
from typing import Any

_CACHE_ID_RE = re.compile(r"^[a-zA-Z0-9]{8,32}$")
_FILE_SAFE_RE = re.compile(r"^[a-zA-Z0-9._-]{1,128}$")

ARTIFACT_KINDS = frozenset(
    {
        "session_json",
        "figure_png",
        "source_pdf",
        "source_docx",
        "index_json",
        "voice_blob",
        "notes_store",
        "upload_blob",
        "job_state",
    }
)

ACTIVITIES = frozenset(
    {
        "client_upload",
        "ingest_store",
        "vision_write_session",
        "vision_write_figure",
        "gcs_upload_session",
        "gcs_upload_figure",
        "gcs_download_session",
        "gcs_download_figure",
        "merge_session",
        "session_patch_ko",
        "translate_save",
        "cache_open",
        "figure_window",
        "notes_upsert",
        "voice_put",
        "paper_delete_local",
        "paper_delete_gcs",
        "index_update",
        "local_write_session",
    }
)


def hash16(data: bytes | str | None) -> str:
    """SHA-256 hex truncated to 16 chars. Empty input → \"\"."""
    if data is None:
        return ""
    if isinstance(data, str):
        raw = data.encode("utf-8")
    else:
        raw = data
    if not raw:
        return ""
    return hashlib.sha256(raw).hexdigest()[:16]


def hash16_file(path: Path | str) -> tuple[str, int]:
    """Return (hash16, bytes_n) for a file; (\"\", 0) on failure."""
    try:
        p = Path(path)
        raw = p.read_bytes()
    except OSError:
        return "", 0
    if not raw:
        return "", 0
    return hash16(raw), len(raw)


def _safe_cache_id(cache_id: str) -> str:
    cid = str(cache_id or "").strip()
    if not _CACHE_ID_RE.match(cid):
        return ""
    return cid


def _safe_file(name: str) -> str:
    n = str(name or "").strip().replace("\\", "/").split("/")[-1]
    if not _FILE_SAFE_RE.match(n):
        return ""
    return n


def locator_local_session(cache_id: str) -> str:
    cid = _safe_cache_id(cache_id)
    return f"local:papers/{cid}/session.json" if cid else ""


def locator_gcs_session(cache_id: str) -> str:
    cid = _safe_cache_id(cache_id)
    return f"gcs:papers/{cid}/session.json" if cid else ""


def locator_local_figure(cache_id: str, file_name: str) -> str:
    cid = _safe_cache_id(cache_id)
    fn = _safe_file(file_name)
    if not cid or not fn:
        return ""
    return f"local:papers/{cid}/figures/{fn}"


def locator_gcs_figure(cache_id: str, file_name: str) -> str:
    cid = _safe_cache_id(cache_id)
    fn = _safe_file(file_name)
    if not cid or not fn:
        return ""
    return f"gcs:papers/{cid}/figures/{fn}"


def locator_mobile_open(cache_id: str) -> str:
    cid = _safe_cache_id(cache_id)
    return f"mobile:open/{cid}" if cid else ""


def artifact_id_session(cache_id: str, gen: int) -> str:
    cid = _safe_cache_id(cache_id)
    g = max(0, int(gen))
    return f"art_sess_{cid}_{g}" if cid else ""


def new_transfer_id() -> str:
    return f"xf_{secrets.token_hex(6)}"


def stage_activity(raw: str) -> str:
    s = str(raw or "").strip().lower().replace("-", "_").replace(" ", "_")
    s = re.sub(r"[^a-z0-9_]", "", s)[:64]
    if s in ACTIVITIES:
        return s
    if s and re.match(r"^[a-z]", s):
        return s
    return "unknown"


def emit_artifact_observe(
    *,
    locator: str,
    artifact_kind: str,
    content_hash: str = "",
    bytes_n: int | None = None,
    gen: int | None = None,
    role: str = "read",
    activity: str = "",
    cache_id: str = "",
    job_id: str = "",
    owner_uid: str = "",
    trace_id: str = "",
    ok: bool = True,
    extra: dict[str, Any] | None = None,
) -> None:
    """design/169i — read-side observe. Never raises."""
    try:
        from sentence_reading.llm import evidence_bus as eb

        kind = str(artifact_kind or "").strip()
        if kind not in ARTIFACT_KINDS:
            kind = "session_json"
        loc = str(locator or "")[:160]
        if not loc:
            return
        details: dict[str, Any] = {
            "locator": loc,
            "artifact_kind": kind,
            "role": "read" if role != "write" else "write",
        }
        h = str(content_hash or "")[:16]
        if h:
            details["content_hash"] = h
        if bytes_n is not None:
            details["bytes_n"] = int(bytes_n)
        if gen is not None:
            details["gen"] = int(gen)
        act = stage_activity(activity) if activity else ""
        if act and act != "unknown":
            details["activity"] = act
        if extra:
            for k, v in extra.items():
                sk = str(k or "").strip()
                if sk and sk not in details:
                    details[sk] = v
        eb.emit(
            "artifact_observe",
            severity="boundary",
            trace_id=trace_id,
            job_id=job_id,
            cache_id=cache_id,
            owner_uid=owner_uid,
            stage="artifact",
            details=details,
            ok=ok,
            code="artifact_observe",
        )
    except Exception:  # noqa: BLE001
        pass


def emit_artifact_transfer(
    *,
    activity: str,
    from_locator: str,
    to_locator: str,
    artifact_kind: str = "session_json",
    content_hash: str = "",
    bytes_n: int | None = None,
    gen: int | None = None,
    agent: str = "cloud_run",
    elapsed_ms: int | None = None,
    ok: bool = True,
    cache_id: str = "",
    job_id: str = "",
    owner_uid: str = "",
    trace_id: str = "",
    hash_mismatch: bool = False,
    extra: dict[str, Any] | None = None,
) -> str:
    """design/169i — source→sink transfer. Returns transfer_id or \"\"."""
    tid = new_transfer_id()
    try:
        from sentence_reading.llm import evidence_bus as eb

        kind = str(artifact_kind or "").strip()
        if kind not in ARTIFACT_KINDS:
            kind = "session_json"
        fl = str(from_locator or "")[:160]
        tl = str(to_locator or "")[:160]
        if not fl and not tl:
            return ""
        details: dict[str, Any] = {
            "transfer_id": tid,
            "activity": stage_activity(activity),
            "from_locator": fl or "unknown",
            "to_locator": tl or "unknown",
            "artifact_kind": kind,
            "agent": str(agent or "cloud_run")[:32],
        }
        h = str(content_hash or "")[:16]
        if h:
            details["content_hash"] = h
        if bytes_n is not None:
            details["bytes_n"] = int(bytes_n)
        if gen is not None:
            details["gen"] = int(gen)
        if elapsed_ms is not None:
            details["elapsed_ms"] = int(elapsed_ms)
        if hash_mismatch:
            details["hash_mismatch"] = 1
        if extra:
            for k, v in extra.items():
                sk = str(k or "").strip()
                if sk and sk not in details:
                    details[sk] = v
        eb.emit(
            "artifact_transfer",
            severity="error" if (not ok or hash_mismatch) else "boundary",
            trace_id=trace_id,
            job_id=job_id,
            cache_id=cache_id,
            owner_uid=owner_uid,
            stage="artifact",
            details=details,
            ok=bool(ok) and not hash_mismatch,
            code="artifact_transfer",
        )
        return tid
    except Exception:  # noqa: BLE001
        return ""


def emit_artifact_derive(
    *,
    activity: str,
    child_id: str,
    parent_ids: list[str] | None = None,
    gen: int | None = None,
    content_hash: str = "",
    cache_id: str = "",
    job_id: str = "",
    owner_uid: str = "",
    trace_id: str = "",
    ok: bool = True,
) -> None:
    """design/169i — new artifact generation edge. Never raises."""
    try:
        from sentence_reading.llm import evidence_bus as eb

        cid_art = str(child_id or "")[:80]
        if not cid_art:
            return
        details: dict[str, Any] = {
            "child_id": cid_art,
            "activity": stage_activity(activity),
        }
        parents = [str(p)[:80] for p in (parent_ids or []) if p][:8]
        if parents:
            details["parent_ids"] = parents
        if gen is not None:
            details["gen"] = int(gen)
        h = str(content_hash or "")[:16]
        if h:
            details["content_hash"] = h
        eb.emit(
            "artifact_derive",
            severity="boundary",
            trace_id=trace_id,
            job_id=job_id,
            cache_id=cache_id,
            owner_uid=owner_uid,
            stage="artifact",
            details=details,
            ok=ok,
            code="artifact_derive",
        )
    except Exception:  # noqa: BLE001
        pass


def emit_artifact_invalidate(
    *,
    locator: str,
    artifact_kind: str = "session_json",
    activity: str = "paper_delete_gcs",
    ok: bool = True,
    cache_id: str = "",
    job_id: str = "",
    owner_uid: str = "",
    trace_id: str = "",
    object_n: int | None = None,
    figure_n: int | None = None,
    extra: dict[str, Any] | None = None,
) -> None:
    """design/169i — delete/tombstone. Never raises."""
    try:
        from sentence_reading.llm import evidence_bus as eb

        loc = str(locator or "")[:160]
        kind = str(artifact_kind or "").strip()
        if kind not in ARTIFACT_KINDS:
            kind = "session_json"
        details: dict[str, Any] = {
            "locator": loc or "unknown",
            "artifact_kind": kind,
            "activity": stage_activity(activity),
        }
        if object_n is not None:
            details["object_n"] = int(object_n)
        if figure_n is not None:
            details["figure_n"] = int(figure_n)
        if extra:
            for k, v in extra.items():
                sk = str(k or "").strip()
                if sk and sk not in details:
                    details[sk] = v
        eb.emit(
            "artifact_invalidate",
            severity="boundary",
            trace_id=trace_id,
            job_id=job_id,
            cache_id=cache_id,
            owner_uid=owner_uid,
            stage="artifact",
            details=details,
            ok=ok,
            code="artifact_invalidate",
        )
    except Exception:  # noqa: BLE001
        pass


def next_session_gen(prior_meta: dict[str, Any] | None) -> int:
    """Bump artifact_gen from prior session meta (default 1)."""
    if not isinstance(prior_meta, dict):
        return 1
    try:
        prev = int(prior_meta.get("artifact_gen") or 0)
    except (TypeError, ValueError):
        prev = 0
    return max(1, prev + 1)
