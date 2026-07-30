# 문장 읽기 — Android Flutter

Monorepo path for the mobile client of [A-sentence-reading](../README.md).
Design: [33](../docs/design/33-mobile-flutter.md) · [47](../docs/design/47-flutter-scaffold.md) · [48](../docs/design/48-flutter-android-platform.md) · [61](../docs/design/61-mobile-email-auth.md).

## Status (0.2.69)

(Platform baseline: **0.2.56**  · scaffold 0.2.55)

- Dart scaffold + **`android/`** platform
- **이메일 로그인 / 가입 / 로그아웃** · `asr_session` 로컬 저장 · 재실행 시 `/api/auth/status` 복구
- Display name 「문장 읽기」 · `applicationId` `com.gjtuc.sentence_reading`
- **No secrets** — public Cloud Run URL only
- Google / 카카오 · 보관 · 읽기 · TTS → 후속

APK binary build needs a local **Android SDK + JDK**.

## Application id

| Field | Value |
|-------|--------|
| Display name | 문장 읽기 |
| Android `applicationId` | `com.gjtuc.sentence_reading` |
| Package (Dart) | `sentence_reading` |

## Prerequisites

1. Install [Flutter](https://docs.flutter.dev/get-started/install) (stable). Example path: `Desktop/.cursor/tools/flutter` (**not** committed).
2. `cd mobile && flutter pub get && flutter test && flutter analyze`
3. For APK: Android SDK + `flutter build apk`

## Out of scope

- Live Enable / IPS (Stock Trading Gate — not this repo)
- Gemini / GCS credentials in the client
- iOS · Play Store
