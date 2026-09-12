# 206 — Practice speak-phase TTS volume

Version: **0.3.255** (amended; was 0.3.206 @ 50%, 0.3.215 @ 20%)

## Locked

During shadowing **speak** phase (mic open + TTS guide: TTS+따라말하기), playback volume is **5%**.
Listen phase (1. TTS) and my-take replay (3. 다시 듣기) stay **100%**.

Why: MediaRecorder captures speaker bleed and 20% guide still felt overwhelming during user vocalization. 5% provides a faint timing anchor without drowning user voice.

Constant: `_kSpeakTtsVolume = 0.05` in `shadowing_practice_screen.dart`.

See also [215](215-practice-skill-epoch-adapt.md).
