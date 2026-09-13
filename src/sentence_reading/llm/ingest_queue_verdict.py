"""design/256 — linked ingest-queue / readiness mismatch verdicts (pure, no I/O)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def _ts(ev: dict[str, Any]) -> float:
    raw = ev.get("ts") or ev.get("t") or ""
    if isinstance(raw, (int, float)):
        return float(raw)
    s = str(raw).strip()
    if not s:
        return 0.0
    try:
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        return datetime.fromisoformat(s).timestamp()
    except ValueError:
        return 0.0


def _details(ev: dict[str, Any]) -> dict[str, Any]:
    d = ev.get("details")
    return d if isinstance(d, dict) else {}


def _http_status(ev: dict[str, Any]) -> int:
    for key in ("http_status", "status"):
        raw = ev.get(key)
        if raw is None:
            raw = _details(ev).get(key)
        try:
            return int(raw)
        except (TypeError, ValueError):
            continue
    return 0


def compute_ingest_queue_verdicts(events: list[dict[str, Any]]) -> list[str]:
    """
    Return ordered verdict codes for poll-oversized / queue / translate / practice gaps.

    Join keys: job_id preferred; fallback trace_id for poll→queue chain.
    """
    rows = [e for e in events if isinstance(e, dict)]
    rows.sort(key=_ts)
    out: list[str] = []

    # job_view_result_too_large
    for e in rows:
        if e.get("kind") != "ingest_job_view_size":
            continue
        d = _details(e)
        if int(d.get("oversized") or 0) == 1 or str(e.get("code") or "") == "result_too_large":
            out.append("job_view_result_too_large")
            break

    # poll_500_blocks_upload_queue
    poll_keys: dict[str, float] = {}
    for e in rows:
        if e.get("kind") != "ingest_poll_terminal":
            continue
        if _http_status(e) < 500:
            continue
        jid = str(e.get("job_id") or "").strip()
        tid = str(e.get("trace_id") or "").strip()
        t = _ts(e)
        if jid:
            poll_keys[f"job:{jid}"] = t
        if tid:
            poll_keys[f"tr:{tid}"] = t

    if poll_keys:
        for e in rows:
            if e.get("kind") != "upload_queue_blocked":
                continue
            if str(e.get("stage") or "") != "resumable_draft":
                continue
            jid = str(e.get("job_id") or _details(e).get("job_id") or "").strip()
            tid = str(e.get("trace_id") or "").strip()
            t = _ts(e)
            matched = False
            if jid and poll_keys.get(f"job:{jid}", 0) and t >= poll_keys[f"job:{jid}"]:
                matched = True
            if tid and poll_keys.get(f"tr:{tid}", 0) and t >= poll_keys[f"tr:{tid}"]:
                matched = True
            # EDGE: blocked events may lack job_id — still flag if any 500 poll precedes.
            if not jid and not tid and any(t >= ts for ts in poll_keys.values()):
                matched = True
            if matched:
                out.append("poll_500_blocks_upload_queue")
                break

    # translate_optout_empty_ko
    for e in rows:
        if e.get("kind") == "translate_optout_mismatch":
            out.append("translate_optout_empty_ko")
            break
        if e.get("kind") in ("reader_open", "open_ko_summary"):
            d = _details(e)
            try:
                sn = int(d.get("sentence_n") or 0)
                kn = int(d.get("ko_sentence_n") or 0)
            except (TypeError, ValueError):
                continue
            pending = d.get("translate_pending")
            if sn > 0 and kn == 0 and pending is False:
                out.append("translate_optout_empty_ko")
                break

    # sentences_over_max_blocks_practice
    for e in rows:
        if e.get("kind") not in (
            "shadowing_chunks_build_done",
            "shadowing_build_round",
        ):
            continue
        err = str(
            _details(e).get("error")
            or e.get("code")
            or _details(e).get("error_code")
            or ""
        )
        if err == "sentences_over_max":
            out.append("sentences_over_max_blocks_practice")
            break

    # Deduplicate while preserving order.
    seen: set[str] = set()
    uniq: list[str] = []
    for v in out:
        if v in seen:
            continue
        seen.add(v)
        uniq.append(v)
    if not uniq:
        uniq.append("tracking")
    return uniq
