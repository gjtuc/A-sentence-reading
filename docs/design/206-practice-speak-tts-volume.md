# 206 — Practice speak-phase TTS volume

Version: **0.3.206**

## Locked

During shadowing **speak** phase (mic open + TTS guide), playback volume is **50%**.
Listen phase and my-take replay stay **100%**.

Why: MediaRecorder captures speaker bleed; full-volume guide drowned the user on replay.

Constant: `_kSpeakTtsVolume = 0.5` in `shadowing_practice_screen.dart`.
