# 168e — 구현 체크리스트 (sweeper + admin)

**Parent:** [168-ingest-observability.md](168-ingest-observability.md) · [168-audit-checklist.md](168-audit-checklist.md)  
**원칙:** 관측·terminal 정직성만. fig_meta / Ni/Cu 수리 / reanalyze resume는 **168f**.

**권장 버전:** `0.3.116` · status 핀 `ingest_stall_detector: true`  
(슬라이스를 여러 커밋으로 나눠도 마지막에만 bump해도 됨. 아래는 **논리 슬라이스**.)

---

## 슬라이스 의존 그래프

```text
e0 schema/kinds/env
 ├─ e1 progress clock + translate stall          ★체감
 ├─ e2 reclaim ops events
 ├─ e3 stuck list helper + GET stuck
 ├─ e4 GET integrity (audit_cache 노출)
 └─ e5 sweeper (worker_lost terminal)
      └─ needs e0 + (e1 clock 권장) + e3 list
```

모바일 APK: **e1이 job error를 poll에 노출하면** 설치 권장. e3–e4만이면 서버만으로 충분.

**추천 구현 순서:** e0+e4 → e2 → e1 → e3 → e5

---

## e0 — 스키마·env·status (기반)

### 목적

이후 슬라이스가 붙일 kind / kill switch / 핀만 먼저 고정.

| # | 파일 | 작업 | 완료 |
|---|------|------|------|
| e0.1 | `llm/ops_events.py` | `_ALLOWED_KINDS`에 추가: `translate_stalled`, `worker_lost`, `reclaim_attempt`, (선택) `translate_section_tick` | ☐ |
| e0.2 | `llm/ops_events.py` | details에 `stall_sec`, `idle_sec` int가 `_safe_details`로 허용되는지 확인 | ☐ |
| e0.3 | `api/app.py` `status()` | `"ingest_stall_detector": <env on>` | ☐ |
| e0.4 | env helpers | `ASR_INGEST_STALL_SEC` 기본 **300**, `0`=detector off | ☐ |
| e0.5 | 동일 | `ASR_INGEST_SWEEPER_SEC` 기본 **60** (또는 120), `0`=sweeper off | ☐ |
| e0.6 | `docs/design/168-audit-checklist.md` | 168e 하위에 e0–e5 링크/체크 반영 (선택) | ☐ |

### 테스트

| # | 내용 | 완료 |
|---|------|------|
| e0.t1 | allowlist emit round-trip (새 kind) | ☐ |
| e0.t2 | status 핀 + `ASR_INGEST_STALL_SEC=0` → flag false | ☐ |

### 하지 않음

실제 stall/sweep 로직, 라우트 추가.

---

## e1 — Translate progress clock + stall detector (D1.3 · D1.5)

### 목적

「서론 10/11」처럼 같은 stage 안에서 굳음을 서버가 N초 후 `translate_stalled`로 선언하고 job을 **terminal error**로 닫기. (클라이언트 5분 idle 504보다 **먼저**.)

### 앵커

- `_tr_progress` @ `api/app.py` (~translate ingest)
- `enrich_session_translations(..., on_progress=_tr_progress)`

| # | 파일 | 함수/위치 | 작업 | 완료 |
|---|------|-----------|------|------|
| e1.1 | `api/app.py` 또는 `llm/ingest_jobs_gcs.py` | `note_job_progress(job, …)` | `_progress_ts` (ISO UTC), `_progress_key` (`percent\|message`) | ☐ |
| e1.2 | `api/app.py` | `_tr_progress` | 매 호출 시 `note_job_progress` + 기존 `_job_set` | ☐ |
| e1.3 | `api/app.py` | `_job_set` (translate) | message/percent 변경 시에만 ts 갱신 | ☐ |
| e1.4 | `llm/translate_section.py` | enrich / `_tick` | (D1.3) 섹션 경계 `on_progress` 보강 필요 시 | ☐ |
| e1.5 | 신규 `llm/ingest_stall.py` (권장) | `translate_stall_sec() -> int` | env 파싱 | ☐ |
| e1.6 | 동일 | `check_translate_stall(job, *, now)` | `stage==translate` ∧ idle≥N → reason | ☐ |
| e1.7 | `api/app.py` | translate `to_thread` 바깥/주기 | emit `translate_stalled` → job error + fail-closed finish | ☐ |
| e1.8 | `api/app.py` | poll `GET …/ingest/jobs/{id}` | (선택) 응답 직전 stall check — worker 죽어도 terminal | ☐ |
| e1.9 | ops details | | `idle_sec`, `stall_sec`, `percent`만. message 전문 금지 | ☐ |

### 엣지

| # | 엣지 | 기대 | 완료 |
|---|------|------|------|
| e1.e1 | N=0 / kill | stall 판정 안 함 | ☐ |
| e1.e2 | `cancel_requested` | stall로 덮지 않음 | ☐ |
| e1.e3 | 이미 `done=true` | no-op | ☐ |
| e1.e4 | partial cache + stall error | `ingest_status`를 **ok로 올리지 않음** (T8) | ☐ |
| e1.e5 | progress가 드묾 | N=300 기본; 테스트는 fake clock | ☐ |

### 테스트

| # | 내용 | 완료 |
|---|------|------|
| e1.t1 | unit: 오래된 `_progress_ts` → stall reason | ☐ |
| e1.t2 | unit: 방금 progress → None | ☐ |
| e1.t3 | integration: mock enrich hang → job.error + event | ☐ |

### 하지 않음

번역 재시도 로직, skip_translate 강제, 모바일 UI 대개편.

---

## e2 — Reclaim 관측 (A1.19 · A1.8)

### 목적

`_reclaim_ingest_job_from_gcs`의 **모든 출구**에 ops event.

| # | 분기 | `details.reason` | 완료 |
|---|------|------------------|------|
| e2.1 | reclaim disabled | `reclaim_disabled` | ☐ |
| e2.2 | `_local_running` | `already_local` | ☐ |
| e2.3 | cancel / discarded | `cancelled` | ☐ |
| e2.4 | `try_claim_lease` → None | `lease_claim_failed` | ☐ |
| e2.5 | upload blob 없음 | `upload_missing` | ☐ |
| e2.6 | worker task 기동 성공 | `reclaimed` | ☐ |
| e2.7 | exception | `reclaim_exception` | ☐ |
| e2.8 | 각 return 직전 `oev.emit("reclaim_attempt", …)` | | ☐ |
| e2.9 | uid sanitize; filename 전문 금지 (`filename_len` OK) | | ☐ |

### 테스트

| # | 내용 | 완료 |
|---|------|------|
| e2.t1 | claim fail → `lease_claim_failed` | ☐ |
| e2.t2 | cancel → `cancelled` | ☐ |

### 하지 않음

reclaim 알고리즘·lease TTL 변경.

---

## e3 — Stuck job 나열 + Admin GET (J1.7)

### 목적

`done=false` ∧ (lease 만료 ∨ translate stall) 목록을 admin이 봄.

### GCS 스코프 (구현 전 고정)

Job은 `users/{uid}/ingest_jobs/` 유저별. 전역 scan 비용·권한 이슈.

| 옵션 | 내용 | 추천 |
|------|------|------|
| A | 인스턴스 `_JOBS`만 | MVP, 불완전 |
| B | 버킷 prefix walk | 완전, 비쌈 |
| C | A + `?job_id=` 단건 GCS load | **권장 MVP** |

| # | 파일 | 작업 | 완료 |
|---|------|------|------|
| e3.1 | `llm/ingest_jobs_gcs.py` | `job_is_stuck(job) -> (bool, reason)` | ☐ |
| e3.2 | 동일 | `public_stuck_row(job) -> dict` (본문·email·파일명 전문 금지) | ☐ |
| e3.3 | `api/app.py` | `GET /api/ops/ingest/jobs/stuck` · `_is_admin_user` | ☐ |
| e3.4 | 동일 | query: `limit`, optional `job_id` | ☐ |
| e3.5 | 동일 | `{ok, jobs, source: memory\|gcs}` | ☐ |

### 테스트

| # | 내용 | 완료 |
|---|------|------|
| e3.t1 | non-admin → 403 | ☐ |
| e3.t2 | lease 만료 memory job → 포함 | ☐ |
| e3.t3 | `done=true` → 제외 | ☐ |
| e3.t4 | cancel → 제외 | ☐ |

### 하지 않음

자동 삭제, 강제 reclaim 버튼.

---

## e4 — Cache integrity Admin GET (J1.8)

### 목적

`audit_cache` HTTP 노출. **수리 없음.**

| # | 파일 | 작업 | 완료 |
|---|------|------|------|
| e4.1 | `llm/ingest_integrity.py` | `violations_to_public(vs)` | ☐ |
| e4.2 | (선택) | `?refresh=1`만 GCS pull; 기본 local/meta | ☐ |
| e4.3 | `api/app.py` | `GET /api/ops/cache/{cache_id}/integrity` · admin · id regex | ☐ |
| e4.4 | 동일 | optional `job_id` → `audit_cache(..., job=)` | ☐ |
| e4.5 | (선택) | GET 기본 emit 안 함; `?emit=1`만 `emit_violations` | ☐ |

### 테스트

| # | 내용 | 완료 |
|---|------|------|
| e4.t1 | index/session mismatch → T4/T5 in body | ☐ |
| e4.t2 | bad cache_id → 400 | ☐ |
| e4.t3 | non-admin → 403 | ☐ |
| e4.t4 | missing → 404 | ☐ |

### 수동 QA (배포 후)

| # | 내용 | 완료 |
|---|------|------|
| e4.m1 | Ni/Cu 또는 acsanm `cache_id`로 GET → violation JSON 보관 | ☐ |

### 하지 않음

fig_meta rewrite, index patch, figure re-upload.

---

## e5 — Worker_lost sweeper (E1.3 · J1.10 · A1.6)

### 목적

lease 만료 zombie를 주기적으로 terminal 마킹. 정상 reclaim 기회를 죽이지 말 것.

### 정책

```text
IF stuck by lease_expired
AND not cancel
AND (reclaim failed / upload_missing / age > 2*lease_ttl)
THEN emit worker_lost
AND set job.error + done=true (fail-closed)
AND DO NOT invent cache_id
```

권장 순서: stuck 감지 → reclaim 1회(e2) → 그래도 stuck이면 mark_lost.

| # | 파일 | 작업 | 완료 |
|---|------|------|------|
| e5.1 | `ingest_stall.py` 또는 `ingest_jobs_gcs.py` | `sweep_candidate(job) -> none\|reclaim\|mark_lost` | ☐ |
| e5.2 | `api/app.py` | `_ingest_sweeper_loop` · `ASR_INGEST_SWEEPER_SEC` (0=off) | ☐ |
| e5.3 | lifespan/startup | `asyncio.create_task` | ☐ |
| e5.4 | sweeper body | `_JOBS` 순회 (+ 스코프 한계 문서화) | ☐ |
| e5.5 | mark path | `worker_lost` + 기존 error finish 헬퍼 | ☐ |
| e5.6 | | `_local_running`이면 mark_lost **금지** | ☐ |

### Cloud Run

| # | 내용 | 완료 |
|---|------|------|
| e5.c1 | 인스턴스 0이면 sweeper 안 돔 → poll e1.8 / e3 단건 보완 | ☐ |
| e5.c2 | 다중 인스턴스: mark idempotent (`save_ingest_job`) | ☐ |

### 테스트

| # | 내용 | 완료 |
|---|------|------|
| e5.t1 | lease 만료 + not running + no upload → worker_lost + done | ☐ |
| e5.t2 | `_local_running` → mark 안 함 | ☐ |
| e5.t3 | sweeper sec=0 → loop 미시작 | ☐ |

### 하지 않음

checkpoint 자동 수리, 조용한 재시작 성공 위장.

---

## 공통 — 버전·배포·문서

| # | 작업 | 완료 |
|---|------|------|
| z.1 | version 세 곳 bump `0.3.116` (APK 필요 시 mobile 포함) | ☐ |
| z.2 | tests 버전 핀 | ☐ |
| z.3 | [168-audit-checklist.md](168-audit-checklist.md) `### 168e` `[x]` | ☐ |
| z.4 | `pre_deploy_guard` → deploy → `verify_live_status --expect 0.3.116` | ☐ |
| z.5 | live stuck/integrity admin 스모크 | ☐ |

---

## 슬라이스 DoD

| 슬라이스 | DoD |
|----------|-----|
| **e0** | 새 kind emit 가능, status 핀, 테스트 그린 |
| **e1** | fake clock stall → job.error + `translate_stalled`; 정상 progress 보존 |
| **e2** | reclaim 모든 return에 reason event |
| **e3** | admin GET stuck 403/200 + memory fixture |
| **e4** | admin GET integrity가 T4/T9 fixture 반환; 쓰기 0 |
| **e5** | sweeper가 upload_missing zombie terminal; running job 보존 |

---

## Out of scope (= 168f 또는 별도)

| 항목 | 어디로 |
|------|--------|
| T9 `save_paper_session` fig stub 유지 | 168f |
| 과거 index `ok` → `partial` 일괄 이주 | 168f |
| H1.5 reanalyze resume | 168f |
| G1.8 empty row merge 보고 | 168d 잔여 / 168f |
| `_syncCursor` soft report | 별도 |
| figure PNG 재추출·재업로드 | 168f / 수동 |
| GitHub Actions cron-only sweeper | e5 후속 선택 |

---

## 관련 체크포인트 (audit)

- A1.6 lease / A1.8 claim / A1.19 reclaim events  
- D1.3 translate tick / D1.5 server stall  
- E1.3 `_finish_job` / worker_lost  
- J1.7 stuck GET / J1.8 integrity GET / J1.10 sweeper  
