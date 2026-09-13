# 245 — Practice speak mic prime + ready beat

Version: **0.3.237** · Status: **locked**  
Amended by [259](259-speak-ui-hold-listen-until-ready.md) (UI hold; **0.3.259**)

받침: [82](82-shadowing-practice-loop.md) · [176](176-focus-practice-pomodoro.md) · [206](206-practice-speak-tts-volume.md) · [214](214-minimal-rhythm-practice-ui.md)

## Intent

Stop cutting the first ~0.3 words when Listen → Speak: MediaRecorder
`prepare`/`start` latency and users speaking as soon as the rail flips.

## Locked product

1. **Prime during Listen:** MethodChannel `prepare` builds `MediaRecorder` +
   `prepare()` with the take path while listen TTS plays (no `start` yet).
2. **Speak entry (engine):** `start` on the primed recorder (fast), then **ready
   beat** **350ms** before speak-guide TTS / `beginSpeak`.
3. **Speak entry (UI) — design/259:** during the ready beat the UI **stays
   Listen** (`듣는 중` + Listen rail). Do **not** show `말할 준비`. Reveal Speak
   chrome (`말하는 중` + Speak rail) **at the same moment** as beat end /
   `beginSpeak`.
4. **Focus clock:** `beginSpeak` only **after** the ready beat (warmup does not
   count toward the 10‑min block).
5. **Fail-closed:** prepare fail → speak still attempts full `start` as today;
   start fail → skip chunk (unchanged).
6. **Non-goals:** changing pad-after-TTS, STT, volume, evidence kinds, mic
   timing (259 is UI-only).

## Files

| Path | Role |
|------|------|
| `ShadowingMicHandler.kt` | `prepare` + primed `start` |
| `shadowing_practice_screen.dart` | prime in listen · ready beat · UI hold (259) |

## Version

**0.3.237** (mic prime) · UI amend ships in **0.3.259**
