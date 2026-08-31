# 168 — Ingest · open · figures observability (과잉 계측)

**Version:** (구현 시 bump — 예: 0.3.112)  
**Depends:** [08](08-errors.md) · [05](05-session-store.md) · [19](19-pipeline-cache.md) · [45](45-progressive-translate.md) · [71](71-mobile-upload-resume.md) · [106](106-ingest-quality-timeout.md) · [107](107-ingest-job-reclaim.md) · [108](108-fail-closed-no-cache.md) · [129](129-lazy-figure-open.md) · [130](130-cloud-error-logs.md) · [134](134-ingest-upload-hang.md) · [158](158-ingest-idle-timeout-resume-button.md) · [167](167-debone-quality-guards.md)  
**Blocks:** Ni/Cu·acsanm 류 **버그 수정 PR** (본 칩 계측·불변식 먼저)

## 무엇인가

분산 ingest·부분 저장·세션 만료·좀비 job 환경에서 **실패를 성공으로 덮지 않기 위해**,  
경계마다 **구조화 이벤트 + 일관성 검증 + stall 탐지**를 **의도적으로 과하게** 깐다.

| 포함 | 미포함 (이번 칩) |
|------|------------------|
| 이벤트 스키마 · correlation ID · phase machine | Datadog / Prometheus / Sentry |
| `consistency_violation` · `ingest_phase` · `integrity_errors[]` | 사용자-facing 새 UI 대시보드 (admin API 확장만) |
| silent catch 전수 제거 (ingest/open/figures/translate 경로) | ingest 알고리즘 변경 |
| GCS job sweeper · admin stuck-job 조회 | 자동 데이터 수리(merge) |
| 계약 테스트 (terminal 불변식) | |

### 관측 사례 (Ni/Cu MDR · 2026-09-01)

| 지표 | job (GCS) | index | session.json | 폰 UX |
|------|-----------|-------|--------------|-------|
| terminal | `done:false`, 90%, `서론 번역 10/11` | `ingest_status:ok` | 243문장·243 KO·12 fig meta | 「분석 멈춤」504 |
| figure_count | — | **0** | **12** | 「이미지 없음」 |
| 원인 추정 | worker 사망 / lease 만료, job 미종료 | `save_paper_session` fig_meta≠session figures | PNG GCS 있음 | prefetch **silent catch** |

**교훈:** GCS에 데이터가 있다 ≠ 성공. **job · index · session · blob · UI** 다섯 층이 일치할 때만 terminal.

---

## Product (locked)

| Rule | Detail |
|------|--------|
| **실패≠성공** | `ingest_status:ok` 는 **terminal 불변식 통과** 후에만 |
| **partial 명시** | `ingest_phase` ∈ `uploading` \| `reading_ready` \| `translate_pending` \| `complete` \| `error` |
| **과잉 계측** | 경계마다 이벤트 1건 이상; silent catch **금지** (ingest/open/figures/translate) |
| **correlation** | 모든 이벤트에 `trace_id` + (`job_id` \| `cache_id`) + `deploy_git_sha` |
| **불일치=이벤트** | warning 문자열만으로는 부족 — `consistency_violation` cloud log + job/session 필드 |
| **stall 이중 탐지** | 클라이언트 hang(130/134/158) **+** 서버 lease/translate stall |
| **수정 순서** | 168 계측 PR → 로그로 원인 확인 → 버그 PR (덮기식 패치 금지) |

---

## Correlation & event schema

### 필수 필드 (JSONL `ops_events/` 또는 `error_logs` 확장)

```json
{
  "ts": "ISO8601",
  "kind": "ingest_phase_transition | consistency_violation | figure_window_empty | translate_stalled | worker_lost | merge_session_richer | ...",
  "trace_id": "tr_…",
  "job_id": "job_…",
  "cache_id": "…",
  "session_id": "ses_…",
  "owner_uid": "…",
  "content_hash": "sha256…",
  "deploy_git_sha": "…",
  "stage": "translate",
  "percent": 90,
  "message": "서론 번역 10/11",
  "details": { }
}
```

- `owner_uid`: `sanitize_uid` — 본문에 토큰/원문 PDF 금지 ([08](08-errors.md) · [130](130-cloud-error-logs.md)).
- `details`: 수치만 (counts, durations, blob bytes, http status) — 문장 원문 금지.

### `trace_id` 발급

| 시작점 | trace_id |
|--------|----------|
| `POST /api/ingest` · `POST …/reanalyze` | 새 UUID → job에 저장 |
| `POST …/open` | `cache_id` + `deploy_git_sha` prefix 또는 client header `X-Asr-Trace` |
| 모바일 poll | job의 `trace_id` 유지; breadcrumb 링버퍼에 적재 |

---

## Phase machine (ingest)

```
upload → extract → quality → vision → debone → figures → ready → translate → save → shadowing → terminal
                                              ↘ reading_ready (partial, design/45)
```

| Phase | `job.done` | `ingest_status` (index) | `translate_pending` |
|-------|------------|-------------------------|---------------------|
| `uploading`…`ready` | false | `processing` (신규) | false |
| `reading_ready` | false | `partial` | true |
| `translate` | false | `partial` | true |
| `complete` | true | `ok` | false |
| `error` | true | `error` | — |

**불법 전환 예:** `translate` 90%에서 worker 사망 → GCS session 243 KO 있음 + `job.done=false` + index `ok` → **`consistency_violation`**.

---

## Terminal invariants (불변식 — pytest + save 시 검증)

`T1`…`Tn` 실패 시 **`_finish_job` 금지**, index `ok` 금지.

| ID | 불변식 |
|----|--------|
| T1 | `job.done=true` ⇒ `job.error` 없음 |
| T2 | `job.done=true` ⇒ `result.cache_id` 비어 있지 않음 ([108](108-fail-closed-no-cache.md)) |
| T3 | `index.ingest_status=ok` ⇒ `job.done=true` (해당 content_hash 최신 job) |
| T4 | `index.figure_count` == `len(session.figures)` |
| T5 | `index.sentence_count` == `len(session.sentences)` |
| T6 | session `figures[].file` 마다 GCS/blob 존재·`size>0` (또는 `lazy_figures` stub이면 `file`만 있고 blob lazy OK — **단, index count는 meta 기준**) |
| T7 | `ingest_phase=complete` ⇒ `translate_pending=false` (번역 opt-in 시) |
| T8 | partial save (`_job_publish_partial`) ⇒ `ingest_status≠ok` |
| T9 | `save_paper_session` 후 `fig_meta` len vs `session.figures` len — 불일치 시 `figures_meta_dropped` violation |
| T10 | `upload_paper_cache` merge richer remote ⇒ `merge_session_richer` 이벤트 필수 |

---

## 모듈 (구현 예정)

| 파일 | 역할 |
|------|------|
| `llm/ops_events.py` | **신규** — GCS JSONL append, redact, rate limit |
| `llm/ingest_integrity.py` | **신규** — T1–T10 검증, violation 반환 |
| `llm/ingest_jobs_gcs.py` | phase·trace_id·integrity_errors on job JSON |
| `api/app.py` | phase transition hooks, stall detector, sweeper hook |
| `cache/paper_cache.py` | `save_paper_session` 전/후 audit |
| `llm/papers_gcs.py` | `upload_paper_cache` merge audit |
| `mobile/…/library_controller.dart` | prefetch/poll breadcrumb + report |
| `mobile/…/error_reporter.dart` | `kind` 확장 |
| `tests/test_ingest_integrity.py` | **신규** — 불변식 |
| `tests/test_ops_events.py` | **신규** |

Kill: `ASR_OPS_EVENTS=0` (default on).

---

## Stall detection (서버)

| 경로 | 조건 | action |
|------|------|--------|
| ingest lease | `lease_until` 만료 ∧ `done=false` ∧ `cancel_requested=false` | `worker_lost` 이벤트; sweeper가 `error` 설정 (owner poll 없어도) |
| translate progress | `stage=translate` ∧ `message`/`percent` N초 무변경 | `translate_stalled` + job `error` (N=300 default) |
| figure window | `ok=true` ∧ `n≥1` ∧ all `image_src` empty | `figure_window_empty` + log ids |
| open translate backfill | task 예외 | 기존 `log.warning` → **ops event** |

Env: `ASR_INGEST_STALL_SEC`, `ASR_INGEST_SWEEPER_SEC` (background, Cloud Run cron or startup loop).

---

## Admin / ops

| API (admin) | 용도 |
|-------------|------|
| `GET /api/ops/ingest/jobs/stuck` | `done=false` ∧ lease 만료 목록 |
| `GET /api/ops/cache/{id}/integrity` | T1–T10 리포트 (read-only) |
| 기존 `GET /api/errors/admin` | `kind` 필터 · `job_id`/`cache_id` 검색 |

---

# 전수조사 — 실패 경로 맵

아래 표는 **168 구현 전 baseline**. `🔇` = silent catch / 조용한 실패. `⚠` = 부분 성공이 성공처럼 보일 수 있음.

## A. Ingest upload → job create

| # | 위치 | 함수/경로 | 성공 조건 | 실패·partial | 현재 탐지 | 168 계측 |
|---|------|-----------|-----------|--------------|-----------|----------|
| A1 | `api/app.py` | `POST /api/ingest` | `job_id` 반환 | 4xx/5xx | HTTP | `ingest_started` + trace_id |
| A2 | `ingest_jobs_gcs.py` | `save_ingest_job` | GCS write | 🔇 fail-soft False | 없음 | push reason + size |
| A3 | `ingest_jobs_gcs.py` | `save_ingest_upload` | blob ok | 🔇 | 없음 | bytes + hash |
| A4 | mobile `client.dart` | `uploadPdf` → `pollIngestJob` | `done`+`cache_id` | 504 idle / 422 | 504 메시지 | breadcrumb + report |
| A5 | mobile `library_controller.dart` | `_beginIngestHang` | progress | 3m hang | ErrorReporter | stage snapshot |
| A6 | `app.py` | `_persist_job` | memory+GCS | throttle skip | 없음 | should_push reason |

## B. Extract · quality · vision · debone

| # | 위치 | 함수/경로 | 성공 조건 | 실패·partial | 현재 탐지 | 168 계측 |
|---|------|-----------|-----------|--------------|-----------|----------|
| B1 | `app.py` | `_run_ingest_job_body` extract | text non-empty | warnings | warnings[] | phase + duration |
| B2 | `vision_ocr.py` | `extract_with_quality` | pages done | timeout | job message | per-page event |
| B3 | `debone.py` | `debone_sentences` | sentences>0 | chunk `[]` ⚠ | ingest_quality [167] | chunk_fail count |
| B4 | `debone_quality.py` | coverage/grounding | flags | partial debone ⚠ | session flags | violation if coverage<floor |
| B5 | `app.py` | `_save_payload` checkpoint | GCS payload | 🔇 | reclaim only | checkpoint_saved |

## C. Figures (ingest-time)

| # | 위치 | 함수/경로 | 성공 조건 | 실패·partial | 현재 탐지 | 168 계측 |
|---|------|-----------|-----------|--------------|-----------|----------|
| C1 | ingest pipeline | figure extract/slot | `session.figures` | empty ⚠ `no_embedded_figures` | warning | T9 prep |
| C2 | `paper_cache.py` | `save_paper_session` fig loop | PNG on disk | **skip if no data-URL** ⚠ | 없음 | **T9 violation** — meta dropped |
| C3 | `papers_gcs.py` | `upload_paper_cache` figures | blob upload | skip missing local 🔇 | 없음 | per-fig ok/miss |
| C4 | `papers_gcs.py` | `_merge_session_meta_richer` | merge | remote richer ⚠ | 없음 | **merge_session_richer** event |

## D. Translate

| # | 위치 | 함수/경로 | 성공 조건 | 실패·partial | 현재 탐지 | 168 계측 |
|---|------|-----------|-----------|--------------|-----------|----------|
| D1 | `app.py` | `_job_publish_partial` | cache readable | `done=false` ⚠ | translate_pending | **ingest_phase=reading_ready** |
| D2 | `translate_section.py` | `enrich_session_translations` | KO filled | stall mid-section | job message only | per-section tick + **stall** |
| D3 | `app.py` | `_tr_progress` / `_on_item` | message update | 10/11 stop ⚠ | poll idle 5m | server stall detector |
| D4 | `app.py` | `_open_translate_backfill_task` | KO backfill | 🔇 log.warning | 없음 | event + integrity |
| D5 | mobile | `_maybeStartTranslatePoll` | translate done | 24×8s 후 **🔇 stop** | 없음 | **translate_poll_exhausted** report |
| D6 | `translate_google.py` | batch API | KO rows | 🔇 fallback | 없음 | provider + latency |

## E. Save · terminal · index

| # | 위치 | 함수/경로 | 성공 조건 | 실패·partial | 현재 탐지 | 168 계측 |
|---|------|-----------|-----------|--------------|-----------|----------|
| E1 | `paper_cache.py` | `save_paper_session` | index entry | `fig_meta`⊂figures ⚠ | 없음 | **T4,T5,T9** audit |
| E2 | `paper_cache.py` | index `ingest_status:ok` | always on save | **partial도 ok** ⚠ | 없음 | `partial` vs `ok` |
| E3 | `app.py` | `_finish_job` | `done=true` | 없으면 zombie | client 504 | sweeper |
| E4 | `app.py` | no `_finish_job` on save fail | job open | zombie ⚠ | 없음 | T3 enforce |
| E5 | `papers_gcs.py` | `download_paper_cache` | session.json | partial figures | 없음 | pull summary |
| E6 | `paper_cache.py` | `backfill_references_from_source_pdf` | refs grow | silent improve | 없음 | refs_backfill event |

## F. Open (library)

| # | 위치 | 함수/경로 | 성공 조건 | 실패·partial | 현재 탐지 | 168 계측 |
|---|------|-----------|-----------|--------------|-----------|----------|
| F1 | `app.py` | `cache_open` | sentences>0 | gcs_pull_failed | HTTP | open_ok + warnings |
| F2 | `app.py` | `refresh_paper_for_open` | session local | fail-closed | HTTP | refresh_code |
| F3 | `paper_cache.py` | `load_cached_session(load_images=False)` | meta | missing file | 없음 | figure stub count |
| F4 | `app.py` | `_remember_session` | session_id | LRU evict old | 없음 | cache_id bind log |
| F5 | mobile | `open()` progress gate | indices valid | fail-closed [123] | error string | **progress_mismatch** report |
| F6 | mobile | `open()` hang 45s | session | timeout | open_empty report | keep |
| F7 | `app.py` | translate backfill spawn | async | 🔇 task fail | log.warning | event |

## G. Figures (lazy open / window)

| # | 위치 | 함수/경로 | 성공 조건 | 실패·partial | 현재 탐지 | 168 계측 |
|---|------|-----------|-----------|--------------|-----------|----------|
| G1 | `app.py` | `cache_open` `lazy_figures` | stubs, empty src | by design | 없음 | figure_count in response |
| G2 | `app.py` | `session_figures_window` | data-URL | empty src | 없음 | **figure_window_empty** |
| G3 | `paper_cache.py` | `figure_data_url` | PNG | None 🔇 | 없음 | miss reason (no file/gcs) |
| G4 | `papers_gcs.py` | `ensure_figure_local` | blob | None 🔇 | 없음 | gcs pull ok/fail |
| G5 | mobile | `_prefetchFigureWindow` | merge rows | **🔇 catch all** | UI only | **figure_window_error** report |
| G6 | mobile | `mergeFigureWindow` | imageSrc set | skip empty 🔇 | 없음 | empty row count |
| G7 | `app.py` | session expired + `cache_id` query | reload GCS | 404 | 129 | cache_id fallback metric |

## H. Reanalyze

| # | 위치 | 함수/경로 | 성공 조건 | 실패·partial | 현재 탐지 | 168 계측 |
|---|------|-----------|-----------|--------------|-----------|----------|
| H1 | `app.py` | `POST …/reanalyze` | new job_id | same as ingest | same | trace_id link `parent_cache_id` |
| H2 | mobile | `reanalyzePaper` | poll terminal | 504 ⚠ partial GCS | error banner | **no resume for reanalyze** — 168: reanalyze draft path |
| H3 | `app.py` | reanalyze body | overwrites cache | rmtree wipes figs ⚠ | 없음 | pre-save integrity |

## I. Shadowing chunks

| # | 위치 | 함수/경로 | 성공 조건 | 실패·partial | 현재 탐지 | 168 계측 |
|---|------|-----------|-----------|--------------|-----------|----------|
| I1 | `app.py` | shadowing stage 99% | plan GCS | exception → warning | 폰 메시지 | event |
| I2 | mobile | `ensureShadowingChunks` | chunks | error string | partial | report kind |

---

## Silent catch 우선 제거 목록 (P0)

| P | 파일:대략적 위치 | 168 동작 |
|---|------------------|----------|
| P0-1 | `library_controller._prefetchFigureWindow` | catch → `ErrorReporter` + kind |
| P0-2 | `library_controller._maybeStartTranslatePoll` exhausted | report `translate_poll_exhausted` |
| P0-3 | `library_controller._syncCursor` | report soft (cursor drift) |
| P0-4 | `figure_data_url` / `ensure_figure_local` None | ops event with reason enum |
| P0-5 | `save_paper_session` fig skip loop | T9 violation before index write |
| P0-6 | `upload_paper_cache` merge | `merge_session_richer` event |
| P0-7 | `_open_translate_backfill_task` except | ops event not only log |

---

## 구현 순서 (locked)

1. **168a — schema + `ops_events.py` + status flag** (`ops_events=true`)
2. **168b — `ingest_integrity.py` + T1–T10 tests** (no behavior change, log-only violations)
3. **168c — phase + trace_id on job JSON**; index `ingest_status` `processing`/`partial`/`error`
4. **168d — P0 silent catch → report** (mobile + server)
5. **168e — sweeper + admin stuck/integrity GET**
6. **168f — 버그 수정 PR** (로그로 확인된 항목만: 예. T9 fig_meta, reanalyze resume)

---

## `/api/status` 핀 (구현 후)

```json
{
  "ops_events": true,
  "ingest_integrity": true,
  "ingest_phase_machine": true,
  "ingest_stall_detector": true,
  "ingest_status_partial": true
}
```

---

## Device pin (E2E)

- Live `/api/status`: `ops_events=true` · `ingest_integrity=true`
- 의도적 T9 violation 스테이징 → admin `consistency_violation` 1건
- figure window empty → `figure_window_empty` 1건 (모바일 report)
- ingest stall (staging slow translate) → `translate_stalled` on server before client 504

---

## Version

**0.3.112** (계측 랜드마크; 기능 수정은 168f 이후 개별 bump)

---

## 체크리스트 (파일·함수 단위)

전수조사 **124 체크포인트** — [168-audit-checklist.md](168-audit-checklist.md)
