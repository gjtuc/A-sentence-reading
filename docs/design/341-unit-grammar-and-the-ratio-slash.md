# 341 — A unit run is grammar, and a slash between symbols is a ratio

**Version:** 0.3.336 · Status: **locked** · speak_norm **v9**  
Continues [339](339-speech-defects-from-the-linter.md) · same defect class as [328](328-variable-exponent-and-spelled-run.md)

## Why

design/339 took the corpus from 224 defective sentences to 83. The two largest
remaining families each had a single cause, and the unit one was not a matter of
naturalness — it changed the meaning:

```
259.1 m²·g⁻¹   ->   "259.1 m times per gram"
```

The `2` is **deleted** by design/216's citation stripper. That is exactly the class
design/328 fixed for orbital exponents (`t2g⁵`) and never extended to units, so a
positive exponent on a unit vanished while a negative one survived — the minus sign
stopped the citation rule from matching. An area per mass was being read out as a
length per mass.

Second, `·` was mapped to " times " by the global symbol table. Inside a unit product
it separates units, it does not multiply them.

## Locked

1. **Units are read as a run, on the printed form.** `_expand_unit_runs` matches a
   number followed by unit tokens joined by `·`, `⋅` or `/`, each with an optional
   `<sup>n</sup>` or unicode exponent, and reads it as grammar: `2` → "square",
   `3` → "cubic", a negative exponent or a `/` → "per". Positives first, then the
   per-terms.
   Doing this before the citation stripper also removes the deletion at its source.
2. **`_UNIT_EXP` protects a leftover positive unit exponent** the same way
   design/328 protects an orbital one, for runs the grammar does not parse.
3. **The token list is deliberately narrow.** A bare `C`, `F` or `N` after a number
   is as likely to be an element, Celsius or a sample name as a unit, so they are
   absent.
4. **`s` is not a plain unit token.** `O 1s` is an orbital, and "1 seconds" would be
   wrong. It is still read as seconds inside a run, where a separator or an exponent
   proves it.
5. **Two lookarounds earned by regressions**, both caught by the existing suite
   rather than by the corpus:
   - `>` before the number and `<` after the run, because `<sub>2g</sub>` was being
     read as "2 grams" once `g` joined the plain tokens — design/328's own test case.
   - no match when a plain-text inverse follows (`800 cm-1`), because that belongs to
     the older unit table which already says "per centimeter"; taking `cm` here
     stranded the `-1`.
6. **A slash between symbols or numbers is "over".** The 38 remaining slash hits
   were dominated by one phrase, `STY CH4/STY CO2`, spoken with the slash intact
   seven times in one paper. Between two lowercase words it stays a pause
   (design/339), and a URL is still left alone: breaking it up would hide that it
   should not be practice text (design/340).
7. **`Downloaded on` joins the back-matter patterns** — an RSC page stamp,
   `Downloaded on 5/28/2026 1:22:30 AM.`

## Measured

| check | design/339 end | now |
|---|---|---|
| `leftover_slash` | 38 | **4** |
| `bare_unit_abbr` | 16 | **8** |
| **sentences flagged** | **78** | **45** |

Across both chips: **224 → 45** of 2,361 sentences.

## What the remaining 45 are

- 11 `element_then_digit` and 7 `composed_name` — the compositional namer, i.e.
  design/326 Phase 2 (the per-paper term dictionary). `AlO(OH)`, `Pt1/CoFe2O4`.
- 9 `mixed_case_token` — mostly `BrO3⁻`, which wants "bromate" rather than
  "B R O 3 to the minus": a lexicon entry, not a rule.
- 8 `bare_unit_abbr` — composite units outside the token list.
- 7 `lowercase_letter_run` — largely the linter's own false positives (`d g b` is a
  correctly spelled consonant-only subscript).
- 4 `url` — back matter in papers not yet re-traced with design/340.
- 4 `leftover_slash` — instrument model names (`D/MAX 2004`) and an XPS label
  (`2p3/2`, now "2p3 over 2"; a reader says "two p three halves").

## Not this chip

- `2p3/2` as "three halves"
- A compound-name lexicon for anions like `BrO3⁻`
- design/326 Phase 2 per-paper term dictionary

## Test

`tests/test_design_341_unit_grammar.py` — the exponent that used to be deleted,
cubic and three-part runs, a slash inside a run as "per", unicode superscripts, the
plain abbreviations that were left to TTS, everything that already worked, the
orbital subscript that must not be grams and the orbital that must not be seconds, a
plain number that is not a unit, the ratio slash, the prose slash, a URL keeping its
slashes, the RSC page stamp as back matter, and idempotence.
