# 240 — Library paired set row / merge nudge

Version: **0.3.235** · Status: **locked** · Amended by [261](261-cross-source-pair-set-row.md)  
Amends [152](152-supplementary-merge.md) · [218](218-supplementary-soft-pairing.md) · polish [243](243-pdf-import-remaining-polish.md)

## Locked

- Parse API `paired_cache_id` into `PaperEntry.pairedCacheId`.
- Disk `PaperDiskIndexEntry` + `toPaperEntry` keep `pairedCacheId` + `canMergeSupplementary`; refresh upsert preserves them.
- `pairAdjacent` helper sorts mates next to each other for list order.
- Visual pair when unpaired.
- When paired + both ready: **one set row** (SI hidden); confirm CTA for true merge ([261](261-cross-source-pair-set-row.md)).
- **No silent auto-merge** without confirm.

## Version

**0.3.235**
