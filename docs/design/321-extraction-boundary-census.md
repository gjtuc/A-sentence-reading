# 321 — Extraction boundary census

**Version:** 0.3.316 · Status: **locked**  
Amends [167](167-debone-quality-guards.md) · [151](151-layout-map-slot-carousel.md) · [124](124-missing-figures.md) · [14](14-vision-ocr-router.md) · [263](263-si-merge-integrity.md)

## Why

Sentence fidelity and figure/table completeness are the product. The guards that
existed caught *total* failure (zero sentences, no cache row, Azure raising) and
missed *partial* loss, because nothing counted what came in against what came
out.

Two measurements were taken downstream of the stage that loses content:

1. `debone_quality.compute_coverage_ratio` is called with the same string that
   was handed to debone. Whatever `section_flow` dropped, vision OCR blanked, or
   adjacent-article stripping removed is already outside the denominator, so the
   ratio prices Gemini only.
2. Figure slot count comes from parsed caption numbers; a body box raised the
   floor to exactly `1`. `LayoutMap.unused_boxes` was written for this and never
   called. Azure could locate 8 bodies, 5 could reach slots, and `fig_n=5` read
   green.

## Locked

### A. Sentence boundary

1. Keep the pre-filter text on the fresh-extract path. A vision resume starts
   from already-filtered pages, so it reports **no** census rather than a
   false 1.0.
2. After sentences are final, measure recall against that pre-filter text and
   emit handoff `extract_text` → `sentences_ready` with `in_n`/`out_n` chars,
   `source_coverage`, `debone_coverage`, `sentence_n`.
3. Warnings: `source_coverage_low:` (<0.50), `source_coverage_warn:` (<0.65),
   and `extract_filter_gap:` when debone coverage exceeds source coverage by
   more than 0.15 — that gap names extraction, not debone, as the loser.

### B. Figure boundary

4. `slot_census(layout, plan)` reports `body_n`, `slot_n`, `empty_n`,
   `partial_n`, `filled_n`, `unused_body_n`. `user_confirmed` counts as filled.
   Carried on `figure_extract_done`; zero when not the v2 path.
5. A raise must not leave the previous paper's census readable.
6. Verdicts: `figure_body_unslotted`, `figure_slot_collapse`,
   `figure_slot_partial`. All need `body_n > 0` to speak.
7. `append_unclaimed_body_slots` runs after caption pairing. Numbered captions
   keep their own slots; only leftover bodies get an appended slot, and each one
   is given its body immediately so it renders that crop under a generic label
   instead of a `(missing)` placeholder. Carousel stays figures-then-tables by
   number (design/92).

### C. Two silent erasures

8. An empty vision OCR return no longer overwrites a page PyMuPDF could read.
   It keeps the original and counts `vision_blank_kept:k/n`. A genuinely blank
   page is unaffected because the original is empty too.
9. SI merge passes `quality_flags` through. Rebuilding without it erased the
   ungrounded mark, making merged papers the one place the `원문 미확인` badge
   could not appear.

## Not this chip

- Turning the ingest quality banner on — still `showIngestQualityBanner = false`.
  Decide after live census numbers exist.
- Removing hallucinated sentences (design/167 keeps `환각 자동 삭제 금지`)
- bbox / aspect-ratio / blank-crop geometry gates
- Azure table cell structure (still bbox only)
- Multi-box server render (`body_box_ids[0]` still wins)
- The `fc-*` caption-rect bug
- Per-source-span accounting, text hashes, full fail-closed on low coverage
- Module-global extract state (concurrency)

## Test

`tests/test_design_321_extraction_census.py`
