# 169j — Translate `on_item` off critical path (progressive writer)

**Parent:** [169-agent-evidence-bus.md](169-agent-evidence-bus.md) · [169h-interior-checkpoint-evidence.md](169h-interior-checkpoint-evidence.md)  
**Related stall:** title `harmonize` `call_done` → missing `harmonize_pool_end` / next section (`job_a805ad4c3980`, `job_58b02834ce38`, 2026-09-01/02)  
**Status:** implemented in **0.3.135** (J0–J3) · live verify pending  
**Next observability:** [169k](169k-observability-pull-verdicts.md) (verdict rules · I3/I4 · worker/zombie)  
**UI:** 없음 (동작만; 사용자 문구 변경 없음)  
**Depends on:** 169h live (≥0.3.133) for acceptance sensors  

---

## 0. Locked product judgment

| # | Judgment |
|---|----------|
| J1 | 94%/90% 「보관본 번역 채우는 중」 정체는 Gemini hang이 아니라 **harmonize 워커가 `on_item` cold path(대형 pack/publish/`_save_payload`/save+GCS)에서 블로킹**되어 `fut.result()`·`pool_end`에 못 가는 구조다. |
| J2 | **워커 증원(Cloud Run / ThreadPool +1)은 이 구멍의 처방이 아니다.** title `n_harm≈1`이면 여분 워커가 future를 풀지 못한다. |
| J3 | ThreadPool 워커 의무 = **번역 결과 → `ko_map`(± 초경량 enqueue)**. Durable I/O·partial pack은 **writer / 섹션·phase 끝**. |
| J4 | Progressive UX는 유지하되 **DropOldest + debounce/dirty + flush**로. “모든 중간 스냅샷 보존”보다 **완료·다음 섹션 전진**이 우선. |
| J5 | `asyncio.wait_for(to_thread(enrich…))`로 전체 번역을 자르는 보험은 **금지에 가깝다** — 스레드를 죽이지 못해 좀비만 남김 (CPython/asyncio 관행). |
| J6 | 유령 FGS(목록 0건·알림만)는 **별 칩** (이 문서 non-goal). |
| J7 | Floor = 센서 **추가만**. 본문·KO 전문 evidence 금지 (169 P5). |

---

## 1. Why (증거 사슬)

```
harmonize_pool_start (blocked_on=threadpool_join)
  → translate_call_start/done harmonize   # 워커 안, Gemini OK
  → (없음) pool_tick / pool_end / section_done
  → UI % 고정 · 다음 섹션 google_batch 없음
```

코드: `pool_end`는 `ThreadPoolExecutor` `with` 종료 **후**.  
`call_done` 다음 같은 워커가 `_emit` → `on_item` (락 잡은 채 가능).  
ingest `_on_item`: 메모리 패치 + `_pack`/`_job_publish_partial` + 주기 `_save_payload`.  
open backfill `_on_item`: 주기 `save_paper_session` + `upload_paper_cache`.

---

## 2. Target architecture

```text
[harmonize / pipeline 워커]
    → ko_map + stage_map only
    → optional: queue.put_nowait(delta)   # never block; never GCS
              │
              ▼
[bounded queue]  DropOldest / coalesce by job+gen
              │
              ▼
[writer thread ×1]
    → throttle partial publish
    → debounce dirty durable (_save_payload / local save)
              │
[section boundary / phase exit / cancel]
    → flush() then final save_paper_session
```

### 2.1 Hot vs cold

| Hot (워커 OK) | Cold (워커 금지) |
|---------------|------------------|
| `ko_map` / `stage_map` 갱신 | `_pack` + `_job_publish_partial` |
| `put_nowait` delta (실패→drop+counter) | `_save_payload` reclaim |
| | `save_paper_session` / `upload_paper_cache` |
| | 대형 evidence 외 동기 I/O |

### 2.2 Queue policy (보강 · 검색 SoT)

| 정책 | 선택 | 이유 |
|------|------|------|
| Bound | `maxsize` 고정 (예: 32~64) | 무한 성장 금지 |
| Overflow | **DropOldest** (또는 같은 `job_id`의 옛 gen coalesce) | progressive는 최신 UI 상태면 충분 ([backpressure DropOldest](https://unseel.com/cs/backpressure)) |
| Enqueue | **`put_nowait` only** | Block put = 다시 번역 막음 |
| Payload | delta 또는 **얕은 스냅샷 복사** | writer 중 session mutate 시 깨진 JSON 방지 |
| Debounce | dirty + 2–5s 또는 **섹션 경계** durable | ([ReactiveCheckpointer](https://cdn.jsdelivr.net/npm/@ownware/loom@0.4.0/dist/checkpoint/reactive.d.ts) 류) |
| Shutdown | phase exit / cancel / 프로세스 종료 시 **`flush()`** | background checkpoint 공통 함정 |

### 2.3 Asyncio ↔ thread (보강)

- 워커는 **`queue.Queue`만**. `asyncio.Queue` / `asyncio.Lock` / 루프 직접 await **금지**.  
- job percent 등 루프 친화 갱신은 `loop.call_soon_threadsafe` 또는 writer→drain ([hybrid concurrency](https://async-concurrency.com/concurrent-execution-worker-patterns/hybrid-concurrency-models/)).  
- `threading.Lock`: **`ko_map`만**. I/O·publish는 락 밖.

### 2.4 Timeout insurance (올바른 형태)

| 하지 말 것 | 할 것 |
|------------|--------|
| `wait_for(to_thread(enrich))`로 전체 번역 kill | writer/cold path **자체 deadline** → skip + checkpoint |
| 스레드 force-kill | 협력: Event는 cancel 시 writer flush/중단용 |

---

## 3. Code touch map (구현 시)

| 영역 | 파일 | 변경 |
|------|------|------|
| Emit 경로 | `llm/translate_section.py` | `_emit`: 락=맵만; cold `on_item` 제거 또는 hot-only 콜백; `pool_end` 전제 유지 |
| Ingest progressive | `api/app.py` `_on_item` (~5921) | 메모리 + enqueue; `_save_payload`/heavy publish 이동 |
| Open backfill | `api/app.py` `_on_item` (~4988) | item마다 save+upload 제거 → writer/phase 끝 |
| Save side | `cache/paper_cache.py` | progressive 중 `upload_paper_cache` 스킵 플래그 검토 |
| Writer | **신규** 소형 모듈 또는 `app.py` job-local | queue + thread + flush API |
| Evidence | kinds + floor **추가만** | 아래 §4 |

버전: 155 규칙 — `app.py`×2 + `pubspec` + `config.dart` 동시 bump.

---

## 4. Evidence kinds (최소 추가)

| kind / checkpoint | 언제 |
|-------------------|------|
| `checkpoint=on_item_enqueue` | put_nowait 성공 (샘플 OK) |
| `checkpoint=writer_drop` | DropOldest / coalesce |
| `checkpoint=writer_done` | cold 작업 종료 (`elapsed_ms`, `ok`) |
| `checkpoint=writer_flush` | phase/section flush |
| (유지) `harmonize_pool_end` | acceptance 핵심 |

details: `job_id`, `cache_id`, `trace_id`, `queue_depth?`, `elapsed_ms`, `ok` — **본문 없음**.

---

## 5. Acceptance (live)

재업로드 translate ON, 169h 센서로:

1. title `harmonize` `call_done` 후 **≤5s** 안에 `harmonize_pool_end` **또는** `harmonize_pool_tick` with `remaining=0`  
2. 이어서 `handoff` → `section_done` → 다음 섹션 `google_batch` `call_start` (abstract 등)  
3. UI가 title 직후 **≥120s** 동일 high-%에 고정되지 않음  
4. (보강) writer 사용 시: phase 끝에 `writer_flush` ok; 정체 재현 시 `writer_drop`만 있고 `pool_end`는 존재  

---

## 6. Implementation phases

| Phase | 내용 |
|-------|------|
| **J0** | ingest `_on_item`에서 `_save_payload` 주기 제거 + `_pack`/publish를 **메인 `as_completed` 이후 throttle** 또는 큐 (최소 패치로 구멍 메움) |
| **J1** | bounded queue + writer + DropOldest + debounce + flush API |
| **J2** | open backfill 동일 패턴; save 중 GCS upload 스킵 플래그 |
| **J3** | evidence kinds + floor + live acceptance §5 |

한 phase = 한 버전 bump 권장. J0만으로도 acceptance 1–3이 열릴 수 있음.

---

## 7. Non-goals

- Cloud Run / harmonize `max_workers` 증원으로 이 스톨 “해결”  
- 유령 upload FGS (별 칩)  
- 「거의 끝나 취소 불가」 UX  
- 169i I3/I4 figure 장부  
- Datadog / 풀 OTel  
- 관리자·사용자 진단 UI  

---

## 8. Agent workflow after ship

1. 스톨 pull: `checkpoint`, `handoff`, `translate_call_*` — **`pool_end` 유무**가 1차 판정  
2. `call_done` 있고 `pool_end` 없으면 → J0/J1 회귀 의심 (다시 cold path가 워커에 붙었는지)  
3. `writer_drop` 폭주 + UI KO 공백 → debounce/bound 튜닝 (번역 정체와 분리)  

---

## 9. Related

- [169h-interior-checkpoint-evidence.md](169h-interior-checkpoint-evidence.md)  
- [169i-artifact-transfer-ledger.md](169i-artifact-transfer-ledger.md) (save gen 조인은 flush 후)  
- [169g-causal-handoff-evidence.md](169g-causal-handoff-evidence.md)  
- External: asyncio↔thread queues · DropOldest backpressure · debounced checkpoint · to_thread cancel limits  
