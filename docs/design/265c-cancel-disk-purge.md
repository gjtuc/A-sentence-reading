# 265c — Cancel → disk purge (policy B)

Version: **0.3.264** · Status: **locked**  
Amends [132](132-ingest-cancel.md) · [185](185-local-paper-sot.md) · [224](224-soft-delete.md) · [265](265-import-title-pair-green.md)

## Problem

Early cancel cleared draft/queue but could leave a partial paper folder / disk index hash → import green「이미 보관」and half rows.

## Locked product

1. **Early cancel** still discards server job/upload (132). No soft-hide (224 undo is wrong here).
2. After successful cancel: wipe drafts/reserve for the **active** hash; **`_rebuildLibraryHashSet`**.
3. If a **paper folder / index row** exists for that ingest (`cache_id` or matching `content_hash`): **hard purge** local artifacts (same stack as delete: edit stash, figures, paper dir, shadowing, bookmarks). Prefer HTTP `deletePaper`; on 404/gone still **local-only purge**.
4. **`tooLate` → no purge** — paper finishes (132).
5. Pending reserved queue items stay (221).

## Non-goals

Soft-hide-as-cancel · SAF/Documents user copies · voice · Documents mirror sync (264+).

## Kill

Revert · or `ASR_INGEST_CANCEL=0` (cancel unavailable unchanged).
