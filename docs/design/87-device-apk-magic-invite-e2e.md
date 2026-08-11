# 87 — Device APK pin + magic → invite redeem (Flutter)

Modules: `mobile/` APK · live magic `client=android` · access waiting · invite redeem  
받침: [33](33-mobile-flutter.md) · [77](77-email-magic-link.md) · [84](84-access-waiting-ux.md) · [86](86-live-smtp-wiring.md)

## 무엇인가

라이브 웹 매직링크 E2E는 닫혔다. 이번 칩은 **폰 APK가 live 0.3.3과 맞는지** 확인하고,  
매직링크 로그인 → **승인 대기** → **초대 코드 입력(redeem)** 까지 실기로 닫는다.

| 포함 | 미포함 |
|------|--------|
| APK `versionName=0.3.3` 빌드·사이드로드 | Play Store |
| 매직링크(앱 `mobile=1`) | 새 서버 기능 |
| 대기 셸 + 초대 코드 입력 | iOS · Live Enable/IPS |

## Product (locked this chip)

1. 실기 폰 USB/`adb`  
2. 매직링크 대상 메일(채팅에 링크·토큰 금지)  
3. 대기 화면 + **초대 코드 입력까지**

## Kill / rollback

- `ASR_EMAIL_MAGIC_LINK=0` · `ASR_ACCESS_GATE=0` (응급)  
- 이전 APK 사이드로드 · revert docs pin  

## Version

**0.3.3** · pubspec `0.3.3+1` (서버 버전 pin 유지 · 앱 실기 완성도)

## Live Enable / IPS

이번 칩에서 불필요함.

## Device pin (E2E)

- APK release `versionName=0.3.3` · `adb install -r` on USB device (SM-G986N)
- Magic → app deep link (`mobile=1` / `…://oauth/magic`) → **액세스 승인 대기** (`상태: none`)
- Invite redeem on waiting UI → **상태: pending** (“코드가 확인되었습니다…”)
- Live SMTP request path still available (`client=android`); device deep-link E2E used admin mint → open Location (no tokens in docs)
- Kill: prior APK · `ASR_EMAIL_MAGIC_LINK=0` · `ASR_ACCESS_GATE=0`

Do not paste magic URLs, session cookies, or invite codes into long-lived docs.
