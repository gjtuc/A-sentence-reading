# 61 — Flutter 이메일 로그인 · 세션 쿠키

모듈: `mobile/lib/api/*` · `mobile/lib/state/auth_controller.dart` · `mobile/lib/screens/login_screen.dart`  
받침: [33-mobile-flutter.md](33-mobile-flutter.md) · [47](47-flutter-scaffold.md) · [48](48-flutter-android-platform.md)

## 무엇을

Android Flutter MVP 구현 순서 **3번 중 로그인(수단 ≥1)**:  
**이메일 가입/로그인** + Cloud Run `asr_session` 쿠키를 앱에 저장·재사용.

| 포함 | 미포함 (후속) |
|------|----------------|
| `POST /api/auth/email/login` · `register` · `logout` | Google / 카카오 네이티브 OAuth |
| `GET /api/auth/status` 로 세션 복구 | 보관 목록 · 읽기 · TTS |
| `SessionStore` (`asr.session.v1` / SharedPreferences) | Play Store · iOS |
| 로그인 UI (가입 토글) | 계정 연결 UI |

## 쿠키

- 서버 쿠키 이름: `asr_session` (httponly · 웹과 동일)
- 앱: `Set-Cookie`에서 값만 추출 → 이후 요청 `Cookie: asr_session=…`
- EDGE: 빈 값 · `deleted` · 잘못된 이름 · 공백만 → 로그아웃 아웃 취급

## UX

1. 하단 **로그인** → 이메일/비밀번호  
2. 가입 모드 토글 (비밀번호 ≥8자 로컬 검사)  
3. 성공 시 계정 라벨 · 로그아웃아웃  
4. 재실행 시 저장된 토큰으로 `/api/auth/status` 복구

## 비목표

- Live Enable / IPS — **Trading Gate. ASR 밖**
- 앱에 Gemini/GCS secret
- 문장/그림 인덱스 변경 (이 단계 없음)

## status

`mobile_email_auth: true`

## 버전

웹 **0.2.82** · pubspec `0.2.82+1`


## Signup UX (0.2.82)

- Password confirm field on register
- Visibility toggle (eye icon) on password fields
- Client validates match before POST (no password logging)

## Version pin

Web/mobile **0.2.86**.
