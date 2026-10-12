# 399 — a footer stamp inside a long line no longer wipes the page

## What was wrong

The source-side coverage check (design/321/330) measures the sentences against
the PyMuPDF text taken before extraction filters anything. Its denominator is
`practice_text_only`, which removes per-page chrome with `_CHROME_LINE`, a
whole-line regex (design/333).

PyMuPDF returns a page as a few lines of 1,000+ characters. A footer stamp such
as `wileyonlinelibrary.com` or `© 2016 WILEY-VCH` sits inside one of them, so the
whole line went:

- Adv Mater 2016 Pt–Co: 40,494 characters in 31 lines, all 16 long ones carrying
  a stamp. 30 characters survived, the denominator was 0 tokens, and the check
  reported only `coverage_denom_too_small:0`.
- Over 225 PDFs on the desktop: 1,345 of 1,534 matching lines were longer than
  1,000 characters. 68 papers kept less than half their text.

The check was blind on those papers, and this was not cosmetic. An ACS paper
(Ni–Cu/SiO2 catalysts) in the local cache (`266da01aa105`, 120 sentences) is missing its whole
Experimental section and the last paragraph of its Introduction, and carried no
warning at all. Its old denominator was 3,273 of 29,418 characters.

The debone-side check was not affected: Azure's text keeps short lines (Pt–Co
read 0.85 / 0.91 there).

## Rules

1. `_strip_chrome`: a matching line of at most `CHROME_LINE_MAX = 300` characters
   still goes whole. 20 of the 1,534 matching lines were that short. A longer line
   loses only the sentence that carries the stamp.
2. `drop_caption_text`: on the source side only, pieces whose 5-word shingles are
   at least half inside the paper's own figure captions leave the text. PyMuPDF
   prints captions inline, and the reader gets them in the figure viewer. A body
   sentence that mentions a figure stays.
3. `source_coverage_warnings(source_text_coverage=...)`: the text ruler
   (design/344) now also runs on the source copy, held to its own 0.80 line.
   It emits `source_text_coverage_low:X`. The word-set ratio stays as it was.

The split handoff reports `caption_chars_dropped`, `source_text_coverage` and
`source_text_missing_n` next to `practice_chars`.

## Measured

Six stored sessions with their source PDFs:

| paper | old chars / tokens | new chars / tokens | word ratio | text ruler | warning |
|---|---|---|---|---|---|
| Pt–Co main | 30 / 0 | 23,138 / 809 | 0.91 | 0.88 | none |
| `36c7a33ec665` | 3,438 / 209 | 33,548 / 1,261 | 0.93 | 0.96 | none |
| `266da01aa105` (Experimental missing) | 3,273 / 165 | 24,000 / 754 | 0.70 | 0.70 | `source_text_coverage_low:0.70` |
| `ff469288b3b0` | 5,896 / 306 | 28,799 / 966 | 0.56 | 0.60 | `source_coverage_warn`, `source_text_coverage_low` |
| `f4ea54509584` | 5,896 / 306 | 28,799 / 966 | 0.50 | 0.49 | `source_coverage_low`, `source_text_coverage_low` |
| `f7e3358fe353` | 202 / 23 | 201 / 23 | — | — | `coverage_denom_too_small:23` |

The word-set ratio alone would have passed `266da01aa105` at 0.70 (warn line
0.65). Most of the 11 pieces still "missing" on Pt–Co are present: PyMuPDF prints
`Pt 75 Co 25` and `efﬁ cient`, the sentences hold `Pt<sub>75</sub>Co<sub>25</sub>`
and `efficient`. The rest are author affiliations and table or panel captions.
The 5 left on `36c7a33ec665` are all present too (equations and the author line
break the shingles).

Over the 225 desktop PDFs, the share of the bibliography-cut text left after
`practice_text_only` is now at least 0.646 (median 0.978). No paper is below half.

## Scope

The warnings are evidence only. The phone's quality banner is off, and its
prefixes do not include `source_`. This change does not recover the missing
Experimental section of `266da01aa105`; it makes that loss visible.

## Tests

`tests/test_design_399_chrome_inside_long_lines.py`
