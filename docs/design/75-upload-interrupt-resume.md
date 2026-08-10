# 75 — Upload interrupt auto-resume (phone call · OEM pause)

모듈(예정): `library_controller` · `upload_notify` · (선택) WorkManager / 별도 upload isolate  
받침: [71-mobile-upload-resume.md](71-mobile-upload-resume.md) · [72-chunked-upload.md](72-chunked-upload.md) · [74-bg-upload-notify.md](74-bg-upload-notify.md)

## 왜

실사용에서 **전화 수신·통화·OEM 절전**이 오면 Flutter Dart HTTP(chunk/poll)가 멈추거나 프로세스가 약해질 수 있다.  
74 FG 알림은 “진행 중처럼” 남을 수 있지만, 실제 전송/폴링이 멈춘 채면 사용자는 끊긴 줄도 모른다.

지금은 앱을 **다시 열면** design/71 초안 resume이 붙잡는 수동 복구에 가깝다.  
이 칩은 **중단 후에도 자동으로** 이어보내기·처리 폴링을 재개(또는 안전하게 실패 고지)하는 것을 목표로 한다.

## 무엇을

| 포함 | 미포함 (더 후속) |
|------|------------------|
| 통화/interrupted lifecycle 감지 후 auto-reattach | iOS BG |
| 앱 복귀·통화 종료 시 draft resume 강제 | 다파일 동시 |
| FG 알림이 “멈춤/이어올리는 중”으로 정직하게 갱신 | 서버가 클라 대신 chunk PUT |
| 장시간 무진행 → fail-closed + 안내 (가짜 성공 금지) | 매직링크 |
| OEM 배터리 예외 안내(선택·강요 금지) | Trading Live Enable / IPS |

## Product (초안 — 구현 칩에서 lock)

1. **중단 감지**: `AppLifecycleState` paused/inactive + (가능 시) 통화/오디오 포커스 힌트. 추측으로 “문제없음” 완료 금지.
2. **자동 재개**: 복귀 또는 FG 유지 중 idle timeout 후 `resumePendingIfAny` / chunk integrity 재개.
3. **정직한 UI**: 멈춤이면 알림/화면이 계속 `%`만 돌리지 말 것. “이어올리는 중” 또는 실패 안내.
4. **수동 없이도**: 전화 끊고 홈만 있어도, 가능하면 백그라운드에서 재개. 불가 OEM은 알림 탭 → 재개.

## INVARIANT

- 세션·user는 기존 쿠키만. 알림/큐 payload에 비밀 금지.
- 남의 job/upload_id 재개 금지 (owner 격리 유지).
- 실패를 성공 알림으로 포장 금지.
- Live Enable / IPS — ASR 밖.

## 기술 후보 (구현 칩에서 하나 고르기)

A. **Lifecycle 강화**: resumed마다 draft 검사 + stalled 중 heartbeat 없으면 알림을 “중단됨·탭하여 이어가기”.  
B. **WorkManager / 네이티브 재시작 큐**: 프로세스 사망 후에도 chunk PUT·job poll 워커.  
C. **별도 upload isolate / FG task 핸들러**: 전화로 Activity가 죽어도 isolate 유지 (74에서 미도입한 경로).

우선순위 제안: **A로 정직함+자동 재개** → 부족하면 B/C.

## Kill / rollback

- Client flag 또는 status 확장 예: `mobile_upload_interrupt_resume` (이름 구현 시 확정)
- Env kill (서버 계약이 생기면) · revert PR · APK 다운핀
- 끄면 동작은 71+74 수준으로 후퇴

## Version (구현 시)

Web/mobile **TBD** (다음 구현 칩에서 pin)

## 지금 당장 (설계만인 동안 사용자 조치)

1. 통화 끝난 뒤 **「문장 읽기」 앱을 다시 연다** → 보관 탭이 draft를 auto-resume.
2. 알림이 남아 있으면 탭해 앱을 앞으로.
3. 그래도 안 되면 같은 PDF를 다시 고른다 (content_hash 일치 시 71이 재부착).

Do not paste emails, cookies, or paper titles into chat/PR.
