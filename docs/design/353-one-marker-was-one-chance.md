# 353 — One marker was one chance

**Version:** 0.3.349 · Status: **locked**  
Finishes [352](352-keep-the-coordinates-we-were-given.md)

## Why

design/352 located 91.6% of box markers. Reading all 31 misses gave four causes, and
three of them spoil only a box's **opening** sentence:

| cause | the marker that failed | n |
|---|---|---|
| a watermark welded to the front | `BY Cc It has been reported that linear scaling…` | 5 |
| the tail of the previous column | `to free energy and the electronic structure of…` | 3 |
| an opening longer than the returned sentence | `…we sug- gest the following: · Rationally…` | 6 |
| a box that should never have had a marker | `(57) Handbook of Binary Alloy Phase Diagrams; ASM…` | 13 |
| genuinely absent | | 2–4 |

The first three leave the box's **second and third** sentences untouched. The fourth is not
a miss at all — it is a box in the denominator that has nothing to find.

## Locked

**More than one try.** `box_openings` returns a box's first three usable sentences, tried
in order. That did the work: 19 rescues.

**Apparatus signals that work on one line.** `reference_signal_density` is a density over a
region and scores **0.00** on a single bibliography entry, so these four shapes needed their
own, each taken from the misses above:

- a numbered entry — a bare or bracketed number then a capital, with a year or `ed.`/`pp.`
- a labelled line — `Key words:`, `Funding:`, `Data availability:`; the colon is what makes
  it safe, since a results sentence says *the keywords were chosen*, never *Keywords:*
- a masthead — the journal's own address: `www.…`, `rsc.li`, `nature.com/…`
- three shouted words in a row — `SCIENTIFIC REP RTS`, `ADVANCED SCIENCE NEWS`; two is
  reachable by an acronym pair in prose, three is not

**The column break, named.** `continues_sentence` marks a box whose opening completes the
previous box's last sentence. That sentence belongs to both boxes, so neither claims it as
its boundary and the box falls through to its later openings. It fires once in ten papers,
because `join_section_text` already glues most column breaks before this stage sees them.

| | design/352 | here |
|---|---|---|
| boxes with a usable marker | 368 | 354 |
| located | 337 (**91.6%**) | 351 (**99.2%**) |
| to within 5% | 320 | 337 |
| missing | 31 | **3** |
| papers at 100% | 2 of 11 | **8 of 11** |

Lowest paper: 95.2%.

## Built, measured, and not used

A box's **closing** sentence names the same boundary from the other side, and was meant to
be the try of last resort — the only recourse when none of a box's own text came back. It
rescued **1 box of 368** before the apparatus signals landed and **0 of 354** after,
because a box that qualifies almost always matches on one of its own openings.

It is kept as a field and reported in the census, not as a branch. Shipping a mechanism
nothing has been shown to need is the habit that produced design/345's withdrawn floor.

## Two attempts that failed the same way

Both widened *who gets a marker* instead of *how many tries a marked box gets*.

Letting each sentence qualify on its own put a marker on every reference-list box, whose
entries read like prose line by line: the denominator went from 368 to **664** and the rate
read 77.1%, with `srep41797` at 36.6%. Letting a previous box's closing stand alone then
admitted apparatus boxes whose predecessor happened to end in prose: 620 and 79.8%.

The rate looked worse both times while more boxes were actually being found — 512 of 664
is more than 337 of 368. A ratio whose denominator moves is not a measurement, which is the
same trap as design/331's collapsed coverage denominator.

## Not this chip

- The 3 remaining misses: heavily reworded sentences the model did not return
- Using the coordinates in the product

## Test

`tests/test_design_353_more_than_one_try.py` — a box offering its next openings, a watermark
no longer costing it, a later opening finding a box whose first was dropped, the column
break named and its fragment refused as a boundary, the closing recorded but unused, a
reference list still getting nothing, an apparatus box not admitted by its predecessor, the
four one-line apparatus shapes, four real sentences that resemble them still marked, and the
try order putting the box's own opening first.
