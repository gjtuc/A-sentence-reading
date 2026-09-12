# design/176 — focus practice (10‑min speaking blocks)

## Intent

Mirror tomato Pomodoro **layout** on the shadowing practice screen:

- Practice **sentence above** the big timer
- Optional camera strip stays small (not hero)
- **GIVE UP** ends the focus session (day success kept)
- Classic chunk loop (listen → speak → next) stays as material

**Not** a 25‑min work/rest Pomodoro product copy — mission is **10 minutes of speaking**.

## Clock contract (plan C)

| Counts | Does not count |
|--------|----------------|
| Mic speak segment open (`beginSpeak` → `endSpeak`) | TTS listen-only |
| | App background / `GIVE UP` / paused |

- Block length: **10 minutes**
- First completed block → **day success** (local prefs)
- Overflow continues into the **next** 10‑min block (blocks stack)
- Prefs key: `asr.focus_practice.v1.{uid}` — `{day, success, blocks_completed}`
- Day key is device-local `yyyy-MM-dd`

## Files

| Path | Role |
|------|------|
| `mobile/lib/api/focus_practice_models.dart` | Day state · serialize · clock format |
| `mobile/lib/api/focus_practice_store.dart` | SharedPreferences |
| `mobile/lib/state/focus_practice_controller.dart` | Session · speak segments · evidence |
| `mobile/lib/screens/shadowing_practice_screen.dart` | Tomato chrome + mic hooks + auto-advance |
| `mobile/test/focus_practice_test.dart` | Clock / day / overflow |

## Evidence (add-only)

`focus_session_start` · `focus_session_end` · `focus_block_done` · `focus_day_success`

Floor version **0.3.159**.

## Out of scope (this chip)

- Server-side daily success sync
- Streak / social / rewards
- Replacing chunk plan generation
- True continuous open-mic (still chunk TTS+mic loop; clock only while mic open)

## Ship

App / pubspec / config **0.3.159**. Commit / deploy when asked.

## Amend (design/250)

Focus calendar history (`asr.focus_practice.v1`) syncs to GCS `users/{uid}/practice/focus_v1.json` via `GET|PUT /api/practice/focus/sync`. Cloud is SoT; local prefs are cache. See [250](250-practice-cloud-sync.md).
