# 339 — Fixing what the speech linter found

**Version:** 0.3.334 · Status: **locked**  
Extends [326](326-practice-speech-tokens.md) · [328](328-variable-exponent-and-spelled-run.md)

## Why

`agent-tools/speak_lint.py` flags spoken output carrying the signature of a known
failure mode, so the review scales past hand-checking. Run over the 2,366 sentences
of the ten-paper corpus it reported **224 defective sentences (9.5%)** — and the
number had not moved since the linter was written, because nothing it found had been
fixed.

The families it names are symptoms. Grouped by cause they were five bugs, and the
worst ones made the sentence say something untrue:

| printed | spoken before |
|---|---|
| `Fig. S1` | "figure **sulfur** 1" |
| `<i>K</i><sub>obs</sub>` | "**potassium** o b s" |
| `where <i>C</i> is` | "where **carbon** is" |
| `t<sub>ion</sub>` | "t i o n" |
| `&gt;` | ">" |
| `Figs. 4` | "figs 4" |
| `0.4 mM` | "0.4 m M" |
| `O<sub>3-δ</sub>` | "oxygen 3- delta" |

## Locked

1. **A subscript that is a word is read as a word.** `_speak_numberish` spelled any
   1–4 letter subscript, so `obs` became "o b s". A `_SUBSCRIPT_WORD` lexicon names
   the common abbreviations (`obs` → "observed", `max` → "maximum", …), and any other
   all-lowercase run of 2+ letters containing a vowel is spoken as itself.
   Single letters and consonant-only runs still spell, so design/326's orbital
   labels (`e g`, `t two g`, `d g b`) are untouched.
2. **Italics mark a variable.** The HTML parser tracked `sub`/`sup` but discarded
   `<i>`, so an italic single letter reached the element pass and was renamed. The
   parser now marks it, and the mark joins `freeze`'s existing placeholder mapping
   rather than inventing a second one. Italic depth is a separate counter from the
   sub/sup stack, so an italic inside a subscript does not change how the subscript
   reads.
3. **A supplementary label is not sulfur.** `Fig. S1` is marked by label word. Then,
   because `Figs. S1 to S7` only puts a label word in front of the first one, a bare
   `S<n>` token in a sentence that already carries a supplementary label or the words
   "supplementary"/"supporting information" is marked too. Without that context
   `S8` and `SO2` stay sulfur.
4. **Dotted abbreviations are expanded before `freeze`.** `Figs.` was in the lexicon
   and still reached TTS as the fruit, because `freeze` takes `Figs` for a proper
   noun before `_expand_acronyms` runs. `Figs.` → "figures", `Eqs.` → "equations".
5. **A lone capital is not an element.** Needed for idempotence: an italic variable
   resolves to `K observed`, and a second pass turned that into "potassium
   observed". In a formula a symbol is glued to digits or other symbols, so a single
   capital standing as its own word is a variable or a label.
   Measured: **0 of 2,366** corpus sentences change under this rule, so it costs
   nothing on real input and only bites re-processed text.
   The exception is composition wording — `N-doped`, `O-rich`, `S-containing` — which
   has to be named explicitly, because the dash pass has already turned the hyphen
   into a space by the time the element pass runs. `test_n_doped` caught that; the
   corpus did not.
6. **`>` and `<` are comparisons.** `&gt;` unescapes to a glyph and all markup is
   already parsed away at that point.
7. **A prose slash is two words.** Only between two all-lowercase words, and never
   in a sentence containing a URL, because mangling a link would hide rather than fix
   the real problem (see below).
8. **Molar and time units.** `mM`/`µM`/`nM`/`pM`, `ppm`, `ppb`, and `sec`.
9. **A Greek letter belongs in a subscript.** The fallback required ASCII, so
   `O<sub>3-δ</sub>` fell through untouched. Now "oxygen three minus delta".

## Measured

| check | before | after |
|---|---|---|
| `lowercase_letter_run` | 42 | **5** |
| `leftover_markup` | 13 | **0** |
| `leftover_slash` | 110 | **41** |
| `element_then_digit` | 25 | **11** |
| `composed_name` | 22 | **7** |
| `mixed_case_token` | 16 | **10** |
| `bare_unit_abbr` | 17 | 18 |
| `url` | 6 | 6 |
| **sentences flagged** | **224** | **83** |

## What the remaining 83 are

Not all of them are speech bugs, and saying so matters more than the number:

- **~10 are back matter that should never have become practice sentences** — the
  `url` family plus the licence, DOI and "Supplementary information accompanies this
  paper" lines. Teaching TTS to read a Creative Commons URL aloud is the wrong
  repair; the sentence should not exist. That is extraction work.
- **18 `bare_unit_abbr` are unit composition**, e.g. `m²·g⁻¹` reaching TTS as
  "m times per gram" instead of "square meters per gram". `·` is mapped to " times "
  globally, which is wrong inside a unit product. This needs the unit grammar, not
  another entry in a table.
- **7 `composed_name`** are the compositional namer's gaps — `AlO(OH)`,
  `Pt1/CoFe2O4`. design/326 Phase 2 (the per-paper term dictionary) is where those
  belong.
- **5 `lowercase_letter_run`** are largely the linter's own false positives: `d g b`
  is a correctly spelled consonant-only subscript.

## Not this chip

- Back matter becoming practice sentences
- Unit-product grammar (`·` inside a unit vs. as a multiplication)
- design/326 Phase 2 per-paper term dictionary
- XPS orbital labels (`2p3/2` → "two p three halves")

## Test

`tests/test_design_339_speech_defects.py` — each locked rule with the printed form
that used to break it, the orbital labels and consonant-only subscripts that must
keep spelling, sulfur that is still sulfur without a supplementary context, a URL
left intact rather than mangled, the known-good forms from earlier chips, and
idempotence over the three shapes that broke it.
