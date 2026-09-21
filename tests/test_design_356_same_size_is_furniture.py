"""design/356 — six author headshots were six figures in the carousel.

`slot_census` reported `body_without_caption_n: 13` on the RSC review and a count is not
a cause. Opening all thirteen named them:

    6  author headshots, 114-115 x 141-143 points, each beside a biography
    6  front-page furniture: a cover graphic over 58% of page 1, the journal banner,
       the `View Article Online` badge on two pages, a logo by `Cite this:`
    1  a wide box in body text on page 7, which may be a real figure

Every one became its own carousel entry labelled `번호 없는 그림`, so studying the paper
meant swiping through six portraits of the authors.

design/338's detector misses them because it clusters on the whole rect and a journal logo
repeats at the *same* coordinates, while these six sit at six different positions. Their
signature is the **size**: within one or two points of each other, six times.

The demotion runs after caption pairing, so anything the paper captioned is already spoken
for and cannot be reached. Measured: the review's `body_without_caption_n` falls from 13 to
7 while `filled_n` stays at 27, and `cs5b00357` and `srep41797` are unchanged.
"""

from __future__ import annotations

from sentence_reading.pdf.layout_map import LayoutBox, LayoutMap
from sentence_reading.pdf.slot_plan import (
    SAME_SIZE_MIN_BOXES,
    SAME_SIZE_MIN_PAGES,
    append_unclaimed_body_slots,
    build_slot_plan,
    demote_same_size_unclaimed,
)


def _box(i: int, page: int, x: float, y: float, w: float, h: float, kind: str = "figure_body") -> LayoutBox:
    return LayoutBox(
        id=f"b{i}",
        page_index=page,
        kind=kind,
        rect={"x0": x, "y0": y, "x1": x + w, "y1": y + h},
        text="",
    )


def _map(boxes: list[LayoutBox]) -> LayoutMap:
    return LayoutMap(pages=[{"width_pt": 595, "height_pt": 842} for _ in range(8)], boxes=boxes)


def portraits() -> list[LayoutBox]:
    """The six headshots, at six different positions and the same size.

    Built fresh each time: the demotion rewrites `kind` in place, so a shared list would
    let one test decide what the next one sees.
    """
    return [
        _box(1, 2, 60, 100, 114, 141),
        _box(2, 2, 60, 300, 114, 141),
        _box(3, 2, 320, 100, 114, 142),
        _box(4, 2, 320, 300, 114, 143),
        _box(5, 3, 60, 100, 115, 143),
        _box(6, 3, 320, 100, 115, 143),
    ]


def test_six_same_size_unclaimed_bodies_are_furniture() -> None:
    layout = _map(portraits())
    assert demote_same_size_unclaimed(layout, "figure_body") == 6
    assert all(b.kind == "figure_chrome" for b in layout.boxes)


def test_they_never_reach_the_carousel() -> None:
    """Six entries labelled `번호 없는 그림` is what the reader used to swipe through."""
    layout = _map(portraits())
    plan = build_slot_plan(layout)
    assert append_unclaimed_body_slots(layout, plan) == 0
    # No caption means no numbered slot (design/358). What matters is that no
    # portrait was appended as unnumbered either.
    assert not [s for s in plan.slots if s.unnumbered]
    assert not [s for s in plan.slots if s.body_box_id or s.body_box_ids]


# ------------------------------------------------- what must not be demoted


def test_a_multi_panel_figure_on_one_page_is_left_alone() -> None:
    """Four equal panels of one figure look exactly like this, and one page is the
    difference. That is why two pages are required."""
    panels = [
        _box(1, 4, 60, 100, 120, 120),
        _box(2, 4, 200, 100, 120, 120),
        _box(3, 4, 60, 240, 120, 120),
        _box(4, 4, 200, 240, 120, 120),
    ]
    layout = _map(panels)
    assert demote_same_size_unclaimed(layout, "figure_body") == 0
    assert all(b.kind == "figure_body" for b in layout.boxes)


def test_two_of_a_size_is_not_enough() -> None:
    """The `View Article Online` badge appears twice. Two is a coincidence a real paper
    can produce; it needs its own evidence, not this rule."""
    pair = [_box(1, 0, 400, 60, 145, 40), _box(2, 1, 400, 60, 146, 40)]
    layout = _map(pair)
    assert demote_same_size_unclaimed(layout, "figure_body") == 0


def test_figures_of_different_sizes_are_left_alone() -> None:
    boxes = [
        _box(1, 1, 60, 100, 400, 300),
        _box(2, 2, 60, 100, 250, 180),
        _box(3, 3, 60, 100, 500, 120),
    ]
    layout = _map(boxes)
    assert demote_same_size_unclaimed(layout, "figure_body") == 0


def test_a_captioned_figure_is_out_of_reach() -> None:
    """The demotion only sees bodies no caption claimed, because it runs after pairing.
    A box already assigned to a slot is not among them."""
    layout = _map(portraits())
    layout.boxes[0].used_by_slot = "fig:1"
    layout.boxes[1].used_by_slot = "fig:2"
    layout.boxes[2].used_by_slot = "fig:3"
    # Three of six are claimed, leaving three unclaimed over two pages.
    demoted = demote_same_size_unclaimed(layout, "figure_body")
    assert demoted == 3
    assert [b.kind for b in layout.boxes[:3]] == ["figure_body"] * 3


def test_tables_use_their_own_kind() -> None:
    boxes = [
        _box(i, p, 60, 100 + 200 * (i % 2), 200, 90, kind="table_body")
        for i, p in enumerate((2, 2, 3), start=1)
    ]
    layout = _map(boxes)
    assert demote_same_size_unclaimed(layout, "table_body") == 3
    assert all(b.kind == "table_chrome" for b in layout.boxes)


def test_the_bounds_say_what_they_mean() -> None:
    assert SAME_SIZE_MIN_BOXES == 3
    assert SAME_SIZE_MIN_PAGES == 2
