# 364 — A fixed sample row, one rung at a time

**Version:** 0.3.398 · Status: **locked**
Groundwork for calibrating the sound compare added in [212](212-practice-skill-ladder.md) · uses the ladder from [244](244-skill-ladder-position.md) and the phone stream from [169g](169g-causal-handoff-evidence.md)

## Why

The sound compare in `phonesClose` holds one tunable number (`0.72`). Nothing in the
repo says whether that number is right, and three separate obstacles stopped anyone
from finding out.

**The ladder cannot be aimed.** `decideSkillAdapt` is the only caller of
`setTierDensity`, and it moves one rung per epoch of 5–10 focus blocks: down at
≤80%, up at ≥90%. Reaching tier 9 from the default tier 2 needs seven promotions,
so 50–100 blocks at 90%+. A speaker who wants to record a round they will
deliberately fail has no way to get there.

**Paper sentences cannot be measured twice.** The text changes every session, so a
score that moved after a scoring change cannot be told apart from a score that moved
because the sentence was easier. Choosing between two candidate thresholds needs the
same audio run through both.

**The audio is thrown away.** `/api/stt/recognize` reads the upload, hands it to
Gemini and to the phoneme model, and drops it. Only the counts survive
(`hear_bytes`, `pcm_n`, `infer_ms`, `phone_n`). Any later scoring method has to ask
the speaker to record everything again.

## Locked

### 1. The corpus is fixed and local

`mobile/lib/practice_sample/sample_corpus.dart`. Two lists, no server, no PDF.

`kSampleFixedLines` — twelve lines (`f01`–`f12`), read at **every** round. Each one
names what it targets in `note`: `baseline_no_symbols`, `defined_abbreviation`,
`unit_nm_and_decimals`, `formula_and_ratio`, `greek_spelled_and_degrees`,
`orbital_label_and_ev`, `th_cluster`, `r_and_l`, `v_and_b`, `stress_shift`,
`final_consonant_clusters`, `long_compound_paper_style`.

The same twelve at every rung is the point: the text is held still so the only
variable left is the rung. Memorisation is accepted here.

`kSampleFreshLines` — thirty lines (`n01`–`n30`), three per round, never reused.
First-exposure difficulty stays real, which is what keeps a hard round failing once
the fixed twelve are known by heart.

Vocabulary is drawn from the speaker's field (catalysis / materials) because that is
where the recognizer already failed: `nm` had to be spoken as letters, `a` as "A".
Sentences are written for this file, not lifted from a publisher PDF.

Chunk marks live in the text as `|` (`kSampleBreak`), so the plan is authored here
rather than asked of Gemini.

### 2. One rung, held

`SkillState.pinned` with `savedTier` / `savedDensity`. `decideSkillAdapt` returns
`pinned` before every other branch; `resolveSkillAdaptApply` treats that like
`cooldown` and changes nothing.

Three things the pin must also do:

- **`bindUid` drops it.** A pin that survived a kill would silently hold every later
  paper on that rung. A starting round re-pins immediately after the bind.
- **`addScored` keeps pinned takes out of `days`.** A sweep deliberately runs rungs
  the speaker cannot reach; folding a 20% hard round into the day would report a
  skill drop that did not happen.
- **`unpinLadder` restores the remembered rung** and clears `epochMeans`,
  `blockSum`, `blockN`, `cooldownBlocks`, so the sweep leaves no residue.

Round `1..10` maps to tier `0..9` at a single fixed density, so the length axis is
locked and the rung differs only in TTS rate and accent mix (`kTtsSkillTier`,
`kTtsSkillLocaleWeights`).

### 3. The audio is kept — for sample rounds only

`src/sentence_reading/llm/sample_takes_gcs.py`. Object name comes from
`personal_object_name`, so a take lands in the speaker's own space:

```
{prefix}/users/{uid}/sample_takes/r{round:02d}/{line}_{ms}_{digest8}.m4a
{prefix}/users/{uid}/sample_takes/r{round:02d}/{line}_{ms}_{digest8}.json
```

The sidecar carries what is needed to score the take again later: `expected`,
`heard`, `heard_phones`, `chunk_index`, `skill_tier`, `skill_density`, `tts_voice`,
`tts_rate`, `app_version`, and the numeric `hear` report.

`tts_voice` and `tts_rate` are filled by the client, not the server, because the
random pick happens on the phone — only it knows which voice was actually played.

**Untagged takes are not kept.** `sample_round` defaults to `0` and
`sample_round_ok` refuses it. Keeping every practice take would be storage and a
privacy surface for data no calibration run needs.

`save_sample_take` never raises into the request path and returns one snake code for
every skip: `bad_round`, `empty_audio`, `too_large`, `bad_line_id`, `gcs_unready`,
`no_uid`, `audio_upload_failed`, `audio_upload_raised`, `meta_upload_failed`,
`meta_upload_raised`, `ok`. A lost sidecar reports failure rather than success,
because an unlabelled take is not a usable sample.

### 4. The row is not a paper

`isSampleCacheId` guards four places:

- `_toggleSelected` and `_selectFromMenu` refuse it, and the checkbox is disabled.
  A delete would 404 forever (`client.deletePaper` throws on 404) and
  `purgeDueSoftDeletes` would keep re-emitting `delete_fail`.
- `ensureShadowingChunks` returns early. The plan is on disk and the server has no
  such paper, so asking would only raise a banner on a working row.
- `_open` routes to `_openSample`, which skips the reader entirely: there is no
  paper to read, and the pin has to last exactly as long as the practice screen.

The row is seeded by `ensureSampleRow` on uid bind, which writes `session.json`,
the chunk plan (`status: 'ok'`), and the disk index entry, then triggers one
`refresh(trigger: 'sample_seed')`. `sampleRowNeedsWrite` compares
`kSampleSeedVersion` and the sentence count, so a later corpus edit rewrites the row
and an unchanged one does not refresh.

### 5. Progress is counted in takes

`sample_rounds.dart`. A round is done at `sampleRoundTarget` takes, not at "opened
it once" — a round abandoned after two sentences must not read as collected.

## Evidence

- `practice_sample_seed` (client, `lifecycle`) — `sentence_n`, `seed_version`
- `practice_sample_take` (server, `stt_recognize`) — `round`, `chunk_index`,
  `skill_tier`, `skill_density`, `take_saved`, `take_bytes`, `take_code`

Both carry integers and one snake code, so the sanitizer in design/169g passes them
without a free-text allowance.

## Not in this design

The scoring change these samples exist to calibrate. The table walk over CTC
posteriors, the "not a target" row that absorbs a restart, and the strictness slider
across the 50 rungs all wait until there is recorded audio to try them on. Raising
`0.72` before that audio exists is explicitly out of scope.

## Docs

`docs/design/212-practice-skill-ladder.md` · `docs/design/244-skill-ladder-position.md`
