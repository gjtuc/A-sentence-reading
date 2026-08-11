# 107 — Ingest job reclaim across Cloud Run instances

Modules: `ingest_jobs_gcs.py` · `api/app.py` (`ingest_job_status`, `_run_ingest_job`)  
받침: [71](71-mobile-upload-resume.md) · [106](106-ingest-quality-timeout.md) · [25](25-cloud-run.md)

## 무엇인가

Cloud Run에서 인제스트가 **한 인스턴스 `asyncio.create_task`에만** 묶여 죽으면 GCS에 **12% 시체**만 남는 근원을 고친다.  
소유자 폴링이 **리스가 만료된** 미완료 job을 보면, GCS에 남은 원본으로 **다른 인스턴스가 처리를 다시 시작**한다.

| 포함 | 미포함 |
|------|--------|
| job **lease** (`lease_until` + `lease_token`) + 주기적 heartbeat | 파이프라인 중간 stage부터 정밀 resume |
| lease 만료 + 원본 blob 있으면 **재시작** (`create_task`) | Gemini 모델/프롬프트 변경 |
| 소유자 세션만 reclaim 트리거 | 클라이언트 필수 UI 변경 |
| kill `ASR_INGEST_JOB_RECLAIM=0` | Live Enable / IPS |

## Product (locked)

1. 워커가 살아 있으면 lease를 갱신한다 → **정상 진행 중엔 다른 인스턴스가 가로채지 않음**  
2. lease가 만료되고 원본 `ingest_uploads` blob이 있으면 **같은 job_id로 처리 재시작** (처음부터 다시; 캐시 히트 가능)  
3. 남의 `job_id` / 비로그인 → 기존처럼 **404/401** (존재 누설 최소화)  
4. 원본 blob 없으면 reclaim하지 않음 (빈 성공·가짜 완료 금지)  
5. 진행률을 가짜로 올리지 않음 — 재시작 시 메시지만 「처리 다시 시작」

## Kill / rollback

- `ASR_INGEST_JOB_RECLAIM=0` → reclaim off (폴링·GCS job 기록은 유지)  
- Revert PR

## Version

**0.3.21** · status `ingest_job_reclaim` · pubspec pin

## Live Enable / IPS

이번 칩에서 불필요함.

## Device / pytest

- lease 만료 + upload blob → poll이 worker task를 다시 띄움  
- lease 유효 → reclaim 안 함  
- 유저 B가 A job reclaim/조회 → 404  
- 실기: live status 플래그 + 소형 PDF가 quality 12%에 영구 고착되지 않고 진행

Do not paste emails, cookies, tokens, or paper titles into chat/PR.
