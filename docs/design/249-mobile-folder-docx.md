# 249 — Mobile folder docx list + upload

Version: **0.3.240** · Status: **locked**  
Amends [70](70-mobile-upload.md) · [226](226-pdf-folder-import-browser.md) · [228](228-pdf-folder-advisory-preview.md) · [248](248-pdf-import-downloads-inapp-browser.md)

## Locked

- Folder browse (papers + downloads): list `.pdf` and `.docx` (name or mime).
- Enqueue / chunked ingest: `.docx` with ZIP `PK` magic; `.pdf` with `%PDF` magic ([`AsrClient`](../../mobile/lib/api/client.dart)).
- Copy into papers tree: mime by extension (Word OOXML vs PDF).
- Advisory for docx: **no PdfBox**. Title = filename stem; role via filename SI heuristics (`si` / `mmc` / `suppl` / supporting) else `main`. DOI miss OK.
- Import screen title: **논문 가져오기**. Row chip `DOCX` when `.docx`.
- design/70: folder-path docx upload allowed (file_picker single-PDF path may stay PDF-only).

## Non-goals

Legacy `.doc` · on-device docx text extract · MES · client docx→PDF.

## Tests

`tests/test_mobile_folder_docx_249.py`

## Version

**0.3.240**
