# 357 — The caption list is the paper

**Version:** 0.3.353 · Status: **locked**  
Extends [321](321-extraction-boundary-census.md) · [324](324-unnumbered-is-not-a-figure-number.md) · [356](356-same-size-is-furniture.md)

## Why

design/356 asked each leftover image what it *looked like*, and six author headshots
fell to a same-size rule. The other seven needed a new rule each: cover art, a banner,
a badge, a logo, a possible scheme. That is the wrong starting point.

The paper already named its figures. A caption is text, and the letters and the
coordinates are now known (design/346 · 352). Captions come in two kinds and they
carry their own numbers. Lined up they are the carousel:

    Figure 1   Figure 2   Table 1   Table 2

A figure's image sits above its caption. A table's grid sits below. Pairing already
walks that geometry (`_strip_candidates` in `caption_pairing.py`) and on ten papers
it fills **102 of 106** caption slots.

The remaining work is not another filter on leftover images. It is to **stop putting
those leftovers in the carousel** once the caption numbers themselves are complete.

## Locked

`caption_numbers_are_complete` is true when the parsed, captioned numbers of one kind
run `1..N` with no gaps. `append_unclaimed_body_slots` then holds leftover bodies of
that kind instead of inventing `번호 없는 그림` slots.

The list checks itself. Nothing external is compared against.

- Azure's count of caption *boxes* cannot serve: a multi-line caption arrives as
  several boxes, so the RSC review detects 54 boxes for 27 figures.
- A floor slot invented because a body exists (`fig:1` with no caption) is not a
  list the paper printed. That is design/321's rescue path, and treating it as
  complete would hide every unlabelled figure.
- Figures and tables are their own lists. A complete figure run does not hold a
  leftover table.

Reported as `held_by_caption_list_n`. On a paper that shows 7 figures while holding
10 bodies, those two numbers say so.

## Measured

| paper | captioned | filled | unnumbered before | held | unnumbered after |
|---|---|---|---|---|---|
| `d4cs00527a` | fig 1..27, table 1 | 27 | 7 | **7** | **0** |
| `cs5b00357` | fig 1..14, table 1 | 14 | 4 | **4** | **0** |
| `science.1212858` | fig 1..3 | 2 | 2 | **2** | **0** |
| `nl5b02080` | fig 1..4, table 1 | 4 | 2 | **2** | **0** |
| `srep41797` | fig + table complete | 10 | 0 | 0 | 0 |

`filled_n` is unchanged on every paper. The images that left the carousel are the
ones no caption claimed.

## Not this chip

- The three caption slots that still have no body (`caption_without_body_n`). Those
  are pairing misses, not leftovers, and they stay in the carousel as empty frames.
- Front-page furniture *above the title* is now held for the same reason as the
  rest, so design/356's leftover-7 list does not need its own rule.
- Chunking at box boundaries, using coordinates beside the reading sentence.

## Test

`tests/test_design_357_caption_list_is_the_paper.py` — 1..N is complete, empty and
floor and gapped and start-at-2 are not, figures and tables are separate lists,
leftovers are held when the list is complete, unlabelled and gapped papers still
rescue, and a complete figure list does not hold a table.
