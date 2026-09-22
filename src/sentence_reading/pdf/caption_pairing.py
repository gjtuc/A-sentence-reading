"""
design/151 — caption pairing: fig below / table above, Gemini, distance fallback, 2-pass refill.
"""

from __future__ import annotations

import re

from sentence_reading.fig_refs import caption_key
from sentence_reading.llm.caption_classify import classify_caption_candidates
from sentence_reading.pdf.layout_map import LayoutBox, LayoutMap
from sentence_reading.pdf.slot_plan import (
    FIG_CAPTION_OVERLAP_PT,
    TABLE_CAPTION_OVERLAP_PT,
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
            if gap < -FIG_CAPTION_OVERLAP_PT or gap > _STRIP_BELOW_PT:
                continue
        else:
            if box.kind not in ("table_caption", "paragraph"):
                continue
            gap = float(body.rect["y0"]) - float(box.rect["y1"])
            if gap < -TABLE_CAPTION_OVERLAP_PT or gap > _STRIP_ABOVE_PT:
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
        if slot.caption_box_id:
            cap_box = layout.box_by_id(slot.caption_box_id)
        if cap_box is None:
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
                # Same geometry as the caption list: a figure sits above its
                # caption, a table sits below. The previous signs looked the
                # other way, so Fig. 3's timeline (4pt above) and Table 1's
                # grid (4pt below) were both skipped.
                if fig:
                    gap = float(cap_box.rect["y0"]) - float(box.rect["y1"])
                    if gap < -FIG_CAPTION_OVERLAP_PT:
                        continue
                else:
                    gap = float(box.rect["y0"]) - float(cap_box.rect["y1"])
                    if gap < -TABLE_CAPTION_OVERLAP_PT:
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


# design/360 — the last automatic try, after above/below (design/358) and the column
# split (design/359) have both failed. Azure tells figures from tables, so a lost figure
# is searched for among unclaimed *figures* and a lost table among unclaimed *tables*,
# and the two cannot be swapped. Nothing here reads the picture: it is the paper's own
# caption, the paper's own page, and the nearest box of the kind the caption names.
NEIGHBOUR_MAX_PT = 220.0
NEIGHBOUR_X_OVERLAP_MIN = 0.5
NEIGHBOUR_Y_OVERLAP_MIN = 0.25


def _overlap_frac(a0: float, a1: float, b0: float, b1: float) -> float:
    return max(0.0, min(a1, b1) - max(a0, b0)) / max(min(a1 - a0, b1 - b0), 1.0)


def _rect_distance(a: LayoutBox, b: LayoutBox) -> float:
    dx = max(
        0.0,
        float(a.rect["x0"]) - float(b.rect["x1"]),
        float(b.rect["x0"]) - float(a.rect["x1"]),
    )
    dy = max(
        0.0,
        float(a.rect["y0"]) - float(b.rect["y1"]),
        float(b.rect["y0"]) - float(a.rect["y1"]),
    )
    return (dx * dx + dy * dy) ** 0.5


def _aligned(cap: LayoutBox, body: LayoutBox) -> bool:
    """Above, below, or beside — but in line with the caption on one axis."""
    x = _overlap_frac(
        float(cap.rect["x0"]),
        float(cap.rect["x1"]),
        float(body.rect["x0"]),
        float(body.rect["x1"]),
    )
    y = _overlap_frac(
        float(cap.rect["y0"]),
        float(cap.rect["y1"]),
        float(body.rect["y0"]),
        float(body.rect["y1"]),
    )
    return x >= NEIGHBOUR_X_OVERLAP_MIN or y >= NEIGHBOUR_Y_OVERLAP_MIN


def fill_from_page_neighbours(layout: LayoutMap, plan: SlotPlan) -> int:
    """Give a still-empty caption the nearest unclaimed body of its own kind.

    Assignment is globally nearest-first, so a body that sits between two empty
    captions goes to the one it is closer to instead of to whichever slot is
    numbered lower. Returns how many slots were filled.
    """
    from sentence_reading.pdf.slot_plan import assign_body_to_slot

    pairs: list[tuple[float, str, str]] = []
    for slot in plan.slots:
        if slot.status == "user_confirmed" or slot.unnumbered:
            continue
        if slot.body_box_id or slot.body_box_ids or not slot.caption_box_id:
            continue
        cap = layout.box_by_id(slot.caption_box_id)
        if cap is None:
            continue
        want = "figure_body" if slot.kind != "table" else "table_body"
        for box in layout.boxes_on_page(cap.page_index):
            if box.kind != want or box.used_by_slot:
                continue
            if not _aligned(cap, box):
                continue
            dist = _rect_distance(cap, box)
            if dist > NEIGHBOUR_MAX_PT:
                continue
            pairs.append((dist, slot.key, box.id))

    pairs.sort(key=lambda t: (t[0], t[1], t[2]))
    filled = 0
    for _dist, slot_key, box_id in pairs:
        slot = plan.slot_by_key(slot_key)
        box = layout.box_by_id(box_id)
        if slot is None or box is None:
            continue
        if slot.body_box_id or slot.body_box_ids or box.used_by_slot:
            continue
        assign_body_to_slot(plan, layout, slot_key, box_id)
        filled += 1
    if filled:
        refresh_slot_statuses(plan)
    return filled


# design/361 — the paper repeating its own number is the evidence. Advanced Energy
# Materials prints Table 1 across pages 22–27 and heads each later page with a 21-char
# `Table 1. (Continued)`; `1-s2.0-S0360319924023218` does the same over two pages with
# 19 characters. Before this, the slot took page 22 and the other five pages became
# unclaimed bodies, so the reader saw one sixth of Table 1 and every count said
# `filled`. Four other papers repeat a caption number across pages without saying
# `Continued` — a graphical-abstract label, a cross-reference Azure typed as a caption —
# and must not be joined, which is why the word is required and not inferred from
# adjacency alone.
_CONTINUED = re.compile(r"\b(continued|continues|cont\.|cont'd)\b", re.IGNORECASE)
CONTINUED_BODY_GAP_PT = 40.0


def attach_continued_pages(layout: LayoutMap, plan: SlotPlan) -> int:
    """Add the later pages of a figure or table that the paper says is continued.

    Returns how many bodies were joined to an existing slot.
    """
    from sentence_reading.pdf.slot_plan import assign_body_to_slot

    joined = 0
    for cap in layout.boxes:
        if cap.kind not in ("figure_caption", "table_caption"):
            continue
        text = cap.text or ""
        if not _CONTINUED.search(text):
            continue
        ck = caption_key(text)
        sk = slot_key_from_caption_key(ck) if ck else None
        slot = plan.slot_by_key(sk) if sk else None
        if slot is None or slot.status == "user_confirmed":
            continue
        held = slot.body_box_ids or ([slot.body_box_id] if slot.body_box_id else [])
        if not held:
            continue
        first = layout.box_by_id(held[0])
        if first is None or first.page_index >= cap.page_index:
            continue
        want = "figure_body" if slot.kind != "table" else "table_body"
        best, best_gap = None, CONTINUED_BODY_GAP_PT
        mine = None
        for box in layout.boxes_on_page(cap.page_index):
            if box.kind != want:
                continue
            gap = _rect_distance(cap, box)
            if box.used_by_slot == slot.key and gap <= CONTINUED_BODY_GAP_PT:
                mine = box
            if box.used_by_slot:
                continue
            if gap <= best_gap:
                best, best_gap = box, gap
        if best is None:
            # An earlier pass may already have handed this page's body to the slot.
            # `1-s2.0-S0360319924023218` page 2 arrives that way, and it still needs
            # the mark so the render path knows to draw both pages.
            if mine is not None:
                slot.continued = True
            continue
        assign_body_to_slot(plan, layout, slot.key, best.id)
        cap.used_by_slot = slot.key
        slot.continued = True
        joined += 1
    if joined:
        refresh_slot_statuses(plan)
    return joined


_SUPP_WORD = r"(?:Supplementary|Supplemental|Supporting)"
_KIND_WORDS = {
    "fig": r"(?:Figures?|Figs?)",
    "scheme": r"Scheme",
    "table": r"Table",
}


def _slot_label_pattern(slot_key: str) -> re.Pattern[str] | None:
    """What a box's text must begin with to be this slot's caption.

    design/362 — a supplementary number is printed two ways. ACS, RSC and Elsevier
    put the `S` on the number (`Figure S1`); Nature puts it in the word in front
    (`Supplementary Fig. 1`). Both name `fig:s1`, so accept either — and accept the
    bare number only when that word is there, or `Supplementary Table 1` would be
    handed to the main paper's `table:1`.
    """
    m = re.match(r"^(fig|scheme|table):s(\d+)$", (slot_key or "").lower())
    if m:
        word = _KIND_WORDS[m.group(1)]
        num = m.group(2)
        return re.compile(
            rf"^\s*(?:{_SUPP_WORD}\s+{word}\.?\s*S?\s*{num}|{word}\.?\s*S\s*{num})\b",
            re.IGNORECASE,
        )
    m = re.match(r"^(fig|scheme|table):(\d+)$", (slot_key or "").lower())
    if not m:
        return None
    word = _KIND_WORDS[m.group(1)]
    return re.compile(rf"^\s*{word}\.?\s*{m.group(2)}\b", re.IGNORECASE)
