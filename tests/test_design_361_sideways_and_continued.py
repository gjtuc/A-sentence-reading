"""design/361 - a sideways table turns upright, and a continued table is one table.

Two defects found together, both on Advanced Energy Materials' Table 1.

It is printed sideways across pages 22-27. The direction is not guessed: PyMuPDF gives
each text line a baseline vector, and 165 of page 22's 171 lines report (0,-1) - the
baseline runs up the sheet - while `page.rotation` is 0 on every one of those pages.
Over 88 papers, 4 have a sideways page, 9 pages, every one clockwise.

Only page 22 was drawn. Pages 23-27 each carry a 21-character `Table 1. (Continued)`
heading and became unclaimed bodies, so the reader saw one sixth of the table while
every count said `filled`. Four other papers repeat a caption number across pages
without saying `Continued` - a graphical-abstract label, a cross-reference Azure typed
as a caption - so the word is required.
"""

from __future__ import annotations

import io

from PIL import Image

from sentence_reading.pdf.caption_pairing import attach_continued_pages
from sentence_reading.pdf.composite import VSTACK_MAX_PIXELS, rotate_png, zoom_for_area
from sentence_reading.pdf.layout_map import LayoutBox, LayoutMap
from sentence_reading.pdf.page_turn import CCW, CW, page_turn, rect_turn
from sentence_reading.pdf.slot_plan import Slot, SlotPlan


class _Rect:
    def __init__(self, x0: float, y0: float, x1: float, y1: float) -> None:
        self.x0, self.y0, self.x1, self.y1 = x0, y0, x1, y1


class _Page:
    """Enough of a PyMuPDF page for the direction reader."""

    def __init__(self, lines: list[tuple[tuple[float, float], tuple]]) -> None:
        self._lines = lines

    def get_text(self, kind: str) -> dict:
        assert kind == "dict"
        return {
            "blocks": [
                {
                    "type": 0,
                    "lines": [{"dir": d, "bbox": b} for d, b in self._lines],
                }
            ]
        }


def _upright(n: int, y0: float = 100.0) -> list:
    return [((1.0, 0.0), (50.0, y0 + i, 500.0, y0 + i + 9)) for i in range(n)]


def _sideways(n: int, d=(0.0, -1.0), x0: float = 50.0) -> list:
    return [(d, (x0 + i, 100.0, x0 + i + 9, 700.0)) for i in range(n)]


def _box(bid: str, kind: str, x0, y0, x1, y1, text: str = "", page: int = 0) -> LayoutBox:
    return LayoutBox(
        id=bid,
        page_index=page,
        kind=kind,
        rect={"x0": x0, "y0": y0, "x1": x1, "y1": y1},
        text=text,
    )


def _png(w: int, h: int, colour=(10, 20, 30)) -> bytes:
    im = Image.new("RGB", (w, h), colour)
    out = io.BytesIO()
    im.save(out, format="PNG")
    im.close()
    return out.getvalue()


# ------------------------------------------------------------------ direction


def test_a_page_whose_baselines_run_up_turns_clockwise() -> None:
    """Page 22's ratio: 165 rotated of 171."""
    page = _Page(_sideways(165) + _upright(6))
    assert page_turn(page) == CW


def test_a_page_whose_baselines_run_down_turns_counter_clockwise() -> None:
    page = _Page(_sideways(40, d=(0.0, 1.0)))
    assert page_turn(page) == CCW


def test_an_upright_page_is_left_alone() -> None:
    assert page_turn(_Page(_upright(60))) == ""


def test_a_page_with_almost_no_text_claims_nothing() -> None:
    """A figure-only page says nothing about its own orientation."""
    assert page_turn(_Page(_sideways(3))) == ""


def test_a_sideways_block_on_an_upright_page_is_found_by_its_own_box() -> None:
    """`1-s2.0-S0021951716000488` page 3: prose above, a sideways table below."""
    page = _Page(_upright(65, y0=60.0) + _sideways(122, x0=300.0))
    assert page_turn(page) == CW  # 122/187 = 0.65, just over the majority
    # And when the majority is too thin, the caption's own box still answers. The prose
    # sits above the block, as it does on that page, so the box sees only the block.
    thin = _Page(_upright(120, y0=60.0) + _sideways(40, x0=300.0))
    assert page_turn(thin) == ""
    assert rect_turn(thin, _Rect(295.0, 200.0, 360.0, 720.0), min_lines=2) == CW


def test_rect_turn_ignores_lines_outside_the_box() -> None:
    page = _Page(_upright(30, y0=60.0) + _sideways(30, x0=300.0))
    assert rect_turn(page, _Rect(40.0, 50.0, 520.0, 100.0), min_lines=2) == ""


# ------------------------------------------------------------------ rotation


def test_clockwise_rotation_swaps_the_sides() -> None:
    turned = rotate_png(_png(400, 100), CW)
    im = Image.open(io.BytesIO(turned))
    assert (im.width, im.height) == (100, 400)
    im.close()


def test_an_empty_turn_returns_the_image_unchanged() -> None:
    raw = _png(400, 100)
    assert rotate_png(raw, "") is raw


def test_the_two_turns_are_opposite() -> None:
    """A clockwise then counter-clockwise turn is the identity."""
    raw = _png(60, 20, colour=(200, 30, 40))
    once = rotate_png(raw, CW)
    back = rotate_png(once, CCW)
    a = Image.open(io.BytesIO(raw))
    b = Image.open(io.BytesIO(back))
    assert a.size == b.size
    assert a.tobytes() == b.tobytes()
    a.close()
    b.close()


# ------------------------------------------------------------------ zoom budget


def test_six_full_pages_drop_below_the_usual_zoom() -> None:
    """Six pages at 8x is 135 megapixels; the budget lowers the zoom instead."""
    rects = [_Rect(49.0, 30.0, 539.0, 750.0) for _ in range(6)]
    zoom = zoom_for_area(rects)
    assert 2.0 < zoom < 8.0
    area = sum((r.x1 - r.x0) * (r.y1 - r.y0) for r in rects)
    assert area * zoom * zoom <= VSTACK_MAX_PIXELS * 1.01


def test_one_ordinary_figure_keeps_the_full_zoom() -> None:
    assert zoom_for_area([_Rect(50.0, 100.0, 300.0, 300.0)]) == 8.0


def test_the_zoom_never_goes_below_two() -> None:
    huge = [_Rect(0.0, 0.0, 600.0, 800.0) for _ in range(80)]
    assert zoom_for_area(huge) == 2.0


# ------------------------------------------------------------------ continued


def _continued_plan() -> tuple[LayoutMap, SlotPlan]:
    """Table 1 on page 22, continued on 23 and 24."""
    boxes = [
        _box("t22", "table_body", 70, 38, 539, 734, page=22),
        _box("c22", "table_caption", 49, 419, 59, 719, "Table 1. Summary of", page=22),
        _box("t23", "table_body", 79, 70, 516, 717, page=23),
        _box("c23", "table_caption", 49, 400, 59, 470, "Table 1. (Continued)", page=23),
        _box("t24", "table_body", 45, 21, 551, 754, page=24),
        _box("c24", "table_caption", 49, 400, 64, 466, "Table 1. (Continued)", page=24),
    ]
    layout = LayoutMap(boxes=boxes)
    slot = Slot(key="table:1", kind="table", n=1, status="filled")
    slot.caption_box_id = "c22"
    slot.caption_text = "Table 1. Summary of"
    slot.body_box_id = "t22"
    slot.body_box_ids = ["t22"]
    layout.box_by_id("t22").used_by_slot = "table:1"
    layout.box_by_id("c22").used_by_slot = "table:1"
    return layout, SlotPlan(slots=[slot])


def test_the_later_pages_join_the_same_slot() -> None:
    layout, plan = _continued_plan()
    assert attach_continued_pages(layout, plan) == 2
    slot = plan.slot_by_key("table:1")
    assert slot is not None
    assert slot.body_box_ids == ["t22", "t23", "t24"]
    assert slot.continued is True
    assert layout.unused_boxes("table_body") == []


def test_a_page_an_earlier_pass_already_attached_is_still_marked() -> None:
    """`1-s2.0-S0360319924023218` page 2 arrives already claimed by its own slot.

    Nothing is left to join, but without the mark the render path draws page 1 only.
    """
    layout, plan = _continued_plan()
    slot = plan.slot_by_key("table:1")
    assert slot is not None
    slot.body_box_ids = ["t22", "t23"]
    layout.box_by_id("t23").used_by_slot = "table:1"
    assert attach_continued_pages(layout, plan) == 1  # page 24 joins
    assert slot.continued is True
    assert slot.body_box_ids == ["t22", "t23", "t24"]


def test_holding_two_pages_is_not_by_itself_a_continuation() -> None:
    """The `Scheme N` / `Figure N` collision puts two pictures in one slot.

    `d4se00467a` gives fig:1 Scheme 1 on page 2 and Figure 1 on page 3, because
    `slot_key_from_caption_key` folds `scheme:1` into `fig:1`. Drawing both would
    stack two unrelated pictures under one label, so the mark is required.
    """
    layout, plan = _continued_plan()
    for bid in ("c23", "c24"):
        layout.box_by_id(bid).text = "Scheme 1. Reactor diagram"
    assert attach_continued_pages(layout, plan) == 0
    slot = plan.slot_by_key("table:1")
    assert slot is not None
    assert slot.continued is False


def test_a_repeated_number_without_the_word_is_not_joined() -> None:
    """Four papers repeat a caption number across pages and mean something else."""
    layout, plan = _continued_plan()
    for bid in ("c23", "c24"):
        layout.box_by_id(bid).text = "Table 1. Summary of catalysts"
    assert attach_continued_pages(layout, plan) == 0
    slot = plan.slot_by_key("table:1")
    assert slot is not None
    assert slot.body_box_ids == ["t22"]


def test_a_continuation_before_the_slots_own_page_is_refused() -> None:
    """A table continues forward. A `Continued` box on an earlier page is not ours."""
    layout, plan = _continued_plan()
    layout.box_by_id("c23").page_index = 2
    layout.box_by_id("t23").page_index = 2
    assert attach_continued_pages(layout, plan) == 1  # page 24 still joins


def test_a_continuation_never_takes_a_figure() -> None:
    layout, plan = _continued_plan()
    layout.box_by_id("t23").kind = "figure_body"
    layout.box_by_id("t24").kind = "figure_body"
    assert attach_continued_pages(layout, plan) == 0


def test_an_empty_slot_is_not_extended() -> None:
    """With no first page there is nothing to continue."""
    layout, plan = _continued_plan()
    slot = plan.slot_by_key("table:1")
    assert slot is not None
    slot.body_box_id = ""
    slot.body_box_ids = []
    layout.box_by_id("t22").used_by_slot = ""
    assert attach_continued_pages(layout, plan) == 0


def test_a_user_confirmed_slot_is_left_alone() -> None:
    layout, plan = _continued_plan()
    slot = plan.slot_by_key("table:1")
    assert slot is not None
    slot.status = "user_confirmed"
    assert attach_continued_pages(layout, plan) == 0
