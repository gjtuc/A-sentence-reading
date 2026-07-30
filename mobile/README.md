# 문장 읽기 — Android Flutter

Monorepo path for the mobile client of [A-sentence-reading](../README.md).
Design: [33](../docs/design/33-mobile-flutter.md) · [61](../docs/design/61-mobile-email-auth.md)–[66](../docs/design/66-mobile-theme.md).

## Status (0.2.74)

- Scaffold baseline **0.2.56** (android/ applicationId)
- 이메일 · Google · 카카오 · 보관 · 읽기 · TTS · **테마 3종**(system/light/dark, 재실행 유지)
- Live Enable / IPS: Trading Gate (ASR out)

## Application id

| Field | Value |
|-------|--------|
| Display name | 문장 읽기 |
| Android `applicationId` | `com.gjtuc.sentence_reading` |

## Prerequisites

1. Flutter stable
2. `cd mobile && flutter pub get && flutter test && flutter analyze`
3. APK sideload needs Android SDK + device (next)

## Out of scope

- Live Enable / IPS
- Gemini / GCS secrets in the client
- iOS · Play Store
