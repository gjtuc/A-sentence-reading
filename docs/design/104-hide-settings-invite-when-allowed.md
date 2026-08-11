# 104 — Hide Settings invite redeem when allowed / admin

Modules: `access_models.dart` · `settings_screen.dart`  
받침: [67](67-access-gate.md) · [84](84-access-waiting-ux.md) · [68](68-mobile-shell-nav.md)

## 무엇인가

모바일 **설정**의 「액세스 (초대 코드)」입력칸을 **이미 승인된 유저**와 **관리자**에게는 숨긴다.

| 역할 / 상태 | 초대 코드 입력칸 | 관리자 OTP·Allow/Deny |
|-------------|------------------|------------------------|
| 승인(allowed) · 일반 | 숨김 | — |
| 관리자 | 숨김 | 유지 |
| none / pending / Deny | 표시 (Deny는 재입력) | — |
| 게이트 off | 숨김 | 관리자면 유지 |

대기 전용 셸([84](84-access-waiting-ux.md))의 초대 입력은 **유지** (미승인·Deny 재입력의 본 경로).

## Product (locked this chip)

1. 승인된 일반 유저 → 설정에서 초대 코드 칸 **숨김**  
2. Deny → **재입력 가능** (대기 셸 A; 설정 폴백도 동일 규칙)  
3. 관리자 → OTP/Allow/Deny **유지**, 초대 코드 **입력칸은 불필요 → 숨김**

## Kill / rollback

- Revert PR · Settings에 항상 redeem UI 복구

## Version

**0.3.18** · status + pubspec

## Live Enable / IPS

이번 칩에서 불필요함.

## Device / pytest

- pure: `shouldShowSettingsInviteRedeem` (admin/allowed/denied/gate-off)
- settings 문자열: 승인·admin 경로에 입력 위젯 조건
- 실기: 승인 계정 설정에 「초대 코드」필드 없음 · 관리자는 mint만

## Device pin (E2E)

- APK `versionName=0.3.18` · `adb install -r` (SM-G986N)
- Admin allowed Settings: **no** 「코드 제출」/「액세스 (초대 코드)」· **yes** 「OTP 초대 코드 발급」
- Non-admin allowed Settings: no invite redeem · no admin/server chrome
- Denied: waiting shell only · 「코드 제출」재입력 · no main tabs
- Web waiting panel invite input unchanged (Settings redeem was mobile-only)

Do not paste emails, cookies, tokens, or invite codes into chat/PR.
