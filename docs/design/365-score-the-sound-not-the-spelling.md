# 365 — Score the sound, not the spelling

**Version:** 0.3.402 · Status: **locked**

## Why

The first two sample rounds (design/364) produced 130 scored takes with slot marks, so
for the first time it is possible to count *which* slots fail rather than guess. The
four worst are not pronunciation at all:

| Failed slot | Count | What the speaker did | Why it scored zero |
|---|---|---|---|
| `vapour` | 42 | read it correctly | transcript answers `vapor` |
| `ni` | 32 | read "nickel" | the voice expands `Ni`, the spoken text does not |
| `two` | 32 | read "two pee" | transcript writes `2p` as one token |
| `p` | 26 | read "two pee" | same joined token |
| `'` | 14 | nothing to read | the apostrophe was its own slot |

`sound_pass_n` was `0` on every one of them, so the phone fallback did not rescue any.

`Both catalysts' strengths` could **never** score above 3/4: `slot_pieces` was
`['both', 'catalysts', "'"]` and a lone apostrophe has no sound to hear.

This is measurement error, not skill. It also gets worse with difficulty, because the
accent mix widens with the rung (`kTtsSkillLocaleWeights`) and a British or Indian
voice invites British spelling back from the recognizer.

## Locked

Both sides of the compare must fold the same way. `skill_score.dart` and
`practice_skill_score.py` are twins; a change to one without the other is a bug.

### 1. Spelling variants fold

`kSpellingPairs` / `SPELLING_PAIRS`, bidirectional, consulted in `_tokenForms`.

An explicit pair list, not a rule. `-our`→`-or` would eat `four`, `hour`, `pour`;
`-ise`→`-ize` would eat `rise`, `precise`, `promise`; `-re`→`-er` would eat `are`,
`there`, `figure`. The corpus is fixed, so a list can be complete for it, and adding a
pair costs one line.

### 2. Element symbols accept their names

`kElementSymbolNames` / `ELEMENT_SYMBOL_NAMES`, **one-directional**: a symbol slot
accepts the element name, not the reverse. The reverse would let a two-letter fragment
claim a long word.

The root cause is that Google's voice expands `Ni` to "nickel" while the spoken text
handed to the scorer keeps `Ni`. Fixing the expansion instead would only cover the
symbols we thought of; folding at compare time covers whatever the voice decides.

### 3. A joined token pays for both pieces

`splitDigitLetterRun` / `split_digit_letter_run`: a heard `2p` also credits `2` and
`p`; `co2` also credits `co` and `2`. The joined form stays in the bag too.

Both pieces really were spoken — "two pee" is two sounds — so this is not a give-away.

### 4. The slot side folds like the heard side, for the compare only

`_spokenSlots` runs the piece through `canonicalizeSoundAlikes` before tokenising.

Without it the fold was one-sided: the heard side turned "two" into `2`, so a spoken
slot `two` could only be claimed by a transcript that happened to write the digit.
The fold is for the compare only. `slot_pieces` and the miss review still carry
the word the voice reads, so a drill never asks the reader for a digit.

### 5. A slot with no letter and no digit is not scored

`slotTokensScorable` / `slot_tokens_scorable`. The piece is still consumed so the walk
stays aligned, but no slot opens and `ref_n` does not count it.

### 6. A possessive mark is not a sound

`stripApostrophes` / `strip_apostrophes`, applied to both bags. The aligner
sometimes hands the apostrophe its own span (item 5 drops that slot) and
sometimes leaves it riding inside the word, where the slot token is `catalysts'`
and no transcript will ever write it back.

## Not in this design

The remaining failures are acoustic and stay failures: `crystallite` heard as "crystal
light", `Scherrer` as "shorter", `Tafel`, `dec` for "decade", `theta`. Those need the
posterior-table walk and the garbage row, which need the audio design/364 is now
collecting. Do **not** widen the word fold to cover them — a fold that accepts "crystal
light" for `crystallite` stops measuring pronunciation.

Proof the fix is not a give-away: `Vanadium paper was observed` against
`Vanadium vapour was absorbed` still scores 2/4.

## Docs

`docs/design/212-practice-skill-score.md` · `docs/design/364-sample-row-one-rung.md`
