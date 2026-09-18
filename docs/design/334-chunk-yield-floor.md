# 334 — A chunk that returns a fraction of its prose has failed

**Version:** 0.3.328 · Status: **locked**  
Extends [167](167-debone-quality-guards.md) · follows [333](333-coverage-denominator-correction.md)

## Why

design/167 guards a chunk that returns **zero** sentences: retry once, then split
deterministically. A chunk that returns *one* sentence out of twenty took the
success path, `ok=True`, and the rest of the section left no trace anywhere in the
quality record.

The gap is structural. Nothing in `_process_chunk_with_guard` compared what came
back against what went in, so the only visible symptom was a coverage ratio that
design/333 had just finished making trustworthy.

## Locked

1. `ChunkStat.chars_out` records the prose characters a chunk returned.
   `yield_ratio = chars_out / chars_in`.
2. `CHUNK_YIELD_MIN = 0.45`. A **substantive** chunk below it is under-yielded.
   Deboning strips citation markers and running heads, so shrinkage is expected;
   losing more than half the chunk is not.
3. Under-yield retries once. If the retry clears the floor it is kept.
4. Otherwise the deterministic splitter runs, and **its output is taken only when
   it returns more characters** than the model did. A guard must never make the
   output smaller than what it was given.
5. `low_yield` survives on the stat even when the retry succeeds, so the event is
   reported rather than erased by its own repair.
6. `chunks_low_yield` appears in `IngestQuality.to_dict()` and as
   `chunk_low_yield:<i>` in the warning list.

`references` and `sparse` chunks are exempt. A short chunk returning little is
what `sparse` means, and a bibliography returning nothing is design/263.

## Measured

The floor is not a guess about a healthy chunk; it fired on real input. On
`srep41797` chunk 6 (1,527 characters, pinned `acknowledgement`) came back under
the floor and the splitter beat it:

```
chunks_low_yield: [6]
chunks_fallback_split: [6]
```

No other chunk in the file tripped it, so the floor is not firing on ordinary
deboning shrinkage.

## What this did not explain

design/333 predicted the yield floor would account for the Sci Rep residual. It
does not. Chunk 6 is 1,527 of 45,968 characters. The real loss was ~12,000
characters deleted by an unverified `references` pin, which is
[335](335-references-pin-is-not-evidence.md). Both defects were live at once and
the coverage metric could not tell them apart.

## Not this chip

- A yield floor for `sparse` chunks
- Comparing yield against a per-section expectation rather than the chunk

## Test

`tests/test_design_334_chunk_yield.py` — ratio helpers, the retry that succeeds,
the split that is only taken when it returns more, the split that is refused when
it returns less, the healthy chunk that never retries, the exempt sparse chunk,
and the warning wiring.
