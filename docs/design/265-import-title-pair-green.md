# 265 — Import title · pairing · green「이미 보관」

Version: **0.3.262** · Status: **locked + shipped**  
Amends [223](223-library-content-hash-border.md) · [224](224-soft-delete.md) · [228](228-pdf-advisory-title.md) · [239](239-pdf-import-advisory-set-pairing.md) · backlog from folder audit (4 mate folders).

Does **not** reopen [263](263-si-merge-integrity.md) merge/bib/figure logic.

## Problem

1. **G** — Import green border = `content_hash ∈ libraryContentHashes` (「이미 보관」). Soft-hide removes the row from UI but disk index still contributes the hash → green sticks until refresh/purge. Hard delete did not rebuild the set.
2. **T** — `guessAdvisoryTitle` prefers truncated / code-like `Info.Title`, and ACS/RSC SI falls through to filename stem (`an1c00673 si 001`, `__1_` → `1`).
3. **P** — Sets require identical `effectivePairingKey` + 1 main + 1 SI. Bad titles → missing or false pairs (both stem `1`).

## Locked product

### G — soft-hide-aware library hashes

1. Meaning unchanged: green = hash is in an **visible** library paper (not soft-hidden).
2. `_rebuildLibraryHashSet` skips disk index rows whose `id ∈ softDelete.hiddenIds`.
3. Call rebuild after soft-hide, hard delete (ok ids), and rely on undo→refresh rebuild.
4. Do **not** purge disk on soft-hide (224 undo/grace intact).

### T — advisory title quality

1. Qualify candidates: reject truncated Info, ACS-code Info, affiliation/Figure S captions, low-quality stems.
2. SI head: skip SI banner then skip affiliation/caption lines before accepting a title.
3. Strip trailing `To cite this article…` / cite chrome.
4. If nothing qualifies → `title=''`, `source='failed'` (no stem `1`/`2` as title).
5. Bump `kPdfAdvisoryCacheSchema` **10 → 11** (wipe stale advisory rows).

### P — pairing key quality + soft-pair

1. `isUsablePairingKey`: reject keys shorter than 12 chars (blocks false `1`/`2` sets).
2. When title key unusable: prefer `doi:<doi>` if DOI present; else `acs:<manuscriptId>` from filename stem (ACS-style id).
3. Success metric: filename gold pairs would_pair ↑ and false sets → 0 — **not** raw set count.
4. `buildPdfImportListItems` unchanged contract (empty key → single/pending).

## Non-goals

265c cancel-orphan · Documents 262 · architecture 255/173 · silent auto-merge · 263 bib cut · server title extractor.

## Tests

- Title fixtures: truncated info → head; code info reject; SI caption skip; stem `1` → failed; cite suffix strip.
- `isUsablePairingKey` rejects short keys.
- Soft-hide / rebuild skips hidden disk hashes (logic covered in controller + unit helpers where extractable).

## Migration

Open import folder after upgrade so advisory re-runs (schema 11). Soft-hide green clears without reinstall data wipe.
