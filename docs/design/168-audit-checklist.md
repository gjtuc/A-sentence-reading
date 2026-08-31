# 168 — 전수조사 체크리스트 (파일·함수 단위)

**Parent:** [168-ingest-observability.md](168-ingest-observability.md)  
**용도:** 구현·리뷰 시 **한 줄씩** 체크. `🔇`= silent catch / 조용한 실패. `⚠`= partial이 성공처럼 보일 수 있음.

**컬럼:** `Pri` = P0(즉시) / P1(168e) / P2(168f 이후) · `Ph` = 168a…f

---

## 범례 — 이벤트 kind (계획)

| kind | 의미 |
|------|------|
| `ingest_started` | job 생성 |
| `ingest_phase_transition` | stage/phase 변경 |
| `consistency_violation` | T1–T10 위반 |
| `figure_window_empty` | ok인데 image_src 전부 빈 |
| `figure_window_error` | window HTTP/타임아웃 |
| `figure_blob_miss` | GCS/로컬 PNG 없음 |
| `translate_stalled` | 서버: translate N초 무변경 |
| `translate_poll_exhausted` | 모바일: open 번역 poll 소진 |
| `worker_lost` | lease 만료 + done=false |
| `merge_session_richer` | upload 시 remote 병합 |
| `checkpoint_saved` | ingest payload checkpoint |
| `open_ok` / `open_fail` | cache_open |
| `progress_mismatch` | 저장 인덱스 vs counts |
| `refs_backfill` | PDF references 재추출 |
| `ingest_gcs_push` / `ingest_gcs_skip` | job GCS push |

---

## A. Ingest 시작 · job 생성 · poll

| ID | 파일 | 함수 / 라우트 | 성공 | 실패·partial | 🔇 | 지금 | kind | Inv | Pri | Ph |
|----|------|---------------|------|--------------|-----|------|------|-----|-----|-----|
| A1.1 | `api/app.py` | `POST /api/ingest` | `job_id`, `content_hash` | 4xx rate limit, auth | | HTTP | `ingest_started` | | P0 | a |
| A1.2 | `api/app.py` | `_persist_job` | memory+GCS | throttle skip push | ⚠ | 없음 | `ingest_gcs_push` / `skip` | | P0 | a |
| A1.3 | `llm/ingest_jobs_gcs.py` | `save_ingest_job` | True | False | 🔇 | 없음 | `ingest_gcs_push` | | P0 | a |
| A1.4 | `llm/ingest_jobs_gcs.py` | `should_push_job` | push/skip | stale local % | | 없음 | `ingest_gcs_skip` | | P1 | a |
| A1.5 | `llm/ingest_jobs_gcs.py` | `serialize_job_record` | JSON | — | | 없음 | trace_id 필드 추가 | | P0 | c |
| A1.6 | `llm/ingest_jobs_gcs.py` | `stamp_lease` / `lease_expired` | lease 갱신 | 만료 | | reclaim만 | `worker_lost` | | P0 | e |
| A1.7 | `llm/ingest_jobs_gcs.py` | `save_ingest_upload` | blob GCS | False | 🔇 | 없음 | `ingest_upload_saved` | | P1 | a |
| A1.8 | `llm/ingest_jobs_gcs.py` | `try_claim_lease` | token | None | | 없음 | `lease_claim` | | P1 | e |
| A1.9 | `mobile/client.dart` | `uploadPdf` → multipart | job_id | 401, 413 | | HTTP | breadcrumb | | P0 | d |
| A1.10 | `mobile/client.dart` | `pollIngestJob` L1295 | `done`+`cache_id` | 504 idle, 404, 422 | | 504 msg | `poll_timeout` | T2 | P0 | d |
| A1.11 | `mobile/client.dart` | poll 루프 내부 | pct/msg 변경 | 동일 msg 5m | | idle reset | **매 poll breadcrumb** | | P0 | d |
| A1.12 | `mobile/library_controller.dart` | `uploadPdf` L1367 | terminal | hang/504 | | hang+error | `_noteIngestHangProgress` | | P0 | d |
| A1.13 | `mobile/library_controller.dart` | `_beginIngestHang` L256 | progress | 3m hang | | ErrorReporter | `ingest_hang` | | P0 | d |
| A1.14 | `mobile/library_controller.dart` | `_onIngestHangLocal` L232 | abort | zombie risk | | report | `ingest_hang_tripped` | | P0 | d |
| A1.15 | `mobile/library_controller.dart` | `_startStallWatch` L357 | 45s hint | soft stall | | notify | `upload_stall_soft` | | P2 | d |
| A1.16 | `mobile/library_controller.dart` | `resumePendingIfAny` L1164 | done | draft stale | | error | `resume_started` | | P1 | f |
| A1.17 | `mobile/library_controller.dart` | `onAppResumed` L391 | resume poll | — | | partial | `app_resumed` | | P2 | d |
| A1.18 | `api/app.py` | `GET /api/ingest/jobs/{id}` L3573 | public view | 404 | | HTTP | reclaim hook | | P0 | e |
| A1.19 | `api/app.py` | `_reclaim_ingest_job_from_gcs` L3442 | worker restart | fail | 🔇 | 없음 | `reclaim_attempt` | | P0 | e |
| A1.20 | `api/app.py` | `POST …/cancel` L3686 | cancelled | too_late | | HTTP | `ingest_cancelled` | | P2 | a |

---

## B. Ingest body — extract · quality · vision · debone

| ID | 파일 | 함수 / 라우트 | 성공 | 실패·partial | 🔇 | 지금 | kind | Inv | Pri | Ph |
|----|------|---------------|------|--------------|-----|------|------|-----|-----|-----|
| B1.1 | `api/app.py` | `_run_ingest_job_body` L4071 | sentences>0 | empty, encrypted | | warnings | `phase:extract` | | P1 | a |
| B1.2 | `api/app.py` | `_run_ingest_job` L4032 | finally heartbeat | cancel | | 없음 | `ingest_worker_end` | | P1 | a |
| B1.3 | `api/app.py` | `_ingest_lease_heartbeat` L3424 | lease renew | worker die | 🔇 | 없음 | `heartbeat_tick` | | P0 | e |
| B1.4 | `pdf/extract.py` 등 | PDF text extract | text | sparse | | warnings | `extract_done` | | P2 | a |
| B1.5 | `llm/vision_ocr.py` | `extract_with_quality` | pages | timeout 60s | | job msg | `vision_page` | | P1 | a |
| B1.6 | `llm/debone.py` | `debone_sentences` | DeboneResult.ok | chunk `[]` ⚠ | | ingest_quality | `debone_chunk` | | P1 | b |
| B1.7 | `llm/debone.py` | `_process_one_chunk` | sentences | empty return | ⚠ | 167 flags | `debone_chunk_empty` | | P1 | b |
| B1.8 | `llm/debone_quality.py` | `assess_debone_result` | flags | low coverage | | session | `debone_quality` | | P1 | b |
| B1.9 | `api/app.py` | `_job_set` L623 | percent/stage | — | | job JSON | `ingest_phase_transition` | | P0 | c |
| B1.10 | `llm/ingest_jobs_gcs.py` | `save_ingest_payload` | checkpoint | False | 🔇 | reclaim | `checkpoint_saved` | | P1 | a |
| B1.11 | `llm/ingest_jobs_gcs.py` | `load_ingest_payload` / `payload_is_valid` | resume | invalid | | reclaim | `checkpoint_resume` | | P1 | a |
| B1.12 | `llm/ingest_jobs_gcs.py` | `build_checkpoint` / `stamp_checkpoint_on_job` | cp on job | — | | 없음 | `checkpoint_stamped` | | P2 | a |
| B1.13 | `api/app.py` | resume skip `skip_debone` L4138 | jump stage | wrong cp ⚠ | | 없음 | `resume_skip_debone` | | P2 | f |

---

## C. Figures — ingest · save · GCS

| ID | 파일 | 함수 | 성공 | 실패·partial | 🔇 | 지금 | kind | Inv | Pri | Ph |
|----|------|------|------|--------------|-----|------|------|-----|-----|-----|
| C1.1 | `pdf/extract_figures_v2.py` 등 | figure pipeline | `session.figures` | 0 figs ⚠ | | `no_embedded_figures` | `figures_extracted` | | P1 | b |
| C1.2 | `cache/paper_cache.py` | `save_paper_session` L748 | index entry | short title None | | 없음 | `save_started` | | P0 | b |
| C1.3 | `cache/paper_cache.py` | fig loop L825–845 | PNG+meta | **no data-URL → skip** ⚠ | 🔇 | 없음 | `figures_meta_dropped` | **T9** | **P0** | b |
| C1.4 | `cache/paper_cache.py` | `shutil.rmtree` L820 | clean dir | **wipes old PNG** ⚠ | | 없음 | `paper_dir_reset` | | P1 | f |
| C1.5 | `cache/paper_cache.py` | index `new_entry` L920 | `figure_count=len(fig_meta)` | **≠ session.figures** ⚠ | | 없음 | `consistency_violation` | **T4,T9** | **P0** | b |
| C1.6 | `cache/paper_cache.py` | `ingest_status:ok` L934 | always ok | **partial도 ok** ⚠ | | 없음 | phase→status | **T3,T8** | **P0** | c |
| C1.7 | `llm/papers_gcs.py` | `upload_paper_cache` L268 | session+blobs | partial upload | 🔇 | 없음 | `upload_paper_cache` | T6 | P0 | a |
| C1.8 | `llm/papers_gcs.py` | fig loop in upload | blob ok | skip missing 🔇 | 🔇 | 없음 | `figure_blob_upload` | T6 | P0 | a |
| C1.9 | `llm/papers_gcs.py` | `_merge_session_meta_richer` L232 | merged | silent ⚠ | 🔇 | 없음 | `merge_session_richer` | **T10** | **P0** | a |
| C1.10 | `llm/papers_gcs.py` | `download_paper_cache` L384 | session.json | partial figs | 🔇 | 없음 | `download_summary` | | P1 | a |
| C1.11 | `llm/papers_gcs.py` | `ensure_figure_local` L606 | Path | None | 🔇 | 없음 | `figure_blob_miss` | T6 | **P0** | d |
| C1.12 | `cache/paper_cache.py` | `figure_data_url` L130 | data-URL | None | 🔇 | 없음 | `figure_data_url_miss` | | **P0** | d |
| C1.13 | `cache/paper_cache.py` | `load_cached_session` L468 | meta+optional PNG | missing file | | empty src | `load_session` | | P1 | b |
| C1.14 | `api/app.py` | layout_artifacts L4687 | json saved | except 🔇 | 🔇 | 없음 | `layout_artifacts` | | P2 | a |

---

## D. Translate — ingest · open backfill · poll

| ID | 파일 | 함수 | 성공 | 실패·partial | 🔇 | 지금 | kind | Inv | Pri | Ph |
|----|------|------|------|--------------|-----|------|------|-----|-----|-----|
| D1.1 | `api/app.py` | `_job_publish_partial` L652 | result ok ⚠ | `done=false` | ⚠ | translate_pending | `ingest_phase:reading_ready` | **T8** | P0 | c |
| D1.2 | `api/app.py` | early save L4694 + partial L4732 | cache_id | no cache | | 108 | `partial_publish` | T8 | P0 | c |
| D1.3 | `llm/translate_section.py` | `enrich_session_translations` | KO filled | stall mid | | job msg | `translate_section_tick` | | **P0** | e |
| D1.4 | `llm/translate_section.py` | `_tick` / on_progress | message | — | | job msg | `translate_progress` | | P0 | a |
| D1.5 | `api/app.py` | `_tr_progress` L4771 | job update | stop 10/11 ⚠ | | poll idle | **server stall detector** | | **P0** | e |
| D1.6 | `api/app.py` | `_on_item` L4777 | per sentence KO | — | | 없음 | `translate_item` | | P2 | a |
| D1.7 | `api/app.py` | translate except L4832 | warning | `translate_failed:` | | warnings | `translate_failed` | | P0 | a |
| D1.8 | `api/app.py` | `_save_payload` translate cp L4791 | every 8 idx | — | | reclaim | `checkpoint_translate` | | P1 | a |
| D1.9 | `api/app.py` | `_backfill_cached_translations` L3917 | KO fill | gemini miss | | warnings | `backfill_translate` | | P1 | a |
| D1.10 | `api/app.py` | `_open_translate_backfill_task` L3993 | upload | except 🔇 | 🔇 | log.warning | `open_translate_backfill_fail` | | **P0** | d |
| D1.11 | `api/app.py` | `cache_open` spawn backfill L2935 | task start | task fail | 🔇 | 없음 | `open_backfill_spawn` | | P0 | d |
| D1.12 | `llm/translate_google.py` | `translate_batch_en_to_ko` | rows | fallback 🔇 | 🔇 | 없음 | `translate_google_batch` | | P2 | a |
| D1.13 | `llm/translate.py` | `translate_dispatch` | KO | fail | | HTTP | — | | P2 | — |
| D1.14 | `mobile/library_controller.dart` | `_maybeStartTranslatePoll` L784 | KO done | **24×8s stop** 🔇 | 🔇 | 없음 | `translate_poll_exhausted` | T7 | **P0** | d |
| D1.15 | `mobile/library_controller.dart` | poll body L812 `openPaper` | refresh session | catch 🔇 | 🔇 | 없음 | `translate_poll_error` | | P0 | d |
| D1.16 | `mobile/reading_models.dart` | `translatePending` / `hasAnyTranslation` | flags | mismatch ⚠ | | UI | `translate_state` | T7 | P1 | c |
| D1.17 | `api/app.py` | `skip_translate` resume L4140 | skip enrich | stale ⚠ | | 없음 | `resume_skip_translate` | | P2 | f |

---

## E. Save · terminal · index · references

| ID | 파일 | 함수 | 성공 | 실패·partial | 🔇 | 지금 | kind | Inv | Pri | Ph |
|----|------|------|------|--------------|-----|------|------|-----|-----|-----|
| E1.1 | `api/app.py` | final `save_paper_session` L4841 | cache_entry | None | | 108 path | `save_terminal` | T2 | P0 | b |
| E1.2 | `api/app.py` | no cache L4865–4888 | job error | zombie if return early ⚠ | | job error | `save_failed_no_cache` | T2 | P0 | b |
| E1.3 | `api/app.py` | `_finish_job` L687 | `done=true` | not called ⚠ | | client 504 | `ingest_terminal` | **T1,T3** | **P0** | e |
| E1.4 | `api/app.py` | `_pack(pending=False)` L4860 | result dict | — | | — | `ingest_phase:complete` | T7 | P0 | c |
| E1.5 | `cache/paper_cache.py` | `sentence_count` in index L928 | match | drift ⚠ | | 없음 | `consistency_violation` | **T5** | P0 | b |
| E1.6 | `cache/paper_cache.py` | `_write_index` L73 | index GCS | fail 🔇 | 🔇 | 없음 | `index_write` | | P1 | a |
| E1.7 | `cache/paper_cache.py` | `backfill_references_from_source_pdf` L611 | refs grow | silent improve | 🔇 | 없음 | `refs_backfill` | | P1 | a |
| E1.8 | `api/app.py` | `cache_open` backfill refs L2895 | reload session | — | | 없음 | `refs_backfill_on_open` | | P2 | f |
| E1.9 | `llm/papers_gcs.py` | `merge_index_entries` | merged index | dup | 🔇 | 없음 | `index_merge` | | P2 | a |
| E1.10 | `api/app.py` | shadowing L4900–4920 | plan GCS | except→warning | | 폰 msg | `shadowing_chunks` | | P1 | a |
| E1.11 | `api/app.py` | terminal delete upload L709 | cleanup | except 🔇 | 🔇 | 없음 | `ingest_cleanup` | | P2 | a |

---

## F. Open (보관함 → 읽기)

| ID | 파일 | 함수 | 성공 | 실패·partial | 🔇 | 지금 | kind | Inv | Pri | Ph |
|----|------|------|------|--------------|-----|------|------|-----|-----|-----|
| F1.1 | `api/app.py` | `cache_open` L2847 | session_id, lazy | 502 gcs, 404, 422 empty | | HTTP | `open_ok` / `open_fail` | T5 | P0 | a |
| F1.2 | `llm/papers_gcs.py` | `refresh_paper_for_open` L577 | pulled | gcs_pull_failed | | HTTP | `refresh_code` | | P0 | a |
| F1.3 | `llm/papers_gcs.py` | `download_paper_cache` | session local | partial | 🔇 | 없음 | `open_download` | | P1 | a |
| F1.4 | `cache/paper_cache.py` | `load_cached_session(load_images=False)` | PaperSession | corrupt JSON | | 404 | `load_session_meta` | | P1 | b |
| F1.5 | `api/app.py` | `_remember_session` L671 | session_id | LRU evict old | ⚠ | 없음 | `session_bound` cache_id | | P1 | a |
| F1.6 | `api/app.py` | `data["lazy_figures"]=True` L2946 | stubs | by design | | — | `open_figure_stubs` count | | P1 | a |
| F1.7 | `api/app.py` | `translate_pending` on open L2933 | backfill task | pending forever ⚠ | | flag | `open_translate_pending` | T7 | P0 | d |
| F1.8 | `mobile/client.dart` | `openPaper` L1474 | ReadingSession | 422 empty | | HTTP | — | | P1 | d |
| F1.9 | `mobile/library_controller.dart` | `open` L845 | session | progress fail | | error | `progress_mismatch` | T5 | **P0** | d |
| F1.10 | `mobile/api/progress_gate.dart` | `validateProgressIndices` | ok | fail-closed | | error | `progress_mismatch` | | P0 | d |
| F1.11 | `mobile/library_controller.dart` | open hang 45s | session | timeout | | open_empty | keep 130 | | P1 | d |
| F1.12 | `mobile/library_controller.dart` | `_maybeShowQualityBanner` L757 | banner | dismiss | | UI | `ingest_quality_ui` | | P2 | — |
| F1.13 | `api/app.py` | `cache_open` except L2972 | 500 | log.warning | 🔇 | log | `open_exception` | | P0 | d |

---

## G. Figures — lazy window (읽기 중)

| ID | 파일 | 함수 | 성공 | 실패·partial | 🔇 | 지금 | kind | Inv | Pri | Ph |
|----|------|------|------|--------------|-----|------|------|-----|-----|-----|
| G1.1 | `api/app.py` | `session_figures_window` L3261 | data-URLs | 404 session | | HTTP | `figure_window` | | P0 | a |
| G1.2 | `api/app.py` | window: session None + `cache_id` L3302 | reload GCS | still fail | | 129 | `figure_window_cache_fallback` | | P0 | a |
| G1.3 | `api/app.py` | `figure_data_url` in loop L3339 | src non-empty | empty ok ⚠ | | 없음 | `figure_window_empty` | T6 | **P0** | d |
| G1.4 | `cache/paper_cache.py` | `figure_data_url` L130 | base64 | None reasons | 🔇 | 없음 | `figure_data_url_miss` | | **P0** | d |
| G1.5 | `llm/papers_gcs.py` | `ensure_figure_local` | Path | None | 🔇 | 없음 | `figure_blob_miss` | T6 | **P0** | d |
| G1.6 | `mobile/client.dart` | `fetchFigureWindow` L1507 | rows | 401, timeout 90s | | throw | `figure_window_error` | | **P0** | d |
| G1.7 | `mobile/library_controller.dart` | `_prefetchFigureWindow` L1053 | merge | **catch all** 🔇 | 🔇 | UI only | `figure_window_error` | | **P0** | d |
| G1.8 | `mobile/api/reading_models.dart` | `mergeFigureWindow` L333 | imageSrc set | skip empty 🔇 | 🔇 | 없음 | `figure_merge_empty_rows` | | P0 | d |
| G1.9 | `mobile/library_controller.dart` | `advanceFigure` / `goToFigureIndex` | prefetch | — | | unawaited | trigger + G7 | | P0 | d |
| G1.10 | `mobile/screens/reader_screen.dart` | figure panel UI | image | 「이미지 없음」 | | UI | — (G7이 원인) | | P2 | — |
| G1.11 | `api/app.py` | `_SESSION_CACHE_IDS` bind L675 | cache_id | missing on LRU ⚠ | | 없음 | `session_cache_id_missing` | | P1 | f |

---

## H. Reanalyze

| ID | 파일 | 함수 | 성공 | 실패·partial | 🔇 | 지금 | kind | Inv | Pri | Ph |
|----|------|------|------|--------------|-----|------|------|-----|-----|-----|
| H1.1 | `api/app.py` | `POST …/reanalyze` L3001 | new job_id | no source | | HTTP | `reanalyze_started` | | P0 | a |
| H1.2 | `api/app.py` | reanalyze → `_run_ingest_job` | same body as ingest | — | | — | parent_cache_id | | P0 | c |
| H1.3 | `mobile/client.dart` | `startReanalyze` L708 | job_id | 4xx | | HTTP | — | | P1 | d |
| H1.4 | `mobile/library_controller.dart` | `reanalyzePaper` L555 | poll terminal | **504 partial GCS** ⚠ | | error banner | `reanalyze_failed` | T3 | P0 | d |
| H1.5 | `mobile/library_controller.dart` | reanalyze: no resume draft | — | unlike upload | ⚠ | resumeOffer false | **reanalyze_resume** (168f) | | P1 | f |
| H1.6 | `api/app.py` | reanalyze uses same cache_id | overwrite | rmtree C1.4 ⚠ | | 없음 | `reanalyze_pre_save_audit` | T6,T9 | P0 | f |
| H1.7 | `mobile/library_controller.dart` | reanalyze 후 `open(entry)` L597 | refresh read | — | | — | `reanalyze_open` | | P2 | — |

---

## I. Shadowing · 연습 구간

| ID | 파일 | 함수 | 성공 | 실패·partial | 🔇 | 지금 | kind | Inv | Pri | Ph |
|----|------|------|------|--------------|-----|------|------|-----|-----|-----|
| I1.1 | `api/app.py` | shadowing stage 99% L4901 | plan rows | gemini fail | | warning | `shadowing_build` | | P1 | a |
| I1.2 | `llm/shadowing_chunks.py` | `build_chunk_plan` | GCS plan | error | 🔇 | 없음 | `shadowing_plan` | | P1 | a |
| I1.3 | `mobile/library_controller.dart` | `ensureShadowingChunks` L1198 | chunks | error string | | UI | `shadowing_chunks_error` | | P1 | d |
| I1.4 | `mobile/library_controller.dart` | `retryShadowingChunks` L1273 | retry | — | | — | `shadowing_retry` | | P2 | — |

---

## J. 에러 리포트 · admin (기존 + 168 확장)

| ID | 파일 | 함수 | 성공 | 168 확장 | Pri | Ph |
|----|------|------|------|----------|-----|-----|
| J1.1 | `llm/error_logs.py` | `append_event` | GCS jsonl | +ops kinds | P0 | a |
| J1.2 | `api/app.py` | `POST /api/errors/report` L2064 | 204 | kind 필터 | P0 | a |
| J1.3 | `api/app.py` | `GET /api/errors/admin` L2117 | list | job_id/cache_id 검색 | P1 | e |
| J1.4 | `mobile/error_reporter.dart` | `report` / `reportApiFailure` | POST | breadcrumb attach | P0 | d |
| J1.5 | `mobile/hang_watchdog.dart` | begin/progress/end | hang | ingest stage snapshot | P0 | d |
| J1.6 | `llm/upload_audit_log.py` | append | audit | phase transitions | P2 | a |
| J1.7 | **신규** | `GET /api/ops/ingest/jobs/stuck` | list | — | P0 | e |
| J1.8 | **신규** | `GET /api/ops/cache/{id}/integrity` | T1–T10 report | — | P0 | e |
| J1.9 | **신규** | `llm/ingest_integrity.py` | `audit_cache(cache_id)` | — | P0 | b |
| J1.10 | **신규** | sweeper (cron/startup) | mark worker_lost | — | P0 | e |

---

## K. Web (`static/app.js`) — 모바일과 동등

| ID | 파일 | 영역 | 168 계측 | Pri | Ph |
|----|------|------|----------|-----|-----|
| K1.1 | `static/app.js` | ingest hang 134 | 이미 report | P1 | d |
| K1.2 | `static/app.js` | figure window prefetch | `figure_window_empty` | P0 | d |
| K1.3 | `static/app.js` | translate pending poll | `translate_poll_exhausted` | P1 | d |
| K1.4 | `static/cite_refs.js` | — | (168 범위 밖) | — | — |

---

## L. 불변식 T1–T10 → 체크리스트 ID 매핑

| 불변식 | 검증 시점 | 관련 ID |
|--------|-----------|---------|
| T1 | `_finish_job` 직전 | E1.3 |
| T2 | `_finish_job` / poll terminal | E1.1, E1.2, A1.10 |
| T3 | index write / open | C1.6, E1.3, H1.4 |
| T4 | `save_paper_session` | C1.5, C1.3 |
| T5 | save / open | E1.5, F1.9 |
| T6 | save upload / window | C1.7–C1.12, G3–G5 |
| T7 | terminal / translate | D1.1, D1.14, E1.4 |
| T8 | partial publish | D1.1, D1.2, C1.6 |
| T9 | fig loop | **C1.3, C1.5** |
| T10 | upload merge | **C1.9** |

---

## M. Ni/Cu (`4e525b306f5a`) — 체크리스트로 읽기

| 관측 | 해당 ID | 설명 |
|------|---------|------|
| job 90% zombie | E1.3, A1.18, J1.7 | `_finish_job` 미호출, sweeper 없음 |
| index fig 0 | **C1.3, C1.5, C1.6** | fig_meta skip + ingest_status ok |
| session 12 fig | C1.3 vs later upload | 불일치 T4/T9 |
| 「이미지 없음」 | **G1.7, G1.4, G1.5** | silent catch chain |
| 「서론 10/11」 stall | **D1.5, A1.10** | server stall 없음, client 504 |
| 재분석 resume 없음 | **H1.5** | upload draft만 resume |
| 번역 poll 조용 종료 | **D1.14** | 192s 후 stop |

---

## N. 구현 진행 체크 (PR 단위)

### 168a — ops_events + schema
- [x] J1.1 `ops_events.py`
- [x] A1.1–A1.3 서버 이벤트 (A1.11 모바일 poll → 168d)
- [x] `/api/status` `ops_events=true`
- [x] tests `test_ops_events.py`

### 168b — ingest_integrity + T1–T10 (log-only)
- [ ] J1.9 `ingest_integrity.py`
- [ ] C1.3, C1.5, C1.6 검증 (log only, 아직 block 안 함)
- [ ] tests `test_ingest_integrity.py`

### 168c — phase + ingest_status
- [ ] A1.5 trace_id on job
- [ ] C1.6 `processing`/`partial`/`error`/`ok`
- [ ] D1.1 `ingest_phase` field
- [ ] mobile `PaperEntry.ingestStatus` partial UI

### 168d — P0 silent catch → report
- [ ] **G1.7** `_prefetchFigureWindow`
- [ ] **D1.14** translate poll
- [ ] **G1.4–G1.5** figure miss reasons
- [ ] **D1.10** open backfill fail
- [ ] A1.11 poll breadcrumb

### 168e — sweeper + admin
- [ ] J1.7, J1.8
- [ ] A1.19 reclaim events
- [ ] **D1.5** translate stall detector
- [ ] E1.3 worker_lost sweeper

### 168f — 버그 수정 (로그 확인 후)
- [ ] **C1.3/T9** fig_meta: stub meta without data-URL
- [ ] **C1.6/T8** partial ≠ ok
- [ ] **H1.5** reanalyze resume
- [ ] G7 cache_id fallback 검증
- [ ] Ni/Cu 수동 integrity 리포트

---

## O. 파일 인덱스 (빠른 lookup)

| 파일 | 체크 ID |
|------|---------|
| `src/sentence_reading/api/app.py` | A*, B*, D*, E*, F*, G*, H*, I*, J* |
| `src/sentence_reading/cache/paper_cache.py` | C1.2–C1.6, C1.12–C1.13, E1.5–E1.7, F1.4, G1.4 |
| `src/sentence_reading/llm/papers_gcs.py` | C1.7–C1.11, C1.9, F1.2–F1.3, G1.5 |
| `src/sentence_reading/llm/ingest_jobs_gcs.py` | A1.3–A1.8, B1.10–B1.12 |
| `src/sentence_reading/llm/translate_section.py` | D1.3–D1.4 |
| `src/sentence_reading/llm/debone.py` | B1.6–B1.7 |
| `src/sentence_reading/llm/error_logs.py` | J1.1 |
| `mobile/lib/api/client.dart` | A1.9–A1.11, F1.8, G1.6, H1.3 |
| `mobile/lib/state/library_controller.dart` | A1.12–A1.17, D1.14–D1.15, F1.9–F1.11, G1.7–G1.9, H1.4–H1.7, I1.3 |
| `mobile/lib/api/reading_models.dart` | D1.16, G1.8 |
| `mobile/lib/api/progress_gate.dart` | F1.10 |
| `mobile/lib/services/error_reporter.dart` | J1.4 |
| `mobile/lib/services/hang_watchdog.dart` | J1.5 |

---

**총 항목:** A20 + B13 + C14 + D17 + E11 + F13 + G11 + H7 + I4 + J10 + K4 = **124 체크포인트** (웹·신규 API 포함).

버그 수정 PR마다 이 표에서 해당 ID를 **✓ 계측됨 / ✓ 수정됨** 으로 갱신한다.
