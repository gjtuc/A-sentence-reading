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


@dataclass
class Slot:
    key: str
    kind: str
    n: int
    status: str = "empty"
    body_box_id: str = ""
    caption_box_id: str = ""
    caption_text: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "kind": self.kind,
            "n": self.n,
            "status": self.status,
            "body_box_id": self.body_box_id or None,
            "caption_box_id": self.caption_box_id or None,
            "caption_text": self.caption_text,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> Slot:
        return cls(
            key=str(raw.get("key") or ""),
            kind=str(raw.get("kind") or "fig"),
            n=int(raw.get("n") or 0),
            status=str(raw.get("status") or "empty"),
            body_box_id=str(raw.get("body_box_id") or ""),
            caption_box_id=str(raw.get("caption_box_id") or ""),
            caption_text=str(raw.get("caption_text") or ""),
        )


@dataclass
class SlotPlan:
    slots: list[Slot] = field(default_factory=list)

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


def assign_body_to_slot(
    plan: SlotPlan,
    layout: LayoutMap,
    slot_key: str,
    body_box_id: str,
) -> None:
    slot = plan.slot_by_key(slot_key)
    box = layout.box_by_id(body_box_id)
    if slot is None or box is None:
        return
    slot.body_box_id = body_box_id
    box.used_by_slot = slot.key
    if slot.caption_box_id or slot.caption_text:
        slot.status = "filled" if slot.caption_box_id else "partial"
    else:
        slot.status = "partial"


def assign_caption_to_slot(
    plan: SlotPlan,
    layout: LayoutMap,
    slot_key: str,
    caption_box_id: str,
    caption_text: str = "",
) -> None:
    slot = plan.slot_by_key(slot_key)
    box = layout.box_by_id(caption_box_id)
    if slot is None:
        return
    if box is not None:
        slot.caption_box_id = caption_box_id
        box.used_by_slot = slot.key
        if not caption_text:
            caption_text = box.text
    slot.caption_text = caption_text
    if slot.body_box_id:
        slot.status = "filled"
    else:
        slot.status = "partial"


def refresh_slot_statuses(plan: SlotPlan) -> None:
    for slot in plan.slots:
        if slot.status == "user_confirmed":
            continue
        has_body = bool(slot.body_box_id)
        has_cap = bool(slot.caption_box_id or slot.caption_text.strip())
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


def _nearest_caption_for_body(layout: LayoutMap, body: LayoutBox, *, fig: bool) -> str:
    want_kind = "figure_caption" if fig else "table_caption"
    best: tuple[str, float] = ("", 1e9)
    for box in layout.boxes_on_page(body.page_index):
        if box.kind != want_kind or not box.text:
            continue
        if fig:
            gap = float(box.rect["y0"]) - float(body.rect["y1"])
            if gap < -8 or gap > 200:
                continue
        else:
            gap = float(body.rect["y0"]) - float(box.rect["y1"])
            if gap < -8 or gap > 200:
                continue
        mid_cap = (float(box.rect["x0"]) + float(box.rect["x1"])) / 2.0
        mid_body = (float(body.rect["x0"]) + float(body.rect["x1"])) / 2.0
        if abs(mid_cap - mid_body) > 48:
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
