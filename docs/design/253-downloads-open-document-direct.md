# 253 — Resume 「다운로드 보기」→ Downloads 바로 열기

Version: **0.3.246** · Status: **locked**  
Amends [247](247-pdf-import-downloads-bridge.md) · [248](248-pdf-import-downloads-inapp-browser.md) · [252](252-find-return-causal-evidence.md)

## Problem

`openDownloadsBrowse` with no Downloads tree grant opened `ACTION_OPEN_DOCUMENT_TREE`. Samsung DocumentsUI ignored tree `EXTRA_INITIAL_URI` and landed on the last papers folder (「차헌 논문」), so 「다운로드 보기」felt broken.

## Locked

1. **Downloads grant present:** in-app 「다운로드」tab + `listPdfs` (248).
2. **Grant missing** on resume 「다운로드 보기」/「다운로드에서 가져오기」: **do not** open tree picker. Use `ACTION_OPEN_DOCUMENT` (multi) with DocumentsContract **document** URI `primary:Download`, MIME PDF + Word OOXML docx → pick → copy into papers tree or enqueue.
3. **Explicit** 「다운로드 변경」/ empty-state folder connect still uses `OPEN_DOCUMENT_TREE`; `EXTRA_INITIAL_URI` = **document** URI `primary:Download` (not tree URI).
4. Switch `pdfImportBrowseMode` to downloads before pick so cancel stays on Downloads tab.
5. Evidence: `pdf_import_pick_*` with `browse=downloads_docs` on the OPEN_DOCUMENT path (no DOI/path plaintext).

## Non-goals

MES · MediaStore auto-scan · auto-grant without user confirm.

## Tests

`tests/test_downloads_open_direct_253.py`

## Version

**0.3.246**
