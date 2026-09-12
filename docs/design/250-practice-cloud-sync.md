# 250 — Practice focus + skill cloud sync

Version: **0.3.241** · Status: **locked**  
Amends [176](176-focus-practice-pomodoro.md) · [212](212-practice-skill-adapt.md) · [215](215-practice-skill-epoch-adapt.md)

## Intent

Survive app uninstall for long-horizon practice accumulators only:

1. Focus calendar blocks (`asr.focus_practice.v1`)
2. Skill tier / density / day accuracy (`asr.practice_skill.v1`)

Local SharedPreferences remain a **cache**. Cloud is SoT for these two blobs.

## Locked

- GCS objects:
  - `{prefix}/users/{uid}/practice/focus_v1.json`
  - `{prefix}/users/{uid}/practice/skill_v1.json`
- API (session auth): `GET|PUT /api/practice/focus/sync` · `GET|PUT /api/practice/skill/sync`
- Payload = existing store JSON + `updated_at_ms` (int, ms epoch; missing → 0)
- Merge:
  - Focus days: per day `max(blocks)`; `best_streak` → `max`
  - Skill days: per day keep larger `n` (tie → larger `sum`)
  - Skill live fields (tier, density, block_*, cooldown, epoch_*): LWW by `updated_at_ms`
- Pull on login / resume; push after local write (debounced OK)
- Soft-fail if GCS down — local continues
- Evidence: `practice_focus_sync` · `practice_skill_sync` (`ok`, `op`, `elapsed_ms` only)

## Non-goals

Papers · bookmarks · TTS prefs · sentence cursor · MES · transcript upload

## Tests

`tests/test_practice_cloud_sync_250.py`

## Version

**0.3.241**
