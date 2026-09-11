# 218 — Supplementary soft pairing + visible role tags

Version: **0.3.218** · Status: **locked** · Amends [152](152-supplementary-merge.md) · [160](160-mobile-library-reader-polish.md)

## Problem

1. Main↔SI pairing used **exact** `title_key`. Author/OCR drift (`the`, SI boilerplate
   prefix, hyphen vs en-dash already folded by NFKC/punct strip) → no `paired_cache_id`
   → merge button never appears.
2. Library **메인/보충** chips sat on the same row as a long title and were easy to miss
   / clip; resume line showed section (`Supplementary 1/8`) which is **not** `doc_role`.

## Locked

1. **Dedup unchanged:** still `title_key + source + doc_role` (no overwrite across near titles).
2. **Pairing key** `normalize_pairing_key(title)` = `normalize_title_key` then strip SI
   boilerplate prefix, then drop English articles `{a,an,the}` only (pairing-only).
3. **`apply_pairing_pass`** indexes by `(pairing_key, source)` for main↔SI 1:1 newest.
4. Exact `title_key` match still wins when present; pairing key covers article drift.
5. Library: role chip **above** title (always visible); `metaResumeLine` prefixes `libraryTag`.
6. Merge eligibility still `can_merge_supplementary` (ingest ok + paired + roles).
7. Non-goals: DOI-only pairing, LLM title rewrite, auto-merge without user tap.

## Merge save hazard (fixed this chip)

`save_paper_session(doc_role=merged)` without `force_cache_id` looked up
`title_key+source+merged`, missed the existing **main** row, wrote a **new**
cache id, then `patch_index_entry(main)` only flipped tags — user saw merge
OK but SI sentences never landed on the opened id. Merge now passes
`force_cache_id=main_id`.

## Tests

`tests/test_supplementary_pairing.py` — Ni/Cu `the` drift; SI prefix; merge flag; tags.

## Version

**0.3.218**
