"""
design/151 — ordered fig:1..N + table:1..M slots with empty/partial/filled status.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sentence_reading.fig_refs import caption_key
from sentence_reading.pdf.layout_map import LayoutBox, LayoutMap

_SLOT_PLAN_NAME = "slot_plan.json"

# design/220 — Azure table_body often overlaps its caption by >8pt.
FIG_CAPTION_OVERLAP_PT = 8.0
TABLE_CAPTION_OVERLAP_PT = 40.0
# design/338 — share of a body box that must sit inside the caption's x-range for
# the two to belong together. Placed from the measured gap: accepted bodies never
# fall below 0.68, and the rejected panels worth rescuing sit at 0.4 and up, while
# the ones that genuinely belong to another column overlap by 0.00.
CAPTION_X_OVERLAP_MIN = 0.5
# design/338 — a body repeating at this tolerance on this many pages is a running
# page graphic, not a figure.
REPEAT_RECT_TOL_PT = 4.0
REPEAT_MIN_PAGES = 2


@dataclass
class Slot:
    key: str
    kind: str
    n: int
    status: str = "empty"
    body_box_id: str = ""
    caption_box_id: str = ""
    caption_text: str = ""
    body_box_ids: list[str] = field(default_factory=list)
    caption_box_ids: list[str] = field(default_factory=list)
    # design/324 — rescued body with no parsed caption number. Its `n` is a
    # carousel position, not a label the paper printed.
    unnumbered: bool = False

    def to_dict(self) -> dict[str, Any]:
        body_ids = self.body_box_ids or (
            [self.body_box_id] if self.body_box_id else []
        )
        cap_ids = self.caption_box_ids or (
            [self.caption_box_id] if self.caption_box_id else []
        )
        return {
            "key": self.key,
            "kind": self.kind,
            "n": self.n,
            "status": self.status,
            "body_box_id": body_ids[0] if body_ids else None,
            "caption_box_id": cap_ids[0] if cap_ids else None,
            "body_box_ids": body_ids,
            "caption_box_ids": cap_ids,
            "caption_text": self.caption_text,
            "unnumbered": bool(self.unnumbered),
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> Slot:
        body_ids = [
            str(x).strip()
            for x in (raw.get("body_box_ids") or [])
            if str(x).strip()
        ]
        if not body_ids:
            legacy = str(raw.get("body_box_id") or "").strip()
            if legacy:
                body_ids = [legacy]
        cap_ids = [
            str(x).strip()
            for x in (raw.get("caption_box_ids") or [])
            if str(x).strip()
        ]
        if not cap_ids:
            legacy = str(raw.get("caption_box_id") or "").strip()
            if legacy:
                cap_ids = [legacy]
        return cls(
            key=str(raw.get("key") or ""),
            kind=str(raw.get("kind") or "fig"),
            n=int(raw.get("n") or 0),
            status=str(raw.get("status") or "empty"),
            body_box_id=body_ids[0] if body_ids else "",
            caption_box_id=cap_ids[0] if cap_ids else "",
            caption_text=str(raw.get("caption_text") or ""),
            body_box_ids=body_ids,
            caption_box_ids=cap_ids,
            unnumbered=bool(raw.get("unnumbered")),
        )


@dataclass
class SlotPlan:
    slots: list[Slot] = field(default_factory=list)
    # design/356 — bodies kept out of the carousel for being one of a run of same-size
    # unclaimed boxes. Reported so the removal is a number rather than a silence.
    same_size_chrome_n: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {"version": 1, "slots": [s.to_dict() for s in self.slots]}

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> SlotPlan:
        slots = [
            Slot.from_dict(s)
            for s in (raw.get("slots") or [])
            if isinstance(s, dict)
        ]
        return cls(slots=slots)

    def slot_by_key(self, key: str) -> Slot | None:
        want = (key or "").strip().lower()
        for s in self.slots:
            if s.key.lower() == want:
                return s
        return None

    def keys_in_order(self) -> list[str]:
        return [s.key for s in self.slots]


def is_supplementary_label(key: str) -> bool:
    """True for fig:s* / table:s* slot keys."""
    return bool(re.match(r"^(?:fig|table):s\d+", (key or "").strip().lower()))


def slot_key_from_caption_key(ckey: str, *, supplementary: bool = False) -> str | None:
    """fig:3a → fig:3; fig:s2 → fig:s2 when supplementary."""
    if not ckey:
        return None
    parts = ckey.split(":", 1)
    if len(parts) != 2:
        return None
    kind, num = parts[0], parts[1]
    if kind not in ("fig", "table", "scheme"):
        return None
    num_lower = num.lower()
    if num_lower.startswith("s"):
        if not supplementary:
            return None
        m = re.match(r"^s(\d+)", num_lower)
        if not m:
            return None
        slot_kind = "table" if kind == "table" else "fig"
        return f"{slot_kind}:s{int(m.group(1))}"
    if is_supplementary_label(ckey):
        return None
    m = re.match(r"^(\d+)", num)
    if not m:
        return None
    slot_kind = "table" if kind == "table" else "fig"
    return f"{slot_kind}:{int(m.group(1))}"


def _slot_n_from_key(key: str) -> int:
    m = re.match(r"^(?:fig|table):s?(\d+)$", (key or "").lower())
    return int(m.group(1)) if m else 0


def _scan_max_numbers(
    layout: LayoutMap, *, supplementary: bool = False
) -> tuple[int, int]:
    max_fig = 0
    max_table = 0
    for box in layout.boxes:
        if not box.text:
            continue
        ckey = caption_key(box.text)
        if not ckey:
            continue
        sk = slot_key_from_caption_key(ckey, supplementary=supplementary)
        if not sk:
            continue
        n = _slot_n_from_key(sk)
        if sk.startswith("fig:"):
            max_fig = max(max_fig, n)
        elif sk.startswith("table:"):
            max_table = max(max_table, n)
    return max_fig, max_table


def build_slot_plan(layout: LayoutMap, *, supplementary: bool = False) -> SlotPlan:
    """Create slots fig:1..N or fig:s1..N when supplementary."""
    max_fig, max_table = _scan_max_numbers(layout, supplementary=supplementary)
    for box in layout.boxes:
        if box.kind == "figure_body":
            max_fig = max(max_fig, 1)
        if box.kind == "table_body":
            max_table = max(max_table, 1)

    slots: list[Slot] = []
    if supplementary:
        for n in range(1, max(max_fig, 0) + 1):
            slots.append(Slot(key=f"fig:s{n}", kind="fig", n=n, status="empty"))
        for n in range(1, max(max_table, 0) + 1):
            slots.append(Slot(key=f"table:s{n}", kind="table", n=n, status="empty"))
    else:
        for n in range(1, max(max_fig, 0) + 1):
            slots.append(Slot(key=f"fig:{n}", kind="fig", n=n, status="empty"))
        for n in range(1, max(max_table, 0) + 1):
            slots.append(Slot(key=f"table:{n}", kind="table", n=n, status="empty"))
    return SlotPlan(slots=slots)


def assign_body_boxes_to_slot(
    plan: SlotPlan,
    layout: LayoutMap,
    slot_key: str,
    body_box_ids: list[str],
    *,
    append: bool = False,
) -> None:
    """Attach bodies to a slot. `append` keeps panels already attached (design/338).

    The figure editor sets the whole list, so replacing stays the default. Automatic
    pairing appends: a multi-panel figure hands its panels over one at a time, and
    replacing meant only the last one survived even when pairing worked.
    """
    slot = plan.slot_by_key(slot_key)
    if slot is None:
        return
    ids = [str(x).strip() for x in body_box_ids if str(x).strip()]
    if append:
        existing = list(slot.body_box_ids or ([slot.body_box_id] if slot.body_box_id else []))
        ids = existing + [i for i in ids if i not in existing]
    slot.body_box_ids = ids
    slot.body_box_id = ids[0] if ids else ""
    for bid in ids:
        box = layout.box_by_id(bid)
        if box is not None:
            box.used_by_slot = slot.key
    if slot.caption_box_ids or slot.caption_box_id or slot.caption_text:
        slot.status = "filled" if slot.caption_box_ids or slot.caption_box_id else "partial"
    else:
        slot.status = "partial" if ids else "empty"


def assign_caption_boxes_to_slot(
    plan: SlotPlan,
    layout: LayoutMap,
    slot_key: str,
    caption_box_ids: list[str],
    caption_text: str = "",
) -> None:
    slot = plan.slot_by_key(slot_key)
    if slot is None:
        return
    ids = [str(x).strip() for x in caption_box_ids if str(x).strip()]
    slot.caption_box_ids = ids
    slot.caption_box_id = ids[0] if ids else ""
    for cid in ids:
        box = layout.box_by_id(cid)
        if box is not None:
            box.used_by_slot = slot.key
            if not caption_text:
                caption_text = box.text
    if caption_text:
        slot.caption_text = caption_text
    if slot.body_box_ids or slot.body_box_id:
        slot.status = "filled"
    else:
        slot.status = "partial" if ids or caption_text else "empty"


def assign_body_to_slot(
    plan: SlotPlan,
    layout: LayoutMap,
    slot_key: str,
    body_box_id: str,
) -> None:
    # design/338 — panels arrive one at a time; keep the ones already attached.
    assign_body_boxes_to_slot(plan, layout, slot_key, [body_box_id], append=True)


def assign_caption_to_slot(
    plan: SlotPlan,
    layout: LayoutMap,
    slot_key: str,
    caption_box_id: str,
    caption_text: str = "",
) -> None:
    assign_caption_boxes_to_slot(
        plan, layout, slot_key, [caption_box_id], caption_text=caption_text
    )


# design/356 — a run of unclaimed bodies that are all the same size is the journal's
# furniture, not the paper's figures. Measured: the RSC review prints six author
# headshots beside the biographies at 114–115 x 141–143 points, and each became its own
# carousel entry labelled `번호 없는 그림`, so studying the paper meant swiping through
# six portraits. design/338's detector misses them because it clusters on the whole rect
# and these sit at six different positions.
#
# Three members over two pages, because one page of same-size boxes is what a
# multi-panel figure looks like, and this runs *after* caption pairing so anything the
# paper captioned is already spoken for and cannot be reached.
SAME_SIZE_MIN_BOXES = 3
SAME_SIZE_MIN_PAGES = 2


def demote_same_size_unclaimed(layout: LayoutMap, box_kind: str) -> int:
    """Re-type same-size unclaimed bodies so they do not become carousel entries."""
    leftover = [b for b in layout.unused_boxes(box_kind)]
    groups: list[list[LayoutBox]] = []
    for box in leftover:
        w = float(box.rect["x1"]) - float(box.rect["x0"])
        h = float(box.rect["y1"]) - float(box.rect["y0"])
        for members in groups:
            m = members[0]
            mw = float(m.rect["x1"]) - float(m.rect["x0"])
            mh = float(m.rect["y1"]) - float(m.rect["y0"])
            if abs(w - mw) <= REPEAT_RECT_TOL_PT and abs(h - mh) <= REPEAT_RECT_TOL_PT:
                members.append(box)
                break
        else:
            groups.append([box])

    demoted = 0
    for members in groups:
        if len(members) < SAME_SIZE_MIN_BOXES:
            continue
        if len({m.page_index for m in members}) < SAME_SIZE_MIN_PAGES:
            continue
        for m in members:
            m.kind = "figure_chrome" if m.kind == "figure_body" else "table_chrome"
            demoted += 1
    return demoted


def append_unclaimed_body_slots(
    layout: LayoutMap, plan: SlotPlan, *, supplementary: bool = False
) -> int:
    """design/321 — give every Azure body a slot. Returns how many were added.

    Slot count comes from parsed caption numbers, and a body box only raised the
    floor to 1, so a paper whose captions are unlabeled or unparseable collapsed
    N bodies into one carousel entry. The rest were never rendered.

    Runs after caption pairing so numbered captions keep their own slots; only
    leftovers get appended. Each appended slot is given its body immediately, so
    it renders that crop under a generic label rather than a `(missing)`
    placeholder.
    """
    added = 0
    same_size_chrome = 0
    for box_kind, slot_kind in (("figure_body", "fig"), ("table_body", "table")):
        same_size_chrome += demote_same_size_unclaimed(layout, box_kind)
        leftover = layout.unused_boxes(box_kind)
        if not leftover:
            continue
        n = max((s.n for s in plan.slots if s.kind == slot_kind), default=0)
        for box in leftover:
            n += 1
            key = f"{slot_kind}:s{n}" if supplementary else f"{slot_kind}:{n}"
            if plan.slot_by_key(key) is not None:
                continue
            plan.slots.append(
                Slot(
                    key=key,
                    kind=slot_kind,
                    n=n,
                    status="empty",
                    # design/324 — `n` here is a carousel position, not a label
                    # the paper printed. Do not let it read as `Figure n`.
                    unnumbered=True,
                )
            )
            assign_body_boxes_to_slot(plan, layout, key, [box.id])
            added += 1
    if added:
        # design/92 — carousel stays all figures, then all tables, by number.
        plan.slots.sort(key=lambda s: (0 if s.kind == "fig" else 1, s.n))
    # design/356 — how many same-size bodies were kept out of the carousel, so the number
    # is reported rather than the removal being invisible.
    plan.same_size_chrome_n = same_size_chrome
    return added


def _has_body(slot: Slot) -> bool:
    return bool(slot.body_box_id or getattr(slot, "body_box_ids", None))


def _has_caption(slot: Slot) -> bool:
    return bool(
        slot.caption_box_id or getattr(slot, "caption_box_ids", None) or slot.caption_text
    )


def slot_census(layout: LayoutMap, plan: SlotPlan) -> dict[str, int]:
    """design/321 — what Azure found vs what the carousel will show.

    `unused_body_n` > 0 means Azure located a figure/table body that no slot
    claimed: those pixels never reach the user and every other counter stays
    green. `slot_n` < `body_n` is the caption-number collapse (design/321 B).

    design/336 — both of those verdicts are computed *after*
    `append_unclaimed_body_slots` has given every leftover a slot, so in the live
    pipeline `unused_body_n` is always 0 and `slot_n >= body_n` always holds. The
    10-paper audit confirms it: `unused_body_n: 0` on all ten. The loss that
    actually survives the repair is design/324's: a slot whose `n` is a carousel
    position rather than a number the paper printed. `unnumbered_n` counts that.
    """
    body_n = 0
    for box in layout.boxes:
        if box.kind in ("figure_body", "table_body"):
            body_n += 1
    counts = {"empty": 0, "partial": 0, "filled": 0}
    for slot in plan.slots:
        if slot.status == "user_confirmed":
            counts["filled"] += 1
        elif slot.status in counts:
            counts[slot.status] += 1
        else:
            counts["empty"] += 1
    unused_body_n = len(layout.unused_boxes("figure_body")) + len(
        layout.unused_boxes("table_body")
    )
    return {
        "body_n": body_n,
        "slot_n": len(plan.slots),
        "empty_n": counts["empty"],
        "partial_n": counts["partial"],
        "filled_n": counts["filled"],
        "unused_body_n": unused_body_n,
        "unnumbered_n": sum(1 for s in plan.slots if getattr(s, "unnumbered", False)),
        # design/337 — the pairing itself, which no counter reported. Measured over
        # ten papers: 92 slots paired, 13 captions with no image, and 51 images
        # with no caption. Azure splits a multi-panel figure into several body
        # boxes; the panels miss their caption's slot and each becomes its own
        # carousel entry, so a 13-item paper can produce 24 slots.
        "caption_without_body_n": sum(
            1 for s in plan.slots if _has_caption(s) and not _has_body(s)
        ),
        "body_without_caption_n": sum(
            1 for s in plan.slots if _has_body(s) and not _has_caption(s)
        ),
        # design/356 — same-size unclaimed bodies held back. On the RSC review this is 6
        # author headshots, which used to be 6 carousel entries.
        "same_size_chrome_n": int(getattr(plan, "same_size_chrome_n", 0) or 0),
    }


def refresh_slot_statuses(plan: SlotPlan) -> None:
    for slot in plan.slots:
        if slot.status == "user_confirmed":
            continue
        has_body = bool(slot.body_box_ids or slot.body_box_id)
        has_cap = bool(
            slot.caption_box_ids or slot.caption_box_id or slot.caption_text.strip()
        )
        if has_body and has_cap:
            slot.status = "filled"
        elif has_body or has_cap:
            slot.status = "partial"
        else:
            slot.status = "empty"


def initial_body_assignments(
    layout: LayoutMap, plan: SlotPlan, *, supplementary: bool = False
) -> None:
    """Assign Azure figure/table bodies to slots by caption number in nearby text."""
    for box in layout.boxes:
        if box.used_by_slot:
            continue
        if box.kind == "figure_body":
            cap_text = _nearest_caption_for_body(layout, box, fig=True)
            ckey = caption_key(cap_text) if cap_text else None
            sk = (
                slot_key_from_caption_key(ckey, supplementary=supplementary)
                if ckey
                else None
            )
            if sk and plan.slot_by_key(sk):
                assign_body_to_slot(plan, layout, sk, box.id)
        elif box.kind == "table_body":
            cap_text = _nearest_caption_for_body(layout, box, fig=False)
            ckey = caption_key(cap_text) if cap_text else None
            sk = (
                slot_key_from_caption_key(ckey, supplementary=supplementary)
                if ckey
                else None
            )
            if sk and plan.slot_by_key(sk):
                assign_body_to_slot(plan, layout, sk, box.id)


def demote_repeating_bodies(layout: LayoutMap) -> int:
    """Re-type running page graphics so they cannot become figures (design/338).

    A journal logo or masthead sits at the same coordinates on every page and Azure
    reports each copy as a `figure_body`. Before design/338 each copy became its own
    carousel entry; with the looser caption match they started joining real figure
    slots, so ChemistryOpen's Figure 1, 3 and 4 rendered with a logo glued above
    them. A real figure never repeats at the same rect on another page, so page
    span is the evidence.

    Measured over ten papers: nine have no repeating bodies at all, and
    ChemistryOpen has 3 groups covering 7 boxes. Returns how many were demoted.
    """
    def _same(a: LayoutBox, b: LayoutBox) -> bool:
        # Tolerance clustering, not bucket rounding: Azure's coordinates wobble a
        # point between copies, and two copies either side of a bucket edge used to
        # land in different groups, letting one logo through.
        return all(
            abs(float(a.rect[k]) - float(b.rect[k])) <= REPEAT_RECT_TOL_PT
            for k in ("x0", "y0", "x1", "y1")
        )

    groups: list[list[LayoutBox]] = []
    for box in layout.boxes:
        if box.kind not in ("figure_body", "table_body"):
            continue
        for members in groups:
            if _same(members[0], box):
                members.append(box)
                break
        else:
            groups.append([box])

    demoted = 0
    for members in groups:
        if len({m.page_index for m in members}) < REPEAT_MIN_PAGES:
            continue
        for m in members:
            m.kind = "figure_chrome" if m.kind == "figure_body" else "table_chrome"
            demoted += 1
    return demoted


def _x_overlap_frac(body: LayoutBox, cap: LayoutBox) -> float:
    """How much of `body`'s width sits inside `cap`'s (design/338)."""
    bx0, bx1 = float(body.rect["x0"]), float(body.rect["x1"])
    cx0, cx1 = float(cap.rect["x0"]), float(cap.rect["x1"])
    width = max(bx1 - bx0, 1.0)
    return max(0.0, min(bx1, cx1) - max(bx0, cx0)) / width


def _nearest_caption_for_body(layout: LayoutMap, body: LayoutBox, *, fig: bool) -> str:
    # design/220 — table overlap allowance (Azure caption/body bleed).
    want_kind = "figure_caption" if fig else "table_caption"
    overlap = FIG_CAPTION_OVERLAP_PT if fig else TABLE_CAPTION_OVERLAP_PT
    best: tuple[str, float] = ("", 1e9)
    for box in layout.boxes_on_page(body.page_index):
        if box.kind != want_kind or not box.text:
            continue
        if fig:
            gap = float(box.rect["y0"]) - float(body.rect["y1"])
            if gap < -overlap or gap > 200:
                continue
        else:
            gap = float(body.rect["y0"]) - float(box.rect["y1"])
            if gap < -overlap or gap > 200:
                continue
        # design/338 — horizontal overlap, not centre distance. Azure splits a
        # multi-panel figure into several body boxes, and a left-hand panel under a
        # full-width caption has its centre far from the caption's while sitting
        # almost entirely inside it. Measured over 130 figure bodies in ten papers:
        # the 16 bodies the centre rule rejected have a median centre offset of
        # 92.6pt (up to 318) but a median 0.76 of the body under the caption, while
        # every body the centre rule accepted overlaps by at least 0.68.
        if _x_overlap_frac(body, box) < CAPTION_X_OVERLAP_MIN:
            continue
        dist = abs(gap)
        if dist < best[1]:
            best = (box.text, dist)
    return best[0]


def merge_user_confirmed_slots(new_plan: SlotPlan, old_plan: SlotPlan | None) -> SlotPlan:
    """Reanalyze — preserve user_confirmed slot assignments."""
    if old_plan is None:
        return new_plan
    for old in old_plan.slots:
        if old.status != "user_confirmed":
            continue
        slot = new_plan.slot_by_key(old.key)
        if slot is None:
            new_plan.slots.append(Slot.from_dict(old.to_dict()))
            continue
        slot.body_box_id = old.body_box_id
        slot.caption_box_id = old.caption_box_id
        slot.caption_text = old.caption_text
        slot.status = "user_confirmed"
    return new_plan


def save_slot_plan(paper_dir: Path, plan: SlotPlan) -> Path:
    paper_dir.mkdir(parents=True, exist_ok=True)
    out = paper_dir / _SLOT_PLAN_NAME
    out.write_text(
        json.dumps(plan.to_dict(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return out


def load_slot_plan(paper_dir: Path) -> SlotPlan | None:
    path = paper_dir / _SLOT_PLAN_NAME
    if not path.is_file():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(raw, dict):
        return None
    return SlotPlan.from_dict(raw)
