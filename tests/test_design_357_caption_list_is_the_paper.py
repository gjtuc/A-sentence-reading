"""design/357 — the caption list is the paper. Images no caption claimed stay out.

The last chip asked each leftover image what it looked like. This one starts from the
captions the paper printed: if those numbers run 1..N with no gaps, that list is the set
of figures, and an image no caption claimed is the journal's.

No paper text in this file. Synthetic boxes and short ASCII strings only.
"""

from __future__ import annotations

from sentence_reading.pdf.layout_map import LayoutBox, LayoutMap
from sentence_reading.pdf.slot_plan import (
    Slot,
    SlotPlan,
    append_unclaimed_body_slots,
    caption_numbers_are_complete,
    slot_census,
)


def _body(bid: str, y: float, *, kind: str = "figure_body", w: float = 200.0, h: float = 80.0) -> LayoutBox:
    return LayoutBox(
        id=bid,
        page_index=0,
        kind=kind,
        rect={"x0": 50.0, "y0": y, "x1": 50.0 + w, "y1": y + h},
        text="",
    )


def _plan_with_captions(*keys: str) -> SlotPlan:
    slots: list[Slot] = []
    for key in keys:
        kind, n_s = key.split(":")
        slots.append(
            Slot(
                key=key,
                kind=kind,
                n=int(n_s),
                status="filled",
                caption_text=f"{'Figure' if kind == 'fig' else 'Table'} {n_s}.",
                caption_box_id=f"c-{key}",
            )
        )
    return SlotPlan(slots=slots)


def test_one_through_n_with_no_gaps_is_complete() -> None:
    plan = _plan_with_captions("fig:1", "fig:2", "fig:3")
    assert caption_numbers_are_complete(plan, "fig") is True


def test_an_empty_list_is_not_complete() -> None:
    """That is design/321: unlabelled figures must still reach the carousel."""
    assert caption_numbers_are_complete(SlotPlan(), "fig") is False


def test_a_floor_slot_with_no_caption_is_not_a_list() -> None:
    """`build_slot_plan` invents fig:1 when it sees a body. That is not a caption."""
    plan = SlotPlan(slots=[Slot(key="fig:1", kind="fig", n=1, status="empty")])
    assert caption_numbers_are_complete(plan, "fig") is False


def test_a_gap_is_not_complete() -> None:
    plan = _plan_with_captions("fig:1", "fig:3")
    assert caption_numbers_are_complete(plan, "fig") is False


def test_starting_at_two_is_not_complete() -> None:
    plan = _plan_with_captions("fig:2", "fig:3")
    assert caption_numbers_are_complete(plan, "fig") is False


def test_figures_and_tables_are_their_own_lists() -> None:
    plan = _plan_with_captions("fig:1", "fig:2")
    assert caption_numbers_are_complete(plan, "fig") is True
    # design/358 — the paper named figures and no table, so it has no table.
    assert caption_numbers_are_complete(plan, "table") is True


def test_leftovers_are_held_when_the_caption_list_is_complete() -> None:
    """Headshots, banners, badges: no rule about what they look like. Just no caption."""
    layout = LayoutMap(
        boxes=[
            _body("portrait", 40.0, w=114.0, h=141.0),
            _body("banner", 200.0, w=400.0, h=40.0),
        ]
    )
    plan = _plan_with_captions("fig:1", "fig:2", "fig:3")
    added = append_unclaimed_body_slots(layout, plan)
    assert added == 0
    assert not [s for s in plan.slots if s.unnumbered]
    census = slot_census(layout, plan)
    assert census["held_by_caption_list_n"] == 2
    assert census["unnumbered_n"] == 0
    assert census["unused_body_n"] == 2
    # The three captioned slots are untouched.
    assert [s.key for s in plan.slots] == ["fig:1", "fig:2", "fig:3"]


def test_unlabelled_figures_are_still_shown() -> None:
    """design/321 still holds: no caption numbers means the leftovers are the paper."""
    layout = LayoutMap(
        boxes=[
            _body("fb-1", 100.0),
            _body("fb-2", 300.0),
        ]
    )
    plan = SlotPlan(slots=[Slot(key="fig:1", kind="fig", n=1, status="empty")])
    added = append_unclaimed_body_slots(layout, plan)
    assert added == 2
    assert [s.unnumbered for s in plan.slots if s.key != "fig:1"] == [True, True]
    assert slot_census(layout, plan)["held_by_caption_list_n"] == 0


def test_a_gapped_list_still_rescues_leftovers() -> None:
    """A missing Figure 2 is a parsing failure, not a complete paper."""
    layout = LayoutMap(boxes=[_body("maybe-fig2", 100.0)])
    plan = _plan_with_captions("fig:1", "fig:3")
    added = append_unclaimed_body_slots(layout, plan)
    assert added == 1
    assert any(s.unnumbered for s in plan.slots)
    assert slot_census(layout, plan)["held_by_caption_list_n"] == 0


def test_a_paper_that_named_figures_and_no_table_has_no_table() -> None:
    """Nano Letters: Figure 1..4 exist, Table 1 does not. A footer is not a table."""
    layout = LayoutMap(boxes=[_body("tb-1", 100.0, kind="table_body")])
    plan = _plan_with_captions("fig:1", "fig:2")
    added = append_unclaimed_body_slots(layout, plan)
    assert added == 0
    assert not [s for s in plan.slots if s.kind == "table"]
    assert slot_census(layout, plan)["held_by_caption_list_n"] == 1
