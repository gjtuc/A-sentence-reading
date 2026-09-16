# 302 — Azure box gate

Version: **0.3.293** · Status: **locked**

## Why

design/301 sees PyMuPDF marker order. This paper's sentence tags come from Azure boxes, and those boxes do not match the visual guess.

- The ABSTRACT polygon crosses the page center even though the banner is a sidebar.
- Roles arrive as `ParagraphRole.PAGE_HEADER`, so an unstripped check leaves headers and footers in the body.
- A later left header owns the right column from the top. An earlier header on that page must not take it.
- A synthetic box that does not cross center will pass while this PDF fails.

## Before editing reading order

1. `python scripts/azure_box_gate.py --fixtures-only` — exit 0.
2. `python scripts/azure_box_gate.py --pdf <path> --out <inventory.json>`.
3. Console is booleans and counts only. The inventory has coordinates, not paper text.
4. `azure_unavailable` means stop and ask for credentials. Do not substitute PyMuPDF.
5. Do not change `section_flow` until `live_ok True`. `results_under40` above 0 is table-cell leak, not a section swap.

## Non-goals

- Deploy
- Printing sentences

## Acceptance

`tests/test_azure_box_gate.py`
