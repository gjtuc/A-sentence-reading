# 263 — SI bibliography + merge integrity

Version: **0.3.261** · Status: **locked + shipped**  
Amends [152](152-supplementary-merge.md) · [261](261-cross-source-pair-set-row.md) · [148](148-cite-panel.md) · [185](185-local-paper-sot.md)

## Problem

After local merge (261), alumina-class SI showed:

1. Bibliography lines as Supplementary practice sentences
2. Cite panel 「참고문헌을 찾지 못했습니다」 (`session.references` empty)
3. Table S figures stuck on 「그림 불러오는 중」 (id `si-*` ≠ PNG filename)

## Locked product

### B — references or-merge

1. Server merge already: `main.references or si.references`.
2. Local merge **must** match that contract.
3. Prefer main when both non-empty (no silent union / renumber).
4. `readingSessionToPaperDiskJson` must persist `references`.

### C — figure id ↔ PNG parity

1. After `si-` id rewrite, write PNG as `figures/{safe(newId)}.png`.
2. Clear `image_src` on disk session (no data-URL flood).
3. Hydrate may repair: if `si-*` miss, try unprefixed name once and rewrite.

### A — bibliography ≠ practice sentences (SI)

1. **SoT:** `extract_bibliography` on full text → `references[]`.
2. **L0 (SI ingest):** if refs non-empty, debone/split on text **before** References/Bibliography header.
3. **L1:** drop sentences that match bibliography entry text (ingest SI + merge append).
4. **L2:** `chunk_kind` → `references` when parser finds ≥2 entries; references chunks emit **zero** sentences.
5. **Do not** blind-cut all SI after the word “References” when `extract_bibliography` is empty (Nature ESM / short PDF SI).

### Migration

Already-merged sessions: figure hydrate repair (C). Refs/bib sentences: re-import SI + merge, or reanalyze. No silent cloud wipe.

## Non-goals

Documents mirror (262) · architecture 255 · silent auto-merge · main+SI bibliography union · DOCX captionless media flood (D).

## Tests

- Local/server merge SI-only refs
- Local merge figure rename roundtrip
- `cut_bibliography_for_sentences` alumina-like vs bib=0 no-op
- `chunk_kind` EndNote-dense → references + empty pairs
