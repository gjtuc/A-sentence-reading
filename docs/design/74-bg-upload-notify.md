# 74 — Background upload notification (chunk + process)

모듈: `upload_notify.dart` · `library_controller.dart` · `home_shell.dart` · Android FG service  
받침: [72-chunked-upload.md](72-chunked-upload.md) · [73-ingest-rate-limit.md](73-ingest-rate-limit.md)

## 무엇을

PDF 업로드가 시작되면 **항상** 알림을 띄우고, 앱이 뒤로 가도 **조각 전송 + 서버 처리 폴링**이 이어지게 한다.  
완료 알림을 탭하면 **가능하면 그 논문 읽기**로 연다.

| 포함 | 미포함 (후속) |
|------|----------------|
| 업로드 시작 시 알림 항상 | iOS BG upload |
| FG 서비스로 chunk + job poll 유지 | WorkManager 재시작 큐 |
| 알림 권한 거부 → 업로드는 진행 + 안내 | 매직링크 |
| 완료 탭 → 해당 paper open | 다파일 동시 업로드 |
| status `mobile_upload_background` | 알림에 파일명/이메일 노출 |
| | 전화·OEM 중단 자동 재개 → [75](75-upload-interrupt-resume.md) |

## Product (locked)

1. 알림: 업로드 시작 시 **항상**
2. 백그라운드: **보내는 중 + 처리 중** 둘 다
3. 권한 거부: 업로드 허용 + “백그라운드·알림 없이는 끊길 수 있음” 안내
4. 완료 탭: **그 논문 읽기** (없으면 보관 탭)

## INVARIANT

- 알림 문구에 이메일·토큰·전체 경로·실명 금지
- user/session은 기존 클라 쿠키만 — 알림 payload에 세션 넣지 않음
- 실패 시 성공 알림 금지
- Live Enable / IPS — **이번 칩 불필요**

## Kill / rollback

- Env: `ASR_MOBILE_UPLOAD_BACKGROUND=0` → status `mobile_upload_background: false`
- Client: flag **false**면 FG/알림 생략 (업로드·청크·폴링은 기존 경로). 키 없음(구서버)은 FG 허용.
- Revert PR · APK 다운핀

## Version

Web/mobile **0.3.3** · pubspec `0.3.3+1`

## Device E2E (SM-G986N · sideload)

1. APK `versionName=0.3.3` · `POST_NOTIFICATIONS` granted
2. PDF 가져오기 → 알림 `PDF 올리는 중` (+ `%` 진행) → HOME → 알림 유지·완료
3. 완료 알림 탭 → 읽기 탭 (`readerish`)
4. 권한 거부 경로: 업로드 계속 + snackbar 안내 (코드·단위)

Note: 일부 OEM 배터리 제한은 Dart HTTP를 멈출 수 있음 → FG+WakeLock+design/71 resume.
E2E는 `deviceidle whitelist` 후 HOME-after-percent로 확인.

Do not paste emails, cookies, or paper titles into chat/PR.

## Live pin (post-merge)

- Cloud Run `/api/status`: `version=0.3.3`, `mobile_upload_background=true`
- Device APK `versionName=0.3.3` (sideload) · SM-G986N
- E2E: PDF 가져오기 → notify visible → Home after percent → `업로드 완료` tap → reader
- Kill: `ASR_MOBILE_UPLOAD_BACKGROUND=0`
- Live Enable / IPS: unchanged (not in this chip)

