# 문장 읽기 — Android Flutter

Monorepo path for the mobile client of [A-sentence-reading](../README.md).
Design: [33](../docs/design/33-mobile-flutter.md) · [61](../docs/design/61-mobile-email-auth.md)–[65](../docs/design/65-mobile-oauth.md).

## Status (0.2.73)

- Scaffold baseline **0.2.56** (android/ applicationId); email/library/reader/TTS/OAuth layered on top
- **이메일 · Google · 카카오** 실 OAuth (서버 검증 · 앱에 secret 없음)
- 보관 · 읽기 · TTS
- Live Enable / IPS: Trading Gate (ASR out)

## Application id

| Field | Value |
|-------|--------|
| Display name | 문장 읽기 |
| Android `applicationId` | `com.gjtuc.sentence_reading` |
| Kakao deep link | `com.gjtuc.sentence_reading://oauth/kakao` |

## Prerequisites

1. Flutter stable
2. `cd mobile && flutter pub get && flutter test && flutter analyze`
3. Device: Google Play services for Google Sign-In; Kakao HTTPS callback already on Cloud Run

## Out of scope

- Live Enable / IPS
- Gemini / GCS / Kakao REST secret in the client
- iOS · Play Store
