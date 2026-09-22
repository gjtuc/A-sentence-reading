"""design/338 — a panel belongs to its caption, and every panel gets drawn.

design/337 measured the pairing and found 51 of 157 slots across ten papers were
images with no caption, while 13 captions had no image. An 11-figure, 2-table paper
produced 24 carousel slots with the same figure appearing twice.

Cause was `_nearest_caption_for_body`'s horizontal test: it required the caption's
centre within 48pt of the body's. Azure splits a multi-panel figure into several
`figure_body` boxes, so a left-hand panel under a full-width caption has a distant
centre while sitting almost entirely inside the caption's span. Measured over 130
figure bodies: rejected bodies had a median centre offset of 92.6pt but a median
0.76 of their width under the caption; accepted bodies never overlapped below 0.68.

Two more gaps had to close with it: `assign_body_to_slot` replaced the body list, so
even correct pairing kept only the last panel, and `_render_slot_png` read
`body_box_id` alone, so a slot holding three panels drew one.
"""

from __future__ import annotations

from sentence_reading.pdf.extract_figures_v2 import _slot_body_rect
from sentence_reading.pdf.slot_plan import (
    CAPTION_X_OVERLAP_MIN,
    Slot,
    SlotPlan,
    _nearest_caption_for_body,
    _x_overlap_frac,
    assign_body_boxes_to_slot,
    assign_body_to_slot,
)


class _Box:
    def __init__(
        self,
        bid: str,
        kind: str,
        x0: float,
        y0: float,
        x1: float,
        y1: float,
        text: str = "",
        page: int = 0,
    ) -> None:
        self.id = bid
        self.kind = kind
        self.rect = {"x0": x0, "y0": y0, "x1": x1, "y1": y1}
        self.text = text
        self.page_index = page
        self.used_by_slot = ""


class _Layout:
    def __init__(self, boxes: list[_Box]) -> None:
        self.boxes = boxes

    def boxes_on_page(self, page: int) -> list[_Box]:
        return [b for b in self.boxes if b.page_index == page]

    def box_by_id(self, bid: str):
        return next((b for b in self.boxes if b.id == bid), None)


# A full-width caption at x 60..540 under two half-width panels.
CAPTION = _Box("c1", "figure_caption", 60, 400, 540, 420, "Figure 3. Panels a and b.")
LEFT = _Box("bL", "figure_body", 60, 200, 290, 390)
RIGHT = _Box("bR", "figure_body", 310, 200, 540, 390)
# A panel in the other column, sharing no x-range with the caption.
FAR = _Box("bF", "figure_body", 560, 200, 780, 390)


# --------------------------------------------------------------- the overlap test


def test_overlap_fraction_is_measured_against_the_body() -> None:
    assert _x_overlap_frac(LEFT, CAPTION) == 1.0
    assert _x_overlap_frac(RIGHT, CAPTION) == 1.0
    assert _x_overlap_frac(FAR, CAPTION) == 0.0


def test_a_side_panel_now_finds_its_caption() -> None:
    """The live defect: the left panel's centre is 135pt from the caption's."""
    mid_cap = (CAPTION.rect["x0"] + CAPTION.rect["x1"]) / 2.0
    mid_left = (LEFT.rect["x0"] + LEFT.rect["x1"]) / 2.0
    assert abs(mid_cap - mid_left) > 48  # the old rule rejected this
    layout = _Layout([CAPTION, LEFT, RIGHT])
    assert _nearest_caption_for_body(layout, LEFT, fig=True) == CAPTION.text
    assert _nearest_caption_for_body(layout, RIGHT, fig=True) == CAPTION.text


def test_a_panel_in_another_column_is_still_refused() -> None:
    layout = _Layout([CAPTION, FAR])
    assert _nearest_caption_for_body(layout, FAR, fig=True) == ""


def test_a_centred_body_keeps_matching() -> None:
    body = _Box("b1", "figure_body", 60, 200, 540, 390)
    layout = _Layout([CAPTION, body])
    assert _nearest_caption_for_body(layout, body, fig=True) == CAPTION.text


def test_the_threshold_sits_below_every_accepted_body() -> None:
    """Measured: accepted bodies never overlap below 0.68, refused ones hit 0.00."""
    assert 0.0 < CAPTION_X_OVERLAP_MIN < 0.68


def test_a_barely_overlapping_body_is_refused() -> None:
    sliver = _Box("bs", "figure_body", 480, 200, 780, 390)  # 20% inside
    assert _x_overlap_frac(sliver, CAPTION) < CAPTION_X_OVERLAP_MIN
    assert _nearest_caption_for_body(_Layout([CAPTION, sliver]), sliver, fig=True) == ""


# --------------------------------------------------------------- accumulation


def _plan() -> SlotPlan:
    return SlotPlan(slots=[Slot(key="fig:3", kind="fig", n=3, status="empty")])


def test_panels_accumulate_instead_of_replacing() -> None:
    plan, layout = _plan(), _Layout([CAPTION, LEFT, RIGHT])
    assign_body_to_slot(plan, layout, "fig:3", "bL")
    assign_body_to_slot(plan, layout, "fig:3", "bR")
    slot = plan.slot_by_key("fig:3")
    assert slot is not None
    assert slot.body_box_ids == ["bL", "bR"]
    # The first stays the representative id for callers that read one.
    assert slot.body_box_id == "bL"


def test_the_same_panel_twice_is_not_duplicated() -> None:
    plan, layout = _plan(), _Layout([CAPTION, LEFT])
    assign_body_to_slot(plan, layout, "fig:3", "bL")
    assign_body_to_slot(plan, layout, "fig:3", "bL")
    assert plan.slot_by_key("fig:3").body_box_ids == ["bL"]


def test_the_editor_still_replaces_the_list() -> None:
    """A user assigning panels by hand sets the list; it must not accumulate."""
    plan, layout = _plan(), _Layout([CAPTION, LEFT, RIGHT])
    assign_body_boxes_to_slot(plan, layout, "fig:3", ["bL", "bR"])
    assign_body_boxes_to_slot(plan, layout, "fig:3", ["bR"])
    assert plan.slot_by_key("fig:3").body_box_ids == ["bR"]


# --------------------------------------------------------------- the render rect


def test_a_multi_panel_slot_renders_the_union() -> None:
    plan, layout = _plan(), _Layout([CAPTION, LEFT, RIGHT])
    assign_body_to_slot(plan, layout, "fig:3", "bL")
    assign_body_to_slot(plan, layout, "fig:3", "bR")
    rect = _slot_body_rect(layout, plan.slot_by_key("fig:3"), 0)
    assert rect is not None
    assert (rect.x0, rect.y0, rect.x1, rect.y1) == (60.0, 200.0, 540.0, 390.0)


def test_a_single_panel_slot_keeps_the_old_path() -> None:
    plan, layout = _plan(), _Layout([CAPTION, LEFT])
    assign_body_to_slot(plan, layout, "fig:3", "bL")
    assert _slot_body_rect(layout, plan.slot_by_key("fig:3"), 0) is None


def test_panels_on_another_page_are_not_unioned_in() -> None:
    other = _Box("bO", "figure_body", 60, 200, 290, 390, page=4)
    plan, layout = _plan(), _Layout([CAPTION, LEFT, other])
    assign_body_to_slot(plan, layout, "fig:3", "bL")
    assign_body_to_slot(plan, layout, "fig:3", "bO")
    # Only one panel lives on page 0, so there is nothing to union there.
    assert _slot_body_rect(layout, plan.slot_by_key("fig:3"), 0) is None
