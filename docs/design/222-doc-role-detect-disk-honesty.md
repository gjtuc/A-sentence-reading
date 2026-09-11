# 222 — Doc-role detect densify + disk tag honesty

Version: **0.3.221** · Status: **locked**  
Amends [152](152-supplementary-merge.md) · [218](218-supplementary-soft-pairing.md) · [185](185-paper-local-sot.md)

## Problem (phone Ni/Cu 2026-09-11)

1. Library showed **two 메인** rows (8/6 vs 234/12). Soft pairing cannot link main↔main.
2. `Supplementary 1/8` on the short row is a **resume section**, not `doc_role`.
3. Downloads `an1c00673_si_001.pdf` detects as `supplementary` today — but:
   - **ZWSP/BOM** before “Supporting Information” → old detector → `main`
   - **Vision recover** upgraded text without **re-detecting** role → stuck `main`
   - After **handoff wipe**, `PaperDiskIndexEntry` had **no `doc_role`** and `toPaperEntry()` **forced 메인** — so even a correct SI looked like main on device

## Locked fixes

### Server detect (`supplementary_detect.py`)

- `detect_doc_role_detailed` → `DocRoleDetectResult{role, reason, …}`
- Strip format chars (BOM/ZWSP) before match
- Primary: line-start SI journal markers (unchanged intent)
- Secondary: `filename` looks like SI **and** head has `S-n` page label
- Ingest: detect **pre_vision** and **post_vision** (unless job override)
- Post-vision cache hit passes `doc_role=`

### Evidence kinds

- `doc_role_detect_start` / `doc_role_detect_done`
- `doc_role_redetect_after_vision`
- `doc_role_pairing_gap` (2+ mains, same pairing_key, 0 SI)

Details: `role`, `reason`, `marker_hit`, `filename_si_hint`, `page_label_hit`, `stripped_format`, `head_len`, `main_n` — **no** paper text / paths.

### Library list

- API rows include `content_hash` when known (picker join prep)

### Mobile disk honesty

- `PaperDiskIndexEntry.docRole` persisted
- `toPaperEntry()` uses it (칩 보충/메인)
- `ReadingSession.docRole` from open/ingest → session.json
- Refresh upserts remote `doc_role`/`content_hash` onto disk **before** handoff wipe

## Non-goals

- Auto-merge
- Client-side SI classification for picker preview
- MediaStore scanner

## Tests

`tests/test_doc_role_detect_222.py` · pairing gap · list `content_hash` · disk tag comments in mobile surface test

## Version

**0.3.221**
