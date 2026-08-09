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

## Android OAuth SHA-1 (0.2.82)

Sideload release APK currently uses the **debug signing** key (`signingConfig = debug`).
Google Sign-In requires an **Android** OAuth client in the same Cloud project as the Web `client_id`.

| Field | Value |
|-------|--------|
| Package name | `com.gjtuc.sentence_reading` |
| SHA-1 (debug / PC-A sideload) | `73:45:00:0C:68:F6:B3:A9:88:1D:9A:FC:42:E7:86:FD:E9:A0:CA:10` |
| SHA-1 (debug / PC-B sideload · 2026-08) | `C1:F6:F2:71:A2:E5:F6:FB:D2:09:9F:AA:1B:67:19:53:18:3B:14:DF` |

### Console steps (ops — no secrets in git)

1. Google Cloud Console → APIs & Services → Credentials
2. Create OAuth client → **Android**
3. Package name = `com.gjtuc.sentence_reading`
4. SHA-1 = value above (recompute if the signing key changes)
5. Keep using the existing **Web** client id as `serverClientId` / `ASR_GOOGLE_CLIENT_ID` (public)


### Registration status (0.2.82 · PC-B verified 0.2.86)

Ops completed in Google Cloud project `peaceful-basis-503207-t4`:

| Item | Value |
|------|--------|
| Android OAuth client name | `ASR Android sideload` |
| Type | Android |
| Package | `com.gjtuc.sentence_reading` |
| SHA-1 | PC-A **and** PC-B fingerprints above (same Android client; both required for multi-machine sideload) |
| Web client (unchanged) | `ASR local` — still used as `serverClientId` / `ASR_GOOGLE_CLIENT_ID` |

Device E2E (Samsung sideload, PC-A key): **Google로 계속** → account picker → **로그인됨** · `providers: google` · logout available. No `DEVELOPER_ERROR` / fail-closed SHA copy.

#### Device E2E — PC-B SHA-1 (0.2.86 · Samsung sideload)

Against live Cloud Run `version=0.2.86` · `google` provider on (installed APK may lag at `0.2.84`; OAuth + session path is the contract). This PC debug keystore SHA-1 matches the documented PC-B value `C1:F6:…:14:DF`.

1. Force-stop → cold open → login-only shell (**Google로 계속** / Kakao / email)
2. **Google로 계속** → account picker → snackbar **Google 로그인되었습니다.** → bottom tabs (보관·읽기·설정)
3. **설정** → provider line `google` · access status coherent when allowed · logout available
4. No `DEVELOPER_ERROR` / ApiException 10 in logcat; no fail-closed SHA copy shown (success path)
5. **로그아웃** → login-only shell; no prior email, no access status, no tabs residue
6. Unauthenticated `GET /api/access/admin/pending` → **403**; `POST /api/auth/google` with empty/`{}` credential → **401** `invalid_token` (not success)

Do not paste account emails, id_tokens, or cookies into chat/PR.

Propagation note: Google may take minutes after create/update; retry Sign-In if account picker succeeds but session fails briefly.

### App behaviour (0.2.82)

- `ApiException: 10` / `DEVELOPER_ERROR` → Korean fail-closed message (not success snackbar)
- No client secret in the APK; id_token still verified only on Cloud Run

### Recompute SHA-1

```bash
# debug keystore (sideload today)
keytool -exportcert -keystore "$HOME/.android/debug.keystore" \
  -alias androiddebugkey -storepass android -file /tmp/debug.cer
# then SHA-1 of the DER cert, or:
apksigner verify --print-certs app-release.apk
```

Live Enable / IPS → Trading Gate (ASR out) — unchanged.

## Version

Web **0.2.82** · status `mobile_oauth` · `mobile_google_sha_runbook` · `mobile_google_android_oauth` · pubspec `0.2.82+1`

## Version pin

Web/mobile **0.2.87**.
