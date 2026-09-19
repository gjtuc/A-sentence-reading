# 338 — A panel belongs to its caption, and a logo is not a figure

**Version:** 0.3.333 · Status: **locked**  
Repairs what [337](337-per-job-geometry-and-figure-pairing.md) measured · amends [321](321-extraction-boundary-census.md) · [324](324-unnumbered-rescued-figures.md)

## Why

design/337 counted the slot pairing and found that across ten papers **51 of 157
carousel slots were images with no caption** while **13 captions had no image**. An
11-figure, 2-table paper produced 24 slots, with the same figure appearing twice.

## A. The horizontal test was centre distance, not overlap

`_nearest_caption_for_body` required the caption's horizontal centre within 48pt of
the body's. Azure splits a multi-panel figure into several `figure_body` boxes, so a
left-hand panel under a full-width caption has a distant centre while sitting almost
entirely inside the caption's span.

Measured over 130 figure bodies in ten papers:

| | bodies the centre rule rejected | bodies it accepted |
|---|---|---|
| centre offset | median **92.6**pt (max 318) | median 0.7pt |
| share of body inside the caption | median **0.76** | median 1.00, min 0.68 |
| vertical gap | median 11.1pt | median 6.3pt |

The rejected bodies are not far away, they are off-centre. The ones that genuinely
belong to another column overlap by **0.00**, so overlap separates the two cases and
centre distance does not.

**Locked:** `CAPTION_X_OVERLAP_MIN = 0.5`, applied as the share of the *body* inside
the caption's x-range. No currently-accepted body falls below 0.68, so nothing that
paired before stops pairing.

## B. Pairing correctly was still not enough

Two gaps had to close with it, or the repair would have been invisible:

- `assign_body_to_slot` called `assign_body_boxes_to_slot`, which **replaced** the
  list. Panels arrive one at a time, so only the last survived even when pairing
  worked. Automatic pairing now appends; the figure editor still replaces, because a
  user setting the list by hand means exactly that list.
- `_render_slot_png` read `body_box_id` alone, so a slot holding three panels drew
  one. `_slot_body_rect` unions the panels on the chosen page. Panels of one figure
  are adjacent, so their bounding box is the figure region — verified on real
  output, where the union spans 0.97 to 1.10 of the panels' summed height.

On `ChemistryOpen`, `fig:3` rendered 343KB before and 817KB after: **half that
figure was missing**, not padded.

## C. A running page graphic is not a figure

Relaxing the horizontal test exposed a defect it had been masking. On `ChemistryOpen`
the masthead sits 20pt above Figure 1, so it began joining real figure slots:

```
x  47..135, y 21..45   → pages 0, 1, 2, 3   (identical rect)
x 425..547, y  3..46   → pages 0, 1, 2, 3   (identical rect)
```

Figures 1, 3 and 4 rendered with a logo glued above them, and `fig:4` took both.
The union waste ratio did not catch it — logo at y3–45, figure from y63, so the span
barely exceeded the sum.

A real figure never repeats at the same rect on another page, so page span is the
evidence. `demote_repeating_bodies` re-types such boxes to `figure_chrome` /
`table_chrome` before anything can claim them, and `chrome_body_n` reports the count.

Two details earned their own tests. Grouping by **rounded bucket** split copies that
straddle a bucket edge — that is why the first measurement found 7 of 8 ChemistryOpen
logos and none of Adv. Mater.'s; tolerance clustering at 4pt finds 8 and 2.

Measured: eight of the ten papers have **no** repeating bodies, so this fires only
where it is needed.

## Measured — ten papers

| | before | after |
|---|---|---|
| carousel slots | 157 | **139** |
| caption with no image | 13 | **5** |
| paired | 92 | **100** |
| image with no caption | 51 | **33** |
| slots holding several panels | 0 | 3 |

Two papers land exactly on their contents: `catalysts-13-01171` has 11 figures and 2
tables and now pairs 13; `ChemistryOpen` has 5 figures and 1 table, demotes 8 logo
copies, and pairs 6 with zero orphans.

## What the remaining 33 are, and why they are not this chip

They are bodies on pages where Azure reported **no `figure_caption` at all** — 29 of
the 33 in the measurement. `d4cs00527a` alone holds 13. These are graphical
abstracts, scheme images, and captions Azure typed as `paragraph`. Deciding whether
each is a figure needs a different signal from geometry, and guessing here would
undo the gain above.

## Not this chip

- Bodies on pages with no caption of any kind (33 remaining)
- Captions Azure types as `paragraph` rather than `figure_caption`
- Panels whose caption sits on the previous or next page

## Test

`tests/test_design_338_panel_pairing.py` — the overlap fraction and its threshold
against the measured floor, a side panel that now pairs and an other-column panel
that still does not, a barely-overlapping sliver refused, panels accumulating
without duplicating while the editor still replaces, the union rect and its
single-panel and cross-page exclusions, and running graphics demoted including the
tolerance case that bucket rounding missed.
