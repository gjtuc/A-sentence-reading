# 105 — Upload fail notification + longer ingest poll

Modules: `upload_notify.dart` · `UploadForegroundService.kt` · `MainActivity.kt` · `client.dart` · `library_controller.dart`  
받침: [74](74-bg-upload-notify.md) · [71](71-mobile-upload-resume.md)

## 무엇인가

업로드·서버 처리가 **실패/타임아웃**하면 알림이 조용히 사라지지 않고 **「업로드 실패」**로 남는다.  
인제스트 폴링 한도는 **12분 → 20분** (품질 추출 등 긴 PDF 대비).

| 포함 | 미포함 |
|------|--------|
| 실패 시 result 알림 (DEFAULT) | 서버 OCR/품질 단계 가속 |
| 타임아웃 문구에 마지막 stage | iOS |
| 폴링 20분 | Live Enable / IPS |
| 진행 중 채널은 기존 LOW 유지 | |

## Product (locked)

1. Fail/timeout → shade에 **업로드 실패** (성공인 척 금지)  
2. 진행 중 heads-up은 강제하지 않음 (LOW 유지)  
3. Poll timeout **20분** · 초과 시 실패 알림 + 앱 에러  
4. 알림 문구에 이메일·경로·토큰 금지

## Kill / rollback

- Revert PR · `ASR_MOBILE_UPLOAD_BACKGROUND=0` (기존 FG 킬)

## Version

**0.3.19** · status + pubspec

## Live Enable / IPS

이번 칩에서 불필요함.

## Device / pytest

- Dart: `showFailed` → native `showUploadFailed` (stop-only 제거)
- Native: `asr_upload_result` channel · fail notif id
- poll timeout 20m · timeout message may include stage
- 실기: 빠른 실패 경로 또는 채널 생성 + 코드 경로 확인

## Device pin (E2E)

- APK `versionName=0.3.19` · `adb install -r` (SM-G986N)
- Source: `showFailed` → `showUploadFailed` / `UPLOAD_FG_FAIL` · result channel `asr_upload_result` (DEFAULT)
- Poll timeout **20** minutes · timeout error may append last stage
- Note: FG service is **not exported** (AuthZ) — adb cannot start it from shell; fail banner is exercised via app `showFailed` path (pytest + code). Next real timeout should show shade「업로드 실패」.

Do not paste emails, cookies, tokens, or paper titles into chat/PR.
