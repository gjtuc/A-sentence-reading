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
    try:
        from sentence_reading.llm.gcs_sync import object_name

        return object_name("error_logs", "events.jsonl")
    except Exception:  # noqa: BLE001
        return None


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
    obj = _gcs_events_object()
    if obj:
        try:
            from sentence_reading.llm.gcs_sync import download_bytes, gcs_config

            if gcs_config().enabled:
                raw = download_bytes(obj, meter=False)
                if raw is not None:
                    return raw
        except Exception:  # noqa: BLE001
            log.warning("error_logs gcs pull failed", exc_info=True)
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
        log.warning("error_logs gcs push failed", exc_info=True)


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


def append_event(event: dict[str, Any]) -> dict[str, Any]:
    """Append one event; trim old lines. Returns the stored event."""
    with _LOCK:
        events = _parse_events(_pull_events_raw())
        events.append(event)
        if len(events) > _MAX_EVENTS_KEEP:
            events = events[-_MAX_EVENTS_KEEP:]
        blob = ("\n".join(json.dumps(e, ensure_ascii=False) for e in events) + "\n").encode(
            "utf-8"
        )
        if len(blob) > _MAX_BODY_BYTES:
            # EDGE: oversized store — keep newest half.
            events = events[len(events) // 2 :]
            blob = ("\n".join(json.dumps(e, ensure_ascii=False) for e in events) + "\n").encode(
                "utf-8"
            )
        _push_events_raw(blob)
        return event


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
