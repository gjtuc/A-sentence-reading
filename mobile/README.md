# 문장 읽기 — Android Flutter

Monorepo path for the mobile client of [A-sentence-reading](../README.md).
Design: [33](../docs/design/33-mobile-flutter.md) · [47](../docs/design/47-flutter-scaffold.md) · [48](../docs/design/48-flutter-android-platform.md) · [61](../docs/design/61-mobile-email-auth.md) · [62](../docs/design/62-mobile-library.md).

## Status (0.2.70)

(Platform baseline: **0.2.56** android/ · scaffold 0.2.55 · email auth 0.2.69)

- **이메일 로그인** · **보관 목록** (`GET /api/cache/papers`) · **open** → 읽기 탭에 세션 요약
- Display name 「문장 읽기」 · `applicationId` `com.gjtuc.sentence_reading`
- **No secrets** — public Cloud Run URL only
- 문장/그림 읽기 UI · TTS · Google/카카오 → 후속

## Out of scope

- Live Enable / IPS (Stock Trading Gate — not this repo)
- Gemini / GCS credentials in the client
- iOS · Play Store
