# 169o — Harmonize residual (post-ingest · plan A)

**Version:** 0.3.143 (ship; 0.3.142 residual + index-preserve fix)  
**Status:** implemented  
**Product:** After analysis, draft KO + digests are durable; sentence/caption
**harmonize** (재감수) continues as a server residual with honest library
progress — same UX family as 169n figure hydrate, **not** a fake “still
translating” residual for work already finished in ingest.

**Kill switch:** `ASR_HARMONIZE_RESIDUAL=0` restores today’s
ingest-inline harmonize (no pending banner). Default **on** (`1`).

**Bugfix (0.3.143):** `save_paper_session` was rewriting the library index
row without `harmonize_*`, so ProgressiveWriter durable saves wiped
`harmonize_pending` and the mobile `재감수 x/N` banner never appeared even
while residual evidence advanced. Preserve those fields across saves.

**Out of scope (v1):** Cloud Run worker count, multi Gemini API keys,
infinite open timeout, translate residual after analysis, changing
`/figures/window` / 169n hydrate logic.

---

## 1. Product decision (plan A)

| Phase | What runs | User-visible |
|-------|-----------|--------------|
| **Ingest / analysis** | pipeline/batch draft KO + `_make_digest` per section; captions draft | Progress through extract → translate draft; ends at ~100% with paper **readable** |
| **Residual** | `_harmonize` pool (sentences + optional captions) | Library: `재감수 x/N 중` → hide on success; honest partial fail + retry/dismiss |
| **Figures** | unchanged 169n hydrate | `그림 x/N 받는 중` (parallel, independent) |

**Honesty rule:** Do not claim “filling translation” after analysis if draft
KO already exists. Only claim **재감수** for remaining `text_ko_stage !=
harmonize` (and caption equivalent if included).

**Digest:** stays **in ingest** (plan A). Residual requires
`session.translate_digests` (or equivalent durable digests). Missing digest
→ skip section + warning / `harmonize_residual_abort` for that slice — never
silently invent success.

---

## 2. Current call graph (cut point)

```text
app.py  _run_ingest_job_body
  └─ want_translate && gemini_available()
        ProgressiveWriter.start()
        def _on_item(...):  # memory + ProgressiveWriter
              session.sentences[i] = replace(..., text_ko, text_ko_stage)
        enrich_session_translations(...)   # translate_section.py
        prog_writer.flush()
        final save / job done 100%
```

Inside `_enrich_session_translations_body`:

```text
for each section:
    Google/Gemini pipeline  → draft KO, on_item(stage=google|draft|…)
    _make_digest(sec, …)    → digests[sec]
    if digest nonempty:
        harmonize_pool_* + ThreadPool _run_harmonize   # ← MOVE TO RESIDUAL
            on_item(..., stage="harmonize")
captions: draft + optional _harmonize(...)             # ← MOVE IF v1 includes captions
```

**Cut:** section `harmonize_pool_*` / `_run_harmonize` (+ caption harmonize).  
**Keep in ingest:** pipeline/batch + `_make_digest` + digests return/persist.

---

## 3. Chip 0 — schema / flags / phase

### 3.1 Existing stages

`Sentence.text_ko_stage` / `Figure.caption_ko_stage` already carry
`draft|…|harmonize`. Residual completion = stage becomes `harmonize`.

### 3.2 Job / result / paper fields (new)

| Field | Type | Meaning |
|-------|------|---------|
| `harmonize_pending` | bool | Draft+digest done; harmonize remaining |
| `harmonize_total` | int | Target sentence (+caption) count |
| `harmonize_done` | int | Successful harmonize patches |
| `harmonize_failed` | int | Confirmed failures |
| `harmonize_attempt_n` | int | Residual generation / retry count |

Surfaced on job `result` and on paper/cache list + open payloads so the
client can poll after `done=true`.

### 3.3 `derive_ingest_phase` (`ingest_jobs_gcs.py`)

**Recommendation:** keep phase `complete` when `done` so library “보관 가능”
semantics stay; drive UI from `harmonize_pending` separately (do **not**
force `translate_pending`). Adding a new phase enum is optional later and
touches mobile chips — avoid in v1 unless needed.

Existing `translate_pending` remains for true empty-KO backfill only.

### 3.4 Env

```text
ASR_HARMONIZE_RESIDUAL=1   # ship default when enabled
ASR_HARMONIZE_RESIDUAL=0   # enrich runs harmonize inline (today)
```

### 3.5 Tests

- Job/result round-trip with new fields  
- `done + harmonize_pending` does not map to `translate_pending`

---

## 4. Chip 1 — split `enrich_session_translations`

**File:** `src/sentence_reading/llm/translate_section.py`

### 4.1 Signature

```text
enrich_session_translations(..., *, run_harmonize: bool | None = None)
```

- `None` → follow `ASR_HARMONIZE_RESIDUAL` (when residual on, ingest call
  site passes `run_harmonize=False`)
- Explicit bool for tests

### 4.2 Body

After digest per section:

- `run_harmonize=True`: existing pool block (behavior parity)
- `run_harmonize=False`: skip pool; still store `digests[sec]`

Captions: draft always; harmonize only if `run_harmonize`.

### 4.3 `_translate_work_units`

Only add harmonize units when `run_harmonize` so ingest 90–97% does not
wait on the long pool.

### 4.4 Extract + residual entry

```text
_harmonize_section(sec, idxs, digest, …)   # refactor of existing pool
harmonize_session_residual(sentences, figures, digests, *,
    on_progress, on_item, workers, job_id, cache_id, …)
count_harmonize_targets(session, digests) → int
```

Residual: require digests; missing → skip + `harmonize_skipped_no_digest`;
reuse `_run_harmonize` / `on_item(..., "harmonize")`.

### 4.5 Tests

- `run_harmonize=False` → `_harmonize` call count 0; digests present  
- `harmonize_session_residual` → N `_harmonize` calls with digests

---

## 5. Chip 2 — ingest exit (`app.py`)

Near translate phase (~`_run_ingest_job_body` ProgressiveWriter /
`enrich_session_translations`):

```text
residual = harmonize_residual_enabled()
enrich(..., run_harmonize=not residual)
flush ProgressiveWriter
persist session (draft KO + digests)

if residual and count_harmonize_targets(...) > 0:
    result: harmonize_pending=True, total/done/failed/attempt_n
    job done=True, percent=100  # readable / library-ready
    asyncio.create_task(_run_harmonize_residual(...))
else:
    harmonize_pending=False  # today’s full complete
```

`_pack` / job result must expose the harmonize_* fields next to any
`translate_pending`.

### 5.1 Interactions with existing guards

| Mechanism | Residual implication |
|-----------|----------------------|
| `_on_item` abort when `done and error` | Residual is `done and not error` → patches allowed |
| lease heartbeat stops on `done` | Residual does not use ingest lease; sweeper must not reclaim done jobs as `worker_lost` for residual work |
| instance death | Need chip 3b: GCS `harmonize_pending` + reclaim/resume |

---

## 6. Chip 3 — `_run_harmonize_residual`

**Location:** `app.py` and/or `llm/harmonize_residual.py` (task spawn in app).

```text
1. Load session by cache_id / job
2. digests = session.translate_digests
3. emit harmonize_residual_start {total, attempt_n}
4. ProgressiveWriter + _on_item (same pattern as translate phase)
5. await to_thread(harmonize_session_residual, …)
6. Throttle update harmonize_done on paper/job meta
   (percent stays 100; message or meta = 「재감수 done/total」)
7. flush; final paper_cache save
8. harmonize_pending=False; emit done or partial
9. fail-soft: never uncaught into event loop
```

### 6.1 Why not only job poll

Client may stop polling the ingest job after `done=true`. Prefer paper list /
open fields (chip 4) as SoT for banner numbers.

### 6.2 Chip 3b — resume after restart

If `harmonize_pending` and no local residual running: claim residual lease
(reuse 169m claim/obs patterns where practical) and spawn residual again.
Avoid double-running two pools on the same cache.

---

## 7. Chip 4 — status read API

**Recommendation:** embed on `GET` papers list + open response:

`harmonize_pending`, `harmonize_done`, `harmonize_total`, `harmonize_failed`

Optional later: `GET /api/cache/{id}/harmonize_status`.

Touch: papers serializer, open `data[...]`, mobile `PaperEntry` parsing.

---

## 8. Chip 5 — mobile library UI (169n twin)

### 8.1 `mobile/lib/state/harmonize_residual.dart`

Mirror `figure_hydrate.dart`:

- phases / snapshot  
- `userLabel`: `재감수 40/120 중` / `재감수 3문장 실패` / empty when done

### 8.2 `library_controller.dart`

On ingest success (beside `enqueueFigureHydrate`):

- if `harmonizePending` → start poll (2–3s) against papers/open fields  
- update snapshot; hide on success  
- **client does not call Gemini** — display only

### 8.3 `library_screen.dart`

Subtitle: harmonize label next to figure hydrate label.

Failure: retry / dismiss (same honesty as 169n).

### 8.4 Chip 5b — reader merge

If reader open while residual runs: poll/merge `text_ko` where stage
became `harmonize`; optional reader banner. Reuse translate-poll /
`preserveClientStateFrom` patterns where possible.

---

## 9. Chip 6 — evidence / floor

### 9.1 New kinds

| kind | when |
|------|------|
| `harmonize_residual_start` | residual task begins |
| `harmonize_residual_progress` | sampled progress |
| `harmonize_residual_done` | pending cleared, failed==0 |
| `harmonize_residual_partial` | failed>0 or gaps |
| `harmonize_residual_abort` | cannot start (no digest / claim fail / open fail) |

Existing `translate_call_*` with `call_kind=harmonize` and
`harmonize_pool_*` remain inside residual (no deletion — evidence floor).

### 9.2 Floor markers

Do not remove: residual spawn, `harmonize_pending`, `run_harmonize`,
`harmonize_session_residual`, new kinds. Adding is OK; shrinking is not
(design/169g).

Files: `evidence_kinds.py` + Dart mirror, `evidence_floor.py`,
`scripts/check_evidence_floor.py`.

---

## 10. `translate_pending` vs `harmonize_pending`

| | `translate_pending` (existing) | `harmonize_pending` (new) |
|--|--------------------------------|---------------------------|
| Meaning | KO empty; needs draft backfill | Draft present; needs 재감수 |
| Trigger | open `needs_translate_backfill` | ingest residual exit |
| Driver | `_spawn_open_translate_backfill` | `_run_harmonize_residual` |
| Client | translate poll | harmonize banner poll |

Invariant: with residual on, ingest finishes draft → open backfill should
not also claim full translate work. Both true at once is a bug.

---

## 11. File checklist

| File | Chip | Change |
|------|------|--------|
| `llm/translate_section.py` | 1,3 | `run_harmonize`, units, extract section, residual + count |
| `api/app.py` | 2,3,4 | flag at enrich, task, residual runner, list/open fields |
| `llm/ingest_jobs_gcs.py` | 0,3b | flags through public_job; optional residual lease |
| `llm/progressive_writer.py` | 3 | reuse |
| `llm/evidence_kinds.py` + Dart | 6 | new kinds |
| `llm/evidence_floor.py` | 6 | freeze markers |
| paper cache / papers serializer | 2–4 | persist + list fields |
| `mobile/.../harmonize_residual.dart` | 5 | UI state |
| `library_controller.dart` / `library_screen.dart` | 5 | poll + subtitle |
| paper models | 4–5 | parse fields |
| tests | each chip | unit + phase + enrich flag |
| this doc | — | SoT |

---

## 12. Runtime sequence

```text
[Upload / ingest]
  enrich(run_harmonize=False) → draft + digests
  done=true, percent=100, harmonize_pending=true
  mobile: 「재감수 0/N 중」 + enqueueFigureHydrate (169n)

[Server _run_harmonize_residual]
  harmonize_residual_start
  ProgressiveWriter + harmonize_session_residual
    on_item stage=harmonize → session_patch_ko / paper_cache
  update harmonize_done
  pending=false; residual_done | residual_partial

[Mobile poll]
  done==total → hide label
  reader open → merge patched KO
```

---

## 13. Implementation order

```text
0  schema · env · this doc
1  enrich split + parity tests (flag off == today)
2  ingest run_harmonize=False + pending + 100% return
3  residual task + writer reuse + evidence
3b resume / residual lease
4  list + open fields
5  mobile banner poll
5b reader merge / optional banner
6  floor · version bump · live measure
   (ingest terminal ts vs residual done ts; 재감수 wall clock off critical path)
```

---

## 14. Deploy / version

When implementing: bump `app.py` version, `/api/status` version, and
`mobile/pubspec.yaml` together; `pre_deploy_guard.py` + evidence floor
green; then Cloud Run deploy per design/155. APK after mobile chip 5.

---

## 15. One-line SoT

**Cut** at `translate_section` harmonize pool; **attach** with
`app.py` `create_task(_run_harmonize_residual)` after durable draft+digest;
**show** via library poll twin of 169n; **swap** KO with existing
`_on_item` + `ProgressiveWriter` + `session_patch_ko`.
