# 231 — PDF advisory head extract size limit (too_large)

Version: **0.3.229** · Status: **locked**  
Amends [228](228-pdf-folder-advisory-preview.md) · depends [230](230-pdf-advisory-evidence-densify.md)

## Problem

Live evidence after 0.3.228: most folder rows `pdf_advisory_cache_fail` with `code=too_large`.
PdfBox head extract aborted when SAF copy exceeded **2MB**, so typical journal PDFs (3–10MB) never got title/SI advisory. Small SI files still worked.

PdfBox generally needs a complete PDF (xref often at end); truncating the first 2MB is not a reliable partial parse.

## Locked fix

- Raise advisory `maxReadBytes` default to **50MB** (same as folder/upload read cap).
- Still fail `too_large` above that cap (honest).
- Keep maxPages=2 / maxChars=8k after load.
- No OCR / Gemini / pattern packs in this chip.

## Evidence

Reuse 230 kinds — expect `n_code_too_large` to drop on eungyu/chawan-sized folders; `n_miss` / reason hist to rise.

## Tests

`tests/test_pdf_advisory_head_limit_231.py`

## Version

**0.3.229**
