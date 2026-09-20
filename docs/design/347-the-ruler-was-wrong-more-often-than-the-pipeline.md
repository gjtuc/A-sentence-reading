# 347 — The ruler was wrong more often than the pipeline

**Version:** 0.3.343 · Status: **locked**  
Corrects [344](344-measure-lost-text-not-lost-words.md) · retires the premise of [345](345-characters-the-paper-never-printed.md)'s withdrawn floor

## Why

design/344 reported that ten papers each lost 3 to 24 real sentences. design/345 built
a per-chunk floor on that reading, shipped it, and withdrew it when the threshold
proved to come from a cross-run comparison. The premise itself was never opened.

Opening one case by hand ended the story:

```
source  ... covered with BZY10−1 wt% BaCO3 sacrifi- cial powder for sintering.
output  ... covered with BaZr<sub>0.9</sub>Y<sub>0.1</sub>O<sub>3-δ</sub>−1 wt% ...
```

The sentence was there. The model had expanded the abbreviation into the full formula
— which is exactly what the system prompt asks for:

> Prefer glossary rich forms from PAPER CONTEXT when the same raw token appears

Five-word shingles cannot survive our own instruction. Every window around the
rewritten token changes, and the ruler declares the sentence gone.

A load test had already pointed this way, and its real finding was missed at first. The
failing chunk was run twelve times across four conditions — the live prompt and a
slimmed one carrying no typography rules, whole chunk and split in halves — to test
whether `gemini-2.5-flash` was being asked for too much at once. It returned **exactly
22 sentences in all twelve runs**, while the ruler's score moved between 0.730 and
1.000. A constant count under a moving score is a ruler problem. Capacity was not the
cause, and neither was instruction load.

## Locked

Before a fragment is called missing, one more look: does any returned sentence share
**70% of its words**? Word overlap ignores order, so it survives a rewritten token,
while 70% of a sentence's vocabulary is far more than a shared topic.

Author biographies are excluded from the report. They are prose, so
`looks_like_prose_line` accepted them, and all five fragments the first pass called
absent in the RSC review were of this kind — `Denis Leybo received his PhD from the
National University of Science and Technology MISIS`. Dropping them is correct;
reporting them as loss buried the real finding. The verb phrase is required, so a
results sentence that merely credits someone (`the same trend was reported by Kreuer
and co-workers`) still counts.

Across the stored traces:

| | shingles alone | with both fixes |
|---|---|---|
| fragments called missing | 33 | **15** |
| of those, actually present | **18** (55%) | **0** |
| partial delivery | 10 | 13 |
| really absent | 5 | **2** |

`srep41797` goes from 2 to **0**. `ChemistryOpen` keeps 4, all partial. The RSC review
keeps 2 real losses out of **805 sentences** — and those two are ordinary body prose,
so they are worth chasing.

## What this retires

The sentence loss design/344 announced was mostly the ruler. Which means:

- **The chunk floor has no case.** design/345 withdrew it for a bad threshold; it is
  now clear the condition it was gating on barely occurs. The 0.594 delivery that
  motivated it was the same measurement error: that chunk returns 22 sentences every
  time, and its score varies with typography.
- **"The model does not return sentences" was wrong** as a general claim. On the one
  chunk examined closely across twelve runs, it returned everything every time.
- **design/346 stands unaffected.** Glyph corruption was measured on the sentences
  themselves, not through this ruler, and 1,483 wrong characters in one run is not a
  matching artefact.

## Also found, not fixed

`600 °C` came back as `600 &amp;deg;C` — an HTML entity in sentence text, which the
reader will hear read out. Separate from this chip and worth its own.

The `PAPER CONTEXT` block is **9,189 characters** against a 3,214-character chunk, so
74% of each request is context. The twelve runs show it costs nothing in completeness,
but it is worth trimming for latency and price.

## Not this chip

- The 2 real losses in the RSC review
- The `&deg;` entity leak
- Trimming the context block

## Test

`tests/test_design_347_ruler_cries_wolf.py` — an expanded abbreviation and restored
typography no longer counted as loss, a genuinely absent sentence still named, a
paraphrase sharing few words still counted as loss, the overlap bar inside a range that
means something, four real biography shapes excluded, and a results sentence that names
a person kept.
