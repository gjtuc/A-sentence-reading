"""design/168a — structured ops events (GCS JSONL + local fallback).

WHY: ingest/open/figures failures must be observable before bug fixes land.
INVARIANT:
- No paper sentence text or PDF bytes in events.
- uid from session/job only — never body user_id.
- emit/append never raises (fail-soft).
- Kill switch ASR_OPS_EVENTS=0.
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
_MAX_JOB_ID = 32
_MAX_TRACE_ID = 40
_MAX_SESSION_ID = 40
_MAX_CONTENT_HASH = 64
_MAX_MSG = 240
_MAX_STAGE = 40
_MAX_EVENTS_KEEP = 10_000
_MAX_BODY_BYTES = 4_000_000

_CACHE_ID_RE = re.compile(r"^[A-Za-z0-9._\-]+$")
_JOB_ID_RE = re.compile(r"^job_[a-f0-9]{12}$")
_TRACE_ID_RE = re.compile(r"^tr_[a-f0-9]{16,32}$")
_SESSION_ID_RE = re.compile(r"^ses_[a-f0-9]{12}$")

_ALLOWED_KINDS = frozenset(
    {
        "ingest_started",
        "ingest_phase_transition",
        "ingest_gcs_push",
        "ingest_gcs_skip",
        "ingest_terminal",
        # design/168b
        "consistency_violation",
        "merge_session_richer",
        # design/168d — figure / translate silent-path observability
        "figure_window_empty",
        "figure_data_url_miss",
        "figure_blob_miss",
        "open_translate_backfill_fail",
        # design/168e — stall / sweeper / reclaim
        "translate_stalled",
        "translate_section_tick",
        "worker_lost",
        "reclaim_attempt",
    }
)


def ops_events_enabled() -> bool:
    """Kill switch: ASR_OPS_EVENTS=0 → off."""
    load_asr_env()
    raw = (os.environ.get("ASR_OPS_EVENTS") or "1").strip().lower()
    return raw not in ("0", "false", "off", "no")


def new_trace_id() -> str:
    return f"tr_{uuid.uuid4().hex[:16]}"


def local_events_path() -> Path:
    return project_root() / "data" / "ops_events" / "events.jsonl"


def _gcs_events_object() -> str | None:
    try:
        from sentence_reading.llm.gcs_sync import object_name

        return object_name("ops_events", "events.jsonl")
    except Exception:  # noqa: BLE001
        return None


def _deploy_git_sha() -> str | None:
    raw = (os.environ.get("ASR_DEPLOY_GIT_SHA") or "").strip()
    return raw[:40] if raw else None


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


def _safe_trace_id(raw: Any) -> str:
    s = str(raw or "").strip()
    if not s or len(s) > _MAX_TRACE_ID:
        return ""
    if not _TRACE_ID_RE.match(s):
        return ""
    return s


def _safe_session_id(raw: Any) -> str:
    s = str(raw or "").strip()
    if not s or len(s) > _MAX_SESSION_ID:
        return ""
    if not _SESSION_ID_RE.match(s):
        return ""
    return s


def _safe_content_hash(raw: Any) -> str:
    s = str(raw or "").strip()
    if not s or len(s) > _MAX_CONTENT_HASH:
        return ""
    if not re.match(r"^[a-f0-9]{64}$", s):
        return ""
    return s


def _safe_details(raw: Any) -> dict[str, Any]:
    """Numeric/enum-only details — no free-text paper content."""
    if not isinstance(raw, dict):
        return {}
    out: dict[str, Any] = {}
    for key, val in raw.items():
        k = str(key or "").strip()[:40]
        if not k or not re.match(r"^[a-z][a-z0-9_]{0,39}$", k):
            continue
        if isinstance(val, bool):
            out[k] = val
        elif isinstance(val, int):
            out[k] = max(-1_000_000_000, min(val, 1_000_000_000))
        elif isinstance(val, float):
            out[k] = round(max(-1e12, min(val, 1e12)), 3)
        elif isinstance(val, str):
            s = val.strip()[:64]
            if s and re.match(r"^[a-z][a-z0-9_]{0,63}$", s):
                out[k] = s
    return out


def build_event(
    kind: str,
    *,
    trace_id: str = "",
    job_id: str = "",
    cache_id: str = "",
    session_id: str = "",
    owner_uid: str = "",
    content_hash: str = "",
    stage: str = "",
    percent: int | None = None,
    message: str = "",
    details: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Normalize one ops row. Returns None when kind is not allowlisted."""
    k = str(kind or "").strip().lower()[:64]
    if k not in _ALLOWED_KINDS:
        return None
    ev: dict[str, Any] = {
        "id": f"ops_{uuid.uuid4().hex[:16]}",
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "kind": k,
        "source": "server",
    }
    tid = _safe_trace_id(trace_id)
    if tid:
        ev["trace_id"] = tid
    jid = _safe_job_id(job_id)
    if jid:
        ev["job_id"] = jid
    cid = _safe_cache_id(cache_id)
    if cid:
        ev["cache_id"] = cid
    sid = _safe_session_id(session_id)
    if sid:
        ev["session_id"] = sid
    uid = sanitize_uid(owner_uid) or ""
    if uid:
        ev["owner_uid"] = uid
    ch = _safe_content_hash(content_hash)
    if ch:
        ev["content_hash"] = ch
    sha = _deploy_git_sha()
    if sha:
        ev["deploy_git_sha"] = sha
    st = redact_text(str(stage or ""), limit=_MAX_STAGE).strip()
    if st:
        ev["stage"] = st
    if percent is not None:
        try:
            ev["percent"] = max(0, min(int(percent), 100))
        except (TypeError, ValueError):
            pass
    msg = redact_text(str(message or ""), limit=_MAX_MSG).strip()
    if msg:
        ev["message"] = msg
    det = _safe_details(details)
    if det:
        ev["details"] = det
    return ev


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
            log.warning("ops_events gcs pull failed", exc_info=True)
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
        log.warning("ops_events gcs push failed", exc_info=True)


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
    """Append one ops row; trim old lines. Never raises."""
    if not ops_events_enabled():
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
        log.warning("ops_events append failed", exc_info=True)
        return None


def emit(
    kind: str,
    *,
    trace_id: str = "",
    job_id: str = "",
    cache_id: str = "",
    session_id: str = "",
    owner_uid: str = "",
    content_hash: str = "",
    stage: str = "",
    percent: int | None = None,
    message: str = "",
    details: dict[str, Any] | None = None,
) -> None:
    """Fire-and-forget ops event. Never raises."""
    if not ops_events_enabled():
        return
    try:
        event = build_event(
            kind,
            trace_id=trace_id,
            job_id=job_id,
            cache_id=cache_id,
            session_id=session_id,
            owner_uid=owner_uid,
            content_hash=content_hash,
            stage=stage,
            percent=percent,
            message=message,
            details=details,
        )
        if event is None:
            return
        append_event(event)
    except Exception:  # noqa: BLE001
        log.warning("ops_events emit failed kind=%s", kind, exc_info=True)


def list_events(*, limit: int = 50) -> list[dict[str, Any]]:
    """Newest-first ops rows (tests / future admin)."""
    lim = max(1, min(int(limit or 50), 200))
    with _LOCK:
        events = _parse_events(_pull_events_raw())
    events.reverse()
    return events[:lim]
