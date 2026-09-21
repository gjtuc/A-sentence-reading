# 352 — Keep the coordinates we were given

**Version:** 0.3.348 · Status: **locked**  
Removes the guesswork [351](351-order-measured-in-its-own-text.md) had to live with

## Why

The layout service returns each paragraph as a box with a page and a rectangle, and
`order_boxes` uses those coordinates to put the paper in reading order. Then the text is
concatenated and **the coordinates are thrown away**. So when something downstream needs a
sentence's position, it searches the whole paper for six of the sentence's words.

design/351 showed what that costs. One sentence of `advmat` anchored 47,078 characters
from its neighbours in a passage that merely reads alike; two sentences of the same paper
are adjacent in the source, 11 characters apart, yet scored as an inversion because the
search picked its six words from different offsets within each. The check was guessing at
something the pipeline had already been told.

Nothing needs to be recovered by search. Each box's **first sentence** is kept before the
text goes anywhere, along with the box it came from. In the returned sentences that marker
is looked for among one chunk's twenty-odd sentences instead of in sixty thousand
characters, and everything from one marker to just before the next belongs to that box.

## Locked

`BoxMark` carries a box's offset in the joined text with its page and rectangle. The
offsets are accumulated **as `marked_text` is assembled**, so they cannot drift from the
string they describe. `place_sentences_in_boxes` puts them on `Sentence.start_char` — a
field that already existed and was never filled — and `source_order_stats` uses them when
they are there, reporting `anchored_by: box`.

Measured through the module over ten papers and 1,405 boxes: 368 carry a usable marker and
**337 are located again (91.6%)**, 320 of those to within 5%, every paper between 87% and
100%.

A marker that is not found is not a wrong answer. Its sentences fall to the previous box,
which is its neighbour in reading order, so the position loses precision rather than
correctness — about one paragraph, against the 47,000 characters the search could miss by.

## Four things had to be right

**Sentence ends hidden by citations.** Journals set the citation against the full stop:
`catalysis.[3] Because`, `temperature.175 The`, `recognized.50,51 The`. Splitting on "full
stop then space" glued two or three sentences into one marker, which no single returned
sentence could match. This alone was most of the shortfall — `Advanced Materials` went
from 51.5% to 93.9% and the corpus from 63.3% to 91.0%.

**Abbreviations that are not sentence ends.** `Fig. 3b shows`, `ca. 500 K`, `S. R. Bare`.
Splitting there leaves a marker of one or two words, which is discarded as too short and
costs that box its marker.

**Letters, not words.** A line-break hyphen makes `depen- dence` three tokens against one,
and a misread glyph makes `jM` a different word from `φM`, while in letters each differs by
one in a hundred and fifty. Two real sentences of a paper practically never differ by a
letter or two, so letters can be held to a high bar.

**Apparatus kept out of the search, and the earliest match preferred.** These are one
fault seen twice. The search walks forward so that a phrase repeated later cannot pull a
box backwards — but a marginal match *ahead* moves the cursor and starves every box behind
it. On `srep41797` a masthead box scraped past the floor at 0.72 against sentence 166 of
192, moved the cursor from 45 to 167, and the seventeen real boxes after it found nothing:
90% of markers down to 28%. An apparatus box has nothing to find among practice sentences,
so letting it search at all was the error. Together these took the corpus from 67.4% to
91.6%, `srep41797` from 28.1% to 90.0% and `cs5b00357` from 44.7% to 97.1%.

## What it opens

Each sentence now knows its page and rectangle. That is what a reader would want next:
the figure nearest the sentence being read, the sentence's place on a page image, and an
exact answer to which box produced no sentences at all.

## Honest limit

This **verifies** order rather than discovering it. The order the markers give is the
order the coordinates already imposed, and between chunks the order is right by
construction — `chunk_raw_text` cuts in order and `_collect_from_results` concatenates in
order. The gain is that the check no longer guesses, plus the position itself.

It costs **no extra model calls and no extra service calls** — only a few hundred string
comparisons on text already in hand.

## Not this chip

- Using the position for anything in the product yet
- The remaining 8% of markers: mostly more citation shapes and hyphenated line breaks
- Cutting chunks at box edges rather than at sentence ends

## Test

`tests/test_design_352_box_marks.py` — citation-hidden sentence ends of three journals,
abbreviations kept whole, letter-level matching surviving a hyphen and a misread glyph,
markers sought in order so a late repeat cannot pull a box back, sentences before the first
marker left unassigned, the census reporting what happened, an absent marker costing only
precision, apparatus boxes getting no marker, and a marginal match far ahead no longer
starving the boxes behind it.
