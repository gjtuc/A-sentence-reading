# 256 — Ingest poll oversized + practice/translate mismatch causal evidence (overkill)

Version: **0.3.256** · Status: **locked**  
Amends [168](168-ingest-observability.md) · [179](179-false-worker-lost-poll-library-evidence.md) · [169p](169p-shadowing-practice-evidence.md) · [221](221-upload-reservation-queue.md) · [99](99-mobile-translate-opt-in.md)

## Why

Live incident (alumina / Elsevier main+SI, 2026-09-13):

1. Ingest job **completed** on server, but mobile poll of `GET /api/ingest/jobs/{id}` kept returning **HTTP 500** → UI 「진행 상태 조회 실패」→ resumable draft stuck → `upload_queue_blocked` → Word SI stayed **대기**.
2. Root of 500: `public_job_view` merges full `result` including **figure base64** (~43MB job JSON). Evidence only had `http_error` / `500` — **no size signal**.
3. Practice prep failed with `bad_sentences` / HTTP 400 while paper had **1044** sentences vs hard cap **400** — details lacked `sentence_n`/`max_n`.
4. Translation looked “not needed” (`need_ko=0`) while session had **ko_n=0**, because ingest used `translate_skipped_opt_out` / client translate pref off — no mismatch alarm.

**Product fixes (strip job payload, raise sentence cap, KO backfill) are deferred.** This chip densifies detection so the next fix chip is falsifiable.

## Hard constraints

- No DOI / URL / path / filename / paper text / base64 in evidence details
- Details: lowercase snake tokens only
- Allowlist both `evidence_kinds.py` + `evidence_kinds.dart`
- Do **not** shrink `FROZEN_KINDS` (add-only; freeze later after live pull)
- Observability only — do **not** strip job result or change practice caps in this version

## Locked emit map

### E1 — `ingest_job_view_size` (server, every poll GET)

Emit in `ingest_job_status` **after** building the public view, **before** `JSONResponse`.

| Field | Meaning |
|-------|---------|
| `result_present` | 0/1 |
| `result_keys_n` | number of keys on `job.result` |
| `figure_n` | figures list/dict length if present |
| `sentence_n` | sentences length if present |
| `data_url_n` | count of string fields starting with `data:image` (walk result shallow+figures only) |
| `data_url_bytes_sum` | sum of those string lengths |
| `est_bytes` | structural estimate (not necessarily full `json.dumps`) |
| `oversized` | 1 if `est_bytes` ≥ **4 MiB** |
| `code` | `result_too_large` when oversized else `ok` |

Join: `job_id`, `trace_id`, `cache_id` when known.

### E2 — densify `ingest_poll_terminal` (mobile)

On every terminal (esp. `http_error`): add `body_bytes` = response body length.  
On success path before decode: still record body size when emitting terminal `ok`.

### E3 — densify `upload_queue_blocked`

When `stage=resumable_draft`: include `job_id` (safe id) + `hash8` for join to poll failures.

### E4 — shadowing `sentences_over_max`

- `build_chunk_plan`: raise `ValueError("sentences_over_max")` when `len(sentences) > MAX` (keep `bad_sentences` only for non-list).
- `shadowing_chunks_build_done` details: `error=sentences_over_max`, `sentence_n`, `max_n`.
- Verdict catalog recognizes `sentences_over_max` → `sentences_over_max_blocks_practice`.

### E5 — `translate_optout_mismatch` (mobile)

Emit when session has `sentence_n ≥ 1`, `ko_sentence_n == 0`, and translate pref is **off** (or ingest opt-out implied by pref off + empty KO with `translate_pending != true`).

Details: `want_translate`, `sentence_n`, `ko_sentence_n`, `ko_missing_n`.

Also densify `pending_enrich_start` / `pending_enrich_scan` with `want_translate`, `sentence_n`, `ko_missing_n` when cheap.

### E6 — linked verdicts (pure, no I/O)

Module: `sentence_reading.llm.ingest_queue_verdict`

| Verdict | Rule |
|---------|------|
| `poll_500_blocks_upload_queue` | same `job_id` (or same `trace_id`): `ingest_poll_terminal` with `http_status≥500` **and later** `upload_queue_blocked` `stage=resumable_draft` |
| `translate_optout_empty_ko` | any `translate_optout_mismatch` **or** (`open_ko_summary`/`reader_open` details with `sentence_n>0`, `ko_sentence_n=0`, `translate_pending=false` + pref off signal) |
| `sentences_over_max_blocks_practice` | `shadowing_chunks_build_done` code/error `sentences_over_max` |
| `job_view_result_too_large` | `ingest_job_view_size` with `oversized=1` / `code=result_too_large` |

CLI: `scripts/track_ingest_queue.py` (pull optional; accepts `--events` JSONL).

## Non-goals (this version)

- Stripping `figure`/`figures`/`image_src` from `public_job_view` (product fix chip)
- Raising `_MAX_SENTENCES` or slicing build (product fix chip)
- Auto-clearing stuck drafts
- Freezing new kinds into `FROZEN_KINDS`

## Tests

`tests/test_ingest_poll_oversized_evidence_256.py` — design locked · kinds mirrored · markers · size helper · verdicts · version **0.3.256**

## Version

**0.3.256**
