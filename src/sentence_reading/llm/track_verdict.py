"""
design/169k — pull-linked verdict rules for translate/ingest jobs.

Pure functions only (no adb/GCS). Used by scripts/track_translate.py and tests.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


def _parse_ts(ts: str) -> datetime | None:
    s = (ts or "").strip()
    if not s:
        return None
    try:
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except ValueError:
        return None


def _delta_s(a: str, b: str) -> float | None:
    ta, tb = _parse_ts(a), _parse_ts(b)
    if ta is None or tb is None:
        return None
    return (tb - ta).total_seconds()


@dataclass
class JobTimeline:
    events: list[dict] = field(default_factory=list)
    terminal_error_ts: str = ""
    terminal_reason: str = ""
    post_terminal_events: int = 0
    harmonize_done_ts: dict[str, str] = field(default_factory=dict)
    pool_end_ts: dict[str, str] = field(default_factory=dict)
    pool_tick_zero_ts: dict[str, str] = field(default_factory=dict)
    phase_exit_ok: bool = False
    last_pool_tick_ts: str = ""
    last_kind: str = ""
    last_ts: str = ""
    writer_flush_ok: bool = False

    @classmethod
    def from_events(cls, events: list[dict]) -> JobTimeline:
        tl = cls(events=sorted(events, key=lambda o: o.get("ts") or ""))
        terminal_seen = False
        for o in tl.events:
            k = o.get("kind") or ""
            d = o.get("details") or {}
            ts = o.get("ts") or ""
            tl.last_kind = k
            tl.last_ts = ts
            if k == "server_job_terminal_error":
                terminal_seen = True
                tl.terminal_error_ts = ts
                tl.terminal_reason = str(d.get("reason_enum") or d.get("reason") or "")
            elif terminal_seen:
                tl.post_terminal_events += 1
            if k == "checkpoint":
                cp = str(d.get("checkpoint") or "")
                sec = str(d.get("section") or "")
                if cp == "harmonize_pool_end":
                    tl.pool_end_ts[sec] = ts
                elif cp == "harmonize_pool_tick" and d.get("remaining") == 0:
                    tl.pool_tick_zero_ts[sec] = ts
                elif cp == "harmonize_pool_tick":
                    tl.last_pool_tick_ts = ts
                elif cp == "writer_flush" and o.get("ok") is not False:
                    tl.writer_flush_ok = True
            if k == "translate_call_done" and d.get("call_kind") == "harmonize":
                sec = str(d.get("section") or "")
                if sec:
                    tl.harmonize_done_ts[sec] = ts
            if k == "translate_phase_exit" and o.get("ok") is not False:
                tl.phase_exit_ok = True
        return tl


def check_169j_section_pass(tl: JobTimeline, section: str = "title") -> bool | None:
    """True if harmonize done → pool_end/tick0 within 5s for section."""
    done_ts = tl.harmonize_done_ts.get(section)
    if not done_ts:
        return None
    end_ts = tl.pool_end_ts.get(section) or tl.pool_tick_zero_ts.get(section)
    if not end_ts:
        return False
    dt = _delta_s(done_ts, end_ts)
    if dt is None:
        return None
    return dt <= 5.0


def compute_verdicts(
    tl: JobTimeline,
    *,
    ui_pct: int | None,
    open_hangs: list[str],
    silence_s: int | None,
    prev: dict[str, Any],
) -> list[str]:
    out: list[str] = []

    if tl.post_terminal_events > 0 and tl.terminal_error_ts:
        out.append(
            f"zombie_worker: {tl.post_terminal_events} events after "
            f"terminal ({tl.terminal_reason or 'error'})"
        )

    if tl.terminal_error_ts and tl.terminal_reason == "worker_lost":
        out.append("worker_lost_terminal")

    j169 = check_169j_section_pass(tl, "title")
    if j169 is True:
        out.append("accept_169j_title: pool_end/tick≤5s after harmonize")
    elif j169 is False:
        out.append("fail_169j_title: harmonize done but no pool_end≤5s")

    if tl.phase_exit_ok:
        out.append("translate_phase_exit_ok")

    # Parallel harmonize pool: suppress false hang when pool recently ticked.
    harmonize_opens = [h for h in open_hangs if "harmonize" in h]
    if harmonize_opens and tl.last_pool_tick_ts and silence_s is not None:
        tick_age = _delta_s(tl.last_pool_tick_ts, tl.last_ts)
        if tick_age is not None and tick_age < 90:
            out.append("harmonize_pool_active: ignore parallel call_start hangs")
        elif harmonize_opens:
            out.append("hang_suspect: harmonize call_start without done/fail")
    elif open_hangs:
        out.append("hang_suspect: call_start without done/fail")

    if (
        ui_pct is not None
        and ui_pct >= 90
        and not harmonize_opens
        and tl.last_kind == "translate_call_done"
        and silence_s is not None
        and silence_s >= 120
    ):
        out.append(f"post_call_stall: {silence_s}s silence at {ui_pct}%")

    if ui_pct is not None and prev.get("ui_pct") == ui_pct:
        stuck_n = int(prev.get("pct_stuck_n") or 0) + 1
    else:
        stuck_n = 0
    if stuck_n >= 3 and open_hangs:
        out.append(f"ui_and_api_stuck pct={ui_pct} ticks={stuck_n}")

    if not out:
        out.append("tracking")
    return out
