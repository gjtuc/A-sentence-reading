# 354 — The boundary from the other side

**Version:** 0.3.350 · Status: **locked**  
Closes a gap [353](353-one-marker-was-one-chance.md) left, and corrects its verdict

## Why

design/353 let a box try its second and third opening sentences, which found 19 boxes that
would otherwise have been lost. It left a gap that the same chip walked past.

`assign_boxes` gives a box every sentence from the one its marker matched. So when the
**second** opening is what won, the box's first sentence — if the model did return it and it
simply was not the marker that matched — stays credited to the **previous** box:

```
previous box's marker matched at 4       cursor 5
this box's *second* opening matched at 7
   → sentences 5 and 6 stay with the previous box
   → but one of them may be this box's first sentence
```

The previous box's **closing** sentence settles it. Matched at output j, the next box starts
at j+1.

## The verdict design/353 got wrong

That field was already built. design/353 measured it as a way to **find** a box whose own
openings had all failed, scored **0 rescues of 354**, and left it unused on the principle
that unproven machinery is debt.

The principle was right and the measurement was of the wrong job. Measured for the job it
was proposed for — **correcting** a boundary rather than finding a box — it matched in **17
of the 18** cases where a later opening won and moved **16 sentences** to the box that
produced them:

| paper | sentences moved |
|---|---|
| `d4cs00527a` | 9 |
| `d4cs00527a` (later run) | 5 |
| `srep41797` | 2 |

That is 0.7% of the corpus's sentences, and it is a **wrong** box rather than an imprecise
one — the distinction that matters, since an unfound marker only costs precision.

`srep41797` shows the other half of the result: a 48-sentence gap where the closing matched
immediately before the win, so nothing had slipped and nothing was moved. The correction
fires on evidence, not on the gap's size.

## Locked

When a box is found by a later opening, the previous box's closing is sought; if it matches
at `j` and `j + 1 < best_i`, the box starts at `j + 1` instead. Reported as
`marker_boundary_fixed_n`.

Without a closing on the previous box there is no evidence, and the boundary is not moved.
The correction can only ever reach back to just after the previous box's own last sentence,
so it cannot take sentences that belong to it.

Marker recovery is unchanged at **99.2%** — this chip moves sentences to the right box, it
does not find more boxes.

## Not this chip

- Using the coordinates in the product
- The 3 markers still unfound, which are sentences the model did not return

## Test

`tests/test_design_354_boundary_from_the_other_side.py` — a returned first sentence no
longer left with the previous box, no correction when the boundary was already right, the
first opening winning needing none, a missing closing leaving the boundary alone, and a
correction never reaching into the previous box's own sentences.
