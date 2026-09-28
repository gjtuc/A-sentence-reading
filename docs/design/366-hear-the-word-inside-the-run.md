# 366 - Hear the word inside the run

**Version:** 0.3.403 - Status: **locked**
First use of the audio [364](364-sample-row-one-rung.md) was built to collect - answers
the question 364 left open about the number in [212](212-practice-skill-ladder.md)

## Why

design/364 exists to calibrate one number: the `0.72` sound overlap in
`phonesClose`. Ten sample rounds are now recorded - 619 takes, every round covering
its fifteen lines - so the number can finally be measured instead of argued about.

The answer is that `0.72` was never the problem.

Across 270 scored takes the sound fallback rescued **9 slots**. It was not a
fallback, it was dead weight. `scripts/phone_threshold_probe.py` shows why.

## How it was measured

The probe reads recorded `practice_skill_scored` rows. Labels come from the data,
not from anyone listening again:

* **positive** - the words already matched the slot, so the speaker demonstrably
  said it. Whatever overlap these produce is what a correct read looks like.
* **negative** - the slot's target paired against the heard run of a *different*
  take, which the speaker was not reading. Whatever overlap these produce is what
  a wrong word looks like.

A threshold has to sit above the negatives and below as many positives as
possible. From 211 takes, 1629 slots, 1131 positives and 7383 negatives:

| overlap bin | 0 | 10 | 20 | 30 | 40 | 50 | 60 | 70 | 80 | 90 |
|---|---|---|---|---|---|---|---|---|---|---|
| per-word cut, correct reads | 6% | 21% | 18% | 21% | 7% | 9% | 7% | 4% | 1% | 1% |
| per-word cut, wrong words | 19% | 45% | 19% | 9% | 1% | 1% | 0% | 0% | 0% | 0% |
| walking the run, correct reads | 0% | 0% | 3% | 8% | 10% | 21% | 19% | 11% | 8% | 15% |
| walking the run, wrong words | 6% | 16% | 24% | 29% | 8% | 7% | 4% | 1% | 0% | 1% |

Under the per-word cut the two groups sit on top of each other, so **no** threshold
could have worked. Walking the run separates them: correct reads pile up above 0.5,
wrong words below 0.4.

At the unchanged `0.72`:

| | correct reads kept | wrong words leaked |
|---|---|---|
| per-word cut | 8.0% | 0.5% |
| walking the run | **32.4%** | 2.7% |

## Locked

### 1. The run is walked, not cut

`phonesClose` / `phones_close` search every stretch of the heard run for the
target, through `bestWindowOverlap` / `best_window_overlap`.

The waveform model (`hear_waveform.py`, wav2vec2 CTC) returns **one run of sounds
for the whole take**. The old code cut that run into per-word pieces by eSpeak's
phone count for each word. That assumed the two sides emit the same number of
sounds per word. They do not, so the cut drifted further out of step with every
word, and a late word was compared against a stretch of the right length in the
wrong place.

`_sliceHeardPhones` is deleted rather than fixed: it also threw away whatever run
was left past the last slot.

The stretch is tried one sound short through two sounds long, because the model
splits one sound in two more often than it drops one.

### 2. The threshold stays 0.72

Raising recall by loosening the standard was available and was not taken. The
negatives above are cross-take pairings - a *random other sentence*, which is an
easy negative. Real confusions (`vapour` heard as "paper") sit much closer, so the
true leak at any threshold is worse than the table says. The alignment fix is free;
loosening is not, and nothing here measures the cost.

### 3. The probe imports the shipped function

`phone_threshold_probe.py` calls `best_window_overlap` from the module rather than
keeping its own copy, so the measurement cannot drift away from the product.

## What it recovers

Of 105 slots the words missed, 13 now pass by sound. Four `fed`, one `graphitic`,
one `of` and one `15` match at **1.00** - the acoustic model heard the target's
exact dictionary sounds while the transcript wrote a different word, which is the
case the fallback was built for. `centre`, `c v d`, `rietveld`, `catalyst` and
`alpha` follow at 0.75-0.83.

`reduced`, `produced`, `alumina`, `reforming` and `rinse` stay failing. Those are
real acoustic misses and must keep failing.

## Not in this design

**The CTC posterior table walk and the garbage row.** `hear_waveform.py` still
takes `torch.argmax` over the logits, so the run is one greedy path and everything
the model was unsure about is gone before scoring sees it. Walking the posterior
table needs the model in hand; this machine has no torch, transformers, ffmpeg or
espeak, so it needs either a local install or a server job. The audio is kept, so
this stays possible at any time.

**Short targets.** 367 of 1498 confirmed slots - 24% - have fewer than
`_MIN_PHONES` sounds, so no threshold can ever reach them. They are `the`, `a`,
`to`, `of`, and they are the most common failures left. Lowering the floor is not
supported by this data: two sounds match too much of anything.

**The strictness slider across the 50 rungs.** Still unmeasured.

## Docs

`docs/design/212-practice-skill-ladder.md` - `docs/design/364-sample-row-one-rung.md`
