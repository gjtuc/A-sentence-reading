"""design/169l L0 — evidence_verdict figure rules (pure, no pull)."""

from __future__ import annotations

from sentence_reading.llm.evidence_verdict import (
    CacheTimeline,
    compute_cache_verdicts,
    compute_figure_verdicts,
    figure_meta_broken,
)


def _ev(kind: str, ts: str, *, cache_id: str = "abc123456789", **details) -> dict:
    row: dict = {
        "kind": kind,
        "ts": ts,
        "cache_id": cache_id,
        "details": dict(details),
        "ok": True,
    }
    return row


def test_figure_meta_broken_bad_file_rel_after_open() -> None:
    """Replay pattern: open ko complete, then bad_file_rel + window empty."""
    cid = "4ba79db36946"
    events = [
        _ev(
            "open_ko_summary",
            "2026-09-02T00:55:34Z",
            cache_id=cid,
            sentence_n=286,
            ko_sentence_n=286,
            figure_n=14,
            ko_figure_n=14,
        ),
        _ev(
            "figure_data_url_miss",
            "2026-09-02T00:55:37Z",
            cache_id=cid,
            reason="bad_file_rel",
        ),
        _ev(
            "figure_window_empty",
            "2026-09-02T00:55:44Z",
            cache_id=cid,
            empty_n=3,
            session_n=14,
            ok=False,
        ),
        _ev(
            "figure_window_res",
            "2026-09-02T00:57:14Z",
            cache_id=cid,
            source="mobile",
            empty_n=3,
            window_n=3,
            ok=False,
        ),
    ]
    tl = CacheTimeline.from_events(cid, events)
    assert figure_meta_broken(tl)
    verdicts = compute_figure_verdicts(tl)
    assert any(v.startswith("figure_meta_broken") for v in verdicts)
    assert any(v == "translate_ok_figure_broken: KO complete but PNG meta/read fail" for v in verdicts)


def test_figure_file_rel_n_gap_on_open() -> None:
    cid = "cache001234567"
    events = [
        _ev(
            "open_ko_summary",
            "2026-09-02T01:00:00Z",
            cache_id=cid,
            figure_n=14,
            ko_figure_n=14,
            figure_file_rel_n=0,
        ),
    ]
    tl = CacheTimeline.from_events(cid, events)
    verdicts = compute_figure_verdicts(tl)
    assert any("figure_meta_broken: file_rel 0/14" in v for v in verdicts)


def test_figure_read_stuck_three_empty_res() -> None:
    cid = "cache001234567"
    events = [
        _ev("open_ko_summary", "2026-09-02T01:00:00Z", cache_id=cid, figure_n=5),
        _ev("figure_window_res", "2026-09-02T01:01:00Z", cache_id=cid, empty_n=2, window_n=2, ok=False),
        _ev("figure_window_res", "2026-09-02T01:02:00Z", cache_id=cid, empty_n=3, window_n=3, ok=False),
        _ev("figure_window_res", "2026-09-02T01:03:00Z", cache_id=cid, empty_n=1, window_n=1, ok=False),
    ]
    tl = CacheTimeline.from_events(cid, events)
    verdicts = compute_figure_verdicts(tl)
    assert any(v.startswith("figure_read_stuck") for v in verdicts)


def test_preserve_gap_gen_bump_no_vision_write() -> None:
    cid = "4ba79db36946"
    events = [
        _ev(
            "artifact_derive",
            "2026-09-02T00:55:13Z",
            cache_id=cid,
            gen=3,
            activity="local_write_session",
        ),
        _ev(
            "open_ko_summary",
            "2026-09-02T00:55:34Z",
            cache_id=cid,
            figure_n=14,
            ko_figure_n=14,
        ),
        _ev(
            "figure_data_url_miss",
            "2026-09-02T00:55:37Z",
            cache_id=cid,
            reason="bad_file_rel",
        ),
    ]
    tl = CacheTimeline.from_events(cid, events)
    verdicts = compute_figure_verdicts(tl)
    assert any(v.startswith("preserve_gap") for v in verdicts)


def test_compute_cache_verdicts_wrapper() -> None:
    cid = "x" * 12
    events = [
        _ev("open_ko_summary", "2026-09-02T01:00:00Z", cache_id=cid, figure_n=1, ko_figure_n=1, figure_file_rel_n=0),
    ]
    verdicts, last = compute_cache_verdicts(cid, events)
    assert verdicts
    assert last
