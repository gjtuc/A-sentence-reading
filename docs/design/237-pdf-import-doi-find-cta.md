# 237 — PDF import DOI find CTA (SI/메인 찾아보기)

Version: **0.3.235** · Status: **locked**  
Amends [157](157-this-paper-panel.md) · [228](228-pdf-folder-advisory-preview.md) · polish [243](243-pdf-import-remaining-polish.md)

## Locked

- After advisory head extract, `extractDoiFromText` → cache `advisory_doi` (schema **v=7** with optional `pairing_key`).
- CTA on ready **single** rows with DOI: **missing mate** label — supplementary → 「메인 찾아보기」; main → 「SI 찾아보기」.
- Tap → `https://doi.org/{doi}` external (157). No enqueue gate. Evidence: `has_doi` only, never DOI plaintext.
- Opens browser only — does not claim file lands in folder (238/241).
- **Hide 찾아보기** when mate already in folder: set row (`PdfImportSetItem` → `onFindMain`/`onFindSi` = null), or single with opposite-role ready entry sharing the same pairing key (`matePresent`).

## Non-goals

Publisher SI deep-links · Crossref-by-title as default.

## Tests

`tests/test_pdf_import_doi_find_237.py` · flutter DOI unit

## Version

**0.3.235**

## Amend (design/251)

「찾아보기」는 장기적으로 **기기 mate-fetch 오케스트레이션**(OA → 공식 API → 안전 패턴 → 기존 doi.org 브라우저)으로 확장한다.  
바이트는 Cloud Run이 출판사 PDF를 대신 받지 않는다. 상세·phase·non-goals: [251](251-mate-direct-fetch.md).

