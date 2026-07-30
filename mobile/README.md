# 문장 읽기 — Android Flutter

Monorepo path for the mobile client of [A-sentence-reading](../README.md).
Design: [33](../docs/design/33-mobile-flutter.md) · [47](../docs/design/47-flutter-scaffold.md) · [48](../docs/design/48-flutter-android-platform.md) · [61](../docs/design/61-mobile-email-auth.md) · [62](../docs/design/62-mobile-library.md) · [63](../docs/design/63-mobile-reader.md).

## Status (0.2.71)

(Platform baseline: **0.2.56** android/ · scaffold 0.2.55 · email 0.2.69 · library 0.2.70)

- **이메일 로그인** · **보관 목록/open** · **읽기** (문장+그림, 인덱스 독립)
- `PATCH /api/session/{id}/cursor` best-effort
- Display name 「문장 읽기」 · `applicationId` `com.gjtuc.sentence_reading`
- **No secrets** — public Cloud Run URL only
- TTS · Google/카카오 → 후속

## Application id

| Field | Value |
|-------|--------|
| Display name | 문장 읽기 |
| Android `applicationId` | `com.gjtuc.sentence_reading` |
| Package (Dart) | `sentence_reading` |

## Out of scope

- Live Enable / IPS (Stock Trading Gate — not this repo)
- Gemini / GCS credentials in the client
- iOS · Play Store
