# 367 — Ask Google for the speed

Version 0.3.404 · Status locked

## The complaint

> 문장 연습을 할 때 사용자의 음성도 배속을 붙이더라고 그래서 더 못알아듣는것 같다고도
> 생각했어. … 원음에서 배속을 가져다 붙이는 방식은 TTS의 음성 품질을 떨어뜨리기도 하고.

Both halves were real.

## What was wrong

The server always synthesized at rate 1.00 and the phone stretched the result
with `AudioPlayer.setPlaybackRate`. Two consequences followed from the stretch
living on the player instead of in the bytes:

1. **The rate leaked onto my own voice.** One `AudioPlayer` serves the TTS
   phase and the playback of my own take. `_playCachedChunkTts` set the rate;
   `_playMyTakePhase` never reset it. At tier 8 my own recording came back
   sped up, which is exactly the phase meant to let me hear myself.
2. **Resampled audio is worse audio.** Time-stretching an MP3 on the device is
   not the same voice speaking faster. Google will speak faster if asked.

The first was only a listening problem, not a scoring one: the recording is
uploaded as raw bytes, so the stretch never reached the scorer. It still made
the one phase that exists to be listened to useless.

## Locked

- **The rate is a synthesis parameter.** `synthesize_mp3` passes
  `speaking_rate` to `AudioConfig`. Nothing downstream stretches anything.
- **The rate is in the cache key.** `cache_key` hashes
  `speak_norm_version | voice | rate | text`. Different speed is different
  audio, so it must be a different entry. The hit rate this costs is near zero
  in practice: random-voice mode plus sentences read once or twice means
  `(text, voice)` rarely repeats to begin with.
- **`clamp_speaking_rate` is the only gate.** 0.5–2.2, matching what the voices
  advertise and covering the whole 50-rung ladder. Google itself accepts
  0.25–4.0.
- **No `setPlaybackRate` call exists in the app.** This is the load-bearing
  part: as long as the call is absent, the leak onto my own take cannot come
  back by someone forgetting a reset. `grep setPlaybackRate mobile/lib` must
  stay empty.
- **The grooming nudge goes into the request.** `_groomRateScale` (design/208)
  is fixed for the cycle before `_ensureChunkTts` runs, so folding it into the
  requested rate is safe and the per-chunk byte cache stays correct.

## Rate sites, after

| Site | Rate |
|---|---|
| `_ensureChunkTts` | `params.speakingRate * _groomRateScale`, clamped |
| miss-review word drill | `playRate`, clamped |
| `TtsController.playText` | `params.speakingRate` |
| my own take | none — the file plays as recorded |

`_heardClientRate` still records what was asked for, so the evidence keeps
telling us what I actually heard.

## Not in this design

The client and server halves must ship together. An old client against a new
server still works (it asks for 1.00 and stretches locally, as before), but a
new client against an old server would ask for 0.75 and be handed 1.00 audio
with nothing left to stretch it. The version bump discipline in design/155
already forces the pair.
