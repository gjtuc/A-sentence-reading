# 84 — Access waiting UX (login OK · invite pending)

Modules: web `accessWaitingPanel` · Flutter `AccessWaitingScreen` · `HomeShell` branch  
받침: [67](67-access-gate.md) · [69](69-access-gate-gcs.md) · [83](83-login-required-gate.md)

## 무엇인가

로그인됐지만 초대 미승인(또는 Deny)이면 **대기 전용 화면만** 보인다.  
보관·읽기 등 본 앱은 숨긴다. Allow 되면 **자동으로** 본 앱으로 들어간다.

| 포함 | 미포함 |
|------|--------|
| 웹+앱 대기 전용 셸 | OTP/Allow API 변경 |
| 초대 코드 입력 · 상태 문구 | BYOK |
| Deny = 대기와 동일 · 재입력 | Live Enable / IPS |
| Allow 후 폴링으로 자동 입장 | |

## Product (locked)

1. 로그인 O · 미승인 → **대기 전용만** (탭/본문 숨김)  
2. **웹 + 앱**  
3. Deny여도 대기 화면 · **코드 재입력**  
4. Allow → **자동** 본 앱  

## Layering

로그인 강제(83) → **이 칩(대기)** → 본 앱 · 유료 API(67)

## Kill / rollback

- `ASR_ACCESS_GATE=0` → 게이트 off · 대기 생략 (비용 위험 · 응급)  
- Revert PR · 클라가 `access_waiting_ux=false`면 대기 셸 스킵  

## Version

**0.3.3** · pubspec `0.3.3+1`

## Fail-closed

- **성공 조회**만 본 앱 / 대기 셸을 확정한다.
- 조회 **실패** 시 본 앱을 새로 열어 유료 사용을 가장하지 않음.
- 다만 이미 Allow(또는 sticky)인 세션은 실패만으로 대기 셸에 **튕기지 않음** → [172](172-access-sticky-on-timeout.md).
- 미지(첫 조회 실패·sticky 없음) → 재연결 UI (승인 대기 문구 금지).

## Live Enable / IPS

이번 칩에서 불필요함.

Do not paste emails, cookies, tokens, or invite codes into chat/PR.
