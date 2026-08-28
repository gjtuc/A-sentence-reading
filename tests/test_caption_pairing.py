"""design/151 — caption pairing with mocked Gemini."""

from __future__ import annotations

from sentence_reading.pdf.caption_pairing import pair_slot_captions
from sentence_reading.pdf.layout_map import LayoutBox, LayoutMap
from sentence_reading.pdf.slot_plan import Slot, SlotPlan, assign_body_to_slot


def test_pair_figure_caption_below() -> None:
    layout = LayoutMap(
        boxes=[
            LayoutBox(
                id="fb",
                page_index=0,
                kind="figure_body",
                rect={"x0": 50, "y0": 100, "x1": 250, "y1": 300},
            ),
            LayoutBox(
                id="fc",
                page_index=0,
                kind="paragraph",
                rect={"x0": 55, "y0": 310, "x1": 245, "y1": 330},
                text="Fig. 1. Caption below body",
            ),
        ]
    )
    plan = SlotPlan(slots=[Slot(key="fig:1", kind="fig", n=1, status="empty")])
    assign_body_to_slot(plan, layout, "fig:1", "fb")
    pair_slot_captions(layout, plan)
    slot = plan.slot_by_key("fig:1")
    assert slot is not None
    assert slot.caption_box_id == "fc"
    assert slot.status == "filled"
