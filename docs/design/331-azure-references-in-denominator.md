# 331 — Azure's bibliography reaches the recall denominator

**Version:** 0.3.325 · Status: **locked**  
Amends [330](330-coverage-denominator.md) · [321](321-extraction-boundary-census.md) · [31](31-reading-order.md)

## Why

design/330 removed the bibliography from the recall denominator using
`cite_refs.cut_bibliography_for_sentences`, which reads the **raw PyMuPDF** text.
That text interleaves columns, so the header heuristics found nothing on 8 of 10
papers and the cut was a no-op exactly where it was needed most.

`order_boxes` already isolates `references_text` on the Azure path — 23,090
characters for `srep41797` — but `RecoverResult` dropped it on the floor.

## Locked

1. `RecoverResult.references_text` carries what `order_boxes` isolated.
2. `coverage_excluding_references(raw, sentences, references_text=...)` removes
   the bibliography by **token set**, not by slicing. Azure's references text is
   a reordering, not a substring of the raw text, so a slice cannot align.
3. A token the body also uses is kept. Only references-only tokens leave the
   denominator, so a real body loss cannot hide behind a shared word.
4. `practice_token_n` is the denominator the ratio was actually divided by, and
   it is reported with `azure_refs_chars` on the
   `extract_text` → `sentences_ready` handoff.

## Measured across the ten-paper set

| paper | raw | design/330 | **design/331** | Azure refs chars |
|---|---|---|---|---|
| Sci Rep | 0.437 | 0.437 | **0.643** | 23,090 |
| Chem Soc Rev | 0.613 | 0.613 | **0.829** | 29,092 |
| Chem Eng J | 0.580 | 0.580 | **0.799** | 10,972 |
| Science | 0.476 | 0.476 | **0.606** | 6,246 |
| Korean J Chem Eng | 0.733 | 0.733 | **0.850** | 807 |
| ACS Catalysis | 0.675 | 0.870 | 0.872 | 3,163 |
| Catalysts | 0.788 | 0.788 | 0.798 | 1,699 |
| Nano Letters | 0.560 | 0.732 | 0.715 | 4,978 |
| Adv Mater | 0.850 | 0.850 | 0.850 | **0** |
| ChemistryOpen | 0.646 | 0.646 | 0.646 | **0** |

Median recall moves from about 0.62 to about 0.80. Four papers are now above
0.82.

## What is still real loss

Sci Rep sits at 0.643 with its bibliography fully out of the denominator, so
roughly a third of its body tokens genuinely never become sentences. That is now
a believable number to chase instead of the earlier 0.437, which was mostly the
metric.

Adv Mater and ChemistryOpen report `azure_refs_chars 0`: `header_key` did not
recognise their references heading, so their denominators still carry the
bibliography. A review's reference list is large, so their true recall is higher
than shown.

## Not this chip

- Teaching `header_key` the remaining references headings
- Chasing the residual Sci Rep loss
- Excluding acknowledgements, author contributions and declarations, which are
  also never practice text

## Test

`tests/test_design_321_extraction_census.py` —
`test_design_331_azure_references_leave_the_denominator`,
`test_design_331_shared_tokens_stay_in_the_denominator`,
`test_design_331_denominator_size_is_reported`
