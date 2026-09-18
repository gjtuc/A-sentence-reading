# 326 — Practice speech: one token, one decision

**Version:** 0.3.320 · `speak_norm` **v7** · Status: **locked**  
Amends [205](205-tts-speak-policy.md) · [217](217-tts-dash-units.md) · [216](216-cite-display-tts-practice-consistency.md) · [90](90-tts-unit-lexicon.md)

## Why

Practice mode exists so a person can read a paper **aloud**. The target voice is
a researcher reading their own paper to colleagues. `spoken_text_for_tts` was one
line of about twenty regex passes, so a later pass could re-chew what an earlier
one produced and the same kind of token got different treatment depending on
which pass reached it first.

Measured against a hand-built ground truth of 20 real sentences
(`agent-tools/expected/speak.expected.json`), **2 of 20 were right**.

| printed | a speaker says | v6 said |
|---|---|---|
| CNTs | C N Ts | **carbon nitrogen Ts** |
| CVDs | C V Ds | **carbon vanadium Ds** |
| SACs | S A Cs | **sulfur ACs** |
| NPs | N Ps | **nitrogen Ps** |
| B-site | B site | **boron site** |
| NiO | nickel oxide | **nickel oxygen** |
| Fe2O3 | iron oxide | **iron two oxygen three** |
| IrO2 | iridium oxide | **iridium oxygen 2** |
| HNO3 | nitric acid | **hydrogen nitrogen oxygen 3** |
| Ni(NO3)2 | nickel nitrate | **nickel nitrogen oxygen 3 2** |
| MgAl2O4 | magnesium aluminate | **magnesium Al2 oxygen four** |
| Pt/C | platinum on carbon | platinum **/** carbon |
| H2/CO | hydrogen to carbon monoxide | hydrogen **/** carbon monoxide |
| ...(TPR) | ..., T P R | **deleted**, then read as letters later |

One trailing `s` was enough to defeat the acronym guard and hand C and N to the
element expander. In this user's field CNT, SAC and NP are the most frequent
terms in the paper.

## Locked product rules

1. **Never say something chemically false.** If the name is not known, spell the
   symbols. Never compose a name from parts.
2. **Prefer what a speaker says**, which is usually shorter than the expansion.
3. **An acronym is atomic**, plural `s` included, and is never split into
   element symbols.
4. **Voice the definition and the abbreviation.** `full_name_abbrev` changes from
   `prefer_one` to **`say_both`**: v6 deleted the abbreviation at its definition
   and then read bare letters in later sentences, so the listener never heard the
   term defined.
5. **Drop only what the mouth skips** — citation markers, footnote daggers.
6. **Units and ranges as spoken**: `0.1 molar`, `5 minutes`, `1 hour`,
   `700 degrees Celsius`, `923 to 1073 kelvin`. A dash between two numbers that
   share a unit is a range; a bare negative keeps its minus.
7. **A slash by meaning**: metal on support is `on` (`Pt/C`), two chemicals is
   `to` (`H2/CO`), unit over unit stays `per` (`Wh/L`, design/90).
8. **Punctuation a speaker can follow**: sentence-opening capital kept, no space
   before a comma, no hyphen left where a formula joined an acronym.
9. **Never harder to say than the printed form.**
10. **Never change a value.** `t2g5 eg~1.2` keeps the 5 and the 1.2.

## Structure

`llm/speak_tokens.py` runs **first** and decides the spans it is sure about,
replacing them with placeholders the later passes cannot touch. Decision order
matters: paper terms, already-spelled runs, site labels, orbital labels,
hyphenated capital pairs, slash pairs, formulas, then acronyms. Formulas come
before acronyms so `HNO3` is a formula, not `H N O` plus a stray 3.

The legacy passes still own units, dashes and arrows, which design/90 and
design/217 already got right and which 71 existing assertions cover.

## Phase 2 — the paper's own dictionary (hybrid)

`spoken_text_for_tts(..., terms=...)` is wired and tested. A fractional doped
formula has no good deterministic reading: spelling `Ba0.5Sr0.5Co0.8Fe0.2O3`
gives "B A 0. 5 S R 0. 5", which is worse than the legacy expansion, so such
tokens are left alone for now. The authors call it **BSCF**; that has to come
from ingest. Filling `terms` from the survey pass and persisting it in
`session.json` is the next chip.

## Measured

- ground truth: **2/20 → 12/20** exact. Of the 8 remaining, 5 differ only in
  digits-versus-words (TTS reads digits correctly), 1 is a foreign-article URL
  that design/325 follow-up removes, and 2 are the markup gaps below.
- existing suites: **109 assertions pass**, including idempotence and the
  design/90 unit contracts.

## Scaling the review past twenty sentences

Hand-checking found the big classes; a linter found the rest.
`agent-tools/speak_lint.py` flags spoken output carrying the signature of a known
failure mode — an element name next to an unexpanded symbol, a lowercased letter
run, leftover markup or a tilde, a bare unit abbreviation, an unresolved slash,
a length blow-up against P9. Run over **2,451 sentences from 10 real papers**,
it found classes twenty hand-picked sentences had missed:

| found by the linter | was | now |
|---|---|---|
| `Kröger-Vink` | **krypton öger Vink** | Kröger Vink |
| `JEM-2200FS` | **J E M minus 2200 fluorine sulfur** | J E M 2200 F S |
| `NH4OH` | nitrogen H4 hydroxy | ammonium hydroxide |
| `H2/He` | hydrogen to **H E** | hydrogen to helium |
| `mV/decade` | millivolt **/decade** | millivolt per decade |
| `1/60 ratio` | **1/60** | 1 to 60 |
| `&amp;gt; 87%` | **&gt; 87%** | greater than 87% |
| `0.02°` (angle) | **0.02°** | 0.02 degrees |
| `BZY10` | **B Z Y 1 0** | B Z Y 10 |
| `C 1s` | **carbon 1s** | C one s |
| `~60` | **~60** | about 60 |
| `30 s`, `17.5 kV`, `10 mg`, `1 um` | printed as-is | seconds, kilovolts, milligrams, micrometers |

Flagged sentences fell from 130 to 74 on the first five papers as these landed.
A capitalised word that merely opens with an element symbol is now frozen as
printed, which is what stopped the `Kröger` class.

## Still flagged, with the honest reason

- **`lowercase_letter_run` (42)** — mostly subscripted single-letter variables
  (`d v i`, `delta t`, `V O`). Reading them as letters is defensible; there is no
  better deterministic answer without knowing the symbol's meaning.
- **`leftover_slash` (99)** — the large remainder is subscripted acronym ratios
  such as `STY_CH4/STY_CO2`. Needs the subscript folding below.
- **`element_then_digit` (37)** and **`composed_name` (26)** — coordination-site
  notation (`Co-Nx`, `M1-Nx`) and `Cs-corrected`. `N-doped` must stay
  "nitrogen doped" while `Cs-corrected` must become "C S corrected", so the two
  cannot be separated by shape alone. This needs a lexicon, not a rule.

## Not this chip

- `H<sub>2</sub>SO<sub>4</sub>` is not folded into one token, so the marked-up
  form misses `sulfuric acid` while the plain form gets it. Sub/sup folding
  across an intervening tag.
- `<i>t<sub>2g</sub></i><sup>5</sup>` loses the exponent for the same reason.
- Doped fractional formulas (waiting on Phase 2 terms).
- `Cs-corrected` versus `N-doped`: a symbol-hyphen-word lexicon.
- Chunk boundaries at breath/clause points — the one-breath rule is written
  down here but not yet enforced in `shadowing_chunk_plan`.

## Test

`tests/test_design_326_speak_tokens.py` — 27 cases, semantic assertions.
