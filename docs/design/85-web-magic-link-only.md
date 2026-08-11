# 85 — Web magic-link only (no password signup UI)

Modules: `index.html` auth dialog · `app.js` magic request · `/api/auth/email/magic/open` web cookie  
받침: [77](77-email-magic-link.md) · [78](78-no-email-password-signup.md) · [83](83-login-required-gate.md)

## 무엇인가

웹 로그인에서도 **비밀번호·가입 UI를 제거하고**, 이메일 = **매직링크만** (구글·카카오 유지).  
메일 링크를 브라우저에서 열면 **웹 세션 쿠키**로 로그인한다.

| 포함 | 미포함 |
|------|--------|
| 웹 비밀번호/가입 칸 제거 | 앱 UI 변경 (이미 78) |
| 웹 → `magic/request` | 비밀번호 API 재활성 |
| `magic/open` 웹: 쿠키 + `/?auth=logged_in` | Live Enable / IPS |
| 앱 메일: `mobile=1` 딥링크 유지 | |

## Product (locked)

1. 웹 이메일 = **매직링크만**  
2. 링크 클릭 = **브라우저 웹 세션**  
3. 구글·카카오 유지  

## Kill / rollback

- `ASR_EMAIL_MAGIC_LINK=0` → 매직링크 off  
- `ASR_EMAIL_PASSWORD=1` → 비밀번호 API만 응급 허용 (웹 UI는 이 칩에서 안 복구)  
- Revert PR  

## Version

**0.3.2** · pubspec `0.3.2+1`

## Fail-closed

- 비밀번호 register/login API는 기본 503 유지 (78)  
- SMTP 미설정 → request 503 · 성공 위장 금지  
- 액세스 게이트 자동 Allow 금지 (77)

## Live Enable / IPS

이번 칩에서 불필요함.

## Live pin (post-merge)

- Cloud Run `/api/status`: `version=0.3.2` · `web_email_magic_link_only=true` · `mobile_email_magic_link=true`
- Kill: `ASR_EMAIL_MAGIC_LINK=0` · rollback: revert PR #122

Do not paste emails, cookies, tokens, or magic URLs into chat/PR.
