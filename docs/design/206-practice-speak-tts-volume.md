# 206 — Practice speak-phase TTS volume

Version: **0.3.215** (amended; was 0.3.206 @ 50%)

## Locked

During shadowing **speak** phase (mic open + TTS guide), playback volume is **20%**.
Listen phase and my-take replay stay **100%**.

Why: MediaRecorder captures speaker bleed; 50% guide still felt too loud vs user take.

Constant: `_kSpeakTtsVolume = 0.2` in `shadowing_practice_screen.dart`.

See also [215](215-practice-skill-epoch-adapt.md).
