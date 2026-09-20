# 345 — Characters the paper never printed

**Version:** 0.3.341 · Status: **locked**  
Follows [344](344-measure-lost-text-not-lost-words.md) · records a withdrawn change

## Why

Tracing design/344's named losses turned up something worse than loss. One run of
`1-s2.0-S1385894724017960` produced sentences reading:

```
Pr?<sub>h</sub>t?<sub>h</sub>nic and electr?<sub>h</sub>nic h?<sub>h</sub>le c?<sub>h</sub>nductivity
```

Every `o` replaced by a two-character sequence, **1,483 times**, and those sentences
were what the reader would have said aloud. The next run of the **same PDF** was
clean. An earlier run of `d4cs00527a` did the same with `y` → `γ`
(`Catalγsis`, `Honeγwell`, `Maγnes`) **440 times**, and its next run was clean too.

The PDF's own embedded text was correct in every case — `catalyst` appears 138 times
cleanly in `d4cs00527a` — and that extraction is deterministic. So this is the
**extractor varying between calls**, not the paper. When the Azure reading-order path
is on, the sentence text is Azure's reading of the page, not the PDF's embedded text,
and Azure's reading of a particular font is not stable.

## Locked

`glyph_corruption_marks` counts signatures that cannot occur in real prose:

| signature | example |
|---|---|
| a Greek letter inside a Latin word | `Catalγsis` |
| a digit standing where a letter belongs | `phen0men0n` |
| a one-letter subscript with the word continuing | `Pr?<sub>h</sub>t?<sub>h</sub>nic` |

The third needed care. `e<sub>g</sub> filling`, `t<sub>ion</sub>`, `H<sub>2</sub>O`
and `K<sub>obs</sub>` are how papers print labels, so the signature is a **single
lowercase** subscript **followed immediately by a letter** — a real subscript is
followed by a space or punctuation. The first attempt also required a letter *before*
the subscript, and missed all 1,483 Elsevier cases because the character before it was
the corrupt one.

The digit rule wants three letters before and two after, which keeps `co2`, `h2o`,
`sp3d` and `mp3` out. It is deliberately conservative: `n0rmalized` scores nothing
because only one letter precedes the digit.

`CORRUPTION_PER_1K_WARN = 0.75`, the geometric middle of the measured gap. All twelve
runs classify correctly:

| run | marks per 1000 chars | |
|---|---|---|
| `cej` corrupted | **27.67** | flagged |
| `d4cs` corrupted | **2.87** | flagged |
| ten clean runs | 0.000 – 0.201 | quiet |

Reported as `glyph_corruption_per_1k` and a `glyph_corruption:<value>` warning.

## Detection only, and why that is the right stopping point

This chip **does not repair** the text. Two repairs are possible and both need their
own design:

1. **Retry the extraction.** The corruption is non-deterministic and a second call was
   clean both times we observed. Cheap, but it belongs in `recover_pdf_text` with its
   own budget and evidence.
2. **Repair against the embedded text.** Strip the corrupt sequence to a skeleton
   (`Pr_t_nic`) and find the embedded-text word that fits (`Protonic`). This is the
   real answer and it is a real algorithm.

A paper scoring 27 marks per 1000 characters is unusable, and until one of those
lands, saying so is worth more than silence.

## A change made and withdrawn

Between design/344 and this chip I built a per-chunk text floor: judge each chunk by
the share of its prose that came back, rather than by design/334's character ratio.
The motivation was sound — on `1-s2.0-S1385894724017960`, chunk 4 (`experimental`)
delivered **0.594** of its text, dropped six Methods sentences, and reported
`chunks_ok 17/17`, `chunks_low_yield []`, because 0.594 passes a 0.45 floor.

The threshold was not sound. It came from comparing each trace's **stored sentences**
against a **fresh extraction** of the same PDF — two different reads of a
non-deterministic extractor. That comparison measures how much the extractor varies,
not how much the pipeline lost, which is exactly what this chip then found.

Shipped live, the floor split 8 of 17 chunks on that paper and pushed its
`coverage_ratio` from 0.864 to 0.628. Withdrawn.

`ChunkStat.text_coverage` now **reports** per-chunk delivery without gating on it.
A gate needs an in-run measurement: the source text and the sentences from the same
extraction, stored together. That is the next chip.

## Not this chip

- Repairing or retrying corrupted extraction
- The per-chunk text floor, until its threshold can be measured in-run
- design/344's named losses on the other nine papers

## Test

`tests/test_design_345_glyph_corruption.py` — both corrupted shapes from real runs,
a digit standing for a letter, clean prose scoring nothing, four real subscript forms
that must not be mistaken for corruption, a Greek letter as its own word, chemical
tokens with digits, a text too short to score, the threshold inside the measured gap,
and the warning wiring both ways.
