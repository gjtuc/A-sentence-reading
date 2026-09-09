# 208 — Practice process grooming (focus loop)

Version: **0.3.208**

## Intent

During **shadowing practice focus sessions only**, lightly groom the *process*
(medium: TTS playback rate) when the take looks broken — not motivation,
not daily tips, not pronunciation scores.

## Locked

- **Default action: NONE** (silence)
- **Scope:** `ShadowingPracticeScreen` while focus session is active
- **User-visible copy:** none (no SnackBar / tips / scores / streaks)
- **Speak phase:** no coaching UI; keep design/206 speak TTS volume 50%
- **Listen + speak:** same TTS bytes; rate via `AudioPlayer.setPlaybackRate` only
- **Focus clock:** unchanged (mic speak only); grooming must not count as speak
- **207 section cue:** separate channel; grooming never uses SnackBar
- **Kill:** `ASR_PRACTICE_GROOMING=0` → status false; missing key → on

## Signals (actuate)

| Signal | Actuate? |
|--------|----------|
| `take_fail` (empty / missing / mic start fail) | yes → maybe rate nudge |
| `take_too_short` (file duration ≪ expected) | yes → maybe rate nudge |
| `mic_perm` | **observe only** — never actuate |

## Lever (P2)

- `rate_nudge`: next cycle `playback_rate_scale = 0.90` (one cycle, then clear)
- Caps: max **2** / focus session; max **1** / rolling 5 chunks
- Stochastic apply probability **0.45** when eligible
- Fade: after **2** clean takes, suppress for **6** chunks

## Evidence (add-only)

`practice_grooming_decision` — signal, action, applied, skip reason, scale, chunk key.

## Non-goals

Streaks, cheer, ELSA colors, STT mid-speak, library/reader grooming, A/B compare (Later).
