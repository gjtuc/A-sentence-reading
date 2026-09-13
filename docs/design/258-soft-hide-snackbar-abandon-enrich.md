# 258 — Soft-hide snackbar countdown · abandon enrich banner

Version: **0.3.258** · Status: **locked**  
Depends: [224](224-library-density-ux.md)

## Problem

1. Soft-hide SnackBar single line was mid-truncated by the undo action (`…삭제됩니` / `다.`).
2. Soft-hide only filtered the library list; `pendingEnrich` / `ensureShadowingChunks` kept running, so 「번역·연습 준비 중」 stayed on an empty library.
3. Static 「1분 후」 copy did not show remaining undo time, and the bar lingered with no sense of purge.

## Locked

| Include | Exclude |
|---------|---------|
| SnackBar two lines with **live countdown**: `N건을 숨겼습니다.` / `{secs}초 후 영구 삭제됩니다.` (60→1) | New “영구 삭제됨” success SnackBar after purge |
| At 0s: dismiss SnackBar + `purgeDueSoftDeletes` | Show `0초 후…` |
| On soft-hide: dequeue enrich + abandon in-flight ensure UI for those ids | Kill HTTP mid-request (best-effort stop at slice boundary) |
| Skip enqueue / ensure for soft-hidden ids until undo | Server tombstone |

## INVARIANT

- Soft-hide still = local prefs + wall-clock `purge_at` (design/224, grace 60s).
- Countdown uses `purge_at_ms` from soft-hide SoT (not a separate UI clock).
- Banner busy flags must clear when the only active work is soft-hidden.
- Undo removes abandon marks so enrich can resume after restore.

## Evidence

- `paper_soft_hide_abandon_work` `{n, shadow_hit, enrich_hit, queue_n}`
- `shadowing_ensure_abort` `code=soft_hide_abort`
- Existing `paper_soft_hide` / `paper_soft_undo`

## Version

**0.3.258**
