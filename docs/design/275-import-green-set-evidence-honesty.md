# 275 — Import green honesty · set ingest evidence · no false success

Version: **0.3.268** · Status: **locked**  
Amends [223](223-library-upload-picker-investigation.md) · [224](224-library-density-ux.md) · [239](239-pdf-import-advisory-set-pairing.md) · [261](261-cross-source-pair-set-row.md) · [265](265-import-title-pair-green.md) · [177](177-paper-delete-causal-evidence.md) · [169g](169g-causal-handoff-evidence.md)

## Problems (phone 2026-09-14)

1. **Ghost green:** Import shows 「이미 보관」 green for SI files that are not visible in the library.
2. **Main+SI set → SI-only feel:** Set enqueue can report success while only one side later lands; detectors cannot tell.
3. **Evidence honesty:** Failures put `ok` only inside `details`, or mark delete `ok:true` before local disk purge; soft-purge HTTP fail is silent.

## Causal (code)

### A. Green border SoT drift

`libraryContentHashes` = visible `papers` ∪ **all** non–soft-hidden **disk index** rows (`_rebuildLibraryHashSet`).

- Soft-hide of a **collapsed set row** only hides the **main** `cache_id` (UI id). Mate SI stays on disk, not in `hiddenIds` → SI hash still greens while the set row is gone from the list.
- Disk orphan after “successful” delete (HTTP ok, local `purge` fail) → green with no library row.
- design/265 fixed soft-hide for *hidden* ids, not mate / orphan / collapse.

### B. Set enqueue vs ingest outcome

`enqueueFolderPdfSet` → `enqueuePickedPdfs` (both bytes). Queue does **not** skip already-green hashes. Later pump/ingest can fail one side.

`pdf_import_set_enqueue` records `details.ok = added >= 2` but often **omits top-level `ok`**. No join evidence that **both** cache_ids reached ingest ok.

### C. Evidence bus honesty holes

1. Mobile `EvidenceBus.record`: top-level `ok` only if caller passes `ok:`; many paths bury failure in `details` only.
2. `_safeDetails` drops most strings (only `[a-z][a-z0-9_]{0,63}`) → lossy diagnosis.
3. `deletePapers`: emits `paper_delete_done ok:true` **before** `_paperDisk.purge`; purge failure still looks like full success.
4. `purgeDueSoftDeletes`: if `deletePapers` returns 0, soft entry stays due — **no** evidence event.

## Locked product / engineering

### G — Green = visible library content (honest)

1. Build `libraryContentHashes` from **published** `papers` (post soft-hide + collapse).
2. For each visible row with `pairedCacheId`, also include the **mate** content hash if mate is not soft-hidden (resolve via disk index / known papers map). Set analyzed → both hashes green → set row green (product wish).
3. Soft-hide of an id **also soft-hides its `pairedCacheId` mate** (same grace/purge).
4. Do **not** union arbitrary disk orphans into green.

### E — Set + delete evidence (no false success)

1. `pdf_import_set_enqueue`: always set **top-level** `ok` = (`added >= 2`); `code` = `ok` / `partial` / `fail`; details ints: `added`, `skipped`, `need_n=2`.
2. After set queue pump completes both items (or one fails): emit `pdf_import_set_ingest` with top-level `ok` only if **both** ingest ok; else `ok:false`, `code=partial|fail`, `main_ok`/`si_ok` as 0/1.
3. `paper_delete_done`: `ok:true` only after HTTP **and** local disk purge attempt; if purge throws → `ok:false`, `code=local_purge_fail` (server may already be gone — still honest).
4. `paper_soft_purge`: each due id → `ok` true/false, `code=ok|http_fail|timeout`; never silent skip.

### D — Detector posture

Prefer top-level `ok == false` over details. Missing top-level `ok` on failure kinds = treat as **unknown/fail-closed** in new verdicts (do not assume success).

## Non-goals

Auto-merge · changing soft-hide 60s grace · shrinking evidence floor · UI redesign beyond green/blue precedence already in 274/set row.

## Version

**0.3.268**
