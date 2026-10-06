# 392 — A spoken word nobody printed

**Version:** 0.3.432 · Status: **locked**
Amends [371](371-sound-reference.md) (`spoken_lo`/`spoken_hi`)

## Why

`Pt/CNT` is read `platinum on C N T`. The slash becomes a spoken word that no
printed word owns. The walk in `align_display_report` gives each printed word
the next spoken word when its own spelling does not match, so `CNT` took `on`,
`prepared` took `C`, `by` took `N`, `CVD` took `T`, and `prepared by C V D` was
left over (`trailing_residue`, cursor 150 of 167 on the phone). Every symbol
after the slash sat one word late.

The same slide came from markup. `sub` of `<sub>` was a printed word and took
a spoken word.

## Locked

1. A printed word whose spelling does not match at the cursor is looked for
   after up to **2** spoken words (`_INSERTED_MAX`). Found, it owns the skipped
   words too (`CNT` → `on C N T`). Only when that fails does it take one spoken
   word as before.
2. A match found that way has to end at a word edge, or `C` would claim the
   front of `CVD`.
3. Words inside `<...>` are dropped like a dropped parenthesis: weight 0, empty
   spoken slice.
4. The normal match keeps its prefix behaviour. `O<sub>2</sub>` read `oxygen`
   splits the one spoken word between `O` and `2`, and an edge check there
   slid every later word (measured: 28 lines that lined up stopped lining up).
5. `inserted_n` counts (1) in the report, in `practice_skill_align` and in the
   `/api/tts/spoken` reply (`align_inserted_n`).
6. The phone's spoken cache key carries `kSpokenAlignRev = 'a392'`, so rows the
   old walk wrote are asked for again. The speak-norm version is not bumped,
   because it is in the sound reference key and would rebuild every reference.

## Measured

Every sentence of the 7 local papers plus two fronts of each, 2157 lines:
lined up to the end 1239 → 1846. The 5 lines that stopped lining up were
already slid under the old walk and line up word by word now except at the end.

## Tests

`tests/test_align_inserted_392.py`
