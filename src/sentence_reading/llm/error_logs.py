"""design/130 — cloud error logs (shared GCS + local fallback).

WHY: multi-user cloud — admin must see others' failures without USB.
INVARIANT:
- Reporter identity from session only (never body user_id).
- Admin-only list/badge/seen.
- Secrets redacted before persist.
- Kill ASR_CLOUD_ERROR_LOGS=0.
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
from sentence_reading.llm import jsonl_store as _jl

log = logging.getLogger(__name__)

_LOCK = threading.RLock()

# Sliding report rate: per uid.
_REPORT_MEM: dict[str, list[float]] = {}

_MAX_MSG = 2_000
_MAX_STACK = 4_000
_MAX_TITLE = 240
_MAX_CACHE_ID = 64
_MAX_EVENTS_KEEP = 2_000
_MAX_BODY_BYTES = 4_000_000
# Admin triage rows keep an email. Drop them after 3 days.
_DEFAULT_RETENTION_DAYS = 3
_ROTATE_MIN_INTERVAL_SEC = 6 * 3600
_LAST_ROTATE_MONO = 0.0

# WHY: catch common secret shapes in free-text message/stack.
_SECRET_PATTERNS: list[re.Pattern[str]] = [
    # WHY bearer first: "Authorization: Bearer tok" must wipe the token, not only "Bearer".
    re.compile(r"(?i)\b(bearer\s+)([A-Za-z0-9\-._~+/]+=*)"),
    re.compile(r"(?i)(authorization\s*[:=]\s*)(\S+)"),
    re.compile(r"(?i)(api[_-]?key\s*[:=]\s*)(\S+)"),
    re.compile(r"(?i)(password\s*[:=]\s*)(\S+)"),
    re.compile(r"(?i)(cookie\s*[:=]\s*)([^\s;]+)"),
    re.compile(r"(?i)(session(_token)?\s*[:=]\s*)(\S+)"),
    re.compile(r"(?i)(asr_session=)([^\s;]+)"),
]


def cloud_error_logs_enabled() -> bool:
    """Kill switch: ASR_CLOUD_ERROR_LOGS=0 → off."""
    load_asr_env()
    raw = (os.environ.get("ASR_CLOUD_ERROR_LOGS") or "1").strip().lower()
    return raw not in ("0", "false", "off", "no")


def retention_days() -> int:
    """Keep admin error rows this many days. 0 turns the age filter off."""
    load_asr_env()
    raw = (os.environ.get("ASR_ERROR_LOG_RETENTION_DAYS") or str(_DEFAULT_RETENTION_DAYS)).strip()
    try:
        n = int(raw)
    except ValueError:
        n = _DEFAULT_RETENTION_DAYS
    return max(0, min(n, 365))


def _env_int(name: str, default: int, *, lo: int, hi: int) -> int:
    load_asr_env()
    raw = (os.environ.get(name) or "").strip()
    if not raw:
        return default
    try:
        n = int(raw)
    except ValueError:
        return default
    if n < lo:
        return default
    return min(n, hi)


def report_rate_limits() -> tuple[int, int]:
    """(max_count, window_sec) for POST /api/errors/report."""
    return (
        _env_int("ASR_ERROR_REPORT_MAX", 30, lo=1, hi=500),
        _env_int("ASR_ERROR_REPORT_WINDOW_SEC", 600, lo=30, hi=86_400),
    )


def local_events_path() -> Path:
    return project_root() / "data" / "error_logs" / "events.jsonl"


def local_seen_path() -> Path:
    return project_root() / "data" / "error_logs" / "admin_seen.json"


def _gcs_events_object() -> str | None:
    return _jl.gcs_object_name("error_logs")


def _gcs_seen_object() -> str | None:
    try:
        from sentence_reading.llm.gcs_sync import object_name

        return object_name("error_logs", "admin_seen.json")
    except Exception:  # noqa: BLE001
        return None


def redact_text(text: str, *, limit: int) -> str:
    """Strip secret-looking spans; truncate. Never raise."""
    s = str(text or "")
    if "\x00" in s:
        s = s.replace("\x00", "")
    for pat in _SECRET_PATTERNS:
        s = pat.sub(lambda m: f"{m.group(1)}REDACTED", s)
    if len(s) > limit:
        s = s[: limit - 1] + "…"
    return s


def _safe_cache_id(raw: Any) -> str:
    s = str(raw or "").strip()
    if not s or len(s) > _MAX_CACHE_ID:
        return ""
    if any(ch in s for ch in ("/", "\\", "..", "\x00")):
        return ""
    if not re.match(r"^[A-Za-z0-9._\-]+$", s):
        return ""
    return s


def normalize_event(
    body: dict[str, Any],
    *,
    uid: str,
    email: str | None,
) -> dict[str, Any] | None:
    """Build a persistable event or None if body is unusable.

    WHY reject empty kind/message: spam/noise must not inflate admin badge.
    EDGE: client-supplied user_id is ignored — uid comes from session only.
    """
    if not isinstance(body, dict):
        return None
    kind = str(body.get("kind") or "").strip().lower()[:64]
    if not kind:
        return None
    message = redact_text(str(body.get("message") or ""), limit=_MAX_MSG)
    if not message.strip():
        return None
    stack = redact_text(str(body.get("stack") or ""), limit=_MAX_STACK)
    stage = redact_text(str(body.get("stage") or ""), limit=120)
    platform = redact_text(str(body.get("platform") or "unknown"), limit=40)
    app_version = redact_text(str(body.get("app_version") or ""), limit=40)
    title = redact_text(str(body.get("paper_title") or ""), limit=_MAX_TITLE)
    cache_id = _safe_cache_id(body.get("cache_id"))
    # Email for admin triage — never put tokens; truncate local-part long hosts.
    em = redact_text((email or "").strip().lower(), limit=120)
    safe_uid = sanitize_uid(uid) or "unknown"
    return {
        "id": f"err_{uuid.uuid4().hex[:16]}",
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "kind": kind,
        "message": message,
        "stack": stack,
        "stage": stage,
        "platform": platform,
        "app_version": app_version,
        "paper_title": title,
        "cache_id": cache_id,
        "uid": safe_uid,
        "email": em,
        # FAIL-CLOSED marker: never trust client claim of admin.
        "source": "client",
    }


def check_report_rate(uid: str) -> bool:
    """Return True if allowed; False if over limit."""
    key = sanitize_uid(uid) or "anon"
    mx, win = report_rate_limits()
    now = time.time()
    with _LOCK:
        arr = [t for t in _REPORT_MEM.get(key, []) if now - t < win]
        if len(arr) >= mx:
            _REPORT_MEM[key] = arr
            return False
        arr.append(now)
        _REPORT_MEM[key] = arr
        return True


def _pull_events_raw() -> bytes:
    """Prefer GCS when available; else local file."""
    return _jl.pull_events_raw(
        local_path=local_events_path(),
        gcs_object=_gcs_events_object(),
        logger=log,
        label="error_logs",
    )


def _push_events_raw(raw: bytes) -> None:
    _jl.push_events_raw(
        raw=raw,
        local_path=local_events_path(),
        gcs_object=_gcs_events_object(),
        logger=log,
        label="error_logs",
    )


def _parse_events(raw: bytes) -> list[dict[str, Any]]:
    return _jl.parse_jsonl_events(raw)


def append_event(event: dict[str, Any]) -> dict[str, Any]:
    """Append one event; drop rows older than 3 days, then trim. Returns the stored event."""
    with _LOCK:
        events = _parse_events(_pull_events_raw())
        events.append(event)
        events, _dropped = _jl.filter_retained(events, keep_days=retention_days())
        events = _jl.trim_jsonl_events(
            events,
            max_keep=_MAX_EVENTS_KEEP,
            max_body_bytes=_MAX_BODY_BYTES,
        )
        _push_events_raw(_jl.encode_jsonl_events(events))
        return event


def rotate_events(
    *,
    keep_days: int | None = None,
    force: bool = False,
) -> dict[str, Any]:
    """Drop admin error rows older than keep_days. Never raises."""
    global _LAST_ROTATE_MONO
    days = retention_days() if keep_days is None else int(keep_days)
    out: dict[str, Any] = {
        "ok": False,
        "before": 0,
        "after": 0,
        "dropped": 0,
        "skipped": 0,
        "keep_days": days,
    }
    if not cloud_error_logs_enabled():
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
            kept, dropped = _jl.filter_retained(events, keep_days=days)
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
        log.warning("error_logs rotate failed", exc_info=True)
        return out


def list_events(*, limit: int = 50) -> list[dict[str, Any]]:
    lim = max(1, min(int(limit or 50), 200))
    with _LOCK:
        events = _parse_events(_pull_events_raw())
    events.reverse()  # newest first
    return events[:lim]


def _load_seen_ts() -> float:
    obj = _gcs_seen_object()
    raw: bytes | None = None
    if obj:
        try:
            from sentence_reading.llm.gcs_sync import download_bytes, gcs_config

            if gcs_config().enabled:
                raw = download_bytes(obj, meter=False)
        except Exception:  # noqa: BLE001
            raw = None
    if raw is None:
        path = local_seen_path()
        if path.is_file():
            raw = path.read_bytes()
    if not raw:
        return 0.0
    try:
        data = json.loads(raw.decode("utf-8"))
        return float(data.get("seen_unix") or 0)
    except Exception:  # noqa: BLE001
        return 0.0


def _save_seen_ts(ts: float) -> None:
    payload = json.dumps({"seen_unix": ts}, ensure_ascii=False).encode("utf-8")
    path = local_seen_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    obj = _gcs_seen_object()
    if not obj:
        return
    try:
        from sentence_reading.llm.gcs_sync import gcs_config, upload_bytes

        if gcs_config().enabled:
            upload_bytes(obj, payload, content_type="application/json; charset=utf-8")
    except Exception:  # noqa: BLE001
        log.warning("error_logs seen push failed", exc_info=True)


def _event_unix(ev: dict[str, Any]) -> float:
    """Parse event ts; missing → 0 (counts as unseen historically)."""
    from datetime import datetime, timezone

    raw = str(ev.get("ts") or "").strip()
    if not raw:
        return 0.0
    try:
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        dt = datetime.fromisoformat(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.timestamp()
    except Exception:  # noqa: BLE001
        return 0.0


def badge_count() -> int:
    seen = _load_seen_ts()
    with _LOCK:
        events = _parse_events(_pull_events_raw())
    n = 0
    for ev in events:
        if _event_unix(ev) > seen:
            n += 1
    return n


def mark_seen_now() -> float:
    ts = time.time()
    with _LOCK:
        _save_seen_ts(ts)
    return ts
