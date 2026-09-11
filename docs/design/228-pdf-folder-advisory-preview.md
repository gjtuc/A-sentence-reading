# 228 — PDF folder advisory title + main/SI preview (F3)

Version: **0.3.226** · Status: **locked**  
Depends: [226](226-pdf-folder-import-browser.md) · [222](222-doc-role-detect-disk-honesty.md) · [227](227-pdf-import-recent-label.md)  
Amends: 222/223/226 non-goal “client title / main·SI preview” — **shipped here as advisory only**

## Product claim

Folder rows show **estimated title** (primary) + filename (secondary) + `추정 메인`/`추정 SI` chip + always-visible watermark **「추정 · 업로드 후 확정」**.  
Server `detect_doc_role` remains SoT after ingest. Client never gates enqueue.

## Locked this ship

| Include | Exclude |
|---------|---------|
| PdfBox-Android head extract (≤2 pages, 8k chars, **50MB** · [231](231-pdf-advisory-head-read-limit.md)) | OCR / MediaStore / Gemini title_guess |
| Dart port of `detect_doc_role_detailed` | Enqueue gate on advisory role |
| Advisory disk cache (same key as hash cache) | Replacing upload wire `displayName` with title |
| First-40 advisory pump, concurrency 2 | Viewport scroll pump (later) |
| Watermark whenever advisory title or role shown | Path/title in evidence |

## INVARIANT

- Wire filename = SAF `displayName`
- Green = full SHA-256 only
- empty_head → advisory role **main** (never filename-only SI)
- Evidence: `n`/`elapsed_ms`/`role`/`reason`/`code` — no title/path/URI
- Logout wipes advisory cache with grant/hash

## Evidence kinds

- `pdf_advisory_pump_start` / `pdf_advisory_pump_done`
- `pdf_advisory_cache_hit` / `pdf_advisory_cache_miss` / `pdf_advisory_cache_fail`
- `pdf_advisory_cancelled`

## Version

**0.3.226**
