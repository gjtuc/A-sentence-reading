"""
Per-uid ingest/upload *call-count* rate limits (design/73).

WHY: shared Cloud Run — one account must not spam upload sessions / chunk PUTs /
ingest starts and burn GCS + Gemini for everyone.

INVARIANT:
- Keyed only by session uid (never body/query user_id).
- Counts requests only — never file bytes / size (product: no size quota chip).
- No daily caps — sliding windows only (product).
- Kill switch ASR_INGEST_RATE_LIMIT=0 disables checks (ops escape hatch).
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from pathlib import Path
from typing import Any

from sentence_reading.cache.paper_cache import project_root
from sentence_reading.llm.auth_google import sanitize_uid
from sentence_reading.llm.env import load_asr_env

log = logging.getLogger(__name__)

_LOCK = threading.RLock()

# action → (env_max, default_max, env_window, default_window_sec)
# WHY put ceiling is high: 50MB / 256KiB ≈ 200 PUTs; allow headroom in-window.
_ACTIONS: dict[str, tuple[str, int, str, int]] = {
    "upload_create": ("ASR_UPLOAD_CREATE_MAX", 12, "ASR_UPLOAD_CREATE_WINDOW_SEC", 600),
    "upload_put": ("ASR_UPLOAD_PUT_MAX", 600, "ASR_UPLOAD_PUT_WINDOW_SEC", 600),
    "ingest_start": ("ASR_INGEST_START_MAX", 10, "ASR_INGEST_START_WINDOW_SEC", 600),
}

# Process memory: {uid: {action: [timestamps...]}}
_MEM: dict[str, dict[str, list[int]]] = {}


def rate_limit_enabled() -> bool:
    """Kill switch: ASR_INGEST_RATE_LIMIT=0 → allow all (limiter off)."""
    load_asr_env()
    raw = (os.environ.get("ASR_INGEST_RATE_LIMIT") or "1").strip().lower()
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


def limits_for(action: str) -> tuple[int, int]:
    """Return (max_count, window_sec) for action. Unknown action → (0, 0) deny."""
    spec = _ACTIONS.get(action)
    if spec is None:
        return 0, 0
    max_env, max_def, win_env, win_def = spec
    # EDGE: absurd env values clamp; <=0 max falls back to default (fail closed-ish).
    mx = _env_int(max_env, max_def, lo=1, hi=100_000)
    win = _env_int(win_env, win_def, lo=1, hi=7 * 24 * 3600)
    return mx, win


def store_path() -> Path:
    return project_root() / "data" / "auth" / "ingest_rate.json"


def _auth_gcs_object() -> str | None:
    try:
        from sentence_reading.llm.gcs_sync import object_name

        return object_name("auth", "ingest_rate.json")
    except Exception:  # noqa: BLE001
        return None


def _push_store(path: Path) -> None:
    try:
        from sentence_reading.llm.gcs_sync import upload_bytes

        obj = _auth_gcs_object()
        if not obj or not path.is_file():
            return
        raw = path.read_bytes()
        if not raw:
            return
        upload_bytes(obj, raw, content_type="application/json; charset=utf-8")
    except Exception as exc:  # noqa: BLE001
        log.debug("ingest_rate gcs push skip: %s", exc)


def _pull_remote() -> dict[str, Any] | None:
    try:
        from sentence_reading.llm.gcs_sync import download_bytes

        obj = _auth_gcs_object()
        if not obj:
            return None
        raw = download_bytes(obj)
        if not raw:
            return None
        data = json.loads(raw.decode("utf-8"))
        return data if isinstance(data, dict) else None
    except Exception as exc:  # noqa: BLE001
        log.debug("ingest_rate gcs pull skip: %s", exc)
        return None


def _read_disk() -> dict[str, Any]:
    path = store_path()
    if not path.is_file():
        return {"version": 1, "by_uid": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return {"version": 1, "by_uid": {}}
    if not isinstance(data, dict):
        return {"version": 1, "by_uid": {}}
    if not isinstance(data.get("by_uid"), dict):
        data["by_uid"] = {}
    return data


def _write_disk(store: dict[str, Any]) -> None:
    path = store_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(store, ensure_ascii=False, separators=(",", ":"))
    path.write_text(raw, encoding="utf-8")
    _push_store(path)


def _as_stamps(raw: Any) -> list[int]:
    if not isinstance(raw, list):
        return []
    out: list[int] = []
    for x in raw:
        try:
            out.append(int(x))
        except (TypeError, ValueError):
            continue
    return out


def _merge_stamp_lists(a: list[int], b: list[int], *, cutoff: int) -> list[int]:
    seen: set[int] = set()
    out: list[int] = []
    for src in (a, b):
        for ix in src:
            if ix < cutoff or ix in seen:
                continue
            seen.add(ix)
            out.append(ix)
    out.sort()
    return out


def _hydrate_uid_from_disk(uid: str) -> None:
    """Union remote/local stamps into memory (multi-instance blunt sync)."""
    disk = _read_disk()
    remote = _pull_remote()
    d_by: dict[str, Any] = (
        disk.get("by_uid") if isinstance(disk.get("by_uid"), dict) else {}
    )
    if remote and isinstance(remote.get("by_uid"), dict):
        for u, actions in remote["by_uid"].items():
            if not isinstance(actions, dict):
                continue
            local_a = d_by.get(u) if isinstance(d_by.get(u), dict) else {}
            merged_a: dict[str, list[int]] = {}
            keys = set(local_a.keys()) | set(actions.keys())
            for act in keys:
                if act not in _ACTIONS:
                    continue
                merged_a[act] = _merge_stamp_lists(
                    _as_stamps(local_a.get(act)),
                    _as_stamps(actions.get(act)),
                    cutoff=0,
                )
            d_by[str(u)] = merged_a

    row = d_by.get(uid)
    if not isinstance(row, dict):
        return
    mem = _MEM.setdefault(uid, {})
    for act, stamps in row.items():
        if act not in _ACTIONS:
            continue
        mem[act] = _merge_stamp_lists(
            mem.get(act) or [], _as_stamps(stamps), cutoff=0
        )


def _persist_uid(uid: str) -> None:
    disk = _read_disk()
    by = disk.setdefault("by_uid", {})
    if not isinstance(by, dict):
        by = {}
        disk["by_uid"] = by
    mem = _MEM.get(uid) or {}
    by[uid] = {k: list(v) for k, v in mem.items() if k in _ACTIONS}
    # EDGE: bound growth — drop idle uids beyond 4000
    if len(by) > 5000:
        disk["by_uid"] = dict(list(by.items())[-4000:])
    _write_disk(disk)


def check_and_record(uid: str, action: str, *, now: int | None = None) -> None:
    """
    Record one call for uid/action or raise ValueError('rate_limited').

    EDGE: unknown action → rate_limited (fail-closed).
    EDGE: empty uid → auth_required.
    """
    if not rate_limit_enabled():
        return
    uid_s = sanitize_uid(uid or "")
    if not uid_s:
        # WHY: never accept client-supplied identity; caller must pass session uid.
        raise ValueError("auth_required")
    if action not in _ACTIONS:
        raise ValueError("rate_limited")
    mx, window = limits_for(action)
    if mx <= 0 or window <= 0:
        raise ValueError("rate_limited")
    ts = int(now if now is not None else time.time())
    cutoff = ts - window
    with _LOCK:
        if uid_s not in _MEM:
            _hydrate_uid_from_disk(uid_s)
        bucket = _MEM.setdefault(uid_s, {})
        stamps = [x for x in (bucket.get(action) or []) if int(x) >= cutoff]
        if len(stamps) >= mx:
            # WHY: do not append on reject — window must drain before retry.
            raise ValueError("rate_limited")
        stamps.append(ts)
        # keep a little extra history for merge
        bucket[action] = stamps[-(mx * 3) :]
        try:
            _persist_uid(uid_s)
        except Exception as exc:  # noqa: BLE001
            # EDGE: disk/GCS fail must not open the gate — memory still enforced.
            log.debug("ingest_rate persist skip: %s", exc)


def clear_memory_for_tests() -> None:
    with _LOCK:
        _MEM.clear()


def rate_limit_status_fields() -> dict[str, Any]:
    """Public /api/status fields — no per-user counters (privacy)."""
    return {
        "ingest_rate_limit": rate_limit_enabled(),
        "ingest_rate_limit_actions": sorted(_ACTIONS.keys()),
    }
