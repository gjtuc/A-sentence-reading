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
- existing suites: **71 assertions pass**, including idempotence and the
  design/90 unit contracts.

## Not this chip

- `H<sub>2</sub>SO<sub>4</sub>` is not folded into one token, so the marked-up
  form misses `sulfuric acid` while the plain form gets it. Sub/sup folding
  across an intervening tag.
- `<i>t<sub>2g</sub></i><sup>5</sup>` loses the exponent for the same reason.
- Doped fractional formulas (waiting on Phase 2 terms).
- Chunk boundaries at breath/clause points — the one-breath rule is written
  down here but not yet enforced in `shadowing_chunk_plan`.

## Test

`tests/test_design_326_speak_tokens.py` — 27 cases, semantic assertions.
