"""design/359 — the caption's x-range is the column, and one box can be two figures.

Two faults shared one wrong question. design/338 asked "how much of the *body* sits
inside the caption's x-range", so a one-line caption could never reach the floor over
a full-width table: Catal. Sci. Technol.'s Table 8 caption covered 0.33 of its own
table and the pair was thrown away, and the s0167 chapter handed Table 3's table to
Table 2 because Table 2's caption ran two lines and covered more of it from 112pt
away. Asking about the narrower of the two answers both.

Engineering (Beijing) prints Fig. 6 and Fig. 7 side by side and Azure returns one
513pt box for both. Fig. 6 took the whole box and Fig. 7 rendered `(missing)`.
Where the paper printed two captions of one kind beside each other, the gap between
them is the cut.

A full-width table under a single one-line caption must *not* be cut. Nothing in
d3cy's Table 8 caption width says where a column ends; only a second caption does.
"""
from __future__ import annotations

from sentence_reading.pdf.layout_map import LayoutBox, LayoutMap
from sentence_reading.pdf.slot_plan import (
    Slot,
    SlotPlan,
    append_unclaimed_body_slots,
    initial_body_assignments,
    refresh_slot_statuses,
    slot_census,
    split_shared_column_bodies,
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


def _slot(key: str, kind: str, n: int) -> Slot:
    return Slot(key=key, kind=kind, n=n)


def test_a_one_line_caption_keeps_its_own_full_width_table() -> None:
    """d3cy page 12: caption 167pt, table 513pt. 167/513 used to be 0.33."""
    layout = LayoutMap(
        boxes=[
            _box("cap8", "table_caption", 41.6, 47.6, 209.0, 57.4, "Table 8. yields"),
            _box("tb8", "table_body", 39.9, 59.9, 553.5, 148.2),
        ]
    )
    plan = SlotPlan(slots=[_slot("table:8", "table", 8)])
    initial_body_assignments(layout, plan)
    slot = plan.slot_by_key("table:8")
    assert slot is not None
    assert slot.body_box_id == "tb8"


def test_the_nearer_caption_wins_even_when_its_line_is_shorter() -> None:
    """s0167 page 3: Table 3's caption is 1.2pt away, Table 2's is 112pt away."""
    layout = LayoutMap(
        boxes=[
            _box("cap2", "table_caption", 41.3, 59.4, 266.5, 70.3, "Table 2. rates"),
            _box("tb2", "table_body", 41.1, 69.7, 423.4, 151.0),
            _box("cap3", "table_caption", 41.3, 173.4, 207.7, 184.1, "Table 3. feeds"),
            _box("tb3", "table_body", 40.6, 182.9, 423.0, 253.7),
        ]
    )
    plan = SlotPlan(
        slots=[_slot("table:2", "table", 2), _slot("table:3", "table", 3)]
    )
    initial_body_assignments(layout, plan)
    assert (t2 := plan.slot_by_key("table:2")) is not None
    assert (t3 := plan.slot_by_key("table:3")) is not None
    assert t2.body_box_ids == ["tb2"]
    assert t3.body_box_ids == ["tb3"]


def test_a_body_in_the_other_column_is_still_refused() -> None:
    """A left-column caption and a right-column image share no x at all."""
    layout = LayoutMap(
        boxes=[
            _box("cap", "figure_caption", 36.3, 500.0, 288.9, 518.0, "Fig. 2. cell"),
            _box("img", "figure_body", 305.4, 340.0, 557.7, 495.0),
        ]
    )
    plan = SlotPlan(slots=[_slot("fig:2", "fig", 2)])
    initial_body_assignments(layout, plan)
    slot = plan.slot_by_key("fig:2")
    assert slot is not None
    assert not slot.body_box_id


def _side_by_side_page() -> tuple[LayoutMap, SlotPlan]:
    """Engineering (Beijing) page 8, as Azure returns it."""
    layout = LayoutMap(
        pages=[{"width_pt": 595.3, "height_pt": 793.7}],
        boxes=[
            _box("merged", "figure_body", 40.6, 66.4, 554.4, 456.4),
            _box("cap7", "figure_caption", 305.4, 461.3, 557.7, 479.6, "Fig. 7. XRD"),
            _box("cap6", "figure_caption", 36.3, 465.0, 288.9, 483.6, "Fig. 6. TEM"),
        ]
    )
    plan = SlotPlan(slots=[_slot("fig:6", "fig", 6), _slot("fig:7", "fig", 7)])
    for key, cid in (("fig:6", "cap6"), ("fig:7", "cap7")):
        slot = plan.slot_by_key(key)
        assert slot is not None
        slot.caption_box_id = cid
        slot.caption_text = "x"
        box = layout.box_by_id(cid)
        assert box is not None
        box.used_by_slot = key
    return layout, plan


def test_two_column_captions_each_get_their_half() -> None:
    layout, plan = _side_by_side_page()
    slot6 = plan.slot_by_key("fig:6")
    assert slot6 is not None
    slot6.body_box_id = "merged"
    slot6.body_box_ids = ["merged"]
    merged = layout.box_by_id("merged")
    assert merged is not None
    merged.used_by_slot = "fig:6"

    assert split_shared_column_bodies(layout, plan) == 2
    refresh_slot_statuses(plan)

    left = layout.box_by_id("merged-c1")
    right = layout.box_by_id("merged-c2")
    assert left is not None and right is not None
    # Cut halfway between Fig. 6's caption end and Fig. 7's caption start.
    cut = (288.9 + 305.4) / 2.0
    assert abs(float(left.rect["x1"]) - cut) < 0.01
    assert abs(float(right.rect["x0"]) - cut) < 0.01
    assert float(left.rect["x0"]) == 40.6
    assert float(right.rect["x1"]) == 554.4
    # Both keep the merged box's full height.
    assert float(left.rect["y0"]) == 66.4
    assert float(right.rect["y1"]) == 456.4

    assert (s6 := plan.slot_by_key("fig:6")) is not None
    assert (s7 := plan.slot_by_key("fig:7")) is not None
    assert s6.body_box_ids == ["merged-c1"]
    assert s7.body_box_ids == ["merged-c2"]
    assert s6.status == "filled"
    assert s7.status == "filled"


def test_the_spent_box_is_neither_unused_nor_a_carousel_entry() -> None:
    layout, plan = _side_by_side_page()
    split_shared_column_bodies(layout, plan)
    append_unclaimed_body_slots(layout, plan)
    census = slot_census(layout, plan)
    assert census["unused_body_n"] == 0
    assert census["unnumbered_n"] == 0
    assert census["column_split_n"] == 2
    assert len(plan.slots) == 2


def test_a_single_caption_does_not_cut_a_full_width_body() -> None:
    """One caption is no evidence of a column boundary. d3cy's table stays whole."""
    layout = LayoutMap(
        boxes=[
            _box("cap8", "table_caption", 41.6, 47.6, 209.0, 57.4, "Table 8. yields"),
            _box("tb8", "table_body", 39.9, 59.9, 553.5, 148.2),
        ]
    )
    slot = _slot("table:8", "table", 8)
    slot.caption_box_id = "cap8"
    slot.caption_text = "Table 8. yields"
    plan = SlotPlan(slots=[slot])
    assert split_shared_column_bodies(layout, plan) == 0
    assert layout.box_by_id("tb8-c1") is None
    body = layout.box_by_id("tb8")
    assert body is not None
    assert body.kind == "table_body"


def test_two_captions_that_already_have_their_own_bodies_are_left_alone() -> None:
    """d3cy page 12 Fig. 13 and Fig. 14: two captions, two boxes, nothing to share."""
    layout = LayoutMap(
        boxes=[
            _box("img13", "figure_body", 47.0, 186.3, 279.8, 403.9),
            _box("img14", "figure_body", 329.2, 188.2, 379.5, 379.5),
            _box("cap14", "figure_caption", 304.5, 384.0, 553.3, 414.7, "Fig. 14. a"),
            _box("cap13", "figure_caption", 41.8, 407.9, 289.8, 427.5, "Fig. 13. b"),
        ]
    )
    plan = SlotPlan(slots=[_slot("fig:13", "fig", 13), _slot("fig:14", "fig", 14)])
    for key, cid, bid in (("fig:13", "cap13", "img13"), ("fig:14", "cap14", "img14")):
        slot = plan.slot_by_key(key)
        assert slot is not None
        slot.caption_box_id = cid
        slot.caption_text = "x"
        slot.body_box_id = bid
        slot.body_box_ids = [bid]
    assert split_shared_column_bodies(layout, plan) == 0


def test_captions_that_overlap_in_x_are_not_a_row() -> None:
    """Two captions stacked in one column are not a left and a right."""
    layout = LayoutMap(
        boxes=[
            _box("merged", "figure_body", 40.6, 66.4, 554.4, 456.4),
            _box("capA", "figure_caption", 36.3, 461.0, 288.9, 470.0, "Fig. 6. a"),
            _box("capB", "figure_caption", 36.3, 465.0, 288.9, 474.0, "Fig. 7. b"),
        ]
    )
    plan = SlotPlan(slots=[_slot("fig:6", "fig", 6), _slot("fig:7", "fig", 7)])
    for key, cid in (("fig:6", "capA"), ("fig:7", "capB")):
        slot = plan.slot_by_key(key)
        assert slot is not None
        slot.caption_box_id = cid
        slot.caption_text = "x"
    assert split_shared_column_bodies(layout, plan) == 0
