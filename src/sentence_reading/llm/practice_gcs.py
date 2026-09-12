"""
design/250 — practice focus + skill GCS sync (cloud SoT for long-horizon accumulators).
Objects: {prefix}/users/{uid}/practice/focus_v1.json · skill_v1.json
"""

from __future__ import annotations

import json
import logging
from typing import Any

from sentence_reading.llm.gcs_sync import (
    download_bytes,
    gcs_client_ready,
    gcs_config,
    personal_object_name,
    upload_bytes,
)

log = logging.getLogger(__name__)

PRACTICE_STORE_MAX_BYTES = 400_000


def focus_store_object() -> str | None:
    return personal_object_name("practice", "focus_v1.json")


def skill_store_object() -> str | None:
    return personal_object_name("practice", "skill_v1.json")


def empty_focus_store() -> dict[str, Any]:
    return {"version": 2, "days": {}, "best_streak": 0, "updated_at_ms": 0}


def empty_skill_store() -> dict[str, Any]:
    return {
        "version": 2,
        "tier": 2,
        "density": 0,
        "days": {},
        "block_sum": 0,
        "block_n": 0,
        "cooldown_blocks": 0,
        "epoch_means": [],
        "epoch_target_n": 5,
        "updated_at_ms": 0,
    }


def _as_int(v: Any, default: int = 0) -> int:
    if isinstance(v, bool):
        return default
    if isinstance(v, int):
        return v
    if isinstance(v, float):
        return int(v)
    if isinstance(v, str):
        try:
            return int(v.strip())
        except ValueError:
            return default
    return default


def _as_float(v: Any, default: float = 0.0) -> float:
    if isinstance(v, bool):
        return default
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        try:
            return float(v.strip())
        except ValueError:
            return default
    return default


def _day_key_ok(k: str) -> bool:
    return bool(k) and len(k) == 10 and k[4] == "-" and k[7] == "-"


def normalize_focus_store(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return empty_focus_store()
    days_in = raw.get("days")
    days: dict[str, int] = {}
    if isinstance(days_in, dict):
        for k, v in days_in.items():
            ks = str(k).strip()
            if not _day_key_ok(ks):
                continue
            n = _as_int(v, 0)
            if n > 0:
                days[ks] = n
    best = max(0, _as_int(raw.get("best_streak"), 0))
    return {
        "version": 2,
        "days": days,
        "best_streak": best,
        "updated_at_ms": max(0, _as_int(raw.get("updated_at_ms"), 0)),
    }


def normalize_skill_store(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return empty_skill_store()
    days_in = raw.get("days")
    days: dict[str, dict[str, Any]] = {}
    if isinstance(days_in, dict):
        for k, v in days_in.items():
            ks = str(k).strip()
            if not _day_key_ok(ks):
                continue
            if not isinstance(v, dict):
                continue
            n = max(0, _as_int(v.get("n"), 0))
            s = _as_float(v.get("sum"), 0.0)
            if n > 0:
                days[ks] = {"sum": s, "n": n}
    means_raw = raw.get("epoch_means")
    means: list[float] = []
    if isinstance(means_raw, list):
        for x in means_raw:
            if isinstance(x, (int, float)):
                means.append(float(x))
    target = _as_int(raw.get("epoch_target_n"), 5)
    target = max(5, min(10, target))
    tier = max(0, min(5, _as_int(raw.get("tier"), 2)))
    density = max(-2, min(2, _as_int(raw.get("density"), 0)))
    return {
        "version": 2,
        "tier": tier,
        "density": density,
        "days": days,
        "block_sum": _as_float(raw.get("block_sum"), 0.0),
        "block_n": max(0, _as_int(raw.get("block_n"), 0)),
        "cooldown_blocks": max(0, _as_int(raw.get("cooldown_blocks"), 0)),
        "epoch_means": means,
        "epoch_target_n": target,
        "updated_at_ms": max(0, _as_int(raw.get("updated_at_ms"), 0)),
    }


def merge_focus_stores(a: Any, b: Any) -> dict[str, Any]:
    sa = normalize_focus_store(a)
    sb = normalize_focus_store(b)
    days: dict[str, int] = {}
    for k in set(sa["days"]) | set(sb["days"]):
        days[k] = max(int(sa["days"].get(k, 0)), int(sb["days"].get(k, 0)))
    best = max(int(sa["best_streak"]), int(sb["best_streak"]))
    updated = max(int(sa["updated_at_ms"]), int(sb["updated_at_ms"]))
    return {
        "version": 2,
        "days": days,
        "best_streak": best,
        "updated_at_ms": updated,
    }


def merge_skill_stores(a: Any, b: Any) -> dict[str, Any]:
    sa = normalize_skill_store(a)
    sb = normalize_skill_store(b)
    # Live fields: LWW by updated_at_ms
    if int(sb["updated_at_ms"]) >= int(sa["updated_at_ms"]):
        live = sb
    else:
        live = sa
    days: dict[str, dict[str, Any]] = {}
    for k in set(sa["days"]) | set(sb["days"]):
        da = sa["days"].get(k)
        db = sb["days"].get(k)
        if not isinstance(da, dict):
            da = None
        if not isinstance(db, dict):
            db = None
        if da is None and db is None:
            continue
        if da is None:
            days[k] = db  # type: ignore[assignment]
            continue
        if db is None:
            days[k] = da
            continue
        na, nb = int(da.get("n", 0)), int(db.get("n", 0))
        sa_sum, sb_sum = float(da.get("sum", 0)), float(db.get("sum", 0))
        if nb > na or (nb == na and sb_sum >= sa_sum):
            days[k] = {"sum": sb_sum, "n": nb}
        else:
            days[k] = {"sum": sa_sum, "n": na}
    out = dict(live)
    out["days"] = days
    out["version"] = 2
    out["updated_at_ms"] = max(int(sa["updated_at_ms"]), int(sb["updated_at_ms"]))
    return normalize_skill_store(out)


def _encode(store: dict[str, Any]) -> bytes | None:
    try:
        raw = json.dumps(store, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    except (TypeError, ValueError):
        return None
    if len(raw) > PRACTICE_STORE_MAX_BYTES:
        return None
    return raw


def _decode_focus(raw: bytes | None) -> dict[str, Any] | None:
    if not raw or len(raw) > PRACTICE_STORE_MAX_BYTES:
        return None
    try:
        return normalize_focus_store(json.loads(raw.decode("utf-8")))
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError):
        return None


def _decode_skill(raw: bytes | None) -> dict[str, Any] | None:
    if not raw or len(raw) > PRACTICE_STORE_MAX_BYTES:
        return None
    try:
        return normalize_skill_store(json.loads(raw.decode("utf-8")))
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError):
        return None


def download_focus_store() -> dict[str, Any] | None:
    obj = focus_store_object()
    if not obj:
        return None
    return _decode_focus(download_bytes(obj))


def download_skill_store() -> dict[str, Any] | None:
    obj = skill_store_object()
    if not obj:
        return None
    return _decode_skill(download_bytes(obj))


def upload_focus_store(store: dict[str, Any]) -> bool:
    obj = focus_store_object()
    if not obj:
        return False
    raw = _encode(normalize_focus_store(store))
    if not raw:
        return False
    return upload_bytes(obj, raw, content_type="application/json; charset=utf-8")


def upload_skill_store(store: dict[str, Any]) -> bool:
    obj = skill_store_object()
    if not obj:
        return False
    raw = _encode(normalize_skill_store(store))
    if not raw:
        return False
    return upload_bytes(obj, raw, content_type="application/json; charset=utf-8")


def push_focus_store(local: dict[str, Any]) -> dict[str, Any]:
    local_s = normalize_focus_store(local)
    ready, _ = gcs_client_ready()
    if not gcs_config().enabled or not ready:
        return local_s
    remote = download_focus_store() or empty_focus_store()
    merged = merge_focus_stores(remote, local_s)
    if not upload_focus_store(merged):
        log.warning("practice focus upload failed")
    return merged


def push_skill_store(local: dict[str, Any]) -> dict[str, Any]:
    local_s = normalize_skill_store(local)
    ready, _ = gcs_client_ready()
    if not gcs_config().enabled or not ready:
        return local_s
    remote = download_skill_store() or empty_skill_store()
    merged = merge_skill_stores(remote, local_s)
    if not upload_skill_store(merged):
        log.warning("practice skill upload failed")
    return merged


def practice_gcs_status_fields() -> dict[str, Any]:
    return {
        "practice_cloud_sync": True,
        "practice_focus_object": focus_store_object(),
        "practice_skill_object": skill_store_object(),
        "practice_store_max_bytes": PRACTICE_STORE_MAX_BYTES,
    }
