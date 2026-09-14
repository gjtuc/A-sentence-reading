# 273 — Transitional pair rows + connector

Version: **0.3.264** · Status: **locked**  
Amends [240](240-library-paired-set-row.md) · [261](261-cross-source-pair-set-row.md)

## Locked

1. Collapse SI into one set row **only when** `canMergeSupplementary` (both ready).
2. Otherwise keep **two** adjacent rows (`pairAdjacent`) with leading accent bar on both (= connector).
3. Merge CTA only when `canMergeSupplementary`.

## Kill

Revert.
