# 226 — PDF folder import browser (논문 폴더 연결)

Version: **0.3.225** · Status: **locked**  
Depends: [70](70-mobile-upload.md) · [221](221-upload-reservation-queue.md) · [223](223-library-upload-picker-investigation.md) · [225](225-library-density-followups.md)

## Product claim (locked)

> 자주 쓰는 **논문 폴더를 한 번 연결**하면 파일 앱처럼 PDF 목록을 보고 고르며, **내용이 같은 파일은 초록「이미 보관」**을 표시한다. **기기 전역 전수는 하지 않는다.**

Footer (always when browsing): 목록은 **연결한 폴더(및 하위)** 기준. Downloads·다른 경로·앱 전용 저장소는 빠질 수 있음.

| Avoid | Use |
|-------|-----|
| 전수조사 / 모든 PDF | 논문 폴더 연결 / 선택한 폴더의 PDF |
| 이미 연결 | 이미 보관 |
| analyzed_at 위장 | (later) 보관된 시각 = `created_at` |

## Locked this ship (F1 + minimal hash for green)

| Include | Exclude (later chips) |
|---------|------------------------|
| Full-screen `PdfImportScreen` | MediaStore / READ_MEDIA / MANAGE_EXTERNAL |
| `OPEN_DOCUMENT_TREE` + persistable **tree** URI only | Persistable single-file URI reopen |
| Folder PDF list (cap 500, `truncated`) | Client title / main·SI preview (F3) |
| Multi-select → stream/read → `enqueuePickedPdfs` (221) | Parallel `uploadPdf` |
| Lazy SHA-256 + disk cache → green via `libraryContentHashes` | Claiming 「전수」 |
| Keep 「파일에서 추가」 SAF escape | Path/folder name in evidence |
| uid-scoped grant + `clearAll` release | analyzed_at field |

## INVARIANT

- Green join = full `content_hash` SHA-256 only (223)
- Copy 「이미 보관」 — never 「이미 연결」
- Upload path = reserve + serial `_pumpUploadQueue` only
- No new broad storage permissions in Manifest
- Evidence: `n` / `hash8` / `elapsed_ms` / `truncated` / `ok` — no URI/path/title text
- Soft-hide green P-keep (225) unchanged

## Prefs / disk

```text
asr.pdf_folder_grant.v1.u.$safeUid
  → { v:1, tree_uri, display_label, granted_at_ms }

app_documents/pdf_hash_cache/u_$safeUid/index.json
  → map cacheKey → { content_hash, size, mtime, computed_at_ms }
  cacheKey = sha256(utf8(docUri)+"|"+size+"|"+mtime)
  LRU cap 2000
```

## Flows

1. 보관 → PDF 가져오기 → `PdfImportScreen`
2. Empty → 「논문 폴더 연결」 → system TREE → takePersistable → list PDFs
3. Visible rows → lazy hash (concurrency 2) → green if ∈ library hashes
4. Multi-check → 「대기열에 추가」 → read bytes (≤50MB) → `enqueuePickedPdfs` → pump
5. 「파일에서 추가」 → existing SAF multi (223)
6. Stale grant / SecurityException → banner 「다시 연결」; SAF still works
7. Logout `clearAll` → releasePersistable + wipe grant + hash cache

## Evidence kinds

- `pdf_folder_grant_start` / `pdf_folder_grant_done` (`ok`, `elapsed_ms`)
- `pdf_folder_scan_done` (`n`, `truncated`, `elapsed_ms`)
- `pdf_folder_grant_stale`
- `pdf_hash_cache_hit` / `pdf_hash_cache_miss` / `pdf_hash_cache_fail`
- Keep `picker_sheet_open` (fire on import screen open for continuity)

## Non-goals (this version)

- MediaStore scanner
- Title / SI advisory preview
- `created_at` / analyzed_at UI polish
- Raising queue max above 20

## Version

**0.3.225**
