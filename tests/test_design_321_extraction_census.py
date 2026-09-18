"""design/321 — boundary census + the two silent-loss fixes.

No paper text in this file. Synthetic boxes and short ASCII strings only.
"""

from __future__ import annotations

from pathlib import Path

from sentence_reading.llm.debone_quality import (
    SOURCE_COVERAGE_LOW,
    source_coverage_warnings,
)
from sentence_reading.llm.evidence_verdict import CacheTimeline, compute_figure_verdicts
from sentence_reading.models import Sentence
from sentence_reading.pdf.layout_map import LayoutBox, LayoutMap
from sentence_reading.pdf.slot_plan import (
    Slot,
    SlotPlan,
    append_unclaimed_body_slots,
    build_slot_plan,
    initial_body_assignments,
    refresh_slot_statuses,
    slot_census,
)

ROOT = Path(__file__).resolve().parents[1]


def _body(bid: str, kind: str, y: float) -> LayoutBox:
    return LayoutBox(
        id=bid,
        page_index=0,
        kind=kind,
        rect={"x0": 50.0, "y0": y, "x1": 300.0, "y1": y + 100.0},
        text="",
    )


def _caption(bid: str, y: float, text: str) -> LayoutBox:
    return LayoutBox(
        id=bid,
        page_index=0,
        kind="figure_caption",
        rect={"x0": 50.0, "y0": y, "x1": 300.0, "y1": y + 10.0},
        text=text,
    )


def test_census_counts_bodies_slots_and_statuses():
    layout = LayoutMap(
        boxes=[
            _body("fb-1", "figure_body", 100.0),
            _body("fb-2", "figure_body", 300.0),
            _body("tb-1", "table_body", 500.0),
        ]
    )
    plan = SlotPlan(
        slots=[
            Slot(key="fig:1", kind="fig", n=1, status="filled"),
            Slot(key="fig:2", kind="fig", n=2, status="partial"),
            Slot(key="table:1", kind="table", n=1, status="empty"),
        ]
    )
    layout.boxes[0].used_by_slot = "fig:1"
    census = slot_census(layout, plan)
    assert census["body_n"] == 3
    assert census["slot_n"] == 3
    assert census["filled_n"] == 1
    assert census["partial_n"] == 1
    assert census["empty_n"] == 1
    # fb-2 and tb-1 were never claimed — that is the silent drop.
    assert census["unused_body_n"] == 2


def test_census_counts_user_confirmed_as_filled():
    layout = LayoutMap(boxes=[_body("fb-1", "figure_body", 100.0)])
    layout.boxes[0].used_by_slot = "fig:1"
    plan = SlotPlan(
        slots=[Slot(key="fig:1", kind="fig", n=1, status="user_confirmed")]
    )
    census = slot_census(layout, plan)
    assert census["filled_n"] == 1
    assert census["empty_n"] == 0
    assert census["unused_body_n"] == 0


def test_unnumbered_captions_no_longer_collapse_bodies_into_one_slot():
    # Three figure bodies, no parseable caption number anywhere.
    layout = LayoutMap(
        boxes=[
            _body("fb-1", "figure_body", 100.0),
            _body("fb-2", "figure_body", 300.0),
            _body("fb-3", "figure_body", 500.0),
        ]
    )
    plan = build_slot_plan(layout)
    # Old behaviour: the body floor is exactly 1, so one slot for three bodies.
    assert len(plan.slots) == 1

    initial_body_assignments(layout, plan)
    added = append_unclaimed_body_slots(layout, plan)
    refresh_slot_statuses(plan)

    assert added == 3
    assert len(plan.slots) == 4
    # Every body now belongs to a slot, so nothing is dropped.
    assert slot_census(layout, plan)["unused_body_n"] == 0
    # Appended slots carry a body, so they render a crop and are not placeholders.
    assert all(s.status != "empty" for s in plan.slots if s.body_box_id)


def test_appended_slots_keep_figures_before_tables():
    layout = LayoutMap(
        boxes=[
            _body("tb-1", "table_body", 100.0),
            _body("fb-1", "figure_body", 300.0),
        ]
    )
    plan = build_slot_plan(layout)
    initial_body_assignments(layout, plan)
    append_unclaimed_body_slots(layout, plan)
    kinds = [s.kind for s in plan.slots]
    assert kinds == sorted(kinds, key=lambda k: 0 if k == "fig" else 1)


def test_numbered_captions_keep_their_own_slots():
    layout = LayoutMap(
        boxes=[
            _body("fb-1", "figure_body", 100.0),
            _caption("fc-1", 205.0, "Figure 2. short label"),
        ]
    )
    plan = build_slot_plan(layout)
    assert [s.key for s in plan.slots] == ["fig:1", "fig:2"]
    initial_body_assignments(layout, plan)
    before = [s.key for s in plan.slots]
    append_unclaimed_body_slots(layout, plan)
    # The body matched fig:2 by caption number, so no slot is invented.
    assert [s.key for s in plan.slots] == before


def test_supplementary_appended_slots_use_s_keys():
    layout = LayoutMap(
        boxes=[
            _body("fb-1", "figure_body", 100.0),
            _body("fb-2", "figure_body", 300.0),
        ]
    )
    plan = build_slot_plan(layout, supplementary=True)
    initial_body_assignments(layout, plan, supplementary=True)
    append_unclaimed_body_slots(layout, plan, supplementary=True)
    assert all(s.key.startswith("fig:s") for s in plan.slots if s.kind == "fig")


def test_source_coverage_warnings_name_the_stage_that_lost_text():
    # Debone looks perfect against what it was handed; the loss is upstream.
    w = source_coverage_warnings(source_coverage=0.40, debone_coverage=0.95)
    assert any(x.startswith("source_coverage_low:") for x in w)
    assert any(x.startswith("extract_filter_gap:") for x in w)

    # Both low → debone is the one that lost it, so no filter-gap claim.
    w2 = source_coverage_warnings(source_coverage=0.40, debone_coverage=0.42)
    assert any(x.startswith("source_coverage_low:") for x in w2)
    assert not any(x.startswith("extract_filter_gap:") for x in w2)

    # Healthy paper stays quiet.
    assert source_coverage_warnings(source_coverage=0.98, debone_coverage=0.99) == []


def test_source_coverage_low_threshold_is_the_debone_one():
    assert SOURCE_COVERAGE_LOW == 0.50
    w = source_coverage_warnings(source_coverage=0.60, debone_coverage=0.62)
    assert any(x.startswith("source_coverage_warn:") for x in w)


def _tl(details: dict) -> CacheTimeline:
    return CacheTimeline(
        cache_id="c1",
        events=[
            {
                "kind": "figure_extract_done",
                "ts": "2026-09-18T10:00:00Z",
                "cache_id": "c1",
                "details": details,
            }
        ],
    )


def test_verdict_names_unslotted_bodies_and_collapse():
    out = compute_figure_verdicts(
        _tl({"body_n": 8, "slot_n": 5, "unused_body_n": 3, "partial_n": 0})
    )
    assert any(v.startswith("figure_body_unslotted:") for v in out)
    assert any(v.startswith("figure_slot_collapse:") for v in out)


def test_verdict_quiet_when_every_body_has_a_slot():
    out = compute_figure_verdicts(
        _tl({"body_n": 5, "slot_n": 5, "unused_body_n": 0, "partial_n": 0})
    )
    assert not any(v.startswith("figure_body_unslotted") for v in out)
    assert not any(v.startswith("figure_slot_collapse") for v in out)


def test_verdict_needs_a_body_count_to_speak():
    assert compute_figure_verdicts(_tl({"unused_body_n": 3})) == []


def test_supplementary_merge_keeps_quality_flags():
    src = (ROOT / "src/sentence_reading/api/supplementary_merge.py").read_text(
        encoding="utf-8"
    )
    assert "quality_flags=getattr(s, \"quality_flags\", ()) or ()" in src


def test_vision_blank_return_keeps_the_pymupdf_page():
    src = (ROOT / "src/sentence_reading/llm/vision_ocr.py").read_text(
        encoding="utf-8"
    )
    # A blank OCR answer must not overwrite a page PyMuPDF could read.
    assert "blank_kept" in src
    assert "vision_blank_kept:" in src
    assert 'if not fresh and (working[page_index] or "").strip():' in src


def test_slot_census_is_wired_into_figure_extract_done():
    app = (ROOT / "src/sentence_reading/api/app.py").read_text(encoding="utf-8")
    for field in ("body_n", "slot_n", "empty_n", "partial_n", "unused_body_n"):
        assert f'"{field}": int(_slot_census.get(' in app
    # The pre-filter copy must be taken on the fresh-extract path only.
    assert "text_pre_filter = text" in app
    assert 'raise ValueError("no_pre_filter_text")' in app
