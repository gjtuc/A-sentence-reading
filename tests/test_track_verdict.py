"""design/169k — track verdict rules (pure, no adb)."""

from __future__ import annotations

from sentence_reading.llm.track_verdict import (
    JobTimeline,
    check_169j_section_pass,
    compute_verdicts,
)


def _ev(kind: str, ts: str, **details) -> dict:
    return {"kind": kind, "ts": ts, "details": dict(details), "ok": True}


def test_169j_title_pass_within_5s() -> None:
    events = [
        _ev("translate_call_done", "2026-09-01T16:24:51Z", call_kind="harmonize", section="title"),
        _ev("checkpoint", "2026-09-01T16:24:52Z", checkpoint="harmonize_pool_tick", section="title", remaining=0),
    ]
    tl = JobTimeline.from_events(events)
    assert check_169j_section_pass(tl, "title") is True
    verdicts = compute_verdicts(tl, ui_pct=90, open_hangs=[], silence_s=2, prev={})
    assert any("accept_169j_title" in v for v in verdicts)


def test_169j_title_fail_no_pool_end() -> None:
    events = [
        _ev("translate_call_done", "2026-09-01T16:24:51Z", call_kind="harmonize", section="title"),
        _ev("progress_view", "2026-09-01T16:26:00Z"),
    ]
    tl = JobTimeline.from_events(events)
    assert check_169j_section_pass(tl, "title") is False


def test_zombie_worker_after_terminal() -> None:
    events = [
        {
            "kind": "server_job_terminal_error",
            "ts": "2026-09-01T16:32:46Z",
            "details": {"reason_enum": "worker_lost"},
            "ok": False,
        },
        _ev("checkpoint", "2026-09-01T16:33:18Z", checkpoint="harmonize_pool_tick", section="introduction"),
    ]
    tl = JobTimeline.from_events(events)
    verdicts = compute_verdicts(tl, ui_pct=None, open_hangs=[], silence_s=10, prev={})
    assert any(v.startswith("zombie_worker:") for v in verdicts)
    assert any(v == "worker_lost_terminal" for v in verdicts)


def test_harmonize_pool_active_suppresses_hang_label() -> None:
    events = [
        _ev("translate_call_start", "2026-09-01T16:31:50Z", call_kind="harmonize", section="introduction"),
        _ev("checkpoint", "2026-09-01T16:31:55Z", checkpoint="harmonize_pool_tick", section="introduction", remaining=14),
        _ev("progress_view", "2026-09-01T16:32:00Z"),
    ]
    tl = JobTimeline.from_events(events)
    hangs = ["OPEN harmonize sec=introduction since=16:31:50"]
    verdicts = compute_verdicts(tl, ui_pct=90, open_hangs=hangs, silence_s=5, prev={})
    assert any("harmonize_pool_active" in v for v in verdicts)
    assert not any("hang_suspect" in v for v in verdicts)
