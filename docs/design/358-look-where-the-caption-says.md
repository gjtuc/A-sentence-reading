# 358 — Look where the caption says

**Version:** 0.3.354 · Status: **locked**  
Amends [321](321-extraction-boundary-census.md) · [357](357-the-caption-list-is-the-paper.md)

## Why

Four caption slots had no picture. Opening the pages named them:

| slot | on the page | why it was empty |
|---|---|---|
| RSC `fig:3` | timeline **4pt above** the caption | refill looked **below** |
| ACS `table:1` | grid **4pt below** the caption | refill looked **above** |
| Science `fig:1` | plot **beside** the caption | above/below does not apply |
| Nano Letters `table:1` | no table in the paper | a footer was typed `table_body`, and that invented `table:1` |

The first two are the caption-list rule, run backwards. The fourth invented a
numbered slot the paper never printed.

## Locked

`refill_empty_slots` uses the same geometry as the caption list:

- a **figure** is taken from **above** its caption
- a **table** is taken from **below** its caption

A body beside the caption is left empty. That is a layout-edit, not another rule.

`build_slot_plan` no longer raises a floor of 1 because a body exists. Slots come
from parsed caption numbers. A leftover body on a paper that already named the
other kind is held: Figure 1..4 and no Table N means no table.

Unlabelled papers (no captions at all) still show leftovers as unnumbered
(design/321). Those slots do not borrow `1`.

## Test

`tests/test_design_358_look_where_the_caption_says.py` — figure from above, table
from below, side-by-side left alone, a footer does not invent Table 1.
