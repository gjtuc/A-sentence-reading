# 246 — Practice sentence cursor (separate from reading)

Version: **0.3.237** · Status: **locked**

받침: [21](21-progress-restore.md) · [82](82-shadowing-practice-loop.md) · [123](123-progress-restore-precise.md)

## Intent

Reading and practice each remember **their own** last sentence per paper.
Opening practice must not jump to (or overwrite) the reading cursor.

## Locked product

1. **Reading progress** (`asr.progress.v1`) unchanged — library ↔ reader still
   saves/restores reading sentence+figure.
2. **Practice progress** new prefs `asr.practice_progress.v1` (+ uid): per
   `cache:<id>` → `{sentence_index, chunk_index, at}`.
3. Practice navigates with a **local** sentence/chunk index — does **not** call
   `library.goToSentenceIndex` / `advanceSentence` (those mutate reading).
4. On practice open: load practice row; if missing, **seed once** from current
   reading `sentenceIndex`; then skip empty-chunk sentences locally.
5. Persist practice cursor on sentence/chunk change, app pause, dispose, give-up.
6. Soft clamp: invalid stored index → seed from reading (do not fail-closed open).
7. Non-goals: cloud sync of practice cursor, changing reading fail-closed rules.

## Files

| Path | Role |
|------|------|
| `practice_progress_store.dart` | load/save/clamp |
| `shadowing_practice_screen.dart` | local cursor · no reader mutation |

## Version

**0.3.237** (ships with design/245 mic prime)
