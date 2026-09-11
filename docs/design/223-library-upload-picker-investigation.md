# 223 — Library upload picker (recent + green + SAF sheet)

Version: **0.3.222** · Status: **locked**  
Depends: [70](70-mobile-upload.md) · [221](221-upload-reservation-queue.md) · [222](222-doc-role-detect-disk-honesty.md)

## Locked MVP (this ship)

| Include | Exclude (later chips) |
|---------|------------------------|
| Custom sheet: 최근 + 대기열 + 「파일에서 추가」 | MediaStore / 전수 스캔 |
| uid-scoped recent: hash, display_name, label, uploaded_at | Persistable URI re-open |
| Green border = `content_hash` ∈ library (list ∪ disk), fail-closed | Client title / main·SI preview |
| Still enqueue via `enqueuePickedPdfs` only | Parallel `uploadPdf` |
| `clearAll` wipes recent | Path/filename in evidence |

## INVARIANT

- Join key = full SHA-256 only
- Green = already in library (not “paired/merged”)
- Copy: 「이미 보관」 — never 「이미 연결」
- Recent prefs: `asr.picker_recent.v1.u.$safeUid`, max 30
- Label = SAF name / short folder hint only (no absolute path in evidence)

## Flows

1. 보관 → PDF 가져오기 → sheet  
2. 「파일에서 추가」 → system multi PDF → enqueue + recent save  
3. 최근 행: green if library hash hit; tap = snackbar if green, else re-pick prompt (MVP: still open SAF)  
4. 대기열 행: remove reserved via existing API  

## Evidence

- `picker_sheet_open`
- `picker_recent_save` (`n`, `hash8` only)

## Version

**0.3.222**
