# 370 — A transcript is not a pronunciation

## The question the app was asking

Until now a word passed when a speech recogniser, given the recording, typed the
same letters back. That is a reading-comprehension test for the recogniser, not
a pronunciation test for the reader. It fails in both directions:

- A word said perfectly fails, because the recogniser wrote `their` where the
  paper printed `there`, or `2p` where it printed `2 p`, or gave up on `Ni`.
- A word said wrong passes, because the recogniser guessed the sentence it
  expected from context instead of writing what it actually heard.

design/365 spent a whole layer forgiving the first kind: spelling pairs
(`vapour`/`vapor`), element symbols read as names (`Ni` → `nickel`),
digit-letter splits, possessive marks, number words, `their`/`there`/`they're`,
plural tolerance. Every one of those rules existed to undo damage the transcript
had done. None of them could touch the second kind, which is the one that makes
a score dishonest.

design/368 removed eSpeak, which had been supplying the *target* side of the
sound compare by looking the spelling up in a dictionary. This change removes
the other half: the transcript.

## What the app asks instead

A word passes when the sounds in the recording line up with **the sounds the
native voice makes for that word**. Nothing reads letters. The pass/fail
decision has exactly one input on each side:

| side | before | now |
|---|---|---|
| target | eSpeak's dictionary reading of the spelling | the native voice's own recorded sounds |
| take | Gemini's transcript, re-read by eSpeak | the waveform model's pass over the recording |

Both sides now come from audio through the same model, so a symbol on the left
means the same thing as a symbol on the right. That was never true before.

## What changed

### Server

`/api/stt/recognize` returns `heard_phones`, `engine`, `waveform_phones`,
`hear_code`, `hear_detail`. It no longer returns `heard`, `compare`, or any
`phone_*` key, and it asserts that `score` and `heard` are absent before
answering.

The route used to sit behind a Gemini availability gate and return early when
Gemini refused — which took the sounds down with it, even though Gemini has no
part in producing them. That gate is gone. The waveform pass runs on its own.

`practice_skill_score.py`: `spoken_slot_coverage` takes `heard_phones` and
judges each slot with `phones_close(slot_phone, heard)`. `content_words` and
`content_word_coverage` (the design/212 v1 scorer, dead on the live path) are
deleted.

### Device

`skill_score.dart`: `diagnoseSpokenSlots` no longer takes `heard`. A slot is a
`(start, end, tokens, phone)` — the tokens are for the review prompt and the
evidence row, the `phone` is what decides. The design/365 word fold is deleted
in full, along with `contentWordCoverage`, `missedContentSpans`,
`splitDigitLetterRun`, `stripApostrophes`, `canonicalizeSoundAlikes`,
`kSpellingPairs`, `kElementSymbolNames`, `kNumberWordDigits`, `takeSkillToken`
and the `their`/`there` helpers.

`miss_review.dart`: `missReviewHeardMatches`, `missReviewHeardTooLong`,
`traceMissReview` and `MissReviewTrace` are deleted. The length gate they
enforced existed because a recogniser asked for one word would write the whole
sentence from memory; a run of sounds cannot do that.

## `sound_ref_missing` — the honest unscored answer

If no slot carries a reference sound, there is nothing to compare against.
Returning 0% would blame the reader for a missing reference, so the take comes
back unscored with `error: sound_ref_missing` (`kSoundRefMissing` on the
device), `accuracy: None`, and the caller records that it was not scored.

This is the state the app is in **today**: the reference sounds do not exist
yet. Until the TTS→CTC reference lands, every take is unscored, and the
difficulty ladder and the missed-word review stay still. That is deliberate.
A scorer that guesses is worse than one that admits it cannot answer.

**Do not deploy this to live on its own.** Live must never carry a version that
cannot score. The next change produces the reference, and the two ship together.

## Cost paid knowingly

`kPhoneMinUnits = 3` (design/366) means a word whose reference is under three
sounds cannot be judged by sound at all — `the` is `ð ə`, two units. Those words
fall into the review list every time. Short function words were the ones the
transcript handled best, so this is a real regression on them, accepted because
the alternative is a compare with too little signal to mean anything. A
reference long enough to judge them needs the word cut out of the native audio,
which is what the SSML timepoint work provides.

## Kept on purpose

`hear_waveform.py` is untouched and is the foundation of what comes next.
`practice_skill_stt` stays in the evidence floor: it names a *stage* — "what
came back from analysing the recording" — not Gemini, so the sensor keeps firing
with real CTC content in it. Shrinking the floor here would have been the
hollow-sensor move design/369 exists to prevent.

## Tests

- `tests/test_practice_skill_212.py` — rebuilt around reference sounds. Includes
  `test_design_370_the_twins_agree_on_the_threshold`, which fails if
  `skill_score.dart` and `phone_match.py` drift apart on `0.72`, `3`, or the
  `sound_ref_missing` spelling.
- `tests/test_stt_server.py::test_api_recognize_edges` — sounds come back with
  Gemini down; no `heard`, `score` or `compare` in the body.
- `mobile/test/practice_skill_test.dart` — 17 tests, rebuilt.
- `mobile/test/miss_review_test.dart` — 14 tests; the three transcript tests are
  gone and a note in the file says which.

## See also

- design/365 — what the word fold did, for anyone wondering why it existed.
- design/366 — the window walk and the `0.72` / `3` calibration.
- design/368 — removing eSpeak from the target side.
- design/369 — the guards that stop a sensor from being satisfied by a comment.
