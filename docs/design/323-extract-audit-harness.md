# 323 — Extract audit harness + ink clipping probe

**Version:** 0.3.317 · Status: **locked** (ops; no product bump)  
Amends [321](321-extraction-boundary-census.md) · [322](322-sentence-order-is-the-paper-order.md) · [302](302-azure-box-gate.md) · [128](128-clip-column-width.md)

## Why

Extraction fidelity and figure completeness now have counters
([321](321-extraction-boundary-census.md)) and an order rule
([322](322-sentence-order-is-the-paper-order.md)), but auditing a paper still
meant ad-hoc probing. Auditing *many* papers needs one command.

Clipping had no measurement at all. The only signal was
`is_caption_only_figure_png` — a single aspect-ratio test
(`height <= 400 and width > height*4`). A figure cropped to 60% of its extent
passed every guard.

## Locked

### A. Ink clipping probe — `pdf/clip_probe.py`

1. Measure ink, not shape. Threshold near-white as background
   (`INK_THRESHOLD = 240`), take the ink bounding box, and report which crop
   edges the ink reaches.
2. An edge counts as touched only when at least `MIN_EDGE_RUN_FRAC = 0.10` of
   that border line carries ink, so a stray speck or a thin frame is not a cut.
3. Two or more touched edges reads as cut: `figure_crop_edge_ink`.
   No ink at all: `figure_crop_blank`. Unreadable bytes report `None` and
   `figure_crop_unreadable` — never a guess.
4. Pure and offline. No Azure, no network, no paper text.

### B. Harness — `scripts/extract_audit.py`

5. One command per paper, repeatable over many: order (322), coverage (321),
   slot census (321), clipping (this chip).
6. Runs without Gemini by default — the non-LLM splitter stands in, which
   still exercises ordering. `--with-gemini` opts into a real debone.
   `--session` audits a stored session instead of re-splitting.
7. Azure is used when configured; `azure_unavailable` is reported, never
   substituted with PyMuPDF (design/302).
8. ASCII JSON, counts and offsets only (design/301 console rule).
   Exit 1 when any paper is flagged.

## Observed on a real cached paper (36c7a33ec665)

| Measure | Value |
|---|---|
| Azure figure/table bodies | 15 |
| Slots from caption numbers alone | **5** |
| Slots appended for unclaimed bodies (321 B7) | **10** |
| `unused_body_n` after append | 0 |
| Crops with ink off two edges | 1 |
| Stored-order backward steps | 61.2% |
| Recall against pre-filter text | 0.75 |

Before design/321 this paper's carousel had 5 entries while Azure had located
15 bodies: **two thirds of its figures and tables never reached the reader**,
with every counter green.

## Not this chip

- Turning the ingest quality banner on
- Acting on `figure_crop_edge_ink` in the product (probe and report only)
- A caption for appended slots beyond the generic `Figure N` / `Table N`
- The `fc-*` caption-rect bug, Azure table cell structure, module-global
  extract state (still design/321 「Not this chip」)

## Test

`tests/test_design_323_clip_probe.py`
