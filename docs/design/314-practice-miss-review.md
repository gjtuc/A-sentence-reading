# 314 — Missed-word review after replay

Locked. Display text stays the paper. Spoken audio uses the existing MP3 route. `speak_norm` stays v6.

## When

After a successful replay only. Speak failure and sentence jumps do not review and do not rest.

The score started during the take is awaited once, before the cursor advances. A late or missing score means no review. Do not score again. Do not call Gemini on this path.

## Snapshot

Before the cursor moves, keep:

- The missed content-word strings from that score, in display order. Function words stay out. Duplicate words keep only the uncovered count, left to right.
- The skill tier and whether the chunk was `random_auto`, taken when that chunk's listen audio was drawn.
- The blank-rest length from the chunk count and the step just finished. Do not recompute after the cursor moves. Settings off means a scheduled rest of zero.

Then advance, show a section cue if the section changed, then review.

## Screen

Reuse the rest cover. One missed word at a time, paper white, not miss red. Follow light stays off. Clear judgment copy before the first word. Between words the cover is blank for 400 ms, not scaled by rate or rest. Give-up stays tappable.

No missed words: existing rest. Rest setting off and no misses: no rest.

## Audio

Do not write the chunk TTS cache. Send the printed word to `POST /api/tts`. Do not reimplement speak rules. Server synthesize rate stays 1.0. Client playback rate is the only speed.

`random_auto`: draw each word from the snapshotted tier minus 2, clamped at 0, including that tier's locale weights. Do not save the tier. Do not apply density skew or the grooming scale.

Fixed voice: use the voice and client rate just heard. Do not switch to a random tier.

Volume is full. Mic stays off. The speaking-block clock does not start.

A word whose audio fails or does not finish within 12 seconds is skipped. Do not estimate its length.

## After the words

Compare wall time of the review, not a character estimate, with the scheduled rest.

- Shorter than the scheduled rest: blank for the remainder. Do not add 3 seconds.
- Longer, or scheduled rest is zero: after the last word, wait 3 seconds once, then listen.

Give-up, a new cycle token, pause, or background stops playback and does not start the next listen.
