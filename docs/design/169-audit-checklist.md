# 169 — Agent Evidence Bus 전수 체크리스트 (파일·함수)

**Parent:** [169-agent-evidence-bus.md](169-agent-evidence-bus.md)  
**용도:** 구현·리뷰 시 **한 줄씩** 체크.  
**원칙:** 관리자/사용자 UI 없음. emit만.  
**컬럼:** `Ph` = 169a…f · `Pri` = P0(필수)/P1/P2 · `Sample` = 전부|1/N

범례: `🔇` = 현재 silent / 미계측 · `⚠` = 실패가 성공처럼 보일 수 있음

---

## 0. 인프라 (169a)

| ID | 파일 | 심볼 | 성공 시 | 실패/경계 시 kind | Pri | Ph | Sample | ☐ |
|----|------|------|---------|-------------------|-----|----|--------|---|
| I0.1 | `llm/evidence_kinds.py` | `ALLOWED_KINDS` | frozenset 정의 | — | P0 | a | — | ☐ |
| I0.2 | `llm/evidence_bus.py` | `evidence_bus_enabled` | env 1 | kill 0 | P0 | a | — | ☐ |
| I0.3 | `llm/evidence_bus.py` | `build_event` | schema_v=1 | kind not allowlisted → None | P0 | a | — | ☐ |
| I0.4 | `llm/evidence_bus.py` | `_safe_details` | bool/int/snake str | CamelCase drop | P0 | a | — | ☐ |
| I0.5 | `llm/evidence_bus.py` | `append_events` | GCS+local | GCS fail → local only + counter | P0 | a | — | ☐ |
| I0.6 | `llm/evidence_bus.py` | `rate_allow` | under limit | over → drop | P0 | a | — | ☐ |
| I0.7 | `api/app.py` | `POST /api/evidence/ingest` | accepted count | 401/403/kill | P0 | a | — | ☐ |
| I0.8 | `api/app.py` | `/api/status` | `evidence_bus: true` | kill false | P0 | a | — | ☐ |
| I0.9 | `scripts/pull_evidence.py` | `main` | filter print | ADC missing → clear error | P0 | a | — | ☐ |
| I0.10 | `tests/test_evidence_bus.py` | * | pins | — | P0 | a | — | ☐ |
| I0.11 | **금지** | `GET /api/evidence/*` | — | **만들지 않음** | P0 | a | — | ☐ |
| I0.12 | **금지** | Settings / admin tile | — | **만들지 않음** | P0 | a | — | ☐ |

---

## 1. 모바일 EvidenceBus 코어 (169b)

| ID | 파일 | 심볼 | 기록 시점 | kind | details 키 (예) | Pri | Ph | Sample | ☐ |
|----|------|------|-----------|------|-----------------|-----|----|--------|---|
| M0.1 | `services/evidence_bus.dart` | `EvidenceBus.record` | 모든 emit 진입 | (arg) | — | P0 | b | 전부 | ☐ |
| M0.2 | `services/evidence_bus.dart` | `flush` | timer 5s / batch 20 | — | accepted/dropped | P0 | b | — | ☐ |
| M0.3 | `services/evidence_bus.dart` | `setEnabled` | status flag | — | — | P0 | b | — | ☐ |
| M0.4 | `services/evidence_kinds.dart` | consts | — | allowlist mirror | — | P0 | b | — | ☐ |
| M0.5 | `api/client.dart` | `postEvidenceBatch` | flush | — | http status | P0 | b | — | ☐ |
| M0.6 | `app.dart` | `_syncPrefsFromAuth` | status fetch | — | evidence_bus flag | P0 | b | — | ☐ |
| M0.7 | `test/evidence_bus_test.dart` | * | unit | — | — | P0 | b | — | ☐ |

---

## 2. Auth · 세션 lifecycle (169b)

| ID | 파일 | 심볼 | 시점 | kind | details | Pri | Ph | Sample | ☐ |
|----|------|------|------|------|---------|-----|----|--------|---|
| A1.1 | `state/auth_controller.dart` (또는 해당) | login success | Google/Kakao/magic | `client_session_start` | provider enum | P0 | b | 전부 | ☐ |
| A1.2 | `app.dart` | logout / clearSession | | `client_session_end` | reason=logout | P0 | b | 전부 | ☐ |
| A1.3 | `library_controller.dart` | `clearAll` | | `client_session_end` | reason=clear_all | P1 | b | 전부 | ☐ |
| A1.4 | `api/client.dart` | 401 handler | | `client_api_fail` | http_status=401 route | P0 | b | 전부 | ☐ |

---

## 3. Prefs · Settings 결정 (169b) — **재분석 번역 스킵 재발 방지**

| ID | 파일 | 심볼 | 시점 | kind | details (필수) | Pri | Ph | ☐ |
|----|------|------|------|------|----------------|-----|----|---|
| P1.1 | `translate_controller.dart` | `setEnabled` | 스위치 변경 | `pref_translate_set` | enabled bool | P0 | b | ☐ |
| P1.2 | `translate_controller.dart` | `bindUid` | 로그인 | `pref_translate_read` | enabled after parse | P1 | b | ☐ |
| P1.3 | `library_controller.dart` | `_wantTranslate` | **매 호출** | `pref_translate_read` | enabled · used_controller bool · auth_ok | P0 | b | ☐ |
| P1.4 | `library_controller.dart` | `reanalyzePaper` | startReanalyze **직전** | `reanalyze_pref_snapshot` | want_translate_pref · want_translate_sent · cache_id | P0 | b | ☐ |
| P1.5 | `library_controller.dart` | `open` | openPaper 직전 | `pref_translate_read` | want_translate | P0 | b | ☐ |
| P1.6 | `library_controller.dart` | upload/ingest start | | `pref_translate_read` | want_translate | P0 | b | ☐ |
| P1.7 | `shadowing_controller.dart` | `setEnabled` | | `pref_shadowing_set` | enabled | P2 | c | ☐ |
| P1.8 | `cite_panel` / settings | setEnabled | | (optional kinds) | | P2 | c | ☐ |

---

## 4. 보관 · open · cursor (169b/c)

| ID | 파일 | 심볼 | 시점 | kind | details | Pri | Ph | Sample | ☐ |
|----|------|------|------|------|---------|-----|----|--------|---|
| L1.1 | `library_controller.dart` | `refresh` | ok/fail | `reader_open` namespace=library_refresh | count · http | P1 | b | 실패=전부 성공=1/5 | ☐ |
| L1.2 | `library_controller.dart` | `open` / `openByCacheId` | begin | `reader_open` | cache_id stage=begin | P0 | b | 전부 | ☐ |
| L1.3 | `library_controller.dart` | `open` | success | `reader_open` | stage=ok · sentence_count · figure_count · translate_pending | P0 | b | 전부 | ☐ |
| L1.4 | `library_controller.dart` | `open` | AsrApiException | `client_api_fail` | route=open · status · message | P0 | b | 전부 | ☐ |
| L1.5 | `library_controller.dart` | `advanceSentence`/`Figure` | | `reader_cursor` | si · fi | P2 | c | 1/20 | ☐ |
| L1.6 | `library_controller.dart` | `deletePaper` | | lifecycle | cache_id | P2 | c | 전부 | ☐ |
| L1.7 | `library_controller.dart` | `mergeSupplementary` | fail | `client_api_fail` | | P1 | c | 전부 | ☐ |
| L1.8 | `library_controller.dart` | `_prefetchFigureWindow` | empty/error 🔇 | `figure_window_res` | empty_n · miss | P0 | c | 전부 | ☐ |
| L1.9 | `client.dart` | `fetchFigureWindow` | | `figure_window_req` / `res` | | P0 | c | 전부 | ☐ |

---

## 5. Ingest · poll · cancel (169b)

| ID | 파일 | 심볼 | 시점 | kind | details | Pri | Ph | Sample | ☐ |
|----|------|------|------|------|---------|-----|----|--------|---|
| U1.1 | `library_controller.dart` | upload begin | | `ingest_upload_start` | bytes · chunked bool | P0 | b | 전부 | ☐ |
| U1.2 | `client.dart` | `pollIngestJob` | pct/msg change | `ingest_poll_tick` | percent · stage_msg_hash | P1 | b | 변경시만 | ☐ |
| U1.3 | `client.dart` | `pollIngestJob` | ok=false | `client_api_fail` | message · job_id · code | P0 | b | 전부 | ☐ |
| U1.4 | `client.dart` | `pollIngestJob` | idle 504 | `client_hang` or `client_api_timeout` | | P0 | b | 전부 | ☐ |
| U1.5 | `library_controller.dart` | reanalyze catch | | `client_api_fail` + set lastIngestFailure | job_id | P0 | b | 전부 | ☐ |
| U1.6 | `library_controller.dart` | `cancelUpload` | | lifecycle | | P2 | c | 전부 | ☐ |
| U1.7 | `client.dart` | `startReanalyze` | response | `reanalyze_start` | job_id · cache_id · translate_q | P0 | b | 전부 | ☐ |

---

## 6. Translate poll · backfill (169c)

| ID | 파일 | 심볼 | 시점 | kind | details | Pri | Ph | ☐ |
|----|------|------|------|------|---------|-----|----|---|
| T1.1 | `library_controller.dart` | `_maybeStartTranslatePoll` | start | lifecycle | cache_id | P1 | c | ☐ |
| T1.2 | `library_controller.dart` | poll exhausted | | `translate_poll_exhausted` | attempts=24 | P0 | c | ☐ |
| T1.3 | `library_controller.dart` | poll error | | `client_api_fail` | stage=translate_poll | P0 | c | ☐ |
| T1.4 | `library_controller.dart` | wantTr2 false stop | | `pref_translate_read` | stopped_poll=1 | P0 | c | ☐ |

---

## 7. ErrorReporter · Hang (169b) — UI 없이 mirror

| ID | 파일 | 심볼 | 시점 | kind | Pri | Ph | ☐ |
|----|------|------|------|------|-----|----|---|
| E1.1 | `error_reporter.dart` | `report` | after POST errors/report | evidence mirror `client_unhandled` or kind map | P0 | b | ☐ |
| E1.2 | `error_reporter.dart` | FlutterError.onError | | `client_unhandled` | P0 | b | ☐ |
| E1.3 | `error_reporter.dart` | `reportApiFailure` | | `client_api_fail` | P0 | b | ☐ |
| E1.4 | `hang_watchdog.dart` | fire | | `client_hang` | P0 | b | ☐ |
| E1.5 | **비목표** | `error_logs_screen.dart` | — | **169에서 수정·확장 금지** (130 전용) | P0 | — | ☐ |

---

## 8. 서버 · reanalyze · cache (169d)

| ID | 파일 | 심볼 | 시점 | kind | details | Pri | Ph | ☐ |
|----|------|------|------|------|---------|-----|----|---|
| S1.1 | `api/app.py` | `cache_reanalyze` | job create | (ops ingest_started 유지) + evidence `reanalyze_start` source=server | want_translate · reanalyze · cache_id | P0 | d | ☐ |
| S1.2 | `api/app.py` | `cache_reanalyze` | download figures | | figures_pulled bool · prior_png_count | P0 | d | ☐ |
| S1.3 | `cache/paper_cache.py` | `save_paper_session` | force_cache_id · prior empty | `figure_preserve_miss` | prior_png · session_figs · forced | P0 | d | ☐ |
| S1.4 | `cache/paper_cache.py` | `save_paper_session` | after write | sample | fig_meta_n · with_file_n | P1 | d | ☐ |
| S1.5 | `api/app.py` | `cache_open` | | ops/open path + evidence boundary | translate · poll · backfill_spawned | P1 | d | ☐ |
| S1.6 | `api/app.py` | figures/window | empty all | `figure_window_empty` (ops 유지) + evidence mirror | | P0 | d | ☐ |
| S1.7 | `api/app.py` | `_fail_job_terminal` | | `server_job_terminal_error` | reason_enum · percent | P0 | d | ☐ |
| S1.8 | `llm/ingest_stall.py` | `check_translate_stall` | skip live | `stall_skipped_live_worker` | | P1 | d | 1/20 | ☐ |
| S1.9 | `llm/ingest_stall.py` | fire | | `stall_fired` | idle_sec · stall_sec | P0 | d | ☐ |
| S1.10 | `api/app.py` | exception handler / middleware | unhandled | `server_handler_fail` | route · exc_type snake | P1 | d | ☐ |
| S1.11 | `api/app.py` | `_run_ingest_job_body` except | | (ops +) evidence | message redact | P0 | d | ☐ |
| S1.12 | `papers_gcs.py` | `download_paper_cache` | fail | evidence | include_figures · reason | P1 | d | ☐ |
| S1.13 | `api/app.py` | reclaim job seed | | evidence | target_cache_id_present · skip_cache | P0 | d | ☐ |

---

## 9. 서버 · 이미 168이 커버하는 것 (중복 emit 정책)

| ID | 기존 kind (ops) | 169 조치 | ☐ |
|----|-----------------|----------|---|
| X1 | `ingest_started` | ops 유지; evidence는 mobile `reanalyze_start`/`ingest_upload_start`로 클라측 보강 | ☐ |
| X2 | `ingest_phase_transition` | **ops only** (서버 스팸 방지) | ☐ |
| X3 | `ingest_terminal` | ops + evidence `server_job_terminal_error` when error | ☐ |
| X4 | `translate_stalled` | ops + evidence `stall_fired` | ☐ |
| X5 | `consistency_violation` | ops only (또는 weekly sample into evidence) | ☐ |
| X6 | `figure_blob_miss` | ops + evidence mirror | ☐ |

---

## 10. Client HTTP 래퍼 (169b) — **모든 API 실패**

| ID | 파일 | 심볼 | 규칙 | ☐ |
|----|------|------|------|---|
| C1.1 | `api/client.dart` | `_decodeObject` / throw AsrApiException | throw 직전 `client_api_fail` (route, status, message[:200]) | ☐ |
| C1.2 | `api/client.dart` | `.timeout` catch | `client_api_timeout` | ☐ |
| C1.3 | `api/client.dart` | evidence POST 자체 실패 | **재귀 금지** — local ring only | ☐ |

대상 라우트 (실패 시 자동 커버되면 C1.1로 충분; 아니면 개별 ☐):

- `GET /api/status`
- `GET /api/cache/papers`
- `POST …/open`
- `POST …/reanalyze`
- `GET …/ingest/jobs/{id}`
- `POST /api/ingest` · chunked upload family
- `GET …/figures/window`
- `POST /api/tts`
- `GET/POST shadowing/*`
- `POST /api/errors/report` (실패해도 evidence local)

---

## 11. Web (169e · optional)

| ID | 파일 | 심볼 | kind | Pri | ☐ |
|----|------|------|------|-----|---|
| W1.1 | `static/evidence.js` | `asrEvidence.record` | — | P2 | ☐ |
| W1.2 | `static/app.js` | ingest fail | `client_api_fail` | P2 | ☐ |
| W1.3 | `static/app.js` | open fail | `client_api_fail` | P2 | ☐ |
| W1.4 | **금지** | admin HTML panel | — | P0 | ☐ |

---

## 12. 에이전트 스크립트 · 운영 (169a)

| ID | 파일 | 동작 | ☐ |
|----|------|------|---|
| G1.1 | `scripts/pull_evidence.py` | `--since` `--kind` `--job` `--cache` `--merge-ops` | ☐ |
| G1.2 | `scripts/pull_evidence.py` | ADC/gsutil 실패 시 **명확한 stderr** (빈 성공 금지) | ☐ |
| G1.3 | `docs/design/169-…` | 에이전트 워크플로 §7 준수 | ☐ |
| G1.4 | Cursor rule (optional 후속) | “실패 수정 전 pull_evidence 필수” | ☐ |

---

## 13. Reader / UI 표면 (의도적 **비계측** 또는 sample)

사용자 프라이버시·노이즈:

| ID | 행위 | 정책 | ☐ |
|----|------|------|---|
| N1 | 문장 텍스트 표시 | **evidence에 문장 넣지 않음** | ☐ |
| N2 | TTS play | sample only / skip | ☐ |
| N3 | annotation 내용 | **금지** (id·count만 가능) | ☐ |
| N4 | 연습 녹음 audio | **금지** | ☐ |
| N5 | lastIngestFailure 배너 | 제품 UX; evidence에 message 복사 OK | ☐ |

---

## 14. 회귀 핀 (구현 완료 시 테스트에 고정)

| ID | assert | ☐ |
|----|--------|---|
| R1 | `reanalyzePaper` 소스에 `reanalyze_pref_snapshot` | ☐ |
| R2 | status JSON에 `evidence_bus` | ☐ |
| R3 | repo에 `GET /api/evidence` **없음** (grep) | ☐ |
| R4 | `error_logs_screen` / Settings admin이 evidence를 **읽지 않음** | ☐ |
| R5 | `pull_evidence.py --help` exit 0 | ☐ |
| R6 | unknown kind → accepted drop | ☐ |
| R7 | body owner_uid ignored | ☐ |

---

## 15. Co–TiO₂ 사례 → 체크리스트 매핑 (왜 이 칩이 필요한지)

| 증상 | 필요한 증거 행 | ID |
|------|----------------|-----|
| 토글 ON인데 번역 스킵 | `reanalyze_pref_snapshot` pref=true sent=false | P1.4 |
| 「처리에 실패」만 보임 | `client_api_fail` message=서버원문 · job_id | U1.3 · U1.5 |
| 번역 중 강제 실패 | `stall_fired` idle_sec | S1.9 |
| 워커 살아있는데 stall | `stall_skipped_live_worker` 없어야 하는데 예전에 fire | S1.8 |
| 그림 3+ 없음 | `figure_preserve_miss` prior_png=0 | S1.3 |
| 번역 준비 중 고착 | `translate_poll_exhausted` / pending | T1.2 |
| 에이전트가 로그 못 봄 | `pull_evidence.py` | G1.1 |

---

## 16. 완료 정의 (169b 최소)

- [ ] 169a 서버 sink + pull script live에서 동작
- [ ] 모바일 재분석 1회 → evidence에 pref_snapshot + (실패 시) client_api_fail
- [ ] Settings/관리자에 새 UI 없음
- [ ] 사용자에게 “증거 수집 중” 문구 없음
- [ ] 다음 Co–TiO₂류 실패에서 **추측 패치 없이** pull 결과만으로 원인 한 줄 특정
