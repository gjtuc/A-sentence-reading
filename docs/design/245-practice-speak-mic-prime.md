# 245 — Practice speak mic prime + ready beat

Version: **0.3.237** · Status: **locked**

받침: [82](82-shadowing-practice-loop.md) · [176](176-focus-practice-pomodoro.md) · [206](206-practice-speak-tts-volume.md) · [214](214-minimal-rhythm-practice-ui.md)

## Intent

Stop cutting the first ~0.3 words when Listen → Speak: MediaRecorder
`prepare`/`start` latency and users speaking as soon as the rail flips.

## Locked product

1. **Prime during Listen:** MethodChannel `prepare` builds `MediaRecorder` +
   `prepare()` with the take path while listen TTS plays (no `start` yet).
2. **Speak entry:** `start` on the primed recorder (fast), then **ready beat**
   **350ms** with status `말할 준비` before speak-guide TTS.
3. **Focus clock:** `beginSpeak` only **after** the ready beat (warmup does not
   count toward the 10‑min block).
4. **Fail-closed:** prepare fail → speak still attempts full `start` as today;
   start fail → skip chunk (unchanged).
5. **Non-goals:** changing pad-after-TTS, STT, volume 20%, evidence kinds.

## Files

| Path | Role |
|------|------|
| `ShadowingMicHandler.kt` | `prepare` + primed `start` |
| `shadowing_practice_screen.dart` | prime in listen · ready beat |

## Version

**0.3.237**
