# 285 — Honest handoff → notify · openByCacheId resolve

Version: **0.3.280** · Status: **locked**  
Amends [74](74-bg-upload-notify.md) · [185](185-local-paper-sot.md) · [284](284-ingest-dual-handoff-notify-evidence.md)  
Follows 284 (obs only). Incident: 2026-09-15 notify miss after dual `cache_id` + mid-handoff supersede GC.

## Why

284 sensors (`notify_complete_gate`, `poll_cache_vs_index`, …) prove dishonest complete. Product still:

1. Ignores `_runPaperHandoff` return → `showCompleted` with poll `cache_id` even when handoff failed.
2. `openByCacheId` only matches visible `papers[].id` → miss when id is collapsed mate, supersede loser, or list lag while disk has session.

## Locked product rules

### N1 — Completed notify requires handoff success

After upload/resume poll ok + `_confirmCacheInLibrary`:

| handoffOk | confirm (seen) | Notify | Upload return |
|-----------|----------------|--------|---------------|
| 1 | 1 | `showCompleted` | `result` |
| 1 | 0 | `showFailed` (list miss) | `null` |
| 0 | * | `showFailed` (handoff fail) | `null` |

Always emit `notify_complete_gate` **before** notify with matching `will_notify` (`completed`|`failed`).  
Do **not** change lease / supersede / dual-run algorithms in this chip.

Failed message (handoff):  
`기기로 옮기기에 실패했습니다. 보관함에서 열어 보거나 다시 동기화해 주세요.`

### N2 — `openByCacheId` resolve ladder (after id miss + refresh)

1. Soft-hidden → miss (`miss_reason=soft_hidden`) — unchanged.
2. Any visible row with `pairedCacheId == id` → **open that row** (`mate_resolve=1`, stage `hit` / `hit_mate`).
3. Disk index entry for `id` has `contentHash` → any visible row with same hash → **open that row** (`mate_resolve=0`, details `resolve=same_hash`, stage `hit_same_hash`).
4. `PaperDiskStore.hasSession(id)` → open via disk SoT: prefer index→`toPaperEntry` / equivalent; else minimal `PaperEntry(id: id)` then existing `open()` local path (`resolve=disk_session`, stage `hit_disk`).
5. Else miss (`not_in_list`).

Densify `paper_notify_open` details: keep 284 fields; add optional `resolve` snake token when hit via 2–4 (`mate`|`same_hash`|`disk_session`).

### Non-goals

- Dual-lease / reclaim algorithm
- Supersede GC policy
- Blocking upload when analysis ok but handoff fails beyond notify+return null (library row may still appear after refresh)
- Main/SI pairing product beyond mate open in N2.2

## Tests

| Test | Assert |
|------|--------|
| `tests/test_design_285_*.py` | design locked · version 0.3.280 in app/pubspec/config · markers in library_controller |
| mobile unit (optional) | resolve ladder pure helper if extracted |

## Acceptance

1. Handoff fail → no `showCompleted` / no pending_open for that id; `notify_complete_gate` has `will_notify=failed`, `handoff_ok=0`.
2. Notify tap on collapsed SI id opens main when pair visible.
3. Notify tap on superseded loser id opens same-hash winner when that row is listed and disk index still knows loser’s hash.
4. Notify tap when only disk session exists still opens (local SoT).
