# 259 — Speak UI hold Listen until ready beat

Version: **0.3.259** · Status: **locked**  
Amends [245](245-practice-speak-mic-prime.md) · [214](214-minimal-rhythm-practice-ui.md)  
Depends: [82](82-shadowing-practice-loop.md) · [176](176-focus-practice-pomodoro.md)

## Problem

design/245 primes the mic and waits **350ms** before speak-guide TTS /
`beginSpeak`, but the practice UI flipped to Speak (`_rhythmPhase = speak`,
status `말할 준비`) as soon as Listen TTS ended. Users saw Speak chrome while
the recorder was still settling — the visual cue to speak arrived too early
relative to when speech should start.

## Locked product

| Include | Exclude |
|---------|---------|
| After Listen TTS, **engine** still enters Speak: mic `start` → **350ms** ready beat → `beginSpeak` + speak-guide TTS | Change mic prime / `prepare` / beat length / pad / volume |
| During ready beat, **UI stays Listen**: status `듣는 중` + Listen rail + Listen hairline | Status `말할 준비` (removed) |
| Reveal Speak UI **at the same tick** as ready-beat end: `_rhythmPhase = speak` + `말하는 중` + `beginSpeak()` | Separate display-phase field; delay mic start |
| Fail before reveal (perm / start / unmount): break Listen disguise — error status + idle phase as today | Fake Speak success UI |

## INVARIANT

1. **Mic timing SoT = design/245** — do not move `start` after the beat; do not
   shorten/lengthen `_speakMicReadyBeat` in this chip.
2. **Focus clock** — `beginSpeak` only after the ready beat (unchanged 245/176).
3. **One visual flip** — Speak rail/status/hairline appear together with
   `말하는 중`, not earlier.
4. **Kotlin / MediaRecorder path** — no change in this chip.

## Files

| Path | Role |
|------|------|
| `shadowing_practice_screen.dart` | Hold Listen UI through ready beat; `_revealSpeakUi` |
| `docs/design/245-…` · `214-…` | Amended copy |

## Version

**0.3.259**

## Residual

Post-beat cancel race → [260](260-speak-ui-post-beat-alive-gate.md).
