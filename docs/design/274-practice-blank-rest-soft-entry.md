# 274 — Blank rest · section cue · soft entry · adapt wire

Version: **0.3.267** · Status: **locked**

Amends [207](207-practice-section-enter-cue.md) · [215](215-practice-skill-epoch-adapt.md) · [267](267-density-rate-bias.md)

## Locked product

### A. Soft entry + adapt wire + gmin

1. **Wire** `FocusPracticeController.onBlockCompleted` → `PracticeSkillController.onFocusBlockDone` (215 was dead without this).
2. **Soft entry:** on `reason == tier_up`, set **density = +2** (apply layer; decide still returns `tierDelta: 1` only).
3. **tier_down:** **keep** current density (asymmetric; no soft-exit to −2).
4. **Deferred rematch:** after adapt, set pending flag; `_reapplyDensity` only at cycle advance boundary (not mid-speak).
5. **gmin = 0.40** in `densitySkewUnit` (`γ = clamp(1 + 0.35·d, 0.40, 1.8)`).

### B. Blank rest after successful Replay

1. Duration: `(15 / N) × k` seconds where `N = chunkCount` and `k = 1-based step just finished` (snapshot **before** cursor advance). Round to nearest ms.
2. Full sentence / N=1 → 15s.
3. UI: **blank stage overlay** (no countdown, no dots). Leave 「집중 끝내기」 tappable.
4. Settings toggle: `asr.practice.blank_rest` default **on**. Subtitle explains it is intentional rest.
   Judgment cheers + blank rest are **nested** under 「따라 말하기 연습」 (left indent ~28, bodyMedium/bodySmall) — not peer switches.
5. **Skip rest:** speak-fail path, sentence picker jump, when next Listen cannot run.

### C. Section cue + order B

1. Immersive section change: **center section name ~2.0s** (replaces small bottom SnackBar as primary cue).
2. After successful Replay: **advance → (cue if section changed) → blank rest → Listen**.
3. Same section: advance → rest → Listen.
4. Picker jump: cue only, no rest.

## Non-goals

Persistent section badge · rest during speak-fail · take-scoped adapt (215) · symmetric soft-exit on tier_down.

## Kill / prefs

- Blank rest: Settings off or clear pref.
- Rate bias: `ASR_PRACTICE_RATE_BIAS=0` / skill off (267).
- Skill adapt: `ASR_PRACTICE_SKILL=0`.

## Evidence

Keep `focus_block_done` / `practice_skill_adapt`. On soft entry add details `soft_entry: 1`, `density_before`, `density_after`.

## Version

**0.3.267** (0.3.266 feature ship; nested settings chrome)
