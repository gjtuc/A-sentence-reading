# 368 — A dictionary is not a voice

Status locked · the first of the two cuts asked for in design/369

## Why

> eSpeak의 데이터와 관련한 파이프 라인 그리고 STT의 데이터와 관련한 파이프라인 다 끊고
> 시작해야 해. 그것에 의존하지 않도록 말이야. … 불량률이 높은 방식에 은근슬쩍 기대지
> 않게 말이야.

The sound half of the scorer compared two things that were never comparable:

- **target**: eSpeak's dictionary reading of the spelling
- **heard**: a wav2vec2 CTC pass over the recording

Those are two different systems with two different inventories and two different
ideas of how many sounds a word has. design/366 stopped assuming they agreed on
the count, which helped, but it could not fix the premise. A dictionary entry is
not what a voice does with a word.

## The trap this removes

```python
phones = waveform or " | ".join(espeak_ipa_words(heard_text))
```

When the waveform model returned nothing, the "heard sounds" became eSpeak's
reading of the Gemini transcript. The sound compare then ran eSpeak against
eSpeak — a spelling compare wearing a costume — and said nothing about it.

It was not what hurt the scores: across the last 544 recognize calls, 543 came
back `hear_code: ok`, so the fallback almost never fired. It is exactly the kind
of quiet substitution that makes a measurement untrustworthy, so it is gone. An
empty answer is the honest one.

## Locked

- **No dictionary runs anywhere in the server.** `_espeak_ipa`,
  `espeak_ipa_words`, `espeak_ipa_per_word`, `phone_assign`,
  `assign_span_phones` and the `_WORD_IPA` cache are deleted, and `espeak-ng` is
  out of the `Dockerfile`. `phone_match.py` only cuts and compares runs of
  symbols now; `split_phone_units`, `overlap_ratio`, `best_window_overlap` and
  `phones_close` stay, because comparing CTC against CTC needs exactly those.
- **`/api/tts/spoken` spans carry no `phone`.** The eight `phone_*` response
  keys are gone. The `practice_skill_align` evidence row keeps firing with
  `phone_code: espeak_cut_368` so the sensor stays alive and truthful.
- **The device cache no longer refuses a phone-less row.** It used to, because a
  row without symbols meant the server had failed to reach eSpeak. Now every row
  is phone-less, so that gate would have thrown away the whole cache and called
  the server once per sentence.

## What this leaves broken on purpose

The sound pass cannot fire. `phonesClose` still exists on both sides, but the
target it is handed is empty, so every slot now decides on the transcript alone
until design/369 replaces the target with the native voice's own CTC run.

## Not in this design

The transcript half of the cut, and the replacement: synthesizing the native
audio at paper-analysis time, running it through the same CTC model, cutting it
per word with the TTS timepoints, and sliding each word's reference across the
take. That is design/369.
