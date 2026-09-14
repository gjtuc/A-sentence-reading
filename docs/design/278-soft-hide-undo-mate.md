# 278 — Soft-hide undo must restore expanded mate (275 asymmetry)

Version: **0.3.271** · Status: **locked**  
Amends [275](275-import-green-set-evidence-honesty.md) · [224](224-soft-delete.md) · [258](258-soft-hide-snackbar-abandon-enrich.md).

## Problem

Phone: alumina Main+SI → library shows only「메인」, import set stays **blue**, no merge CTA. SI text/figures absent in reader (never merged, and SI gone from library).

**Causal defect (275):**
1. Collapsed set trash soft-hides **main+SI** (`softHidePapers` expands `pairedCacheId`).
2. SnackBar「실행 취소」calls `undoSoftHide` with the **pre-expansion** UI id list (main only).
3. Main returns; SI stays soft-hidden → filtered out before pairing → unpaired「메인」.
4. After grace, `purgeDueSoftDeletes` hard-deletes SI.

Evidence pattern: `paper_soft_hide` `requested_n:1` / `n:2`, then `paper_soft_undo` `n:1`.

## Locked product

1. `softHidePapers` returns **`hiddenIds`** (expanded list actually hidden).
2. Library SnackBar undo uses **`hiddenIds`**, not the pre-expansion selection.
3. `undoSoftHide` also expands: if undoing A and mate B is still soft-hidden (disk index `pairedCacheId`), restore B too (and reverse).
4. Evidence: `paper_soft_undo` details include `requested_n` + `n` (expanded).

## Non-goals

Changing 275 mate-expand-on-hide · changing cancel orphan purge (265c) · auto-merge.

## Recovery (ops)

Re-enqueue import Main+SI set for alumina (docx SI) after fix APK; partial ingest still surfaces via 275.

## Tests

- softHide expands mate; undo with returned ids restores both.
- undoSoftHide([main]) while SI hidden restores both via disk pairing.

## Ship

**0.3.271**
