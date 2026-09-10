# 215 — Practice skill epoch adapt (Bitcoin-style window)

Version: **0.3.215** · Status: **locked**

받침: [176](176-focus-practice-pomodoro.md) · [206](206-practice-speak-tts-volume.md) · [212](212-practice-skill-adapt.md) · [213](213-practice-skill-evidence.md) · [214](214-minimal-rhythm-practice-ui.md)

## Intent

Stop mid-block difficulty whip-saw. Adapt only after several **completed
focus blocks**, using the mean of those block means — inspired by Bitcoin
difficulty retargeting over a window of blocks.

## Locked (replaces 212 §9 adapt timing/thresholds)

1. **Per take:** score + judgment cheer only. **No** density/TTS adapt on take.
2. **Per focus block done:** if the block had ≥1 scored take, push
   `block_mean = blockSum/blockN` into an epoch list; clear in-block accum.
3. **Epoch length N:** uniform random **5..10** inclusive. Drawn when epoch
   starts (fresh install / after an epoch resolves). Persisted in skill prefs.
4. **When `epochMeans.length >= N`:** compute
   `epoch_avg = mean(epochMeans)`, then:
   - **≤80%** → density +1 (finer); else if soft-max → TTS tier −1
   - **≥90%** → density −1 (coarser); else if soft-min → TTS tier +1
   - **80–90%** → hold
5. After resolve (whether hold or change): clear `epochMeans`, draw new N,
   apply cooldown on tier change as before.
6. **Judgment cheers (214)** stay on take bands **&lt;60 / 60–75 / ≥75** —
   orthogonal to adapt thresholds.

## Speak TTS volume (206 amend)

Speak-phase guide TTS volume: **20%** (`_kSpeakTtsVolume = 0.2`).
Listen + my-take replay remain 100%.

## Evidence

Piggyback `practice_skill_adapt` with `phase=epoch_adapt` and numeric details:
`epoch_n`, `epoch_target`, `epoch_avg` (no transcripts).

## Version

**0.3.215**
