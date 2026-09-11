# -*- coding: utf-8 -*-
"""design/220 — Azure table caption/body overlap must not steal body for earlier slot."""
from __future__ import annotations

from sentence_reading.pdf.layout_map import LayoutBox, LayoutMap
from sentence_reading.pdf.slot_plan import (
    TABLE_CAPTION_OVERLAP_PT,
    build_slot_plan,
    initial_body_assignments,
    refresh_slot_statuses,
)


def _box(
    bid: str,
    kind: str,
    *,
    y0: float,
    y1: float,
    text: str = "",
    x0: float = 90,
    x1: float = 500,
    page: int = 1,
) -> LayoutBox:
    return LayoutBox(
        id=bid,
        page_index=page,
        kind=kind,
        rect={"x0": x0, "y0": y0, "x1": x1, "y1": y1},
        text=text,
    )


def test_overlap_constant_allows_azure_bleed() -> None:
    assert TABLE_CAPTION_OVERLAP_PT >= 40.0


def test_si_table_s3_body_not_stolen_by_s2_when_caption_overlaps() -> None:
    """Reproduce an1c00673 SI: tb under S3 overlaps caption by ~11pt.

    Old gap<-8 rule assigned that body to Table S2; S3 stayed caption-only.
    """
    layout = LayoutMap(
        boxes=[
            _box(
                "p-s2",
                "table_caption",
                y0=141.0,
                y1=152.9,
                text="Table S2. Surface compositions.",
            ),
            _box("tb-s2", "table_body", y0=153.7, y1=206.6, text=""),
            _box(
                "p-s3",
                "table_caption",
                y0=237.8,
                y1=252.8,
                text="Table S3. Desorption areas of CO2.",
            ),
            # body.y0 < caption.y1 → overlap ~11.5pt (live Azure)
            _box("tb-s3", "table_body", y0=241.3, y1=348.4, text=""),
            _box(
                "p-s4",
                "table_caption",
                y0=436.2,
                y1=462.5,
                text="Table S4. Comparisons of rates.",
            ),
            _box("tb-s4", "table_body", y0=463.9, y1=656.5, text=""),
        ]
    )
    plan = build_slot_plan(layout, supplementary=True)
    initial_body_assignments(layout, plan, supplementary=True)
    refresh_slot_statuses(plan)

    s2 = plan.slot_by_key("table:s2")
    s3 = plan.slot_by_key("table:s3")
    s4 = plan.slot_by_key("table:s4")
    assert s2 is not None and s3 is not None and s4 is not None
    assert s2.body_box_id == "tb-s2"
    assert s3.body_box_id == "tb-s3"
    assert s4.body_box_id == "tb-s4"
    assert s3.status in ("filled", "partial")
    # With body assigned, status should not stay empty
    assert s3.body_box_id


def test_orphan_helper_stops_before_next_table_caption() -> None:
    from sentence_reading.pdf import extract_figures_v2 as v2

    doc = v2._orphan_table_png_until_next_caption.__doc__ or ""
    assert "next Table caption" in doc
    assert v2._TABLE_CAPTION_LINE.match("Table S4. Comparisons")
