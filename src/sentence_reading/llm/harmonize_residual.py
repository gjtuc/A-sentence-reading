"""design/169o — post-ingest harmonize residual task helpers."""

from __future__ import annotations

import logging
from dataclasses import replace
from typing import Any

log = logging.getLogger(__name__)

# cache_id → in-flight residual (process-local; multi-instance uses index pending)
_HARMONIZE_RESIDUAL_INFLIGHT: set[str] = set()


def residual_inflight(cache_id: str) -> bool:
    return bool((cache_id or "").strip()) and (cache_id.strip() in _HARMONIZE_RESIDUAL_INFLIGHT)


def try_mark_residual_inflight(cache_id: str) -> bool:
    cid = (cache_id or "").strip()
    if not cid or cid in _HARMONIZE_RESIDUAL_INFLIGHT:
        return False
    _HARMONIZE_RESIDUAL_INFLIGHT.add(cid)
    return True


def clear_residual_inflight(cache_id: str) -> None:
    _HARMONIZE_RESIDUAL_INFLIGHT.discard((cache_id or "").strip())


def patch_harmonize_index(
    cache_id: str,
    *,
    pending: bool,
    total: int = 0,
    done: int = 0,
    failed: int = 0,
    attempt_n: int = 1,
) -> None:
    from sentence_reading.cache.paper_cache import patch_index_entry

    patch_index_entry(
        cache_id,
        harmonize_pending=bool(pending),
        harmonize_total=int(total),
        harmonize_done=int(done),
        harmonize_failed=int(failed),
        harmonize_attempt_n=int(attempt_n),
    )


def index_harmonize_fields(entry: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(entry, dict):
        return {
            "harmonize_pending": False,
            "harmonize_total": 0,
            "harmonize_done": 0,
            "harmonize_failed": 0,
            "harmonize_attempt_n": 0,
        }
    try:
        total = int(entry.get("harmonize_total") or 0)
    except (TypeError, ValueError):
        total = 0
    try:
        done = int(entry.get("harmonize_done") or 0)
    except (TypeError, ValueError):
        done = 0
    try:
        failed = int(entry.get("harmonize_failed") or 0)
    except (TypeError, ValueError):
        failed = 0
    try:
        attempt = int(entry.get("harmonize_attempt_n") or 0)
    except (TypeError, ValueError):
        attempt = 0
    return {
        "harmonize_pending": bool(entry.get("harmonize_pending")),
        "harmonize_total": total,
        "harmonize_done": done,
        "harmonize_failed": failed,
        "harmonize_attempt_n": attempt,
    }


def apply_on_item_to_session(session: Any, kind: str, index: int, ko: str, stage: str) -> None:
    if kind == "sentence" and 0 <= index < len(session.sentences):
        s = session.sentences[index]
        session.sentences[index] = replace(s, text_ko=ko, text_ko_stage=stage)
    elif kind == "figure" and 0 <= index < len(session.figures):
        f = session.figures[index]
        session.figures[index] = replace(f, caption_ko=ko, caption_ko_stage=stage)
