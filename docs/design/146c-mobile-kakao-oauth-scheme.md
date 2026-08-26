# 146c — Mobile Kakao OAuth scheme fix (flutter_web_auth_2)

Modules: `oauth_models.dart` · `auth_google.py` · `AndroidManifest.xml` · `CallbackActivity` · design/65  
받침: [65](65-mobile-oauth.md) · [146a](146a-mobile-account-link.md) · [140](140-mobile-mvp-backlog-split.md)

## 무엇인가

`flutter_web_auth_2` v4는 callback scheme이 `^[a-z][a-z\d+.-]*$`만 허용한다.  
기존 `com.gjtuc.sentence_reading`(**밑줄**)은 **ArgumentError**로 Custom Tab이 열리기 전에 실패 → 로그인·연결 카카오 버튼 무반응.

| 포함 | 미포함 |
|------|--------|
| OAuth 딥링크 scheme → `com.gjtuc.sentence-reading` (하이픈) | 146b 창고 병합 |
| 서버 redirect · AndroidManifest · CallbackActivity | package `applicationId` 변경 |
| 로그인 화면 카카오 E2E | Live Enable / IPS |

**WHY hyphen scheme:** `applicationId`는 `com.gjtuc.sentence_reading` 유지. URI scheme만 플러그인 규칙에 맞춘다.

## Product (locked)

1. **카카오 로그인** · **카카오 연결** 모두 `FlutterWebAuth2` → 새 scheme  
2. 이메일 매직링크 · Google Custom Tab fallback도 **같은 scheme** (서버 bounce)  
3. `CallbackActivity` 등록 — 플러그인이 deep link를 받아 `authenticate` 완료  
4. fail-closed: 로그인 성공 snackbar는 `user != null`일 때만

## Kill / rollback

- Revert PR · Live CD 이전 APK(0.3.63)는 카카오 OAuth 여전히 실패 (scheme 불일치)

## Live Enable / IPS

불필요.

## Version

**0.3.64**

## Device / E2E pin

- APK **0.3.64** sideload SM-G986N: 로그아웃 → **카카오로 계속** → `CustomTabActivity` (Chrome) 오픈 ✅ (0.3.63는 무반응)
- pytest `tests/test_mobile_kakao_oauth_scheme.py` + full suite pass
- **Full login callback** requires Live CD — Live `version=0.3.64` · redirect `com.gjtuc.sentence-reading://oauth/kakao?…` (post-merge verify)

Do not paste tokens, cookies, or emails into chat/PR.
