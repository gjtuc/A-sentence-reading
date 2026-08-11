# 83 — Login-required gate (web + API + mobile)

Modules: `login_required.py` · `_GcsUidMiddleware` gate · web `app.js`/`styles.css` · Flutter `HomeShell` kill awareness  
받침: [67](67-access-gate.md) · [68](68-mobile-shell-nav.md) · [77](77-email-magic-link.md) · [78](78-no-email-password-signup.md)

## 무엇인가

**비로그인 사용자는 로그인 화면만** 본다. 웹·앱 공통.  
직접 URL/API 호출은 **UI → 로그인**, **API → 401**.  
로그인에 꼭 필요한 경로만 예외.

| 포함 | 미포함 |
|------|--------|
| `ASR_LOGIN_REQUIRED` 킬 (기본 **on**) | 액세스 OTP/Allow 변경 (67 유지) |
| API 미들웨어 401 | 비밀번호 UI 재도입 |
| 웹: 본문 숨김 + 로그인 다이얼로그 강제 | Live Enable / IPS |
| 앱: 기존 셸 게이트 + 킬 OFF 시 익명 허용 | |

## Product (locked)

1. 비로그인 → **로그인 화면만**  
2. **웹 + 앱**  
3. 직접 URL/API → **거절** (화면 로그인 / API 401)  
4. 예외 → `/api/status` · `/api/auth/*`(로그인용) · `/static/*` · `/` 만  

## Layering

`login required (identity)` → then `67 invite allow (cost)` → paid features.

## Kill / rollback

- `ASR_LOGIN_REQUIRED=0` → 게이트 off (익명 허용; 응급)  
- Revert PR  

## Public allowlist (anonymous)

- `GET /api/status`
- `GET /api/auth/status`
- `POST /api/auth/google`
- `GET /api/auth/kakao/start` · `GET /api/auth/kakao/callback`
- `POST /api/auth/email/login|register` (78 kill may still 503)
- `POST /api/auth/email/magic/request` · `GET /api/auth/email/magic/open`
- `POST /api/auth/logout`
- `GET /` · `/static/*`

Admin magic mint 등은 **세션 필요** (allowlist 밖).

## Version

**0.3.0** · pubspec `0.3.0+1`

## Fail-closed / multi-user

- 세션 없으면 비공개 API 401 (`auth_required`) — 빈 성공 JSON 금지  
- body/query `user_id` 신뢰 금지 (기존 불변)  
- 로그아웃 후 게이트 재적용 (웹)  

## Live Enable / IPS

이번 칩에서 불필요함.

Do not paste emails, cookies, or tokens into chat/PR.
