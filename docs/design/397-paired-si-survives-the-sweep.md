# 397 — A paired SI survives the sweep; Wiley citations are citations

**Version:** 0.3.437 · Status: **locked**

## Why

One Main+SI import (Adv Mater 2016 Pt–Co, `job_547ca83a0d0f` main,
`job_b51e7fe85acc` SI) left the library with the main paper only.

1. Both jobs finished. The SI arrived on the phone (24/24 files, ack, cloud copy
   wiped). In the same second the pairing pass folded it under the main row
   (`collapsed_n 1`), and `sweepLocalResidues` deleted its folder
   (`paper_residue_sweep deleted_n 2`, `library_index_upsert remove caller purge`).
   The keep set was the visible rows plus soft-hidden ids. A folded SI is in
   neither, and its folder is what the merge reads. The server copy was already
   wiped, so it could not come back.
2. Five minutes later another instance, holding a poll snapshot of the SI job at
   88%, swept it. Reclaim answered `job_already_done`, and the sweeper still
   wrote `worker_lost` / `server_job_terminal_error`.
3. In the main paper, Azure gives Wiley citation marks as `[ 1 ]`, `[ 5f, 7 ]`,
   `[ 1a,e ]`. The bracket rule wanted a digit right after `[` and digits only, so
   14 of 18 marked sentences kept the mark on screen and opened no reference row,
   though 22 references were parsed. `[001]` (a zone axis) was read as entry 1.

## Locked

1. `residueLibraryIds` (`mobile/lib/services/paper_residue.dart`) adds each row's
   `pairedCacheId` to the residue keep set. `_rebuildLibraryHashSet` already
   treated the folded mate as in the library; the sweep now agrees.
2. The bracket rule is one pattern in `cite_refs.py`, `static/cite_refs.js` and
   `mobile/lib/api/cite_refs.dart`: spaces allowed inside, `5f` is entry 5,
   `5a–c` is entry 5, a bare `e` after `1a,` adds nothing, no leading zero.
   A test asserts the three copies hold the same pattern.
3. Sweeper: `job_already_done` copies the shared terminal state into the stale
   copy (`_adopt_gcs_terminal`), records `skipped_already_terminal`, and never
   marks lost. Other reclaim failures are unchanged.

## Not this chip

- `Body ⚠` (`high_body_ratio:0.97`). An Adv Mater Communication has no body
  headings, so one Body section is the paper's shape, not a split failure.
- `Acknowledgement` as a section. design/340 left it as prose on purpose.
- Reference 9 missing from the 22 parsed (the paper has 23).
- The split handoff reads `practice_chars 30` / `refs_share 0.999` for this paper,
  while the same function on the PyMuPDF text keeps 27,621 characters. The server
  input differs; not traced here.

## Tests

`tests/test_design_397_paired_si_and_wiley_cites.py`,
`mobile/test/paper_residue_sweep_test.dart`, `mobile/test/cite_refs_test.dart`.
