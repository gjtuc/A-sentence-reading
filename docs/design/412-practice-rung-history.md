# 412 - Practice rung history, and the fields the skill sync dropped

## Problem

The reader asked how the practice rung had moved. The evidence log keeps seven days
(design/169g), so nothing older than 10/12 was left, and the phone kept only the current
rung. The rung was 17/50 (tier 3, density 1) against a start of 13/50, with daily
averages mostly under 90%.

The skill sync (design/250) explained it. `normalize_skill_store` kept the rung, the
days and the epoch, and dropped `pinned`, `saved_tier`, `saved_density` and the
design/371 pass line. `pushSkill` then wrote the server's reply over the phone's copy.

- A sample round (design/364) pins a rung and remembers the one to return to. Killed
  mid-round, the phone's stored copy no longer said it was pinned, so the bind that
  drops a stale pin found nothing to drop and the round's rung became the account's.
  Round 4 (tier 3) ran across a night, 9/26 23:25 to 9/27 13:18.
- The pass line restarted cold every session: `line_n` 1108 at the end of the 10/12
  session read 0 at the start of 10/13; 1329 on 10/13 was gone on 10/14.

## Change

- Server (`practice_gcs.py`) keeps `pinned`, `saved_tier`, `saved_density`, the line
  (`line_avg`, `line_var`, `line_n`, `line_unit`; absent without a unit), `history`
  and `ladder_fix`. A merge against a client that sends no line keeps the learned one;
  a missing pin means not pinned.
- Phone (`practice_cloud_sync.dart`) merges the push reply with what it sent instead
  of taking the reply whole. Its own copy wins a tie.
- `mergeSkillStates` takes the union of the history, the larger `ladder_fix`, and the
  learned line over an empty one.

## History (`practice_skill/skill_history.dart`)

One row per epoch decision (hold included), sample round start and return, a stale pin
dropped on bind, and a reset. Each row has the time, the reason, the rung before and
after, the epoch average and block count, and the two lines in force. At most 400 rows,
synced in `skill_v1.json`.

- In the app: 연습 캘린더 → 「난이도 기록 보기」, newest first.
- From a PC: `python scripts/skill_history.py` prints the days and the rows.
- `practice_skill_adapt` evidence also carries `tier_before`, `finer_line`,
  `coarser_line`.

## One-time reset

`kSkillLadderFix = 1`. A bind that finds `ladder_fix` under it puts the account on
13/50 (tier 2, density 0), clears the epoch, writes a `reset` row and stores the mark.
The reader chose this over keeping 17/50. A fresh account starts with the mark set.

## Practice numbers

- Missed-word review: 3 tries in all (`kMissReviewTotalTries`), was 7. Word, its
  weakest sound, word again.
- Epoch lines: finer at or under 75%, coarser at or over 85% (was 80 and 90). The
  reader's choice.

## Tests

`tests/test_design_412_skill_history.py`, `mobile/test/practice_skill_test.dart` and
`mobile/test/practice_cloud_sync_250_test.dart` (design/412 cases at the end),
`mobile/test/miss_review_test.dart`.
