"""design/168b — ingest integrity checks (T1–T10), log-only.

WHY: detect job/index/session/blob inconsistency before bug-fix PRs.
INVARIANT:
- Never blocks save/finish (emit only).
- details numeric/enum only — no paper text.
- Kill switch ASR_INGEST_INTEGRITY=0.
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from typing import Any

from sentence_reading.llm.env import load_asr_env

log = logging.getLogger(__name__)

_CACHE_ID_RE = re.compile(r"^[A-Za-z0-9._\-]+$")


def ingest_integrity_enabled() -> bool:
    """Kill switch: ASR_INGEST_INTEGRITY=0 → off."""
    load_asr_env()
    raw = (os.environ.get("ASR_INGEST_INTEGRITY") or "1").strip().lower()
    return raw not in ("0", "false", "off", "no")


@dataclass(frozen=True)
class Violation:
    invariant: str
    code: str
    details: dict[str, Any] = field(default_factory=dict)


def _safe_int(raw: Any, default: int = 0) -> int:
    try:
        return int(raw)
    except (TypeError, ValueError):
        return default


def check_job(job: dict[str, Any]) -> list[Violation]:
    """T1, T2, T7 against an in-memory or GCS job dict."""
    if not isinstance(job, dict):
        return []
    out: list[Violation] = []
    done = bool(job.get("done"))
    if done and job.get("error"):
        out.append(
            Violation(
                invariant="T1",
                code="done_with_error",
                details={"done": 1, "has_error": 1},
            )
        )
    if done:
        result = job.get("result")
        cache_id = ""
        if isinstance(result, dict):
            cache_id = str(result.get("cache_id") or "").strip()
        if not cache_id:
            out.append(
                Violation(
                    invariant="T2",
                    code="done_without_cache_id",
                    details={"done": 1, "cache_id_len": 0},
                )
            )
        if isinstance(result, dict) and result.get("translate_pending"):
            out.append(
                Violation(
                    invariant="T7",
                    code="complete_translate_pending",
                    details={"done": 1, "translate_pending": 1},
                )
            )
    return out


def check_fig_meta(session_figures: int, fig_meta: int) -> list[Violation]:
    """T9 — session.figures len vs persisted fig_meta len."""
    sf = max(0, int(session_figures))
    fm = max(0, int(fig_meta))
    if sf == fm:
        return []
    return [
        Violation(
            invariant="T9",
            code="figures_meta_dropped",
            details={"session_figures": sf, "fig_meta": fm},
        )
    ]


def check_session_vs_index(
    session_payload: dict[str, Any], entry: dict[str, Any]
) -> list[Violation]:
    """T4, T5 — index counts vs session payload lists."""
    if not isinstance(session_payload, dict) or not isinstance(entry, dict):
        return []
    out: list[Violation] = []
    figs = session_payload.get("figures") or []
    sents = session_payload.get("sentences") or []
    session_fig_n = len(figs) if isinstance(figs, list) else 0
    session_sent_n = len(sents) if isinstance(sents, list) else 0
    index_fig_n = _safe_int(entry.get("figure_count"), -1)
    index_sent_n = _safe_int(entry.get("sentence_count"), -1)
    if index_fig_n >= 0 and index_fig_n != session_fig_n:
        out.append(
            Violation(
                invariant="T4",
                code="figure_count_mismatch",
                details={
                    "index_figure_count": index_fig_n,
                    "session_figures": session_fig_n,
                },
            )
        )
    if index_sent_n >= 0 and index_sent_n != session_sent_n:
        out.append(
            Violation(
                invariant="T5",
                code="sentence_count_mismatch",
                details={
                    "index_sentence_count": index_sent_n,
                    "session_sentences": session_sent_n,
                },
            )
        )
    return out


def check_partial_vs_status(
    *, job_done: bool, ingest_status: str
) -> list[Violation]:
    """T8 — partial (job not done) must not claim ingest_status=ok."""
    status = str(ingest_status or "").strip().lower()
    if (not job_done) and status == "ok":
        return [
            Violation(
                invariant="T8",
                code="partial_marked_ok",
                details={"job_done": 0, "ingest_status_ok": 1},
            )
        ]
    return []


def check_index_vs_job(
    entry: dict[str, Any], job: dict[str, Any]
) -> list[Violation]:
    """T3 — index ok implies latest job done (when job provided)."""
    if not isinstance(entry, dict) or not isinstance(job, dict):
        return []
    status = str(entry.get("ingest_status") or "").strip().lower()
    if status != "ok":
        return []
    if bool(job.get("done")):
        return []
    details: dict[str, Any] = {"ingest_status_ok": 1, "job_done": 0}
    e_hash = str(entry.get("content_hash") or "").strip().lower()
    j_hash = str(job.get("content_hash") or "").strip().lower()
    if e_hash and j_hash and e_hash != j_hash:
        # Different paper — do not flag T3.
        return []
    if e_hash and j_hash:
        details["content_hash_match"] = 1
    return [
        Violation(
            invariant="T3",
            code="index_ok_job_not_done",
            details=details,
        )
    ]


def check_figure_blobs(cache_id: str, figures: list[Any]) -> list[Violation]:
    """T6 — local figure files exist and size>0 when `file` is set.

    EDGE: no file fields → skip (nothing to verify locally).
    """
    cid = str(cache_id or "").strip()
    if not cid or not _CACHE_ID_RE.match(cid) or ".." in cid:
        return []
    if not isinstance(figures, list):
        return []
    from sentence_reading.cache.paper_cache import cache_root

    root = cache_root() / cid
    checked = 0
    missing = 0
    empty = 0
    for fig in figures:
        if not isinstance(fig, dict):
            continue
        rel = str(fig.get("file") or "").strip().replace("\\", "/")
        if not rel or rel.startswith("/") or ".." in rel:
            continue
        checked += 1
        path = root / rel
        if not path.is_file():
            missing += 1
            continue
        try:
            if path.stat().st_size <= 0:
                empty += 1
        except OSError:
            missing += 1
    if checked == 0:
        return []
    if missing == 0 and empty == 0:
        return []
    return [
        Violation(
            invariant="T6",
            code="figure_blob_miss",
            details={
                "scope": "local",
                "checked": checked,
                "missing": missing,
                "empty": empty,
            },
        )
    ]


def audit_cache(
    cache_id: str, *, job: dict[str, Any] | None = None
) -> list[Violation]:
    """Compose T4–T6 (+ job T1–T3/T7) for one cache_id. Never raises."""
    cid = str(cache_id or "").strip()
    if not cid or not _CACHE_ID_RE.match(cid):
        return []
    try:
        from sentence_reading.cache.paper_cache import (
            get_index_entry,
            load_cached_session,
        )

        entry = get_index_entry(cid)
        loaded = load_cached_session(cid, load_images=False)
        out: list[Violation] = []
        if loaded is None:
            return out
        _session, meta = loaded
        if not isinstance(meta, dict):
            meta = {}
        if isinstance(entry, dict):
            out.extend(check_session_vs_index(meta, entry))
            if isinstance(job, dict):
                out.extend(check_index_vs_job(entry, job))
        figs = meta.get("figures") or []
        if isinstance(figs, list):
            out.extend(check_figure_blobs(cid, figs))
        if isinstance(job, dict):
            out.extend(check_job(job))
        return out
    except Exception:  # noqa: BLE001
        log.warning("ingest_integrity audit_cache failed", exc_info=True)
        return []


def violations_to_public(violations: list[Violation]) -> list[dict[str, Any]]:
    """Admin JSON rows — invariant/code/details only (no free text)."""
    out: list[dict[str, Any]] = []
    for v in violations:
        if not isinstance(v, Violation):
            continue
        row: dict[str, Any] = {
            "invariant": str(v.invariant or "").strip().upper()[:8],
            "code": str(v.code or "").strip().lower()[:64],
        }
        if isinstance(v.details, dict) and v.details:
            # Reuse ops-safe filtering via emit path shape.
            clean: dict[str, Any] = {}
            for key, val in v.details.items():
                k = str(key or "").strip()[:40]
                if not k or not re.match(r"^[a-z][a-z0-9_]{0,39}$", k):
                    continue
                if isinstance(val, bool):
                    clean[k] = val
                elif isinstance(val, int):
                    clean[k] = val
                elif isinstance(val, float):
                    clean[k] = round(val, 3)
                elif isinstance(val, str):
                    s = val.strip()[:64]
                    if s and re.match(r"^[a-z][a-z0-9_]{0,63}$", s):
                        clean[k] = s
            if clean:
                row["details"] = clean
        out.append(row)
    return out


def emit_violations(
    violations: list[Violation],
    *,
    trace_id: str = "",
    job_id: str = "",
    cache_id: str = "",
    owner_uid: str = "",
    content_hash: str = "",
    stage: str = "",
    percent: int | None = None,
) -> None:
    """Fire ops consistency_violation per row. Never raises."""
    if not ingest_integrity_enabled():
        return
    if not violations:
        return
    try:
        from sentence_reading.llm import ops_events as oev

        for v in violations:
            if not isinstance(v, Violation):
                continue
            details = dict(v.details or {})
            inv = str(v.invariant or "").strip().upper()[:8]
            code = str(v.code or "").strip().lower()[:64]
            if inv:
                # ops_events details allow lowercase enum strings only
                details["invariant"] = inv.lower()
            if code and re.match(r"^[a-z][a-z0-9_]{0,63}$", code):
                details["code"] = code
            oev.emit(
                "consistency_violation",
                trace_id=trace_id,
                job_id=job_id,
                cache_id=cache_id,
                owner_uid=owner_uid,
                content_hash=content_hash,
                stage=stage,
                percent=percent,
                details=details,
            )
    except Exception:  # noqa: BLE001
        log.warning("ingest_integrity emit_violations failed", exc_info=True)
