"""design/361 — which way a sideways page has to turn, from the page's own text.

Journals print a wide table or figure by rotating it onto a portrait page. The crop we
render then comes out lying on its side and the reader has to tilt the phone.

The direction is not guessed. PyMuPDF gives every text line a unit vector along its
baseline, so the page says which way it was set:

    (1, 0)   upright — the baseline runs left to right
    (0, -1)  the baseline runs up the page, so the image turns clockwise to read
    (0, 1)   the baseline runs down the page, so it turns counter-clockwise

The PDF's own `/Rotate` key is not usable for this. Measured on Advanced Energy
Materials' six-page Table 1: `page.rotation` is 0 on every one of pages 22–27, while
165 of page 22's 171 text lines report `(0, -1)`.

Measured over 88 papers: 4 have a sideways page, 9 pages in all, every one clockwise.
"""

from __future__ import annotations

from collections import Counter

# A page mixes the rotated block with an upright running header and folio, so a
# majority is the test, not unanimity. Page 22 above is 165/171 = 0.96; the lowest
# of the nine is 122/187 = 0.65 on `1-s2.0-S0021951716000488` page 3, where half the
# page is upright prose above a sideways table.
TURN_MAJORITY = 0.6
# Below this a page has too little text to claim anything. A figure-only page says
# nothing about its own orientation and is left alone.
TURN_MIN_LINES = 8

CW = "cw"
CCW = "ccw"


def line_directions(page) -> Counter[tuple[int, int]]:
    """Every text line's baseline direction on this page, rounded to an axis."""
    tally: Counter[tuple[int, int]] = Counter()
    try:
        blocks = page.get_text("dict").get("blocks") or []
    except Exception:  # noqa: BLE001
        return tally
    for block in blocks:
        if block.get("type") != 0:
            continue
        for line in block.get("lines") or []:
            d = line.get("dir") or (1.0, 0.0)
            try:
                tally[(round(float(d[0])), round(float(d[1])))] += 1
            except (TypeError, ValueError):
                continue
    return tally


def page_turn(page) -> str:
    """`"cw"`, `"ccw"`, or `""` when the page reads upright or cannot say."""
    tally = line_directions(page)
    total = sum(tally.values())
    if total < TURN_MIN_LINES:
        return ""
    if tally.get((0, -1), 0) >= TURN_MAJORITY * total:
        return CW
    if tally.get((0, 1), 0) >= TURN_MAJORITY * total:
        return CCW
    return ""


def rect_turn(page, rect, *, min_lines: int = 1) -> str:
    """The turn of the lines inside `rect`, for a sideways block on an upright page.

    `1-s2.0-S0021951716000488` page 3 prints upright prose above a sideways table, so
    the page majority is thin. Asking the caption's own box is the sharper question.
    """
    if rect is None:
        return ""
    tally: Counter[tuple[int, int]] = Counter()
    try:
        blocks = page.get_text("dict").get("blocks") or []
    except Exception:  # noqa: BLE001
        return ""
    for block in blocks:
        if block.get("type") != 0:
            continue
        for line in block.get("lines") or []:
            bbox = line.get("bbox") or (0, 0, 0, 0)
            if not _intersects(rect, bbox):
                continue
            d = line.get("dir") or (1.0, 0.0)
            try:
                tally[(round(float(d[0])), round(float(d[1])))] += 1
            except (TypeError, ValueError):
                continue
    total = sum(tally.values())
    if total < min_lines:
        return ""
    if tally.get((0, -1), 0) >= TURN_MAJORITY * total:
        return CW
    if tally.get((0, 1), 0) >= TURN_MAJORITY * total:
        return CCW
    return ""


def _intersects(rect, bbox) -> bool:
    try:
        bx0, by0, bx1, by1 = (float(v) for v in bbox)
    except (TypeError, ValueError):
        return False
    return (
        float(rect.x0) < bx1
        and bx0 < float(rect.x1)
        and float(rect.y0) < by1
        and by0 < float(rect.y1)
    )
