# 225 — Library density follow-ups (224b · upload bar · magnetic trash)

Version: **0.3.224** · Status: **locked**  
Depends: [224](224-library-density-ux.md) · [221](221-upload-reservation-queue.md) · [122](122-library-reorder-no-white-flash.md) · [132](132-upload-cancel.md)

## Locked this ship

| Include | Exclude (later) |
|---------|-----------------|
| **224b** — soft-hide of open paper → leave reader surface | Server tombstone |
| **225-U** — shared `UploadStatusBar` on library + reader | MediaStore picker |
| **225-F** — edit-mode drag over trash → soft-hide (no order persist) | **225-G** multi-block reorder |
| Picker green keeps disk hashes while soft-hidden (P-keep) | Soft-hide removes green |

## INVARIANT

- Soft-hide still filters via `_publishPapers` / prefs (224)
- Magnetic trash drop: **no** `reorderPapers` / order prefs write
- Drag id snapshotted at `onReorderStart` (not drop index alone)
- design/122 proxy kept (wrap with `Listener`, do not replace)
- `cancelUpload` same path from library or reader
- AccessWaiting: still no gear/library

## Flows

1. Reading paper soft-hidden → `clearOpened` + `nav_surface=library`
2. Upload / auto-open → reader shows progress + 취소 / 대기열
3. Edit → drag row onto trash (magnet) → soft-hide + 60s undo SnackBar
4. Edit → tap trash with checks → same soft-hide helper

## Evidence

- `nav_surface` when soft-hide forces library (existing kind OK)
- optional: reuse `paper_soft_hide`
- no new floor kinds required

## Version

**0.3.224**
