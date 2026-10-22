"""design/443 - a caption under a running head, and a table carried onto the next page.

The Advanced Materials SI (adma201600469) prints `Submitted to` at the top of every page.
On its landscape page 19 the caption `Table S1.` starts 1pt under it and Azure returns
one paragraph for both, so no caption read and Table S1 rendered `(missing)`. The same
table runs on to the top of page 20 with no heading, and once the caption reads, the
caption list is complete and design/357 would hold that second part back.
"""

from __future__ import annotations

from types import SimpleNamespace

from sentence_reading.pdf.caption_pairing import attach_carried_table_pages
from sentence_reading.pdf.layout_map import LayoutBox, LayoutMap, build_layout_map_from_result
from sentence_reading.pdf.slot_plan import Slot, SlotPlan

_PT = 72.0


class _Hit:
    def __init__(self, x0: float, y0: float) -> None:
        self.x0, self.y0 = x0, y0


class _Page:
    def __init__(self, w: float, h: float, hits: dict[str, list[_Hit]] | None = None) -> None:
        self.rect = SimpleNamespace(width=w, height=h)
        self.rotation = 0
        self._hits = hits or {}

    def get_text(self, kind: str) -> dict:
        return {"blocks": []}

    def search_for(self, needle: str) -> list[_Hit]:
        return self._hits.get(needle, [])


def _para(page: int, x0: float, y0: float, x1: float, y1: float, text: str):
    poly = [x0 / _PT, y0 / _PT, x1 / _PT, y0 / _PT, x1 / _PT, y1 / _PT, x0 / _PT, y1 / _PT]
    region = SimpleNamespace(page_number=page + 1, polygon=poly)
    return SimpleNamespace(bounding_regions=[region], content=text)


def _result(paras) -> SimpleNamespace:
    return SimpleNamespace(paragraphs=paras, figures=[], tables=[], model_id="m")


def _si_pages() -> list[_Page]:
    portrait = [_Page(595.0, 842.0) for _ in range(3)]
    landscape = _Page(842.0, 595.0, {"Table S1": [_Hit(85.0, 79.0)]})
    return [*portrait, landscape]


def _layout(caption_text: str, *, head_pages=(0, 1, 2)) -> LayoutMap:
    paras = [_para(p, 331, 67, 394, 79, "Submitted to") for p in head_pages]
    paras.append(_para(3, 85, 67, 528, 93, caption_text))
    paras.append(_para(3, 84, 93, 145, 111, "Methods."))
    return build_layout_map_from_result(_result(paras), _si_pages())


def _caption_box(layout: LayoutMap) -> LayoutBox:
    return next(b for b in layout.boxes if b.page_index == 3 and b.rect["y0"] < 90)


def test_the_running_head_comes_off_the_caption() -> None:
    layout = _layout("Submitted to Table S1. A detailed comparison of methods.")
    cap = _caption_box(layout)
    assert cap.kind == "table_caption"
    assert cap.text == "Table S1. A detailed comparison of methods."
    assert cap.rect["y0"] > 78  # starts at the caption's line, not the head's


def test_the_heads_on_their_own_pages_stay_paragraphs() -> None:
    layout = _layout("Submitted to Table S1. A detailed comparison of methods.")
    heads = [b for b in layout.boxes if b.text == "Submitted to"]
    assert len(heads) == 3
    assert all(b.kind == "paragraph" for b in heads)


def test_a_head_printed_on_one_page_only_is_not_a_running_head() -> None:
    layout = _layout("Submitted to Table S1. A detailed comparison.", head_pages=(0,))
    cap = _caption_box(layout)
    assert cap.kind == "paragraph"
    assert cap.text.startswith("Submitted to")


def test_body_text_after_a_head_does_not_become_a_caption() -> None:
    layout = _layout("Submitted to Table S1 shows the methods we compared.")
    assert _caption_box(layout).kind == "paragraph"


def test_short_text_repeated_mid_page_is_not_a_head() -> None:
    """Table cells like `NA` repeat on many pages; they sit in the page, not its band."""
    paras = [_para(p, 300, 400, 320, 410, "NA") for p in (0, 1, 2)]
    paras.append(_para(3, 85, 300, 528, 320, "NA Table S1. A detailed comparison."))
    layout = build_layout_map_from_result(_result(paras), _si_pages())
    box = next(b for b in layout.boxes if b.page_index == 3)
    assert box.kind == "paragraph"


# ------------------------------------------------------------------ carried table


def _box(bid: str, kind: str, page: int, x0, y0, x1, y1, text: str = "") -> LayoutBox:
    return LayoutBox(
        id=bid,
        page_index=page,
        kind=kind,
        rect={"x0": x0, "y0": y0, "x1": x1, "y1": y1},
        text=text,
    )


def _carried(extra: list[LayoutBox] | None = None) -> tuple[LayoutMap, SlotPlan]:
    """Table S1 from the foot of page 18 to the top of page 19 (0-based), as Azure gave it."""
    pages = [{"page_index": i, "width_pt": 842.0, "height_pt": 595.0} for i in (18, 19, 20)]
    boxes = [
        _box("cap", "table_caption", 18, 85, 79, 528, 93, "Table S1. A detailed comparison"),
        _box("t18", "table_body", 18, 79, 93, 761, 519),
        _box("t19", "table_body", 19, 93, 81, 760, 220),
        *(extra or []),
    ]
    layout = LayoutMap(pages=pages, boxes=boxes)
    slot = Slot(key="table:s1", kind="table", n=1, status="filled")
    slot.caption_box_id = "cap"
    slot.body_box_id = "t18"
    slot.body_box_ids = ["t18"]
    layout.box_by_id("t18").used_by_slot = "table:s1"
    layout.box_by_id("cap").used_by_slot = "table:s1"
    return layout, SlotPlan(slots=[slot])


def test_the_part_on_the_next_page_joins_the_table() -> None:
    layout, plan = _carried()
    assert attach_carried_table_pages(layout, plan) == 1
    slot = plan.slot_by_key("table:s1")
    assert slot.body_box_ids == ["t18", "t19"]
    assert slot.continued is True
    assert layout.unused_boxes("table_body") == []


def test_a_page_with_its_own_table_caption_is_a_new_table() -> None:
    layout, plan = _carried([_box("cap2", "table_caption", 19, 93, 60, 500, 75, "Table S2. X")])
    assert attach_carried_table_pages(layout, plan) == 0


def test_a_table_ending_mid_page_is_not_carried() -> None:
    layout, plan = _carried()
    layout.box_by_id("t18").rect["y1"] = 300
    assert attach_carried_table_pages(layout, plan) == 0


def test_a_part_starting_low_on_the_page_is_not_carried() -> None:
    layout, plan = _carried()
    layout.box_by_id("t19").rect.update({"y0": 300, "y1": 450})
    assert attach_carried_table_pages(layout, plan) == 0


def test_a_part_with_other_edges_is_not_carried() -> None:
    layout, plan = _carried()
    layout.box_by_id("t19").rect.update({"x0": 300, "x1": 760})
    assert attach_carried_table_pages(layout, plan) == 0


def test_a_table_carried_over_three_pages_takes_all_of_them() -> None:
    layout, plan = _carried([_box("t20", "table_body", 20, 80, 70, 760, 400)])
    layout.box_by_id("t19").rect["y1"] = 540
    assert attach_carried_table_pages(layout, plan) == 2
    assert plan.slot_by_key("table:s1").body_box_ids == ["t18", "t19", "t20"]
