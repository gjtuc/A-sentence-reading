# 349 — The cut that split a sentence

**Version:** 0.3.345 · Status: **locked**  
Closes what [347](347-the-ruler-was-wrong-more-often-than-the-pipeline.md) left

## Why

design/347 cleared the ruler of 18 false alarms and left a handful of genuine losses
across ten papers and 2,356 sentences. Placing each one in its chunk answered the
question immediately — they sat at the **end**:

| paper | chunk | position in chunk |
|---|---|---|
| cata13 | 7 | 99% |
| d4cs | 1 | 94% |
| d4cs | 5 | 98% |
| d4cs | 12 | 88%, 96% |
| d4cs | 13 | 97% |
| d4cs | 17 | 99% |
| d4cs | 22 | 96% |
| d4cs | 24 | 99% |
| d4cs | 26 | 97% |

And one pair sat on **both sides of the same cut**: chunk 24 at 99%, chunk 25 at 2%.

`chunk_raw_text` had two paths and only one of them looked where it was cutting.

```python
# plain text — looked for a boundary
br = max(window.rfind("\n\n"), window.rfind(". "), window.rfind("? "))
if br > size // 3:
    end = start + br + ...

# section-pinned — cut at exactly `size`
end = min(start + size, len(body))
piece = body[start:end].strip()
```

The reading-order service always marks sections, so **the pinned path is the one live
takes**. A sentence straddling the cut arrived as a fragment at the end of one chunk and
another fragment at the start of the next — and the system prompt says to drop
*incomplete fragments that are only initials or truncated*. Both halves went, exactly as
instructed.

Measured over the nine papers with a stored source:

| | cuts inside a section | of those, ending mid-sentence |
|---|---|---|
| before | 76 | **75** |
| after | 78 | **0** |

75 of 76. The one exception was a chunk whose window held no sentence end past a third
of its length.

## Locked

One `_split_keeping_sentences` for both paths, so there is no second implementation to
drift. It prefers a paragraph break, then `. ` `.\n` `? ` `! `, and only past a third of
the window — cutting at the first period would make chunks tiny and multiply the model
calls. With no boundary at all, as in a table dump, it falls back to a hard cut rather
than returning one giant chunk.

The two extra chunks (76 → 78) are the cost: a cut moved earlier leaves a little more
for the next piece.

## What this also explains

The 23 fragments reported as **partial delivery** are the same shape — half a sentence
arriving is what a split sentence looks like from the ruler's side. Those should mostly
resolve with this, which is the check to run next.

## Not this chip

- Re-measuring the ten papers to confirm the losses are gone end to end
- Sentence order, still 40% backward on five of ten papers
- The missing-report filter, which still lists author lists, affiliations, reference
  entries and figure axis labels as if body prose had been lost

## Test

`tests/test_design_349_cut_between_sentences.py` — a cut landing after a sentence end,
no sentence split across two pieces, the pinned path cutting the same way, every pinned
chunk keeping its mark, nothing dropped, a paragraph break preferred, text with no break
still cut, a short body left alone, and a break too early in the window not taken.
