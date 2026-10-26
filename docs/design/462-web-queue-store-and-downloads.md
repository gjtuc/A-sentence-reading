# 462 — Web queue store and Downloads files

## Report

On the web, dropping a PDF showed 「파일을 저장하지 못했습니다.」, and 논문 가져오기 found no files at all.

## Causes

1. `PrefsUploadReserveStore` saved the queue's copy of each file under the app documents folder with `dart:io`. The browser has neither, so `saveLocalPdf` returned null, and every web enqueue (drop, 「파일에서 추가」, import) failed.
2. Web Downloads mode (design/416) connected the Downloads folder itself with `showDirectoryPicker`. Chrome's File System Access blocklist refuses the Downloads, Desktop and Documents folders themselves (their subfolders are fine). The refusal arrives as the same `AbortError` as a cancel, so the screen stayed empty with no message.

## Changes

- `api/web_blob_store.dart` (stub or web): IndexedDB `asr_blobs` / `files` keeps the bytes. On the web `PrefsUploadReserveStore` saves, reads and deletes with keys `web/ingest_reserve/<hash>.<pdf|docx>`, so the `ingest_reserve` path check still holds. The queue list itself stays in SharedPreferences.
- Web Downloads: `SafTreeChannel.pickWebDocs(downloads: true)` opens `showOpenFilePicker` (multiple, PDF/DOCX, `startIn: 'downloads'`). Chrome lets you pick files inside Downloads. Picked files go through `droppableDoc` / `isOldWordDoc` and `enqueuePickedPdfs`. The screen shows 「대기열에 N건 넣었습니다.」 plus any skipped or `.doc` note. Evidence: `pdf_import_pick_done` with `browse: web_downloads_docs`.
- Folder picks that fail on the web show `kWebBlockedFolderNote` (pick a folder inside Downloads etc.). The empty connect screens say the same on the web.
- `kOldWordNote` is shared by drop and the Downloads dialog.

## Not changed

- Phone paths (`dart:io` store, SAF tree, OPEN_DOCUMENT).
- Draft store: a null save is already tolerated on the web.
