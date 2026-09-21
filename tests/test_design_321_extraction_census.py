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
    # design/358 — a body is not a caption. No parsed number means no numbered slot.
    assert len(plan.slots) == 0

    initial_body_assignments(layout, plan)
    added = append_unclaimed_body_slots(layout, plan)
    refresh_slot_statuses(plan)

    assert added == 3
    assert len(plan.slots) == 3
    # Every body now belongs to a slot, so nothing is dropped.
    assert slot_census(layout, plan)["unused_body_n"] == 0
    # Appended slots carry a body, so they render a crop and are not placeholders.
    assert all(s.status != "empty" for s in plan.slots if s.body_box_id)


def test_appended_slots_are_marked_unnumbered():
    # design/324 — a rescued body must not claim the next figure number.
    layout = LayoutMap(
        boxes=[
            _body("fb-1", "figure_body", 100.0),
            _body("fb-2", "figure_body", 300.0),
            _body("tb-1", "table_body", 500.0),
        ]
    )
    plan = build_slot_plan(layout)
    initial_body_assignments(layout, plan)
    append_unclaimed_body_slots(layout, plan)
    appended = [s for s in plan.slots if s.unnumbered]
    assert appended, "expected rescued slots"
    assert all(s.body_box_id for s in appended)
    # Round-trip keeps the flag so a reopened plan still tells the truth.
    from sentence_reading.pdf.slot_plan import SlotPlan as SP

    again = SP.from_dict(plan.to_dict())
    assert [s.unnumbered for s in again.slots] == [s.unnumbered for s in plan.slots]


def test_unnumbered_caption_does_not_assert_a_figure_number():
    from sentence_reading.pdf.composite import slot_unnumbered_caption

    fig = slot_unnumbered_caption("fig")
    tbl = slot_unnumbered_caption("table")
    assert fig == "번호 없는 그림"
    assert tbl == "번호 없는 표"
    for s in (fig, tbl):
        assert not any(ch.isdigit() for ch in s)


def test_caption_numbered_slots_are_not_marked_unnumbered():
    layout = LayoutMap(
        boxes=[
            _body("fb-1", "figure_body", 100.0),
            _caption("fc-1", 205.0, "Figure 2. short label"),
        ]
    )
    plan = build_slot_plan(layout)
    initial_body_assignments(layout, plan)
    append_unclaimed_body_slots(layout, plan)
    assert all(not s.unnumbered for s in plan.slots)


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


def test_design_330_references_leave_the_coverage_denominator():
    """A bibliography is never practice text, so it must not read as loss."""
    from sentence_reading.llm.debone_quality import (
        compute_coverage_ratio,
        coverage_excluding_references,
        practice_text_only,
    )

    body = " ".join(f"alpha{i} beta{i} gamma{i}" for i in range(40))
    refs = "\n".join(
        f"{i}. A. Author, B. Author, J. Chem. Phys. {100 + i}, {i * 7} (20{i:02d})."
        for i in range(1, 26)
    )
    raw = f"{body}\n\nReferences\n{refs}\n"
    sents = [
        Sentence(id=str(i), text=f"alpha{i} beta{i} gamma{i}", section="results")
        for i in range(40)
    ]

    practice = practice_text_only(raw)
    assert len(practice) < len(raw), "the bibliography should be cut"
    assert "alpha0" in practice

    old = compute_coverage_ratio(raw, sents)
    new = coverage_excluding_references(raw, sents)
    assert new > old
    assert new > 0.95


def test_design_330_cut_is_a_noop_without_a_bibliography():
    from sentence_reading.llm.debone_quality import practice_text_only

    plain = "The catalyst was stable. Conversion rose with temperature."
    assert practice_text_only(plain) == plain


def test_design_333_reference_tokens_are_not_subtracted():
    """design/331 subtracted Azure's reference tokens; that was unsound.

    A reference title carries the paper's own topic words, so removing those
    tokens strips body vocabulary too. On srep41797 the denominator collapsed from
    about 600 tokens to 40. The bibliography is removed by cutting the text.
    """
    from sentence_reading.llm.debone_quality import coverage_excluding_references

    body = " ".join(f"alpha{i} beta{i}" for i in range(30))
    refs = " ".join(f"zeta{i} omega{i}" for i in range(30))
    raw = f"{body} {refs}"
    sents = [
        Sentence(id=str(i), text=f"alpha{i} beta{i}", section="results")
        for i in range(30)
    ]
    # Passing references_text must not change the answer any more.
    assert coverage_excluding_references(
        raw, sents
    ) == coverage_excluding_references(raw, sents, references_text=refs)


def test_design_333_a_tiny_denominator_is_not_reported_as_a_ratio():
    from sentence_reading.llm.debone_quality import (
        COVERAGE_MIN_DENOM_TOKENS,
        coverage_is_measurable,
        source_coverage_warnings,
    )

    assert coverage_is_measurable(COVERAGE_MIN_DENOM_TOKENS) is True
    assert coverage_is_measurable(9) is False
    w = source_coverage_warnings(
        source_coverage=0.55, debone_coverage=0.9, denom_tokens=9
    )
    assert w == ["coverage_denom_too_small:9"]
    # With a real denominator the normal warnings still fire.
    w2 = source_coverage_warnings(
        source_coverage=0.40, debone_coverage=0.95, denom_tokens=800
    )
    assert any(x.startswith("source_coverage_low:") for x in w2)


def test_design_333_back_matter_and_page_chrome_leave_the_denominator():
    from sentence_reading.llm.debone_quality import strip_back_matter

    body = "The catalyst was stable. " * 40
    raw = (
        f"{body}\n"
        "SCIENTIFIC REPORTS | 7:41797 | DOI: 10.1038/srep41797 www.nature.com/x\n"
        f"{body}\n"
        "Author Contributions\n"
        "Q.L. supervised the work and prepared the manuscript.\n"
        "This work is licensed under a Creative Commons Attribution 4.0 License.\n"
    )
    out = strip_back_matter(raw)
    assert "nature.com" not in out
    assert "Creative Commons" not in out
    assert "Author Contributions" not in out
    assert "The catalyst was stable." in out


def test_design_333_back_matter_cut_ignores_an_early_heading():
    """A file with two articles carries another paper's back matter up top."""
    from sentence_reading.llm.debone_quality import strip_back_matter

    tail_of_other_paper = "Supplementary information\nFigs. S1 to S4\n"
    target = "The design of cost-effective catalysts matters. " * 60
    out = strip_back_matter(tail_of_other_paper + target)
    assert "cost-effective" in out, "the target paper must survive"


def test_design_331_shared_tokens_stay_in_the_denominator():
    """A body loss must not hide behind a word the references also use."""
    from sentence_reading.llm.debone_quality import coverage_excluding_references

    raw = "catalyst alpha beta gamma delta catalyst epsilon"
    refs = "catalyst"
    # Sentences cover only `catalyst`, missing the rest of the body.
    sents = [Sentence(id="1", text="catalyst", section="results")]
    ratio = coverage_excluding_references(raw, sents, references_text=refs)
    assert ratio < 0.4, ratio


def test_design_331_recover_result_carries_references():
    from sentence_reading.llm.vision_ocr import RecoverResult

    r = RecoverResult(text="t", pages=["t"])
    assert r.references_text == ""
    r2 = RecoverResult(text="t", pages=["t"], references_text="refs here")
    assert r2.references_text == "refs here"


def test_design_331_denominator_size_is_reported():
    from sentence_reading.llm.debone_quality import practice_token_n

    raw = "alpha beta gamma delta epsilon"
    assert practice_token_n(raw) == 5
    # design/333 — references_text is reported, never subtracted.
    assert practice_token_n(raw, "delta epsilon") == 5

    app = (ROOT / "src/sentence_reading/api/app.py").read_text(encoding="utf-8")
    assert '"azure_refs_chars": len(_refs_text or "")' in app
    assert '"practice_token_n": _denom_n' in app
    assert "_denom_n = practice_token_n(" in app


def test_design_330_denominator_is_reported_on_the_handoff():
    app = (ROOT / "src/sentence_reading/api/app.py").read_text(encoding="utf-8")
    assert '"practice_chars": len(_practice or "")' in app
    assert '"refs_share"' in app


def test_slot_census_is_wired_into_figure_extract_done():
    app = (ROOT / "src/sentence_reading/api/app.py").read_text(encoding="utf-8")
    for field in ("body_n", "slot_n", "empty_n", "partial_n", "unused_body_n"):
        assert f'"{field}": int(_slot_census.get(' in app
    # The pre-filter copy must be taken on the fresh-extract path only.
    assert "text_pre_filter = text" in app
    # The guarantee: with no pre-extraction copy, no source coverage is computed — a
    # ratio against the filtered text would read a false 1.0.
    #
    # design/355 changed how that is expressed. It used to `raise ValueError` into an
    # `except Exception: pass`, which also threw away the rest of the report and left a
    # resumed paper with no handoff and no explanation. Now the computation is gated and
    # the absence is named, so the report still runs and still refuses the false ratio.
    assert '_has_pre = bool((text_pre_filter or "").strip())' in app
    assert "if _has_pre:" in app
    assert 'warnings.append("source_coverage_unavailable:resume")' in app
    assert 'raise ValueError("no_pre_filter_text")' not in app
