# 240 — Library paired set row / merge nudge

Version: **0.3.235** · Status: **locked**  
Amends [152](152-supplementary-merge.md) · [218](218-supplementary-soft-pairing.md) · polish [243](243-pdf-import-remaining-polish.md)

## Locked

- Parse API `paired_cache_id` into `PaperEntry.pairedCacheId`.
- Disk `PaperDiskIndexEntry` + `toPaperEntry` keep `pairedCacheId` + `canMergeSupplementary`; refresh upsert preserves them.
- `pairAdjacent` helper sorts mates next to each other for list order.
- Visual pair (connector / subtitle); keep **two** openable rows; strengthen merge chip when `can_merge_supplementary`.
- **No auto-merge.** Reader one-session = existing merge only.

## Version

**0.3.235**
