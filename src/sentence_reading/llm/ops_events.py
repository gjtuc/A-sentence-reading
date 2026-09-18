"""design/168a — structured ops events (GCS JSONL + local fallback).

WHY: ingest/open/figures failures must be observable before bug fixes land.
INVARIANT:
- No paper sentence text or PDF bytes in events.
- uid from session/job only — never body user_id.
- emit/append never raises (fail-soft).
- Kill switch ASR_OPS_EVENTS=0.
"""

from __future__ import annotations

import logging
import os
import re
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from sentence_reading.cache.paper_cache import project_root
from sentence_reading.llm.auth_google import sanitize_uid
from sentence_reading.llm.env import load_asr_env
from sentence_reading.llm.error_logs import redact_text
from sentence_reading.llm import jsonl_store as _jl

log = logging.getLogger(__name__)

_LOCK = threading.RLock()
_LAST_ROTATE_MONO: float = 0.0

_MAX_CACHE_ID = 64
_MAX_JOB_ID = 32
_MAX_TRACE_ID = 40
_MAX_SESSION_ID = 40
_MAX_CONTENT_HASH = 64
_MAX_MSG = 240
_MAX_STAGE = 40
_MAX_EVENTS_KEEP = 10_000
_MAX_BODY_BYTES = 4_000_000
_DEFAULT_RETENTION_DAYS = 7
_ROTATE_MIN_INTERVAL_SEC = 6 * 3600

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
        # design/169m — lease / sweeper causality
        "lease_heartbeat",
        "sweep_decision",
        # design/179
        "sweep_kill_decision",
        # design/286
        "false_worker_lost_guard",
        "false_worker_lost_suspect",
        "post_terminal_ingest_progress",
    }
)


def ops_events_enabled() -> bool:
    """Kill switch: ASR_OPS_EVENTS=0 → off."""
    load_asr_env()
    raw = (os.environ.get("ASR_OPS_EVENTS") or "1").strip().lower()
    return raw not in ("0", "false", "off", "no")


def retention_days() -> int:
    """design/169g phase 6 — ops keep window (default same as evidence 7d)."""
    load_asr_env()
    raw = (
        os.environ.get("ASR_OPS_EVENTS_RETENTION_DAYS")
        or str(_DEFAULT_RETENTION_DAYS)
    ).strip()
    try:
        n = int(raw)
    except ValueError:
        n = _DEFAULT_RETENTION_DAYS
    return max(0, min(n, 365))


def parse_event_ts(raw: Any) -> datetime | None:
    return _jl.parse_event_ts(raw)


def filter_retained(
    events: list[dict[str, Any]],
    *,
    keep_days: int | None = None,
    now: datetime | None = None,
) -> tuple[list[dict[str, Any]], int]:
    days = _DEFAULT_RETENTION_DAYS if keep_days is None else int(keep_days)
    return _jl.filter_retained(events, keep_days=days, now=now)


def new_trace_id() -> str:
    return f"tr_{uuid.uuid4().hex[:16]}"


def local_events_path() -> Path:
    return project_root() / "data" / "ops_events" / "events.jsonl"


def _gcs_events_object() -> str | None:
    return _jl.gcs_object_name("ops_events")


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
    return _jl.pull_events_raw(
        local_path=local_events_path(),
        gcs_object=_gcs_events_object(),
        logger=log,
        label="ops_events",
    )


def _push_events_raw(raw: bytes) -> None:
    _jl.push_events_raw(
        raw=raw,
        local_path=local_events_path(),
        gcs_object=_gcs_events_object(),
        logger=log,
        label="ops_events",
    )


def _parse_events(raw: bytes) -> list[dict[str, Any]]:
    return _jl.parse_jsonl_events(raw)


def append_event(event: dict[str, Any]) -> dict[str, Any] | None:
    """Append one ops row; trim by age + count. Never raises."""
    if not ops_events_enabled():
        return None
    try:
        with _LOCK:
            events = _parse_events(_pull_events_raw())
            events.append(event)
            events, _dropped = filter_retained(events, keep_days=retention_days())
            events = _jl.trim_jsonl_events(
                events,
                max_keep=_MAX_EVENTS_KEEP,
                max_body_bytes=_MAX_BODY_BYTES,
            )
            _push_events_raw(_jl.encode_jsonl_events(events))
        return event
    except Exception:  # noqa: BLE001
        log.warning("ops_events append failed", exc_info=True)
        return None


def rotate_events(
    *,
    keep_days: int | None = None,
    force: bool = False,
) -> dict[str, Any]:
    """design/169g phase 6 — drop ops rows older than keep_days. Never raises."""
    global _LAST_ROTATE_MONO
    out: dict[str, Any] = {
        "ok": False,
        "before": 0,
        "after": 0,
        "dropped": 0,
        "skipped": 0,
        "keep_days": retention_days() if keep_days is None else int(keep_days),
    }
    if not ops_events_enabled():
        out["skipped"] = 1
        return out
    now_m = time.monotonic()
    if (
        not force
        and _LAST_ROTATE_MONO > 0
        and (now_m - _LAST_ROTATE_MONO) < _ROTATE_MIN_INTERVAL_SEC
    ):
        out["skipped"] = 1
        out["ok"] = True
        return out
    try:
        with _LOCK:
            events = _parse_events(_pull_events_raw())
            before = len(events)
            kept, dropped = filter_retained(events, keep_days=out["keep_days"])
            if len(kept) > _MAX_EVENTS_KEEP:
                dropped += len(kept) - _MAX_EVENTS_KEEP
                kept = kept[-_MAX_EVENTS_KEEP:]
            if dropped == 0 and not force:
                _LAST_ROTATE_MONO = now_m
                out.update(ok=True, before=before, after=before, dropped=0)
                return out
            _push_events_raw(_jl.encode_jsonl_events(kept))
            _LAST_ROTATE_MONO = now_m
            out.update(ok=True, before=before, after=len(kept), dropped=dropped)
            return out
    except Exception:  # noqa: BLE001
        log.warning("ops_events rotate failed", exc_info=True)
        return out


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
