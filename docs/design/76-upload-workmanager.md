# 76 — WorkManager upload resume (process death)

모듈: Android `UploadResumeWorker` · `UploadResumeScheduler` · `upload_notify` channel · `library_controller`  
받침: [71](71-mobile-upload-resume.md) · [72](72-chunked-upload.md) · [74](74-bg-upload-notify.md) · [75](75-upload-interrupt-resume.md)

## 무엇을

앱 **프로세스가 죽어도** OS WorkManager가 draft를 읽어 **조각 전송 + job 폴링**을 이어간다.  
재개 중에도 **알림을 항상** 유지한다.

| 포함 | 미포함 |
|------|--------|
| Native WorkManager (Flutter pub 추가 없음) | iOS BG |
| chunk PUT + job poll 둘 다 | 다파일 |
| 진행 중 알림 항상 (product 2A) | 매직링크 |
| 배터리 설정 안내 버튼 1회/작업 (3C→무시 시 재표시 금지) | Live Enable / IPS |
| status `mobile_upload_workmanager` | |

## Product (locked)

1. **A** — 프로세스 종료 후에도 네트워크 되면 자동 재개  
2. **A** — 재개 중 알림 항상  
3. **C→A** — 배터리 제한 시 설정 안내 버튼; **같은 content_hash 작업**에서 한 번 무시하면 다시 안 띄움  
4. **A** — chunk + processing poll 둘 다  

## 동작

- 업로드 시작·progress: unique work **REPLACE** + 초기 delay(~60s) — 살아 있으면 타이머 리셋  
- stall(75): **REPLACE** immediate enqueue  
- 성공/실패/clear: cancel  
- Worker: Flutter prefs `flutter.asr.upload_draft.v1` + `flutter.asr.session.v1` 읽기 → HTTP (쿠키만; work input에 토큰 금지)  
- FG 알림: 기존 `UploadForegroundService` 재사용  

## INVARIANT

- Work input / 알림에 세션·이메일·경로 비밀 금지  
- 실패를 성공 알림으로 포장 금지  
- Live Enable / IPS — **이번 칩 불필요**

## Kill / rollback

- `ASR_MOBILE_UPLOAD_WORKMANAGER=0` → status false → 클라 enqueue 생략 (71/75 유지)  
- Revert PR · APK 다운핀  

## Version

**0.2.97** · pubspec `0.2.97+1`

## Device E2E (pre-merge)

- APK `versionName=0.2.97` · SM-G986N
- Mid-upload soft-kill (`am crash` / process death; **not** `force-stop` which cancels WM). Shell `kill -9` may be denied (UID).
- **Worker-only proof (no MainActivity reopen):** logcat `UploadResumeWorker: E2E76_WM doWork start` + `E2E76_WM resume phase=…` while FG upload notification stays (`E2E76 PASS`)
- Manifest `<queries>` include `OPEN_DOCUMENT` / `GET_CONTENT` so file_picker works after clean boot
- ProGuard keep for WorkManager Room (`proguard-rules.pro`) — prevents InitializationProvider crash
- MULTI-USER: logout → `library.clearAll()` cancels unique WM work + clears draft
- Kill: `ASR_MOBILE_UPLOAD_WORKMANAGER=0`
- Live Enable / IPS: unchanged (이번 칩 불필요)

Do not paste emails, cookies, or paper titles into chat/PR.

## Live pin (post-merge)

- Cloud Run `/api/status`: `version=0.2.97`, `mobile_upload_workmanager=true`
- Device APK `versionName=0.2.97` · SM-G986N
- E2E: soft process death → `E2E76_WM` Worker log + resume notification (`E2E76 PASS`)
- Kill: `ASR_MOBILE_UPLOAD_WORKMANAGER=0`
- Live Enable / IPS: unchanged

