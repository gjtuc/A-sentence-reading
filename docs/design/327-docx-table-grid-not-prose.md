# 327 — A Word table grid is not prose

**Version:** 0.3.322 · Status: **locked**  
Amends [249](249-mobile-folder-docx.md) · [295](295-docx-vml-caption-split.md) · [321](321-extraction-boundary-census.md)

## Why

`docx/extract.py::extract_text` appended `_table_plain(block)` for **every**
table, so a cell grid entered the sentence stream as one pipe-separated blob. The
same captioned table is separately rendered into its own carousel slot by
`_table_as_png_data_url`, so the reader met it twice: once as a picture, once as
a `sentence` no one can read aloud.

Practice mode exists to read a paper **aloud** (design/326). A grid of numbers
has no spoken form, and it also inflates the sentence count and the coverage
denominator, which hides real loss.

## Locked

1. `table_is_grid(table)` — two or more rows **and** two or more columns.
2. `extract_text` skips a grid. Its content belongs to the slot PNG only.
3. A one-column or one-row table is often a text box holding a paragraph, so it
   still counts as prose and is kept.
4. The skip is **counted**, not silent: `figure_source_census` returns
   `table_grid_n`, carried on `figure_extract_done` (design/321).

## Known limit

A grid with **no** caption never becomes a figure slot either, so its numbers now
reach neither the sentences nor the carousel. `table_grid_n` is what makes that
visible; pairing an uncaptioned grid to a slot is a separate chip.

## Test

`tests/test_design_327_docx_table_grid.py`
