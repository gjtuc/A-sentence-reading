# 248 — Downloads in-app browser (reuse PDF import list)

Version: **0.3.239** · Status: **locked**  
Amends [226](226-pdf-folder-import-browser.md) · [238](238-pdf-import-open-document-pick.md) · [241](241-saf-tree-write-copy.md) · [242](242-pdf-import-find-watch.md) · [247](247-pdf-import-downloads-bridge.md)

## Problem

「받은 PDF 고르기」opened system DocumentsUI — not the in-app PDF list (advisory / set rows / green 이미 보관). Downloads could not reuse the paper-folder browser.

## Locked

- Import screen modes: **논문 폴더** | **다운로드**.
- Downloads uses a **separate** persistable tree grant: prefs `asr.pdf_downloads_grant.v1.u.$uid` (same JSON shape as paper grant). Not an auto-grant; user confirms `OPEN_DOCUMENT_TREE` (247 Downloads DocumentsContract hint).
- Same `listPdfs` → hash / advisory / `buildPdfImportListItems` UI as papers.
- 「받은 PDF 고르기」/ find-resume dialog → switch to downloads mode (+ connect if needed). **No** `pickDocuments` on these CTAs.
- Selection in downloads mode: if papers tree writable → `copyUriIntoTree` into papers grant → switch to papers + rescan; else enqueue bytes (238 fallback).
- Find-watch still observes **papers** tree only (242).
- PDF + **docx** list/upload: [249](249-mobile-folder-docx.md) (was PDF-only at 248 ship).

## Non-goals

MES · MediaStore scan · replacing papers grant with Downloads. (docx: 249)

## Tests

`tests/test_pdf_import_downloads_248.py`

## Version

**0.3.239**

## Amend (design/251)

Downloads 상시 탭·중복 CTA는 mate-fetch(T1+)가 늘면 **축소/제거 가능**. Fallback은 T4·「방금 파일 고르기」. See [251](251-mate-direct-fetch.md).

## Amend (design/253)

No-grant path on Downloads CTAs: `OPEN_DOCUMENT` pick (PDF+DOCX) instead of forcing tree connect. In-app list only after grant exists. See [253](253-downloads-open-document-direct.md).
