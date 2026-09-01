# 169g — Causal handoff evidence + floor guard

**Parent:** [169-agent-evidence-bus.md](169-agent-evidence-bus.md) · [169e-google-batch-evidence.md](169e-google-batch-evidence.md) · [155-deploy-live-guard.md](155-deploy-live-guard.md)  
**Companion guard:** `scripts/check_evidence_floor.py` · `.cursor/rules/evidence-floor-guard.mdc`  
**Status:** Phase 0–3 shipped through **0.3.129** (floor + Gemini + handoff + `progress_view`); 4–6 still phased  
**UI:** 없음  
**Retention target:** evidence JSONL **7일** (구현 = phase F; 지금 rotate 없음)

---

## 0. Locked product judgment (2026-09-01)

| # | Judgment |
|---|----------|
| J1 | 지금 169는 **점(point) 이벤트 + job/cache 사후 조인**이다. **주는/받는 주체 동시 스냅샷·변환 그래프는 없다.** |
| J2 | 클라우드 디버깅에 필요한 최소 단위는 “모든 UX 클릭”이 아니라 **시스템 경계 handoff** (클라↔Run↔GCS↔Google↔Gemini↔poll↔open↔delete). |
| J3 | 논문 본문·주석 내용·녹음 **금지** (169 P5). 인과는 **건수·section·elapsed·blocked_on·ok** 로만. |
| J4 | **169c/d/e 센서와 allowlist는 회귀 금지.** 옛 워크트리·다른 채팅이 센서를 지운 채 버전만 bump 해 배포하면 live 관측이 다시 장님이 된다 → **evidence floor guard**. |
| J5 | Evidence 보관은 **약 7일**이면 충분 (169f retention을 7d로 확정). 논문 `paper_retention`과 **별개**. |

---

## 1. Why (오늘 94% 스톨이 증명한 구멍)

`job_541c53ae11e4`:

1. UI: 94% 「보관본 번역 채우는 중」
2. Evidence: `title` `google_batch` start→done (~0.5s)
3. 이후 **~20분** `call_*` / `phase_exit` / `save_ko` 없음
4. Ops: `ingest_gcs_push` 계속 → 워커는 죽음이 아님
5. 코드: title 직후 `gemini_post` → `_make_digest` / `_harmonize` 인데 **`call_start` 없음**

→ “Google hang”도 “죽은 워커”도 evidence로 **증명 불가**.  
필요한 것: **producer done → consumer in_flight** 를 같은 `handoff_id`/`span_id`로 동시에 남기는 계약.

---

## 2. Floor guard (즉시 · 이전 버전/삭제로 덮지 못하게)

### 2.1 Threat model

| 위협 | 155만으로? | 추가 가드 |
|------|------------|-----------|
| 옛 워크트리 **낮은 semver** 배포 | ✅ `local_version_downgrade` | — |
| 같은/높은 semver인데 **169e kinds·emit 삭제** 후 배포 | ❌ | ✅ evidence floor |
| 에이전트가 “리팩터”로 `_google_batch_timed` 제거 | ❌ | ✅ floor + Cursor rule |
| Dart allowlist만 옛 목록 | ❌ | ✅ py↔dart mirror check |

### 2.2 Mechanism (코드)

| 파일 | 역할 |
|------|------|
| `src/sentence_reading/llm/evidence_floor.py` | `EVIDENCE_FLOOR_VERSION`, `FROZEN_KINDS`, `FROZEN_EMIT_MARKERS` |
| `scripts/check_evidence_floor.py` | allowlist ⊇ frozen · Dart mirror · 소스에 marker 문자열 존재 |
| `scripts/pre_deploy_guard.py` | deploy 경로에서 floor check 실패 시 `errors`에 추가 |
| `tests/test_evidence_floor.py` | CI pin |
| `.cursor/rules/evidence-floor-guard.mdc` | `alwaysApply: true` — 센서 삭제·우회 금지 |

### 2.3 `FROZEN_KINDS` (최소 · 축소 금지)

169c+d+e 관측 최소 집합 (추가만 허용, **제거 금지**):

```
translate_phase_enter, translate_phase_exit, translate_item_done,
translate_call_start, translate_call_done, translate_call_slow, translate_call_fail,
translate_save_ko, open_ko_summary, translate_poll_start, translate_poll_ko,
reanalyze_pref_snapshot, stall_fired, figure_preserve_miss,
library_refresh, paper_delete, figure_window_req, figure_window_res,
server_job_terminal_error, download_cache_fail, reclaim_seed
```

### 2.4 `FROZEN_EMIT_MARKERS` (파일 경로 → 필수 부분 문자열)

예:

| path | must contain |
|------|----------------|
| `llm/translate_section.py` | `"translate_call_start"`, `"translate_call_done"`, `_google_batch_timed` |
| `llm/translate_google.py` | `"google_chunk"`, `"translate_call_start"` |
| `llm/evidence_kinds.py` | each frozen kind as quoted string |
| `mobile/.../evidence_kinds.dart` | same kinds |
| `mobile/.../library_controller.dart` | `reanalyze_pref_snapshot` |

### 2.5 Escape

`ASR_SKIP_EVIDENCE_FLOOR=1` — **비상만** (155 skip과 동일 취급). 설계·채팅에 “임시”라고 적어도 커밋에 남기지 말 것.

### 2.6 Version floor note

Live가 이미 `0.3.126+`이면 155가 다운그레이드를 막는다.  
Floor는 **그 위에** “버전은 올려도 센서를 지우는 배포”를 막는다.

---

## 3. Causal model (구현 목표 스키마)

### 3.1 네 종류 (점 → 간선)

| kind | 의미 | details (snake) |
|------|------|-----------------|
| `span_start` | 작업 구간 시작 | `span_id`, `span_kind`, `section?`, `in_n?`, `blocked_on?` |
| `span_end` | 구간 종료 | `span_id`, `span_kind`, `elapsed_ms`, `out_n?`, `ok`, `exc_type?` |
| `handoff` | A→B 전달 | `handoff_id`, `from_span`, `to_span`, `from_stage`, `to_stage`, `in_n`, `out_n` |
| `progress_view` | 클라가 본 % | `job_id`, `percent`, `msg_hash`, `cache_id?` |

기존 `translate_call_start/done` 는 **Google span의 특수화**로 유지 (호환).  
신규 일반 span은 Gemini·GCS·open에도 쓴다.

### 3.2 `span_kind` allowlist (초기)

```
google_batch, google_chunk, gemini_digest, gemini_harmonize, gemini_draft,
gemini_sense, gemini_polish, gcs_save, cache_open, client_poll, client_upload,
reanalyze, figure_window, paper_delete
```

### 3.3 ID 규칙

- `span_id` = `sp_` + 12 hex (서버 `secrets.token_hex(6)`; 모바일은 동일 포맷)
- `handoff_id` = `hf_` + 12 hex
- 모든 이벤트에 가능하면 `trace_id` (job 생성 시 `oev.new_trace_id()`를 evidence에도 복사 — **지금 미흡 → phase B**)
- 조인 키: `job_id` + `cache_id` + `span_id` / `handoff_id`

### 3.4 읽기 규칙 (에이전트)

```
hang = span_start without span_end|fail for same span_id (>N sec)
blind = handoff from_stage=X but no span_start for to_stage
ui_desync = progress_view.percent high AND active span_kind in {gemini_*} with long silence on call_*
```

---

## 4. Implementation plan — 코드 단위 (강제 순서)

**버전:** 각 phase 배포 시 `app.py` ×2 + `pubspec` + `config.dart` 동시 bump (155).  
**가드:** phase 0이 먼저 main에 있어야 이후 센서 삭제를 막음.

### Phase 0 — Floor guard (이 칩과 동시 · 버전 bump 선택적)

1. **`evidence_floor.py`**
   - `EVIDENCE_FLOOR_VERSION = "0.3.126"`
   - `FROZEN_KINDS: frozenset[str]`
   - `FROZEN_EMIT_MARKERS: list[tuple[str, tuple[str, ...]]]` (relative path, markers)
2. **`check_evidence_floor.py`**
   - `main()` → JSON `{ok, errors[]}` exit 0/1
   - errors: `kind_missing_py:…`, `kind_missing_dart:…`, `marker_missing:path:…`
3. **`pre_deploy_guard.py`**
   - `run_checks` 끝에서 `from sentence_reading.llm.evidence_floor import verify_evidence_floor` 또는 subprocess
   - 실패 시 `evidence_floor:…`
4. **`tests/test_evidence_floor.py`**
   - `verify_evidence_floor()` empty errors
5. **`.cursor/rules/evidence-floor-guard.mdc`**
6. Docs index + 169 parent phase row

### Phase 1 — Gemini span_start/end (blind 제거 · **다음 관측 필수**)

| 파일 | 변경 |
|------|------|
| `evidence_kinds.py` + Dart | add `span_start`, `span_end` (또는 당분간 `translate_call_start`에 `call_kind=digest\|harmonize\|draft…` 재사용 — **호환 우선 시 B안**) |
| `translate_section.py` `_gemini_timed` | **시작 시** `_emit_translate_call("translate_call_start", call_kind=…)`; 종료 시 done 또는 기존 slow/fail 유지 + **`translate_call_done`** |
| `_make_digest` / `_harmonize` | 이미 `_gemini_timed` 경유 → 자동 커버 확인 |
| `evidence_floor.py` | frozen markers에 `call_kind` digest 경로 또는 span markers 추가 |
| tests | mock generate hang → start without done 재현 가능하면 단위로 start emit assert |

**B안 (권장, 종류 폭발 방지):** 새 kind 없이 Gemini도 `translate_call_start`/`done` + `call_kind=digest|harmonize|draft|sense|polish`.  
Floor에 `translate_call_done` already frozen.

### Phase 2 — Section handoff emit

| 파일 | 변경 |
|------|------|
| `translate_section.py` 섹션 루프 (`for sec, idxs in by_sec`) | google batch **done 직후**, gemini_post 켜져 있으면 `handoff` `from_stage=google_batch:{sec}` `to_stage=gemini_digest:{sec}` |
| digest 종료 후 | `handoff` → `gemini_harmonize` 또는 next `google_batch:{next_sec}` |
| `evidence_kinds` | `handoff` 추가 → floor에 **추가만** |

### Phase 3 — progress_view (UI↔서버 시계)

| 파일 | 변경 |
|------|------|
| `mobile/.../client.dart` `pollIngestJob` | percent/message 변경 시 `progress_view` (기존 poll_tick과 병행 또는 details 확장) |
| 서버 job update 경로 | (선택) 동일 percent를 evidence sample — 스팸 주의 1/N |
| 조인 | 같은 `job_id` |

### Phase 4 — Lifecycle handoffs (업로드→open→delete)

체크리스트를 **handoff 목록**으로 재해석 (본문 없이):

| from → to | emit 위치 |
|-----------|-----------|
| upload → ingest_started | `library_controller` + server job create |
| phase vision → cache → translate | ops 유지; evidence는 `handoff` sample or phase_enter already |
| translate_phase_exit → translate_save_ko | `app.py` post-translate |
| save → reading_ready / open | `open_ko_summary` 강화 + handoff |
| open → reader tab | `nav_tab` + `reader_open` 에 `handoff_id` |
| delete | `paper_delete` + server GCS delete result counts |

파일: `library_controller.dart`, `app.py` open/reanalyze/delete, `papers_gcs.py` (실패는 이미 `download_cache_fail`).

### Phase 5 — `trace_id` 전파

| 파일 | 변경 |
|------|------|
| job dict 생성 | 기존 `trace_id` |
| `evidence_bus.emit` 호출부 | `trace_id=job["trace_id"]` 누락분 채움 (`translate_section` `_EVIDENCE_CTX`에 trace_id 필드 추가) |
| 모바일 | `EvidenceBus.record`에 optional `traceId`; poll/open이 job 응답의 trace 저장 |

### Phase 6 — Retention 7d (구 169f)

| 파일 | 변경 |
|------|------|
| `evidence_bus.py` 또는 `scripts/rotate_evidence.py` | GCS JSONL rotate / delete lines older than 7d **또는** day-sharded objects `events/YYYY-MM-DD.jsonl` + lifecycle rule |
| Cloud Run / cron | 일 1회 (CD 또는 Cloud Scheduler) |
| ops_events | **별도** 정책 명시 (기본 7d 동일 권장) |

---

## 5. Non-goals

- 문장/캡션/PDF/주석/녹음 내용 저장  
- 관리자·사용자 증거 UI  
- Datadog/Sentry  
- 번역 속도 튜닝·progressive KO cache write (별 칩)  
- 웹 `evidence.js` (optional 후순위)

---

## 6. Agent workflow after this chip

1. 배포 전: `python scripts/pre_deploy_guard.py` (floor 포함)  
2. 스톨 분석: pull `translate_call_*`, `span_*`/`handoff`, `progress_view`, ops push  
3. **센서 삭제 PR/커밋 금지** — floor + rule  
4. 인과 구현은 Phase 1부터 **한 phase = 한 버전 bump**

---

## 7. Acceptance

### Guard (phase 0)

- [x] `check_evidence_floor.py` exit 0 on main  
- [x] 고의로 `translate_call_start` 를 kinds에서 제거하면 exit 1 (test_evidence_floor)  
- [x] deploy script가 floor 실패 시 abort  

### Causal (phase 1+)

- [ ] title `call_done` 직후 `call_start` `call_kind=digest` (0.3.127 emit; live verify pending) (또는 `span_start`) 수 초 내 출현  
- [ ] digest hang = start without done  
- [ ] UI 94% + digest in_flight 를 pull 한 번에 설명 가능  

---

## 8. Related

- [169c](169c-dense-translate-open-auth.md) · [169d](169d-full-product-evidence.md) · [169e](169e-google-batch-evidence.md)  
- [155-deploy-live-guard.md](155-deploy-live-guard.md)  
- [169-audit-checklist.md](169-audit-checklist.md)  
