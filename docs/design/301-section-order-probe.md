# 301 — Section order probe

Version: **0.3.293** · Status: **locked**

## Why

Picker-section checks rewrote a throwaway script and stalled.

- Windows cp949 raised `UnicodeEncodeError` on `©` before marker order printed.
- The phone dump stores the reader sentence in `content-desc`, not `text`.
- Page 0 of an Elsevier PDF is multicolumn, so live replaces that text with vision OCR. PyMuPDF order alone cannot explain tagged sentences.

## Rules

1. Run `python scripts/section_order_probe.py --pdf <path> [--ui <dump.xml>]`. Do not write `_w.py`.
2. The script prints ASCII only. Do not print raw page text to the console.
3. Read phone UI through `content-desc` and `text`. The probe does this.
4. If `vision_repair_expected` is true, do not treat the PyMuPDF marker order as the live sentence tags. Azure order is design/302.

## Non-goals

- Fixing Elsevier front-page reading order
- Calling Gemini / vision OCR
- Version bump

## Acceptance

`tests/test_section_order_probe.py`
