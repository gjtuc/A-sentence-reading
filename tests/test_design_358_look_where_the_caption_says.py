"""design/358 — look where the caption says, and only make slots captions name.

The refill that fills an empty caption slot had the directions backwards: figures
searched below, tables searched above. Fig. 3's timeline sat 4pt above its caption
and Table 1's grid sat 4pt below, and both were skipped.

A `table_body` is not a caption. Raising a floor slot to `table:1` because Azure
tagged a footer invented Nano Letters' empty Table 1.

Science Fig. 1 sits beside its caption. That is not this chip — the reader edits it.
"""

from __future__ import annotations

from sentence_reading.pdf.caption_pairing import refill_empty_slots
from sentence_reading.pdf.layout_map import LayoutBox, LayoutMap
from sentence_reading.pdf.slot_plan import (
    Slot,
    SlotPlan,
    build_slot_plan,
    caption_numbers_are_complete,
    refresh_slot_statuses,
)


def _box(
    bid: str,
    kind: str,
    x0: float,
    y0: float,
    x1: float,
    y1: float,
    text: str = "",
) -> LayoutBox:
    return LayoutBox(
        id=bid,
        page_index=0,
        kind=kind,
        rect={"x0": x0, "y0": y0, "x1": x1, "y1": y1},
        text=text,
    )


def test_a_figure_is_taken_from_above_the_caption() -> None:
    """RSC Fig. 3: timeline 4pt above the caption, nothing below."""
    layout = LayoutMap(
        boxes=[
            _box("img", "figure_body", 85, 577, 510, 702),
            _box("cap", "figure_caption", 42, 706, 255, 716, "Fig. 3. overview"),
        ]
    )
    layout.boxes[1].used_by_slot = "fig:3"
    plan = SlotPlan(
        slots=[
            Slot(
                key="fig:3",
                kind="fig",
                n=3,
                status="partial",
                caption_box_id="cap",
                caption_text="Fig. 3. overview",
            )
        ]
    )
    refill_empty_slots(layout, plan)
    refresh_slot_statuses(plan)
    slot = plan.slot_by_key("fig:3")
    assert slot is not None
    assert slot.body_box_id == "img"
    assert slot.status == "filled"


def test_a_table_is_taken_from_below_the_caption() -> None:
    """ACS Table 1: grid 4pt below the caption, nothing above."""
    layout = LayoutMap(
        boxes=[
            _box("cap", "table_caption", 60, 68, 226, 79, "Table 1. properties"),
            _box("grid", "table_body", 60, 83, 565, 205),
        ]
    )
    layout.boxes[0].used_by_slot = "table:1"
    plan = SlotPlan(
        slots=[
            Slot(
                key="table:1",
                kind="table",
                n=1,
                status="partial",
                caption_box_id="cap",
                caption_text="Table 1. properties",
            )
        ]
    )
    refill_empty_slots(layout, plan)
    refresh_slot_statuses(plan)
    slot = plan.slot_by_key("table:1")
    assert slot is not None
    assert slot.body_box_id == "grid"
    assert slot.status == "filled"


def test_a_figure_beside_the_caption_is_left_alone() -> None:
    """Science Fig. 1: the plot is to the right, same band. The reader edits it."""
    layout = LayoutMap(
        boxes=[
            _box("cap", "figure_caption", 213, 558, 355, 678, "Fig. 1. oxides"),
            _box("side", "figure_body", 366, 558, 559, 716),
        ]
    )
    plan = SlotPlan(
        slots=[
            Slot(
                key="fig:1",
                kind="fig",
                n=1,
                status="partial",
                caption_box_id="cap",
                caption_text="Fig. 1. oxides",
            )
        ]
    )
    refill_empty_slots(layout, plan)
    slot = plan.slot_by_key("fig:1")
    assert slot is not None
    assert not slot.body_box_id


def test_a_body_without_a_caption_does_not_invent_table_one() -> None:
    layout = LayoutMap(
        boxes=[_box("footer", "table_body", 322, 720, 427, 757)]
    )
    plan = build_slot_plan(layout)
    assert plan.slots == []
    assert caption_numbers_are_complete(plan, "table") is False
