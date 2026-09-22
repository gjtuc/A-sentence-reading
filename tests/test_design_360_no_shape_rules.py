"""design/360 - no rule may describe what a figure looks like.

The two furniture detectors guessed a picture's identity from its shape. Journals
place figures at the same spot page after page, so design/338's repeat rule caught
real figures: `1-s2.0-S0926337304006745` prints Fig. 1 on page 3 and Fig. 3 on page 5
one point apart, and both were demoted. Over 88 papers it demoted 137 boxes, 67 with
a numbered caption 4-10pt away.

The paper's caption list already holds unclaimed images back (design/357), so nothing
replaces the detectors.

design/358 fixed the first search's direction and stopped. This is the second stage:
the nearest unclaimed body of the kind the caption names, on the caption's page, in
any direction.
"""

from __future__ import annotations

import sentence_reading.pdf.slot_plan as slot_plan
from sentence_reading.pdf.caption_pairing import fill_from_page_neighbours
from sentence_reading.pdf.layout_map import LayoutBox, LayoutMap
from sentence_reading.pdf.slot_plan import (
    Slot,
    SlotPlan,
    append_unclaimed_body_slots,
    caption_numbers_are_complete,
    slot_census,
)


def _box(
    bid: str,
    kind: str,
    x0: float,
    y0: float,
    x1: float,
    y1: float,
    text: str = "",
    page: int = 0,
) -> LayoutBox:
    return LayoutBox(
        id=bid,
        page_index=page,
        kind=kind,
        rect={"x0": x0, "y0": y0, "x1": x1, "y1": y1},
        text=text,
    )


def _slot(key: str, kind: str, n: int, cap: str = "") -> Slot:
    s = Slot(key=key, kind=kind, n=n)
    if cap:
        s.caption_box_id = cap
        s.caption_text = "x"
        s.status = "partial"
    return s


def test_the_shape_detectors_are_gone() -> None:
    assert not hasattr(slot_plan, "demote_repeating_bodies")
    assert not hasattr(slot_plan, "demote_same_size_unclaimed")


def test_the_census_no_longer_reports_furniture() -> None:
    census = slot_census(LayoutMap(), SlotPlan())
    assert "same_size_chrome_n" not in census
    assert "chrome_body_n" not in census


def test_two_figures_at_the_same_spot_on_two_pages_both_survive() -> None:
    """Applied Catalysis A: Fig. 1 p3 and Fig. 3 p5, one point apart."""
    layout = LayoutMap(
        boxes=[
            _box("f1", "figure_body", 326.6, 68.5, 523.9, 225.5, page=2),
            _box("c1", "figure_caption", 304.1, 232.5, 544.6, 243.3, "Fig. 1. a", page=2),
            _box("f3", "figure_body", 327.8, 67.8, 523.7, 225.4, page=4),
            _box("c3", "figure_caption", 304.2, 231.4, 544.9, 271.0, "Fig. 3. b", page=4),
        ]
    )
    plan = SlotPlan(
        slots=[_slot("fig:1", "fig", 1, "c1"), _slot("fig:3", "fig", 3, "c3")]
    )
    assert fill_from_page_neighbours(layout, plan) == 2
    assert (s1 := plan.slot_by_key("fig:1")) is not None
    assert (s3 := plan.slot_by_key("fig:3")) is not None
    assert s1.body_box_id == "f1"
    assert s3.body_box_id == "f3"


def test_a_table_above_its_caption_is_still_found() -> None:
    """srep41797 pages 4-7: the grid sits ~7pt above the caption."""
    layout = LayoutMap(
        boxes=[
            _box("grid", "table_body", 155.0, 46.3, 489.8, 105.6),
            _box("cap", "table_caption", 154.7, 112.5, 545.3, 134.3, "Table 1. rates"),
        ]
    )
    plan = SlotPlan(slots=[_slot("table:1", "table", 1, "cap")])
    assert fill_from_page_neighbours(layout, plan) == 1
    slot = plan.slot_by_key("table:1")
    assert slot is not None
    assert slot.body_box_id == "grid"
    assert slot.status == "filled"


def test_a_figure_beside_its_caption_is_found() -> None:
    """Science Fig. 1: the plot is in the next column, same band."""
    layout = LayoutMap(
        boxes=[
            _box("cap", "figure_caption", 213, 558, 355, 678, "Fig. 1. oxides"),
            _box("side", "figure_body", 366, 558, 559, 716),
        ]
    )
    plan = SlotPlan(slots=[_slot("fig:1", "fig", 1, "cap")])
    assert fill_from_page_neighbours(layout, plan) == 1
    slot = plan.slot_by_key("fig:1")
    assert slot is not None
    assert slot.body_box_id == "side"


def test_a_lost_table_never_takes_a_figure() -> None:
    layout = LayoutMap(
        boxes=[
            _box("cap", "table_caption", 60, 300, 226, 311, "Table 2. yields"),
            _box("img", "figure_body", 60, 320, 500, 480),
        ]
    )
    plan = SlotPlan(slots=[_slot("table:2", "table", 2, "cap")])
    assert fill_from_page_neighbours(layout, plan) == 0
    slot = plan.slot_by_key("table:2")
    assert slot is not None
    assert not slot.body_box_id


def test_a_body_out_of_line_on_both_axes_is_refused() -> None:
    """Diagonally opposite corner: neither column nor band matches."""
    layout = LayoutMap(
        boxes=[
            _box("cap", "figure_caption", 36, 700, 289, 718, "Fig. 4. cell"),
            _box("far", "figure_body", 320, 60, 560, 300),
        ]
    )
    plan = SlotPlan(slots=[_slot("fig:4", "fig", 4, "cap")])
    assert fill_from_page_neighbours(layout, plan) == 0


def test_a_body_on_another_page_is_refused() -> None:
    layout = LayoutMap(
        boxes=[
            _box("cap", "figure_caption", 36, 700, 289, 718, "Fig. 4. cell", page=3),
            _box("img", "figure_body", 36, 500, 289, 690, page=4),
        ]
    )
    plan = SlotPlan(slots=[_slot("fig:4", "fig", 4, "cap")])
    assert fill_from_page_neighbours(layout, plan) == 0


def test_the_nearer_caption_gets_the_shared_body() -> None:
    """Nearest-first, not lowest-numbered-first."""
    layout = LayoutMap(
        boxes=[
            _box("cap2", "figure_caption", 36, 100, 289, 118, "Fig. 2. a"),
            _box("img", "figure_body", 36, 300, 289, 420),
            _box("cap5", "figure_caption", 36, 430, 289, 448, "Fig. 5. b"),
        ]
    )
    plan = SlotPlan(
        slots=[_slot("fig:2", "fig", 2, "cap2"), _slot("fig:5", "fig", 5, "cap5")]
    )
    assert fill_from_page_neighbours(layout, plan) == 1
    assert (s2 := plan.slot_by_key("fig:2")) is not None
    assert (s5 := plan.slot_by_key("fig:5")) is not None
    assert not s2.body_box_id
    assert s5.body_box_id == "img"


def test_an_uncaptioned_image_is_still_held_by_the_caption_list() -> None:
    """The headshots design/356 removed: design/357 holds them with no shape rule."""
    boxes = [
        _box("f1", "figure_body", 40, 60, 500, 300),
        _box("c1", "figure_caption", 40, 310, 500, 320, "Fig. 1. a"),
    ]
    for i in range(6):
        boxes.append(
            _box("head%d" % i, "figure_body", 40 + i * 10, 400, 154 + i * 10, 542, page=i)
        )
    layout = LayoutMap(boxes=boxes)
    slot = _slot("fig:1", "fig", 1, "c1")
    slot.body_box_id = "f1"
    slot.body_box_ids = ["f1"]
    layout.boxes[0].used_by_slot = "fig:1"
    layout.boxes[1].used_by_slot = "fig:1"
    plan = SlotPlan(slots=[slot])
    assert caption_numbers_are_complete(plan, "fig") is True
    assert append_unclaimed_body_slots(layout, plan) == 0
    census = slot_census(layout, plan)
    assert census["unnumbered_n"] == 0
    assert census["held_by_caption_list_n"] == 6
