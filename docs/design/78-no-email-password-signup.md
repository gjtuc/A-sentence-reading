# 78 — No email password signup (OAuth + magic-link only)

Modules: `login_screen.dart` · `/api/auth/email/register|login` kill · status `mobile_email_password`  
받침: [61](61-mobile-email-auth.md) · [65](65-mobile-oauth.md) · [77](77-email-magic-link.md)

## 무엇인가

구글·카카오·이메일 **매직링크**는 유지하고, **이메일+비밀번호 가입/로그인 UI·API 수집 경로를 끈다**.  
비밀번호를 GCS/accounts에 새로 쌓지 않기 위함 (기존 해시 레거시는 그대로 두되, 앱에서 새 수집 안 함).

| 포함 | 미포함 |
|------|--------|
| 로그인 화면에서 비밀번호/가입 토글 제거 | 구글·카카오 제거 |
| `ASR_EMAIL_PASSWORD` 킬 (기본 off) | 매직링크 제거 |
| status `mobile_email_password` | Live Enable / IPS |
| register/login API fail-closed when off | |

## Product (locked)

1. Google / Kakao 유지  
2. Magic-link = 이메일 로그인 옵션  
3. 이메일 회원가입으로 비밀번호 수집 **안 함**

## Kill / rollback

- `ASR_EMAIL_PASSWORD=1` → 비밀번호 register/login API 다시 허용 (응급·테스트)  
- Revert PR · APK 다운핀  

## Version

**0.3.2** · pubspec `0.3.2+1`

## Device E2E (pre-merge)

- APK `versionName=0.3.2` · SM-G986N  
- 로그인 화면에 비밀번호/「가입」 없음 · Google/카카오/매직링크 버튼만  
- Live Enable / IPS: unchanged  

Do not paste emails, cookies, or tokens into chat/PR.
