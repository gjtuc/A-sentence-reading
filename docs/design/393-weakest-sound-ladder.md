# 393 — One weakest sound, down and up

**Version:** 0.3.432 · Status: **locked**
Replaces the ladder of [384](384-which-sound-was-missing.md)

## Why

The design/384 ladder painted every failed symbol blue and opened a sound drill
only after the same sound failed two word tries in a row, then climbed back
after two drill tries whether the sound cleared or not. The user wants one
target at a time and a drill that holds until it clears.

## Locked

1. Blue is **one** symbol: the drilled sound, else the least sure of the sounds
   that failed in the last take (`lowestMissedSound`). None failed, none blue.
2. A missed word try drops straight to a drill on that sound. No two-miss wait.
3. A drill plays the word at half speed and judges the drilled sound alone
   (design/384 rule kept). Cleared, the next try is the word again.
4. A drill that misses aims at the weakest failed sound of its own take, which
   may be a different one.
5. The word passing goes to the next word.
6. **7** tries per word, word tries and drills together (`kMissReviewTotalTries`).
   Then the next word. A missed word with nothing to aim at tries the word again.
7. `review_hear` notes `review_step`, `sound_i`, `next_sound_i`.

`MissReviewClimb` holds the steps. `MissReviewLadder` and
`kMissReviewSoundTries` are gone.

## Tests

`mobile/test/miss_review_test.dart` (design/393 tests),
`mobile/test/review_sound_marks_test.dart` (focus).
