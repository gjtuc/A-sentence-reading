# 328 — A variable's exponent is not a citation, and a spelled run is not a formula

**Version:** 0.3.322 · Status: **locked**  
Amends [326](326-practice-speech-tokens.md) · [216](216-cite-display-tts-practice-consistency.md)

## Why

design/326 recorded two remaining speech defects as "sub/sup folding gaps".
Tracing the pipeline stage by stage showed both diagnoses were wrong.

### A. `_SPELLED_RUN` was splitting formulas

design/326 added `_SPELLED_RUN` so an already-spelled acronym (`N M R`) survives a
second pass unchanged, which is what keeps the transform idempotent. Its lookahead
was `(?![A-Za-z])`, so on

```
0.1 M H2SO4
```

it matched **`M H`** — two single capitals separated by a space, followed by `2`,
which is not a letter. The acid was frozen apart and its tail `2SO4` reached the
element passes as `sulfur O four`. The plain form `H2SO4` was correct all along,
which is why this looked like a markup problem.

The lookahead is now `(?![A-Za-z0-9])`. `B Z Y 10` and `C N Ts` still hold,
because in those the run is followed by a space.

### B. design/216 was eating exponents

design/216 strips a numeric `<sup>n</sup>` before the HTML-to-spoken pass because
in ACS text that is a reference marker. On

```
<i>t<sub>2g</sub></i><sup>5</sup>
```

it deleted the `5`, so the ear received `t two g` where the paper printed
`t2g^5`. That breaks design/326 P10 — never change a value — and it is silent.

## Locked

1. `protect_variable_exponents(raw)` runs **before** the citation rule and marks
   a numeric superscript that follows an italic single letter with an optional
   subscript (`<i>t<sub>2g</sub></i>`, `<i>x</i>`). Nothing about design/216
   changes; the citation rule simply never sees a marked exponent.
2. The italic body must be one letter, so an italic journal name followed by a
   real reference marker is untouched.
3. `resolve_variable_exponents` renders the mark after the HTML pass:
   `to the 5`, and `~1.2` becomes `to the about 1.2`.
4. `_SPELLED_RUN` does not match when a digit follows.

## Measured

| input | before | after |
|---|---|---|
| `0.1 M H<sub>2</sub>SO<sub>4</sub>` | 0.1 molar **H2 sulfur O four** | 0.1 molar sulfuric acid |
| `<i>t<sub>2g</sub></i><sup>5</sup>` | t two g (**5 lost**) | t two g to the 5 |
| `major contributors.<sup>12</sup>` | contributors. | contributors. (unchanged) |

Idempotence holds on every case in the design/326 probe set.

## Test

`tests/test_design_326_speak_tokens.py` —
`test_marked_up_formula_is_named_too`,
`test_a_spelled_run_is_still_stable_next_to_a_number`,
`test_variable_exponent_is_not_eaten_as_a_citation`,
`test_a_real_citation_marker_is_still_stripped`
