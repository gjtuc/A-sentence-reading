# 214 — Minimal rhythm practice UI + judgment cheers

Version: **0.3.214** · Status: **locked**

받침: [82](82-shadowing-practice-loop.md) · [176](176-focus-practice-pomodoro.md) · [212](212-practice-skill-adapt.md) · [213](213-practice-skill-evidence.md)

## Intent

Reskin **practice mode only** as a **minimal rhythm stage** (dark, sparse, one
accent, easy to read) and show **English judgment cheers** when a take is
scored — like a rhythm-game hit callout, not a stiff accuracy toast.

## Locked product

1. **Surface:** `shadowing_practice_screen` only. Reader / library / settings
   chrome outside practice unchanged (settings may host the cheers toggle).
2. **Concept:** minimal rhythm — not neon arcade, not confetti-per-take.
3. **Loop unchanged:** listen TTS → TTS+speak → my-take replay → next.
4. **Phase UX:** keep Korean status (`듣는 중` / `말하는 중` / `내 녹음 듣는 중`)
   plus a **3-step rail** (Listen · Speak · Replay). Active step filled; thin
   top hairline tinted by phase.
5. **Cheers timing:** when `onTakeReady` returns scored accuracy (may land
   during or near end of replay). Do **not** block replay. Unscored / STT fail
   → no cheer.
6. **Bands (same as 212 adapt):** `<60%` / `60–75%` / `≥75%` → Good / Great /
   Perfect copy pools. English only. Playful rotating lines; no blame
   (`Bad` / `Failed`).
7. **Per-take motion:** center-over-text pop + fade (~0.9–1.1s),
   `IgnorePointer`, tier color, optional tiny `%`, light haptic by tier.
8. **Pref:** `asr.practice.judgment_cheers` default **on**.
9. **Evidence (213 piggyback):** add `judgment_tier` = `good|great|perfect` on
   `practice_skill_scored` details only. No copy string / transcript / audio.

## Palette

| token | hex |
| --- | --- |
| stage | `#121212` |
| rail idle | `#333333` |
| listen | `#8E8E8E` |
| speak | `#5B9FD4` |
| replay | `#6B6B6B` |
| good | soft amber |
| great | green |
| perfect | gold |

## Later

- Combo streak / milestone confetti
- SFX pack
- On-device file ASR (faster judgment after speak)

## Version

**0.3.214**
