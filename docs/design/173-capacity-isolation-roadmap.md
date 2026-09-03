# 173 — Capacity & isolation roadmap (access hot path · Run size · workers)

Modules: `access_gate.py` · `app.py` · `deploy_cloud_run.sh` · (later) worker service  
받침: [25](25-cloud-run.md) · [69](69-access-gate-gcs.md) · [84](84-access-waiting-ux.md) · [107](107-ingest-job-reclaim.md) · [155](155-deploy-live-guard.md) · [172](172-access-sticky-on-timeout.md)

## 왜 (핵심)

제품은 rich 파이프라인·Gemini 번역·그림·쉐도잉까지 커졌는데, live Cloud Run은 여전히:

| Live (0.3.147) | 값 |
|----------------|-----|
| CPU / RAM | **1 vCPU / 1Gi** |
| instances | min 1 · max **3** |
| process | **uvicorn 1** (workers 없음) |
| concurrency / instance | **80** (default) |
| heavy work | **API와 동일 프로세스** (`asyncio.create_task`) |
| `/api/access/status` | 로그인 시 **매 호출** `refresh_access_gate_from_gcs()` (GCS ≤4, **TTL 없음**) |

그 결과 “조금 바쁜” 인스턴스에서 access/auth가 타임아웃 → (172 이전) 승인 대기 튕김.  
**172는 UX 증폭만 완화.** 이 문서는 **원인 쪽** 로드맵이다.

진단 캔버스(참고): 채팅 세션 `asr-server-bottleneck.canvas.tsx`.

## 무엇인가

세 **강제 위상**으로 공장(무거운 일)과 창구(짧은 RPC)를 나눈다.

| Phase | 이름 | 한 줄 |
|-------|------|--------|
| **173a** | Access hot-path cache | status/paid 가드의 **매요청 full GCS** 제거 (TTL) |
| **173b** | Run capacity bump | CPU/RAM/concurrency/throttling/maxScale을 제품에 맞춤 |
| **173c** | Worker isolation | ingest·translate를 API 프로세스 밖으로 |

| 포함 | 미포함 |
|------|--------|
| TTL·in-proc 캐시 · 배포 스펙 · 워커 설계 | Gemini 모델/프롬프트 변경 |
| kill env · 증거/status 플래그 | Live Enable / IPS |
| design/69 Allow 전파 SLA 명시 | 클라 sticky 제거 (172 유지) |

## Product (locked) — 공통

1. **유료 API fail-closed 유지** — 캐시/워커 오류로 미승인에게 유료 성공 UI·성공 API를 열지 않음.  
2. **Allow 전파 SLA** — 관리자 Allow 후 다른 인스턴스/클라이언트가 **≤ 60s** 안에 `can_use_paid`를 봄 (173a TTL 상한과 동일).  
3. **Deny는 즉시성 우선** — Deny/revoke 직후 paid는 **가능하면 즉시** 막음 (캐시 invalidate on write).  
4. **172 sticky 유지** — 서버가 느려도 승인 대기 오진 금지.  
5. **155 deploy guard 유지** — 스펙/워커 배포도 버전 bump + pre_deploy_guard.  
6. **위상 순서 강제:** **173a → 173b → 173c**. c를 a/b 없이 먼저 하지 않음 (관측·핫패스 없이 워커만 키우면 비용·복잡도만 증가).

---

## 173a — Access hot-path cache (첫 칩)

### 목표

로그인된 `GET /api/access/status` 와 `user_may_use_paid` 가 **매 히트마다 4× GCS** 하지 않게 한다.

### Product (locked)

1. 프로세스 메모리 캐시: `accounts` + invite/events/redeem merge 결과.  
2. **TTL 기본 45s** (env `ASR_ACCESS_GATE_TTL_S`, clamp **5–60**). 60s = Allow SLA 상한.  
3. **Write 경로 invalidate (즉시):** mint / redeem / admin decide(Allow·Deny) / 로컬 gate write 성공 시 캐시 폐기 → 다음 호출은 GCS pull.  
4. `GET /api/access/status`: TTL 유효하면 **refresh 스킵**, `public_access_view`만.  
5. `user_may_use_paid`: TTL 유효하면 refresh 스킵. **만료·miss만** pull.  
6. 부트(lifespan)는 기존처럼 1회 refresh (워밍).  
7. status JSON에 관측 필드: `access_gate_cache` = `{ttl_s, hit_ratio optional}` 또는 `access_gate_ttl_s`.  
8. GCS 실패 시: **마지막 성공 스냅샷이 있으면 TTL 동안 유지** (창구 생존). 스냅샷 없으면 기존 fail-soft/fail-closed (paid deny).

### 왜 45s인가

- design/69: 다른 인스턴스 Allow가 “영원히” 안 보이면 안 됨 → 상한 60s.  
- 폴링(대기 셸 5s, resume refresh)이 45s 안에 여러 번 GCS를 때리지 않게.  
- Deny invalidate로 “허용이 풀린 뒤에도 오래 열림”은 write 경로에서 차단.

### Kill / rollback

- `ASR_ACCESS_GATE_TTL_S=0` → 캐시 off (매요청 refresh = 69 구동작).  
- Revert PR.

### Acceptance

- [ ] 단위: TTL 내 두 번째 `refresh_access_gate_from_gcs` 호출이 download를 안 함 (mock).  
- [ ] decide Allow/Deny 후 같은 프로세스에서 즉시 새 status 반영 (invalidate).  
- [ ] live: 번역 중인 인스턴스에서 `/api/access/status` p95가 유의미히 하락 (전후 evidence/`client_api_timeout` route=`access_status` 감소).  
- [ ] 다른 인스턴스 Allow → **≤60s** 내 paid 가능 (또는 폴링으로 진입).

### Version

**0.3.148** (예정) · 이 칩만 먼저 배포 가능.

---

## 173b — Cloud Run capacity bump

### 목표

한 논문 ingest/translate가 인스턴스를 먹어도 **짧은 RPC가 20s 안에 살** 여유를 만든다.  
(173a 이후 — 캐시 없이도 버티는 물리적 여유.)

### Product (locked)

| 설정 | 현재 | 목표 (locked) |
|------|------|----------------|
| `--memory` | 1Gi | **2Gi** |
| `--cpu` | 1 | **2** |
| `--max-instances` | 3 | **6** (초기; 비용 보고 조정) |
| `--concurrency` | 80 (default) | **16** (명시) |
| CPU throttling | default on | **`--no-cpu-throttling`** |
| `--min-instances` | 1 | **1** 유지 (콜드스타트 완화 유지) |
| `--timeout` | 300 | **300** 유지 |

### 왜 concurrency를 낮추나

80은 “가벼운 JSON API”용. 이 서비스는 요청 하나가 스레드·Gemini·메모리를 먹는다.  
concurrency를 낮추면 Cloud Run이 **더 빨리 스케일 아웃**하고, 한 박스에 폴링+잡이 몰리는 정도를 줄인다.

### Kill / rollback

- deploy 스크립트 값을 이전으로 되돌리고 재배포 (155 가드: 버전 bump 필요 시 패치 버전).  
- env만으로 되돌리기 어려움 → 스크립트 SoT.

### Acceptance

- [ ] `gcloud run services describe` 가 표의 목표와 일치.  
- [ ] 단일 논문 번역 중 같은 계정 `access/status` 타임아웃 rate 감소 (172 sticky와 독립 측정).  
- [ ] OOM/리비전 크래시 비율이 이전 대비 악화되지 않음.

### Version

**0.3.149** (예정) · 173a 이후. 코드 변경 최소·배포 칩.

### 비용 메모

CPU 2 + no-throttling + max 6은 청구 상승. 베타 단일 주 사용자면 체감 가치 ≫ 비용.  
다중 테넌시 전에 maxScale·minScale 재검토.

---

## 173c — Worker isolation

### 목표

ingest / 장시간 translate / heavy reanalyze 가 **API 컨테이너의 요청 경로·CPU를 직접 점유하지 않게** 한다.

### Product (locked) — 방향

1. **API 서비스** (`asr-sentence-reading`): auth, access, library list/open(메타), job **enqueue**, status poll.  
2. **Worker 서비스** (`asr-sentence-reading-worker` 가칭): GCS job lease를 소비해 `_run_ingest_job_body` 계열 실행.  
3. Job 진실은 기존 **GCS ingest jobs** (design/107 lease) 를 확장 — 새 DB 필수 아님.  
4. API는 `create_task`로 본문을 돌리지 않고 **enqueue + 필요 시 “같은 리전에 worker 깨우기”** (HTTP 내부 또는 Cloud Tasks).  
5. Worker도 155/169g 가드·동일 이미지 태그 또는 공유 패키지.  
6. 실패 시 job은 running/lease 만료 → 107 reclaim 의미 유지.

### 비목표 (173c MVP)

- 번역만 따로 마이크로서비스 분리 (ingest 워커 안에 번역 유지 OK).  
- 멀티 리전.  
- 오토스케일 세밀 FinOps 대시보드.

### 구현 스케치 (잠정)

```
Client → API /ingest → save upload blob + job JSON (queued)
                    → notify worker (or worker polls queued)
Worker → claim lease → run pipeline → GCS session/figures
Client → poll job_status (API, light)
```

### Kill / rollback

- `ASR_INGEST_INLINE=1` (가칭) → API in-process `create_task` 구경로 (107과 공존).  
- Worker 서비스 traffic 0% + API inline.

### Acceptance

- [ ] API 인스턴스 CPU가 대용량 ingest 중에도 access/status p95 < 2s (캐시 히트 시).  
- [ ] Worker 사망 시 107 lease 만료 후 다른 worker/API reclaim.  
- [ ] 폰 업로드 E2E 성공 (기존 71/105 계약).

### Version

**0.3.150+** (예정) · 다수 PR. 173a/b 없이 착수 금지.

---

## 관측 (전 phase)

| Signal | 용도 |
|--------|------|
| `client_api_timeout` route=`access_status` | 창구 실패 (172 이후에도 서버 건강 지표) |
| `/api/status` `access_gate_ttl_s` / cache | 173a 켜짐 |
| Cloud Run CPU/mem utilization | 173b |
| ingest job `lease` + worker instance id | 173c |
| evidence: `access_gate_refresh` (optional kind) | pull 횟수 vs status 히트 |

새 kind를 넣으면 **evidence floor add-only** (169g).

---

## 강제 순서 / 의존

```
172 sticky (done 0.3.147)
    ↓
173a TTL cache          ← 즉시 체감 · 저위험
    ↓
173b Run size/concurrency
    ↓
173c Worker service     ← 구조 해법
```

- 173b만 하고 173a를 스킵하지 말 것: concurrency·CPU를 키워도 **매 status마다 GCS×4**면 창구가 다시 죽음.  
- 173c만 먼저 하지 말 것: 관측·핫패스·용량 없이 워커는 운영 면만 키움.

---

## Agent / 배포 규칙

- 새 채팅: `python scripts/session_freshness_guard.py` (155/전역 룰).  
- 각 phase 배포: app+pubspec+config **동시 bump**, `pre_deploy_guard`, 전역 deploy hook.  
- `ASR_SKIP_DEPLOY_GUARD` 비상만.

## Live Enable / IPS

불필요.

Do not paste emails, cookies, tokens, or invite codes into chat/PR.
