# 75 — Upload interrupt auto-resume (phone call · OEM pause)

모듈: `library_controller.dart` · `upload_notify.dart` · `home_shell.dart`  
받침: [71-mobile-upload-resume.md](71-mobile-upload-resume.md) · [72-chunked-upload.md](72-chunked-upload.md) · [74-bg-upload-notify.md](74-bg-upload-notify.md)

## 무엇을

전화·OEM 절전 등으로 **진행 heartbeat가 멈추면** 알림/화면을 정직하게 「중단」으로 바꾸고,  
앱이 **다시 앞으로 오면** draft를 **자동 재개**한다 (design/71 경로).

| 포함 | 미포함 (후속) |
|------|----------------|
| Lifecycle paused/inactive + stall watchdog | iOS BG |
| resumed 시 draft auto-resume | WorkManager 재시작 큐 (B) |
| 알림 「중단됨 · 탭하여 이어가기」 | 별도 upload isolate (C) |
| status `mobile_upload_interrupt_resume` | 매직링크 · 다파일 |
| 무진행 시 가짜 % 금지 | Live Enable / IPS |

## Product (locked · approach A)

1. **중단 감지**: 업로드 중 progress heartbeat가 `45s` 없으면 stall.
2. **정직한 UI**: stall 시 stage/알림을 「중단됨 · 앱을 열면 이어갑니다」로 교체 (완료/성공 금지).
3. **자동 재개**: `AppLifecycleState.resumed`에서 kill switch on이면 draft가 있을 때 `resumePendingIfAny` (stale in-flight면 uploading lock 해제 후 재개).
4. **OEM 한계**: 백그라운드에서 Dart가 완전히 죽으면 알림 탭/앱 재오픈으로 재개 (B/C는 후속).

## INVARIANT

- 알림에 이메일·토큰·경로 금지
- user는 세션만 — 클라 `user_id` 없음
- 실패/중단을 성공 알림으로 포장 금지
- Live Enable / IPS — **이번 칩 불필요**

## Kill / rollback

- Env: `ASR_MOBILE_UPLOAD_INTERRUPT_RESUME=0` → status `mobile_upload_interrupt_resume: false`
- Client: flag false면 stall 표시·강제 resume 생략 (71 cold-open resume은 유지)
- Revert PR · APK 다운핀

## Version

Web/mobile **0.2.93** · pubspec `0.2.93+1`

## Device E2E

1. APK `0.2.93` · live flag true
2. 업로드 시작 → 알림 → (가능하면) 통화/장시간 pause 시뮬레이션 또는 force-stop 없이 Home+지연
3. stall 문구 또는 resumed 후 이어올리기·완료
4. 실패 시 성공 알림 없음

Do not paste emails, cookies, or paper titles into chat/PR.

## Live pin (post-merge)

- Cloud Run \/api/status\: \ersion=0.2.93\, \mobile_upload_interrupt_resume=true- Device APK \ersionName=0.2.93\ · SM-G986N
- E2E: mid-upload airplane → STALL_VISIBLE → network/app resume → resumeish=True
- Kill: \ASR_MOBILE_UPLOAD_INTERRUPT_RESUME=0- Live Enable / IPS: unchanged

