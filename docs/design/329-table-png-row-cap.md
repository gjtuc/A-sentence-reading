# 329 — A table picture does not end mid-table

**Version:** 0.3.323 · Status: **locked**  
Amends [327](327-docx-table-grid-not-prose.md) · [323](323-extract-audit-harness.md) · [321](321-extraction-boundary-census.md)

## Why

`_table_as_png_data_url` sliced the cell text at a hardcoded **45 rows**:

```python
lines = (plain or "").splitlines()[:45]
```

design/323 recorded "a table clipped mid-row cannot be reconstructed or verified"
as a hole with no measurement. Tracing a real supplementary file gave the number:

| file | table rows | over 45 |
|---|---|---|
| `1-s2.0-S0272884226009739-mmc1` | 49, 37, 48, 10 | **49, 48** |

Two of its four tables lost **4 rows and 3 rows**. The picture simply stopped,
with nothing in the caption or the evidence to say so. A reader comparing the app
against the paper would find rows missing and no reason given.

## Locked

1. `TABLE_PNG_MAX_ROWS = 200`. Real papers fit; the image grows with the table.
2. Past the cap the picture appends `... N more rows not shown`, computed from
   the real overflow. It never ends mid-table in silence.
3. `figure_source_census` reports `table_max_rows` and `table_over_png_cap_n`,
   both carried on `figure_extract_done` (design/321).

## Measured after

Same file: `table_max_rows 49`, `table_over_png_cap_n 0`. Both previously
truncated tables now render whole.

## Not this chip

- Rendering a Word table as structure rather than a monospaced picture
- The 120-character line clip inside a row
- Azure table cell structure on the PDF path (still bbox only, design/321)

## Test

`tests/test_design_327_docx_table_grid.py` — `test_row_cap_fits_a_real_paper_table`,
`test_overflowing_table_says_how_many_rows_are_missing`,
`test_census_reports_table_rows_and_overflow`
