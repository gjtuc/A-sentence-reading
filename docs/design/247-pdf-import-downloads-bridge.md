# 247 — Downloads bridge (SAF INITIAL_URI + resume pick)

Version: **0.3.238** · Status: **locked**  
Amends [238](238-pdf-import-open-document-pick.md) · [242](242-pdf-import-find-watch.md) · [226](226-pdf-folder-import-browser.md) · [237](237-pdf-import-doi-find-cta.md)

## Problem

- 「받은 PDF 고르기」/「논문 폴더 연결」`EXTRA_INITIAL_URI` used `MediaStore.Downloads` on API 29+ — system picker **ignores** it, so Downloads did not open.
- Find-watch only observes the **connected tree**. Browser downloads land in system Download → user saw no recognition.

## Locked

- Kotlin `downloadsDocumentUri` / `downloadsTreeUri` via `DocumentsContract` `primary:Download` (never MediaStore for INITIAL_URI).
- `pickDocuments` → document URI hint; `pickTree` → tree URI hint (user may still pick another folder).
- Still **no** MES / MediaStore scan / auto Downloads tree grant (226 / 238).
- After 「찾아보기」 arm: on import screen **resume**, if watch still armed and no tree hit → one dialog → open **downloads in-app browse** ([248](248-pdf-import-downloads-inapp-browser.md); once per arm).
- Polish: [248](248-pdf-import-downloads-inapp-browser.md) replaces DocumentsUI pick with in-app Downloads list.
- CTA labels (237 amend): have SI → 「메인 찾아보기」; have main → 「SI 찾아보기」.

## Non-goals

Auto-ingest without SAF pick · docx SI · MES.

## Tests

`tests/test_pdf_import_downloads_247.py`

## Version

**0.3.238**

## Amend (design/252)

Resume offer path emits `pdf_find_watch_resume_offer` with `outcome`/`skip_reason` (proves silent return). See [252](252-find-return-causal-evidence.md).
