# 360 — Stop guessing what a picture is

**Version:** 0.3.356 · Status: **locked**
Retires the shape detectors in [338](338-panel-pairing-and-page-graphics.md) · [356](356-same-size-is-furniture.md)
Completes the neighbour stage promised by [358](358-look-where-the-caption-says.md) · [359](359-the-caption-is-the-column.md)

## Why

64 caption slots still had no picture. Classifying all 64 off the cached layouts:

| cause | slots |
|---|---|
| the body was demoted as journal furniture | **39** |
| an unclaimed body sits **beside** the caption | 15 |
| an unclaimed body sits on the **other side**, or further away | 7 |
| other | 3 |

### The furniture detectors were deleting the paper's figures

Two detectors guessed what a picture *is* from how it looks:

- design/338 — a body repeating within 4pt on two pages is a running page graphic
- design/356 — three same-size unclaimed bodies over two pages are author headshots

Journals place figures at the same spot on page after page, so design/338's rule
catches real figures. `1-s2.0-S0926337304006745` prints Fig. 1 on page 3 at
`x 326.6–523.9, y 68.5–225.5` and Fig. 3 on page 5 at `x 327.8–523.7, y 67.8–225.4`.
One point apart. Both were demoted, both slots went empty.

Measured over 88 papers: **137 boxes demoted, 67 of them with a numbered caption
4–10pt away** — the distance of a caption printed under its own figure. A journal
logo does not have "Figure 5" printed beneath it.

This also corrects design/359's classification. What was reported as
"Azure found no figure box on that page" for 31 slots was, for 30 of them, a box
Azure *did* find and we threw away.

### The neighbour stage was never built

design/358 fixed the direction of the first search (figure above, table below) and
stopped there. The second stage — for a slot still empty, take the nearest
unclaimed body of the same kind in **any** direction — was described but not
implemented, which is why the 15 "beside" slots and `srep41797`'s four tables
(the grid sits ~7pt **above** its caption on pages 4–7) stayed empty.

## Locked

### No rule may describe what a figure looks like

`demote_repeating_bodies` and `demote_same_size_unclaimed` are deleted, with
`chrome_body_n` and `same_size_chrome_n`. Nothing replaces them.

The paper's caption list already does this job honestly. design/357's
`caption_numbers_are_complete` holds every unclaimed body back when the numbers run
1..N with no gaps, so logos, mastheads, badges, cover art and author headshots still
never reach the carousel — not because they look like furniture, but because the
paper never captioned them. `held_by_caption_list_n` counts them.

### `fill_from_page_neighbours`

Runs last, after design/358's above/below and design/359's column split have both
failed, and before design/321's leftovers.

For each slot with a caption and no body, candidates are unclaimed boxes **of the
kind the caption names** (a lost figure searches figures, a lost table searches
tables — Azure tells them apart, so the two can never be swapped), on the caption's
own page, within 220pt by rectangle distance, and in line with the caption on one
axis: at least 0.5 x-overlap (above or below) or 0.25 y-overlap (beside).

Assignment is globally nearest-first, so a body between two empty captions goes to
the caption it is nearer to rather than to whichever slot is numbered lower.

## What is not locked

A slot with no unclaimed body of its kind on its caption's page stays empty and the
reader is sent to the layout editor. Pulling coordinates from the PDF's embedded
image objects is still unbuilt — but design/360 removes most of the need, since the
"Azure found nothing" group was mostly our own deletion.

## Measured

88 papers, re-audited off the cached layouts:

| | design/359 | design/360 |
|---|---|---|
| **captions with no picture** | **64** | **3** |
| slots paired | 681 | 745 |
| slots with neither caption nor body | 59 | 56 |
| slot count | 993 | 1065 |
| unnumbered carousel entries | 188 | 260 |
| unclaimed bodies held by the caption list | 253 | 275 |

35 papers changed. The three captions still without a picture are
`s10853-010-5036-9` fig:6, `div-class-title-microscopic…` fig:1 and `acsaem.9b01599`
fig:4 — no unclaimed body of their kind exists anywhere on the caption's page.

The two rises are the same fact from two sides. On a paper whose caption numbers are
complete the former furniture is now **held** instead of deleted, which is why
`held_by_caption_list_n` grew by 22 — `d4cs00527a`'s six headshots go from demoted to
held and still show nothing, and ChemistryOpen's masthead the same. The 72 extra
unnumbered entries are all on papers whose caption list is empty or gapped, where
design/321 has always shown leftovers; 66 of them are in one 87-page supplementary
PDF whose 119 unclaimed bodies form 93 distinct rectangles from 40×27 to 486×691
points. That is not a repeating footer. The old detector had grouped seven different
full-page graphics on seven pages as one logo.

Sentence coverage and order are untouched: minimum text coverage 0.4603 and maximum
backward step 0 in both runs.

## Test

`tests/test_design_360_no_shape_rules.py`
