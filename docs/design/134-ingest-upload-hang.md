# 134 — Ingest/upload hang on no progress (wire to upload path)

Modules: Flutter `hang_watchdog` · `library_controller` · `error_reporter` · web `app.js` · `api/app.py`  
받침: [130](130-cloud-error-logs.md) · [75](75-upload-interrupt-resume.md) · [76](76-upload-workmanager.md) · [132](132-ingest-cancel.md) · [133](133-logout-session-isolation.md)

## 무엇인가

130에서 ingest **진전 없음 3분** hang 규칙은 있었지만, **보관 열기**에만 연결되고 **업로드·정제 경로**에는 `HangWatchdog`가 안 붙었다.  
기존 45s `_stallWatch`는 “중단 · 이어올리기” 힌트(75/76)일 뿐, **오류 로그·실패 UI**가 아니다.  
진전 없이 폴링/자동 재시도만 반복되면 성공인 척 로딩이 남을 수 있다 (공유 클라우드에서 치명).

| 포함 | 미포함 |
|------|--------|
| 업로드·poll 경로에 `HangWatchdog.ingestStall` 연결 | 132 취소 API **자동** 호출 |
| 진전( % 상승 · 단계 전진 )일 때만 시계 갱신 | 표지→그림 #1 · 캡션 분할 |
| hang → 로컬 실패 UI + `POST /api/errors/report` | 45s soft-stall/WM 동작 제거 |
| status `ingest_upload_hang` · stall 초(환경변수) | |
| 웹 ingest poll 동일 규칙 | |
| **0.3.50** | |

## Product (locked)

1. **멈춤** = 한 번의 올리기/정제 시도 안에서 **의미 있는 진전이 N초 동안 없음** (기본 N=180). 벽시계 “시작 후 N분 무조건 컷” 아님.
2. 단계 라벨만 바뀌거나 같은 % 폴링·자동 재시도로 **시계를 리셋하지 않음**. 사용자가 파일을 다시 고르거나 명시적 재시도만 새 시도.
3. hang 시 **로컬 discard + 실패 문구** (성공/무한 busy 금지). 서버 cancel API는 이 칩에서 자동 호출 안 함.
4. hang은 **오류** → 130 클라우드 오류 로그로 보고 (비밀·쿠키·파일 본문 금지).
5. 킬: `ASR_INGEST_UPLOAD_HANG=0` · stall 초 `ASR_INGEST_HANG_STALL_SEC` (기본 180, E2E만 짧게).

## Kill / rollback

- `ASR_INGEST_UPLOAD_HANG=0` → status false → 클라 hang begin 생략  
- Revert PR · 이전 APK  
- Soft 45s interrupt/resume(75)은 유지

## Live Enable / IPS

이번 칩에서 불필요함.

## Version

**0.3.50**

## Device / E2E pin

- Live `/api/status`: `version=0.3.50` · `ingest_upload_hang=true` · `ingest_hang_stall_seconds=180`
- Local E2E: stall 초를 짧게 두고 진전 없는 job에서 실패 UI + (로그인 시) errors/report
- APK `0.3.50` · SM-G986N: 업로드 경로 hang 배선·실패 문구 (또는 짧은 stall 빌드/로컬 서버)

Do not paste session cookies, emails, or secrets into docs.
