# 346 — The service's boxes, the paper's letters

**Version:** 0.3.342 · Status: **locked**  
Fixes [345](345-characters-the-paper-never-printed.md)

## Why

design/345 found that the layout service's *reading* of a page changes between calls.
One run of `1-s2.0-S1385894724017960` replaced every `o` with a two-character
sequence — 1,483 times, in the sentences the reader would say aloud — and the next run
of the same file was clean. An RSC review came back with `y` as `γ` 440 times
(`catalγst`, `Honeγwell`) and its next run was clean too.

The PDF's embedded text does not vary and was right every time.

The two strengths are separable, and that is the whole idea. The service is good at
saying **where** a paragraph sits and **in what order** the paragraphs run — work the
embedded text cannot do, since it carries no column or role structure. The PDF is good
at saying **which letters** are in it. So keep the boxes and take the letters from the
paper.

No similarity matching is needed. The boxes already carry page coordinates in PDF
points, so the paper's own words inside a box can be asked for directly.

Where the two readings disagreed, the PDF was right every single time:

| service read | the paper prints |
|---|---|
| `BaZro.9` | `BaZr0.9` |
| `6gb` | `σgb` |
| `Ap(0)` | `Δφ(0)` |
| `PH20` | `pH2O` |
| `"total` | `σtotal` |

## Locked

Words whose **centre** falls inside the box, not `get_text(clip=...)`. That call keeps
any line *touching* the rect and keeps it whole, so a neighbouring line two points away
arrives in full. On Scientific Reports it pulled in about as many foreign words as the
paragraph had — 64 of 91 paragraphs contaminated, agreement 0.549. Centre containment
brought that to **0 of 91**.

Measured over four papers, 700 paragraphs of 80 characters or more:

| | |
|---|---|
| the service's words present in the clip | median **1.0000** |
| the clip's words present in the service | median **1.0000** |
| word **order** similarity | median **1.0000**, none broken |
| real paragraphs with no embedded text | 3 |

Three refusals, each from a case in that corpus:

- **`kept_no_embedded`** — axis ticks (`0.0 0.1 0.2`), legend labels (`BZY10-1650`) and
  logos are drawn inside the figure image, so the PDF has no text there. Also every
  paragraph of a scanned PDF, which makes this change a no-op on those files.
- **`kept_short`** — below 80 characters the service's reading is kept. The PDF renders
  `ABSTRACT` letter-spaced as `A B S T R A C T`, which would break heading recognition.
- **`kept_runs_together`** — one RSC paragraph's embedded font has no space glyphs and
  reads `transferredchargeishalfoftheamountofthedonorconcentration`. Substituting that
  would be worse than the corruption this repair exists to fix. The bound is a word
  over 20 letters **that the service did not also read**, which is why
  `hydrodechlorination` (19, the longest legitimate word of 697 clips) is safe; the
  broken one is 24.

`kept_disagree` guards against an unexplained mismatch — wrong page, rotated page —
below 0.70 agreement. It is **conditional on the service's reading looking sound**,
and that condition is the point: when corruption is severe the two readings agree
almost nowhere, so agreement alone refuses the repair exactly where it is needed. The
first version of this guard did precisely that, and the test for the Elsevier
corruption caught it. design/345's signatures decide which side is suspect.

Reported as `embedded_text_replaced:N` and one warning per refusal reason. On the
Elsevier paper: `replaced 100`, `kept_short 108`, `kept_no_embedded 455`.

## What it did to the paper that started this

Three runs of the same file:

| | 342 clean service read | 345 corrupted read | **346 paper's letters** |
|---|---|---|---|
| sentences | 148 | 147 | 148 |
| corruption marks per 1000 chars | 0.067 | 27.666 | **0.066** |
| text delivered (design/344) | — | 0.0719 | **0.9563** |
| missing fragments | — | 125 | **6** |
| coverage | 0.8638 | 0.6275 | **0.8951** |
| sentences out of source order | 46.83% | 45.92% | **23.39%** |

The order result was not the goal. Sentences are anchored to the source text to check
their order, and when the sentence letters came from the service while the anchor text
came from the PDF, a quarter of the sentences could not be found at all — 98 anchored
before, 124 now. Half of the "backward" sentences were never disorder; they were two
readings of the same page failing to match.

## Not this chip

- design/344's named losses on the nine other papers
- The per-chunk text floor design/345 withdrew, which now has a sound ruler to be
  rebuilt on: with the letters from one source, source text and sentences are finally
  measured in the same alphabet
- Retrying a corrupted extraction. Less necessary now that the letters do not come
  from it, but figure-internal labels still do

## Test

`tests/test_design_346_embedded_text.py` — taking words out of a box, a neighbouring
line staying out, an empty region, the paper winning a disagreement, the Elsevier
corruption being replaced, no embedded text and short boxes keeping the service's
reading, the run-together font being refused, a genuinely long word not being mistaken
for it, severe corruption still being repaired, an unexplained mismatch still refused,
and both bounds sitting inside their measured gaps.
