# 65 — Flutter Google · Kakao login

Modules: `oauth_models.dart` · `client.dart` · `auth_controller.dart` · `login_screen.dart`  
Server: existing `POST /api/auth/google` · `GET /api/auth/kakao/start|callback` (+ mobile deep link)  
See: [23-multi-auth-link.md](23-multi-auth-link.md) · [33-mobile-flutter.md](33-mobile-flutter.md) · [61](61-mobile-email-auth.md)

## What

Wire **real** Cloud Run OAuth into the Android app (not mocks). Email already works; this adds means 2/3 and 3/3.

| In | Out |
|----|-----|
| Google id_token → `POST /api/auth/google` | Account-link UI polish |
| Kakao via Custom Tab → HTTPS callback → app deep link with `asr_session` | iOS |
| Provider buttons gated by `/api/auth/status` | Secrets in APK |
| SessionStore same as email | Live Enable / IPS |

## Flows

### Google
1. `GET /api/auth/status` → `client_id` (public Web client id)
2. `google_sign_in` with `serverClientId=client_id` → id_token
3. `POST /api/auth/google` `{ credential }` → Set-Cookie → SessionStore

### Kakao
1. Open `{api}/api/auth/kakao/start?mode=login&mobile=1` (Custom Tab)
2. Kakao → HTTPS `/api/auth/kakao/callback` (console URI unchanged)
3. Server redirects to `com.gjtuc.sentence_reading://oauth/kakao?asr_session=…`
4. App stores token (Custom Tab cookies are not visible to Flutter)

## INVARIANT

- No Gemini/GCS/Kakao REST secret in the app
- Password email path still PBKDF2 on server
- Live Enable / IPS → Trading Gate (ASR out)

## EDGE

- missing `client_id` / provider off → hide button
- empty / cancelled Google → message, stay logged out
- Kakao `auth_error` / missing `asr_session` → refuse
- malformed deep link / blank token → clear, error
- web Kakao callback (mobile=0) unchanged → `/?auth=`

## Version

Web **0.2.75** · status `mobile_oauth: true` · pubspec `0.2.75+1`
