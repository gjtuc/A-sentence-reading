# 333 — The recall denominator, corrected

**Version:** 0.3.327 · Status: **locked**  
Amends [331](331-azure-references-in-denominator.md) · [330](330-coverage-denominator.md) · [321](321-extraction-boundary-census.md)

## Why

Chasing the residual Sci Rep loss found three faults in the **metric**, one of
them introduced by design/331 the same day.

### A. design/331's token subtraction is withdrawn

design/331 removed Azure's bibliography from the denominator by **token set**.
A reference title carries the paper's own topic words, so subtracting those tokens
strips the body vocabulary with them. On `srep41797`, whose bibliography is 23,090
of 50,975 characters, the denominator collapsed from about 600 tokens to **40**,
and the reported 0.643 was computed over a handful of words.

The bibliography is removed by cutting the **text** (design/330). `references_text`
is kept for reporting only.

### B. Back matter and per-page chrome stayed in the denominator

The Sci Rep footer — `SCIENTIFIC REPORTS | 7:41797 | DOI: 10.1038/... www.nature.com`
— repeats once per page, so `nature`, `com`, `www`, `doi`, `1038` each appeared 12
times and counted as lost body. The Creative Commons block,
`How to cite this article`, `Publisher's note`, `Author Contributions` and the
affiliation lines did the same.

`strip_back_matter` removes chrome lines, then cuts at a back-matter heading —
but **only in the last third** of the text. A file holding more than one article
carries another paper's `Supporting Online Material` near the top; cutting there
removed the target paper and drove the Science excerpt's denominator to **9
tokens**.

### C. Citations fused onto words could never match

Extraction glues a citation superscript to the preceding word
(`coagulation16`, `study34`). `_token_set` now also emits the bare word, on both
sides of the comparison, so the real word matches.

## Locked

1. No token subtraction. `practice_token_n(raw, references_text)` ignores its
   second argument and exists for reporting.
2. `strip_back_matter` drops chrome lines unconditionally and cuts a back-matter
   heading only past 66% of the text.
3. `COVERAGE_MIN_DENOM_TOKENS = 120`. Below that,
   `source_coverage_warnings` returns `coverage_denom_too_small:<n>` and no
   ratio-based warning. A ratio over nine tokens is not a measurement.
4. A fused citation token also yields its bare word when the word is 5+ letters.

## Denominators after the correction

| paper | before | after |
|---|---|---|
| Science excerpt | 9 tokens | **267** |
| Sci Rep | 40 tokens | **629** |
| ChemistryOpen | 128 tokens | 129 |

## What Sci Rep's loss actually is

With the denominator sound, `srep41797` sits at **0.51**, and of 310 missing
tokens **306 are present in `marked_text`**. Extraction kept them; the sentence
stage dropped them. The missing words are ordinary prose — `equilibrium`,
`ozonation`, `through`, `quality`, `absorption` — not chrome.

That makes it the same class as the ChemistryOpen case in design/325: a chunk
returning a fraction of its sentences still reports `ok`, because design/167 only
catches a chunk returning **zero**. 112 sentences came out of a Results section of
15,217 characters with every chunk green. The per-chunk yield floor is the next
chip.

## Not this chip

- The per-chunk yield floor itself
- Numbered reference lists that `cut_bibliography_for_sentences` does not cut
  (Sci Rep's `1. Haag, W. R. & Hoigne, J. ...` still sits in the denominator)

## Test

`tests/test_design_321_extraction_census.py` —
`test_design_333_reference_tokens_are_not_subtracted`,
`test_design_333_a_tiny_denominator_is_not_reported_as_a_ratio`,
`test_design_333_back_matter_and_page_chrome_leave_the_denominator`,
`test_design_333_back_matter_cut_ignores_an_early_heading`
