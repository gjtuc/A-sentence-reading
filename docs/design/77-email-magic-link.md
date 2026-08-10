# 77 — Email magic-link login (deep link → app)

Modules: `auth_magic_link.py` · `email_smtp.py` · `/api/auth/email/magic/*` · Flutter login + Android VIEW intent  
받침: [61](61-mobile-email-auth.md) · [65](65-mobile-oauth.md) · [67](67-access-gate.md) · [68](68-mobile-shell-nav.md)

## 무엇인가

일반 사용자가 **이메일로 받은 링크**를 눌러 Android 앱이 바로 열리고 `asr_session`이 잡힌다.  
비밀번호를 기억하지 않아도 로그인된다. **액세스 게이트 OTP 승인은 그대로 필요** (로그인 ≠ 유료 사용).

| 포함 | 미포함 |
|------|--------|
| mint (해시 저장) + SMTP 발송 | 비밀번호 제거 |
| HTTPS open → custom-scheme bounce | iOS / App Links assetlinks |
| 앱 cold-start deep link | Live Enable / IPS |
| status `mobile_email_magic_link` | Trading Gate |
| 관리자 일회 URL mint (실기기 E2E·지원) | |

## Product (locked)

1. **A** — 급하지 않아도 적용
2. **A** — 일반 사용자; **OTP 게이트 유지** (자동 allow 금지)
3. **A** — 메일 링크 → **앱 즉시 오픈** (`com.gjtuc.sentence_reading://oauth/magic`)

## 동작

1. `POST /api/auth/email/magic/request` `{email}`  
   - 형식 불량이면 400  
   - SMTP 미설정·킬스위치 → 503 fail-closed (보낸 척 금지)  
   - 성공 시 동일 문구 (계정 유무 누설 최소화: 유효 이메일이면 mint+발송 시도; 신규는 redeem 시 passwordless 계정 생성)
2. 메일 본문: `https://…/api/auth/email/magic/open?t=…` (토큰 원문 1회)
3. `GET …/open` → 단회 redeem → 302 → `…://oauth/magic?asr_session=…&auth=magic`
4. 앱 intent → MethodChannel → `applySessionToken` → `/api/auth/status`  
5. 미승인 계정은 기존처럼 Settings에서 초대 OTP

## INVARIANT

- 토큰 원문·세션·이메일을 로그/알림/PR에 넣지 않음 (해시만 저장)
- Work input / 알림에 세션 금지
- Access gate 우회 금지
- `ASR_EMAIL_MAGIC_LINK=0` → status false · enqueue/API 거절

## Kill / rollback

- `ASR_EMAIL_MAGIC_LINK=0`
- `ASR_EMAIL_AUTH=0` (이메일 계열 전체)
- Revert PR · APK 다운핀

## SMTP

- `ASR_SMTP_HOST` · `ASR_SMTP_PORT` · `ASR_SMTP_USER` · `ASR_SMTP_PASS` · `ASR_SMTP_FROM`
- 미설정 시 request 503 (빈 성공 금지)

## Version

**0.2.94** · pubspec `0.2.94+1`

## Device E2E (pre-merge)

- APK `versionName=0.2.94` · SM-G986N
- Local API + `adb reverse` (pre-CD) · admin mint → HTTPS open → custom-scheme VIEW
- Deep link → shell tabs · Settings shows `magic-user@…` · **상태: none · 유료 API 차단** (OTP 게이트 유지)
- Logout → login screen (탭/보관 잔여 없음)
- Kill: `ASR_EMAIL_MAGIC_LINK=0`
- Live Enable / IPS: unchanged

Do not paste emails, cookies, or paper titles into chat/PR.

## Live pin (post-merge)

- Cloud Run `/api/status`: `version=0.2.94`, `mobile_email_magic_link=true`
- SMTP: `ASR_SMTP_*` required for user request path; admin mint for support/E2E
- Device APK `versionName=0.2.94` · SM-G986N
- E2E: magic deep link → session · access status not auto-allowed (`E2E77 PASS`)
- Kill: `ASR_EMAIL_MAGIC_LINK=0`
- Live Enable / IPS: unchanged
