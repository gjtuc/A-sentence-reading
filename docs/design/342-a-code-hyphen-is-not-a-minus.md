# 342 — A hyphen inside a code is not a minus, and not a range

**Version:** 0.3.337 · Status: **locked** · speak_norm **v10**  
Continues [341](341-unit-grammar-and-the-ratio-slash.md) · amends [217](217-dash-vs-minus.md)

## Why

The plan for this chip was a compound-name lexicon, because design/341 left 18
defects in the naming families. Ranking the chemical tokens that actually produce
bad speech put something else first:

```
BZY10-1700   ->   "B Z Y 10 minus 1700"
```

A sample code, read as a subtraction. It appears in **66 sentences of one paper**.

**The linter never flagged it.** It has no check for a wrongly voiced dash, so 66
defective sentences sat outside the 45 the linter was reporting. The corpus token
ranking (`agent-tools/chemtokens.py`) found it. The linter now has the check, so it
cannot come back unnoticed.

## Locked

Three rules had to move, because silencing each one exposed the next.

1. **`_dash_pass_a` no longer reads a hyphen after a frozen token as a unary
   minus.** design/217 guards mid-token hyphens with `(?<![A-Za-z0-9.])`, but
   after `freeze` the left neighbour is a placeholder, which is none of those. The
   placeholder mark joins the guard.
2. **`restore` silences a hyphen glued to a placeholder.** With the minus gone, a
   later range rule said "B Z Y 10 **to** 1700". The placeholder proves the two
   halves are one name, which is how `BZY10-ZnO` has always read.
3. **A leading zero marks a code, not a range.** The linter's new check immediately
   found a second shape: `award DMR 08-019762` was read as "08 **to** 019762". A
   printed range never writes its bounds with a leading zero. The check is on
   integers only — `0.5-1.5 V` is a decimal range and still says "to".

While merging the two range rules in `spoken_post`, the unguarded one was undoing
the guarded one's decision, so they are now a single rule that also accepts decimals
and spaced dashes.

## What it now says

| printed | before | after |
|---|---|---|
| `BZY10-1700` | B Z Y 10 **minus** 1700 | B Z Y 10 1700 |
| `award DMR 08-019762` | 08 **to** 019762 | 08-019762 |
| `10-1700 K` | 10 to 1700 kelvin | unchanged |
| `1.08-2.15 mm` | 1.08 to 2.15 millimeters | unchanged |
| `0.5-1.5 V` | 0.5 to 1.5 volt | unchanged |
| `-70 kJ/mol` | minus 70 | unchanged |
| `10-3` | ten to the minus 3 | unchanged |
| `BZY10-ZnO` | B Z Y 10 zinc oxide | unchanged |

## Not done, and why

**The compound-name lexicon was deferred deliberately.** Reading
`_is_complex_formula` shows the current spelling is a *product decision*, not a
defect: "Three or more element symbols has no single spoken name a reader expects
(LaNiO3, NiCo2O4). Spelling them is honest; composing a name is not." So
`CoFe2O4` → "C O F E 2 O 4" is the locked choice, and design/326 Phase 2 (the
paper's own term dictionary) is the designated answer.

There is a question worth putting to the product owner rather than settling in code:
spelling by letter destroys the symbol boundaries — a listener cannot tell `Co` from
`C O`, or `Fe` from `F E`. Reading the element names (`cobalt iron two oxygen four`)
composes no name and keeps the information. That is a change of reading, not of
policy, but it is the owner's call.

## Not this chip

- The compound-name lexicon / design/326 Phase 2
- Whether a 3+ element formula should be read by element name instead of letters
- Funding and acknowledgement sentences as practice text — both remaining
  `voiced_dash_in_code` and `range_dash` hits live in them, and design/340 left
  acknowledgement prose alone on purpose
- `γ` for `y` and `0` for `o` inside words on one RSC paper (`catal<γ>st`,
  `phen0men0n`) — that is an extraction defect, not speech

## Test

`tests/test_design_342_sample_code_hyphen.py` — the code with a number suffix, two
codes in one sentence, the formula-suffix code that already worked, other code
shapes, negative numbers and decade powers that must stay a minus, five printed
range shapes including decimals and spaced dashes, a range following a frozen token,
grant numbers, the leading-zero rule applying to integers only, element and technique
hyphens, and idempotence.
