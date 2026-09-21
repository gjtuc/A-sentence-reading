# 359 — The caption's x-range is the column

**Version:** 0.3.355 · Status: **locked**
Amends [338](338-panel-pairing-and-page-graphics.md) · [357](357-the-caption-list-is-the-paper.md) · [358](358-look-where-the-caption-says.md)

## Why

Three slots were empty with the picture sitting right next to the caption, on the
same page. Opening the pages showed two faults, and the first one had been asking
the wrong question since design/338.

### A short caption cannot cover a wide table

`_x_overlap_frac` divided the overlap by the **body's** width, so the test read
"how much of this table sits under the caption line". A one-line caption is
narrower than the table it names, so the share can never reach the 0.5 floor.

| paper · page | caption | body | share (design/338) |
|---|---|---|---|
| `d3cy01612a` p12 `Table 8` | 167.4pt, one line | 513.5pt | **0.33** — refused |
| `s0167-2991…` p3 `Table 3` | 166.4pt, one line | 382.4pt | **0.44** — refused |
| `s0167-2991…` p3 `Table 2` | 225.2pt, two lines | same 382.4pt body | 0.59 — accepted |

So the rule was scoring **caption length**. `s0167`'s Table 3 sits **1.2pt** above
its table and lost it to Table 2 from **112.6pt** away, because Table 2's caption
wrapped to a second line and therefore covered more of it. `d3cy`'s Table 8 caption
and table sit 2.5pt apart on page 12 and **both went unused**; the slot then took a
page-11 paragraph that merely mentions "Table 8" as its caption and searched page 11,
where the only table already belonged to Table 7. Table 9 lost its caption the same
way.

### One Azure box, two column figures

Engineering (Beijing) `1-s2.0-S2095809922003708-main` page 8 prints Fig. 6 and Fig. 7
as a left and a right column graphic. Azure returns **one** box for both:

```
┌───────────────────────────────────────────────┐
│   figure_body  fb-0819   x 40.6..554.4        │
│        Fig. 6        │        Fig. 7          │
└───────────────────────────────────────────────┘
[Fig. 6 caption 36.3..288.9]  [Fig. 7 caption 305.4..557.7]
```

Fig. 6 claimed the whole box, so the carousel showed one picture twice the paper's
width and Fig. 7 rendered `(missing)`.

## Locked

### Overlap is measured against the narrower box

`_x_overlap_frac` divides by `min(body_width, caption_width)`. The floor stays 0.5.

- a caption inside its own body scores 1.0 regardless of how short the line is
- a body in the other column still scores 0.00 and is still refused
- design/338's narrow panel under a full-width caption still scores ~1.0

### `split_shared_column_bodies`

Runs after `refill_empty_slots`, before design/321's leftovers.

Where two or more captions **of the same kind** sit on one page with overlapping
y-bands and **disjoint x-ranges**, and one body box covers the whole row's x-span
and is vertically adjacent (figure above, table below), the body is cut at the
midpoint of each gap between consecutive captions and each slot is given its part.

The spent box is re-typed `figure_split` / `table_split`, so it is neither counted
as an unused body nor appended as an unnumbered carousel entry.

`column_split_n` reports how many parts were handed out.

## What is not locked

**A caption's width alone is not a column boundary.** `d3cy`'s Table 8 caption is
167pt because its text ends, not because the column is 167pt wide — that column is
248pt. Cutting on caption width alone would halve a correct full-width table. Only a
**second caption of the same kind beside it** is evidence that the page has two
columns at that height, and only then is there anything to split.

A single caption with a body beside it (Science `fig:1`) is still a layout-edit,
per design/358.

## Measured

| | before | after |
|---|---|---|
| `1-s2.0-S2095809922003708-main (1)` | 12/14 filled, `fig:7` empty | **14/14**, split 2 |
| `s0167-2991%2803%2980223-9` | 4/5 filled, `table:3` empty | **5/5** |
| `d3cy01612a (2)` | 23/24 filled, `table:8` empty | **24/24** |

## Test

`tests/test_design_359_one_box_two_captions.py` — a one-line caption keeps its
full-width table, the nearer caption wins over the longer line, the other column is
still refused, two column captions each get their half, the spent box is neither
unused nor a carousel entry, a single caption does not cut a full-width body, two
captions that already have bodies are untouched, and two captions stacked in one
column are not a row.
