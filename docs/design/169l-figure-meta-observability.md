# 169l — Figure meta observability (PNG 링크 · save boundary)

**Parent:** [169-agent-evidence-bus.md](169-agent-evidence-bus.md) · [169i-artifact-transfer-ledger.md](169i-artifact-transfer-ledger.md) · [169k-observability-pull-verdicts.md](169k-observability-pull-verdicts.md)  
**Sibling:** [168-audit-checklist.md](168-audit-checklist.md) (G1 figure window) · [168-ingest-observability.md](168-ingest-observability.md)  
**Status:** **draft** — L0 verdict engine shipped (0.3.136+); L1 save emit pending  
**UI:** 없음 (에이전트 pull·verdict·track만)

---

## 0. Why now (live 2026-09-02)

| 관측 | 의미 |
|------|------|
| **번역 품질 OK** | `ko_sentence_n=286`, `ko_figure_n=14` — 문장·캡션 번역 완료 |
| **읽기 UI stuck** | 「그림 불러오는 중…」 — `figureCount>0` + `imageSrc` empty (design/129) |
| **gen 2→3 회귀** | `artifact_derive` gen 3 @ translate save 직후 `figure_data_url_miss` **reason=`bad_file_rel`** |
| **window 전부 empty** | `figure_window_empty` `empty_n=3`, mobile `figure_window_res empty_n=3` |
| **preserve_miss 없음** | `figure_preserve_miss` 미발화 — `forced && prior_png==0` 조건만 (169i I3 partial) |
| **vision_write_figure 없음** | gen 3 save 후 `artifact_observe activity=vision_write_figure` 없음 → preserve meta 실패 |
| **169k K4 pending** | `translate_ok_figure_broken` 자동 verdict 없음 — GCS `session.json` 수동 확인 필요 |

**교훈:** 169g/h/j/k는 **translate 시간축**은 잡지만, **figure PNG meta 링크**는 save boundary에서 깨져도 **읽기 요청 전까지** evidence가 없다. `ko_figure_n==figure_n`은 **캡션 KO**이지 **PNG 서빙 가능**이 아니다.

---

## 1. Locked judgments

| # | Judgment |
|---|----------|
| L-J1 | 사용자 진단 UI 금지 (169 P2). verdict = **스크립트 stdout + JSONL** only |
| L-J2 | 본문·캡션 전문·PNG bytes 금지 (169 P5). **figure id·locator·hash16·건수·reason enum** only |
| L-J3 | **169i I3/I4 칩을 대체하지 않음** — figure ledger·patch gen은 169i/169k 유지; 169l은 **meta completeness + verdict** |
| L-J4 | **save boundary emit** — `bad_file_rel`은 읽기(증상) 센서; **원인**은 `save_paper_session` 직후 `figure_meta_write` |
| L-J5 | `translate_ok` 와 `figure_read_ok` 는 **분리 verdict** — 번역 ship ≠ 읽기 ship |
| L-J6 | `ingest_integrity` violation → evidence bus 승격 (log-only 종료) |
| L-J7 | Floor = **kind 추가만** (169g/169i I6). 기존 figure kind 삭제 금지 |
| L-J8 | 에이전트 폰 화면: **screencap png 우선**, uiautomator dump는 보조 (dump≠png 시 dump 무시) |

---

## 2. Problem — figure lifecycle vs evidence holes

### 2.1 Pipeline hops

```text
[1] PDF ingest        → Figure 객체 (image_src data-URL or lazy stub)
[2] vision_write      → figures/*.png + session.json figures[].file
[3] gcs_upload        → GCS figures/
[4] translate         → caption_ko (PNG bytes often untouched)
[5] translate_save    → gen↑ session.json re-write (prior PNG preserve)
[6] cache_open        → open_ko_summary
[7] figure_window     → lazy PNG fetch → mobile mergeFigureWindow
```

### 2.2 Incident map (`4ba79db36946`)

| Hop | Result | Evidence today |
|-----|--------|----------------|
| 1 | OK (`figure_n=14`) | `open_ko_summary.figure_n` |
| 2 | OK (gen 2) | 23:28–23:39 `figure_window_res empty_n=0` |
| 3 | OK (indirect) | `artifact_transfer gcs_*` |
| 4 | OK | `ko_figure_n=14` |
| 5 | **FAIL meta link** | `artifact_derive gen=3` only; no `vision_write_figure` |
| 6 | Misleading OK | `ko_figure_n=14` — **no `figure_file_rel_n`** |
| 7 | FAIL | `bad_file_rel`, `figure_window_empty` |

**Root hop:** **[5] translate_save** — not PDF extract, not caption translate.

### 2.3 `bad_file_rel` semantics

`paper_cache.figure_data_url_with_reason`: `figures[].file` missing or not `figures/…` prefix → PNG on disk/GCS may exist but **meta pointer gone**.

### 2.4 Why existing sensors miss it

| Sensor | Gap |
|--------|-----|
| `figure_preserve_miss` | Only `forced reanalyze && prior_png==0` |
| `check_figure_blobs` (T6) | Skips rows with no `file` → `checked==0` |
| `check_fig_meta` (T9) | Count only, not `file` presence |
| `figure_data_url_miss` | Read-time symptom, no figure id in details |
| `open_ko_summary` | No `figure_file_rel_n` / `session_gen` |
| K4 `evidence_verdict.py` | Not implemented |

---

## 3. Architecture

```text
                    save_paper_session (paper_cache.py)
                              │
              ┌───────────────┼───────────────┐
              ▼               ▼               ▼
    figure_meta_write   ingest_integrity   artifact_derive
    (new)               → bus violation    (existing gen)
              │               (T11 new)
              └───────────────┬───────────────┘
                              ▼
                    evidence/events.jsonl
                              │
              ┌───────────────┴───────────────┐
              ▼                               ▼
    scripts/pull_evidence.py          cache_open open_ko_summary
              │                       (+ figure_file_rel_n, gen)
              ▼
    llm/evidence_verdict.py (new, pure)
              │
    scripts/evidence_verdict.py (new CLI)
              │
              ▼
    scripts/track_translate.py ── merge translate + figure verdicts
```

**Layers:**

| Layer | Module | Role |
|-------|--------|------|
| Collection | `evidence_bus`, `paper_cache`, `app.py`, `ingest_integrity` | Emit at save/open/read |
| Integrity | `ingest_integrity` T11 + bus | Invariant → pull-visible |
| Detection | `evidence_verdict.py`, `track_verdict.py` | Rule-based RCA |

---

## 4. New evidence kinds

All appended to `evidence_floor.py` `FROZEN_KINDS` on implement. Dart mirror in mobile only if client emits.

### 4.1 `figure_meta_write`

**When:** `save_paper_session()` after `session.json` + figure meta rows written (every save).

**Emit:** `paper_cache.py` end of save loop.

```json
{
  "kind": "figure_meta_write",
  "source": "server",
  "severity": "boundary",
  "cache_id": "4ba79db36946",
  "ok": false,
  "code": "figure_meta_incomplete",
  "details": {
    "gen": 3,
    "activity": "translate_save",
    "session_fig_n": 14,
    "fig_meta_n": 14,
    "file_rel_n": 0,
    "prior_png_n": 14,
    "decoded_src_n": 0,
    "preserved_n": 0,
    "missing_file_n": 14,
    "sample_missing_ids": ["fig-0001", "fig-0002", "fig-0003"]
  }
}
```

| Field | Meaning |
|-------|---------|
| `session_fig_n` | `len(session.figures)` |
| `fig_meta_n` | `len(fig_meta)` persisted rows |
| `file_rel_n` | rows with `file` starting `figures/` |
| `prior_png_n` | `len(prior_fig_bytes)` before rmtree |
| `decoded_src_n` | figures written from inline data-URL |
| `preserved_n` | rows that got `file_rel` from decode or prior |
| `missing_file_n` | `session_fig_n - file_rel_n` |
| `sample_missing_ids` | up to 8 figure ids (P5) |

**ok:** `file_rel_n == session_fig_n` when `session_fig_n > 0`.

**activity enum:** `ingest_store` \| `translate_save` \| `reanalyze` \| `merge_session`.

### 4.2 `figure_meta_regress`

**When:** new save vs prior meta: `prev_file_rel_n > new_file_rel_n`.

```json
{
  "kind": "figure_meta_regress",
  "ok": false,
  "code": "file_rel_regress",
  "details": {
    "gen_prev": 2,
    "gen_new": 3,
    "prev_file_rel_n": 14,
    "new_file_rel_n": 0
  }
}
```

### 4.3 `figure_preserve_skip`

**When:** `session_fig_n > 0` and `preserved_n == 0` but **not** covered by `figure_preserve_miss` (e.g. translate save, prior existed, forced=0).

```json
{
  "kind": "figure_preserve_skip",
  "ok": false,
  "details": {
    "reason": "prior_bytes_unused",
    "prior_png_n": 14,
    "session_fig_n": 14,
    "forced": 0,
    "activity": "translate_save"
  }
}
```

**Do not widen** `figure_preserve_miss` conditions — keep I3 semantics.

### 4.4 `ingest_integrity_violation`

**When:** any `ingest_integrity.Violation` emitted (was log-only).

```json
{
  "kind": "ingest_integrity_violation",
  "ok": false,
  "code": "figure_file_rel_missing",
  "details": {
    "invariant": "T11",
    "figure_n": 14,
    "file_rel_n": 0,
    "missing_n": 14
  }
}
```

### 4.5 Extensions to existing kinds

**`open_ko_summary.details` add:**

| Field | Type | Meaning |
|-------|------|---------|
| `figure_file_rel_n` | int | meta rows with valid `figures/…` file |
| `session_gen` | int | session.json gen at open |
| `session_hash16` | str | optional, 169i chain |

**`figure_window_empty.details` add:**

| Field | Meaning |
|-------|---------|
| `empty_reasons` | `{ "bad_file_rel": 3 }` aggregate |
| `sample_empty_ids` | up to 3 figure ids |

**`figure_data_url_miss.details` add (ops/evidence):**

| Field | Meaning |
|-------|---------|
| `figure_id` | id attempted (P5: id only) |

**Mobile `figure_window_res.details` add:**

| Field | Meaning |
|-------|---------|
| `server_empty_reasons` | passthrough from API when present |

---

## 5. Integrity — invariant T11

**File:** `llm/ingest_integrity.py`

```python
def check_figure_file_rel(figures: list) -> list[Violation]:
    """T11 — when figure_n>0, every meta row must have figures/ file rel."""
```

| Code | Condition |
|------|-----------|
| `figure_file_rel_missing` | `file_rel_n < figure_n` and `figure_n > 0` |

**Call sites:**

- `save_paper_session` after fig_meta built
- `audit_cache()` on open/reanalyze audit
- optional: post `gcs_download_session`

T6 remains (blob exists when `file` set). T11 covers **file field missing** — incident class.

---

## 6. Verdict catalog (169k K4 extension)

**Pure functions:** `src/sentence_reading/llm/evidence_verdict.py`  
**CLI:** `scripts/evidence_verdict.py`

Join keys (priority): `cache_id` → `details.gen` → `job_id` → `handoff_id` → `trace_id`.

| Verdict | Rule (summary) |
|---------|----------------|
| `figure_meta_broken` | `figure_file_rel_n < figure_n` on latest open **OR** last `figure_meta_write ok=false` **OR** `bad_file_rel` within 5m of open |
| `figure_meta_regress` | any `figure_meta_regress` event |
| `preserve_gap` | 169i §5 **OR** `figure_preserve_skip` **OR** regress with `prev_file_rel_n>0` |
| `figure_read_stuck` | `figure_n>0` and last 3× `figure_window_res.empty_n>0` within 10m |
| `translate_ok_figure_broken` | `progress_view pct>=100` (or job done) **AND** `figure_meta_broken` |
| `figure_fetch_stall` | `figure_window_req` without ok res >30s (when req kind live) |

**169k separation (L-J5):**

- Translate verdicts stay in `track_verdict.py` (`accept_169j_title`, `zombie_worker`, …).
- Figure verdicts from `evidence_verdict.py` — merged in track stdout under `--- figure verdicts ---`.

### 6.1 Incident replay acceptance

Given pulled evidence for `4ba79db36946` (2026-09-02 00:55Z):

- MUST emit: `translate_ok_figure_broken`, `figure_meta_broken`
- SHOULD emit: `preserve_gap` or `figure_meta_regress`
- MUST NOT require GCS session.json read for verdict

---

## 7. Implementation phases

**Order:** L0 → L1 → L2 → L3. Each phase = version bump + floor append + tests.

| Phase | Scope | Files |
|-------|-------|-------|
| **L0** | Verdict engine + CLI (emit 없이 replay) | `llm/evidence_verdict.py`, `scripts/evidence_verdict.py`, `tests/test_evidence_verdict_figure.py`, `track_translate.py` merge — **0.3.136+ shipped** |
| **L1** | Save boundary emit | `paper_cache.py` (`figure_meta_write`, `figure_meta_regress`, `figure_preserve_skip`) |
| **L2** | Integrity bus + T11 | `ingest_integrity.py`, `open_ko_summary` fields in `app.py`, `evidence_kinds.py`, `evidence_floor.py` |
| **L3** | Read path enrich | `app.py` `session_figures_window` empty_reasons; mobile `figure_window_res`; optional `figure_window_req` |
| **L4** | Agent screencap-first | `track_translate.py`, `.cursor/rules/` agent phone rule |

**169i I3 completion** (vision_write_figure / gcs figure sample) remains in [169i-artifact-transfer-ledger.md](169i-artifact-transfer-ledger.md) — 169l L1 does not block I3 but complements it.

### L0 acceptance

- [ ] `python scripts/evidence_verdict.py --cache-id 4ba79db36946 --since 6h` → `translate_ok_figure_broken`
- [ ] `tests/test_evidence_verdict_figure.py` synthetic JSONL
- [ ] `track_translate.py` prints figure verdict section

### L1 acceptance

- [ ] translate complete save → `figure_meta_write` with `ok=false` **before** first `figure_window_empty` on same cache
- [ ] gen 2→3 with file rel drop → `figure_meta_regress`
- [ ] floor includes new kinds; delete → `check_evidence_floor.py` fail

### L2 acceptance

- [ ] T11 violation appears in `pull_evidence` as `ingest_integrity_violation`
- [ ] `open_ko_summary` includes `figure_file_rel_n`, `session_gen`

### L3 acceptance

- [ ] `figure_window_empty.details.empty_reasons.bad_file_rel >= 1` on incident replay
- [ ] mobile res includes server reason passthrough

---

## 8. Agent workflow

### 8.1 RCA SOP (figure 「불러오는 중」)

1. `python scripts/track_translate.py` (**screencap png first**, L-J8)
2. `python scripts/evidence_verdict.py --cache-id CACHE --since 6h`
3. If `figure_meta_broken` / `translate_ok_figure_broken`:
   - hop = **save boundary** (`paper_cache.save_paper_session`), not PDF extract
   - join: last `figure_meta_write` or `artifact_derive` gen vs `open_ko_summary.session_gen`
4. If only `figure_read_stuck` without meta broken → network/session 404 path
5. Patch target: preserve path in `paper_cache.py` (prior_fig_bytes → fig_meta.file)

### 8.2 Deploy gate (optional post-L0)

```bash
python scripts/evidence_verdict.py --since 30m --fail-on translate_ok_figure_broken,figure_meta_broken
```

After live smoke upload; non-zero → hold deploy.

### 8.3 Track stdout format

```text
--- translate verdicts ---
tracking; accept_169j_title

--- figure verdicts ---
translate_ok_figure_broken; figure_meta_broken; preserve_gap

--- last figure events ---
00:55:13 artifact_derive gen=3
00:55:37 figure_data_url_miss bad_file_rel
00:55:44 figure_window_empty empty_n=3
```

---

## 9. Cost · sampling

| Event | Rate | Notes |
|-------|------|-------|
| `figure_meta_write` | 1 per save | ~translate end + reanalyze |
| `figure_meta_regress` | rare | only on decrease |
| `figure_preserve_skip` | rare | failure path |
| `ingest_integrity_violation` | per violation | T11 on save/open |
| 169i figure transfer | unchanged | fail full, success sample |

P10 rate limit: duplicate `figure_meta_write` same gen within 60s → sample.

---

## 10. Non-goals

- User-facing 「그림 진단」 UI or Settings tile
- PNG/PDF bytes in evidence
- Full per-figure success transfer log every save
- Replacing 169h checkpoints with artifact kinds
- Auto-repair (re-write meta from GCS) — separate product chip
- Datadog / admin dashboard

---

## 11. Related

- [169k-observability-pull-verdicts.md](169k-observability-pull-verdicts.md) — K4 parent; 169l = K4 figure pack + L1 emit
- [169i-artifact-transfer-ledger.md](169i-artifact-transfer-ledger.md) — §5 `preserve_gap`, I3 figure ledger
- [168-audit-checklist.md](168-audit-checklist.md) — G1 figure window
- [155-deploy-live-guard.md](155-deploy-live-guard.md) — floor + version bump
