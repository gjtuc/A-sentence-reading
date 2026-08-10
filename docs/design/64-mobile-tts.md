# 64 — Flutter TTS (current sentence)

Modules: `tts_models.dart` · `tts_controller.dart` · `client.dart` · `reader_screen.dart`
Server: existing `POST /api/tts` · `GET /api/tts/voices` ([15-tts-and-gestures.md](15-tts-and-gestures.md))
See: [33-mobile-flutter.md](33-mobile-flutter.md) · [63-mobile-reader.md](63-mobile-reader.md)

## What

Reader plays the **current English sentence** via Cloud TTS. The app only fetches MP3 and plays it; synthesis + GCS cache stay on the server (same path as PC web).

| In | Out |
|----|-----|
| Play / Stop on sentence panel | Random-mode UI (web-only for now) |
| Client `playbackRate` (0.5–2.2) | Google / Kakao login |
| Default Neural2 voice optional | App-side Gemini / GCS keys |
| Stop on sentence advance | Upload / notes |

## Cache (PC parity)

1. App → `POST /api/tts` `{ text, voice?, speaking_rate: 1.0 }`
2. Server: local disk → GCS download → Cloud synthesize → local + GCS put (best-effort)
3. Response `audio/mpeg` → Flutter `audioplayers` BytesSource
4. Speed = **client** `setPlaybackRate` (server always caches native 1.0)

## INVARIANT

- TTS never mutates sentence/figure indexes
- Empty / whitespace-only text → client refuses before network
- Live Enable / IPS → Trading Gate only (ASR out)

## EDGE

- empty sentence → error, no POST
- 503 `tts_unavailable` · 400 `empty_text` · 502 `tts_failed` → surface message
- NaN / insane rate → clamp to [0.5, 2.2]
- sentence advance / dispose → stop playback
- binary success body must not be JSON-decoded

## Non-goals

- Live Enable / IPS
- Signalsmith WASM stretch (web); mobile uses player rate
- Storing MP3 on device long-term

## Version

Web **0.2.82** · status `mobile_tts: true` · pubspec `0.2.82+1`

## Version pin

Web/mobile **0.2.91**.
