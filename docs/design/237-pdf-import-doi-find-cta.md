# 237 — PDF import DOI find CTA (SI/메인 찾아보기)

Version: **0.3.234** · Status: **locked**  
Amends [157](157-this-paper-panel.md) · [228](228-pdf-folder-advisory-preview.md)

## Locked

- After advisory head extract, `extractDoiFromText` → cache `advisory_doi` (schema **v=6**).
- CTA on ready rows with DOI: supplementary → 「SI 찾아보기」; main → 「메인 찾아보기」.
- Tap → `https://doi.org/{doi}` external (157). No enqueue gate. Evidence: `has_doi` only, never DOI plaintext.
- Opens browser only — does not claim file lands in folder (238/241).

## Non-goals

Publisher SI deep-links · Crossref-by-title as default.

## Tests

`tests/test_pdf_import_doi_find_237.py` · flutter DOI unit

## Version

**0.3.234**
