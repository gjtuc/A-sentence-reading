# 221 — Upload reservation queue (multi-PDF enqueue)

모듈: `mobile/lib/api/upload_reserve_*.dart` · `library_controller.dart` · `library_screen.dart` · `widgets/upload_queue_sheet.dart`  
받침: [70](70-mobile-upload.md) · [71](71-mobile-upload-resume.md) · [72](72-chunked-upload.md) · [76](76-upload-workmanager.md) · [132](132-upload-cancel.md)

## Locked (MVP)

| 결정 | 값 |
|------|-----|
| Durable queue | prefs `asr.upload_reserve.v1` + disk `ingest_reserve/{sha256}.pdf` |
| Active head | **keep** singleton `asr.upload_draft.v1` + `ingest_drafts/` (WM/FGS/resume 호환) |
| Pump | serial only — mirror `_pumpPendingEnrichQueue`; wrap existing `uploadPdf` |
| Add while analyzing | yes |
| Remove reserved | local only (delete prefs row + reserve file) |
| Cancel active | design/132 only — does **not** wipe pending reserved |
| Auto-open | `first_only` (첫 성공 1건만 읽기 탭 자동 open) |
| Server | no API change |
| Parallel Gemini / multi-job | **no** |
| FGS stop | only when queue empty **and** no resumable draft |
| Max queue | 20 |

## Non-goals (this chip)

- Parallel `uploadPdf` / multi active draft
- Holding all PDF bytes in RAM
- Clearing global draft when removing a **pending** item
- Server-side reservation queue
- Reorder UI beyond FIFO (FIFO only in MVP)

## Flows

1. 보관 → PDF 가져오기 → SAF **multi-select** → each file sha256 → write `ingest_reserve/{hash}.pdf` → append prefs item (`status=reserved`)
2. `_pumpUploadQueue`: if not uploading/reanalyzing and no resumable draft blocking → promote head → `uploadPdf` (writes singleton draft as today)
3. Success → remove queue item + reserve file → optional `pendingAutoOpenCacheId` (first_only) → pump next
4. Fail with draft still resumable → keep item `active`; do **not** pump next
5. Fail with draft cleared / cancel → remove item → pump next
6. Cold start: load prefs; migrate lone draft into queue UI if missing; resume draft first; else pump reserved

## Evidence kinds

- `upload_queue_enqueue`
- `upload_queue_remove`
- `upload_queue_pump_start`
- `upload_queue_pump_done`
- `upload_queue_blocked`

## INVARIANT

- At most one in-flight `uploadPdf` / singleton draft
- Reserve PDFs never deleted by `_drafts.clear()` (separate tree)
- Logout `clearAll` clears reserve queue + files
- Evidence kinds allowlisted py ↔ dart

## EDGE

- Duplicate hash while reserved → skip / snackbar (no second copy)
- SAF bytes null → fail that file only; others still enqueue
- Queue full (20) → refuse extras
- Reanalyze in flight → enqueue allowed for later; pump waits until reanalyze idle
- `discardResumeDraft` → drop matching active queue item → pump

## Version pin

Web/mobile **0.3.220**
