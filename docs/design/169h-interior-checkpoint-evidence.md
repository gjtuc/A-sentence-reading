# 169h — Interior checkpoint evidence (단계 안쪽 densify)

**Parent:** [169-agent-evidence-bus.md](169-agent-evidence-bus.md) · [169g-causal-handoff-evidence.md](169g-causal-handoff-evidence.md)  
**Next:** [169j](169j-translate-on-item-off-critical-path.md) — `on_item` cold path off ThreadPool (pool_end stall fix)  
**Sibling:** [169i-artifact-transfer-ledger.md](169i-artifact-transfer-ledger.md) (조각 장부)  
**Status:** design locked · **H0–H2 implemented in 0.3.133** (context bind + checkpoint + slow callback)  
**UI:** 없음  
**Depends on:** 169g Phase 0–6 live (≥0.3.132) — floor + boundary handoffs + Gemini `call_*` + 7d retention

---

## 0. Locked product judgment (2026-09-01)

| # | Judgment |
|---|----------|
| H1 | 169g는 **단계 경계**(Google/Gemini `call_*`, section `handoff`, lifecycle, `progress_view`)까지다. **경계와 경계 사이**에서 멈추면 evidence가 조용해진다. |
| H2 | 2026-09-01 live 재업로드 (`job_8c0bd53cd315`): title `harmonize` `call_done` (14:32:45Z) 이후 **다음 섹션 `google_batch` `call_start` / `section_done` handoff가 안 보임**. 경계 센서만으로 “어디서”는 좁혔고 “왜”는 못 고름. |
| H3 | 1번(본 칩) = **시간축 미시 발판** (`blocked_on`, pool start/end, callback enter/exit). 2번(169i) = **객체 source→sink 장부**. **구현 순서: 169h → 169i.** |
| H4 | 본문·KO 전문·PDF bytes **금지** (169 P5). 건수·section·elapsed·`blocked_on`·`exc_type`·ids만. |
| H5 | Floor = **추가만**. 기존 frozen kinds 축소 금지. 새 kind는 phase마다 floor에 append. |
| H6 | `_EVIDENCE_CTX`가 `threading.local`이라 ThreadPool 워커 emit에서 `job_id`/`trace_id` 누락이 이미 관측됨 → **컨텍스트 전파 수정이 Phase H0 (센서 densify보다 먼저).** |

---

## 1. Why (경계 센서의 한계)

169g 읽기 규칙:

```
hang  = span_start without end
blind = handoff → to 인데 to의 call_start/span_start 없음
```

title 경로에서 이미 보이는 것:

`google_batch done` → handoff → `digest` start/done → handoff → `harmonize` start/done`

그 직후 코드 (`translate_section.py` 섹션 루프)는 대략:

1. `as_completed`로 남은 harmonize future 대기 / pool shutdown  
2. `_emit_handoff(gemini_harmonize → section_done)`  
3. `_emit_handoff(section_done → google_batch, section=next)`  
4. 다음 루프 `_google_batch_timed` → `call_start`

**암흑 = 1–4 사이.** 여기에 CCTV가 없으면 Gemini hang / lock / `on_item` / emit 직전을 구분 못 함.

업계 대응: nested span + milestone event ([OTel events vs spans](https://oneuptime.com/blog/post/2026-01-30-span-event-design/view)), async context 전파 ([OTel async boundaries](https://oneuptime.com/blog/post/2026-02-06-propagate-trace-context-async-boundaries/view)), handoff에서 trace가 끊기지 않게 ([dark at handoff](https://tianpan.co/blog/2026/05/17/trace-goes-dark-at-agent-handoff)).

---

## 2. Causal model extension

169g §3 (`span_*` / `handoff` / `progress_view`)를 **유지**.  
본 칩은 같은 버스에 **미시 stage + `blocked_on`** 을 채운다.

### 2.1 Kinds

| kind | 역할 |  sparseness |
|------|------|-------------|
| `translate_call_start` / `done` / `fail` / `slow` | 기존 LLM/Google span | 유지 |
| `handoff` | 기존 A→B | 유지 + **미시 to_stage 허용** |
| `checkpoint` | 순간 이정표 (duration 없음) | **신규** — 남용 금지 |
| `callback_span` *(또는 `checkpoint`로 흡수)* | `on_item` / `on_progress` enter/exit | slow만 또는 섹션 첫/끝 |

**권장 B안 (종류 폭발 방지):**  
새 kind는 `checkpoint` 하나.  
pool/section은 `handoff`의 `from_stage`/`to_stage`를 미시 토큰으로 확장 + 필요 시 `translate_call_*`에 `call_kind=harmonize_pool` 같은 **비-HTTP span**은 쓰지 말고 checkpoint로.

### 2.2 `details` 계약 (snake)

공통 (가능하면 항상):

- `job_id`, `cache_id`, `trace_id`, `owner_uid` — **워커에서도 비면 안 됨** (H6)
- `section` — snake token
- `checkpoint` 또는 `from_stage` / `to_stage`
- `blocked_on` — 아래 allowlist
- `in_n` / `out_n` / `remaining` / `worker_n`
- `elapsed_ms`, `ok`, `exc_type`

### 2.3 `blocked_on` allowlist (초기)

```
gemini_http
google_http
threadpool_join
on_item_callback
on_progress_callback
lock_ko_map
section_enter
next_section_enter
emit_handoff
gcs_patch
unknown
```

### 2.4 미시 `from_stage` / `to_stage` / `checkpoint` 토큰

섹션 루프 (title→abstract 구멍 우선):

| token | 의미 |
|-------|------|
| `section_enter` | `_sec_queue` 바퀴 시작 (`si`, `queue_len`, `n_plain`) |
| `harmonize_pool_start` | ThreadPool submit 직전 (`n_harm`, `workers`) |
| `harmonize_pool_tick` | 매 N개 또는 마지막 (`finished_h`, `remaining`) |
| `harmonize_pool_end` | pool 종료 직후 |
| `section_done` | 기존 handoff to (유지) |
| `section_exit` | next handoff 직전 |
| `next_section_armed` | next `google_batch`/`gemini_pipeline` handoff emit 직후 |
| `on_item_enter` / `on_item_exit` | 콜백 (index, stage, elapsed) |
| `pool_task_fail` | future 예외 (`exc_type`, section) |

과계측 금지: 문장마다 checkpoint **금지**. pool tick은 `first | every 5 | last` (기존 spam guard와 동일 철학).

### 2.5 읽기 규칙 (에이전트)

```
hang_interior = checkpoint X 이후 N초 침묵 AND 다음 기대 토큰 없음
pool_hang     = harmonize_pool_start 있고 pool_end 없음
              OR pool_tick remaining>0 고정
callback_hang = on_item_enter 있고 exit 없음 (>200ms 샘플만 남겨도)
blind_next    = handoff section_done→google_batch 있고 next call_start 없음
ctx_orphan    = call_*/checkpoint 에 job_id 또는 trace_id 빈 문자열 (회귀)
```

오늘 스톨 판정표:

| 마지막 센서 | 결론 |
|-------------|------|
| pool_start, tick remaining>0 | 다른 harmonize future hang |
| pool_end 없음, call_done만 | join/shutdown |
| pool_end, section_done handoff 없음 | emit/lock |
| section_done + next armed, call_start 없음 | I5 루프 진입 |
| on_item_enter only | 패치 콜백 (→ 169i와 조인) |

---

## 3. Implementation plan (강제 순서)

**버전:** phase마다 `app.py` ×2 + `pubspec` + `config.dart` 동시 bump (155).  
**가드:** floor에 새 kind/marker **추가만**.

### Phase H0 — Evidence context across threads (**먼저 · 센서 densify보다 우선**)

| 파일 | 변경 |
|------|------|
| `llm/translate_section.py` | pool submit 시 `job_id/cache_id/trace_id/owner_uid/section`을 클로저로 캡처해 `_emit_translate_call` / `_emit_handoff`에 **명시 전달** (local 의존 제거) |
| tests | 워커 스레드에서 emit mock → ids non-empty assert |

### Phase H1 — Section enter/exit + pool checkpoints

| 파일 | 변경 |
|------|------|
| `evidence_kinds.py` + Dart | `checkpoint` 추가 |
| `evidence_floor.py` | frozen kinds + markers |
| `translate_section.py` | §2.4 토큰 emit (title→next 경로 필수) |
| tests | mock: pool_start without end 재현 가능하면 assert |

### Phase H2 — Slow callback sensors

| 파일 | 변경 |
|------|------|
| `translate_section.py` `_emit` / `_tick` | enter/exit; **elapsed_ms ≥ 200** 또는 섹션 첫/끝만 evidence |
| (선택) `app.py` on_item 경로 | 동일 `blocked_on=on_item_callback` |

### Phase H3 — Live acceptance on post-title stall

재업로드 translate ON → pull:

1. title `harmonize` `call_done` 이후 **5초 내** `harmonize_pool_end` **또는** `section_done` handoff **또는** `blocked_on=…` checkpoint 중 **하나 이상**
2. 정체 시 `ctx_orphan` 0건 (H0)
3. abstract `call_start`가 오면 정상; 안 오면 마지막 checkpoint로 원인 행 선택 가능

### Phase H4 — (optional) caption / phase_exit 미시

섹션 루프 이후 caption·마무리도 동일 패턴. P1.

---

## 4. Emit 위치 (코드 지도)

`src/sentence_reading/llm/translate_section.py` — `_enrich_session_translations_body`:

| 줄 근처 (개념) | emit |
|----------------|------|
| `for _si, (sec, idxs) in enumerate(_sec_queue)` 직후 | `checkpoint=section_enter` |
| harmonize `ThreadPoolExecutor` 직전 | `harmonize_pool_start` + `blocked_on=threadpool_join` |
| `as_completed` 루프 내부 spam guard | `harmonize_pool_tick` |
| pool `with` 블록 종료 직후 | `harmonize_pool_end` |
| 기존 `_emit_handoff(… section_done)` | 유지 |
| next-section `_emit_handoff` 직후 | `checkpoint=next_section_armed` |
| `_emit` / `_tick` | H2 callback |

---

## 5. Non-goals

- 169i artifact hash/locator 장부 (별 칩)  
- 문장/캡션 내용 로그  
- Datadog / 풀 OpenTelemetry SDK 도입  
- 관리자·사용자 증거 UI  
- 번역 속도 튜닝 자체 (원인 고정 후 별 패치)  
- 모든 함수에 checkpoint

---

## 6. Agent workflow

1. 배포 전: `pre_deploy_guard.py` (floor 포함)  
2. 스톨: pull `translate_call_*`, `handoff`, `checkpoint`, `progress_view` — **마지막 `blocked_on` / checkpoint 토큰**으로 표 §2.5 행 선택  
3. `on_item` hang이면 169i session gen/transfer 조인  
4. 센서 삭제 금지  

---

## 7. Acceptance

### H0

- [ ] 워커 스레드 emit에 `job_id`+`trace_id` 비지 않음 (unit + live sample)

### H1–H2

- [ ] `checkpoint` in py+dart allowlist + floor  
- [ ] title 완료 후 pool_end 또는 section_done 또는 blocked_on 중 하나 5s 내 (live)  
- [ ] 의도적 floor에서 `checkpoint` 제거 시 `check_evidence_floor` exit 1  

### Product

- [ ] 동일 재현 스톨에서 “유력 가설 1개”로 좁힐 수 있음 (코드 추측만이 아님)

---

## 8. Related

- [169g-causal-handoff-evidence.md](169g-causal-handoff-evidence.md)  
- [169i-artifact-transfer-ledger.md](169i-artifact-transfer-ledger.md)  
- [169e-google-batch-evidence.md](169e-google-batch-evidence.md)  
- [155-deploy-live-guard.md](155-deploy-live-guard.md)  
- [169-audit-checklist.md](169-audit-checklist.md)  
