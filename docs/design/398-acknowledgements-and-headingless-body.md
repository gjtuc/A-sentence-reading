# 398 — Acknowledgements leave the reader; a headingless Body is not a fault

## What the phone showed (0.3.437, Adv Mater 2016 Pt–Co Communication)

- The reader ended with an `Acknowledgements` section: funding and thanks, read as
  practice sentences.
- The section bar showed `Body ⚠` (`high_body_ratio:0.97`).

## Why

An Adv Mater Communication prints no Introduction, Experimental, Results or
Conclusion. Azure's own `sectionHeading` tags on this paper are exactly two:
`Supporting Information` and `Acknowledgements`. Every sentence is Body because the
paper has nothing else, so the `high_body_ratio` warning (design/167) reports the
paper's shape as a failed split.

Measured on three papers with the rule in `pdf/body_headings.py`:

| paper | sectionHeading tags | body headings |
|---|---|---|
| Adv Mater Communication | 2 | 0 |
| Elsevier Appl Catal B article | 16 | 14 |
| ACS Nano article | 4 | 3 |

## Rules

### Acknowledgements

`debone_quality.drop_acknowledgement_sentences` removes sentences whose section is
Acknowledgement(s) only when **all** hold:

- the source prints the heading: the section mark
  `<<<ASR_SECTION acknowledgement>>>` is in the debone input, or a short line
  (≤ 40 chars) has `header_key == "acknowledgement"`;
- the section is at most `ACK_DROP_MAX = 12` sentences;
- and at most `ACK_DROP_SHARE = 10%` of the paper.

Otherwise the sentences stay and `acknowledgement_kept:N` is recorded. A drop
records `acknowledgement_dropped:N`. A model labelling body prose as
Acknowledgements cannot delete a page this way.

The dropped sentences are still passed to `build_ingest_quality`, so the coverage
measure does not count a deliberate drop as text the reader lost.

### Headingless Body

`pdf/body_headings.ordered_with_body_headings` is `azure_ordered_pages` with the
body heading count taken from the same analyze call (no second Azure call).
`vision_ocr` records `body_headings:N`.

A body heading is a `sectionHeading` box whose `header_key` is not title,
abstract, references, acknowledgement, appendix, declaration or credit, and is not
apparatus (Supporting Information, Keywords, Conflict of Interest, Author
Contributions, Data Availability, Funding, Notes, Abbreviations, Associated
Content). An untagged short box (< 80 chars) whose `header_key` is a body key also
counts.

At the split handoff, `quiet_headingless_body` renames `high_body_ratio:X` to
`body_ratio_headingless:X` only when `body_headings:0` is present. The phone and the
web match the `high_body_ratio` prefix, so the ⚠ and the quality banner do not fire.
Without the signal (no Azure, PyMuPDF path) the warning stands.

`section_flow.py` is not edited: `azure_box_gate.py` reports `live_ok False` on this
paper because a Communication has no abstract, introduction or experimental heading
to find.

## Scope

Both changes act at ingest. A paper already in the library keeps its stored
sentences and warnings until it is analyzed again.

## Not addressed here

- Reference 9 of the Pt–Co main is still missing (22 of 23 parsed).
- On the Azure path the section text arrives as one long line, so the per-line
  chrome filter in `strip_back_matter` can wipe a whole section from the coverage
  denominator (`practice_chars 30`).

## Tests

`tests/test_design_398_ack_and_headingless_body.py`
