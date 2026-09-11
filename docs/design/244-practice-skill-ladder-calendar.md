# 244 — Practice skill ladder on focus calendar

Version: **0.3.236** · Status: **locked**

받침: [176](176-focus-practice-pomodoro.md) · [212](212-practice-skill-adapt.md) · [215](215-practice-skill-epoch-adapt.md)

## Intent

Show the learner’s **current practice difficulty position** on the focus
calendar heat legend — competitive ladder feel, not social ranking.

## Locked product

1. **Surface:** `focus_practice_calendar_sheet` legend row only (live sheet).
   Do **not** patch legacy `practice_focus_calendar_sheet`.
2. **Copy:** `적음 ■■■■ 많음 · 난이도 n/30` (exact prefix `난이도`).
3. **SoT:** `SkillStore` `tier` + `density` only. Never TTS prefs
   (`asr_tts_skill_tier_v1`).
4. **Formula (harder ↑):**  
   `hardness0 = tier×5 + (2 − density)` → `0..29`  
   display `n = hardness0 + 1` → `1..30`  
   Default tier 2 / density 0 → **13/30**.
5. **Density direction:** higher density = finer = **easier** = lower `n`.
6. **Null / skill kill:** `난이도 —` (same spirit as 인식 `—`).
7. **Snapshot:** sheet open time is enough (SkillStore not Listenable).
8. **Caption:** note that color = block count; 난이도 = ladder position.
9. **Non-goals:** evidence kinds, adapt/grooming/TTS pick changes, leaderboard,
   Settings exposure, mid-sheet live refresh.

## Files

| Path | Role |
|------|------|
| `mobile/lib/practice_skill/skill_ladder.dart` | pure formula + label |
| `mobile/lib/widgets/focus_practice_calendar_sheet.dart` | legend UI |
| `mobile/lib/screens/shadowing_practice_screen.dart` | pass skillFeatureOn |
| `mobile/test/practice_skill_ladder_test.dart` | direction + defaults |

## Version

**0.3.236**
