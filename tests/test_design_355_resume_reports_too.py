"""design/355 — a resumed paper reported nothing, and said nothing about that.

Two holes, both in the same block.

**The report sat inside the branch a resume skips.** `if not resumed_debone:` guarded the
whole design/321 quality report, so a job that resumed after debone emitted no
`extract_text → sentences_ready` handoff at all. Its *warnings* survived — the payload is
saved after the report ran, so they were restored with it — but the twelve measured values
behind them were absent from the evidence stream for that paper, which is the record used
to tell one paper's failure from another's.

**Its own failure was `except Exception: pass`.** A resume leaves `text_pre_filter` empty,
because it starts from already-filtered pages, so the block raised `no_pre_filter_text`
immediately and the exception was swallowed. A paper whose quality could not be measured
looked exactly like a paper with nothing to report.

The report now runs on both paths, measures what a resume does have — the sentences, the
text they were made from, the stored `ingest_quality` — names what it does not with
`source_coverage_unavailable:resume`, and names its own failure.
"""

from __future__ import annotations

import re
from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "src" / "sentence_reading" / "api" / "app.py"
SRC = APP.read_text(encoding="utf-8")
LINES = SRC.splitlines()


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip())


def _line_of(needle: str) -> int:
    for i, line in enumerate(LINES, 1):
        if needle in line:
            return i
    raise AssertionError(f"not found: {needle}")


def _gate_block() -> tuple[int, int]:
    gate = next(i for i, l in enumerate(LINES, 1) if l.strip() == "if not resumed_debone:")
    base = _indent(LINES[gate - 1])
    for i in range(gate + 1, len(LINES) + 1):
        line = LINES[i - 1]
        if not line.strip():
            continue
        if _indent(line) <= base and line.strip() != "else:":
            return gate, i - 1
    return gate, len(LINES)


def test_the_quality_report_is_not_inside_the_resume_gate() -> None:
    gate, end = _gate_block()
    order = _line_of("_ord = source_order_stats(text_for_sentences, sentences)")
    handoff = _line_of('to_stage="sentences_ready"')
    assert not gate < order <= end, "the order report is back inside the resume branch"
    assert not gate < handoff <= end, "the handoff is back inside the resume branch"


def test_the_report_runs_at_the_same_level_as_the_gate() -> None:
    gate, _end = _gate_block()
    report = _line_of("design/321 — price the extraction stage")
    assert _indent(LINES[report - 1]) == _indent(LINES[gate - 1])


def test_a_failed_report_is_named_rather_than_swallowed() -> None:
    assert 'warnings.append(f"quality_report_failed:{type(exc).__name__}")' in SRC
    # The old shape must not come back anywhere near the report.
    report = _line_of("design/321 — price the extraction stage")
    window = "\n".join(LINES[report - 1 : report + 110])
    assert "except Exception:  # noqa: BLE001\n            pass" not in window


def test_a_resume_says_the_source_census_is_unavailable() -> None:
    """It starts from already-filtered pages, so there is no pre-extraction copy. Saying
    so is the difference between an unmeasurable paper and a clean one."""
    assert 'warnings.append("source_coverage_unavailable:resume")' in SRC


def test_the_handoff_records_which_shape_it_is() -> None:
    report = _line_of("design/321 — price the extraction stage")
    window = "\n".join(LINES[report - 1 : report + 110])
    assert '"resumed": bool(resumed_debone)' in window
    assert '"pre_filter_available": _has_pre' in window


def test_the_order_stats_still_use_the_text_the_sentences_came_from() -> None:
    """design/351. Anchoring in `text_pre_filter` reported 44% on a paper that is 99%
    correct, and on a resume that variable is empty."""
    assert "source_order_stats(text_for_sentences, sentences)" in SRC
    assert "source_order_stats(text_pre_filter, sentences)" not in SRC


def test_the_report_appears_exactly_once() -> None:
    """It was moved, not copied. Two copies would double every warning."""
    assert len(re.findall(r'to_stage="sentences_ready"', SRC)) == 1
    assert SRC.count("_ord = source_order_stats(") == 1
