# 문장 읽기 — Android Flutter

Monorepo path for the mobile client of [A-sentence-reading](../README.md).
Design: [33](../docs/design/33-mobile-flutter.md) · [47](../docs/design/47-flutter-scaffold.md) · [48](../docs/design/48-flutter-android-platform.md).

## Status (0.2.56)

- Dart scaffold: Material shell, placeholder screens, `/api/status` client
- **`android/` platform** checked in (Gradle, Manifest, `MainActivity`)
- Display name 「문장 읽기」 · `applicationId` `com.gjtuc.sentence_reading`
- **No secrets** — public Cloud Run URL only

APK binary build needs a local **Android SDK + JDK**. This PC may only have Flutter SDK; `flutter build apk` then fails with `No Android SDK found` (expected until SDK is installed).

## Application id

| Field | Value |
|-------|--------|
| Display name | 문장 읽기 |
| Android `applicationId` | `com.gjtuc.sentence_reading` |
| Package (Dart) | `sentence_reading` |

## Prerequisites

1. Install [Flutter](https://docs.flutter.dev/get-started/install) (stable). Example path used on the data PC: `Desktop/.cursor/tools/flutter` (**not** committed to this repo).
2. `android/` is already present. To regenerate:

```bash
cd mobile
flutter create . --org com.gjtuc --project-name sentence_reading --platforms=android
flutter pub get
flutter analyze
```

3. For APK: install Android Studio / command-line SDK, set `ANDROID_HOME`, then `flutter build apk`.

## Out of scope

- Live Enable / IPS (Stock Trading Gate — not this repo)
- Gemini / GCS credentials in the client
- iOS · Play Store
