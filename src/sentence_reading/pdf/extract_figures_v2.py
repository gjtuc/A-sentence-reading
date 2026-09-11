"""
design/151 — slot-ordered figure extraction orchestrator (rich-v20).
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

from sentence_reading.models import Figure
from sentence_reading.pdf.caption_pairing import pair_slot_captions, refill_empty_slots
from sentence_reading.pdf.composite import (
    composite_figure_png,
    composite_table_png,
    placeholder_png,
    rect_from_dict,
    slot_missing_caption,
)
from sentence_reading.pdf.extract import (
    is_caption_only_figure_png,
    orphan_figure_png_from_caption,
)
from sentence_reading.pdf.layout_map import (
    LayoutMap,
    analyze_layout_map,
    read_figure_png,
)
from sentence_reading.pdf.slot_plan import (
    SlotPlan,
    build_slot_plan,
    initial_body_assignments,
    refresh_slot_statuses,
)

log = logging.getLogger(__name__)

_last_artifacts: dict[str, Any] | None = None

_TABLE_CAPTION_LINE = re.compile(
    r"^\s*Table\.?\s*S?\d+[a-z]?\b",
    re.IGNORECASE,
)


def get_last_layout_artifacts() -> dict[str, Any] | None:
    return _last_artifacts


def _set_artifacts(layout: LayoutMap, plan: SlotPlan) -> None:
    global _last_artifacts
    _last_artifacts = {
        "layout_map": layout.to_dict(),
        "slot_plan": plan.to_dict(),
    }


def _orphan_table_png_until_next_caption(page, cap_rect) -> bytes | None:
    """design/220 — caption-only table: clip below until next Table caption."""
    import fitz

    from sentence_reading.pdf.extract import _column_x_range, _render_page_clip

    page_rect = page.rect
    x0, x1 = _column_x_range(page_rect, cap_rect, bleed_frac=0.10)
    y0 = max(float(page_rect.y0), float(cap_rect.y0) - 4)
    y1 = min(float(page_rect.y1), float(cap_rect.y1) + 260)
    # Stop before the next table caption under this one.
    try:
        for block in page.get_text("dict").get("blocks") or []:
            if block.get("type") != 0:
                continue
            text = "".join(
                span.get("text") or ""
                for line in block.get("lines") or []
                for span in line.get("spans") or []
            )
            if not _TABLE_CAPTION_LINE.match(text.strip()):
                continue
            bbox = block.get("bbox") or (0, 0, 0, 0)
            by0 = float(bbox[1])
            if by0 <= float(cap_rect.y1) + 2:
                continue
            y1 = min(y1, by0 - 2)
    except Exception:  # noqa: BLE001
        pass
    if y1 <= y0 + 12:
        return None
    clip = fitz.Rect(x0, y0, x1, y1)
    return _render_page_clip(page, clip)


def _render_slot_png(
    doc,
    client,
    layout: LayoutMap,
    slot,
) -> tuple[bytes, str, int | None]:
    from sentence_reading.pdf.extract import _png_data_url, _render_page_clip

    body_box = layout.box_by_id(slot.body_box_id) if slot.body_box_id else None
    cap_box = layout.box_by_id(slot.caption_box_id) if slot.caption_box_id else None
    page_index = (
        body_box.page_index
        if body_box is not None
        else (cap_box.page_index if cap_box is not None else 0)
    )
    page = doc[page_index] if 0 <= page_index < len(doc) else doc[0]
    body_rect = rect_from_dict(body_box.rect) if body_box else None
    cap_rect = rect_from_dict(cap_box.rect) if cap_box else None
    caption = (slot.caption_text or "").strip()

    if slot.status == "empty":
        label = slot_missing_caption(slot.kind, slot.n)
        return placeholder_png(label), label, page_index

    png = b""
    if slot.kind == "table":
        png = composite_table_png(page, body_rect, cap_rect) or b""
        # design/220 — if body missing / caption-only strip, expand below caption
        # but stop before the next table caption on the page.
        if (
            cap_rect is not None
            and body_rect is None
            and (not png or is_caption_only_figure_png(png))
        ):
            orphan = _orphan_table_png_until_next_caption(page, cap_rect)
            if orphan:
                png = orphan
    else:
        png = composite_figure_png(page, body_rect, cap_rect) or b""
        if (
            slot.kind == "fig"
            and body_rect is None
            and cap_rect is not None
            and (not png or is_caption_only_figure_png(png))
        ):
            orphan_png = orphan_figure_png_from_caption(page, cap_rect)
            if orphan_png:
                png = orphan_png
        if not png and body_box and body_box.azure_ref and layout.operation_id:
            try:
                png = read_figure_png(
                    client,
                    model_id=layout.model_id,
                    result_id=layout.operation_id,
                    figure_id=body_box.azure_ref,
                )
            except Exception as exc:  # noqa: BLE001
                log.warning("azure figure crop failed %s: %s", body_box.azure_ref, exc)
    if not png and body_rect is not None:
        png = _render_page_clip(page, body_rect) or b""
    if not png:
        label = caption or slot_missing_caption(slot.kind, slot.n)
        return placeholder_png(label), label, page_index

    if not caption:
        if slot.kind == "table":
            caption = f"Table {slot.n}"
        else:
            caption = f"Figure {slot.n}"
    return png, caption, page_index


def slots_to_figures(
    doc,
    client,
    layout: LayoutMap,
    plan: SlotPlan,
    *,
    fig_id_prefix: str = "slot",
) -> list[Figure]:
    from sentence_reading.pdf.extract import _png_data_url

    out: list[Figure] = []
    for i, slot in enumerate(plan.slots):
        png, caption, page_index = _render_slot_png(doc, client, layout, slot)
        out.append(
            Figure(
                id=f"{fig_id_prefix}-{i + 1:04d}",
                image_src=_png_data_url(png),
                caption=caption,
                page_index=page_index,
                slot_key=slot.key,
            )
        )
    return out


def extract_figures_v2(pdf_path: Path, *, doc_role: str = "main") -> list[Figure]:
    """Azure layout map → slot plan → pairing → slot-ordered Figure[]."""
    import fitz

    from sentence_reading.pdf.supplementary_detect import normalize_doc_role

    supplementary = normalize_doc_role(doc_role) == "supplementary"
    layout, client, _result = analyze_layout_map(pdf_path)
    doc = fitz.open(pdf_path)
    try:
        plan = build_slot_plan(layout, supplementary=supplementary)
        initial_body_assignments(layout, plan, supplementary=supplementary)
        pair_slot_captions(layout, plan)
        refill_empty_slots(layout, plan)
        refresh_slot_statuses(plan)
        merged = slots_to_figures(doc, client, layout, plan)
        _set_artifacts(layout, plan)
        return merged
    finally:
        doc.close()


def render_slot_figure(
    pdf_path: Path,
    layout: LayoutMap,
    plan: SlotPlan,
    slot_key: str,
) -> Figure | None:
    """Re-render one slot after user assign (figure_edit API)."""
    import fitz

    from sentence_reading.pdf.extract import _png_data_url

    slot = plan.slot_by_key(slot_key)
    if slot is None:
        return None
    doc = fitz.open(pdf_path)
    try:
        layout_map = layout
        client = None
        png, caption, page_index = _render_slot_png(doc, client, layout_map, slot)
        idx = plan.keys_in_order().index(slot.key)
        return Figure(
            id=f"slot-{idx + 1:04d}",
            image_src=_png_data_url(png),
            caption=caption,
            page_index=page_index,
            slot_key=slot.key,
        )
    finally:
        doc.close()
