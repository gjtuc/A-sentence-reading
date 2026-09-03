# 171 — Device figure/table disk cache

**Parent:** [129-lazy-figure-open.md](129-lazy-figure-open.md) · [169n-figure-hydrate-library.md](169n-figure-hydrate-library.md) · [102-library-delete.md](102-library-delete.md)  
**Status:** **0.3.145** — mobile documents PNG cache  
**UI:** no new screens; hydrate banner hides when disk already full after kill/reopen

---

## 0. Locked judgments

| # | Judgment |
|---|----------|
| J1 | Figure + Table are one carousel; same on-disk cache. |
| J2 | Cache survives process kill; network only for missing slots. |
| J3 | Library delete purges `{cache_id}` folder; server GCS delete unchanged. |
| J4 | Paths are uid-scoped; same-uid re-login keeps disk; logout clears RAM only. |
| J5 | Server `/open` + `/figures/window` contracts unchanged (data-URLs). |
| J6 | `content_hash` mismatch → wipe paper dir then re-hydrate. |

---

## 1. Layout

```text
{documents}/asr_figure_cache/u/{uid_safe}/{cache_id}/
  manifest.json
  {figure_id}.png
```

Module: `mobile/lib/services/figure_disk_cache.dart` (`FigureDiskCache`).

---

## 2. Integration

| Path | Behavior |
|------|----------|
| Hydrate | inject disk → skip window if filled==total → write on window merge |
| Reader open | disk inject → RAM hydrate preserve → prefetch skips if ±1 filled |
| Delete | `_figureDisk.purge` + clear `_hydrateSessions` / `_figureHydrate` |
| Auth | `bindFigureDiskUid` on login; `bindUid(null)` on `clearAll` |

Evidence details: `source=disk|hydrate_bg|reader_prefetch`, `disk_hit_n`, `disk_miss_n`.

---

## 3. Acceptance

1. Hydrate paper to full → force-stop app → reopen library → **no** long `그림 x/N 받는 중` (disk hit).  
2. Delete paper → folder gone; reopen would re-download.  
3. Reanalyze (new content_hash) → wipe + honest re-fetch.
