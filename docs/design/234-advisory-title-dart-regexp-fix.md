# 234 — Advisory title Dart RegExp `(?i)` crash fix

Version: **0.3.231** · Status: **locked**  
Amends [233](233-pdf-advisory-title-chrome-skip.md)

## Problem

0.3.230 `_journalChrome` used inline `(?i)`. Dart `RegExp` throws `FormatException: Invalid group` on first match → advisory pump `code=exc` for every PDF → UI lost titles and 추정 메인/SI chips.

## Locked

- Use `caseSensitive: false` (no inline `(?i)`).
- Keep 233 chrome skip semantics.
- Evidence: `pdf_advisory_cache_fail` may include `exc_type` snake token.

## Tests

`mobile/test/advisory_title_smoke_test.dart` · `tests/test_pdf_import_ux_232_233.py`

## Version

**0.3.231**
