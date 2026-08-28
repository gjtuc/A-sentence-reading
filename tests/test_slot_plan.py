"""design/151 — slot plan ordering + merge user_confirmed."""

from __future__ import annotations

from sentence_reading.pdf.layout_map import LayoutBox, LayoutMap
from sentence_reading.pdf.slot_plan import (
    Slot,
    SlotPlan,
    build_slot_plan,
    is_supplementary_label,
    merge_user_confirmed_slots,
    slot_key_from_caption_key,
)


def test_slot_key_from_caption_key() -> None:
    assert slot_key_from_caption_key("fig:3") == "fig:3"
    assert slot_key_from_caption_key("table:2") == "table:2"
    assert slot_key_from_caption_key("fig:s7") is None
    assert slot_key_from_caption_key("fig:s7", supplementary=True) == "fig:s7"
    assert is_supplementary_label("fig:s1") is True
    assert is_supplementary_label("fig:1") is False


def test_build_slot_plan_ordered() -> None:
    layout = LayoutMap(
        boxes=[
            LayoutBox(
                id="p1",
                page_index=0,
                kind="figure_caption",
                rect={"x0": 0, "y0": 0, "x1": 1, "y1": 1},
                text="Fig. 3. Plot",
            ),
            LayoutBox(
                id="p2",
                page_index=0,
                kind="table_caption",
                rect={"x0": 0, "y0": 0, "x1": 1, "y1": 1},
                text="Table 2. Data",
            ),
        ]
    )
    plan = build_slot_plan(layout)
    keys = [s.key for s in plan.slots]
    assert keys.index("fig:3") < keys.index("table:2")
    assert all(s.status == "empty" for s in plan.slots)


def test_merge_user_confirmed() -> None:
    old = SlotPlan(
        slots=[
            Slot(
                key="fig:2",
                kind="fig",
                n=2,
                status="user_confirmed",
                body_box_id="fb-0002",
                caption_text="Fig. 2. User fixed",
            )
        ]
    )
    new = SlotPlan(slots=[Slot(key="fig:2", kind="fig", n=2, status="empty")])
    merged = merge_user_confirmed_slots(new, old)
    slot = merged.slot_by_key("fig:2")
    assert slot is not None
    assert slot.status == "user_confirmed"
    assert slot.body_box_id == "fb-0002"
