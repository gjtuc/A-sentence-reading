# 257 — Ingest poll slim + practice cap + translate hydrate honesty

Version: **0.3.257** · Status: **locked**  
Amends [256](256-ingest-poll-oversized-causal-evidence.md) · [99](99-mobile-translate-opt-in.md) · [80](80-shadowing-chunks.md) · [129](129-figure-window.md)

## Why

Live evidence (design/256) proved three product roots:

1. `public_job_view` merges full `result` with figure `image_src` data-URLs (~43MB) → Cloud Run HTTP 500 on poll → resumable draft → Word queue stuck.
2. `_MAX_SENTENCES = 400` rejects papers with 1044 sentences (`sentences_over_max`). SI (221) build actually succeeded; UI error was **global** `shadowingChunksError` cross-talk from the main paper.
3. `_wantTranslate()` returns `false` while any figure hydrate is active — suppresses KO backfill even when Settings translate is ON. Pref-OFF empty KO stays opt-out (design/99); do **not** auto-fill while OFF.

## Locked product changes

### P1 — Slim ingest job poll / pack (unblocks queue)

1. `_pack` and other ingest `to_public_dict()` that feed `job["result"]`: use **`include_images=False`**.
2. `public_job_view`: before `out.update(result)`, run **`slim_job_result_for_poll(result)`**:
   - Strip / empty every `image_src` on `figure` and `figures[]`
   - Keep: `cache_id`, `session_id`, `title`, counts, `sentences` (text only), `translate_pending`, `shadowing_chunks`, `harmonize_*`, `warnings`, `ingest_quality`, …
3. On done: **do not force** `translate_pending = False` if result already has `translate_pending=True` (deferred KO honesty).

`ingest_job_view_size` evidence remains; after fix, oversized should be rare for new jobs.

### P2 — Practice sentence cap

- Raise `_MAX_SENTENCES` / `MAX_SENTENCES` from **400 → 2000**.
- Budgeted slice build unchanged.
- Reader: show `shadowingChunksError` only when `shadowingChunksCacheId ==` open paper `cacheId` (no cross-paper banner).
- Distinct user message when API error is `sentences_over_max` (optional; HTTP body already carries code).

### P3 — Translate want honesty

- `_wantTranslate()`: **remove** “hydrate active ⇒ false” short-circuit. Prefer live Settings toggle / prefs always.
- Still **no** KO backfill while pref OFF (`translate_optout_mismatch` stays the alarm).

## Non-goals

- Changing design/99 default (translate still default OFF)
- Freezing new evidence kinds
- Soft-truncate first-N practice without user consent

## Tests

`tests/test_ingest_poll_slim_257.py` — slim helper · public_job_view no data-URL · pack marker · MAX 2000 · version **0.3.257**

## Version

**0.3.257**
