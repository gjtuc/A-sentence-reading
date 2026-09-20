# 351 — Order measured in its own text

**Version:** 0.3.347 · Status: **locked**  
Corrects the instrument of [322](322-sentence-order-is-the-paper-order.md)

## Why

Five of ten papers reported 40% or more of their sentences out of source order, three
reported under 10%, and almost nothing sat in between. A ten-fold split that clean is a
cause you can find. There were two, and both were in the measure.

### The wrong text

```python
_ord = source_order_stats(text_pre_filter, sentences)
```

`text_pre_filter` is the raw page text. The sentences come from the **reading-order**
text, and the whole point of that stage is that the two orders differ: a two-column page
read naively interleaves columns, and the service puts it right. So every place the
service changed the order registered as the sentences stepping backwards.

Anchored in the text the sentences were actually made from:

| paper | reported | actual |
|---|---|---|
| d4cs | 44.46% | **0.9%** |
| srep | 41.58% | 3.7% |
| science | 41.94% | 3.2% |
| advmat | 40.13% | 1.8% |
| kjche | 43.08% | 6.1% |

This is the third time in this session that sentences were compared against a text they
did not come from — design/345's withdrawn threshold and design/347's false losses were
the same mistake wearing different clothes.

### The wrong rule

Counting a sentence as backward when it sits below the running **maximum** makes one
displaced sentence a verdict on everything after it. On `advmat` that read 24.8% while
only 1.8% of sentences stepped back from the one before: a single sentence at index 313
anchored 47,078 characters ahead, and the remaining 18 were all "backward".

Counting only a step from the previous sentence has the opposite blind spot. Swap the
halves of a paper and exactly one pair is out of place — and a swapped block is the
defect design/322 was built to catch.

## Locked

The length of the longest run already in order answers both, because one displaced
sentence costs one and a swapped half costs half:

| case | out of order |
|---|---|
| the paper's own order | 0.0% |
| one sentence displaced | 4.2% |
| a swapped half | **50.0%** |
| fully reversed | >90% |

`ORDER_BACKWARD_PCT_WARN` moves from 20% to **15%** — above the 6.1% worst of eleven
correctly-anchored runs, far below a swap. The old 20% was set against a measure that
reported 44% on a paper whose order is 99% correct, so it was never protecting anything.

## What this means for the product

Sentence order was never broken. Across ten papers, 94% to 100% of sentences are in the
paper's own order, and what remains is a handful of individually displaced sentences
rather than a shuffle. The `sentence_order_backward` warning was firing on live papers
that read correctly.

## Not this chip

- The individual displaced sentences (1 to 6 per paper) — small, and each needs its own look
- Anchoring by first match: `_anchor_pos` takes the first occurrence of its 6-gram, so a
  repeated phrase can anchor early. It did not matter at this scale, but it is a known
  soft spot

## Test

`tests/test_design_351_order_measured_in_its_own_text.py` — the paper's own order clean,
a swapped half still caught and still warning, one displaced sentence not called a
scramble, two costing two, a reversed paper above 90%, anchoring in a differently-ordered
text reproducing the original fault, the threshold between measurement and a swap, and the
two guarantees design/322 already had.
