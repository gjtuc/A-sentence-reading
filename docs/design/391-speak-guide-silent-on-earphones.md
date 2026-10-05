# 391 — Speak guide silent on earphones

**Version:** 0.3.431 · Status: **locked**
Amends [206](206-practice-speak-tts-volume.md) · [215](215-practice-skill-epoch-adapt.md)

## Why

In the speak phase the guide voice was 0 on the phone speaker but 5% when
earphones were connected (`hasHeadset`). The user wants the speak phase to be
the same everywhere: they say the chunk alone, with no native voice.

## Locked

1. Speak phase (`tts_speak`) plays the guide at volume **0** on every output,
   earphones and Bluetooth included. `_kSpeakTtsVolume = 0.0`.
2. The guide still plays, silent. The follow light and the speak window keep
   the player's clock, as on the phone speaker before.
3. Listen phase and my-take replay stay at 100%.
4. The screen no longer asks `hasHeadset`. The Android handler keeps the method.
5. `shadowing_loop_event.tts_volume_pct` reports the volume actually set.

## Tests

`tests/test_speak_guide_silent_391.py`
