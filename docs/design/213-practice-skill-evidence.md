# 213 — Practice skill dense evidence (first-use observation)

Version: **0.3.213** · Status: **locked**  
받침: [212](212-practice-skill-adapt.md) · [169](169-agent-evidence-bus.md) · [209](209-practice-cycle-wide-evidence.md) (killed — do not revive those kinds)

## Intent

While skill adapt (212) is new, collect **dense numeric/enum evidence** so we can
inspect real distributions and choose product direction later.

## Locked

1. **No transcript, no audio, no chunk/spoken text** in evidence (169 P5).
2. **Local durable JSONL queue** during practice; **deferred flush** after focus
   end / app pause / screen dispose (not mid-cycle spam only).
3. Also mirror into `EvidenceBus` when bus enabled (best-effort).
4. Kinds (add-only):
   - `practice_skill_spoken` — spoken fetch hit/miss/ms/version pin
   - `practice_skill_stt` — recognize outcome, bytes, ms, engine enum
   - `practice_skill_scored` — accuracy, bins, ref_n/hit_n, density, tier
   - `practice_skill_unscored` — reason enum
   - `practice_skill_adapt` — density/tier deltas, soft-bound flags, reason
   - `practice_skill_flush` — batch flush meta (counts only)
5. Kill: `ASR_PRACTICE_SKILL_EVIDENCE=0` → status false; missing → **on**
   (observation default). Still requires skill feature on for scoring path.
6. Cap local queue ~5000 events; drop oldest.
7. **Not** design/209 kinds (`practice_cycle_wide` stays dead).

## Details allowlist (snake only)

accuracy, accuracy_pct, accuracy_bin, judgment_tier, ref_n, hit_n, list_v,
schema_v, density, tier, density_delta, tier_delta, can_finer, can_coarser,
block_n, cooldown, take_bytes, stt_ms, spoken_ms, cache_hit,
chunk_index, chunk_n, sentence_id_h16, speak_norm, engine, phase,
reason, code, pending_n, accepted, dropped, focus_elapsed_ms,
epoch_n, epoch_target, epoch_avg

(`judgment_tier` = `good|great|perfect` — design/214; no copy string)
(`epoch_*` — design/215 epoch adapt)

## Version

**0.3.213**
