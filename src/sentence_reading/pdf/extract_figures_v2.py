"""
design/151 — slot-ordered figure extraction orchestrator (rich-v20).
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

from sentence_reading.models import Figure
from sentence_reading.pdf.caption_pairing import (
    fill_from_page_neighbours,
    pair_slot_captions,
    refill_empty_slots,
)
from sentence_reading.pdf.composite import (
    composite_figure_png,
    composite_table_png,
    placeholder_png,
    rect_from_dict,
    slot_missing_caption,
    slot_unnumbered_caption,
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
    append_unclaimed_body_slots,
    build_slot_plan,
    initial_body_assignments,
    refresh_slot_statuses,
    slot_census,
    split_shared_column_bodies,
)

log = logging.getLogger(__name__)

_last_artifacts: dict[str, Any] | None = None
_last_census: dict[str, int] | None = None
# design/337 — which document the two above describe. Cloud Run runs this service
# at `--concurrency 16` and `_run_ingest_job` is a bare task, so two ingests share
# the process. "last" is process-global, not per-job: without a key, paper A could
# persist paper B's layout_map and slot_plan, and every later re-render and figure
# edit for A would then reason about B's geometry.
_last_key: str | None = None

_TABLE_CAPTION_LINE = re.compile(
    r"^\s*Table\.?\s*S?\d+[a-z]?\b",
    re.IGNORECASE,
)


def artifacts_key(pdf_path: Path | str) -> str:
    return str(pdf_path)


def get_last_layout_artifacts(expect: Path | str | None = None) -> dict[str, Any] | None:
    """design/337 — refuse to hand back another document's geometry.

    A caller that knows which file it extracted passes it; a mismatch returns None
    rather than the wrong paper's boxes.
    """
    if expect is not None and _last_key != artifacts_key(expect):
        log.warning(
            "layout artifacts key mismatch (want=%s have=%s) - refusing",
            artifacts_key(expect),
            _last_key,
        )
        return None
    return _last_artifacts


def get_last_slot_census(expect: Path | str | None = None) -> dict[str, int] | None:
    """design/321 — body-vs-slot census of the last v2 extract."""
    if expect is not None and _last_key != artifacts_key(expect):
        return None
    return _last_census


def _set_artifacts(
    layout: LayoutMap,
    plan: SlotPlan,
    pdf_path: Path | str,
) -> None:
    global _last_artifacts, _last_census, _last_key
    _last_artifacts = {
        "layout_map": layout.to_dict(),
        "slot_plan": plan.to_dict(),
    }
    _last_census = slot_census(layout, plan)
    _last_key = artifacts_key(pdf_path)


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


def _slot_body_rect(layout: LayoutMap, slot, page_index: int):
    """Union of every panel this slot holds on `page_index` (design/338).

    A multi-panel figure arrives as several Azure `figure_body` boxes. The render
    path used `body_box_id` alone, so a slot holding three panels drew one — which
    is why pairing them correctly is only half the repair. The panels of one figure
    are adjacent on the page, so their bounding box is the figure region.
    """
    ids = list(getattr(slot, "body_box_ids", None) or [])
    if len(ids) < 2:
        return None
    rects = []
    for bid in ids:
        box = layout.box_by_id(bid)
        if box is None or box.page_index != page_index:
            continue
        rects.append(rect_from_dict(box.rect))
    if len(rects) < 2:
        return None
    out = rects[0]
    for r in rects[1:]:
        out = out | r
    return out


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
    body_rect = _slot_body_rect(layout, slot, page_index) or (
        rect_from_dict(body_box.rect) if body_box else None
    )
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
        if getattr(slot, "unnumbered", False):
            # design/324 — rescued body; its number is a position, not a label.
            caption = slot_unnumbered_caption(slot.kind)
        elif slot.kind == "table":
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

    global _last_census, _last_key

    supplementary = normalize_doc_role(doc_role) == "supplementary"
    # design/321 — a raise must not leave the previous paper's census readable.
    _last_census = None
    _last_key = None
    layout, client, _result = analyze_layout_map(pdf_path)
    doc = fitz.open(pdf_path)
    try:
        plan = build_slot_plan(layout, supplementary=supplementary)
        initial_body_assignments(layout, plan, supplementary=supplementary)
        pair_slot_captions(layout, plan)
        refill_empty_slots(layout, plan)
        # design/359 — the caption's x-range is the column boundary. Where the paper
        # printed two captions of one kind side by side and Azure returned one box for
        # both, hand each caption its own part before leftovers are counted.
        split_shared_column_bodies(layout, plan)
        # design/360 — last automatic try: the nearest unclaimed box of the kind the
        # caption names, on the caption's own page, in any direction.
        fill_from_page_neighbours(layout, plan)
        append_unclaimed_body_slots(layout, plan, supplementary=supplementary)
        refresh_slot_statuses(plan)
        merged = slots_to_figures(doc, client, layout, plan)
        _set_artifacts(layout, plan, pdf_path)
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
