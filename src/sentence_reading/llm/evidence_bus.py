"""design/169 — Agent Evidence Bus (GCS JSONL, no admin/user UI).

WHY: global breadcrumbs for error improvement; agents pull via script.
INVARIANT:
- No paper sentence text / PDF bytes / tokens.
- owner_uid from session/server only — never trust body user_id.
- emit/append never raises (fail-soft).
- No GET list API in this module's contract.
- Kill ASR_EVIDENCE_BUS=0.
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
from sentence_reading.llm.evidence_kinds import ALLOWED_KINDS

log = logging.getLogger(__name__)

_LOCK = threading.RLock()
_RATE_MEM: dict[str, list[float]] = {}

_MAX_CACHE_ID = 64
_MAX_JOB_ID = 32
_MAX_TRACE_ID = 40
_MAX_SESSION_ID = 40
_MAX_CONTENT_HASH = 64
_MAX_MSG = 200
_MAX_STAGE = 40
_MAX_ROUTE = 120
_MAX_CODE = 64
_MAX_EVENTS_KEEP = 20_000
_MAX_BODY_BYTES = 6_000_000
_MAX_BATCH = 50
_RATE_MAX = 60
_RATE_WINDOW_SEC = 60

_CACHE_ID_RE = re.compile(r"^[A-Za-z0-9._\-]+$")
_JOB_ID_RE = re.compile(r"^job_[a-f0-9]{12}$")
_TRACE_ID_RE = re.compile(r"^tr_[a-f0-9]{16,32}$")
_SESSION_ID_RE = re.compile(r"^ses_[a-f0-9]{12}$")
_SOURCE_OK = frozenset({"mobile", "web", "server", "agent"})
_SEVERITY_OK = frozenset(
    {"lifecycle", "decision", "boundary", "error", "consistency", "sample"}
)


def evidence_bus_enabled() -> bool:
    """Kill switch: ASR_EVIDENCE_BUS=0 → off."""
    load_asr_env()
    raw = (os.environ.get("ASR_EVIDENCE_BUS") or "1").strip().lower()
    return raw not in ("0", "false", "off", "no")


def local_events_path() -> Path:
    return project_root() / "data" / "evidence" / "events.jsonl"


def _gcs_events_object() -> str | None:
    try:
        from sentence_reading.llm.gcs_sync import object_name

        return object_name("evidence", "events.jsonl")
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
    s = str(raw or "").strip().lower()
    if not s or len(s) > _MAX_CONTENT_HASH:
        return ""
    if not re.match(r"^[a-f0-9]{64}$", s):
        return ""
    return s


def _safe_details(raw: Any) -> dict[str, Any]:
    """Numeric/enum/snake details — no free-text paper content."""
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
    source: str = "server",
    severity: str = "boundary",
    trace_id: str = "",
    parent_trace_id: str = "",
    job_id: str = "",
    cache_id: str = "",
    session_id: str = "",
    owner_uid: str = "",
    content_hash: str = "",
    stage: str = "",
    percent: int | None = None,
    message: str = "",
    details: dict[str, Any] | None = None,
    route: str = "",
    http_status: int | None = None,
    ok: bool | None = None,
    code: str = "",
    app_version: str = "",
    pipeline_version: str = "",
) -> dict[str, Any] | None:
    """Normalize one evidence row. Returns None when kind not allowlisted."""
    k = str(kind or "").strip().lower()[:64]
    if k not in ALLOWED_KINDS:
        return None
    src = str(source or "server").strip().lower()
    if src not in _SOURCE_OK:
        src = "server"
    sev = str(severity or "boundary").strip().lower()
    if sev not in _SEVERITY_OK:
        sev = "boundary"
    ev: dict[str, Any] = {
        "id": f"ev_{uuid.uuid4().hex[:16]}",
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "schema_v": 1,
        "source": src,
        "kind": k,
        "severity": sev,
    }
    tid = _safe_trace_id(trace_id)
    if tid:
        ev["trace_id"] = tid
    ptid = _safe_trace_id(parent_trace_id)
    if ptid:
        ev["parent_trace_id"] = ptid
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
    rt = redact_text(str(route or ""), limit=_MAX_ROUTE).strip()
    if rt:
        ev["route"] = rt
    if http_status is not None:
        try:
            hs = int(http_status)
            if 100 <= hs <= 599:
                ev["http_status"] = hs
        except (TypeError, ValueError):
            pass
    if ok is not None:
        ev["ok"] = bool(ok)
    code_s = str(code or "").strip().lower()[:_MAX_CODE]
    if code_s and re.match(r"^[a-z][a-z0-9_]{0,63}$", code_s):
        ev["code"] = code_s
    av = redact_text(str(app_version or ""), limit=40).strip()
    if av:
        ev["app_version"] = av
    pv = redact_text(str(pipeline_version or ""), limit=32).strip()
    if pv:
        ev["pipeline_version"] = pv
    det = _safe_details(details)
    if det:
        ev["details"] = det
    return ev


def check_ingest_rate(uid: str) -> bool:
    """Return True if this uid may accept more events this minute."""
    key = sanitize_uid(uid) or "anon"
    now = time.time()
    with _LOCK:
        arr = [t for t in _RATE_MEM.get(key, []) if now - t < _RATE_WINDOW_SEC]
        if len(arr) >= _RATE_MAX:
            _RATE_MEM[key] = arr
            return False
        arr.append(now)
        _RATE_MEM[key] = arr
        return True


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
            log.warning("evidence_bus gcs pull failed", exc_info=True)
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
        log.warning("evidence_bus gcs push failed", exc_info=True)


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


def append_events(events: list[dict[str, Any]]) -> int:
    """Append many rows; return count written. Never raises."""
    if not evidence_bus_enabled() or not events:
        return 0
    try:
        with _LOCK:
            existing = _parse_events(_pull_events_raw())
            existing.extend(events)
            if len(existing) > _MAX_EVENTS_KEEP:
                existing = existing[-_MAX_EVENTS_KEEP:]
            blob = (
                "\n".join(json.dumps(e, ensure_ascii=False) for e in existing) + "\n"
            ).encode("utf-8")
            if len(blob) > _MAX_BODY_BYTES:
                existing = existing[len(existing) // 2 :]
                blob = (
                    "\n".join(json.dumps(e, ensure_ascii=False) for e in existing)
                    + "\n"
                ).encode("utf-8")
            _push_events_raw(blob)
        return len(events)
    except Exception:  # noqa: BLE001
        log.warning("evidence_bus append failed", exc_info=True)
        return 0


def ingest_client_batch(
    raw_events: list[Any],
    *,
    owner_uid: str,
) -> tuple[int, int]:
    """Normalize client batch; stamp session uid. Returns (accepted, dropped)."""
    if not evidence_bus_enabled():
        return 0, len(raw_events) if isinstance(raw_events, list) else 0
    if not isinstance(raw_events, list):
        return 0, 0
    uid = sanitize_uid(owner_uid) or ""
    accepted_rows: list[dict[str, Any]] = []
    dropped = 0
    for item in raw_events[:_MAX_BATCH]:
        if not isinstance(item, dict):
            dropped += 1
            continue
        if not check_ingest_rate(uid or "anon"):
            dropped += 1
            continue
        # WHY: never trust client owner_uid / uid fields.
        ev = build_event(
            str(item.get("kind") or ""),
            source=str(item.get("source") or "mobile"),
            severity=str(item.get("severity") or "boundary"),
            trace_id=str(item.get("trace_id") or ""),
            parent_trace_id=str(item.get("parent_trace_id") or ""),
            job_id=str(item.get("job_id") or ""),
            cache_id=str(item.get("cache_id") or ""),
            session_id=str(item.get("session_id") or ""),
            owner_uid=uid,
            content_hash=str(item.get("content_hash") or ""),
            stage=str(item.get("stage") or ""),
            percent=item.get("percent") if isinstance(item.get("percent"), int) else None,
            message=str(item.get("message") or ""),
            details=item.get("details") if isinstance(item.get("details"), dict) else None,
            route=str(item.get("route") or ""),
            http_status=item.get("http_status")
            if isinstance(item.get("http_status"), int)
            else None,
            ok=item.get("ok") if isinstance(item.get("ok"), bool) else None,
            code=str(item.get("code") or ""),
            app_version=str(item.get("app_version") or ""),
            pipeline_version=str(item.get("pipeline_version") or ""),
        )
        if ev is None:
            dropped += 1
            continue
        accepted_rows.append(ev)
    written = append_events(accepted_rows)
    # EDGE: append partial failure → count unwritten as dropped.
    if written < len(accepted_rows):
        dropped += len(accepted_rows) - written
        return written, dropped
    return written, dropped


def emit(
    kind: str,
    *,
    source: str = "server",
    severity: str = "boundary",
    trace_id: str = "",
    parent_trace_id: str = "",
    job_id: str = "",
    cache_id: str = "",
    session_id: str = "",
    owner_uid: str = "",
    content_hash: str = "",
    stage: str = "",
    percent: int | None = None,
    message: str = "",
    details: dict[str, Any] | None = None,
    route: str = "",
    http_status: int | None = None,
    ok: bool | None = None,
    code: str = "",
    app_version: str = "",
    pipeline_version: str = "",
) -> None:
    """Fire-and-forget server evidence. Never raises."""
    if not evidence_bus_enabled():
        return
    try:
        event = build_event(
            kind,
            source=source,
            severity=severity,
            trace_id=trace_id,
            parent_trace_id=parent_trace_id,
            job_id=job_id,
            cache_id=cache_id,
            session_id=session_id,
            owner_uid=owner_uid,
            content_hash=content_hash,
            stage=stage,
            percent=percent,
            message=message,
            details=details,
            route=route,
            http_status=http_status,
            ok=ok,
            code=code,
            app_version=app_version,
            pipeline_version=pipeline_version,
        )
        if event is None:
            return
        append_events([event])
    except Exception:  # noqa: BLE001
        log.warning("evidence_bus emit failed kind=%s", kind, exc_info=True)


def list_events(*, limit: int = 50) -> list[dict[str, Any]]:
    """Newest-first (tests / agent scripts only — no HTTP)."""
    lim = max(1, min(int(limit or 50), 500))
    with _LOCK:
        events = _parse_events(_pull_events_raw())
    events.reverse()
    return events[:lim]
