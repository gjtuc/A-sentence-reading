# 65 — Flutter Google · Kakao login

Modules: `oauth_models.dart` · `oauth_bridges.dart` · `client.dart` · `auth_controller.dart` · `login_screen.dart`  
Server: existing `POST /api/auth/google` · `GET /api/auth/google/mobile/start` · `GET /api/auth/kakao/start|callback` (+ mobile deep link)  
See: [23-multi-auth-link.md](23-multi-auth-link.md) · [33-mobile-flutter.md](33-mobile-flutter.md) · [61](61-mobile-email-auth.md)

## What

Wire **real** Cloud Run OAuth into the Android app (not mocks). Email already works; this adds means 2/3 and 3/3.

| In | Out |
|----|-----|
| Google native Sign-In + **account chooser every tap** (0.3.52) | Account-link UI polish |
| Custom Tab GIS fallback when Android SHA-1 missing | iOS |
| Kakao via Custom Tab → HTTPS callback → app deep link with `asr_session` | Secrets in APK |
| Provider buttons gated by `/api/auth/status` | Live Enable / IPS |
| SessionStore same as email | |

## Flows

### Google (0.3.52 — native + account chooser)
1. `GET /api/auth/status` → `client_id` (public Web client id)
2. `google_sign_in`: **`signOut()` then `signIn()`** → account picker every time → id_token
3. `POST /api/auth/google` `{ credential }` → Set-Cookie → SessionStore

WHY `signOut` first: after one successful login Google skipped the picker and reused the last account, so admin vs other Google identities could not be chosen.

### Google (fallback — Custom Tab GIS · SHA-1 / DEVELOPER_ERROR)
1. Native path throws ApiException 10 / `DEVELOPER_ERROR`
2. App opens Custom Tab → `GET /api/auth/google/mobile/start`
3. Page runs **Google Identity Services** (`disableAutoSelect` + `auto_select: false`)
4. `POST /api/auth/google` `{ credential, mobile:1 }` → JSON includes `asr_session`
5. Redirect `com.gjtuc.sentence_reading://oauth/google?asr_session=…` → app `applySessionToken`

### Kakao
1. Open `{api}/api/auth/kakao/start?mode=login&mobile=1` (Custom Tab)
2. Kakao → HTTPS `/api/auth/kakao/callback` (console URI unchanged)
3. Server redirects to `com.gjtuc.sentence_reading://oauth/kakao?asr_session=…`
4. App stores token (Custom Tab cookies are not visible to Flutter)

## INVARIANT

- No Gemini/GCS/Kakao REST secret in the app
- Password email path still PBKDF2 on server
- Live Enable / IPS → Trading Gate (ASR out)
- Mobile Google deep link carries **session only** (never Google id_token in the URL)
- Every Google login attempt must allow **account selection** (no silent reuse)

## EDGE

- missing `client_id` / provider off → hide button
- native cancel / empty id_token → message, stay logged out (no Custom Tab)
- DEVELOPER_ERROR → Custom Tab fallback
- empty / cancelled Google Custom Tab → message, stay logged out
- Kakao `auth_error` / missing `asr_session` → refuse
- malformed deep link / blank token → clear, error
- web Kakao callback (mobile=0) unchanged → `/?auth=`
- `POST /api/auth/google` without `mobile` → no `asr_session` in JSON (cookie only)

## Android OAuth SHA-1 (sideload)

Sideload release APK currently uses the **debug signing** key (`signingConfig = debug`).
Native `google_sign_in` requires an **Android** OAuth client:

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
5. Keep using the existing **Web** client id as `ASR_GOOGLE_CLIENT_ID` (public)

### Registration status (0.2.82 · PC-B verified 0.2.86)

Ops completed in Google Cloud project `peaceful-basis-503207-t4`:

| Item | Value |
|------|--------|
| Android OAuth client name | `ASR Android sideload` |
| Type | Android |
| Package | `com.gjtuc.sentence_reading` |
| SHA-1 | PC-A **and** PC-B fingerprints above (same Android client; both required for multi-machine sideload) |
| Web client (unchanged) | `ASR local` — still used as `serverClientId` / `ASR_GOOGLE_CLIENT_ID` |

### Device E2E — account chooser (0.3.52)

Against Live post-CD `version=0.3.52` · `mobile_google_account_chooser=true`:

1. Cold open → **Google로 계속** → native account picker (not silent last-account)
2. Pick account A → logged in; logout / reopen → **Google로 계속** → picker again → pick account B
3. Settings shows google provider when allowed
4. Unauth `POST /api/auth/google` empty body → **401**; `GET /api/auth/google/mobile/start` without client id → **503**

Do not paste account emails, id_tokens, or cookies into chat/PR.

### App behaviour

- Legacy native ApiException 10 / DEVELOPER_ERROR → Custom Tab fallback (then fail-closed Korean copy if that fails)
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

Web/mobile **0.3.52** · status `mobile_oauth` · `mobile_google_account_chooser` · `mobile_google_custom_tab` · `mobile_google_sha_runbook` · `mobile_google_android_oauth` · pubspec `0.3.52+1`
