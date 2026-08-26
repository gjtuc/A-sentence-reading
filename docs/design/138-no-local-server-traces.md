# 138 — Remove local-server traces (Live + device only)

Modules: `autostart.py` · `setup.py` · `README` · Flutter `config`/`settings` · `app.js` hang E2E hooks · Android cleartext · `api/app.py` status  
받침: [25](25-cloud-run.md) · [33](33-mobile-flutter.md) · [134](134-ingest-upload-hang.md)

## 무엇인가

로컬 uvicorn(`127.0.0.1:8770` 등)을 **제품·앱·문서·자동시작**에서 지운다.  
검증·실사용은 **폰 APK → Live(Cloud Run)** 만. `adb reverse`·LAN cleartext·설정 hang 시뮬 금지.

| 포함 | 미포함 |
|------|--------|
| Windows autostart 등록 중단 · 설치 시 unregister | pytest `TestClient` (서버 프로세스 없음) |
| README 「로컬 실행」·autostart 안내 제거 → Live만 | Cloud Run Dockerfile의 uvicorn |
| 앱 `ASR_API_BASE` dart-define 제거 · Live URL 고정 | APK 자체 업데이트 |
| 설정 「업로드 hang 시뮬 (로컬)」 제거 | hang **감지** 자체 (design/134) |
| 웹 `__asrHangE2E` · loopback cleartext 예외 제거 | Fig 점프 · MVP 다듬기 |
| APK **0.3.56** 빌드·실기 설치 | Live Enable / IPS |

## Product (locked)

1. **A** — 제품 경로에서 로컬 주소·로컬 전용 버튼·자동시작 **전부** 제거  
2. hang 시뮬은 **이 칩에서 같이** 제거 (설정 WIP 별도 칩 없음)  
3. README 등 사용자 문서에서 로컬 실행 안내 **삭제** · Live URL만  
4. **APK 0.3.56** 빌드·설치 포함 · 폰+Live E2E  
5. CI/pytest는 프로세스 없는 TestClient 유지 (사용자용 로컬 서버 아님)

## Kill / rollback

- Revert PR · 이전 APK `0.3.55`  
- (복구 시) `python -m sentence_reading.autostart register` 는 **거부** — 옛 커밋 필요

## Live Enable / IPS

이번 칩에서 불필요함.

## Version

**0.3.56** · pipeline **rich-v15** (추출 변경 없음)

## Device / E2E pin

- SM-G986N APK **0.3.56** installed (`versionName=0.3.56`)
  - Settings: **업로드 hang 시뮬 (로컬)** absent · no `8789` / `127.0.0.1` on UI
  - Library tab against Live: **보관 7건** (cloud list loads)
- `python -m sentence_reading.autostart register` → exit 1 (refuse)
- `python -m sentence_reading.autostart unregister` → clears leftover Ensure Server task
- Live `/api/status` after CD: expect `version=0.3.56` · `live_only=true` · `mobile_live_only=true`
- Kill: revert PR · prior APK 0.3.55

Do not paste emails, cookies, tokens, or secrets into chat/PR.
