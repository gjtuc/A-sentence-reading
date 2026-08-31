"""Server-only ingest upload audit trail (JSONL in GCS + local fallback).

WHY: answer "which uid created this cache_id?" without exposing PII in UI.
INVARIANT:
- uid from session/job only — never body email or paper title.
- No list API for clients; ops read GCS/local file directly.
- Kill switch ASR_UPLOAD_AUDIT_LOG=0.
"""

from __future__ import annotations

import json
import logging
import os
import re
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from sentence_reading.cache.paper_cache import project_root
from sentence_reading.llm.auth_google import sanitize_uid
from sentence_reading.llm.env import load_asr_env
from sentence_reading.llm.error_logs import redact_text

log = logging.getLogger(__name__)

_LOCK = threading.RLock()

_MAX_CACHE_ID = 64
_MAX_FILENAME = 180
_MAX_JOB_ID = 32
_MAX_EVENTS_KEEP = 10_000
_MAX_BODY_BYTES = 4_000_000

_CACHE_ID_RE = re.compile(r"^[A-Za-z0-9._\-]+$")
_JOB_ID_RE = re.compile(r"^job_[A-Za-z0-9._\-]+$")


def upload_audit_enabled() -> bool:
    """Kill switch: ASR_UPLOAD_AUDIT_LOG=0 → off."""
    load_asr_env()
    raw = (os.environ.get("ASR_UPLOAD_AUDIT_LOG") or "1").strip().lower()
    return raw not in ("0", "false", "off", "no")


def local_events_path() -> Path:
    return project_root() / "data" / "upload_audit" / "events.jsonl"


def _gcs_events_object() -> str | None:
    try:
        from sentence_reading.llm.gcs_sync import object_name

        return object_name("upload_audit", "events.jsonl")
    except Exception:  # noqa: BLE001
        return None


def _safe_cache_id(raw: Any) -> str:
    s = str(raw or "").strip()
    if not s or len(s) > _MAX_CACHE_ID:
        return ""
    if not _CACHE_ID_RE.match(s):
        return ""
    return s


def _safe_job_id(raw: Any) -> str:
    s = str(raw or "").strip()
    if not s or len(s) > _MAX_JOB_ID:
        return ""
    if not _JOB_ID_RE.match(s):
        return ""
    return s


def _safe_filename(raw: Any) -> str:
    from sentence_reading.llm.ingest_jobs_gcs import safe_filename

    name = str(raw or "").strip().replace("\\", "/")
    base = name.rsplit("/", 1)[-1]
    cleaned = safe_filename(redact_text(base, limit=_MAX_FILENAME))
    return cleaned or "document.pdf"


def build_event(
    *,
    uid: str,
    cache_id: str,
    filename: str,
    job_id: str = "",
) -> dict[str, Any] | None:
    """Normalize one audit row. Returns None when required fields invalid."""
    safe_uid = sanitize_uid(uid) or ""
    cid = _safe_cache_id(cache_id)
    if not safe_uid or not cid:
        return None
    return {
        "id": f"upl_{uuid.uuid4().hex[:16]}",
        "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "uid": safe_uid,
        "cache_id": cid,
        "filename": _safe_filename(filename),
        "job_id": _safe_job_id(job_id),
    }


def _pull_events_raw() -> bytes:
    obj = _gcs_events_object()
    if obj:
        try:
            from sentence_reading.llm.gcs_sync import download_bytes, gcs_config

            if gcs_config().enabled:
                raw = download_bytes(obj, meter=False)
                if raw is not None:
                    return raw
        except Exception:  # noqa: BLE001
            log.warning("upload_audit gcs pull failed", exc_info=True)
    path = local_events_path()
    if path.is_file():
        return path.read_bytes()
    return b""


def _push_events_raw(raw: bytes) -> None:
    path = local_events_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    obj = _gcs_events_object()
    if not obj:
        return
    try:
        from sentence_reading.llm.gcs_sync import gcs_config, upload_bytes

        if not gcs_config().enabled:
            return
        upload_bytes(obj, raw, content_type="application/x-ndjson; charset=utf-8")
    except Exception:  # noqa: BLE001
        log.warning("upload_audit gcs push failed", exc_info=True)


def _parse_events(raw: bytes) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if not raw:
        return out
    for line in raw.decode("utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict) and obj.get("id"):
            out.append(obj)
    return out


def append_event(event: dict[str, Any]) -> dict[str, Any] | None:
    """Append one audit row; trim old lines. Never raises."""
    if not upload_audit_enabled():
        return None
    try:
        with _LOCK:
            events = _parse_events(_pull_events_raw())
            events.append(event)
            if len(events) > _MAX_EVENTS_KEEP:
                events = events[-_MAX_EVENTS_KEEP:]
            blob = (
                "\n".join(json.dumps(e, ensure_ascii=False) for e in events) + "\n"
            ).encode("utf-8")
            if len(blob) > _MAX_BODY_BYTES:
                events = events[len(events) // 2 :]
                blob = (
                    "\n".join(json.dumps(e, ensure_ascii=False) for e in events) + "\n"
                ).encode("utf-8")
            _push_events_raw(blob)
        return event
    except Exception:  # noqa: BLE001
        log.warning("upload_audit append failed", exc_info=True)
        return None


def record_upload(
    *,
    uid: str,
    cache_id: str,
    filename: str,
    job_id: str = "",
) -> dict[str, Any] | None:
    """Persist one successful ingest→library row. No title/email."""
    event = build_event(uid=uid, cache_id=cache_id, filename=filename, job_id=job_id)
    if event is None:
        return None
    return append_event(event)
