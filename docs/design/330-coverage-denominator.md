# 330 — The coverage denominator is the practice text

**Version:** 0.3.324 · Status: **locked**  
Amends [321](321-extraction-boundary-census.md) · [167](167-debone-quality-guards.md) · [263](263-si-merge-integrity.md)

## Why

design/321 measured recall against the whole extracted file. A reference list is
deliberately never practice text (design/263 L2 — a references chunk emits zero
sentences), so leaving it in the denominator makes correct behaviour read as loss.

Chasing the worst number in the ten-paper set showed exactly that. `srep41797`
had `source_coverage 0.4366`, which looked like 56% of the paper going missing.
Its section split is:

| part | chars |
|---|---|
| title | 3,647 |
| results | 15,217 |
| methods | 2,340 |
| acknowledgement | 1,527 |
| **references** | **23,090** |

Body total 22,731 of 50,975 raw characters is **44.6%** — almost exactly the
0.4366 that was reported. Nearly nothing of the body was actually lost.

## Locked

1. `practice_text_only(raw)` cuts the bibliography using
   `cite_refs.cut_bibliography_for_sentences`, the same cut the SI path already
   trusts. It is a **no-op** when no bibliography parses, so a paper with unusual
   back matter is unaffected and never loses body text from the denominator.
2. `coverage_excluding_references` is what `build_ingest_quality` and the
   design/321 census use.
3. The denominator is reported, not assumed: the `extract_text` →
   `sentences_ready` handoff carries `practice_chars` and `refs_share`.

## Measured, and its limit

| paper | refs share | coverage before | after |
|---|---|---|---|
| ACS Catalysis | 0.136 | 0.675 | **0.870** |
| Nano Letters | 0.309 | 0.560 | **0.732** |
| the other 8 | 0.0 | unchanged | unchanged |

The cut fires on 2 of 10 because `extract_bibliography` reads the **raw PyMuPDF**
text, whose column interleaving breaks the header heuristics on the rest. On the
Azure path `order_boxes` already isolates `references_text` — 23,090 characters
for `srep41797` — but `RecoverResult` does not carry it to the census. Threading
it through is the next chip, and `refs_share` is what makes the gap visible in the
meantime: a low coverage with `refs_share 0` is either real loss **or** an
unparsed bibliography, and the section census tells which.

## Correction to design/321 and 323

The earlier claim that "no paper reaches 0.75 recall" was partly an artefact of
this denominator. Two of the ten are above 0.87 and 0.73 once the bibliography
leaves the denominator, and the remaining low numbers still need the Azure
references length before they can be read as loss.

## Test

`tests/test_design_321_extraction_census.py` —
`test_design_330_references_leave_the_coverage_denominator`,
`test_design_330_cut_is_a_noop_without_a_bibliography`,
`test_design_330_denominator_is_reported_on_the_handoff`
