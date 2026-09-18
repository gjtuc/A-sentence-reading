# 332 — A reference list with no heading is still a reference list

**Version:** 0.3.326 · Status: **locked**  
Amends [31](31-reading-order.md) · [263](263-si-merge-integrity.md) · [331](331-azure-references-in-denominator.md) · [302](302-azure-box-gate.md)

## Why

design/331 found two of ten papers reporting `azure_refs_chars 0`. Chasing why
showed that neither prints a `References` heading at all: Wiley (Adv Mater,
ChemistryOpen) puts the numbered list straight after `Acknowledgements`.

`header_key` therefore never opened a references section, and design/263's
"a references chunk emits zero sentences" never applied. The entries became
**practice sentences**:

| paper | reference entries served as sentences |
|---|---|
| Adv Mater 2021 review | **106 of 496 (21.4%)** |
| Catalysts (MDPI) | **38 of 344 (11.0%)** |

More than one practice sentence in five asked the reader to say
`A. Author, B. Author, Adv. Mater. 2019, 31, 1234` aloud. That is the opposite of
what practice mode is for, and it is exactly the 「불필요한 것」 the product is
supposed to remove.

`_is_bibliography_line` already existed but was only consulted to decide whether
to keep a footnote-tagged box, never to route a section.

## Locked

1. `_retag_bibliography_runs` runs after `_read_page` has assigned keys and
   before sections are grouped, so the column logic is untouched
   (design/302 — do not change the ordering while the box gate is the contract).
2. **Two consecutive** bibliography lines switch the section to `references`. One
   numbered line in the middle of prose does not.
3. The first line of a run is retagged too, even though the run only tipped over
   on the second.
4. An explicit heading always ends the run, so a journal that prints Methods
   after References recovers. The pass never overrides `_read_page`'s key for a
   heading box; it only stops treating what follows as references.

## Measured

| paper | sentences | reference entries as sentences | `azure_refs_chars` |
|---|---|---|---|
| Adv Mater | 496 → **373** | 21.4% → **0%** | 0 → **15,080** |
| Catalysts | 344 → **263** | 11.0% → **0%** | 0 → **15,706** |

This also completes design/331 for those two papers: their recall denominators
now see the bibliography they were previously counting as lost body.

`azure_box_gate --fixtures-only` stays green, including `refs_not_practice`.

## Not this chip

- Acknowledgements, author contributions and conflict-of-interest statements are
  still practice text. They are short, but they are not the paper.
- Chasing the residual Sci Rep loss (0.643 with references excluded)

## Test

`tests/test_section_flow.py` —
`test_design_332_headingless_reference_list_is_not_practice`,
`test_design_332_a_single_numbered_line_is_not_a_reference_list`,
`test_design_332_a_heading_after_the_list_stops_the_run`
