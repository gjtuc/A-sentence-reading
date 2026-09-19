# 336 — Delete only what you can name, and say how much

**Version:** 0.3.331 · Status: **locked**  
Extends [335](335-references-pin-is-not-evidence.md) · amends [263](263-bibliography-not-practice.md) · [321](321-extraction-boundary-census.md) · [330](330-coverage-denominator.md) · [333](333-coverage-denominator-correction.md)

## Why

design/335 made the section **pin** prove its case before deleting text. Two
read-only audits of the whole backend for that same shape — an upstream label
causing unverified deletion, and a metric naming the wrong cause — found the duty
had not been applied evenly. Five findings survived verification.

Not everything the audits raised was real; see **Rejected** below. Each item here
was reproduced first.

## A. `chunk_kind`'s own `references` verdict deleted whole chunks, unaccounted

`chunk_kind` searches only `chunk[:800]` for a bibliography heading, and the
`extract_bibliography(chunk) >= 2` short-circuit returns `"references"` *before*
the prose-line check runs. `_process_chunk_with_guard` then emptied the chunk with
`ok=True`, `bib_chars_dropped=0`, no warning, and no entry in `chunks_failed`.

This is design/335 inverted. There, the pin deleted and the text heuristic was
misreported as the failing party; here the text heuristic is the one deleting, and
it was trusted absolutely. It is the worse of the two, because design/335 at least
produced a wrong non-zero signal somebody could chase.

Reproduced:

| chunk shape | `chunk_kind` |
|---|---|
| `References` + entries + 3 paragraphs of appendix prose | `references` |
| 1 paragraph of prose + `References` + entries | `references` |
| `Acknowledgements` + prose (no parseable entries) | `substantive` |

So prose both **after** and **ahead of** the heading was condemned, the second
whenever the heading still lands inside the 800-character window.

**Locked:** both routes now run the same design/335 pair —
`split_off_bibliography_lines` then `pin_rescue_worth_keeping` — and
`bib_chars_dropped` is set on both. `ChunkStat.references_verdict` records which
signal decided (`"pin"` or `"kind"`), and the aggregate reports
`references_pin_rejected` and `references_kind_rejected` separately so the two are
never conflated.

The audits' `Acknowledgements → References → Appendix` example does **not**
reproduce: `extract_bibliography` needs a bibliography heading to locate entries,
so that chunk falls through to the prose-line check, which saves it. The live
trigger is a `References` heading, not the alias.

## B. `bib_chars_dropped` was write-only

design/335 added the counter so bibliography deletion is "reported instead of
assumed." It reached `to_dict()` and the cache and stopped: `quality_to_warnings`
never turned it into a string at any magnitude, so a 12,000-character deletion and
a 0-character one read identically to anything that greps warnings.

**Locked:** `BIB_DROPPED_REPORT_CHARS = 400` emits `bib_chars_dropped:N`. Measured
bibliographies in the 10-paper audit run 467 to 18,398 characters, so this fires
routinely by design — the point is that the number is never silent.

## C. The implausible-cut guard lived in dead code

`practice_text_for_coverage` carried design/333's refusal —
`len(cut) < len(text) * 0.25 → keep the original` — and had **no callers** in
`src/`, `scripts/` or `tests/`. The live denominator is `practice_text_only`, and
it ran unguarded. `bibliography_header_start` returns the *first* match with no
position floor, so an SI cover sheet or a "see References therein" near the top
could cut the paper away.

The consequence compounds with design/333's own floor: a collapsed denominator
makes `source_coverage_warnings` return `coverage_denom_too_small` and **suppress**
`source_coverage_low` and `extract_filter_gap`. A paper that lost most of its body
would report a measurement problem instead of a loss.

**Locked:** `PRACTICE_CUT_MIN_SHARE = 0.25` moves into `practice_text_only`, and
`practice_text_for_coverage` becomes an alias so the two cannot drift again.

## D. Both design/321 slot verdicts are dead by construction

`slot_census` computes `unused_body_n` from `layout.unused_boxes(...)`, but
`append_unclaimed_body_slots` has already given every leftover body a slot and
marked it used. So `unused_body_n` is identically 0 and `slot_n >= body_n` always
holds, which kills both `figure_body_unslotted` and `figure_slot_collapse`. All
ten audited papers report `unused_body_n: 0`.

Meanwhile the loss that survives the repair is design/324's: a slot whose `n` is a
carousel position rather than a printed label. `Slot.unnumbered` marks it, and
nothing counted it.

**Locked:** `slot_census` reports `unnumbered_n`.

## E. `section_flow` deleted at six gates and counted none

Measured across ten papers, the role-label gate alone removes 188 to 8,724
characters per file, and `order_boxes` had no counter of any kind. A coverage gap
therefore could not be told apart from a mislabelled body paragraph — and design/321's
`source_coverage` cannot help, because `text_pre_filter` for the Azure path is
already `ordered.marked_text`, i.e. post-drop.

**Locked:** `OrderedPaper.drop_census` counts boxes and characters per named
reason: `figure_table_kind`, `role_pageheader` / `role_pagefooter` /
`role_pagenumber`, `footnote`, `chrome_text`, `publisher_banner`, plus
`buried_in_figure_n`, `buried_in_table_n`, `front_matter_n`,
`retagged_references_n` and `dropped_not_sentence_n`. `_drop_chrome` keeps its
boolean signature and delegates to the new `_chrome_reason`.

`retagged_references_n` is the one to watch: it counts boxes the sticky `in_refs`
run relabelled, which is design/335's root cause made visible at its origin
instead of only at the deletion gate.

## Rejected after measurement

- **"Do not trust the `pageheader`/`pagefooter` role label."** Audited: of the 42
  prose-shaped boxes those labels dropped across ten papers, **all 42 were genuine
  chrome** — running heads, Wiley/RSC download banners, Creative Commons lines.
  Several are ones `_CHROME` alone misses, because `©` extracts as `@`. Distrusting
  the label would have pushed roughly 11,000 characters of boilerplate into
  practice. The lesson from design/335 is not "never trust a label", it is **bound
  the blast radius**: chrome labels delete a repeating 50–370 character box, the
  references pin deleted 5,000-character body chunks.
- **"`sentence_order_backward` counts one step for a relocated section."** False.
  `high` is a running maximum, so every sentence in a displaced block scores. The
  real caveat is the reference order: it is PyMuPDF's linearisation, which is the
  thing Azure exists to correct, so a high percentage does **not** establish that
  the paper is scrambled — only that the two disagree.
- **`debone.py` `section == "skip"`.** Dead code. `_SECTION_ALIASES` has no `skip`
  entry and `_normalize_section` defaults to `body`, so the branch cannot fire. It
  fails open (content is kept), so it is not a loss.

## Not this chip

- The adjacent-article trim runs before `text_pre_filter` is snapshotted, and
  `_ = adj_plan` discards the page counts the plan already computed
- Resumed jobs skip the whole design/321 reporting block and emit nothing in its
  place, so "clean" and "unmeasured" look alike
- `_last_census` / `_last_artifacts` are module globals read across `await`, with
  no ingest concurrency limit — a data hazard, not only a reporting one
- `coverage_excluding_references` is token-**set** recall, so paragraph-scale loss
  barely moves it
- Client warning allowlists match five hand-listed prefixes and miss every warning
  added since design/321; the banner is hard-disabled anyway
- Unsticking `in_refs` (carried from design/335)

## Test

`tests/test_design_336_delete_only_what_you_name.py` — the reproduced `chunk_kind`
triggers including the alias that does *not* fire, prose surviving on both sides of
the heading, a real bibliography still dropped without calling the model, the two
routes reported apart, the counter becoming a warning above the floor and staying
quiet below it, and the live denominator refusing an implausible cut while still
making a plausible one.
