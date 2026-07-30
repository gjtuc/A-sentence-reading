# 63 — Flutter reader (independent cursors)

Modules: reading_models.dart · reader_screen.dart · library_controller.dart
Server: PATCH /api/session/{id}/cursor
See: 33-mobile-flutter.md · 04-api-contract.md · 62-mobile-library.md

## What

Opened session shown as sentence (top) + figure (bottom); indexes move independently.

| In | Out |
|----|-----|
| split UI, sentence/figure chevrons | (TTS → [64](64-mobile-tts.md)) |
| ReadingSession clamp/wrap | Google/Kakao |
| PATCH cursor best-effort | app upload |
| PNG/JPEG data-URL, http(s) | SVG preview |

## INVARIANT

- advanceSentence never changes figureIndex
- advanceFigure never changes sentenceIndex

## EDGE

- empty lists -> index 0, buttons disabled
- corrupt JSON rows skipped; huge index clamped
- SVG data-URL -> caption placeholder
- cursor PATCH failure -> UI kept

## Non-goals

- Live Enable / IPS — Trading Gate (ASR out)
- Gemini/GCS secrets in app

## Version

Web **0.2.72** · status mobile_reader: true · pubspec 0.2.72+1
