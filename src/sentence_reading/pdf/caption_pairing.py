"""
design/151 — caption pairing: fig below / table above, Gemini, distance fallback, 2-pass refill.
"""

from __future__ import annotations

import re

from sentence_reading.fig_refs import caption_key
from sentence_reading.llm.caption_classify import classify_caption_candidates
from sentence_reading.pdf.layout_map import LayoutBox, LayoutMap
from sentence_reading.pdf.slot_plan import (
    SlotPlan,
    assign_caption_to_slot,
    refresh_slot_statuses,
    slot_key_from_caption_key,
)

_WIDTH_RATIO_MIN = 0.5
_WIDTH_RATIO_MAX = 1.2
_STRIP_BELOW_PT = 180.0
_STRIP_ABOVE_PT = 180.0


def _body_width(box: LayoutBox) -> float:
    return max(float(box.rect["x1"]) - float(box.rect["x0"]), 1.0)


def _width_ratio(a: LayoutBox, b: LayoutBox) -> float:
    return _body_width(b) / _body_width(a)


def _x_overlap(a: LayoutBox, b: LayoutBox) -> bool:
    mid_b = (float(b.rect["x0"]) + float(b.rect["x1"])) / 2.0
    return float(a.rect["x0"]) - 24 <= mid_b <= float(a.rect["x1"]) + 24


def _plan_supplementary(plan: SlotPlan) -> bool:
    from sentence_reading.pdf.slot_plan import is_supplementary_label

    return any(is_supplementary_label(s.key) for s in plan.slots)


def _caption_number_matches(
    slot_key: str, text: str, *, supplementary: bool = False
) -> bool:
    ckey = caption_key(text)
    if not ckey:
        return False
    sk = slot_key_from_caption_key(ckey, supplementary=supplementary)
    return bool(sk and sk.lower() == (slot_key or "").lower())


def _strip_candidates(
    layout: LayoutMap,
    body: LayoutBox,
    *,
    fig: bool,
) -> list[LayoutBox]:
    out: list[LayoutBox] = []
    for box in layout.boxes_on_page(body.page_index):
        if box.used_by_slot and box.used_by_slot != "":
            continue
        if fig:
            if box.kind not in ("figure_caption", "paragraph"):
                continue
            gap = float(box.rect["y0"]) - float(body.rect["y1"])
            if gap < -8 or gap > _STRIP_BELOW_PT:
                continue
        else:
            if box.kind not in ("table_caption", "paragraph"):
                continue
            gap = float(body.rect["y0"]) - float(box.rect["y1"])
            if gap < -8 or gap > _STRIP_ABOVE_PT:
                continue
        if not box.text.strip():
            continue
        ratio = _width_ratio(body, box)
        if ratio < _WIDTH_RATIO_MIN or ratio > _WIDTH_RATIO_MAX:
            continue
        if not _x_overlap(body, box):
            continue
        out.append(box)
    out.sort(
        key=lambda b: abs(
            (float(b.rect["y0"]) - float(body.rect["y1"]))
            if fig
            else (float(body.rect["y0"]) - float(b.rect["y1"]))
        )
    )
    return out[:5]


def pair_slot_captions(layout: LayoutMap, plan: SlotPlan) -> None:
    """Primary 1-pass pairing for slots with body boxes."""
    supplementary = _plan_supplementary(plan)
    for slot in plan.slots:
        if slot.status in ("filled", "user_confirmed"):
            continue
        if not slot.body_box_id:
            continue
        body = layout.box_by_id(slot.body_box_id)
        if body is None:
            continue
        fig = slot.kind != "table"
        candidates = _strip_candidates(layout, body, fig=fig)
        if not candidates:
            _distance_fallback(layout, plan, slot, body, fig=fig, supplementary=supplementary)
            continue
        texts = [c.text for c in candidates]
        pick = classify_caption_candidates(slot_key=slot.key, candidates=texts)
        if pick is None or pick < 0 or pick >= len(candidates):
            _distance_fallback(layout, plan, slot, body, fig=fig, supplementary=supplementary)
            continue
        chosen = candidates[pick]
        if not _caption_number_matches(slot.key, chosen.text, supplementary=supplementary):
            _distance_fallback(layout, plan, slot, body, fig=fig, supplementary=supplementary)
            continue
        assign_caption_to_slot(plan, layout, slot.key, chosen.id, chosen.text)
    refresh_slot_statuses(plan)


def _distance_fallback(
    layout: LayoutMap,
    plan: SlotPlan,
    slot,
    body: LayoutBox,
    *,
    fig: bool,
    supplementary: bool = False,
) -> None:
    best: tuple[LayoutBox | None, float] = (None, 1e9)
    for box in layout.boxes_on_page(body.page_index):
        if box.used_by_slot:
            continue
        if not box.text.strip():
            continue
        if not _caption_number_matches(slot.key, box.text, supplementary=supplementary):
            continue
        if fig:
            gap = float(box.rect["y0"]) - float(body.rect["y1"])
            if gap < -8 or gap > _STRIP_BELOW_PT * 1.5:
                continue
        else:
            gap = float(body.rect["y0"]) - float(box.rect["y1"])
            if gap < -8 or gap > _STRIP_ABOVE_PT * 1.5:
                continue
        if not _x_overlap(body, box):
            continue
        dist = abs(gap)
        if dist < best[1]:
            best = (box, dist)
    if best[0] is not None:
        assign_caption_to_slot(plan, layout, slot.key, best[0].id, best[0].text)


def refill_empty_slots(layout: LayoutMap, plan: SlotPlan) -> None:
    """2-pass — global search for Figure N / Table N labels."""
    for slot in plan.slots:
        if slot.status in ("filled", "user_confirmed"):
            continue
        label_re = _slot_label_pattern(slot.key)
        if label_re is None:
            continue
        cap_box: LayoutBox | None = None
        body_box: LayoutBox | None = None
        for box in layout.boxes:
            if box.used_by_slot:
                continue
            text = (box.text or "").strip()
            if text and label_re.match(text):
                if box.kind.endswith("_caption") or box.kind == "paragraph":
                    cap_box = box
                    break
        if cap_box is None:
            for box in layout.boxes:
                if box.used_by_slot:
                    continue
                text = (box.text or "").strip()
                if text and label_re.match(text):
                    cap_box = box
                    break
        if cap_box is None:
            continue
        if not slot.caption_box_id:
            assign_caption_to_slot(plan, layout, slot.key, cap_box.id, cap_box.text)
        if not slot.body_box_id:
            fig = slot.kind != "table"
            want_kind = "figure_body" if fig else "table_body"
            best_body: tuple[LayoutBox | None, float] = (None, 1e9)
            for box in layout.boxes:
                if box.kind != want_kind or box.used_by_slot:
                    continue
                if box.page_index != cap_box.page_index:
                    continue
                if fig:
                    gap = float(box.rect["y0"]) - float(cap_box.rect["y1"])
                    if gap < -20:
                        continue
                else:
                    gap = float(cap_box.rect["y0"]) - float(box.rect["y1"])
                    if gap < -20:
                        continue
                dist = abs(gap)
                if dist < best_body[1]:
                    best_body = (box, dist)
            if best_body[0] is not None:
                from sentence_reading.pdf.slot_plan import assign_body_to_slot

                assign_body_to_slot(plan, layout, slot.key, best_body[0].id)
        if slot.body_box_id and not slot.caption_box_id:
            body = layout.box_by_id(slot.body_box_id)
            if body is not None:
                _distance_fallback(layout, plan, slot, body, fig=slot.kind != "table")
    refresh_slot_statuses(plan)


def _slot_label_pattern(slot_key: str) -> re.Pattern[str] | None:
    m = re.match(r"^(fig|table):s(\d+)$", (slot_key or "").lower())
    if m:
        kind, num = m.group(1), m.group(2)
        if kind == "table":
            return re.compile(rf"^\s*Table\.?\s*S\s*{num}\b", re.IGNORECASE)
        return re.compile(rf"^\s*(?:Figures?|Figs?)\.?\s*S\s*{num}\b", re.IGNORECASE)
    m = re.match(r"^(fig|table):(\d+)$", (slot_key or "").lower())
    if not m:
        return None
    kind, num = m.group(1), m.group(2)
    if kind == "table":
        return re.compile(rf"^\s*Table\.?\s*{num}\b", re.IGNORECASE)
    return re.compile(rf"^\s*(?:Figures?|Figs?)\.?\s*{num}\b", re.IGNORECASE)
