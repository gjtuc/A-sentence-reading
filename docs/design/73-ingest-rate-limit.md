# 73 — Ingest / upload call-count rate limit

모듈: `ingest_rate_limit.py` · `app.py` `_ingest_rate_limited`  
받침: [72-chunked-upload.md](72-chunked-upload.md) · [67-access-gate.md](67-access-gate.md) (redeem 한도 패턴)

## 무엇을

로그인 유저(세션 UID)별 **호출 횟수** 슬라이딩 창 한도.  
업로드 세션 생성 · 조각 PUT · ingest 시작(multipart·complete)에 적용.

| 포함 | 미포함 (후속) |
|------|----------------|
| 횟수·빈도 한도만 | **파일 용량 한도 신설** (하지 않음) |
| `upload_create` / `upload_put` / `ingest_start` | 하루(daily) 캡 |
| 429 + 문구 `요청이 너무 많습니다.` | OS 백그라운드 알림 |
| `ASR_INGEST_RATE_LIMIT=0` 킬스위치 | IP 기반 한도 |
| status `ingest_rate_limit` | 매직링크 |

## 기본값 (환경변수로 조절 · daily 없음)

| action | max | window |
|--------|-----|--------|
| `upload_create` | `ASR_UPLOAD_CREATE_MAX`=12 | `ASR_UPLOAD_CREATE_WINDOW_SEC`=600 |
| `upload_put` | `ASR_UPLOAD_PUT_MAX`=600 | `ASR_UPLOAD_PUT_WINDOW_SEC`=600 |
| `ingest_start` | `ASR_INGEST_START_MAX`=10 | `ASR_INGEST_START_WINDOW_SEC`=600 |

PUT 상한은 50MB÷256KiB≈200에 여유. **크기 검사와 별개** — 이번 칩은 횟수만.

## INVARIANT

- user = 세션 UID만 (`anon_unauth` 버킷은 비로그인 공용)
- 바디/쿼리 `user_id` 신뢰 금지
- 거절 시 성공 UI·job 시작 금지
- Live Enable / IPS — **이번 칩 불필요**

## Kill / rollback

- `ASR_INGEST_RATE_LIMIT=0` → 한도 검사 off
- Revert PR · status 키 false/무시

## Version

Web/mobile **0.2.99** · pubspec `0.2.99+1`

## Device / live E2E (2026-08-10)

1. Live Cloud Run `/api/status`: `version=0.2.99`, `ingest_rate_limit=true` (browser + Invoke-RestMethod)
2. Sideload APK `versionName=0.2.99` · Google 로그인 · Settings→서버: `version | 0.2.99`
3. Local uvicorn (`ASR_UPLOAD_CREATE_MAX=2`, gate off): user A 3rd create → **429** `요청이 너무 많습니다.` · user B still 200 (isolation)
4. Live throwaway email create → `access_denied` (gate) before quota — expected; paid-path 429 covered by local + pytest
5. Flutter unit: `createChunkedUpload` surfaces 429 copy (no success)

Do not paste emails, cookies, or paper titles into chat/PR.
