"""design/169p — pure shadowing practice verdict rules (no I/O)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


BUILD_API_ERRORS = frozenset(
    {
        "gemini_unavailable",
        "gcs_pull_failed",
        "paper_not_found",
        "practice_off",
        "shadowing_disabled",
        "build_failed",
    }
)

ENSURE_PENDING_S = 120.0
GEMINI_HANG_SLACK_S = 30.0
PREP_STUCK_S = 120.0


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


@dataclass
class ShadowingTimeline:
    cache_id: str = ""
    events: list[dict[str, Any]] = field(default_factory=list)

    @classmethod
    def from_events(
        cls, events: list[dict[str, Any]], *, cache_id: str = ""
    ) -> ShadowingTimeline:
        cid = (cache_id or "").strip()
        rows = [
            e
            for e in events
            if isinstance(e, dict)
            and str(e.get("kind") or "").startswith("shadowing_")
            and (not cid or str(e.get("cache_id") or "") == cid)
        ]
        rows.sort(key=_ts)
        if not cid and rows:
            cid = str(rows[-1].get("cache_id") or "")
        return cls(cache_id=cid, events=rows)


def compute_shadowing_verdicts(
    timeline: ShadowingTimeline,
    *,
    now_ts: float | None = None,
    budget_s: float = 90.0,
) -> list[str]:
    """Return ordered verdict codes for a shadowing prep/loop timeline."""
    now = now_ts if now_ts is not None else datetime.now(timezone.utc).timestamp()
    evs = timeline.events
    out: list[str] = []

    def kinds(k: str) -> list[dict[str, Any]]:
        return [e for e in evs if e.get("kind") == k]

    gates = kinds("shadowing_gate")
    for g in gates:
        gate = str(_details(g).get("gate") or g.get("code") or "")
        if gate == "kill_off":
            out.append("gate_kill_off")
        elif gate == "pref_off":
            out.append("gate_pref_off")

    ensure_starts = kinds("shadowing_ensure_start")
    ensure_dones = kinds("shadowing_ensure_done")
    for last_done in ensure_dones:
        d = _details(last_done)
        if str(d.get("error_code") or last_done.get("code") or "") == "cap_hit":
            out.append("build_cap_hit")
    if ensure_starts and not ensure_dones:
        age = now - _ts(ensure_starts[-1])
        if age >= ENSURE_PENDING_S:
            out.append("ensure_pending_long")
    elif ensure_starts and ensure_dones:
        last_done = ensure_dones[-1]
        d = _details(last_done)
        if str(d.get("plan_status") or "") == "pending" and not last_done.get("ok"):
            out.append("ensure_pending_long")

    for e in kinds("shadowing_chunks_build_done") + kinds("shadowing_build_round"):
        err = str(
            _details(e).get("error")
            or e.get("code")
            or _details(e).get("error_code")
            or ""
        )
        if err in BUILD_API_ERRORS:
            out.append("build_api_fail")
            break
        if err == "cap_hit":
            out.append("build_cap_hit")
            break

    boot_dones = kinds("shadowing_boot_done")
    for b in boot_dones:
        code = str(_details(b).get("error_code") or b.get("code") or "")
        if code == "cap_hit":
            out.append("build_cap_hit")
        d = _details(b)
        chunk_n = int(d.get("chunk_n") or 0)
        plan_st = str(d.get("plan_status") or "")
        if b.get("ok") and chunk_n >= 1:
            out.append("accept_prep_ok")
        elif plan_st == "ok" and chunk_n == 0:
            out.append("plan_ok_chunk_empty")
            # sid bind miss when server had sentences
            gets = kinds("shadowing_chunks_get")
            if gets:
                sn = int(_details(gets[-1]).get("sentence_n") or 0)
                if sn > 0:
                    out.append("sid_bind_miss")
            else:
                out.append("sid_bind_miss")

    gemini_starts = kinds("shadowing_gemini_call_start")
    gemini_dones = kinds("shadowing_gemini_call_done")
    if gemini_starts:
        last_s = gemini_starts[-1]
        done_after = [d for d in gemini_dones if _ts(d) >= _ts(last_s)]
        if not done_after:
            hang_limit = float(budget_s) + GEMINI_HANG_SLACK_S
            if now - _ts(last_s) >= hang_limit:
                out.append("server_gemini_hang")

    boot_starts = kinds("shadowing_boot_start")
    if boot_starts and not boot_dones:
        last = boot_starts[-1]
        age = now - _ts(last)
        terminal = bool(gates) or any(
            str(_details(e).get("error") or e.get("code") or "") in BUILD_API_ERRORS
            for e in kinds("shadowing_chunks_build_done")
            + kinds("shadowing_build_round")
        )
        if age >= PREP_STUCK_S and not terminal:
            out.append("prep_ui_stuck")

    for e in kinds("shadowing_loop_event"):
        phase = str(_details(e).get("phase") or "")
        if e.get("ok") is False:
            if phase == "tts":
                out.append("loop_tts_fail")
            elif phase in ("mic_start", "mic_stop"):
                out.append("loop_mic_fail")

    # De-dupe preserve order
    seen: set[str] = set()
    uniq: list[str] = []
    for v in out:
        if v not in seen:
            seen.add(v)
            uniq.append(v)
    return uniq
