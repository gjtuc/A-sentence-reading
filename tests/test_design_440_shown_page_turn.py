"""design/440 — the turn is read in the page as shown, after its `/Rotate`."""

from __future__ import annotations

import io

import fitz
from PIL import Image

from sentence_reading.pdf.composite import composite_sideways_png
from sentence_reading.pdf.page_turn import CCW, CW, page_turn, rect_turn


def _page(rotation: int):
    doc = fitz.open()
    page = doc.new_page(width=595, height=794)
    for i in range(12):
        page.insert_text((300, 120 + 30 * i), "Potential (V) vs. NHE line", fontsize=9)
    page.set_rotation(rotation)
    return doc, page


def _shown_block(page) -> fitz.Rect:
    return fitz.Rect(290, 100, 560, 480) * page.rotation_matrix


def test_stored_upright_text_on_a_rotate_90_page_turns_counter_clockwise() -> None:
    doc, page = _page(90)
    assert page_turn(page) == CCW
    assert rect_turn(page, _shown_block(page), min_lines=2) == CCW
    doc.close()


def test_rotate_270_turns_the_other_way() -> None:
    doc, page = _page(270)
    assert page_turn(page) == CW
    doc.close()


def test_rotation_zero_is_unchanged() -> None:
    doc, page = _page(0)
    assert page_turn(page) == ""
    doc.close()


def test_a_box_is_matched_in_the_shown_space() -> None:
    """Azure boxes are in the shown page; a box away from the block finds nothing."""
    doc, page = _page(90)
    assert rect_turn(page, fitz.Rect(0, 0, 200, 90), min_lines=2) == ""
    assert rect_turn(page, _shown_block(page), min_lines=2) == CCW
    doc.close()


def test_the_sideways_crop_comes_out_tall() -> None:
    """The stored block is taller than wide, so upright it is tall again."""
    doc, page = _page(90)
    shown = _shown_block(page)
    png = composite_sideways_png(page, shown, None, rect_turn(page, shown), zoom=1.0)
    im = Image.open(io.BytesIO(png))
    assert im.height > im.width
    im.close()
    doc.close()
