# 361 — The page says which way up

**Version:** 0.3.357 · Status: **locked**
Found by the held-box audit in [360](360-stop-guessing-what-a-picture-is.md) · extends [338](338-panel-pairing-and-page-graphics.md) panel union

## Why

design/360 left 275 unclaimed bodies held back by the caption list. Classifying every
one of them by "is there a numbered caption within 30pt" gave:

| | boxes |
|---|---|
| no caption within 30pt — the paper never named it | 254 |
| a caption is near and **its slot is already filled** | 15 |
| a caption is near but its number did not parse | 6 |
| **a caption is near and its slot is empty** | **0** |

Nothing was lost to the holding itself. But ten of the 15 turned out to be Wiley and
ACS page badges, and **five were pages 23–27 of Advanced Energy Materials' Table 1**.

That table runs across pages 22–27. Each later page is headed by a 21-character
`Table 1. (Continued)`. The slot took page 22 and the other five pages were filed as
unclaimed bodies, so the reader saw **one sixth of Table 1** while `slot_census` said
`filled`. No metric could see it: the census asks whether a slot has *a* body, not
whether it has all of them. `1-s2.0-S0360319924023218` has the same table over two
pages; its page-2 body was already attached, and only the render drew one page.

And the same table is printed **sideways**. Its caption is a 10×300pt strip standing in
the left margin. The crop came out lying on its side and the reader had to turn the
phone.

## Locked

### The rotation is read, not guessed

`src/sentence_reading/pdf/page_turn.py`. PyMuPDF gives every text line a unit vector
along its baseline, so the page states how it was set:

| `line["dir"]` | meaning | turn |
|---|---|---|
| `(1, 0)` | reads left to right | upright |
| `(0, -1)` | reads up the sheet | **clockwise** |
| `(0, 1)` | reads down the sheet | counter-clockwise |

The PDF's own `/Rotate` key cannot be used: `page.rotation` is **0** on all six of
those pages while 165 of page 22's 171 lines report `(0, -1)`.

A majority (0.6) decides, not unanimity, because a sideways page still carries an
upright running header and folio. Under 8 lines a page claims nothing — a figure-only
page says nothing about its own orientation.

`rect_turn` asks the same question of one box, for a sideways block on an otherwise
upright page. `1-s2.0-S0021951716000488` page 3 prints prose above a sideways table and
is only 122/187 = 0.65 rotated; the caption's own box is unambiguous.

The turn is recorded per page in `LayoutMap.pages[i]["turn"]`, filled in the one loop
that already opens the PyMuPDF page for its width and height. `turn_of_page` reads `""`
for a map stored before this change, so an old cache reads as upright.

### Rendering turns the crop, and cuts caption and body together

`composite_sideways_png` clips caption and body in **one** rect and turns it once.
The upright path clips them separately and stacks top to bottom, which is wrong here:
Table 1's caption is at `x 49..59` and the table at `x 70..539`, so the caption is to
the *left*. Turning one clip puts it back on top with no rule about which side a
caption takes. The page already laid it out; we only re-orient it.

`rotate_png` uses PIL. `ROTATE_90` turns counter-clockwise, so `cw` maps to 270.

### A continued caption joins the slot it names

`attach_continued_pages`. A caption box joins an existing slot when **all** of:

- its text says `Continued` / `Cont.` / `Cont'd` — the paper's own word
- its parsed number matches a slot that already holds a body
- that body is on an **earlier** page
- an unclaimed body **of the slot's kind** sits within 40pt on the caption's page

The word is required and not inferred from adjacency, because four papers repeat a
caption number across pages and mean something else: `1-s2.0-S0021951716000488` prints
`Table 1` on pages 3 and 5 with no table beside the second, `appl_catal_b` the same for
`Fig. 3`, and `Advanced Materials - 2024 - He` carries a 48-character `Figure 1` label
on page 1 beside the 1050-character caption on page 4 — a graphical abstract.

### Every page of a *continued* slot is drawn

`_slot_body_pages` and `_slot_page_rect` in `extract_figures_v2`. A slot renders one
strip per page, in page order, and stacks them — but **only when `Slot.continued` is
set**, which happens solely in `attach_continued_pages`, on the paper's own word. The
caption is drawn on its own page only, so `(Continued)` headings stay where the paper
put them.

Holding bodies on two pages is *not* by itself evidence of a continuation. Measured
over 88 papers, 4 slots span more than one page and only 2 are continued tables; the
other 2 are a different defect (below). Gating on the mark keeps them unchanged.

### The pixel budget is spent by rendering smaller

Six pages at the usual 8× zoom is 5960×22702 = 135 megapixels and a 3.8 MB PNG.
Shrinking the finished canvas made it **worse** — resampling a table of 7pt type turns
crisp glyph edges into grey ramps and the PNG came out at 4.4 MB. `zoom_for_area`
instead picks the render zoom that fits the strips into 41 megapixels together (the
area the existing 6400px side cap already implies), floored at 2× so type stays
readable. Result: 3480×13259, **2.47 MB**, and the 7pt table body — subscripts included
— is still sharp.

## Measured

| | before | after |
|---|---|---|
| Advanced Energy Materials Table 1 | page 22 only, sideways | pages 22–27, upright, 2.47 MB |
| `1-s2.0-S0360319924023218` Table 1 | page 1 only | pages 1–2 |
| `1-s2.0-S0021951716000488` Table 1 | sideways | upright |

Sideways pages over 88 papers: 4 papers, 9 pages, **all clockwise**, none
counter-clockwise.

## Found while measuring, not fixed here

**`Scheme N` and `Figure N` share one slot.** `caption_key` keeps them apart
(`scheme:1` vs `fig:1`) and `slot_key_from_caption_key` then folds both to `fig:1`:

```python
slot_kind = "table" if kind == "table" else "fig"
```

So on `d4se00467a` slot `fig:1` holds Scheme 1's reactor diagram from page 2 *and*
Figure 1's isotherms from page 3, and only one of them is ever drawn — under the label
`Figure 1`. `Advanced Materials - 2024 - He` is the same, with Scheme 1's graphical
abstract on page 1 and Figure 1's five panels on page 4.

Measured: 3 of 88 papers print a Scheme, and **all 3 collide** with a Figure of the same
number. The paper says these are different things. Giving schemes their own slot kind
touches the slot key, the number scan, the completeness test, the carousel order
(design/92 puts Fig → Scheme → Table), the labels and `fig_refs`' reference chips, so it
is its own change.

## What is not locked

The journal's running side-text comes along inside the clip, as it did before. The six
held boxes beside a caption whose number did not parse are still unidentified.

## Test

`tests/test_design_361_sideways_and_continued.py`
