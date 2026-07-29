# 문장 읽기 — Android Flutter (scaffold)

Monorepo path for the mobile client of [A-sentence-reading](../README.md).
Design: [33](../docs/design/33-mobile-flutter.md) · [47](../docs/design/47-flutter-scaffold.md).

## Status (0.2.55)

Scaffold only: Material shell, placeholder screens (login / library / reader),
HTTP client stub for `GET /api/status`. **No secrets** in the app — only the
public Cloud Run base URL.

## Application id

| Field | Value |
|-------|--------|
| Display name | 문장 읽기 |
| Android `applicationId` | `com.gjtuc.sentence_reading` |
| Package (Dart) | `sentence_reading` |

## Prerequisites

1. Install [Flutter](https://docs.flutter.dev/get-started/install) (stable).
2. Generate native Android project files (once):

```bash
cd mobile
flutter create . --org com.gjtuc --project-name sentence_reading
flutter pub get
```

3. Point `lib/config.dart` at your Cloud Run URL if needed (default is production).

## Run / APK

```bash
flutter run
flutter build apk
```

Sideload the APK; Play Store is out of scope for MVP.

## Out of scope here

- Live Enable / IPS (Stock Trading Gate — not this repo)
- Gemini / GCS credentials in the client
- iOS
