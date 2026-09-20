# 350 — Apparatus is not loss

**Version:** 0.3.346 · Status: **locked**  
Finishes the reporting side of [347](347-the-ruler-was-wrong-more-often-than-the-pipeline.md) and [349](349-the-cut-that-split-a-sentence.md)

## Why

Once design/349 removed the real losses, everything still listed as missing was
apparatus the pipeline drops on purpose. That matters more than it sounds: it is exactly
how design/344's real finding got buried. Five of the fragments it named were author
biographies, and nobody looked past them to ask whether the rest were real.

`looks_like_prose_line` accepted all of it, because a biography *is* prose.

## Locked

`is_front_or_reference_apparatus` refuses four shapes beyond the back-matter and
prose-line checks already in place. Each comes from the corpus:

| shape | fragment | signal |
|---|---|---|
| author biography | `Her research is aimed at gaining fundamental insights in …` | verb phrase required |
| author / affiliation | `Allen,† Sungwoo Lee,† … ‡Department of Materials, Oxford, OX1 3PH` | 3 daggers, or 2 with a department name |
| series citation | `367 of Astronomical Society of the Pacific Conference Series (…, 2007), p.` | series name **and** a year |
| supplementary files | `Formation of the 855 line defect (AVI) Motion of kink … (AVI)` | 2 format markers |
| figure axis labels | `( FCH4in − FCH4out ) H2 produced (µmol .min-1) CO produced (µmol .min-1)` | 2 units in parentheses |

Every bound needs **two** of its signal, because one of each occurs in ordinary prose: a
footnote dagger on a sample label, a single unit in parentheses, `since 2015`, one
supporting video. A year alone is not a citation and one dagger is not an author list.

## What the report says now

| | design/344 | design/347 | design/349 | here |
|---|---|---|---|---|
| fragments called missing | 33 | 15 | — | — |
| of those, actually present | **18** | 0 | 0 | 0 |
| reported as really absent | 5 | 11 | 8 | **the real ones only** |

On the two papers re-run after design/349, `d4cs` reports **0** real losses where it had
2, and `nl5b` and `srep` report none at all. The three genuine body sentences that
started this — one in `cata13` and two in `d4cs` — are back in the output and, being
present, are no longer reported.

## Still reported, and rightly

Two fragments of `science` survive every filter:

```
1) were obtained by using a thin-film rotating-disk electrode with well-defined oxygen 32.
Sana for discussions and the anonymous referees for their constructive criticism.
```

The first is a caption joined to a reference number by the extractor — a sign something
upstream went wrong, which is worth seeing. The second is a mid-sentence piece of an
acknowledgement; back matter is judged whole, and half of it does not match.

## Not this chip

- Sentence order, still 40% backward on five of ten papers
- Acknowledgement fragments, which need the back-matter test to work on pieces
- Re-running the remaining eight papers to confirm design/349 end to end

## Test

`tests/test_design_350_apparatus_is_not_loss.py` — eight corpus apparatus shapes refused,
six real sentences still reported including one crediting a person and one carrying a
unit, and four single-signal cases that must not be mistaken for apparatus.
