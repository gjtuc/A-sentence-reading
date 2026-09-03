"""design/169p — shadowing_verdict catalog."""

from __future__ import annotations

from sentence_reading.llm.shadowing_verdict import (
    ShadowingTimeline,
    compute_shadowing_verdicts,
)


def _ev(kind: str, *, ts: str, cache_id: str = "abc12345", **kw):
    row = {"kind": kind, "ts": ts, "cache_id": cache_id}
    row.update(kw)
    return row


def test_gate_kill_and_pref() -> None:
    tl = ShadowingTimeline.from_events(
        [
            _ev(
                "shadowing_gate",
                ts="2026-09-03T01:00:00+00:00",
                ok=False,
                details={"gate": "kill_off"},
            ),
            _ev(
                "shadowing_gate",
                ts="2026-09-03T01:00:01+00:00",
                ok=False,
                details={"gate": "pref_off"},
            ),
        ]
    )
    v = compute_shadowing_verdicts(tl)
    assert "gate_kill_off" in v
    assert "gate_pref_off" in v


def test_accept_prep_ok() -> None:
    tl = ShadowingTimeline.from_events(
        [
            _ev("shadowing_boot_start", ts="2026-09-03T01:00:00+00:00"),
            _ev(
                "shadowing_boot_done",
                ts="2026-09-03T01:00:05+00:00",
                ok=True,
                details={"plan_status": "ok", "chunk_n": 3, "rounds": 1},
            ),
        ]
    )
    assert compute_shadowing_verdicts(tl) == ["accept_prep_ok"]


def test_sid_bind_miss() -> None:
    tl = ShadowingTimeline.from_events(
        [
            _ev(
                "shadowing_chunks_get",
                ts="2026-09-03T01:00:00+00:00",
                details={"plan_status": "ok", "sentence_n": 10},
            ),
            _ev(
                "shadowing_boot_done",
                ts="2026-09-03T01:00:02+00:00",
                ok=False,
                details={"plan_status": "ok", "chunk_n": 0, "error_code": "chunk_empty"},
            ),
        ]
    )
    v = compute_shadowing_verdicts(tl)
    assert "plan_ok_chunk_empty" in v
    assert "sid_bind_miss" in v


def test_build_api_fail() -> None:
    tl = ShadowingTimeline.from_events(
        [
            _ev(
                "shadowing_chunks_build_done",
                ts="2026-09-03T01:00:00+00:00",
                ok=False,
                code="gemini_unavailable",
                details={"error": "gemini_unavailable"},
            ),
        ]
    )
    assert "build_api_fail" in compute_shadowing_verdicts(tl)


def test_build_cap_hit() -> None:
    tl = ShadowingTimeline.from_events(
        [
            _ev(
                "shadowing_ensure_done",
                ts="2026-09-03T01:00:00+00:00",
                ok=False,
                details={"error_code": "cap_hit", "rounds": 40},
            ),
        ]
    )
    assert "build_cap_hit" in compute_shadowing_verdicts(tl)


def test_prep_ui_stuck() -> None:
    from datetime import datetime, timezone

    tl = ShadowingTimeline.from_events(
        [
            _ev("shadowing_boot_start", ts="2026-09-03T01:00:00+00:00"),
        ]
    )
    t0 = datetime(2026, 9, 3, 1, 0, 0, tzinfo=timezone.utc).timestamp()
    v = compute_shadowing_verdicts(tl, now_ts=t0 + 200)
    assert "prep_ui_stuck" in v


def test_server_gemini_hang() -> None:
    from datetime import datetime, timezone

    t0 = datetime(2026, 9, 3, 1, 0, 0, tzinfo=timezone.utc).timestamp()
    tl = ShadowingTimeline.from_events(
        [
            _ev(
                "shadowing_gemini_call_start",
                ts="2026-09-03T01:00:00+00:00",
                details={"call_kind": "chunk_plan"},
            ),
        ]
    )
    v = compute_shadowing_verdicts(tl, now_ts=t0 + 90 + 40, budget_s=90)
    assert "server_gemini_hang" in v


def test_loop_mic_fail() -> None:
    tl = ShadowingTimeline.from_events(
        [
            _ev(
                "shadowing_boot_done",
                ts="2026-09-03T01:00:00+00:00",
                ok=True,
                details={"plan_status": "ok", "chunk_n": 2},
            ),
            _ev(
                "shadowing_loop_event",
                ts="2026-09-03T01:00:05+00:00",
                ok=False,
                details={"phase": "mic_start", "ok": False},
            ),
        ]
    )
    v = compute_shadowing_verdicts(tl)
    assert "accept_prep_ok" in v
    assert "loop_mic_fail" in v
