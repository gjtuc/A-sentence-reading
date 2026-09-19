# 337 — Geometry belongs to one job, and the pairing has to be counted

**Version:** 0.3.332 · Status: **locked**  
Follows [336](336-delete-only-what-you-can-name.md) · amends [321](321-extraction-boundary-census.md) · [324](324-unnumbered-rescued-figures.md)

## A. `_last_artifacts` crossed between concurrent ingests — a data defect

`extract_figures_v2` stashes the layout map and slot plan in module globals and
`app.py` reads them back. "Last" is process-global, not per-job:

- Cloud Run runs this service at `--concurrency 16` (`scripts/deploy_cloud_run.sh`).
- `_run_ingest_job` is a bare `asyncio.create_task` with no semaphore.
- `extract_figures` runs in a worker thread, so another job can overwrite the
  globals at any instant.

The census read sat close to the extract, but `get_last_layout_artifacts()` was
read **~500 lines and many awaits later**, and its value is **persisted** through
`save_paper_session(layout_artifacts=...)`. So paper A could store paper B's
`layout_map` and `slot_plan`, and every later slot re-render and figure edit for A
would then reason about B's geometry. That is a data defect, not a reporting one.

**Locked:**

1. `_last_key` records which document the globals describe.
2. `get_last_layout_artifacts(expect)` / `get_last_slot_census(expect)` return
   `None` on a key mismatch, and the artifacts path logs it. Calling without
   `expect` keeps the old behaviour for existing callers.
3. `extract_figures_v2` clears `_last_key` alongside `_last_census` on entry, so a
   raise cannot leave the previous paper's geometry readable.
4. `app.py` captures the artifacts **beside the extract** into
   `_layout_artifacts_early` and uses that local at the persist site, so the long
   window is gone rather than merely guarded. The local is initialised on the main
   path, not inside the `try` that fills it.

## B. The slot pairing was broken and nothing counted it

design/336 added `unnumbered_n` and it immediately reported **11 of 24** on
`catalysts-13-01171`. Pulling that thread found the label was the symptom, not the
defect. Per-slot provenance on that paper:

| | count | what the reader gets |
|---|---|---|
| caption, no image | 7 | a figure description with no picture |
| caption + image | 6 | correct |
| image, no caption | 11 | `번호 없는 그림` at carousel positions 12–21 |

An 11-figure, 2-table paper produces **24 carousel slots**, with the same figure
appearing twice.

It is not one paper. Across the ten-paper audit (`agent-tools/slotaudit.py`):

| paper | caption w/o image | paired | image w/o caption | slots |
|---|---|---|---|---|
| `catalysts-13-01171` | 7 | 6 | **11** | 24 |
| ChemistryOpen | 0 | 6 | **8** | 14 |
| `d4cs00527a` | 1 | 27 | 13 | 41 |
| Adv. Mater. | 2 | 8 | 6 | 16 |
| `cs5b00357` | 1 | 14 | 4 | 19 |
| `srep41797` | 1 | 9 | 1 | 11 |
| **total** | **13** | **92** | **51** | 157 |

**51 of 157 slots (33%) are images with no caption.** Azure splits a multi-panel
figure into several `figure_body` boxes — note the body/caption counts, e.g. 39
bodies against 54 captions on `d4cs00527a` — and `_nearest_caption_for_body`
(`slot_plan.py:401`) only accepts a caption whose horizontal centre is within 48pt
of the body's, so panel sub-boxes miss their own caption's slot.
`append_unclaimed_body_slots` then gives each orphan panel its own carousel entry.

design/321 introduced that append to stop panels being dropped entirely. So the
trade was **missing panels → duplicate entries**. Neither is the paper.

**Locked for this chip:** the pairing is now measured in production.
`slot_census` reports `caption_without_body_n` and `body_without_caption_n`
alongside the existing counters, which stay green on exactly this input —
`unused_body_n` is 0 and `slot_n >= body_n` holds, which is why the pairing needed
counters of its own (design/336 D).

**Not fixed here.** The repair is to attach extra panels to their caption's slot as
additional `body_box_ids` and composite them, which also requires the multi-body
render path — `_render_slot_png` uses `body_box_id` only, so a slot with three
panels renders one. That is a chip with its own measurement, not a change to make
while the numbers are this fresh.

## Not this chip

- Widening `_nearest_caption_for_body` beyond the 48pt centre test
- Rendering every `body_box_ids` entry instead of only the first
- The adjacent-article trim running before `text_pre_filter` is snapshotted
- Resumed jobs emitting no design/321 reporting at all
- Unsticking `in_refs` (carried from design/335)

## Test

`tests/test_design_337_artifacts_key.py` — the matching document is served, another
document is refused, the live A→B→A race is caught, an absent expectation keeps the
old behaviour, a cleared key refuses everything, and the pairing census counts both
halves while the old verdicts read green on the same plan.
