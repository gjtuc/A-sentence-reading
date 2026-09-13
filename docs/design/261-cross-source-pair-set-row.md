# 261 — Cross-source pairing + hybrid set row

Version: **0.3.260** · Status: **locked**  
Amends [218](218-supplementary-soft-pairing.md) · [240](240-library-paired-set-row.md) · [152](152-supplementary-merge.md) · [185](185-local-paper-sot.md)

## Problem

1. Server pairing keyed `(pairing_key, source)` so **pdf main + docx SI** never
   got `paired_cache_id` / merge CTA (import 239 already groups by key only).
2. Library kept two rows; product now wants **one set line** when mates are
   ready — without lying that they are already one reader session.
3. Post-185 handoff, server `POST merge-supplementary` hits `session_missing`.

## Locked product

### A — Pairing

1. `apply_pairing_pass` indexes by **`pairing_key` only** (not source).
2. Pair only when exactly **1 main + 1 SI** for that key; else unpaired + gap
   evidence when 2+ mains.
3. **Dedup unchanged:** `(title_key, source, doc_role)`.
4. Client runs the same local pairing pass after `mergeRemoteWithLocal` so
   wiped libraries still get mates.

### B — Hybrid one row (not silent auto-merge)

1. When paired + both ingest ok: library shows **one set row** (SI hidden from
   list; main tile is the set).
2. Subtitle: 「합치면 한 세션으로 읽기」 — not 「자동 합치지 않음」.
3. CTA **짝과 합치기** still requires confirm dialog (152).
4. True one-session (`doc_role=merged`, SI `hidden_in_library`) only after
   successful merge.

### C — 185-safe merge

1. Prefer **device local merge** when both sessions exist on disk.
2. Else server `POST` while cloud sessions exist.
3. Never claim merge success on `session_missing`.

## Non-goals

Silent auto-merge without confirm · dropping `source` from dedup · Documents
mirror (see [262](262-documents-mirror.md)).

## Version

**0.3.260**
