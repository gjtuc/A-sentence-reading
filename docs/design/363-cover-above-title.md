# 363 — The cover sits above the title

**Version:** 0.3.359 · Status: **locked**
Found when classifying supplementary PDFs after [362](362-two-label-styles.md) · supersedes the body-search half of [229](229-acs-si-badge-chrome-veto.md) / [235](235-doc-role-conspectus-esi-footnote-veto.md) / [281](281-si-filename-supported-abstract-veto.md)

## Why

The old detector searched the first 8,000 characters for `Supporting Information` /
`Supplementary` / `ESI`. Main papers print those words after the title — as an ACS
badge above the abstract, as an RSC footnote, as a methods sentence. Three files in
the 95-file folder were called SI for that reason:

- `manabayeva-…-synthesis.pdf` — title first, badge, ABSTRACT
- `wang-et-al-…-methane.pdf` — the same
- `ChemistryOpen - 2015 - Jiang - …` — title first, the word appears later

Their ACS twins with a trailing `1` (`…synthesis1.pdf`, `…methane1.pdf`) really are
SI: line 1 is `S1`, line 2 is `Supporting Information`, line 3 is the title.

A main paper can mention supplementary material anywhere in the body. It is very
hard for it to print the cover phrase *above its own title*.

## Locked

Either signal is enough.

### 1. The filename

`_si_001`, `mmc1`, `MOESM`, `ESM`, `suppl`, `.som.`, `suppmat` (the existing
`filename_looks_like_si`, which already refuses `supported`). Reason `filename_si`.

This is how `41929_2026_1513_MOESM1_ESM` stays SI: Nature reprints the article title
above `Supplementary information`, so the cover line is *under* the title. The
filename still has `MOESM` / `ESM`.

### 2. The cover line above the title

These phrases, as their own line, before any title line:

- Supporting Information
- Supporting Online Material
- Supporting Material
- Supplementary information
- Supplementary Materials
- Electronic Supplementary Information (the RSC spelling of the same cover)

Walk from the top. Skip journal furniture (`S-1`, ACCESS, Cite This, a URL). The
first real line is either the cover or the title. A cover sitting on `ABSTRACT` /
`CONSPECTUS` with no title in between is the ACS badge, not a cover. Reason
`cover_above_title`.

A sentence that merely contains the words (`Details are given in the Supporting
Information.`) does not match.

## Not this chip

- **A trailing `1` on an ACS filename** is not a rule. `…synthesis1.pdf` is SI
  because of the cover line, not because of the `1`. The twin without `1` is the
  main paper.
- **`Extended Data`** — Nature's third numbering. No file in the folder is only
  that.

## Files

- `src/sentence_reading/pdf/supplementary_detect.py` — `cover_phrase_above_title`
- `mobile/lib/pdf/doc_role_detect.dart` — the same walk
- `tests/test_design_363_cover_above_title.py`
