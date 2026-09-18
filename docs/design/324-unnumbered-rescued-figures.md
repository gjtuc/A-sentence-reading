# 324 — A rescued figure does not borrow a number

**Version:** 0.3.318 · Status: **locked**  
Amends [321](321-extraction-boundary-census.md) · [124](124-missing-figures.md) · [151](151-layout-map-slot-carousel.md)

## Why

[321](321-extraction-boundary-census.md) B7 added `append_unclaimed_body_slots`
so an Azure body whose caption number never parsed still reaches the carousel.
On a paper with unparseable captions that rescued **10 real figures**
(`36c7a33ec665`: 5 slots for 15 bodies).

Cross-checking a hand-built ground truth against the real pipeline on
`science.1212858` showed the cost. That file is a Science issue excerpt: it
carries the tail of one article, the target article, the head of a third, and a
journal landing page. Azure finds 5 figure bodies; the paper prints 3 figures.
The two rescued bodies took the next integers and `_render_slot_png` fell
through to the generic caption, so the carousel read:

| slot | shown before | truth |
|---|---|---|
| fig:4 | `Figure 4` | not a figure in this paper |
| fig:5 | `Figure 5` | landing-page graphic |

Dropping the body was dishonest. Numbering it is also dishonest — it asserts a
label the paper never printed, which is the same class as design/124's
「성공 위장 금지」.

## Locked

1. `Slot.unnumbered: bool = False`. `append_unclaimed_body_slots` sets it.
   A slot filled from a parsed caption number never sets it.
2. Serialised both ways, so a reopened `slot_plan.json` still tells the truth.
3. When such a slot has no caption text, `_render_slot_png` uses
   `slot_unnumbered_caption(kind)` — `번호 없는 그림` / `번호 없는 표`.
   The string carries **no digit**.
4. `Slot.n` on a rescued slot is a carousel position only. Ordering is
   unchanged (figures then tables, design/92).

## Not this chip

- Suppressing rescued slots entirely — the 15-body paper proves they are often
  real content
- Deciding which rescued bodies are journal chrome vs paper figures
- The `fc-*` caption-rect bug, Azure table cell structure, module globals
  (still design/321 「Not this chip」)

## Test

`tests/test_design_321_extraction_census.py` —
`test_appended_slots_are_marked_unnumbered`,
`test_unnumbered_caption_does_not_assert_a_figure_number`,
`test_caption_numbered_slots_are_not_marked_unnumbered`
