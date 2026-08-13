# 130 — Cloud error logs (detect · store · admin badge)

Modules: `llm/error_logs.py` · `api/app.py` · Flutter `error_reporter` / `hang_watchdog` / `error_logs_screen` · Settings  
받침: [08](08-errors.md) · [10](10-security-limits.md) · [22](22-google-auth-gcs.md) · [67](67-access-gate.md) · [68](68-mobile-shell-nav.md)

## 무엇인가

과도기 앱에서 실패·타임아웃·**무한 로딩/같은 작업 무한 반복**을 잡고,  
로그를 **클라우드(GCS 공유 칸)**에 쌓아 **관리자**가 설정 **오류 로그**(배지)로 본다.  
다른 계정·기기 오류도 관리자만 모아 고친다.

| 포함 | 미포함 |
|------|--------|
| `POST /api/errors/report` (로그인 유저) | 관리자 이메일/푸시 알림 |
| `GET /api/errors/admin` · badge · seen | 캡션 말줄임 · 처리 취소 |
| GCS `error_logs/` + 로컬 폴백 | 새 추출 파이프라인 |
| Flutter 전역 핸들러 + hang watchdog | APK 자체 업데이트 |
| 설정 「서버」→「오류 로그」교체 | |
| 킬 `ASR_CLOUD_ERROR_LOGS=0` · report rate limit | |

## Product (locked)

1. 탐지 촘촘 + 로그 꼼꼼 → **클라우드 저장**
2. 관리자: **남의 로그 포함** 조회 (일반 유저 상호 비공개)
3. 알림 = 설정 **배지만** (이메일 없음)
4. UI: 관리자 **서버 버튼 → 오류 로그** 교체
5. 로그에 **논문 제목·cache id** 허용 · 토큰/비밀번호 금지
6. 앱 전체(미포착·API·hang) — 1차는 전역 훅 + API/열기 hang
7. Hang: 짧은 API **45s** · ingest 진전 없음 **3분** · 동일 단계 진전 없이 **5회**

## Kill / rollback

- `ASR_CLOUD_ERROR_LOGS=0` → report/list no-op / 403-ish off (status flag false)
- Revert PR · 이전 APK

## Live Enable / IPS

이번 칩에서 불필요함.

## Version

**0.3.46**

## Device pin (E2E)

- Live `/api/status`: `version=0.3.46` · `cloud_error_logs=true`
- APK `versionName=0.3.46` · SM-G986N
- Settings (admin): 「서버」없음 · 「오류 로그」타일 → 화면 「아직 수집된 오류가 없습니다.」(배포 전 404는 실패 표시, 빈 성공 아님)
- Live unauth: `POST /api/errors/report` · `GET /api/errors/admin` · badge → **401**
- Kill: `ASR_CLOUD_ERROR_LOGS=0` · revert PR · prior APK

Do not paste session cookies, tokens, or full stacks with secrets into docs.
