# 260 — Speak UI post-beat alive gate

Version: **0.3.260** · Status: **locked**  
Amends [259](259-speak-ui-hold-listen-until-ready.md) · Depends [245](245-practice-speak-mic-prime.md)

## Problem

After the 350ms ready beat, `_runSpeakPhase` only checked `mounted` before
`_revealSpeakUi()`. Give Up / sentence jump / pause during the beat could still
flip Speak chrome and start speak TTS.

## Locked product

1. After `_speakMicReadyBeat`, reveal Speak UI only if the same `alive()` as
   `_runCycle`: `mounted && token == _cycleToken && sessionActive && !paused`.
2. If not alive: `stop` mic, return cancel/fail — **no** `_revealSpeakUi`, no
   speak-guide TTS, no `beginSpeak`.
3. Non-goals: beat length, mic prime/start order, Kotlin, volume, `말할 준비`.

## Version

**0.3.260**
